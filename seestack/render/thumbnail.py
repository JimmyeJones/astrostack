"""
Thumbnail cache.

A thumbnail is a 256x256 PNG preview of a frame, debayered and gently stretched
so the user can actually see what's in it. Without a stretch the linear data
looks black except for the brightest stars.

We keep thumbs in ``<project>/cache/thumbs/`` and key them on frame id. The
side cache is invalidated by clearing it from the GUI; nothing in the rest of
the pipeline reads from it.

Generation is a pure function so it can run in worker processes via JobRunner.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

THUMB_SIZE = 256
THUMBS_DIRNAME = "thumbs"
# Bumped whenever the thumbnail pipeline (debayer / stretch / size) changes
# enough that previously cached thumbnails should be discarded. The preview
# pane checks this before reusing a cached PNG.
THUMB_VERSION = 3


def thumbs_dir(project_dir: Path) -> Path:
    return Path(project_dir) / "cache" / THUMBS_DIRNAME


def thumb_path_for(project_dir: Path, frame_id: int) -> Path:
    return thumbs_dir(project_dir) / f"frame_{frame_id:06d}.png"


def _version_sentinel(project_dir: Path) -> Path:
    return thumbs_dir(project_dir) / ".version"


def ensure_thumb_cache_current(project_dir: Path) -> bool:
    """
    Make sure the thumbnail cache matches the current pipeline version. If
    the on-disk version doesn't match, the cache is wiped. Returns True if
    a wipe happened.

    Call this once after opening a project — old thumbs from a previous
    Seestack version (different stretch, different size) will be regenerated
    on demand instead of showing weird stale previews.
    """
    d = thumbs_dir(project_dir)
    sentinel = _version_sentinel(project_dir)
    current = str(THUMB_VERSION)
    if sentinel.exists():
        try:
            if sentinel.read_text().strip() == current:
                return False
        except OSError:
            pass
    # Mismatch (or missing). Wipe + write new sentinel.
    wiped = False
    if d.exists():
        for f in d.iterdir():
            try:
                f.unlink()
                wiped = True
            except OSError:
                pass
    d.mkdir(parents=True, exist_ok=True)
    sentinel.write_text(current)
    return wiped


def generate_thumbnail(
    fits_path: str | Path,
    out_path: str | Path,
    *,
    bayer_pattern: str | None = None,
    size: int = THUMB_SIZE,
) -> Path:
    """
    Read a FITS file, debayer, downsample, autostretch, and write as PNG.

    Designed to be called from a worker process — pure inputs/outputs, no shared
    state.
    """
    from PIL import Image

    from seestack.io.fits_loader import bilinear_debayer, load_seestar_raw

    rgb, info = load_seestar_raw(fits_path, debayer=False, out_dtype=np.float32)
    # rgb is the raw 2D mosaic at this point; debayer with the requested pattern.
    pattern = bayer_pattern or info.bayer_pattern or "RGGB"
    rgb = bilinear_debayer(rgb, pattern=pattern)

    h, w = rgb.shape[:2]
    target_w = size
    target_h = max(1, int(round(h * (size / w))))
    rgb_small = _downsample_rgb(rgb, target_h, target_w)

    stretched = autostretch(rgb_small)
    out = (np.clip(stretched, 0.0, 1.0) * 255).astype(np.uint8)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(out).save(out_path, format="PNG")
    return out_path


def autostretch(
    rgb: np.ndarray,
    *,
    target_bg: float = 0.20,
    sigma_factor: float = -2.0,
) -> np.ndarray:
    """
    PixInsight-style "Screen Transfer Function" (STF) autostretch.

    Each channel is stretched independently so that **its own** robust sky
    median lands at ``target_bg`` (default 20% grey). This is what every
    professional astro tool does, and it's the right answer because:

      - Sky goes to clean neutral grey: each R/G/B channel's median maps to
        the same target value, so the sky has no colour cast.
      - Per-channel SNR is preserved: we don't multiply weak channels by
        large factors, so red noise doesn't get amplified relative to green.
      - Star colours come through naturally because the *shape* of the
        stretch curve is the same for all channels.

    The maths: PixInsight's "midtones transfer function":

        mtf(x, m) = (m - 1) · x / ((2·m - 1)·x - m)

    where ``m`` is chosen per channel so that ``mtf(median, m) = target_bg``
    after shadow clipping at ``median + sigma_factor·σ``.
    """
    img = rgb.astype(np.float32, copy=True)

    # NaN = uncovered canvas (mosaic gaps, corners). These MUST be excluded
    # from every statistic — otherwise a mosaic's large no-data regions drag
    # the per-channel median to ~0 and the stretch goes haywire (colour cast,
    # wrong black point). We compute all stats over the finite pixels only and
    # set uncovered pixels to 0 (black) in the output.
    finite_any = np.isfinite(img).any(axis=2)
    if not finite_any.any():
        return np.zeros_like(np.nan_to_num(img))

    # Normalize the *whole image* to 0..1 first — keeps per-channel scales
    # intact relative to each other. Use nan-aware min/max over covered pixels.
    lo = float(np.nanmin(img))
    hi = float(np.nanmax(img))
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
        return np.zeros_like(np.nan_to_num(img))
    img = (img - lo) / (hi - lo)

    out = np.zeros_like(img)
    for c in range(3):
        chan = img[..., c]
        finite = np.isfinite(chan)
        if not finite.any():
            continue
        med, sigma = _robust_median_sigma(chan[finite])
        # Black point = median - 2σ (clipped at 0).
        shadows = max(0.0, med + sigma_factor * sigma)
        rng = max(1.0 - shadows, 1e-6)
        # Apply the stretch only to covered pixels; uncovered stay 0.
        x = np.clip((chan[finite] - shadows) / rng, 0.0, 1.0)
        norm_med = max((med - shadows) / rng, 1e-6)
        m = _midtones_for(norm_med, target_bg)
        out_chan = out[..., c]
        out_chan[finite] = np.clip(_mtf(x, m), 0.0, 1.0)

    return out


def _robust_median_sigma(values: np.ndarray) -> tuple[float, float]:
    """
    Median and MAD-based sigma — resistant to bright stars.

    ``values`` should already be the finite (covered) pixels; callers strip
    NaN before passing it in.
    """
    med = float(np.median(values))
    mad = float(np.median(np.abs(values - med)))
    sigma = 1.4826 * mad if mad > 0 else float(values.std() or 1e-3)
    return med, sigma


def _mtf(x: np.ndarray, m: float) -> np.ndarray:
    """PixInsight midtones transfer function. ``m`` in (0, 1)."""
    if abs(m - 0.5) < 1e-9:
        return x
    return (m - 1.0) * x / ((2.0 * m - 1.0) * x - m)


def _midtones_for(median: float, target: float) -> float:
    """
    Closed-form inverse of ``_mtf``: choose m so ``mtf(median, m) = target``.

    Derived from the MTF formula by solving for m. Both arguments must be in
    (0, 1); we clamp to avoid division by zero or runaway curves.
    """
    median = float(np.clip(median, 1e-6, 1 - 1e-6))
    target = float(np.clip(target, 1e-3, 1 - 1e-3))
    denom = median * (1.0 - 2.0 * target) + target
    if abs(denom) < 1e-12:
        return 0.5
    m = median * (1.0 - target) / denom
    return float(np.clip(m, 1e-3, 1 - 1e-3))


def _downsample_rgb(rgb: np.ndarray, target_h: int, target_w: int) -> np.ndarray:
    """
    Resize an RGB float image to (target_h, target_w) using Pillow's box filter.

    Crucially this uses ONE global normalization for all three channels so the
    color balance is preserved through the uint8 round-trip Pillow needs.
    """
    from PIL import Image

    lo = float(rgb.min())
    hi = float(rgb.max())
    if hi <= lo:
        return np.zeros((target_h, target_w, 3), dtype=np.float32)

    u8 = ((rgb - lo) / (hi - lo) * 255).astype(np.uint8)
    img = Image.fromarray(u8, mode="RGB").resize((target_w, target_h), Image.BOX)
    out = np.asarray(img, dtype=np.float32) / 255.0
    return out * (hi - lo) + lo
