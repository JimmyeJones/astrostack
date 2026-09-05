"""Library-level master calibration store.

Master darks/flats are shared across targets (one master dark for a given
exposure/gain/temperature calibrates every light shot that way), so they live
at the library root rather than inside a single target:

    <library_root>/calibration/
        masters.json          ← registry (list of master metadata)
        dark_1.fits
        flat_2.fits
        ...

The registry is a small JSON file written atomically. Master *builds* run on the
single job worker, but master *deletion* runs on the request threadpool, so the
two are concurrent writers — their read-modify-write sequences are serialised by
``_REGISTRY_LOCK`` (the atomic replace alone only makes each write atomic, not the
read→mutate→write sequence).
"""

from __future__ import annotations

import contextlib
import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from webapp.atomicio import write_text_durably

log = logging.getLogger(__name__)

CALIBRATION_SUBDIR = "calibration"
REGISTRY_NAME = "masters.json"
# Persisted high-water mark of the highest master id ever allocated. Master ids
# (and the ``{kind}_{id}.fits`` filenames derived from them) are *permanent*
# references — a stack run stores the server-resolved calibration path in its
# options — so an id must never be reused for a different master. ``max(current
# ids)+1`` is not monotonic across deletions, so we also carry this counter,
# which survives deleting every registry entry. It lives in its own tiny file so
# ``masters.json`` stays a bare list (an older app version simply ignores this
# file, so a downgrade loses no masters — it only reverts to the old id policy).
NEXT_ID_NAME = "masters_next_id"

# The registry is a small JSON file mutated by a read-modify-write. The durable
# atomic replace in ``_write_registry`` makes each *write* atomic, but not the
# read→mutate→write *sequence*: a build job (`register_master`, on the job
# worker) and a delete (`delete_master`, on the Starlette threadpool) can
# interleave so one clobbers the other's change — a just-built master vanishes
# or a deleted one is resurrected. This process-level lock serialises the two
# mutating sequences. Writes are rare, so the coarse global lock is harmless.
_REGISTRY_LOCK = threading.Lock()

# FITS extensions we'll treat as calibration frames in a source folder.
FITS_GLOBS = ("*.fit", "*.fits", "*.FIT", "*.FITS", "*.fit.gz", "*.fits.gz")


def calibration_dir(library_root: str | Path) -> Path:
    return Path(library_root) / CALIBRATION_SUBDIR


def _registry_path(library_root: str | Path) -> Path:
    return calibration_dir(library_root) / REGISTRY_NAME


def _read_registry(library_root: str | Path) -> list[dict[str, Any]]:
    path = _registry_path(library_root)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("calibration registry unreadable (%s); treating as empty", exc)
        return []


def _write_registry(library_root: str | Path, entries: list[dict[str, Any]]) -> None:
    path = _registry_path(library_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Durable as well as atomic — losing this file to a power cut orphans every
    # built master (the FITS survive, but nothing knows what they are). See
    # webapp.atomicio.
    write_text_durably(path, json.dumps(entries, indent=2), suffix=".json.tmp")


def _read_id_high_water(library_root: str | Path) -> int:
    """Highest master id ever allocated (0 if the counter is missing/unreadable).

    A missing counter (an older library, or a downgrade that never wrote it)
    falls back to the registry max, so allocation is still correct — it just
    can't see ids freed by a *past* deletion. Going forward the counter tracks
    every allocation, so future ids are never reused."""
    path = calibration_dir(library_root) / NEXT_ID_NAME
    try:
        return int(path.read_text().strip())
    except (OSError, ValueError):
        return 0


def _write_id_high_water(library_root: str | Path, value: int) -> None:
    path = calibration_dir(library_root) / NEXT_ID_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    write_text_durably(path, str(int(value)))


def list_masters(library_root: str | Path) -> list[dict[str, Any]]:
    """Return all registered masters (newest first), dropping any whose file
    has since been deleted from disk."""
    entries = _read_registry(library_root)
    out = []
    for e in entries:
        fp = calibration_dir(library_root) / e.get("filename", "")
        e = dict(e, exists=fp.exists())
        out.append(e)
    out.sort(key=lambda e: e.get("created_utc", ""), reverse=True)
    return out


def get_master(library_root: str | Path, master_id: int) -> dict[str, Any] | None:
    for e in _read_registry(library_root):
        if int(e.get("id", -1)) == int(master_id):
            return e
    return None


def master_path(library_root: str | Path, master_id: int) -> Path | None:
    """Absolute path to a master's FITS, or None if unknown/missing."""
    e = get_master(library_root, master_id)
    if e is None:
        return None
    fp = calibration_dir(library_root) / e["filename"]
    return fp if fp.exists() else None


def master_id_for_path(library_root: str | Path, path: str | None) -> int | None:
    """Reverse of :func:`master_path` — the master id whose file is ``path``.

    Used to turn a recorded run's server-resolved calibration path back into the
    master id a form control uses. Matches on filename within the calibration
    dir, so it survives the library being moved. Returns ``None`` if no master
    matches (e.g. the master was deleted since the run)."""
    if not path:
        return None
    name = Path(path).name
    for e in _read_registry(library_root):
        if e.get("filename") == name:
            try:
                return int(e["id"])
            except (KeyError, TypeError, ValueError):
                return None
    return None


def resolve_master_paths(
    library_root: str | Path,
    dark_master_id: Any = None,
    flat_master_id: Any = None,
    flat_dark_master_id: Any = None,
    bias_master_id: Any = None,
) -> tuple[str | None, str | None, str | None, str | None]:
    """Map dark/flat/flat-dark/bias master ids → on-disk FITS paths. Raises
    ``KeyError`` with a human message if an id is given but no such master
    exists.

    ``flat_dark_master_id`` is a dark/bias matched to the flat's exposure,
    subtracted from the flat before normalising; ``bias_master_id`` is a master
    bias subtracted from the lights when no dark is chosen (see
    :meth:`CalibrationMasters.load`).
    """
    def _one(mid: Any, kind: str) -> str | None:
        if mid in (None, "", "none"):
            return None
        e = get_master(library_root, int(mid))
        if e is None:
            raise KeyError(f"no {kind} master with id {mid}")
        fp = master_path(library_root, int(mid))
        if fp is None:
            raise KeyError(f"{kind} master {mid} file is missing")
        return str(fp)

    return (
        _one(dark_master_id, "dark"),
        _one(flat_master_id, "flat"),
        _one(flat_dark_master_id, "flat-dark"),
        _one(bias_master_id, "bias"),
    )


def modal_dim(vals: list[Any]) -> int | None:
    """Most common frame dimension in *vals* (ignoring unknowns), or ``None``.

    A target's frames can carry the odd stray size (a mis-ingested file, a frame
    from another camera), so the *modal* value — not the first or the max — is the
    size ``run_stack`` will validate calibration masters against. Used both to
    reject a wrong-camera master before it can hard-fail an unattended stack and
    to tell the Stack form which masters can't apply to this target."""
    counts: dict[int, int] = {}
    for v in vals:
        if v is None:
            continue
        try:
            k = int(v)
        except (TypeError, ValueError):
            continue
        counts[k] = counts.get(k, 0) + 1
    return max(counts, key=lambda k: counts[k]) if counts else None


def dims_conflict(
    master: dict[str, Any], width_px: int | None, height_px: int | None,
) -> bool:
    """True when *master* was provably built for a different frame size.

    Deliberately one-sided: a master that never recorded its dimensions, or a
    target whose frames never recorded theirs, cannot be *disproved*, so it is not
    a conflict. Every caller that refuses a master on size shares this rule — the
    unattended binder, the saved-pick binder, and the "why was my stack
    uncalibrated?" diagnosis — so they can never disagree about which masters fit.
    """
    mw, mh = master.get("width_px"), master.get("height_px")
    if mw is None or mh is None or width_px is None or height_px is None:
        return False
    try:
        return int(mw) != int(width_px) or int(mh) != int(height_px)
    except (TypeError, ValueError):
        return False


def modal_bayer(vals: list[Any]) -> str | None:
    """Most common usable ``BAYERPAT`` in *vals*, or ``None``.

    The string twin of :func:`modal_dim`, and it borrows the engine's own
    normaliser so "is this the same sensor layout?" has exactly one answer across
    the app: anything that isn't one of the four real 2×2 CFA phases (a blank
    card, a mono frame) is ignored rather than voted for.
    """
    from seestack.calibrate.apply import _norm_bayer

    counts: dict[str, int] = {}
    for v in vals:
        p = _norm_bayer(v)
        if p is None:
            continue
        counts[p] = counts.get(p, 0) + 1
    return max(counts, key=lambda k: counts[k]) if counts else None


def bayer_conflict(master: dict[str, Any], bayer_pattern: str | None) -> bool:
    """True when *master* was provably built on a different colour-filter phase.

    Same one-sided rule as :func:`dims_conflict`: a master (or a target) that
    never recorded a usable ``BAYERPAT`` cannot be *disproved*, so it is not a
    conflict, and nothing that binds today stops binding.

    Only meaningful for a **flat**, which is divided into the raw Bayer mosaic
    per colour — one pixel out of phase and every red photosite is corrected by a
    green value, which tints the whole picture. A dark or bias corrects each
    physical pixel, so its phase genuinely doesn't matter and callers must not
    gate on this; ``CalibrationMasters.calibration_warnings`` mentions it there
    instead. The engine refuses a mismatched flat outright
    (``CalibrationMasters.validate``), so the unattended binders share this test
    for the same reason they share ``dims_conflict``: binding one would turn a
    walk-away stack into an error.
    """
    from seestack.calibrate.apply import _norm_bayer

    mine, theirs = _norm_bayer(master.get("bayer_pattern")), _norm_bayer(bayer_pattern)
    return mine is not None and theirs is not None and mine != theirs


def _match_distance(
    master: dict[str, Any], *, exposure_s: float | None,
    gain: float | None, sensor_temp_c: float | None, kind: str,
) -> float:
    """How poorly a master matches a target's acquisition params (lower = better).

    Darks capture thermal + bias signal at a *specific* exposure/gain/temperature,
    so exposure must match closely. Flats are exposure-independent (they're
    normalised), so only gain/optical-train and temperature matter. A param that
    is unknown on either side neither helps nor hurts (contributes 0).
    """
    d = 0.0
    if kind == "dark" and exposure_s and master.get("exposure_s"):
        d += 3.0 * abs(float(master["exposure_s"]) - exposure_s) / max(exposure_s, 1e-6)
    if gain is not None and master.get("gain") is not None:
        d += abs(float(master["gain"]) - gain) / max(abs(gain), 1.0)
    if sensor_temp_c is not None and master.get("sensor_temp_c") is not None:
        d += 0.1 * abs(float(master["sensor_temp_c"]) - sensor_temp_c)
    return d


def recommend_masters(
    masters: list[dict[str, Any]], *, exposure_s: float | None = None,
    gain: float | None = None, sensor_temp_c: float | None = None,
) -> dict[str, Any]:
    """Pick the best-matching dark, flat and bias for a target's acquisition params.

    Returns the recommended master ids (or None if none of a kind exist) plus a
    per-master match score in 0..1 (higher = better) so the UI can badge the
    best option. Only masters whose file still exists are considered. A bias is
    exposure-independent (the zero-second read pedestal), so — like a flat — it's
    matched on gain/temperature only.
    """
    scores: dict[int, float] = {}
    best: dict[str, tuple[int, float]] = {}
    darks: list[dict[str, Any]] = []
    flats_by_id: dict[int, dict[str, Any]] = {}
    for m in masters:
        if not m.get("exists", True):
            continue
        kind = str(m.get("kind", ""))
        if kind not in ("dark", "flat", "bias"):
            continue
        try:
            mid = int(m["id"])
        except (KeyError, TypeError, ValueError):
            continue
        dist = _match_distance(m, exposure_s=exposure_s, gain=gain,
                               sensor_temp_c=sensor_temp_c, kind=kind)
        score = 1.0 / (1.0 + dist)
        scores[mid] = round(score, 4)
        cur = best.get(kind)
        if cur is None or dist < cur[1]:
            best[kind] = (mid, dist)
        if kind == "dark":
            darks.append(m)
        else:
            flats_by_id[mid] = m

    flat_id = best["flat"][0] if "flat" in best else None
    flat_dark_id = _recommend_flat_dark(darks, flats_by_id.get(flat_id))
    return {
        "params": {"exposure_s": exposure_s, "gain": gain,
                   "sensor_temp_c": sensor_temp_c},
        "dark_master_id": best["dark"][0] if "dark" in best else None,
        "flat_master_id": flat_id,
        "flat_dark_master_id": flat_dark_id,
        "bias_master_id": best["bias"][0] if "bias" in best else None,
        "scores": scores,
    }


# The Stack form warns when a chosen dark's exposure is more than 25% off the
# subs (`Stack.tsx` `expMismatch`); mirror that threshold as the confidence gate
# for *unattended* auto-binding, where there is no human to see the warning.
_AUTO_BIND_EXP_MISMATCH_FRAC = 0.25

# A flat is exposure-independent, so :func:`recommend_masters` always returns the
# best *available* one no matter how poorly its gain/temperature match. For
# *unattended* binding — where no human sees the interactive form's warning — also
# require the flat's gain/temperature to be a confident match, so a flat shot on a
# genuinely different rig (a different scope/reducer on the same camera body, or a
# very different gain/temperature) is left off rather than dividing the walk-away
# stack by the wrong illumination pattern. This mirrors the dark's exposure gate:
# "leave the flat uncalibrated rather than risk applying the wrong one". The bar is
# the same match distance the flat-dark already uses (:data:`_FLAT_DARK_MAX_DIST`);
# because an unknown gain/temperature on either side contributes 0 distance (see
# :func:`_match_distance`), a flat that simply never recorded them still binds,
# exactly as today — the gate only *tightens*, catching a materially mismatched flat.
_AUTO_BIND_FLAT_MAX_DIST = 1.0

# A master bias is the readout pedestal *plus* fixed-pattern structure (amp glow,
# column offsets) that scales with the camera's gain/offset. Like the flat, it is
# exposure-independent, so :func:`recommend_masters` returns the best *available*
# bias no matter how poorly its gain/temperature match. For *unattended* binding —
# where the bias is subtracted from the lights (no dark) with no human to see the
# form's warning — require the same confident gain/temperature match: a bias shot
# at a very different gain would subtract the wrong pedestal and a mis-scaled fixed
# pattern, and the per-frame background subtraction only removes the DC offset, not
# that spatial structure. Same bar as the flat; an unknown gain/temperature still
# binds (the gate only *tightens*).
_AUTO_BIND_BIAS_MAX_DIST = _AUTO_BIND_FLAT_MAX_DIST

# A master dark encodes thermal signal *and* the gain-dependent bias pedestal, so a
# dark shot at a genuinely different gain/offset (same integration time, different
# rig) over-/under-subtracts on the walk-away path. The dark already has an exposure
# gate (:data:`_AUTO_BIND_EXP_MISMATCH_FRAC`); this adds the missing gain/temperature
# gate to complete the "auto-bind only a master we're confident about" contract the
# flat (:data:`_AUTO_BIND_FLAT_MAX_DIST`) and bias (:data:`_AUTO_BIND_BIAS_MAX_DIST`)
# already have. Same bar as those; an unknown gain/temperature still binds (the gate
# only *tightens*, catching a materially mismatched-gain dark).
_AUTO_BIND_DARK_MAX_DIST = _AUTO_BIND_FLAT_MAX_DIST


#: ``auto_bind_master_ids`` key → the ``StackOptions`` path key it resolves to.
#: One table, so the id form and the path form of a confident binding can never
#: name different things.
_BOUND_ID_TO_PATH_KEY = {
    "dark_master_id": "dark_path",
    "flat_master_id": "flat_path",
    "flat_dark_master_id": "flat_dark_path",
    "bias_master_id": "bias_path",
}


def auto_bind_master_paths(
    library_root: str | Path,
    masters: list[dict[str, Any]],
    *,
    exposure_s: float | None = None,
    gain: float | None = None,
    sensor_temp_c: float | None = None,
    width_px: int | None = None,
    height_px: int | None = None,
    bayer_pattern: str | None = None,
) -> dict[str, Any]:
    """Calibration master *paths* safe to auto-apply in an *unattended* stack.

    The ``StackOptions``-shaped view of :func:`auto_bind_master_ids` — the same
    decision, resolved to the on-disk files a run needs. (The interactive Stack
    form wants the *ids*, because that is what its pickers hold; taking both from
    one function is what keeps the watched and unattended paths agreeing.)

    Returns only the confident ``StackOptions`` keys (``dark_path`` / ``flat_path``
    / ``flat_dark_path`` / ``bias_path``, plus ``scale_dark_to_light=True`` when a
    dark is bound for exposure-scaling); an empty dict means "leave the stack
    uncalibrated". Never raises.
    """
    bound = auto_bind_master_ids(
        library_root, masters, exposure_s=exposure_s, gain=gain,
        sensor_temp_c=sensor_temp_c, width_px=width_px, height_px=height_px,
        bayer_pattern=bayer_pattern)
    out: dict[str, Any] = {}
    for id_key, path_key in _BOUND_ID_TO_PATH_KEY.items():
        mid = bound.get(id_key)
        if mid is None:
            continue
        p = master_path(library_root, int(mid))
        if p is not None:
            out[path_key] = str(p)
    if bound.get("scale_dark_to_light") and "dark_path" in out and "bias_path" in out:
        out["scale_dark_to_light"] = True
    return out


def auto_bind_master_ids(
    library_root: str | Path,
    masters: list[dict[str, Any]],
    *,
    exposure_s: float | None = None,
    gain: float | None = None,
    sensor_temp_c: float | None = None,
    width_px: int | None = None,
    height_px: int | None = None,
    bayer_pattern: str | None = None,
) -> dict[str, Any]:
    """Calibration master *ids* safe to auto-apply in an *unattended* stack.

    The single definition of "which masters are we confident about for these
    subs?". :func:`auto_bind_master_paths` is the same answer resolved to files
    (what a run needs); the Stack form reads the ids (what its pickers hold), so
    a watched stack can land on exactly the masters a walk-away stack would.

    :func:`recommend_masters` always returns the best *available* master of each
    kind and leaves the interactive Stack form to *warn* on a poor match. In an
    autonomous chain there is no human to see that warning, so this is stricter —
    it binds only a master we are *confident* about:

    * a **dark** whose gain/temperature confidently match (a dark encodes the
      gain-dependent bias pedestal, so a wrong-gain dark mis-subtracts even at the
      right exposure) and whose exposure either matches the subs within 25% (the
      Stack form's own mismatch threshold) *or* — when only the exposure is off —
      can be exposure-scaled to the subs because a confident master bias is also
      available (bound as ``dark_master_id`` + ``bias_master_id`` +
      ``scale_dark_to_light``, the unattended equivalent of the form's "select your
      master bias and scale the dark"). A dark with a materially mismatched
      gain/temperature, or a
      mismatched exposure with no scalable bias, is left off, so the stack stays
      uncalibrated exactly as today rather than risking an over-/under-subtraction;
    * the recommended **flat** and its **flat-dark** (flats are exposure
      independent, and the flat-dark is already distance-gated inside
      :func:`_recommend_flat_dark`);
    * a **bias** only when no dark was bound (a dark already carries the bias).

    When ``width_px``/``height_px`` are given (the subs' raw, un-debayered
    dimensions), a master is bound only if *its* recorded dimensions match. A
    master built for a different camera/binning would otherwise be bound and then
    make ``run_stack`` **hard-fail** at :meth:`CalibrationMasters.validate` — the
    opposite of this helper's "leave uncalibrated rather than risk anything"
    contract. The dimension gate is skipped only when the subs' dimensions are
    unknown (then behaviour is unchanged from today).

    Returns only the confident keys (``dark_master_id`` / ``flat_master_id`` /
    ``flat_dark_master_id`` / ``bias_master_id``, plus ``scale_dark_to_light=True``
    when a dark is bound for exposure-scaling); an empty dict means "leave the
    stack uncalibrated". Never raises — a master that can't be resolved to an
    on-disk file is simply skipped.
    """
    rec = recommend_masters(masters, exposure_s=exposure_s, gain=gain,
                            sensor_temp_c=sensor_temp_c)
    by_id: dict[int, dict[str, Any]] = {}
    for m in masters:
        try:
            by_id[int(m["id"])] = m
        except (KeyError, TypeError, ValueError):
            continue

    def _dims_ok(mid: Any) -> bool:
        """Master ``mid``'s dimensions match the subs' (or the subs' are unknown,
        so we can't gate). A master whose own dimensions are unrecorded can't be
        confirmed to match, so it fails the gate when the subs' dims *are* known."""
        if width_px is None or height_px is None:
            return True  # nothing to gate against — preserve prior behaviour
        m = by_id.get(int(mid)) if mid is not None else None
        if not m:
            return False
        mw, mh = m.get("width_px"), m.get("height_px")
        if mw is None or mh is None:
            return False
        try:
            return int(mw) == int(width_px) and int(mh) == int(height_px)
        except (TypeError, ValueError):
            return False

    def _bindable(mid: Any) -> int | None:
        """``mid`` as an int when this master may be bound: its dimensions match
        the subs' *and* its file still resolves on disk. ``None`` otherwise, so a
        master whose file has gone is skipped exactly as it always was."""
        if mid is None or not _dims_ok(mid):
            return None
        return int(mid) if master_path(library_root, int(mid)) is not None else None

    out: dict[str, Any] = {}

    # Dark — bind only when its gain/temperature confidently match the subs (a dark
    # encodes the gain-dependent bias pedestal, so a wrong-gain dark mis-subtracts
    # even at the right exposure; unknown gain/temperature still passes, so the gate
    # only tightens on a materially mismatched-gain dark). Given that confident
    # gain/temperature match:
    #   * bind the dark directly when its exposure also matches within 25%;
    #   * else — the dark's *exposure* is the only mismatch — recover it by
    #     exposure-scaling to the subs, but only when a confident master bias is
    #     also available and the dark's + subs' exposures are both known
    #     (dark_path + bias_path + scale_dark_to_light, the engine's
    #     ``bias + (dark − bias)·t_light/t_dark``). This is the unattended
    #     equivalent of the interactive form's "select your master bias and scale
    #     the dark" nudge; it recovers the thermal signal a bias-only fallback
    #     can't. Without a confident bias (or a known exposure) the dark is left
    #     off, so the stack stays uncalibrated exactly as today.
    #
    # `recommend_masters` ranks darks by *combined* distance (exposure ×3 + gain +
    # temp) and returns only the single closest — but that closest dark can *fail*
    # its bind gate (a mismatched gain, or a mismatched exposure with no scalable
    # bias) while a slightly-further dark would bind cleanly. Classic case: a
    # gain-mismatched-but-exposure-perfect dark out-ranks a gain-matched dark that
    # only needs bias-scaling, so keying off the single top pick leaves the stack
    # dark-uncalibrated even though a usable dark existed. So try every dark in
    # ascending match distance and bind the *first that clears a gate*. This never
    # binds a dark we wouldn't already trust (each candidate still passes the same
    # gain/temp + exposure/scalable gates); it only stops the best-ranked-but-
    # unbindable dark from masking a bindable one. Ordering by distance means the
    # closest bindable dark wins (an exposure-perfect dark is preferred over one
    # that needs scaling, since its exposure term is 0).
    def _try_bind_dark(cand: dict[str, Any]) -> dict[str, Any] | None:
        """The confident dark-binding keys for master ``cand``
        (``dark_master_id`` alone, or ``dark_master_id`` + ``bias_master_id`` +
        ``scale_dark_to_light`` when only the exposure is off and a confident bias
        can scale it), or ``None`` when it can't be confidently bound to these
        subs."""
        if not exposure_s or not _dark_match_confident(
                cand, gain=gain, sensor_temp_c=sensor_temp_c):
            return None
        dexp = cand.get("exposure_s")
        if not (dexp and float(dexp) > 0):
            return None  # a dark's thermal signal is exposure-specific — can't gate
        mid = cand.get("id")
        if abs(float(dexp) - exposure_s) / exposure_s <= _AUTO_BIND_EXP_MISMATCH_FRAC:
            d = _bindable(mid)
            return {"dark_master_id": d} if d is not None else None
        # Exposure mismatch, gain/temp confident: recover via exposure-scaling if a
        # confident master bias (with matching dimensions) is available.
        bias_id = rec.get("bias_master_id")
        bm = by_id.get(int(bias_id)) if bias_id is not None else None
        if bm is not None and _bias_match_confident(
                bm, gain=gain, sensor_temp_c=sensor_temp_c):
            dp = _bindable(mid)
            bp = _bindable(bias_id)
            if dp is not None and bp is not None:
                return {"dark_master_id": dp, "bias_master_id": bp,
                        "scale_dark_to_light": True}
        return None

    dark_bound = False
    dark_candidates = sorted(
        (m for m in by_id.values()
         if str(m.get("kind", "")) == "dark" and m.get("exists", True)),
        key=lambda m: _match_distance(
            m, exposure_s=exposure_s, gain=gain,
            sensor_temp_c=sensor_temp_c, kind="dark"),
    )
    for cand in dark_candidates:
        keys = _try_bind_dark(cand)
        if keys:
            out.update(keys)
            dark_bound = True
            break

    # Flat (+ its flat-dark) — exposure independent, but only when its
    # gain/temperature confidently match the subs (a flat from a different rig
    # would divide in the wrong illumination pattern; unknown params still pass).
    # Mirror the dark path: ``recommend_masters`` returns only the single closest
    # flat, but that flat can fail its confidence *or* dimension gate while a
    # slightly-further flat binds cleanly (e.g. the top-ranked flat is from a
    # different-sized camera, but a second confident, same-dimension flat exists).
    # Keying off only the top pick would then leave the stack flat-uncalibrated
    # even though a usable flat existed — so try every flat in ascending match
    # distance and bind the first that clears both gates. This never binds a flat
    # we wouldn't already trust; it only stops the best-ranked-but-unbindable flat
    # from masking a bindable one. Byte-for-byte unchanged when the top flat binds.
    flat_candidates = sorted(
        (m for m in by_id.values()
         if str(m.get("kind", "")) == "flat" and m.get("exists", True)),
        key=lambda m: _match_distance(
            m, exposure_s=None, gain=gain,
            sensor_temp_c=sensor_temp_c, kind="flat"),
    )
    for cand in flat_candidates:
        if not _flat_match_confident(cand, gain=gain, sensor_temp_c=sensor_temp_c):
            continue
        # A flat divides into the raw Bayer mosaic per colour, so one built on a
        # different CFA phase would tint every frame — and the engine refuses it
        # outright (``CalibrationMasters.validate``), which would turn a
        # walk-away stack into an error. Skip it here for the same reason the
        # dimension gate exists, and let a further-but-matching flat bind.
        if bayer_conflict(cand, bayer_pattern):
            continue
        p = _bindable(cand.get("id"))
        if p is None:
            continue
        out["flat_master_id"] = p
        # The flat-dark calibrates *this* flat, so match it to the flat we bound
        # (not necessarily ``recommend_masters``' top flat).
        fd = _bindable(_recommend_flat_dark(dark_candidates, cand))
        if fd is not None:
            out["flat_dark_master_id"] = fd
        break

    # Bias — only meaningful for the lights when no dark was applied, and (like the
    # flat) only when its gain/temperature confidently match the subs; a bias from a
    # different rig would subtract the wrong pedestal + fixed pattern (unknown params
    # still pass, so the gate only tightens on a materially mismatched bias). Same
    # top-pick-can-fail-a-gate reasoning as the dark/flat: iterate the candidates in
    # ascending match distance and bind the first that clears both gates.
    if not dark_bound:
        bias_candidates = sorted(
            (m for m in by_id.values()
             if str(m.get("kind", "")) == "bias" and m.get("exists", True)),
            key=lambda m: _match_distance(
                m, exposure_s=None, gain=gain,
                sensor_temp_c=sensor_temp_c, kind="bias"),
        )
        for cand in bias_candidates:
            if not _bias_match_confident(cand, gain=gain, sensor_temp_c=sensor_temp_c):
                continue
            bp = _bindable(cand.get("id"))
            if bp is None:
                continue
            out["bias_master_id"] = bp
            break

    return out


def _flat_match_confident(
    flat: dict[str, Any] | None, *,
    gain: float | None, sensor_temp_c: float | None,
) -> bool:
    """Whether a recommended flat matches the subs' gain/temperature closely enough
    to auto-bind unattended (see :data:`_AUTO_BIND_FLAT_MAX_DIST`).

    Uses the same gain/temperature match distance as the recommender; a flat is
    exposure independent, so exposure is ignored. Unknown gain/temperature on
    either side contributes 0 distance, so a flat missing those fields still
    clears the bar (behaviour unchanged from before the gate)."""
    if not flat:
        return False
    dist = _match_distance(flat, exposure_s=None, gain=gain,
                           sensor_temp_c=sensor_temp_c, kind="flat")
    return dist <= _AUTO_BIND_FLAT_MAX_DIST


def _dark_match_confident(
    dark: dict[str, Any] | None, *,
    gain: float | None, sensor_temp_c: float | None,
) -> bool:
    """Whether a recommended dark matches the subs' gain/temperature closely enough
    to auto-bind unattended (see :data:`_AUTO_BIND_DARK_MAX_DIST`).

    The *exposure* gate is applied separately by the caller (a dark's thermal
    signal is exposure-specific); this checks only the gain/temperature match, so
    exposure is passed as ``None`` (its distance term is skipped). Unknown
    gain/temperature on either side contributes 0 distance, so a dark missing those
    fields still clears the bar (behaviour unchanged from before the gate)."""
    if not dark:
        return False
    dist = _match_distance(dark, exposure_s=None, gain=gain,
                           sensor_temp_c=sensor_temp_c, kind="dark")
    return dist <= _AUTO_BIND_DARK_MAX_DIST


def _bias_match_confident(
    bias: dict[str, Any] | None, *,
    gain: float | None, sensor_temp_c: float | None,
) -> bool:
    """Whether a recommended bias matches the subs' gain/temperature closely enough
    to auto-bind unattended (see :data:`_AUTO_BIND_BIAS_MAX_DIST`).

    Uses the same gain/temperature match distance as the flat; a bias is a
    zero-second read, so exposure is ignored. Unknown gain/temperature on either
    side contributes 0 distance, so a bias missing those fields still clears the
    bar (behaviour unchanged from before the gate)."""
    if not bias:
        return False
    dist = _match_distance(bias, exposure_s=None, gain=gain,
                           sensor_temp_c=sensor_temp_c, kind="bias")
    return dist <= _AUTO_BIND_BIAS_MAX_DIST


def _wrong_size_advice(
    masters: list[dict[str, Any]], *, width_px: int | None, height_px: int | None,
) -> str | None:
    """Advice for the "you *have* masters, but they're for another camera" case.

    A master whose dimensions don't match the frames is refused outright — the
    unattended binders skip it and ``CalibrationMasters.validate`` would fail the
    run — so the stack comes out uncalibrated while the library visibly holds a
    dark/flat. That reads as a bug to a beginner, and the generic "build or pick a
    master" copy doesn't explain it. Only fires when **every** master of that kind
    conflicts: with one usable master left, the size isn't why the stack was
    uncalibrated.
    """
    if width_px is None or height_px is None:
        return None
    for kind in ("dark", "flat"):
        owned = [m for m in masters
                 if m.get("kind") == kind and m.get("exists", True)]
        if not owned or not all(
                dims_conflict(m, width_px, height_px) for m in owned):
            continue
        build = (f"Build a master {kind} from frames shot the same way as these "
                 f"subs.")
        if len(owned) == 1:
            m = owned[0]
            return (
                f"Your master {kind} was built at "
                f"{m.get('width_px')}×{m.get('height_px')}, but this target's "
                f"frames are {width_px}×{height_px} — a different camera or "
                f"binning mode, so it can't be applied. {build}"
            )
        return (
            f"None of your master {kind}s match this target's frames "
            f"({width_px}×{height_px}) — they were built for a different camera "
            f"or binning mode, so none can be applied. {build}"
        )
    return None


def diagnose_uncalibrated(
    masters: list[dict[str, Any]], *,
    exposure_s: float | None = None, gain: float | None = None,
    sensor_temp_c: float | None = None,
    width_px: int | None = None, height_px: int | None = None,
) -> str | None:
    """A *specific*, actionable hint for why an unattended stack came out
    uncalibrated — when the library holds a master that's usable but for one
    concrete, fixable thing.

    Two signatures are detected, most-blocking first:

    * **Wrong camera/binning** (:func:`_wrong_size_advice`): every master dark (or
      flat) the library owns was built at a different frame size, so none of them
      *can* apply. Checked first because no other advice is true while the master
      is unusable — and because it's the one case where the user can see a master
      sitting right there in the library.
    * **Exposure-mismatched dark with no bias to scale it** — the signature
      v0.103.11–0.103.12 narrowed the still-uncalibrated dark case down to: the
      library's best-matching master **dark** confidently matches the subs'
      gain/temperature but its **exposure** is mismatched (so
      :func:`auto_bind_master_paths` won't bind it directly), and there is **no
      confident master bias** to exposure-scale it against (with one, v0.103.12
      would have scaled the dark and the stack would *be* calibrated). The fix is
      concrete — build a master bias — after which the exposure-scaling reuses the
      existing dark automatically.

    ``width_px``/``height_px`` are the target's modal raw frame dimensions; when
    either is unknown the size signature is skipped and behaviour is unchanged.

    Returns the advice string, or ``None`` when no specific advice applies (the
    caller then falls back to the generic copy). Pure and never raises — a master
    with unusable fields is simply skipped, mirroring the auto-bind helpers.
    """
    size_advice = _wrong_size_advice(
        masters, width_px=width_px, height_px=height_px)
    if size_advice:
        return size_advice
    if not exposure_s or exposure_s <= 0:
        return None
    rec = recommend_masters(masters, exposure_s=exposure_s, gain=gain,
                            sensor_temp_c=sensor_temp_c)
    by_id: dict[int, dict[str, Any]] = {}
    for m in masters:
        try:
            by_id[int(m["id"])] = m
        except (KeyError, TypeError, ValueError):
            continue

    dark_id = rec.get("dark_master_id")
    dm = by_id.get(int(dark_id)) if dark_id is not None else None
    if dm is None or not _dark_match_confident(
            dm, gain=gain, sensor_temp_c=sensor_temp_c):
        return None
    try:
        dexp = float(dm.get("exposure_s"))
    except (TypeError, ValueError):
        return None
    if dexp <= 0:
        return None
    # A dark whose exposure already matches within the bind threshold would have
    # been bound directly — nothing to advise.
    if abs(dexp - exposure_s) / exposure_s <= _AUTO_BIND_EXP_MISMATCH_FRAC:
        return None
    # A confident master bias would let v0.103.12 exposure-scale the dark, so the
    # stack wouldn't be uncalibrated — this advice only applies when one is absent.
    bias_id = rec.get("bias_master_id")
    bm = by_id.get(int(bias_id)) if bias_id is not None else None
    if bm is not None and _bias_match_confident(
            bm, gain=gain, sensor_temp_c=sensor_temp_c):
        return None
    return (
        f"You have a master dark taken at a different exposure "
        f"({_fmt_seconds(dexp)} vs {_fmt_seconds(exposure_s)}) — build a master "
        f"bias and AstroStack will scale that dark to your subs automatically."
    )


def _fmt_seconds(value: float) -> str:
    """Format an exposure in seconds without a trailing ``.0`` (30.0 → ``30s``,
    2.5 → ``2.5s``) for user-facing calibration copy."""
    return f"{value:g}s"


#: One target's acquisition signature, as :func:`master_coverage` needs it: the
#: same five numbers every other binder gates on (median exposure/gain/sensor
#: temperature of the accepted subs, plus their modal raw frame size). A plain
#: dict keeps the helper pure and unit-testable without a Library/Project.
COVERAGE_TARGET_KEYS = (
    "name", "safe_name", "exposure_s", "gain", "sensor_temp_c",
    "width_px", "height_px", "bayer_pattern",
)


def coverage_miss_reason(
    master: dict[str, Any], *,
    exposure_s: float | None = None,
    gain: float | None = None,
    sensor_temp_c: float | None = None,
    width_px: int | None = None,
    height_px: int | None = None,
    bayer_pattern: str | None = None,
) -> str | None:
    """*Why* the unattended binder can't apply ``master`` to these subs, in one
    plain-language clause — or ``None`` when nothing about the master itself
    disqualifies it.

    :func:`master_coverage` can tell a beginner *which* of their targets a master
    misses; that's the diagnosis, but the cure is still "go read the build form and
    work out what numbers to use". The gates already know the answer — a frame-size
    conflict, a gain the dark was never shot at, an exposure too far off to trust —
    so this names it: *"your subs are 10s, this dark is 30s"*.

    Mirrors :func:`auto_bind_master_paths`' gates exactly (same thresholds, same
    one-sided "can't be disproved isn't a conflict" rule) and is checked most-
    decisive-first, so the clause names the blocker the user would have to fix
    first. ``None`` means every gate passes on its own — the master was simply
    passed over for a closer one of its kind, which only the caller (who knows what
    *was* bound) can phrase. Pure, so it needs no library on disk; never raises.
    """
    if not master.get("exists", True):
        return "its file is missing from your calibration library"

    # 1. Frame size — the most decisive blocker (a wrong-size master can't be
    #    applied at all, whatever else matches).
    mw, mh = master.get("width_px"), master.get("height_px")
    if dims_conflict(master, width_px, height_px):
        return (f"it was built at {mw}×{mh}, your subs are {width_px}×{height_px} "
                f"— a different camera or binning")
    if (width_px is not None and height_px is not None
            and (mw is None or mh is None)):
        return ("it doesn't record the frame size it was built at, so AstroStack "
                "can't confirm it fits your subs")

    kind = str(master.get("kind") or "")
    # 1b. Colour-filter phase — flats only, and the same one-sided test the binder
    #     uses. A flat divides into the raw Bayer mosaic per colour, so one phase
    #     out corrects red photosites with green values and tints every frame; the
    #     engine refuses it, so the binder skips it.
    if kind == "flat" and bayer_conflict(master, bayer_pattern):
        return (f"it was built on a {master.get('bayer_pattern')} colour-filter "
                f"layout, your subs are {bayer_pattern} — a different camera or "
                f"readout mode")
    # 2. Gain / sensor temperature — the shared confidence gate for every kind.
    confident = {
        "dark": _dark_match_confident, "flat": _flat_match_confident,
        "bias": _bias_match_confident,
    }.get(kind)
    if confident is not None and not confident(
            master, gain=gain, sensor_temp_c=sensor_temp_c):
        return _acquisition_reason(master, gain=gain, sensor_temp_c=sensor_temp_c)

    # 3. Exposure — darks only (a flat/bias is exposure-independent).
    if kind == "dark":
        if not exposure_s:
            return ("your subs don't record their exposure, so a dark can't be "
                    "matched to them safely")
        dexp = master.get("exposure_s")
        try:
            dexp = float(dexp) if dexp is not None else None
        except (TypeError, ValueError):
            dexp = None
        if not dexp or dexp <= 0:
            return ("it doesn't record its own exposure, so it can't be matched to "
                    "your subs safely")
        if abs(dexp - exposure_s) / exposure_s > _AUTO_BIND_EXP_MISMATCH_FRAC:
            return (f"your subs are {_fmt_seconds(exposure_s)}, this dark is "
                    f"{_fmt_seconds(dexp)} — build a master bias and AstroStack "
                    f"can scale it to your subs")
    return None


def _acquisition_reason(
    master: dict[str, Any], *, gain: float | None, sensor_temp_c: float | None,
) -> str:
    """The gain/temperature half of :func:`coverage_miss_reason`: whichever of the
    two actually differs, named with both numbers.

    The gate is a *combined* distance, so name the term that dominates it (gain is
    weighted 1.0 per relative unit, temperature 0.1 per °C — see
    :func:`_match_distance`) and fall back to a generic clause when neither side
    recorded enough to point at one."""
    # Parse once and carry the floats into the copy: a registry value that is a
    # numeric *string* must not format-crash after passing the distance maths.
    mgain = mtemp = None
    gain_d = temp_d = 0.0
    if gain is not None and master.get("gain") is not None:
        with contextlib.suppress(TypeError, ValueError):
            mgain = float(master["gain"])
            gain_d = abs(mgain - gain) / max(abs(gain), 1.0)
    if sensor_temp_c is not None and master.get("sensor_temp_c") is not None:
        with contextlib.suppress(TypeError, ValueError):
            mtemp = float(master["sensor_temp_c"])
            temp_d = 0.1 * abs(mtemp - sensor_temp_c)
    if gain_d >= temp_d and gain_d > 0 and mgain is not None:
        return f"it was shot at gain {mgain:g}, your subs at gain {gain:g}"
    if temp_d > 0 and mtemp is not None:
        return (f"its sensor was {mtemp:g}°C, your subs were "
                f"{float(sensor_temp_c):g}°C")
    return "it wasn't shot the same way as these subs"


def master_coverage(
    library_root: str | Path,
    masters: list[dict[str, Any]],
    targets: list[dict[str, Any]],
) -> dict[str, Any]:
    """Which of the user's targets each master can actually calibrate.

    The Calibration page lists the masters you've built, but nothing connects them
    back to the library: a beginner who built one 30 s dark has no idea it covers
    four of their six targets and misses the two they shot at 10 s (or the ones
    from a second Seestar). Today they only find out target-by-target, on the
    Stack form or after an uncalibrated result — six times over.

    "Covers" is deliberately the **strict, unattended** test: a master counts for a
    target only if :func:`auto_bind_master_paths` — the same confidence gate the
    walk-away auto-stack binds through — would apply it. So the roll-up promises
    exactly what the app will actually do on its own, never something the user
    would have to pick by hand. That also means a target whose subs recorded no
    exposure/gain is judged on what *is* known, exactly as an unattended stack
    would judge it.

    ``targets`` are plain dicts (see :data:`COVERAGE_TARGET_KEYS`) so this stays a
    pure read-only function over the registry — the caller does the per-target
    frame read. Returns::

        {"n_targets": int,
         "masters": [{"id", "name", "kind", "n_covered", "covered", "missed"}, …],
         "uncovered": [target names with no master at all]}

    ``masters`` keeps the input order (the registry's newest-first), and every
    name list is in the caller's target order, so the display is stable between
    polls. Never raises: a master whose file has gone simply covers nothing.
    """
    bound_ids: list[set[int]] = []
    bound_dark: list[bool] = []
    for t in targets:
        try:
            # The *id* form of the same binding the unattended stack uses: this
            # roll-up only ever wanted "which masters", and taking the ids
            # directly saves resolving each one to a file and looking it back up
            # in the registry to recover the id it started as.
            bound = auto_bind_master_ids(
                library_root, masters,
                exposure_s=t.get("exposure_s"), gain=t.get("gain"),
                sensor_temp_c=t.get("sensor_temp_c"),
                width_px=t.get("width_px"), height_px=t.get("height_px"),
                bayer_pattern=t.get("bayer_pattern"),
            )
        except Exception:  # noqa: BLE001 — a roll-up is a nicety, never a 500
            log.warning("master coverage probe failed for %r", t.get("name"))
            bound = {}
        ids = {int(mid) for key in _BOUND_ID_TO_PATH_KEY
               if (mid := bound.get(key)) is not None}
        bound_ids.append(ids)
        bound_dark.append(bound.get("dark_master_id") is not None)

    names = [str(t.get("name") or t.get("safe_name") or "?") for t in targets]
    rows: list[dict[str, Any]] = []
    for m in masters:
        try:
            mid = int(m["id"])
        except (KeyError, TypeError, ValueError):
            continue
        kind = str(m.get("kind") or "?")
        covered = [n for n, ids in zip(names, bound_ids) if mid in ids]
        missed = [n for n, ids in zip(names, bound_ids) if mid not in ids]
        # Why each miss misses. A bare list of names is the diagnosis; the reason
        # is what turns it into something the user can act on. `None` back from
        # the pure helper means the master clears every gate on its own, so it was
        # passed over rather than rejected — only we know what won instead.
        detail = []
        for t, ids, has_dark in zip(targets, bound_ids, bound_dark, strict=True):
            if mid in ids:
                continue
            name = str(t.get("name") or t.get("safe_name") or "?")
            reason = coverage_miss_reason(
                m, exposure_s=t.get("exposure_s"), gain=t.get("gain"),
                sensor_temp_c=t.get("sensor_temp_c"),
                width_px=t.get("width_px"), height_px=t.get("height_px"),
                bayer_pattern=t.get("bayer_pattern"),
            )
            if reason is None:
                reason = (
                    "a master dark was used instead — a dark already includes "
                    "the bias" if kind == "bias" and has_dark
                    else f"another of your {kind} masters is a closer match")
            detail.append({"name": name, "reason": reason})
        rows.append({
            "id": mid, "name": str(m.get("name") or f"master {mid}"),
            "kind": kind,
            "n_covered": len(covered), "covered": covered, "missed": missed,
            "missed_detail": detail,
        })
    return {
        "n_targets": len(targets),
        "masters": rows,
        "uncovered": [n for n, ids in zip(names, bound_ids) if not ids],
        # The *numbers* an uncovered target would need a dark shot at — the point
        # a beginner actually stalls at ("build a dark from frames shot the same
        # way" doesn't say which way). Same source as the rest of the roll-up, so
        # it can never disagree with it; additive, so an older client ignores it.
        "uncovered_detail": [
            {"name": n, "exposure_s": t.get("exposure_s"), "gain": t.get("gain")}
            for n, t, ids in zip(names, targets, bound_ids, strict=True)
            if not ids
        ],
    }


# A flat-dark must match the *flat's* exposure closely (it removes the flat's own
# dark-current/bias pedestal). Only recommend one whose match distance clears
# this bar, so we never suggest, say, a 300 s dark for a 2 s flat.
_FLAT_DARK_MAX_DIST = 1.0


def _recommend_flat_dark(
    darks: list[dict[str, Any]], flat: dict[str, Any] | None,
) -> int | None:
    """Pick the dark master that best matches the recommended flat's exposure.

    Flat-darks calibrate the *flat* (not the lights), so they match the flat's
    exposure/gain/temperature — **and its dimensions**. A dark built for another
    camera or binning mode cannot be subtracted from this flat at all:
    ``CalibrationMasters.load`` compares the two shapes and, on a mismatch,
    silently skips the subtraction and normalises the flat with its own pedestal
    still in it. Recommending one would put exactly that silent mismatch on the
    Stack form behind a ★, so a further-but-usable dark is preferred instead —
    the same "the top pick can fail a gate" reasoning the unattended binder uses
    for the dark and the flat.

    Returns ``None`` when there is no recommended flat, the flat has no recorded
    exposure, or no dark matches it closely enough (see
    :data:`_FLAT_DARK_MAX_DIST`)."""
    if not flat or not darks:
        return None
    flat_exp = flat.get("exposure_s")
    if not flat_exp:
        return None  # can't exposure-match a flat-dark without the flat's exposure
    flat_gain = flat.get("gain")
    flat_temp = flat.get("sensor_temp_c")
    best_id: int | None = None
    best_dist = float("inf")
    for d in darks:
        try:
            did = int(d["id"])
        except (KeyError, TypeError, ValueError):
            continue
        # One-sided, like every other size gate in this module: a master or a flat
        # that never recorded its dimensions can't be disproved, so it still ranks.
        if dims_conflict(d, flat.get("width_px"), flat.get("height_px")):
            continue
        dist = _match_distance(d, exposure_s=flat_exp, gain=flat_gain,
                               sensor_temp_c=flat_temp, kind="dark")
        if dist < best_dist:
            best_dist = dist
            best_id = did
    return best_id if best_dist <= _FLAT_DARK_MAX_DIST else None


def _next_id(library_root: str | Path, entries: list[dict[str, Any]]) -> int:
    """Allocate a fresh master id that has never been used before.

    Master ids — and the ``{kind}_{id}.fits`` filenames derived from them — are
    *permanent* references: a stack run persists the server-resolved calibration
    path (``.../dark_1.fits``) in its ``options_json``, and a one-click *Reprocess
    everything* reuses those options verbatim. So reusing an id for a *different*
    master would silently rebind an old run's recorded dark/flat to different
    pixels and miscalibrate the unattended reprocess. ``max(current ids)+1`` is
    not monotonic across deletions (deleting the newest master frees its id), so
    combine it with the persisted high-water mark, which survives deleting every
    entry.
    """
    from_entries = max((int(e.get("id", 0)) for e in entries), default=0)
    return max(from_entries, _read_id_high_water(library_root)) + 1


def register_master(
    library_root: str | Path,
    *,
    name: str,
    array,
    meta,
) -> dict[str, Any]:
    """Save a built master to disk and add it to the registry. Returns the
    new registry entry. ``array``/``meta`` are the outputs of
    :func:`seestack.calibrate.build_master`."""
    from seestack.calibrate.masters import save_master

    with _REGISTRY_LOCK:
        entries = _read_registry(library_root)
        mid = _next_id(library_root, entries)
        filename = f"{meta.kind}_{mid}.fits"
        save_master(calibration_dir(library_root) / filename, array, meta)
        entry = {
            "id": mid,
            "name": name or f"{meta.kind} {mid}",
            "kind": meta.kind,
            "filename": filename,
            "n_frames": meta.n_frames,
            "method": meta.method,
            "exposure_s": meta.exposure_s,
            "gain": meta.gain,
            "sensor_temp_c": meta.sensor_temp_c,
            "bayer_pattern": meta.bayer_pattern,
            "width_px": meta.width_px,
            "height_px": meta.height_px,
            "created_utc": datetime.now(timezone.utc).isoformat(),
        }
        entries.append(entry)
        _write_registry(library_root, entries)
        # Advance the high-water mark last, so this id is never handed out again
        # even after every registry entry is later deleted. (If a crash lands
        # between the two writes, ``max(current ids)`` still covers this id, so
        # the counter is only ever an *extra* guard, never the sole source.)
        _write_id_high_water(library_root, mid)
    return entry


def delete_master(library_root: str | Path, master_id: int) -> bool:
    """Remove a master's registry entry and its FITS file. Returns True if it
    existed."""
    with _REGISTRY_LOCK:
        entries = _read_registry(library_root)
        keep = [e for e in entries if int(e.get("id", -1)) != int(master_id)]
        removed = [e for e in entries if int(e.get("id", -1)) == int(master_id)]
        if not removed:
            return False
        for e in removed:
            fp = calibration_dir(library_root) / e.get("filename", "")
            try:
                fp.unlink(missing_ok=True)
            except OSError as exc:
                log.warning("could not delete master file %s: %s", fp, exc)
        _write_registry(library_root, keep)
    return True


def find_fits_in_dir(source_dir: str | Path) -> list[Path]:
    """All FITS files directly inside ``source_dir`` (non-recursive), sorted."""
    d = Path(source_dir)
    found: set[Path] = set()
    for pat in FITS_GLOBS:
        found.update(d.glob(pat))
    return sorted(found)
