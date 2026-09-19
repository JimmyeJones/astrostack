"""
Build and persist master calibration frames.

A *master* is the per-pixel combination of many same-kind raw frames (darks,
flats or bias). Combining many frames beats out the read noise so the master
is a clean estimate of the fixed pattern we want to remove.

Combination methods
-------------------
``median``       — per-pixel median. Robust default: rejects cosmic-ray hits,
                   satellite trails and the odd warm pixel without tuning.
``sigma_mean``   — iterated sigma-clipping (reject pixels more than ``sigma``
                   MADs from the per-pixel median, recomputing the scale over the
                   survivors until it converges) then mean of what survives.
                   Slightly lower noise than the median when the inputs are clean.
``mean``         — plain average. Lowest noise, but no outlier rejection.

Memory
------
Combining needs the frames stacked in RAM (median/clip aren't single-pass), so
we cap the number actually loaded (``max_frames``, evenly sampled) to bound
peak memory. The combine holds one contiguous ``(N, H, W)`` float32 stack (the
per-frame arrays are dropped once it's built) and masks non-finite samples in
that same buffer, so peak is roughly one stack plus transients — for
Seestar-sized frames (~8 MB/frame as float32) 64 frames is ~0.5 GB of stack
(~1 GB peak with the isfinite/reduction transients), fine for a one-off
calibration job.
"""

from __future__ import annotations

import logging
import math
import warnings
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

import numpy as np

log = logging.getLogger(__name__)

ProgressFn = Callable[[str, int, int], None]

VALID_KINDS = ("dark", "flat", "bias")
VALID_METHODS = ("median", "sigma_mean", "mean")


@dataclass
class MasterMeta:
    """Provenance / matching metadata stored alongside a master frame."""

    kind: str  # 'dark' | 'flat' | 'bias'
    n_frames: int
    width_px: int
    height_px: int
    method: str
    # Acquisition parameters the master should be matched against. None when the
    # source headers didn't carry the value.
    exposure_s: float | None = None
    gain: float | None = None
    sensor_temp_c: float | None = None
    # The coldest and warmest frame that actually went into the combine, in °C —
    # the two numbers ``sensor_temp_c``'s median sits between. A single stamped
    # temperature is a *claim that the set was uniform*, and nothing about a
    # folder of darks enforces it: a Seestar's sensor is uncooled, so it follows
    # the night and the season, and one folder can hold a cold night and a warm
    # one. Dark current roughly doubles every 6-7 °C, so such a master is a blend
    # of two dark currents and its stamped value is a middle no frame was shot
    # at — which the mismatch advisory then finds a perfect match for.
    #
    # Unlike :attr:`n_supplied` and :attr:`header_kinds` these **are** written
    # into the master's FITS header, because they are part of what the master *is*
    # rather than how it was built: a master reloaded off disk has to still be
    # able to say that its stamped temperature is a middle. ``None`` when no
    # source frame recorded a temperature, and on every master built before this
    # field existed — both of which read as "didn't say", never as "uniform".
    sensor_temp_min_c: float | None = None
    sensor_temp_max_c: float | None = None
    bayer_pattern: str | None = None
    # How many frames the caller actually supplied, before the ``max_frames``
    # memory bound sampled the set down. ``None`` when unknown — it is a
    # *build-time* fact, not part of the master's identity, so it is deliberately
    # not written into the FITS header and a master loaded back from disk reports
    # ``None`` rather than a number it can't stand behind. Equal to
    # :attr:`n_frames` plus any skipped frames when no sampling happened; larger
    # when it did, which is the only case worth telling the user about.
    n_supplied: int | None = None
    # What the combined frames' own ``IMAGETYP`` cards said, as
    # ``{'dark': 40}`` — a tally over the frames that actually went into the
    # master, counting only *recognised* values (see
    # :func:`seestack.io.fits_loader.frame_kind_from_header`). Empty when no
    # frame carried a card we recognise, which is the common case for cameras
    # that don't write one and must read as "unknown", never as a mismatch.
    # Build-time provenance like :attr:`n_supplied`: not written into the master's
    # FITS header, so a master loaded back off disk reports ``None``.
    header_kinds: dict[str, int] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _sigma_clip_mean(stack: np.ndarray, sigma: float, max_iters: int = 5) -> np.ndarray:
    """Iterated per-pixel sigma-clip about the median, then mean of the survivors.

    ``stack`` is (N, H, W). Uses the MAD (scaled to σ) as a robust scale so a
    couple of outlier frames don't inflate the rejection threshold. The clip is
    repeated — recomputing the median and MAD over the *surviving* samples each
    round and only ever removing more — until the kept set stops changing or
    ``max_iters`` rounds elapse. This matches how DSS/Siril/PixInsight combine
    masters: after the first round removes the grossest outliers the recomputed
    scale is tighter and catches milder ones that a single round leaves in.
    """
    # The kept set only shrinks (a rejected sample never returns), so iterating
    # is guaranteed to converge; the max_iters cap is just a belt-and-braces bound.
    kept = np.ones(stack.shape, dtype=bool)
    for _ in range(max(1, max_iters)):
        masked = np.where(kept, stack, np.nan)
        with np.errstate(invalid="ignore"):
            med = np.nanmedian(masked, axis=0)
            mad = np.nanmedian(np.abs(masked - med), axis=0) * 1.4826  # MAD → σ
        # mad==0 means the surviving *majority* sits exactly at the median — NOT
        # that there are no outliers. A minority cosmic-ray/hot-pixel spike
        # routinely coexists with mad==0 (common on quantised bias/dark frames),
        # so substituting +inf here would keep the spike and bake it into the
        # master. Use tol=0 instead: only the exact-median samples survive, so the
        # result degrades to the (robust) median there and the spike is rejected.
        tol = sigma * np.where(mad > 0, mad, 0.0)
        new_keep = kept & (np.abs(stack - med) <= tol)
        if np.array_equal(new_keep, kept):
            break
        kept = new_keep
    # Mean over the kept samples; fall back to the (always-finite) full-stack
    # median where nothing survived, exactly as the single-round version did.
    with np.errstate(invalid="ignore"):
        out = np.nanmean(np.where(kept, stack, np.nan), axis=0)
        # NaN-aware so the fallback is genuinely finite wherever *any* sample is
        # finite (a plain median would return NaN at a pixel that has even one NaN
        # input, defeating the "always-finite" fallback on a partially-NaN stack).
        full_med = np.nanmedian(stack, axis=0)
    return np.where(np.isfinite(out), out, full_med).astype(np.float32, copy=False)


def _exposure_in_group(
    value: float, group: Sequence[float], *, allow_zero: bool = False,
) -> bool:
    """Is ``value`` one of the lengths in ``group``, within the module's own
    "is this the same exposure?" tolerance? Header rounding (9.998 against 10.0)
    is the same length; a real Seestar step (10 → 30 s) is not.

    ``allow_zero`` adds **0 as a length of its own**, matching only another 0.
    It is off by default, and on only for a bias, because a bias is *defined* as
    the zero-length readout: a camera that writes ``EXPTIME = 0`` is stating the
    frame's whole identity, where for a light or a dark the same card means
    nothing usable and is dropped (see
    :func:`seestack.calibrate.apply.distinct_exposures`). A relative tolerance
    cannot express it — ``0`` is 100 % away from every positive length and
    ``0/0`` is not a ratio — so it is an exact match rather than a new
    threshold.
    """
    from seestack.calibrate.apply import EXPOSURE_MISMATCH_TOL

    if allow_zero and value == 0.0:
        return any(g == 0.0 for g in group)
    return any(abs(value / g - 1.0) <= EXPOSURE_MISMATCH_TOL
               for g in group if g > 0)


def _majority_exposure_group(
    values: Sequence[float | None], *, allow_zero: bool = False,
) -> list[float] | None:
    """The exposure length most of these frames were shot at, as the list of
    raw values belonging to that group — or ``None`` when there is nothing to
    gate on (no recorded exposure, or only one length, which is every ordinary
    folder).

    Grouped by :func:`seestack.calibrate.apply.distinct_exposures`, the same
    grouping the dark advisory and the binder use, so "two exposures" means the
    same thing everywhere. Ties keep the **shortest** length, because
    ``distinct_exposures`` reports groups shortest-first and the first maximum
    wins — deterministic, and exactly the shape-rule's own tie-break.

    ``allow_zero`` carries a **0 s** group alongside them, for a bias. It has to
    be added here rather than inside ``distinct_exposures``, which drops a
    non-positive value on purpose: for a light or a dark "0 s" is a blank card,
    not a length. For a bias it is the length — and dropping it is what made the
    commonest contaminated-bias folder invisible, because a set of 0 s frames
    plus a stray 10 s dark grouped as *one* length (10 s) and gated on nothing.
    The 0 s group is still only a candidate for the majority, so a lone
    zero-stamped frame among real ones is the minority and is the frame that
    gets set aside — never the other way round, which is the whole point of
    taking a majority rather than the shortest.
    """
    from seestack.calibrate.apply import distinct_exposures

    vals = [float(v) for v in values
            if v is not None and math.isfinite(float(v))
            and (float(v) > 0 or (allow_zero and float(v) == 0.0))]
    groups = distinct_exposures(vals)
    if allow_zero and any(v == 0.0 for v in vals):
        groups = [0.0] + groups   # shortest-first, so the tie-break is unchanged
    if len(groups) < 2:
        return None  # nothing to split — behaviour is byte-identical
    members: list[list[float]] = [[] for _ in groups]
    for v in vals:
        for i, g in enumerate(groups):
            if _exposure_in_group(v, [g], allow_zero=allow_zero):
                members[i].append(v)
                break
    best = max(range(len(groups)), key=lambda i: len(members[i]))
    return members[best] or [groups[best]]


def _gain_in_group(value: float, group: Sequence[float]) -> bool:
    """Is ``value`` one of the settings in ``group``, by the module's own
    "is this the same gain?" question? A header round-trip (80.0 against
    79.9999) is the same setting; any real step (80 → 160) is not."""
    from seestack.calibrate.apply import gain_mismatch

    return any(not gain_mismatch(g, value) for g in group)


def _majority_gain_group(values: Sequence[float | None]) -> list[float] | None:
    """The gain setting most of these frames were shot at, as the list of raw
    values belonging to that group — or ``None`` when there is nothing to gate
    on (no recorded gain, or only one setting, which is every ordinary folder).

    Grouped by :func:`seestack.calibrate.apply.distinct_gains`, the same grouping
    the gain advisory uses, so "two gains" means the same thing everywhere. Ties
    keep the **lowest** setting, because ``distinct_gains`` reports groups
    lowest-first and the first maximum wins — deterministic, and exactly the
    shape and exposure rules' own tie-break.

    A gain of 0 is a legitimate setting (unlike a 0 s exposure), so only the
    missing, the non-finite and the negative are dropped here — the same rule
    ``distinct_gains`` itself applies.
    """
    from seestack.calibrate.apply import distinct_gains

    vals = [float(v) for v in values
            if v is not None and math.isfinite(float(v)) and float(v) >= 0]
    groups = distinct_gains(vals)
    if len(groups) < 2:
        return None  # nothing to split — behaviour is byte-identical
    members: list[list[float]] = [[] for _ in groups]
    for v in vals:
        for i, g in enumerate(groups):
            if _gain_in_group(v, [g]):
                members[i].append(v)
                break
    best = max(range(len(groups)), key=lambda i: len(members[i]))
    return members[best] or [groups[best]]


def build_master(
    paths: Sequence[str | Path],
    *,
    kind: str,
    method: str = "median",
    sigma: float = 3.0,
    max_frames: int = 64,
    progress: ProgressFn | None = None,
    should_stop: Callable[[], bool] | None = None,
    skipped: list[tuple[str, str]] | None = None,
    require_declared_kind: bool = False,
) -> tuple[np.ndarray, MasterMeta] | None:
    """Combine raw FITS frames into a master.

    Parameters
    ----------
    paths
        Raw single-extension FITS files (all the same kind, shape and bayer
        pattern). When the set isn't uniform, the **majority** shape wins and
        files that don't match it are skipped — so one stray frame from another
        camera or binning mode can't hijack the build. For a **dark or a bias**,
        the same majority rule applies to the frames' *exposure* (see below):
        a dark's entire content is its exposure and a bias is *defined* as the
        zero-length readout, so in either case a set holding two lengths does
        not describe either one. It applies to their *gain* as well, which sets
        the size of the pedestal they exist to measure.
    kind
        'dark', 'flat' or 'bias' — recorded in the metadata.
    method
        'median' (default), 'sigma_mean' or 'mean'.
    sigma
        Clip threshold for ``sigma_mean``.
    max_frames
        Cap on frames actually loaded (evenly sampled across the input) to
        bound peak memory.
    should_stop
        Optional cancellation predicate polled once per input frame (and again
        before the final combine). When it returns ``True`` the build aborts
        promptly and returns ``None`` **before any master is written** — no
        partial output is produced. A dark/flat set can be many frames, so a
        long build stays responsive to the Jobs-page Cancel button.
    skipped
        Optional list to collect ``(filename, reason)`` for every frame that was
        dropped during the build — ``"unreadable"`` (failed to load),
        ``"wrong size"`` (not a 2-D frame, or a shape that doesn't match the
        majority), ``"wrong exposure"`` (a dark or bias whose length isn't the
        majority one) or ``"wrong gain"`` (a dark or bias whose gain isn't the
        majority one). Lets the caller tell the user *how many* of their frames were
        actually used vs. silently set aside, instead of a bare success. Frames
        dropped by ``max_frames`` sampling are **not** recorded here — that's an
        intentional memory bound, not a skip. Default ``None`` = don't collect.
    require_declared_kind
        When ``True``, a frame whose own header **declares** a kind belonging to a
        different master slot — a light, or a flat in a dark build — is skipped
        (reason ``"wrong kind"``) instead of being combined. A frame that declares
        *nothing* is still used: "didn't say" is not "said the wrong thing", and
        plenty of legitimate calibration FITS carry no ``IMAGETYP``.

        Default ``False``, which is exactly today's behaviour, because a build the
        user aimed at a folder they chose is *meant* to take what is in it. It is
        set by the **discover-driven** one-click build, where the folder was
        classified from only ``discover.SAMPLE_HEADERS`` sampled headers: a mixed
        folder whose samples all happened to read "dark" would otherwise build a
        master out of the lights sitting beside them, and a contaminated master
        dark corrupts every frame it is later applied to.

        The filter runs **before** the majority-shape reference is chosen, so a
        mixed folder's reference is decided among the frames that will actually be
        used (lights from the same camera share the darks' shape, so the shape rule
        cannot catch this on its own).

    Returns
    -------
    (master_2d_float32, MasterMeta), or ``None`` if cancelled via ``should_stop``.
    """
    from seestack.calibrate.discover import KIND_TO_MASTER
    from seestack.io.fits_loader import frame_kind_from_header, load_seestar_raw

    if kind not in VALID_KINDS:
        raise ValueError(f"unknown calibration kind {kind!r} (expected one of {VALID_KINDS})")
    if method not in VALID_METHODS:
        raise ValueError(f"unknown method {method!r} (expected one of {VALID_METHODS})")
    paths = [Path(p) for p in paths]
    if not paths:
        raise ValueError("no calibration frames supplied")

    # How many the user actually gave us, kept so the caller can *say* that a
    # large set was sampled rather than leaving them to wonder why their 200
    # darks produced a master "from 64 frames".
    n_supplied = len(paths)

    # Evenly sample down to max_frames so very large dark/flat sets don't OOM.
    if len(paths) > max_frames:
        idx = np.linspace(0, len(paths) - 1, max_frames).round().astype(int)
        sampled = [paths[i] for i in sorted(set(idx.tolist()))]
        log.info("Master %s: sampling %d of %d frames", kind, len(sampled), len(paths))
        paths = sampled

    progress = progress or (lambda *a: None)
    should_stop = should_stop or (lambda: False)
    total = len(paths)

    loaded: list[tuple[str, np.ndarray, Any]] = []
    for i, p in enumerate(paths, start=1):
        if should_stop():
            log.info("master %s: build cancelled after %d/%d frames", kind, i - 1, total)
            return None
        progress("Loading", i, total)
        try:
            raw, info = load_seestar_raw(p, debayer=False, out_dtype=np.float32)
        except Exception as exc:  # noqa: BLE001 — one bad file shouldn't sink the build
            log.warning("master %s: skipping %s (%s)", kind, p.name, exc)
            if skipped is not None:
                skipped.append((p.name, "unreadable"))
            continue
        if raw.ndim != 2:
            log.warning("master %s: skipping %s (not a 2D Bayer frame)", kind, p.name)
            if skipped is not None:
                skipped.append((p.name, "wrong size"))
            continue
        if require_declared_kind:
            declared = frame_kind_from_header(getattr(info, "raw_header", None) or {})
            # Only a frame that *declares* a different slot is dropped; one that
            # declares nothing, or declares a kind that maps to this slot (a
            # flat-dark in a dark build), is kept exactly as before.
            if declared and KIND_TO_MASTER.get(declared) != kind:
                log.warning("master %s: skipping %s (declares %s)", kind, p.name, declared)
                if skipped is not None:
                    skipped.append((p.name, "wrong kind"))
                continue
        loaded.append((p.name, raw, info))

    if not loaded:
        if require_declared_kind and skipped is not None and any(
                reason == "wrong kind" for _n, reason in skipped):
            # Say *why* rather than "mismatched": the folder looked like this kind
            # when it was sampled, and every frame in it turned out to say otherwise.
            raise ValueError(
                f"no {kind} frames here — every frame says it is something else")
        raise ValueError("no usable calibration frames (all failed to load or mismatched)")

    # The reference shape is the **majority** one, not whichever frame happened to
    # load first. A single stray file from another camera or binning mode sorted
    # ahead of the real set used to define the reference and skip every genuine
    # frame after it — leaving a one-frame master of the wrong sensor, reported as
    # a successful build and only failing much later when a stack refuses it on
    # shape. Ties keep the first-seen shape, which is exactly the old behaviour
    # whenever the set is uniform (the overwhelming common case). Peak memory is
    # unchanged: the number of arrays held is still bounded by ``max_frames``.
    counts: dict[tuple[int, ...], int] = {}
    for _, raw, _ in loaded:
        counts[tuple(raw.shape)] = counts.get(tuple(raw.shape), 0) + 1
    ref_shape = max(counts, key=lambda s: counts[s])  # first max wins on a tie

    # ...and, for a dark, the majority **exposure**, by exactly the same rule and
    # for exactly the same reason.
    #
    # A dark is a photograph of the sensor's own dark current, and dark current
    # grows with exposure — so a folder holding 10 s and 30 s darks does not hold
    # one master's worth of frames, it holds two. Combining them produced a master
    # whose pixels are a median of two different dark currents (measured on a
    # synthetic set: 100 ADU and 300 ADU in, **200 ADU** out — a level neither
    # length ever has), stamped with the median exposure, **20 s** — a length no
    # frame in it was shot at. It then over-subtracts from every short light and
    # under-subtracts from every long one, in the one place in this app whose
    # whole job is to remove a pedestal exactly.
    #
    # Nothing prevents that folder: `discover.classify_frames` groups by folder
    # and asks only what *kind* the frames are, and a build the user aims by hand
    # takes what is in the folder. This is the same majority rule the shape gate
    # above already applies to a stray frame from another camera.
    #
    # Flats are exempt, deliberately: a flat is normalised before it divides, so
    # its exposure is not part of what it says. Flat-darks arrive here as
    # ``kind="dark"`` and want the rule as much as darks do (a flat-dark must
    # match its flat's exposure).
    #
    # **A bias wants it too, and used to be exempt for a reason that was really
    # the bug.** "A bias is by definition the zero-length frame" is a statement
    # about what a bias *is*, not about what is in the folder — so it argued for
    # the gate rather than against it. Measured on a synthetic folder of 0 s
    # readouts (500 ADU) with a few 10 s darks mixed in, the identical folder
    # built as a ``dark`` set the 10 s frames aside as "wrong exposure", while
    # built as a ``bias`` it combined all six: an even split gave a **1000 ADU**
    # master stamped **5 s** — a bias frame that claims to be a five-second
    # exposure — and the 4-to-2 folder gave **833 ADU** stamped **0 s**, which is
    # the silent one, a pedestal 67 % too big wearing a bias's own label. That
    # matters more than the same mistake in a dark, because the bias is what
    # carries dark exposure-scaling: ``_effective_dark`` computes
    # ``bias + (dark − bias)·t_light/t_dark``, so an inflated bias is wrong at
    # every pixel of every scaled frame, and it is also
    # :func:`~seestack.calibrate.defects.build_defect_map`'s fallback source.
    #
    # The bias call passes ``allow_zero``, because the commonest shape of that
    # folder is 0 s frames plus a stray dark and ``distinct_exposures`` drops a
    # non-positive value — so without it the set groups as one length and the
    # gate never fires. See :func:`_majority_exposure_group`.
    #
    # A frame that recorded **no** exposure is kept, mirroring this module's own
    # "didn't say is not said the wrong thing" rule for ``require_declared_kind``:
    # plenty of legitimate calibration FITS carry no ``EXPTIME``, and dropping them
    # would turn a missing header into a smaller master.
    ref_exposure_group: list[float] | None = None
    if kind in ("dark", "bias"):
        ref_exposure_group = _majority_exposure_group(
            [info.exposure_s for _n, _r, info in loaded],
            allow_zero=(kind == "bias"))

    # ...and, for a dark or a bias, the majority **gain**, by the same rule
    # again — the same bug as the exposure one, one setting sideways.
    #
    # A dark and a bias are both photographs of a pedestal the sensor adds, and
    # the size of that pedestal is set by the gain: raise the gain and the read
    # noise, the offset and the amplified dark current all scale with it. So a
    # folder holding gain-80 and gain-160 darks does not hold one master's worth
    # of frames either, and `discover.classify_frames` no more prevents that
    # folder than it prevents the two-exposure one — it groups by folder and
    # asks only what *kind* the frames are.
    #
    # Measured on a synthetic set, at the same 10 s and the same temperature,
    # with only the gain differing: 100 ADU (gain 80) and 300 ADU (gain 160) in,
    # an evenly-split folder gives a **200 ADU** master stamped **gain 120** — a
    # level and a setting no frame in it was ever shot at, on all three combine
    # methods. The 4-to-2 folder is worse, because it is *silent*: `mean` gives
    # a 166.7 ADU master stamped gain **80**, so the v0.466.0 gain advisory —
    # which compares the master's own stamped gain against the lights — sees a
    # perfect match and says nothing about a pedestal 67 % too big.
    #
    # And unlike an exposure, a gain gap has no lever anywhere that corrects it:
    # `scale_dark_to_light` rescales a mismatched *length*, nothing rescales a
    # mismatched *setting* (see `CalibrationMasters.calibration_warnings`).
    #
    # Flats are exempt, deliberately, and for the same reason they are exempt
    # from the exposure rule: a flat is normalised to its own median before it
    # divides, so a constant gain factor divides straight back out and is not
    # part of what the flat says.
    #
    # A frame that recorded **no** gain is kept, exactly as for exposure:
    # "didn't say" is not "said the wrong thing".
    ref_gain_group: list[float] | None = None
    if kind in ("dark", "bias"):
        ref_gain_group = _majority_gain_group(
            [info.gain for _n, _r, info in loaded])

    arrays: list[np.ndarray] = []
    exposures: list[float] = []
    gains: list[float] = []
    temps: list[float] = []
    patterns: list[str] = []
    # Tallied over the frames that actually make it into the combine, so the
    # count the user is shown is the count the master is made of — a frame
    # skipped for shape never contributes its opinion.
    header_kinds: dict[str, int] = {}
    for name, raw, info in loaded:
        if tuple(raw.shape) != ref_shape:
            log.warning("master %s: skipping %s (shape %s != %s)",
                        kind, name, raw.shape, ref_shape)
            if skipped is not None:
                skipped.append((name, "wrong size"))
            continue
        if (ref_exposure_group is not None and info.exposure_s is not None
                and not _exposure_in_group(info.exposure_s, ref_exposure_group,
                                           allow_zero=(kind == "bias"))):
            log.warning("master %s: skipping %s (exposure %.4gs, master is %.4gs)",
                        kind, name, info.exposure_s, ref_exposure_group[0])
            if skipped is not None:
                skipped.append((name, "wrong exposure"))
            continue
        if (ref_gain_group is not None and info.gain is not None
                and not _gain_in_group(info.gain, ref_gain_group)):
            log.warning("master %s: skipping %s (gain %.4g, master is %.4g)",
                        kind, name, info.gain, ref_gain_group[0])
            if skipped is not None:
                skipped.append((name, "wrong gain"))
            continue
        arrays.append(raw)
        declared = frame_kind_from_header(getattr(info, "raw_header", None) or {})
        if declared:
            header_kinds[declared] = header_kinds.get(declared, 0) + 1
        if info.exposure_s is not None:
            exposures.append(info.exposure_s)
        if info.gain is not None:
            gains.append(info.gain)
        if info.sensor_temp_c is not None:
            temps.append(info.sensor_temp_c)
        if info.bayer_pattern:
            patterns.append(info.bayer_pattern.upper())

    if should_stop():
        log.info("master %s: build cancelled before combine", kind)
        return None
    progress("Combining", 0, 1)
    n_frames = len(arrays)
    stack = np.stack(arrays, axis=0)  # (N, H, W) — a fresh, owned copy
    # ``np.stack`` copied every frame into ``stack``, so the per-frame arrays held
    # by ``arrays``/``loaded`` are now redundant. Drop them before the combine so
    # the peak isn't three live copies of the frame set (the two lists + ``stack``
    # + the finite-masked copy below): on a 64-frame Seestar-sized set that is the
    # difference between ~1.6 GB and ~1.0 GB of peak RAM. ``arrays`` isn't touched
    # again (``n_frames`` is captured above), and the small metadata lists
    # (exposures/gains/…) were already extracted.
    del arrays, loaded
    # NaN-aware combine (the engine invariant: a non-finite sample is "no data",
    # don't fold it into a value). Real Seestar raws are finite integer readouts
    # cast to float32, so masking is a no-op and this is byte-for-byte identical to
    # a plain median/mean on them — but a user-supplied float FITS calibration frame
    # carrying a NaN/inf pixel would otherwise poison that pixel in the master (and
    # thence every calibrated light). Treat NaN *and* inf uniformly (nanmean ignores
    # NaN but not inf), mirroring the `sigma_mean` path and the flat build. An
    # all-non-finite pixel (no finite sample anywhere) stays NaN = genuinely no data.
    # Mask **in place** — we exclusively own ``stack`` (just built by ``np.stack``,
    # source frames dropped) — rather than allocating a second full N×H×W copy.
    nonfinite = ~np.isfinite(stack)
    if nonfinite.any():
        stack[nonfinite] = np.nan
    del nonfinite
    finite_stack = stack
    with np.errstate(invalid="ignore"), warnings.catch_warnings():
        # An all-non-finite pixel legitimately reduces to NaN ("no data"); numpy
        # warns "Mean/Median of empty slice" there — expected, not an error.
        warnings.filterwarnings("ignore", r"(Mean|All-NaN|Degrees of freedom).*",
                                RuntimeWarning)
        if method == "median":
            master = np.nanmedian(finite_stack, axis=0).astype(np.float32, copy=False)
        elif method == "mean":
            master = np.nanmean(finite_stack, axis=0).astype(np.float32, copy=False)
        else:  # sigma_mean
            master = _sigma_clip_mean(finite_stack, sigma)
    progress("Combining", 1, 1)

    h, w = ref_shape
    meta = MasterMeta(
        kind=kind,
        n_frames=n_frames,
        width_px=int(w),
        height_px=int(h),
        method=method,
        exposure_s=float(np.median(exposures)) if exposures else None,
        gain=float(np.median(gains)) if gains else None,
        sensor_temp_c=float(np.median(temps)) if temps else None,
        # Off the same list the median comes from, so the stamped value and the
        # range it sits in can never describe different frames.
        sensor_temp_min_c=float(min(temps)) if temps else None,
        sensor_temp_max_c=float(max(temps)) if temps else None,
        bayer_pattern=_mode(patterns),
        n_supplied=n_supplied,
        header_kinds=header_kinds,
    )
    return master, meta


def _mode(values: Sequence[str]) -> str | None:
    if not values:
        return None
    uniq, counts = np.unique(np.array(values), return_counts=True)
    return str(uniq[int(np.argmax(counts))])


# ---- FITS persistence ---------------------------------------------------

_META_CARDS = {
    "exposure_s": "EXPTIME",
    "gain": "GAIN",
    "sensor_temp_c": "CCD-TEMP",
    "sensor_temp_min_c": "SSTMPMIN",
    "sensor_temp_max_c": "SSTMPMAX",
    "bayer_pattern": "BAYERPAT",
}


def save_master(path: str | Path, master: np.ndarray, meta: MasterMeta) -> None:
    """Write a master frame to FITS, embedding its metadata in the header."""
    from astropy.io import fits

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    hdu = fits.PrimaryHDU(data=np.asarray(master, dtype=np.float32))
    h = hdu.header
    h["SSKIND"] = (meta.kind, "AstroStack calibration master kind")
    h["SSNFRAME"] = (meta.n_frames, "Frames combined")
    h["SSMETHOD"] = (meta.method, "Combination method")
    if meta.exposure_s is not None:
        h["EXPTIME"] = meta.exposure_s
    if meta.gain is not None:
        h["GAIN"] = meta.gain
    if meta.sensor_temp_c is not None:
        h["CCD-TEMP"] = meta.sensor_temp_c
    # Additive cards: a reader that doesn't know them ignores them, and a master
    # written before they existed simply has neither.
    if meta.sensor_temp_min_c is not None:
        h["SSTMPMIN"] = (meta.sensor_temp_min_c, "Coldest source frame (C)")
    if meta.sensor_temp_max_c is not None:
        h["SSTMPMAX"] = (meta.sensor_temp_max_c, "Warmest source frame (C)")
    if meta.bayer_pattern:
        h["BAYERPAT"] = meta.bayer_pattern
    # Atomic write so a crash mid-save can't leave a truncated master.
    tmp = path.with_suffix(path.suffix + ".tmp")
    hdu.writeto(tmp, overwrite=True)
    tmp.replace(path)


def load_master(path: str | Path) -> tuple[np.ndarray, MasterMeta]:
    """Read a master frame FITS back into ``(array_float32, MasterMeta)``."""
    from astropy.io import fits

    path = Path(path)
    with fits.open(path, memmap=False) as hdul:
        data = np.asarray(hdul[0].data, dtype=np.float32)
        h = hdul[0].header

    def _f(key: str) -> float | None:
        try:
            return float(h[key]) if key in h else None
        except (TypeError, ValueError):
            return None

    if data.ndim != 2:
        raise ValueError(f"master {path} is not a 2D frame (shape {data.shape})")
    meta = MasterMeta(
        kind=str(h.get("SSKIND", "dark")),
        n_frames=int(h.get("SSNFRAME", 0) or 0),
        width_px=int(data.shape[-1]),
        height_px=int(data.shape[-2]),
        method=str(h.get("SSMETHOD", "median")),
        exposure_s=_f("EXPTIME"),
        gain=_f("GAIN"),
        sensor_temp_c=_f("CCD-TEMP"),
        sensor_temp_min_c=_f("SSTMPMIN"),
        sensor_temp_max_c=_f("SSTMPMAX"),
        bayer_pattern=str(h["BAYERPAT"]).strip() if "BAYERPAT" in h else None,
    )
    return data, meta
