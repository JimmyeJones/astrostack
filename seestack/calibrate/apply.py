"""
Apply master calibration frames to a raw light frame.

A :class:`CalibrationMasters` bundle is built **once per stack** (loading the
master FITS into RAM) and then shared, read-only, across the worker threads
that load each light frame. Each worker calls :meth:`apply_raw` on the raw
Bayer mosaic before debayering.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:  # pragma: no cover - typing only
    from seestack.calibrate.defects import DefectMap

log = logging.getLogger(__name__)

# Flat values below this fraction of the mean are floored before dividing, so a
# near-black corner of the flat (or a dead pixel) can't explode into a huge
# spike in the calibrated light frame.
_FLAT_FLOOR = 0.1

# How far a master dark's exposure may differ from the lights before the advisory
# mismatch warning fires, as a fraction of the *dark's* exposure
# (``|t_light / t_dark − 1|``). Seestar exposures are discrete (10/20/30 s), so a
# real mismatch is ≥2× — well past this; the slack only absorbs header rounding on
# a nominally-matched pair.
#
# Public because the Stack form warns about the same mismatch at *pick* time, and
# the two must agree: a threshold written independently in the frontend let the app
# stay quiet before the night was spent and then complain about it afterwards (or
# the reverse) on a borderline pair. The webapp serves these two numbers to the
# form (``…/calibration-suggestions`` → ``tolerances``) so there is one source of
# truth; a test pins that the served values *are* these.
EXPOSURE_MISMATCH_TOL = 0.15
# How far a master dark's sensor temperature may differ from the lights (°C)
# before the advisory warning fires. Dark current ~doubles per 6-7 °C, so a few
# degrees is tolerable; this flags a clearly-mismatched dark library.
TEMP_MISMATCH_TOL_C = 5.0
# The share of a target's subs a master dark must *miss* on temperature before
# the advisory says so.
#
# Exposure is a setting, so a second one is a second population by definition.
# Temperature is not: an uncooled sensor drifts through a night and follows the
# season across nights, so on a target spanning many nights a few subs sit beyond
# the tolerance of *any* dark. What reaches the stacked picture is their share of
# one frame's residual — below a tenth that is well inside what the tolerance
# itself already calls tolerable, and saying it anyway is a warning the reader
# cannot act on.
#
# It floors *reporting*, never correction, and it can only ever suppress a
# warning the old reference-frame test fired by accident (that test asked one
# frame, so a lone outlier chosen as reference spoke for the whole session).
TEMP_MISMATCH_MIN_SHARE = 0.10

# Historical private aliases — kept so nothing that referenced them breaks.
_EXPOSURE_MISMATCH_TOL = EXPOSURE_MISMATCH_TOL
_TEMP_MISMATCH_TOL_C = TEMP_MISMATCH_TOL_C


def distinct_exposures(values: Iterable[float | None]) -> list[float]:
    """The distinct sub lengths in a set of lights, shortest first.

    Two subs count as the **same** exposure when their lengths agree to within
    :data:`EXPOSURE_MISMATCH_TOL` — the very question the dark advisory asks,
    answered once so header rounding (``9.998`` against ``10.0``) can never read
    as a second exposure while a real Seestar step (10 → 20 → 30 s) always does.
    Each group is reported by its median, so one mistyped header cannot move the
    length the group is named by.

    Values that are missing, non-finite or non-positive are dropped rather than
    grouped: "we don't know how long this sub was" is not an exposure, and
    treating it as one would invent a mismatch out of a blank FITS card.

    Grouping is against each group's **first** member rather than a running
    value, so a long ramp of near-neighbours cannot chain two genuinely
    different exposures into one group.
    """
    vals = sorted(
        float(v) for v in values
        if v is not None and math.isfinite(float(v)) and float(v) > 0
    )
    if not vals:
        return []
    groups: list[list[float]] = [[vals[0]]]
    for v in vals[1:]:
        first = groups[-1][0]
        if abs(v / first - 1.0) <= EXPOSURE_MISMATCH_TOL:
            groups[-1].append(v)
        else:
            groups.append([v])
    out: list[float] = []
    for g in groups:
        n = len(g)
        out.append(g[n // 2] if n % 2 else (g[n // 2 - 1] + g[n // 2]) / 2.0)
    return out


def typical_exposure_s(values: Iterable[float | None]) -> float | None:
    """The one number that stands for ``values`` in a per-sub figure, or ``None``
    when not one of them recorded a usable exposure.

    The **median** when the subs are all one length, which is every ordinary
    target: it is robust, so one mistyped header cannot move the length a whole
    stack is described by.

    The **mean** when they are genuinely several lengths. A target is one folder,
    never one exposure — shoot it at 10 s on one night and 30 s on the next and it
    is one target with two in it — and there the median is not a summary of the
    set, it is one member of it chosen by position. Measured on a six-sub target:
    4x10 s + 2x30 s really holds 100 s of light and the median reports 60 s
    (-40 %), while 3x10 s + 3x30 s holds 120 s and the median reports 180 s
    (+50 %). The mean is the only value whose product with the frame count is the
    light that was actually collected, which is the whole point of the figure.

    "All one length" is :func:`distinct_exposures`, so header rounding (``9.998``
    against ``10.0``) stays one exposure and a real Seestar step (10 -> 20 ->
    30 s) does not — the same question the dark advisory, the Stack form and the
    master binder all already ask, answered once.

    Public, and here rather than in the stacker, because two surfaces multiply it
    by a *count*: the FITS integration time (``seestack.stack.stacker``'s
    ``EXPOSURE``/``EXPTOTAL``) and the health panel's uneven-grain shortfall
    (``seestack.stackhealth``), which reads the answer against the panel map's
    own :data:`~seestack.mosaicmap.THIN_MIN_SHORTFALL_S`. Two definitions let the
    map and the note give opposite instructions about one panel.
    """
    exposures = [
        float(v) for v in values
        if v is not None and math.isfinite(float(v)) and float(v) > 0
    ]
    if not exposures:
        return None
    if len(distinct_exposures(exposures)) > 1:
        return sum(exposures) / len(exposures)
    return sorted(exposures)[len(exposures) // 2]  # median


def _finite_temps(values: Iterable[float | None]) -> list[float]:
    """The usable sensor temperatures in a set of lights, coldest first.

    Unlike an exposure a temperature may legitimately be zero or negative, so the
    only values dropped are the missing and the non-finite ones: "this sub never
    recorded a temperature" is not a temperature, and reading a blank FITS card as
    0 °C would invent a mismatch out of nothing.
    """
    return sorted(
        float(v) for v in values
        if v is not None and math.isfinite(float(v))
    )


def temperature_spread(
    values: Iterable[float | None],
) -> tuple[float, float, float] | None:
    """``(coldest, median, warmest)`` sensor temperature over a set of lights, or
    ``None`` when none of them recorded one.

    Public because the Stack form describes the same target *before* the night is
    spent that the finished run describes afterwards, and the two must not
    disagree about it — the same reason :data:`TEMP_MISMATCH_TOL_C` is public
    (see :meth:`CalibrationMasters.calibration_warnings`).
    """
    temps = _finite_temps(values)
    if not temps:
        return None
    n = len(temps)
    med = temps[n // 2] if n % 2 else (temps[n // 2 - 1] + temps[n // 2]) / 2.0
    return temps[0], med, temps[-1]


def temperature_mismatch_count(
    values: Iterable[float | None], dark_temp_c: float | None,
    *, tol_c: float = TEMP_MISMATCH_TOL_C,
) -> tuple[int, int]:
    """``(how many of these lights this dark's temperature misses, how many of
    them recorded a temperature at all)``.

    The advisory's own test — ``|t_sub − t_dark| >= tol`` — asked of every sub
    instead of one. Both halves are returned because the share is what decides
    whether the gap is worth saying (:data:`TEMP_MISMATCH_MIN_SHARE`) and the
    count is what makes the sentence actionable. ``(0, n)`` when the dark's own
    temperature is unknown: an unrecorded master cannot be disproved, exactly as
    everywhere else in this module.
    """
    temps = _finite_temps(values)
    if dark_temp_c is None or not math.isfinite(float(dark_temp_c)):
        return 0, len(temps)
    dt = float(dark_temp_c)
    return sum(1 for t in temps if abs(t - dt) >= float(tol_c)), len(temps)


def _deg(value: float) -> str:
    """A sensor temperature as the header meant it: one decimal, no trailing
    zeros. ``float32`` round-trips a ``24.3`` card as ``24.299999237…``."""
    return f"{round(float(value), 1) + 0.0:g}"


def _join_exposures(values: Sequence[float]) -> str:
    """``[10, 30]`` → ``"10s and 30s"``; ``[10, 20, 30]`` → ``"10s, 20s and 30s"``."""
    parts = [f"{v:g}s" for v in values]
    if len(parts) <= 1:
        return "".join(parts)
    return f"{', '.join(parts[:-1])} and {parts[-1]}"


def _norm_bayer(pattern: str | None) -> str | None:
    """Normalise a ``BAYERPAT`` string for comparison, or ``None`` if unusable.

    Masters and frames both carry the pattern as free FITS text, so ``'rggb'``,
    ``' RGGB '`` and ``'RGGB'`` are the same sensor. Anything that isn't one of
    the four 2×2 CFA phases (a blank card, an ``'NONE'``, a mono master) reads as
    *undeclared* — the guards below only ever fire when **both** sides declare a
    real, different phase, so an unknown value can never fail a stack that works
    today.
    """
    if not pattern:
        return None
    p = str(pattern).strip().upper()
    return p if p in ("RGGB", "BGGR", "GRBG", "GBRG") else None


def _sanitize_pedestal(arr: np.ndarray) -> np.ndarray:
    """Replace non-finite master dark/bias pixels with 0.0 (= no correction).

    ``build_master`` legitimately produces a NaN pixel where *no* input frame
    had finite data ("genuinely no data" — see ``masters.py``), and an imported
    third-party master can carry NaN/inf too. Subtracting such a pixel straight
    from the light (``light − dark``) would turn real, good signal into NaN/inf
    at that pixel of **every** calibrated frame — a permanent hole (NaN spreads
    through debayer and reads as zero coverage in the stack) or a reduction-
    poisoning ``±inf``. A no-data *pedestal* pixel means "no correction here",
    so it must subtract 0, mirroring the flat's floor-to-1.0 at load time
    (``flat_norm``). Done once at load, off the per-frame hot path.
    """
    return np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0)


@dataclass
class CalibrationMasters:
    """Loaded master dark / flat ready to apply to raw frames.

    The flat is stored *pre-normalised* to a mean of 1.0 (with a floor) so the
    per-frame hot path is a single divide.
    """

    dark: np.ndarray | None = None
    flat_norm: np.ndarray | None = None
    bias: np.ndarray | None = None
    # Boolean mask of master-dark pixels that were non-finite before sanitizing
    # (= "genuinely no data"), or None when the dark is all-finite (the common
    # real-Seestar case, so no extra array is retained). Used only on the
    # exposure-scaling path to keep a no-data dark pixel meaning "no correction"
    # (see :meth:`_effective_dark`); the unscaled path already subtracts the
    # sanitized 0 there.
    dark_nodata_mask: np.ndarray | None = None
    # Boolean mask of master-*bias* pixels that were non-finite before sanitizing
    # (= "genuinely no data"), or None when the bias is all-finite. Used only on
    # the exposure-scaling path: with no trustworthy bias pedestal at such a
    # pixel, the scaled formula ``bias + (dark − bias)·ratio`` would scale the
    # sanitized 0 into a spurious ``dark·ratio``, so :meth:`_effective_dark`
    # falls back to the unscaled dark there (the documented "no correction beyond
    # the plain dark" behaviour).
    bias_nodata_mask: np.ndarray | None = None
    dark_path: str | None = None
    flat_path: str | None = None
    bias_path: str | None = None
    # Exposure of the master dark / bias in seconds (from their FITS headers),
    # None when the header didn't carry it. Used only for optional dark
    # exposure-scaling (see ``scale_dark_to_light`` / :meth:`_effective_dark`).
    dark_exposure_s: float | None = None
    bias_exposure_s: float | None = None
    # Sensor temperature (°C) the master dark was shot at, None when the header
    # didn't carry it. Used only for the advisory mismatch check
    # (:meth:`calibration_warnings`) — dark current varies with temperature, so a
    # dark shot far from the lights' temperature leaves a residual.
    dark_temp_c: float | None = None
    # The ``BAYERPAT`` each master declares (normalised, ``None`` when the header
    # didn't carry one — every master built before this field was read, and any
    # third-party import without the card). Masters are applied to the **raw
    # Bayer mosaic**, so a master whose CFA phase is shifted relative to the
    # lights lines its red pixels up with their green ones. That is harmless for
    # a dark or bias (dark current and read pedestal are per *physical* pixel)
    # and wrecks the colour of every frame for a flat, which is multiplicative
    # per colour — see :meth:`validate` and :meth:`calibration_warnings`.
    dark_bayer_pattern: str | None = None
    flat_bayer_pattern: str | None = None
    bias_bayer_pattern: str | None = None
    # ``((flat_dark_h, flat_dark_w), (flat_h, flat_w))`` when a flat-dark was
    # supplied whose shape doesn't match the flat, so it was **not** subtracted
    # before normalising; ``None`` whenever the flat-dark was applied (or none was
    # given). Unlike a wrong-shaped dark/flat — which :meth:`validate` refuses —
    # this one is silently survivable: the stack succeeds and the flat is simply
    # normalised with its own dark-current + bias pedestal still in it, which
    # flattens the flat's own contrast and leaves part of the vignetting
    # uncorrected. Recorded so :meth:`calibration_warnings` can say so, the same
    # way a wrong-shaped bias that blocks dark exposure-scaling does.
    flat_dark_shape_mismatch: tuple[tuple[int, int], tuple[int, int]] | None = None
    # When True *and* a master bias is available, a master dark shot at a
    # different exposure than the light is scaled to the light's integration
    # time before subtraction (see :meth:`_effective_dark`). Off by default.
    scale_dark_to_light: bool = False
    # Sensor defect map derived from the master dark (or, with no dark, the
    # master bias) when ``repair_sensor_defects`` was requested at load time —
    # ``None`` whenever the option is off, no pedestal master is loaded, or the
    # master carries no credible defects. Applied per frame in :meth:`apply_raw`
    # (raw-Bayer domain, before the flat divide and long before debayer), so a
    # broken photosite is replaced while it is still one pixel. See
    # :mod:`seestack.calibrate.defects`.
    defects: "DefectMap | None" = None

    @classmethod
    def load(
        cls,
        dark_path: str | None = None,
        flat_path: str | None = None,
        flat_dark_path: str | None = None,
        bias_path: str | None = None,
        *,
        scale_dark_to_light: bool = False,
        repair_sensor_defects: bool = False,
    ) -> "CalibrationMasters":
        """Load masters from disk. Any path may be ``None``.

        ``flat_dark_path`` is an optional dark/bias matched to the flat's own
        exposure. When given it is subtracted from the flat *before*
        normalising, so the flat captures only the illumination pattern rather
        than the illumination pattern riding on the flat's dark-current + bias
        pedestal — a more correct flat (this is what DSS/Siril call a
        "flat-dark"). Without it the flat is mean-normalised as-is, unchanged.

        ``bias_path`` is an optional master bias, subtracted from the *lights*
        as the readout pedestal — but **only when no master dark is chosen**. A
        master dark already contains the bias, so subtracting both would
        double-subtract it; when ``dark_path`` is given the bias is loaded for
        provenance/shape reasons but never applied to the lights (see
        :meth:`apply_raw`). This gives a correct ``(light − bias) / flat``
        calibration for the common bias+flat (no dark) workflow.

        ``scale_dark_to_light`` opts into exposure-scaling the dark: when a
        master bias is also loaded and the dark's exposure differs from the
        light's, the dark's *dark current* is scaled to the light's integration
        time — ``dark = bias + (dark − bias)·(t_light / t_dark)`` — so a dark
        library shot at one exposure can still calibrate subs at another. It
        needs the bias to hold the exposure-independent readout pedestal fixed;
        without a bias (or an unknown exposure) the dark is used unscaled.

        ``repair_sensor_defects`` opts into deriving a **sensor defect map**
        from the master dark (or, with no dark, the master bias) and repairing
        those photosites in every light — see
        :mod:`seestack.calibrate.defects`. Off by default; with it off nothing
        is measured and no frame is touched, so a run is byte-for-byte what it
        is today.
        """
        from seestack.calibrate.masters import load_master

        dark = None
        dark_nodata_mask = None
        dark_exposure_s = None
        dark_temp_c = None
        dark_bayer = None
        flat_norm = None
        flat_bayer = None
        bias = None
        bias_nodata_mask = None
        bias_exposure_s = None
        bias_bayer = None
        flat_dark_shape_mismatch = None
        if dark_path:
            dark, dark_meta = load_master(dark_path)
            dark = np.asarray(dark, dtype=np.float32)
            # Remember which dark pixels are genuinely no-data *before* they're
            # sanitized to 0, so the exposure-scaling path can keep them at
            # "no correction" instead of scaling the 0 into a spurious pedestal.
            nodata = ~np.isfinite(dark)
            dark_nodata_mask = nodata if bool(nodata.any()) else None
            dark = _sanitize_pedestal(dark)
            dark_exposure_s = dark_meta.exposure_s
            dark_temp_c = dark_meta.sensor_temp_c
            dark_bayer = _norm_bayer(dark_meta.bayer_pattern)
        if bias_path:
            bias, bias_meta = load_master(bias_path)
            bias = np.asarray(bias, dtype=np.float32)
            # Remember which bias pixels are genuinely no-data *before* they're
            # sanitized to 0, so the exposure-scaling path can fall back to the
            # unscaled dark there instead of scaling the 0 into a wrong pedestal.
            bias_nodata = ~np.isfinite(bias)
            bias_nodata_mask = bias_nodata if bool(bias_nodata.any()) else None
            bias = _sanitize_pedestal(bias)
            bias_exposure_s = bias_meta.exposure_s
            bias_bayer = _norm_bayer(bias_meta.bayer_pattern)
        if flat_path:
            flat, flat_meta = load_master(flat_path)
            flat = np.asarray(flat, dtype=np.float32)
            flat_bayer = _norm_bayer(flat_meta.bayer_pattern)
            # Map non-finite flat pixels to NaN so an ``inf`` is handled exactly
            # like a NaN below (ignored by ``nanmean`` and floored to 1.0 = no
            # correction there) instead of poisoning the mean and dropping the
            # *whole* flat. A flat is multiplicative, so ``_sanitize_pedestal``'s
            # 0.0 would be wrong here — NaN is the right "no data" sentinel. This
            # mirrors the flat-dark sanitisation just below; ``build_master``
            # already emits NaN (not inf) for no-data pixels, so this only bites a
            # hand-crafted/imported flat FITS carrying an inf. An all-finite flat
            # (the common case) is byte-for-byte unchanged.
            if not np.isfinite(flat).all():
                flat = np.where(np.isfinite(flat), flat, np.nan).astype(
                    np.float32, copy=False)
            if flat_dark_path:
                flat_dark, _ = load_master(flat_dark_path)
                # Sanitize non-finite flat-dark pixels to 0 (= no subtraction
                # there), mirroring the master dark/bias. Without this an imported
                # third-party flat-dark carrying an inf makes the flat's nanmean
                # non-finite and silently drops the *whole* flat (below), while a
                # NaN would only be masked out later by the flat floor.
                flat_dark = _sanitize_pedestal(
                    np.asarray(flat_dark, dtype=np.float32))
                if flat_dark.shape == flat.shape:
                    flat = flat - flat_dark
                else:
                    log.warning(
                        "flat-dark %s is %s but the flat is %s; skipping the "
                        "flat-dark subtraction", flat_dark_path,
                        flat_dark.shape, flat.shape,
                    )
                    # Remember it so the user hears about it too. The log line
                    # above reached the server log only, and this is the one
                    # calibration slot whose mismatch neither fails the stack nor
                    # changes what the picker said — it just quietly produces a
                    # worse flat.
                    # ``load_master`` refuses anything that isn't a 2-D frame, so
                    # both shapes are (h, w).
                    flat_dark_shape_mismatch = (
                        (int(flat_dark.shape[0]), int(flat_dark.shape[1])),
                        (int(flat.shape[0]), int(flat.shape[1])),
                    )
            mean = float(np.nanmean(flat))
            if not np.isfinite(mean):
                log.warning("flat master %s has a non-finite mean; ignoring it", flat_path)
            elif mean <= 0:
                log.warning("flat master %s has non-positive mean; ignoring it", flat_path)
            else:
                fn = flat / mean
                # Floor tiny / non-finite values to 1.0 (= no correction there).
                flat_norm = np.where(np.isfinite(fn) & (fn > _FLAT_FLOOR), fn, 1.0
                                     ).astype(np.float32, copy=False)
        # Sensor defect map — measured once, here, off the per-frame hot path.
        # The *dark* is the better source (it carries dark current as well as
        # the readout pedestal, so a merely-warm pixel shows up); the bias is
        # the fallback for the no-dark workflow. The no-data mask is excluded
        # because a master with no data at a pixel says nothing about the
        # sensor there — see ``find_sensor_defects``.
        defects = None
        if repair_sensor_defects:
            from seestack.calibrate.defects import build_defect_map

            if dark is not None:
                defects = build_defect_map(dark, exclude=dark_nodata_mask)
            elif bias is not None:
                defects = build_defect_map(bias, exclude=bias_nodata_mask)
            if defects is not None:
                log.info("Sensor defect map: %d photosite(s) will be repaired "
                         "from their same-colour neighbours", defects.n_defects)
        return cls(dark=dark, flat_norm=flat_norm, bias=bias, defects=defects,
                   dark_nodata_mask=dark_nodata_mask,
                   bias_nodata_mask=bias_nodata_mask,
                   dark_path=dark_path, flat_path=flat_path, bias_path=bias_path,
                   dark_exposure_s=dark_exposure_s, bias_exposure_s=bias_exposure_s,
                   dark_temp_c=dark_temp_c,
                   dark_bayer_pattern=dark_bayer, flat_bayer_pattern=flat_bayer,
                   bias_bayer_pattern=bias_bayer,
                   flat_dark_shape_mismatch=flat_dark_shape_mismatch,
                   scale_dark_to_light=scale_dark_to_light)

    @property
    def is_empty(self) -> bool:
        return self.dark is None and self.flat_norm is None and self.bias is None

    @property
    def _bias_applies(self) -> bool:
        """The master bias is subtracted from lights only when no dark is set —
        a dark already carries the bias pedestal, so applying both would
        double-subtract it."""
        return self.dark is None and self.bias is not None

    @property
    def _dark_scaling_applies(self) -> bool:
        """Whether exposure-scaling of the dark actually takes effect.

        ``_effective_dark`` can only scale the dark to the lights' exposure when
        a master bias **matching the dark's shape** is present (it holds the
        exposure-independent bias pedestal fixed while scaling the dark current).
        A loaded but *wrong-shaped* bias does **not** enable scaling — the dark
        is subtracted unscaled — so both the scaling path and the exposure-
        mismatch advisory (``calibration_warnings``) must gate on this same
        predicate. Otherwise the warning is silenced exactly when the unscaled
        fallback (which over/under-subtracts a mismatched-exposure pedestal on
        every frame) makes it most needed."""
        return (self.scale_dark_to_light and self.dark is not None
                and self.bias is not None
                and self.bias.shape == self.dark.shape)

    @property
    def n_sensor_defects(self) -> int:
        """How many photosites the defect map repairs per frame (0 = none).

        Provenance only — the run stamps it so a user who turned the
        (off-by-default) repair on can see it did something, and how much."""
        return self.defects.n_defects if self.defects is not None else 0

    def describe(self) -> str:
        parts = []
        if self.dark is not None:
            parts.append("dark")
        elif self._bias_applies:
            parts.append("bias")
        if self.flat_norm is not None:
            parts.append("flat")
        return "+".join(parts) if parts else "none"

    def validate(
        self,
        shape: tuple[int, int],
        light_bayer_pattern: str | None = None,
    ) -> None:
        """Raise ``ValueError`` if a loaded master doesn't match the lights.

        Called once, up front, against the reference frame's raw dimensions so
        a camera/binning mismatch fails fast with a clear message instead of
        silently skipping the correction on every frame.

        ``light_bayer_pattern`` (the reference frame's ``BAYERPAT``) additionally
        fails a **flat** whose own declared CFA phase differs. Shape alone is not
        enough for a flat: it is divided into the *raw Bayer mosaic*, so a flat
        one pixel out of phase divides every red photosite by a green correction
        and vice versa — the picture keeps its detail and comes out the wrong
        colour on every single frame, which is far harder to notice (and to
        diagnose) than a hard failure. Refusing is the same fail-closed shape the
        dimension guard already has.

        Deliberately narrow, so it cannot fail a stack that works today: it fires
        only when the flat **and** the lights each declare one of the four real
        CFA phases and those phases differ (see :func:`_norm_bayer`). Omit the
        argument, or leave either side's header without a usable ``BAYERPAT`` —
        which is every master built before this field was read — and nothing
        changes. A dark or bias phase mismatch is *not* fatal (it corrects per
        physical pixel, so the phase is irrelevant) and is reported by
        :meth:`calibration_warnings` instead.
        """
        # Only validate a master that can actually touch a pixel. A master bias
        # is subtracted only when no dark is set (see ``_bias_applies``); with a
        # dark present it is never applied to lights (and the exposure-scaling
        # path in ``_effective_dark`` already shape-guards it), so a leftover
        # wrong-shaped bias must not abort an otherwise-valid dark+flat stack.
        rows = [("dark", self.dark), ("flat", self.flat_norm)]
        if self._bias_applies:
            rows.append(("bias", self.bias))
        for name, arr in rows:
            if arr is not None and tuple(arr.shape) != tuple(shape):
                raise ValueError(
                    f"calibration {name} master is {arr.shape[1]}×{arr.shape[0]} "
                    f"but the frames are {shape[1]}×{shape[0]} — they must match "
                    f"(same camera, binning and no debayering)."
                )
        light_cfa = _norm_bayer(light_bayer_pattern)
        flat_cfa = self.flat_bayer_pattern
        if (self.flat_norm is not None and light_cfa is not None
                and flat_cfa is not None and flat_cfa != light_cfa):
            raise ValueError(
                f"calibration flat master has a {flat_cfa} colour-filter layout "
                f"but your subs are {light_cfa} — dividing by it would swap the "
                f"colour channels and tint every frame. Use a flat shot with the "
                f"same camera and readout mode as your lights."
            )

    def calibration_warnings(
        self,
        light_exposure_s: float | None,
        light_temp_c: float | None = None,
        light_bayer_pattern: str | None = None,
        *,
        light_exposures_s: Iterable[float | None] | None = None,
        light_temps_c: Iterable[float | None] | None = None,
    ) -> list[str]:
        """Advisory (non-fatal) warnings that the master dark doesn't match the
        lights it's calibrating.

        ``light_bayer_pattern`` adds one more: a dark or bias whose declared CFA
        phase differs from the lights'. That one is *not* fatal — a pedestal is
        subtracted per physical pixel, so its Bayer phase genuinely doesn't
        matter — but a phase that disagrees means the master came off a different
        sensor or readout mode, which is worth saying out loud before the user
        blames the result on their sky. (The flat is the fatal case, because a
        flat divides per colour; :meth:`validate` refuses that one.)

        A **flat-dark** whose shape doesn't match the flat gets one too. It is
        the only calibration pick that is neither refused nor applied — the flat
        is simply normalised with its own pedestal still in it (see
        :attr:`flat_dark_shape_mismatch`), so without this the user is told
        nothing at all.

        ``validate()`` only checks master *shape*. But a master dark shot at a
        different **exposure** than the lights silently over/under-subtracts its
        pedestal on the default (non-scaling) path — ``apply_raw`` subtracts the
        full unscaled dark — crushing the background or leaving residual dark
        current on *every* calibrated frame, with nothing telling the user. And a
        dark shot at a very different **temperature** leaves residual dark current
        (which ~doubles per ~6-7 °C) even at a matched exposure. This returns a
        plain-language warning per real mismatch so the stack log can flag it,
        instead of shipping a silently mis-calibrated stack. Empty when the dark
        matches (or there's nothing to compare, or exposure-scaling is on and will
        correct the exposure difference itself).

        ``light_exposures_s`` is **every** light's exposure, where
        ``light_exposure_s`` is only the reference frame's. A target is not
        necessarily one exposure — shoot it at 10 s on one night and 30 s on the
        next and it is one target with two in it — and then the reference frame
        stands in for a session it is not representative of: a dark matched to
        *it* is silently wrong on the rest, and this advisory, asked only about
        it, says nothing at all. Hand over the whole set and the dark is judged
        against all of it, and the wording stops claiming "every frame" about a
        subset. Omit it (every direct caller, and every older one) and the
        reference frame stands in exactly as before.

        ``light_temps_c`` is the same correction for the **temperature** half,
        and it is the same false premise: a target is not one temperature either.
        An uncooled sensor follows the ambient, so a target shot over a winter and
        a summer night is one target with a 20 °C spread in it, and asking only
        the reference frame meant the *same* subs with the *same* dark either
        warned or said nothing depending on which frame ``pick_reference_frame``
        happened to land on — and, when it did warn, named a temperature most of
        the subs were not shot at.

        Temperature differs from exposure in two ways that shape what is said.
        There is no correction for it — a bias cannot rescale a dark to a warmer
        night the way it can to a longer sub — so this only ever *reports*, and
        the binding is deliberately unchanged (a dark that misses a minority is
        still better than no dark at all). And it is continuous rather than a
        setting, so "how many subs does this dark miss?" is a share, not a list:
        the advisory speaks when that share reaches
        :data:`TEMP_MISMATCH_MIN_SHARE` and says the range and the count, so a
        reader can tell "shoot a second dark" from "ignore this". Omit the set
        (every older caller) and the reference frame stands in exactly as before.
        """
        warnings: list[str] = []
        # Whichever pedestal actually reaches the lights (never both — see
        # ``_bias_applies``): its CFA phase disagreeing with theirs is a
        # provenance smell, not a wrong result.
        light_cfa = _norm_bayer(light_bayer_pattern)
        if light_cfa is not None:
            pedestal = ("dark", self.dark_bayer_pattern) if self.dark is not None else (
                ("bias", self.bias_bayer_pattern) if self._bias_applies else (None, None)
            )
            name, cfa = pedestal
            if name is not None and cfa is not None and cfa != light_cfa:
                warnings.append(
                    f"Master {name} has a {cfa} colour-filter layout but your subs "
                    f"are {light_cfa} — it was still subtracted (a {name} corrects "
                    f"each physical pixel, so the layout doesn't change the maths), "
                    f"but it was shot on a different camera or readout mode, so it "
                    f"may not match your sensor's hot pixels."
                )
        # A flat-dark whose shape doesn't match the flat is the one calibration
        # pick that is neither refused nor applied: the stack succeeds, and the
        # only trace is a server-log line the walk-away user never reads. The
        # flat is then normalised with its own dark-current + bias pedestal still
        # in it, which flattens its contrast and leaves part of the vignetting
        # uncorrected on every frame — so say it, the same way a wrong-shaped
        # bias that blocks dark exposure-scaling is said below.
        if self.flat_norm is not None and self.flat_dark_shape_mismatch is not None:
            (fdh, fdw), (fh, fw) = self.flat_dark_shape_mismatch
            warnings.append(
                f"Your flat-dark is {fdw}×{fdh} but the flat is {fw}×{fh} — it "
                f"was built for a different camera or binning mode, so it "
                f"couldn't be subtracted. Your flat still carries its own dark "
                f"pedestal, which leaves some vignetting uncorrected. Use a "
                f"flat-dark shot with the same camera and readout mode as the "
                f"flat, or leave it out."
            )
        if self.dark is None:
            return warnings
        de = self.dark_exposure_s
        # Exposure-scaling (when a shape-matching bias is present) corrects the
        # exposure gap itself, so only warn about it on the plain unscaled-
        # subtraction path. A wrong-shaped bias does NOT enable scaling
        # (``_effective_dark`` falls back to the unscaled dark), so gate on the
        # same predicate the scaling path uses — else the warning is silenced
        # exactly when the unscaled fallback makes it necessary.
        scaling_active = self._dark_scaling_applies
        # Scaling was *asked for* but a wrong-shaped bias silenced it. Worth
        # saying separately: the generic advice below ends with "turn on dark
        # exposure-scaling", which is nonsense to someone who already did, and
        # leaves them with no idea why nothing happened.
        blocked_by_bias_shape = (
            self.scale_dark_to_light and self.dark is not None
            and self.bias is not None and self.bias.shape != self.dark.shape
        )
        # What the lights actually are, when the caller knows. One distinct
        # length (the ordinary case, and every caller that omits the set) falls
        # through to the single-exposure branch below, byte for byte.
        exposures = (
            distinct_exposures(light_exposures_s)
            if light_exposures_s is not None else []
        )
        mismatched = (
            [e for e in exposures if abs(e / float(de) - 1.0) > EXPOSURE_MISMATCH_TOL]
            if de and de > 0 else []
        )
        if not scaling_active and de and de > 0 and len(exposures) > 1 and mismatched:
            # These subs are not all one length, so "your subs are Ns" would be
            # false however N were chosen, and so would "on every frame" — the
            # dark is right for some of them. Say which, and how many lengths
            # there are, because that is the thing the user has to fix.
            lengths = _join_exposures(exposures)
            bad = _join_exposures(mismatched)
            over = [e for e in mismatched if float(de) > e]
            under = [e for e in mismatched if float(de) < e]
            if over and not under:
                effect = "over-subtracted"
            elif under and not over:
                effect = "under-subtracted"
            else:
                effect = "over- or under-subtracted"
            lead = (
                f"Master dark is {de:g}s but these subs were not all shot at the "
                f"same length ({lengths}) — its pedestal will be {effect} on the "
                f"{bad} ones."
            )
            if blocked_by_bias_shape:
                bh, bw = self.bias.shape[0], self.bias.shape[1]
                dh, dw = self.dark.shape[0], self.dark.shape[1]
                warnings.append(
                    f"{lead} Dark exposure-scaling is on, which would have "
                    f"matched it to each sub, but your master bias is {bw}×{bh} "
                    f"and the dark is {dw}×{dh}, so it can't hold the readout "
                    f"pedestal fixed while the dark is rescaled — the dark was "
                    f"subtracted unscaled. Use a bias built from the same camera "
                    f"and binning as the dark."
                )
            else:
                warnings.append(
                    f"{lead} Turn on dark exposure-scaling (needs a master bias) "
                    f"and the dark is matched to each sub as it goes in, or "
                    f"stack each exposure on its own with a dark to match."
                )
        elif (not scaling_active and de and de > 0
                and light_exposure_s and light_exposure_s > 0):
            ratio = float(light_exposure_s) / float(de)
            if abs(ratio - 1.0) > EXPOSURE_MISMATCH_TOL:
                direction = "over" if de > light_exposure_s else "under"
                if blocked_by_bias_shape:
                    bh, bw = self.bias.shape[0], self.bias.shape[1]
                    dh, dw = self.dark.shape[0], self.dark.shape[1]
                    warnings.append(
                        f"Master dark is {de:g}s but your subs are "
                        f"{light_exposure_s:g}s — its pedestal will be "
                        f"{direction}-subtracted on every frame. Dark "
                        f"exposure-scaling is on, but your master bias is "
                        f"{bw}×{bh} and the dark is {dw}×{dh}, so it can't hold "
                        f"the readout pedestal fixed while the dark is rescaled "
                        f"— the dark was subtracted unscaled. Use a bias built "
                        f"from the same camera and binning as the dark, or a "
                        f"{light_exposure_s:g}s dark."
                    )
                else:
                    warnings.append(
                        f"Master dark is {de:g}s but your subs are {light_exposure_s:g}s — "
                        f"its pedestal will be {direction}-subtracted on every frame. "
                        f"Use a dark matched to your exposure, or turn on dark "
                        f"exposure-scaling (needs a master bias)."
                    )
        dt = self.dark_temp_c
        # What the lights' temperatures actually are, when the caller knows.
        # Nothing known (every older caller, and a library that never recorded a
        # ``CCD-TEMP``) falls through to the single-value branch below, byte for
        # byte.
        spread = (
            temperature_spread(light_temps_c) if light_temps_c is not None else None
        )
        if dt is not None and spread is not None:
            lo, med, hi = spread
            n_off, n_all = temperature_mismatch_count(light_temps_c, float(dt))
            if n_all and n_off and n_off >= TEMP_MISMATCH_MIN_SHARE * n_all:
                mixed = (hi - lo) >= TEMP_MISMATCH_TOL_C
                if n_off == n_all and not mixed:
                    # One night's worth of subs, all at much the same temperature
                    # and all of them wrong — today's sentence, said about the
                    # set rather than about whichever frame led it.
                    warnings.append(
                        f"Master dark was shot at {_deg(dt)}°C but your subs are at "
                        f"{_deg(med)}°C — dark current changes with temperature, so "
                        f"some may remain. A temperature-matched dark calibrates best."
                    )
                elif n_off == n_all:
                    warnings.append(
                        f"Master dark was shot at {_deg(dt)}°C but these subs were "
                        f"not all shot at the same temperature ({_deg(lo)}°C to "
                        f"{_deg(hi)}°C), and none of them is within "
                        f"{TEMP_MISMATCH_TOL_C:g}°C of it — dark current changes "
                        f"with temperature, so some will remain on every frame. A "
                        f"dark shot on a night like these calibrates best."
                    )
                else:
                    warnings.append(
                        f"Master dark was shot at {_deg(dt)}°C but these subs were "
                        f"not all shot at the same temperature ({_deg(lo)}°C to "
                        f"{_deg(hi)}°C) — {n_off} of {n_all} are "
                        f"{TEMP_MISMATCH_TOL_C:g}°C or more away from it, so some "
                        f"dark current will remain on those. A second dark shot on "
                        f"a night like theirs calibrates them best."
                    )
        elif (dt is not None and light_temp_c is not None
                and abs(float(dt) - float(light_temp_c)) >= TEMP_MISMATCH_TOL_C):
            warnings.append(
                f"Master dark was shot at {dt:g}°C but your subs are at "
                f"{light_temp_c:g}°C — dark current changes with temperature, so "
                f"some may remain. A temperature-matched dark calibrates best."
            )
        return warnings

    def dark_scaling_exposures(
        self, light_exposures_s: Iterable[float | None] | None,
    ) -> tuple[float, list[float]] | None:
        """``(dark_exposure_s, the distinct sub lengths)`` when the dark really is
        scaled for at least one of them — otherwise ``None``.

        The single answer to "did exposure-scaling actually happen?", so a run's
        provenance can't claim something :meth:`_effective_dark` didn't do. It
        returns non-``None`` under **exactly** the condition that method scales:
        the option is on, a shape-matching master bias holds the readout pedestal
        fixed, and the exposures are known, positive and materially different.

        A *wrong-shaped* bias is the case this exists for. It doesn't enable
        scaling (see :attr:`_dark_scaling_applies`) — the dark is subtracted
        unscaled — but "a bias is loaded" reads as enough from the outside, and a
        stamp written on that looser test tells the user the dark was matched to
        their subs when it wasn't.

        It takes the **set** because the scaling is per frame: ``apply_raw`` is
        handed each sub's own exposure, so on a target shot at 10 s one night and
        30 s the next a 10 s dark is left alone on some subs and tripled on the
        rest. Asked only about a representative value — which is what the run
        provenance used to hand it — that target answers *"nothing was scaled"*
        whenever the representative happens to be the dark's own length, and the
        History line disappears from the one run that most needed it. The second
        element is therefore every distinct length the dark was applied across,
        not the single one it was "scaled to", because on a mixed target there is
        no such single value.

        Lengths are grouped by :func:`distinct_exposures`, so header rounding
        cannot read as a second exposure, and a value that is missing, non-finite
        or non-positive is dropped rather than scaled by.
        """
        if not self._dark_scaling_applies:
            return None
        de = self.dark_exposure_s
        if not de or de <= 0:
            return None
        exposures = distinct_exposures(light_exposures_s or [])
        # Matched exposures leave the dark unscaled, so a set in which *every*
        # length matches has nothing to advertise — exactly the old single-value
        # test, asked of each member.
        if not any(abs(e / float(de) - 1.0) > 1e-3 for e in exposures):
            return None
        return float(de), exposures

    def dark_scaling_provenance(
        self, light_exposure_s: float | None,
    ) -> tuple[float, float] | None:
        """``(dark_exposure_s, light_exposure_s)`` when the dark really is scaled.

        The one-exposure view of :meth:`dark_scaling_exposures`, kept for callers
        that genuinely have a single length to ask about. Implemented in terms of
        it so there is still only one definition of "did scaling happen?".
        """
        got = self.dark_scaling_exposures([light_exposure_s])
        if got is None:
            return None
        de, exposures = got
        return de, exposures[0]

    def _effective_dark(self, light_exposure_s: float | None) -> np.ndarray | None:
        """The dark to subtract, exposure-scaled to the light when opted in.

        Returns the stored dark unchanged unless ``scale_dark_to_light`` is on,
        a master bias with the dark's shape is available, and both exposures are
        known and positive. In that case it returns
        ``bias + (dark − bias)·(t_light / t_dark)`` — the dark current scaled to
        the light's integration time while the exposure-independent bias pedestal
        stays fixed — so a dark shot at one exposure calibrates subs at another.
        A ratio of ~1 (matched exposures) is left as the plain dark to avoid
        needless float work and rounding.
        """
        dark = self.dark
        if (self._dark_scaling_applies
                and self.dark_exposure_s and light_exposure_s
                and self.dark_exposure_s > 0 and light_exposure_s > 0):
            ratio = float(light_exposure_s) / float(self.dark_exposure_s)
            if abs(ratio - 1.0) > 1e-3:
                scaled = (self.bias + (dark - self.bias) * ratio).astype(
                    np.float32, copy=False)
                # ``scaled`` is a fresh array, so the in-place writes below can't
                # mutate the shared master dark/bias.
                #
                # A genuinely no-data *bias* pixel (sanitized to 0) has no
                # trustworthy pedestal to hold fixed, so the formula collapses to
                # ``dark·ratio`` — a scaled dark rather than the documented
                # "subtract the dark unscaled" fallback. Restore the plain dark
                # there, matching what the whole scaling path degrades to without
                # a usable bias. (A dark-no-data pixel below still wins: it maps
                # to 0 = no correction.)
                if self.bias_nodata_mask is not None:
                    scaled[self.bias_nodata_mask] = dark[self.bias_nodata_mask]
                # A genuinely no-data dark pixel (sanitized to 0) must still mean
                # "no correction" here, exactly as on the unscaled path. Scaling
                # turns that 0 into ``bias·(1 − ratio)`` — a spurious pedestal
                # added into every calibrated light there — so restore 0 at those
                # pixels.
                if self.dark_nodata_mask is not None:
                    scaled[self.dark_nodata_mask] = 0.0
                return scaled
        return dark

    def apply_raw(self, raw: np.ndarray,
                  light_exposure_s: float | None = None) -> np.ndarray:
        """Return the calibrated raw mosaic: ``(raw − pedestal) / flat_norm``.

        The subtracted pedestal is the master dark when one is set, otherwise
        the master bias if one is set (``(light − bias) / flat``) — never both,
        so the bias is not double-subtracted through a dark that already
        contains it. When ``scale_dark_to_light`` is enabled and a bias is
        available, the dark is first scaled to ``light_exposure_s`` (see
        :meth:`_effective_dark`); passing ``None`` (the default, and what direct
        callers use) simply leaves the dark unscaled. Masters whose shape
        doesn't match ``raw`` are skipped (this is the defensive per-frame guard;
        :meth:`validate` is the up-front check). Returns a new float32 array —
        the input is not modified.
        """
        out = np.asarray(raw, dtype=np.float32)
        dark = self._effective_dark(light_exposure_s)
        if dark is not None and dark.shape == out.shape:
            out = out - dark
        elif self._bias_applies and self.bias.shape == out.shape:
            out = out - self.bias
        # Repair broken photosites *after* the pedestal subtraction (so the
        # neighbours we median are themselves dark-corrected) and *before* the
        # flat divide (so a defect can't be handed to the flat's own floor as if
        # it were signal). Still the raw Bayer mosaic, so the replacement comes
        # from same-colour neighbours and the defect never reaches the debayer
        # that would smear it into a 3×3 halo. ``None`` (the default) is a
        # no-op; a shape mismatch is a no-op too, matching the per-frame guards
        # above.
        if self.defects is not None:
            if out is raw:
                out = out.copy()
            self.defects.repair(out)
        if self.flat_norm is not None and self.flat_norm.shape == out.shape:
            out = out / self.flat_norm
        result = out.astype(np.float32, copy=False)
        # Honour the "returns a new array" contract even on the no-masters path:
        # if nothing above produced a fresh array (an empty bundle applied to an
        # already-float32 input aliases ``raw``), copy so a caller that mutates
        # the result in place can never corrupt the shared source frame. Any
        # applied master already yields a fresh array, so this only copies on the
        # otherwise-aliasing empty path — never a hot-path double-copy.
        if result is raw:
            result = result.copy()
        return result
