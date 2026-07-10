"""
Build and persist master calibration frames.

A *master* is the per-pixel combination of many same-kind raw frames (darks,
flats or bias). Combining many frames beats out the read noise so the master
is a clean estimate of the fixed pattern we want to remove.

Combination methods
-------------------
``median``       — per-pixel median. Robust default: rejects cosmic-ray hits,
                   satellite trails and the odd warm pixel without tuning.
``sigma_mean``   — one round of sigma-clipping (reject pixels more than
                   ``sigma`` MADs from the per-pixel median) then mean of what
                   survives. Slightly lower noise than the median when the
                   inputs are clean.
``mean``         — plain average. Lowest noise, but no outlier rejection.

Memory
------
Combining needs the frames stacked in RAM (median/clip aren't single-pass), so
we cap the number actually loaded (``max_frames``, evenly sampled) to bound
peak memory. For Seestar-sized mosaics (~8 MB/frame as float32) 64 frames is
~0.5 GB — fine for a one-off calibration job.
"""

from __future__ import annotations

import logging
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
    bayer_pattern: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _sigma_clip_mean(stack: np.ndarray, sigma: float) -> np.ndarray:
    """One round of per-pixel sigma-clip about the median, then mean.

    ``stack`` is (N, H, W). Uses the MAD (scaled to σ) as a robust scale so a
    couple of outlier frames don't inflate the rejection threshold.
    """
    med = np.median(stack, axis=0)
    mad = np.median(np.abs(stack - med), axis=0) * 1.4826  # MAD → σ estimate
    # mad==0 means a *majority* of frames sit exactly at the median — NOT that
    # there are no outliers. A minority cosmic-ray/hot-pixel spike routinely
    # coexists with mad==0 (common on quantised bias/dark frames), so substituting
    # +inf here would keep the spike and bake it into the master. Use tol=0 instead:
    # only the exact-median samples survive, so the result degrades to the (robust)
    # median at those pixels and the spike is correctly rejected.
    tol = sigma * np.where(mad > 0, mad, 0.0)
    keep = np.abs(stack - med) <= tol
    # Mean over kept samples; fall back to the median where nothing survived.
    kept = np.where(keep, stack, np.nan)
    with np.errstate(invalid="ignore"):
        out = np.nanmean(kept, axis=0)
    return np.where(np.isfinite(out), out, med).astype(np.float32, copy=False)


def build_master(
    paths: Sequence[str | Path],
    *,
    kind: str,
    method: str = "median",
    sigma: float = 3.0,
    max_frames: int = 64,
    progress: ProgressFn | None = None,
) -> tuple[np.ndarray, MasterMeta]:
    """Combine raw FITS frames into a master.

    Parameters
    ----------
    paths
        Raw single-extension FITS files (all the same kind, shape and bayer
        pattern). Files whose shape doesn't match the first one are skipped.
    kind
        'dark', 'flat' or 'bias' — recorded in the metadata.
    method
        'median' (default), 'sigma_mean' or 'mean'.
    sigma
        Clip threshold for ``sigma_mean``.
    max_frames
        Cap on frames actually loaded (evenly sampled across the input) to
        bound peak memory.

    Returns
    -------
    (master_2d_float32, MasterMeta)
    """
    from seestack.io.fits_loader import load_seestar_raw

    if kind not in VALID_KINDS:
        raise ValueError(f"unknown calibration kind {kind!r} (expected one of {VALID_KINDS})")
    if method not in VALID_METHODS:
        raise ValueError(f"unknown method {method!r} (expected one of {VALID_METHODS})")
    paths = [Path(p) for p in paths]
    if not paths:
        raise ValueError("no calibration frames supplied")

    # Evenly sample down to max_frames so very large dark/flat sets don't OOM.
    if len(paths) > max_frames:
        idx = np.linspace(0, len(paths) - 1, max_frames).round().astype(int)
        sampled = [paths[i] for i in sorted(set(idx.tolist()))]
        log.info("Master %s: sampling %d of %d frames", kind, len(sampled), len(paths))
        paths = sampled

    progress = progress or (lambda *a: None)
    total = len(paths)

    arrays: list[np.ndarray] = []
    ref_shape: tuple[int, int] | None = None
    exposures: list[float] = []
    gains: list[float] = []
    temps: list[float] = []
    patterns: list[str] = []
    for i, p in enumerate(paths, start=1):
        progress("Loading", i, total)
        try:
            raw, info = load_seestar_raw(p, debayer=False, out_dtype=np.float32)
        except Exception as exc:  # noqa: BLE001 — one bad file shouldn't sink the build
            log.warning("master %s: skipping %s (%s)", kind, p.name, exc)
            continue
        if raw.ndim != 2:
            log.warning("master %s: skipping %s (not a 2D Bayer frame)", kind, p.name)
            continue
        if ref_shape is None:
            ref_shape = raw.shape
        elif raw.shape != ref_shape:
            log.warning("master %s: skipping %s (shape %s != %s)",
                        kind, p.name, raw.shape, ref_shape)
            continue
        arrays.append(raw)
        if info.exposure_s is not None:
            exposures.append(info.exposure_s)
        if info.gain is not None:
            gains.append(info.gain)
        if info.sensor_temp_c is not None:
            temps.append(info.sensor_temp_c)
        if info.bayer_pattern:
            patterns.append(info.bayer_pattern.upper())

    if not arrays:
        raise ValueError("no usable calibration frames (all failed to load or mismatched)")

    progress("Combining", 0, 1)
    stack = np.stack(arrays, axis=0)  # (N, H, W)
    if method == "median":
        master = np.median(stack, axis=0).astype(np.float32, copy=False)
    elif method == "mean":
        master = np.mean(stack, axis=0).astype(np.float32, copy=False)
    else:  # sigma_mean
        master = _sigma_clip_mean(stack, sigma)
    progress("Combining", 1, 1)

    h, w = ref_shape
    meta = MasterMeta(
        kind=kind,
        n_frames=len(arrays),
        width_px=int(w),
        height_px=int(h),
        method=method,
        exposure_s=float(np.median(exposures)) if exposures else None,
        gain=float(np.median(gains)) if gains else None,
        sensor_temp_c=float(np.median(temps)) if temps else None,
        bayer_pattern=_mode(patterns),
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
        bayer_pattern=str(h["BAYERPAT"]).strip() if "BAYERPAT" in h else None,
    )
    return data, meta
