"""Incremental stacking: "add new subs to the last stack" (opt-in, per target).

A plain re-stack of a big target re-reads every sub it has ever shot: on a
target with tens of thousands of subs, adding one night costs 8–22 hours. The
expensive part of a stack — reading, calibrating, aligning and accumulating each
sub — is *additive*: the weighted mean is Σw·x / Σw, and the κ-σ reference is a
running Welford mean/variance. So when ``StackOptions.incremental`` is on, a run
saves that running state beside its outputs (one ``{base}_incremental.npz`` in
the target's ``output/`` folder), and the next run adds only the new subs to it,
then repeats the cheap post-steps (levelling, gradient, colour, save) exactly as
a full stack does.

**A full stack is always a correct answer; an incremental one is only taken
when it is provably the same stack plus new subs.** :func:`plan` checks, and any
failing check means an ordinary full stack (which then saves fresh state), with
the reason logged and recorded on the run:

* the configuration is one the state can describe — the standard κ-σ or weighted
  mean combine on a single-field canvas (no drizzle, min/max, mosaic, mono,
  lucky imaging, star-matched subs or rejection map);
* the saved state exists and parses, and was written by this state version;
* every option and calibration input that affects pixels hashes the same;
* the reference frame and the output canvas (WCS text + shape) are identical;
* every sub in the saved state is still accepted and solved, with the same
  solution and the same quality metrics (anything un-accepted, removed, re-solved
  or re-measured since → full stack);
* every new sub's centre lands on the stored canvas;
* there is at least one new sub, and no more new subs than old ones (beyond
  that a full rebuild is the better answer: it costs at most twice as much and
  re-derives every frozen yardstick from all the data);
* on the κ-σ path, the saved stack is deep enough (``kappa_min_frames``) that
  its old clip decisions could have removed a lone satellite trail.

**What is approximate, by design.** Old subs keep the κ-σ clip decisions they
had (they were clipped against the mean/σ of the subs present then; a full
re-stack would re-clip them against the larger set), and quality weights and
photometric scales of new subs are measured against the yardsticks *frozen* by
the first full stack (``WeightYardsticks``, ``photometric_reference``), so both
halves of one stack are weighted by one rule. ``tests/test_incremental_stack.py``
pins the difference against a full stack.

The engine never imports ``webapp``; nothing here writes outside ``output/``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import zipfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from seestack.io.project import FrameRow
from seestack.stack.weighting import WeightYardsticks

log = logging.getLogger(__name__)

#: Bumped whenever the saved state's layout, or what the per-sub pixel pipeline
#: puts into it, changes — a state from another version is never continued.
STATE_VERSION = 1

#: The sidecar's suffix after the run's basename. Registered in
#: ``seestack.stack.output.RUN_ARTEFACT_SUFFIXES`` (so deleting the run reclaims
#: it) and in ``SERIES_ARTEFACTS`` (so a re-stack's archive *removes* it rather
#: than keeping one stale copy per run — only the newest state is ever useful).
SIDECAR_SUFFIX = "_incremental.npz"

#: Combines whose whole state is additive and therefore continuable.
SUPPORTED_COMBINES = frozenset({"sigma-clip", "mean"})

#: Option keys that cannot change a single accumulated pixel: naming, threads,
#: previews, postures, and the post-steps every incremental run repeats from the
#: restored sums anyway. Every other ``StackOptions`` field is hashed, so a new
#: option is treated as pixel-affecting until someone says otherwise here.
_UNHASHED_KEYS = frozenset({
    "output_name", "max_workers", "quick_look_interval", "save_progress",
    "unattended", "auto_drizzle", "incremental", "tiff_mode",
    "final_gradient_removal", "final_gradient_mode", "final_gradient_box_size",
    "color_calibration", "color_calibration_mode",
})

_CALIBRATION_KEYS = ("dark_path", "flat_path", "flat_dark_path", "bias_path")

_META_NAME = "meta.json"
_ZIP_LEVEL = 1  # deflate, fastest: the integer/weight planes shrink a lot, sums barely


def sidecar_path(output_dir: Path, basename: str) -> Path:
    return Path(output_dir) / f"{basename}{SIDECAR_SUFFIX}"


def welford_spill_path(output_dir: Path, basename: str) -> Path:
    """Where a run parks its pass-1 Welford state until the sidecar is written."""
    return Path(output_dir) / f"{basename}{SIDECAR_SUFFIX}.welford.part"


# ---- what can be continued ---------------------------------------------------

def unsupported_reason(options: Any, combine: str, *, is_mosaic: bool,
                       frames: list[FrameRow]) -> str | None:
    """Why a run with these (effective) options can't carry incremental state,
    or ``None`` when it can. Asked both before trying an incremental run and
    before saving state after a full one."""
    if combine not in SUPPORTED_COMBINES:
        return {
            "drizzle": "drizzle stacks are always rebuilt in full",
            "min-max-reject": "min/max rejection is always rebuilt in full",
        }.get(combine, f"the {combine} combine is always rebuilt in full")
    if is_mosaic:
        return "mosaics are always rebuilt in full"
    if getattr(options, "mono", False):
        return "mono stacks are always rebuilt in full"
    if float(getattr(options, "lucky_fraction", 1.0)) < 1.0:
        return "lucky imaging picks its subs from the whole set, so it is rebuilt in full"
    if getattr(options, "star_match_unsolved", False):
        return "star-matched subs are always rebuilt in full"
    if getattr(options, "record_rejection_map", False):
        return "a rejection map is always rebuilt in full"
    if any(f.id is None for f in frames):
        return "some subs have no database id"
    return None


# ---- fingerprints ------------------------------------------------------------

def _file_stamp(path: str | None) -> list[Any] | None:
    if not path:
        return None
    try:
        st = os.stat(path)
    except OSError:
        return [str(path), None, None]
    return [str(path), int(st.st_size), int(st.st_mtime_ns)]


def options_hash(options: Any, combine: str) -> str:
    """A hash of every option and calibration input that affects accumulated
    pixels (``options`` are the run's *effective* options)."""
    opts = {k: v for k, v in asdict(options).items() if k not in _UNHASHED_KEYS}
    payload = {
        "state_version": STATE_VERSION,
        "combine": combine,
        "options": opts,
        "calibration": {k: _file_stamp(getattr(options, k, None))
                        for k in _CALIBRATION_KEYS},
    }
    blob = json.dumps(payload, sort_keys=True, default=repr).encode()
    return hashlib.sha256(blob).hexdigest()


def frames_digest(frames: list[FrameRow]) -> str:
    """A hash of everything about a set of subs that decided their pixels and
    weights: which file, its plate solution, its CFA phase and the QC metrics the
    weighting/photometric passes read. Order-independent."""
    h = hashlib.sha256()
    for f in sorted(frames, key=lambda r: int(r.id or -1)):
        h.update(json.dumps([
            f.id, f.source_path, f.wcs_json, f.bayer_pattern,
            f.fwhm_px, f.star_count, f.sky_adu_median, f.transparency_score,
            f.eccentricity_median,
        ], default=repr).encode())
        h.update(b"\n")
    return h.hexdigest()


# ---- the plan ----------------------------------------------------------------

@dataclass
class IncrementalPlan:
    """What :func:`plan` decided. ``eligible`` False means "run a full stack";
    ``reason`` says why in plain words (also when eligible: what it will do)."""

    eligible: bool
    reason: str
    meta: dict[str, Any] = field(default_factory=dict)
    #: Subs pass 1 (Welford) still has to see — new since the last state.
    pass1_frames: list[FrameRow] = field(default_factory=list)
    #: Subs pass 2 / the single pass still has to add to the weighted sum.
    pass2_frames: list[FrameRow] = field(default_factory=list)

    @property
    def n_added(self) -> int:
        return len(self.pass2_frames)

    @property
    def yardsticks(self) -> WeightYardsticks | None:
        y = self.meta.get("yardsticks")
        return WeightYardsticks(**y) if isinstance(y, dict) else None

    @property
    def photometric_reference(self) -> float | None:
        ref = self.meta.get("photometric_reference")
        return float(ref) if ref is not None else None


def read_meta(path: Path) -> dict[str, Any]:
    """The sidecar's metadata, without loading any canvas array. Raises on a
    missing or unreadable file."""
    with zipfile.ZipFile(path) as zf:
        meta = json.loads(zf.read(_META_NAME).decode())
    if not isinstance(meta, dict):
        raise ValueError("incremental state metadata is not an object")
    return meta


def _centre_on_canvas(frame: FrameRow, canvas_wcs: Any, shape: tuple[int, int]) -> bool:
    from seestack.io.wcs_io import wcs_from_text

    fw = wcs_from_text(frame.wcs_json) if frame.wcs_json else None
    if fw is None or not frame.width_px or not frame.height_px:
        return False
    ra, dec = fw.pixel_to_world_values((frame.width_px - 1) / 2.0,
                                       (frame.height_px - 1) / 2.0)
    x, y = canvas_wcs.world_to_pixel_values(ra, dec)
    h, w = shape
    return bool(np.isfinite(x) and np.isfinite(y)
                and -0.5 <= float(x) < w - 0.5 and -0.5 <= float(y) < h - 0.5)


def plan(path: Path, *, options: Any, combine: str, is_mosaic: bool,
         frames: list[FrameRow], ref: FrameRow, dst_wcs_text: str,
         dst_shape: tuple[int, int], min_base: int = 1) -> IncrementalPlan:
    """Decide whether this run may continue the saved state at ``path``.

    ``frames`` is the run's full, final candidate list (accepted, solved, after
    the canvas outlier cut); ``options`` its effective options. ``min_base`` is
    the fewest subs the saved stack must hold for its old clip decisions to be
    trusted (the κ-σ caller passes ``kappa_min_frames``: below it a lone trail in
    an old sub could not have been clipped, and continuing would keep it for
    good). Never raises: any problem reading the state is a reason for a full
    stack.
    """
    def full(reason: str) -> IncrementalPlan:
        return IncrementalPlan(False, reason)

    why = unsupported_reason(options, combine, is_mosaic=is_mosaic, frames=frames)
    if why is not None:
        return full(why)
    if not path.is_file():
        return full("there is no saved state from a previous stack yet")
    try:
        meta = read_meta(path)
    except Exception as exc:  # noqa: BLE001 — any unreadable state → full stack
        return full(f"the saved state could not be read ({type(exc).__name__})")
    if meta.get("version") != STATE_VERSION:
        return full("the saved state is from another version")
    if meta.get("options_hash") != options_hash(options, combine):
        return full("stacking options or calibration changed since the last stack")
    if meta.get("ref_id") != ref.id:
        return full("the reference sub changed")
    if (meta.get("canvas_wcs") != dst_wcs_text
            or tuple(meta.get("canvas_shape") or ()) != tuple(dst_shape)):
        return full("the output canvas changed")
    try:
        used = {int(i) for i in meta["used_ids"]}
        wel_ids = {int(i) for i in meta.get("welford_ids") or []}
    except (KeyError, TypeError, ValueError):
        return full("the saved state is incomplete")
    if combine == "sigma-clip" and not wel_ids:
        return full("the saved state has no κ-σ statistics")
    by_id = {f.id: f for f in frames}
    old_ids = used | wel_ids
    missing = old_ids - by_id.keys()
    if missing:
        return full(f"{len(missing)} sub(s) in the last stack are no longer accepted "
                    "or were removed")
    if meta.get("frames_digest") != frames_digest([by_id[i] for i in old_ids]):
        return full("a sub in the last stack was re-solved or re-measured")
    if getattr(options, "quality_weighted", False) and not isinstance(
            meta.get("yardsticks"), dict):
        return full("the saved state has no quality-weight yardsticks")
    if getattr(options, "photometric_normalize", False) and not meta.get(
            "photometric_reference"):
        return full("photometric normalization has no reference level yet")
    try:
        _check_arrays(path, dst_shape, welford=combine == "sigma-clip")
    except Exception as exc:  # noqa: BLE001 — any damage → full stack
        return full(f"the saved state is damaged ({exc})")
    pass2 = [f for f in frames if f.id not in used]
    pass1 = [f for f in frames if f.id not in wel_ids] if combine == "sigma-clip" else []
    if not pass2:
        return full("there are no new subs since the last stack")
    if len(used) < max(1, int(min_base)):
        return full(f"the last stack has only {len(used)} subs, too few for its "
                    "outlier rejection to be kept as it is")
    if len(pass2) > len(used):
        return full(f"{len(pass2)} new subs is more than the {len(used)} already "
                    "stacked, so a full rebuild is the better answer")
    from seestack.io.wcs_io import wcs_from_text

    canvas_wcs = wcs_from_text(dst_wcs_text)
    if canvas_wcs is None:
        return full("the output canvas could not be read")
    off = [f for f in pass2 if not _centre_on_canvas(f, canvas_wcs, dst_shape)]
    if off:
        return full(f"{len(off)} new sub(s) fall outside the last stack's canvas")
    yard = meta.get("yardsticks")
    if isinstance(yard, dict) and getattr(options, "quality_weighted", False):
        # A yardstick the first stack couldn't measure would leave that factor
        # neutral for every new sub that *can* be measured on it.
        checks = (("best_fwhm", "fwhm_px"), ("median_ecc", "eccentricity_median"),
                  ("median_stars", "star_count"), ("median_sky", "sky_adu_median"),
                  ("median_transp", "transparency_score"))
        for key, attr in checks:
            if yard.get(key) is None and any(
                    getattr(f, attr, None) is not None for f in pass2):
                return full("new subs carry a quality measure the last stack had none of")
    return IncrementalPlan(
        True, f"adding {len(pass2)} new sub(s) to the {len(used)} already stacked",
        meta=meta, pass1_frames=pass1, pass2_frames=pass2)


# ---- array I/O ---------------------------------------------------------------

def _check_arrays(path: Path, shape: tuple[int, int], *, welford: bool) -> None:
    """Every array the run will restore is present with the canvas's shape and
    the dtype the accumulators use — read from the ``.npy`` headers only, so a
    damaged or mismatched state is caught before a single sub is read."""
    h, w = int(shape[0]), int(shape[1])
    want = {
        "wsum_sum": ((h, w, 3), np.float32),
        "wsum_weight": ((h, w, 3), np.float32),
        "wsum_count": ((h, w), np.uint32),
    }
    if welford:
        want.update({
            "welford_n": ((h, w, 3), np.uint32),
            "welford_mean": ((h, w, 3), np.float32),
            "welford_m2": ((h, w, 3), np.float32),
        })
    with zipfile.ZipFile(path) as zf:
        for name, (shp, dtype) in want.items():
            with zf.open(f"{name}.npy") as fh:
                major, _minor = np.lib.format.read_magic(fh)
                read_header = (np.lib.format.read_array_header_1_0 if major == 1
                               else np.lib.format.read_array_header_2_0)
                got_shape, _, got_dtype = read_header(fh)
            if tuple(got_shape) != shp or np.dtype(got_dtype) != np.dtype(dtype):
                raise ValueError(f"{name} is {got_shape} {got_dtype}")


def _write_array(zf: zipfile.ZipFile, name: str, arr: np.ndarray) -> None:
    with zf.open(f"{name}.npy", "w", force_zip64=True) as fh:
        np.lib.format.write_array(fh, np.ascontiguousarray(arr), allow_pickle=False)


def _read_array(zf: zipfile.ZipFile, name: str) -> np.ndarray:
    with zf.open(f"{name}.npy") as fh:
        return np.lib.format.read_array(fh, allow_pickle=False)


def _new_zip(path: Path) -> zipfile.ZipFile:
    return zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED,
                           compresslevel=_ZIP_LEVEL, allowZip64=True)


def load_welford_state(path: Path) -> dict[str, np.ndarray]:
    with zipfile.ZipFile(path) as zf:
        return {k: _read_array(zf, f"welford_{k}") for k in ("n", "mean", "m2")}


def load_wsum_state(path: Path) -> dict[str, np.ndarray]:
    with zipfile.ZipFile(path) as zf:
        return {k: _read_array(zf, f"wsum_{k}") for k in ("sum", "weight", "count")}


def spill_welford(path: Path, state: dict[str, np.ndarray]) -> Path:
    """Park pass 1's Welford state on disk, so pass 2 can free it (the OOM
    guard charges pass 2 without it) and the sidecar can still carry it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with _new_zip(path) as zf:
        for k in ("n", "mean", "m2"):
            _write_array(zf, f"welford_{k}", state[k])
    return path


def write_sidecar(path: Path, meta: dict[str, Any], wsum_state: dict[str, np.ndarray],
                  welford_spill: Path | None) -> Path:
    """Write the state atomically (``.part`` + ``os.replace``). The Welford
    members are streamed out of ``welford_spill`` one at a time, so no extra
    canvas array is held while writing."""
    part = path.with_name(path.name + ".part")
    meta = dict(meta, version=STATE_VERSION,
                written_utc=datetime.now(timezone.utc).isoformat())
    try:
        with _new_zip(part) as zf:
            zf.writestr(_META_NAME, json.dumps(meta))
            for k in ("sum", "weight", "count"):
                _write_array(zf, f"wsum_{k}", wsum_state[k])
            if welford_spill is not None:
                with zipfile.ZipFile(welford_spill) as src:
                    for k in ("n", "mean", "m2"):
                        name = f"welford_{k}.npy"
                        with src.open(name) as fin, zf.open(
                                name, "w", force_zip64=True) as fout:
                            shutil.copyfileobj(fin, fout, 1 << 20)
        os.replace(part, path)
    finally:
        try:
            part.unlink()
        except FileNotFoundError:
            pass
    return path


def discard(path: Path | None) -> None:
    """Best-effort removal of a spill or stale state file."""
    if path is None:
        return
    try:
        Path(path).unlink()
    except FileNotFoundError:
        pass
    except OSError as exc:
        log.warning("could not remove %s: %s", path, exc)
