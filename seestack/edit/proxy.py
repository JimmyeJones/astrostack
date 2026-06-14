"""Downsampled linear proxy for live editor preview.

Editing a 150 MP drizzled/mosaic FITS interactively would exhaust RAM, so the
live preview always runs on a cached, decimated **linear** proxy (<=1500 px,
~27 MB float32). Decimation is by striding — like ``render_stack_png`` — so NaN
(uncovered/mosaic gaps) is preserved for the NaN-aware ops. The full-res image is
read once at build time and released; the cache is an ``.npy`` re-read with
``mmap_mode`` and copied per render. Geometry ops use ``proxy_scale`` to translate
between proxy and full coordinates.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

PROXY_VERSION = 1
PROXY_MAX_PX = 1500
_PROXY_DIRNAME = "edit_proxies"


def proxy_dir(project_dir: Path) -> Path:
    return Path(project_dir) / "cache" / _PROXY_DIRNAME


def _proxy_paths(project_dir: Path, run_id: int) -> tuple[Path, Path]:
    d = proxy_dir(project_dir)
    return d / f"run_{run_id}.npy", d / f"run_{run_id}.json"


def _load_fits_rgb(fits_path: str | Path) -> np.ndarray:
    """Read a stack FITS into float32 ``(H, W, 3)`` (same logic as render_stack_png)."""
    from astropy.io import fits as _fits

    arr = np.asarray(_fits.getdata(fits_path), dtype=np.float32)
    if arr.ndim == 3:
        rgb = np.transpose(arr, (1, 2, 0))
        if rgb.shape[2] == 1:
            rgb = np.repeat(rgb, 3, axis=2)
        elif rgb.shape[2] > 3:
            rgb = rgb[..., :3]
    else:
        rgb = np.stack([arr, arr, arr], axis=-1)
    return rgb


def build_proxy(fits_path: str | Path, max_px: int = PROXY_MAX_PX) -> tuple[np.ndarray, float]:
    """Return ``(proxy_rgb, proxy_scale)`` where ``proxy_scale = full_w / proxy_w``."""
    rgb = _load_fits_rgb(fits_path)
    h, w = rgb.shape[:2]
    longest = max(h, w)
    if longest > max_px:
        step = int(np.ceil(longest / max_px))
        rgb = rgb[::step, ::step]
        scale = float(step)
    else:
        scale = 1.0
    return np.ascontiguousarray(rgb, dtype=np.float32), scale


def get_proxy(project_dir: Path, run_id: int, fits_path: str | Path) -> tuple[np.ndarray, float]:
    """Return a cached proxy (building/refreshing it as needed) as a writable copy."""
    npy_path, meta_path = _proxy_paths(project_dir, run_id)
    fits_path = Path(fits_path)
    try:
        src_mtime = fits_path.stat().st_mtime
    except OSError:
        src_mtime = 0.0

    if npy_path.exists() and meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text())
            if (meta.get("version") == PROXY_VERSION
                    and abs(float(meta.get("src_mtime", -1)) - src_mtime) < 1e-6):
                arr = np.load(npy_path, mmap_mode="r")
                return np.array(arr, dtype=np.float32), float(meta.get("proxy_scale", 1.0))
        except (OSError, ValueError):
            pass

    rgb, scale = build_proxy(fits_path)
    npy_path.parent.mkdir(parents=True, exist_ok=True)
    np.save(npy_path, rgb)
    meta_path.write_text(json.dumps(
        {"version": PROXY_VERSION, "src_mtime": src_mtime, "proxy_scale": scale,
         "shape": list(rgb.shape)}
    ))
    return rgb, scale


def clear_proxy(project_dir: Path, run_id: int) -> None:
    """Remove a run's cached proxy (call when the run is deleted)."""
    for p in _proxy_paths(project_dir, run_id):
        try:
            p.unlink(missing_ok=True)
        except OSError:
            pass
