"""Library-level master calibration store.

Master darks/flats are shared across targets (one master dark for a given
exposure/gain/temperature calibrates every light shot that way), so they live
at the library root rather than inside a single target:

    <library_root>/calibration/
        masters.json          ← registry (list of master metadata)
        dark_1.fits
        flat_2.fits
        ...

The registry is a small JSON file written atomically. The single job worker is
the only writer; routers only read, so no locking is needed beyond the atomic
replace.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

CALIBRATION_SUBDIR = "calibration"
REGISTRY_NAME = "masters.json"

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
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(entries, indent=2))
    os.replace(tmp, path)


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


def resolve_master_paths(
    library_root: str | Path,
    dark_master_id: Any = None,
    flat_master_id: Any = None,
    flat_dark_master_id: Any = None,
) -> tuple[str | None, str | None, str | None]:
    """Map dark/flat/flat-dark master ids → on-disk FITS paths. Raises
    ``KeyError`` with a human message if an id is given but no such master
    exists.

    ``flat_dark_master_id`` is a dark/bias matched to the flat's exposure,
    subtracted from the flat before normalising (see
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
    )


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
    """Pick the best-matching dark and flat for a target's acquisition params.

    Returns the recommended master ids (or None if none of a kind exist) plus a
    per-master match score in 0..1 (higher = better) so the UI can badge the
    best option. Only masters whose file still exists are considered.
    """
    scores: dict[int, float] = {}
    best: dict[str, tuple[int, float]] = {}
    darks: list[dict[str, Any]] = []
    flats_by_id: dict[int, dict[str, Any]] = {}
    for m in masters:
        if not m.get("exists", True):
            continue
        kind = str(m.get("kind", ""))
        if kind not in ("dark", "flat"):
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
        "scores": scores,
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
    exposure/gain/temperature. Returns ``None`` when there is no recommended
    flat, the flat has no recorded exposure, or no dark matches it closely
    enough (see :data:`_FLAT_DARK_MAX_DIST`)."""
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
        dist = _match_distance(d, exposure_s=flat_exp, gain=flat_gain,
                               sensor_temp_c=flat_temp, kind="dark")
        if dist < best_dist:
            best_dist = dist
            best_id = did
    return best_id if best_dist <= _FLAT_DARK_MAX_DIST else None


def _next_id(entries: list[dict[str, Any]]) -> int:
    return (max((int(e.get("id", 0)) for e in entries), default=0)) + 1


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

    entries = _read_registry(library_root)
    mid = _next_id(entries)
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
    return entry


def delete_master(library_root: str | Path, master_id: int) -> bool:
    """Remove a master's registry entry and its FITS file. Returns True if it
    existed."""
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
