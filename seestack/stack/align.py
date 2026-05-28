"""
Per-frame alignment for the stacker.

Pipeline per frame:

  load → debayer → (optional) per-frame background flatten → reproject

Returns a 3-channel float32 array shaped to the output canvas plus a boolean
validity mask (pixels outside the source frame are False).

GPU acceleration
----------------
The reproject step (the dominant per-frame cost) routes through the ``xp``
shim. When CuPy is available **and** the input arrays are large enough to
amortise host↔device transfer, we run ``cupyx.scipy.ndimage.map_coordinates``
on the GPU. With small frames the transfer overhead wins, so we fall back to
NumPy automatically.

Why custom reproject instead of ``reproject.reproject_interp``? We need to
apply the *same* coordinate transform to all three colour channels.
``reproject_interp`` recomputes the pixel→pixel mapping on every call, so
running it three times triples the cost. Computing the mapping once with
astropy and applying ``map_coordinates`` per channel cuts that to roughly the
cost of a single reproject — a ~3× speedup that compounds on top of the GPU
speedup.
"""

from __future__ import annotations

import logging

import numpy as np

from seestack.bg.hot_pixels import suppress_hot_cold_pixels
from seestack.bg.per_frame import BackgroundOptions, subtract_background
from seestack.core.xp import GPU_AVAILABLE, to_cpu, to_device

log = logging.getLogger(__name__)

# Below this many pixels the GPU path is slower because of host↔device
# transfer overhead. ~1.5M pixels is roughly half of a Seestar frame so
# anything full-size goes to GPU; small synthetic test frames stay on CPU.
GPU_PIXEL_THRESHOLD = 1_500_000

# Central patch for sub-pixel refinement — taken from the reference frame,
# shared across all worker threads. A 512² window in the middle of the canvas
# has plenty of stars to lock onto and is small enough that phase correlation
# is fast.
REF_PATCH_SIZE = 512

# Each source frame's outermost N pixels are ignored when building the
# valid-mask, so they never contribute to the stack. They suffer from:
#   - Bilinear debayer artefacts (insufficient same-channel neighbours at the
#     border of the Bayer mosaic).
#   - Reproject interpolation against the constant zero just outside the
#     frame, biasing the edge inward.
# Kept small (3 px = enough to skip the debayer-bias ring) because a larger
# inset turns every frame's footprint into a sharp on/off contribution
# boundary, and on a mosaic with non-flattened frames those boundaries
# become visible as a forest of rectangle outlines. The proper cure for the
# brightness step at frame boundaries is per-frame bg flatten (zero-sky pass)
# — this inset only handles the genuinely-bad outermost ring.
FRAME_EDGE_INSET_PX = 3


def align_one(
    fits_path: str,
    bayer_pattern: str | None,
    src_wcs_text: str,
    dst_wcs_text: str,
    dst_shape: tuple[int, int],
    *,
    background_options: BackgroundOptions | None = None,
    use_gpu: bool | None = None,
    suppress_hot_pixels: bool = True,
    hot_pixel_sigma: float = 5.0,
    ref_patch: np.ndarray | None = None,
    ref_patch_origin: tuple[int, int] | None = None,
    subpixel_refine: bool = False,
) -> tuple[np.ndarray, np.ndarray, int, int] | None:
    """
    Load → debayer → bg-flatten → reproject one frame, **windowed**.

    Rather than reprojecting onto the whole output canvas, we first work out
    where the source frame's footprint lands on the canvas and only reproject
    that sub-rectangle. For a mosaic — where the canvas is the union of many
    panels — this is the difference between every frame scanning the full
    multi-panel canvas (slow) and each frame touching only its own panel.
    For a single-target stack the window ≈ the whole canvas, so there's no
    cost.

    Parameters
    ----------
    background_options
        If provided and ``enabled=True``, fits and subtracts a 2D sky
        background per channel before reprojection.
    use_gpu
        Force-enable or force-disable GPU. ``None`` (default) auto-decides.

    Returns
    -------
    (window_rgb, window_valid, y0, x0) or None.
        ``window_rgb`` is (wh, ww, 3) float32 — the reprojected frame, NaN
        outside its footprint. ``window_valid`` is (wh, ww) bool. ``(y0, x0)``
        is the window's top-left corner in the output canvas.
        Returns ``None`` if the frame's footprint doesn't intersect the
        canvas at all (e.g. a stray frame from a different target).
    """
    from seestack.io.fits_loader import bilinear_debayer, load_seestar_raw
    from seestack.io.wcs_io import wcs_from_text

    raw, info = load_seestar_raw(fits_path, debayer=False, out_dtype=np.float32)
    pattern = bayer_pattern or info.bayer_pattern or "RGGB"
    rgb = bilinear_debayer(raw, pattern=pattern)

    if suppress_hot_pixels:
        rgb = suppress_hot_cold_pixels(rgb, sigma=hot_pixel_sigma, use_gpu=use_gpu)

    if background_options is not None and background_options.enabled:
        rgb = subtract_background(rgb, background_options, use_gpu=use_gpu)

    src_wcs = wcs_from_text(src_wcs_text)
    dst_wcs = wcs_from_text(dst_wcs_text)
    if src_wcs is None or dst_wcs is None:
        raise ValueError(f"missing WCS for {fits_path}")

    result = reproject_rgb_windowed(rgb, src_wcs, dst_wcs, dst_shape, use_gpu=use_gpu)
    if result is None:
        return None
    win_rgb, win_valid, y0, x0 = result

    if subpixel_refine and ref_patch is not None and ref_patch_origin is not None:
        win_rgb = _apply_subpixel_shift_windowed(
            win_rgb, y0, x0, ref_patch, ref_patch_origin,
        )
        # Valid mask is unchanged — the shift is <1 pixel so coverage doesn't move.

    return win_rgb, win_valid, y0, x0


def _footprint_bbox_on_canvas(
    src_wcs, dst_wcs, h_src: int, w_src: int, dst_shape: tuple[int, int],
    *, pad: int = 2, inset: int = 0,
) -> tuple[int, int, int, int] | None:
    """
    Where does the source frame land on the destination canvas?

    Projects the source frame's 4 corners through ``src→dst`` and returns the
    clipped, padded bounding box ``(y0, y1, x0, x1)`` in canvas pixels — or
    ``None`` if the frame doesn't intersect the canvas.

    ``inset`` shrinks the source corners inward by that many pixels before
    projection, so the bbox covers only the trusted interior of the frame
    (matching the valid-mask inset applied later).
    """
    from astropy.wcs.utils import pixel_to_pixel

    h_dst, w_dst = dst_shape
    # Use the inset-shrunken corners so the bbox doesn't waste work on the
    # border strip we'll mask out anyway.
    lo_x = float(inset)
    hi_x = float(w_src - 1 - inset)
    lo_y = float(inset)
    hi_y = float(h_src - 1 - inset)
    if hi_x <= lo_x or hi_y <= lo_y:
        # Inset larger than the frame — caller should fall back to no inset.
        return None
    corners_x = np.array([lo_x, hi_x, hi_x, lo_x], dtype=np.float64)
    corners_y = np.array([lo_y, lo_y, hi_y, hi_y], dtype=np.float64)
    dst_x, dst_y = pixel_to_pixel(src_wcs, dst_wcs, corners_x, corners_y)
    finite = np.isfinite(dst_x) & np.isfinite(dst_y)
    if not finite.any():
        return None
    dst_x = dst_x[finite]
    dst_y = dst_y[finite]

    x0 = max(0, int(np.floor(dst_x.min())) - pad)
    x1 = min(w_dst, int(np.ceil(dst_x.max())) + pad + 1)
    y0 = max(0, int(np.floor(dst_y.min())) - pad)
    y1 = min(h_dst, int(np.ceil(dst_y.max())) + pad + 1)
    if x1 <= x0 or y1 <= y0:
        return None
    return y0, y1, x0, x1


def reproject_rgb_windowed(
    src_rgb: np.ndarray,
    src_wcs,
    dst_wcs,
    dst_shape: tuple[int, int],
    *,
    order: int = 1,
    use_gpu: bool | None = None,
) -> tuple[np.ndarray, np.ndarray, int, int] | None:
    """
    Reproject only the canvas sub-rectangle the source frame actually covers.

    Returns ``(window_rgb, window_valid, y0, x0)`` or ``None`` if the frame
    doesn't intersect the canvas. The window arrays are sized to the
    footprint bounding box, not the full canvas.
    """
    from astropy.wcs.utils import pixel_to_pixel

    h_src, w_src = src_rgb.shape[:2]
    # Inset the trusted region so debayer/reproject edge artefacts at the
    # outer border of the source frame can't contribute to the stack.
    inset = FRAME_EDGE_INSET_PX if min(h_src, w_src) > 4 * FRAME_EDGE_INSET_PX else 0
    bbox = _footprint_bbox_on_canvas(
        src_wcs, dst_wcs, h_src, w_src, dst_shape, inset=inset,
    )
    if bbox is None:
        return None
    y0, y1, x0, x1 = bbox
    win_h = y1 - y0
    win_w = x1 - x0

    # Build the destination-pixel grid for *just the window*, offset to canvas
    # coordinates, then map window pixels back to source pixels.
    yy, xx = np.indices((win_h, win_w), dtype=np.float32)
    yy += y0
    xx += x0
    src_x, src_y = pixel_to_pixel(dst_wcs, src_wcs, xx, yy)
    src_x = np.asarray(src_x, dtype=np.float32)
    src_y = np.asarray(src_y, dtype=np.float32)

    valid = np.isfinite(src_x) & np.isfinite(src_y)
    # Inset the valid region to the trusted interior of the source frame.
    valid &= (src_x >= inset) & (src_x <= w_src - 1 - inset)
    valid &= (src_y >= inset) & (src_y <= h_src - 1 - inset)

    if use_gpu is None:
        use_gpu = GPU_AVAILABLE and (win_h * win_w >= GPU_PIXEL_THRESHOLD)

    if use_gpu:
        aligned = _reproject_rgb_gpu(src_rgb, src_y, src_x, order)
    else:
        aligned = _reproject_rgb_cpu(src_rgb, src_y, src_x, order)

    aligned[~valid] = np.nan
    return aligned, valid, y0, x0


def reproject_rgb(
    src_rgb: np.ndarray,
    src_wcs,
    dst_wcs,
    dst_shape: tuple[int, int],
    *,
    order: int = 1,
    use_gpu: bool | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Reproject a 3-channel float image from ``src_wcs`` to ``dst_wcs`` at
    ``dst_shape`` (H, W).

    ``order=1`` is bilinear interpolation. Higher orders are sharper but slow
    and rarely worth it once you stack many frames.

    Returns ``(aligned_rgb, valid_mask)`` where pixels outside the source frame
    are NaN in ``aligned_rgb`` and False in ``valid_mask``.
    """
    from astropy.wcs.utils import pixel_to_pixel

    h_dst, w_dst = dst_shape
    yy, xx = np.indices((h_dst, w_dst), dtype=np.float32)

    # Destination pixels → source pixels in one shot. WCS math always runs on
    # CPU (astropy is numpy-only). The result is small so the transfer cost is
    # negligible if we're going to the GPU.
    src_x, src_y = pixel_to_pixel(dst_wcs, src_wcs, xx, yy)
    src_x = np.asarray(src_x, dtype=np.float32)
    src_y = np.asarray(src_y, dtype=np.float32)

    h_src, w_src = src_rgb.shape[:2]
    valid = np.isfinite(src_x) & np.isfinite(src_y)
    valid &= (src_x >= 0) & (src_x <= w_src - 1)
    valid &= (src_y >= 0) & (src_y <= h_src - 1)

    # Decide CPU vs GPU.
    if use_gpu is None:
        use_gpu = GPU_AVAILABLE and (h_dst * w_dst >= GPU_PIXEL_THRESHOLD)

    if use_gpu:
        aligned = _reproject_rgb_gpu(src_rgb, src_y, src_x, order)
    else:
        aligned = _reproject_rgb_cpu(src_rgb, src_y, src_x, order)

    aligned[~valid] = np.nan
    return aligned, valid


def extract_reference_patch(
    rgb: np.ndarray, size: int = REF_PATCH_SIZE,
) -> tuple[np.ndarray, tuple[int, int]]:
    """
    Pull a central luminance patch from an aligned RGB array.

    Returned shape is (h, w) where (h, w) = (min(size, H), min(size, W)).
    Origin is the (y0, x0) top-left corner in the parent canvas, so the
    caller can crop the same region from other frames for cross-correlation.
    """
    h, w = rgb.shape[:2]
    ph = min(size, h)
    pw = min(size, w)
    y0 = (h - ph) // 2
    x0 = (w - pw) // 2
    luma = 0.299 * rgb[y0:y0 + ph, x0:x0 + pw, 0] \
        + 0.587 * rgb[y0:y0 + ph, x0:x0 + pw, 1] \
        + 0.114 * rgb[y0:y0 + ph, x0:x0 + pw, 2]
    # Replace NaN with the median so phase correlation isn't biased.
    luma = np.where(np.isfinite(luma), luma, np.nanmedian(luma))
    return luma.astype(np.float32, copy=False), (y0, x0)


def _apply_subpixel_shift(
    aligned: np.ndarray,
    ref_patch: np.ndarray,
    ref_origin: tuple[int, int],
) -> np.ndarray:
    """
    Cross-correlate the aligned frame's central patch with the reference
    patch and apply the resulting sub-pixel shift to all three channels.

    No-op if the measured shift is implausibly large (suggesting bad
    plate-solve rather than seeing jitter) or if scikit-image isn't
    available.
    """
    try:
        from skimage.registration import phase_cross_correlation
    except ImportError:
        return aligned

    from scipy.ndimage import shift as nd_shift

    y0, x0 = ref_origin
    ph, pw = ref_patch.shape
    frame_patch = (
        0.299 * aligned[y0:y0 + ph, x0:x0 + pw, 0]
        + 0.587 * aligned[y0:y0 + ph, x0:x0 + pw, 1]
        + 0.114 * aligned[y0:y0 + ph, x0:x0 + pw, 2]
    )
    finite = np.isfinite(frame_patch)
    if not finite.any():
        return aligned
    frame_patch = np.where(finite, frame_patch, np.nanmedian(frame_patch))

    try:
        # 10x upsampling = 0.1 pixel resolution, plenty for stacking.
        shift, _, _ = phase_cross_correlation(
            ref_patch, frame_patch.astype(np.float32, copy=False),
            upsample_factor=10,
        )
    except Exception as exc:  # noqa: BLE001 — bad correlation, leave frame alone
        log.debug("phase_cross_correlation failed: %s", exc)
        return aligned

    dy, dx = float(shift[0]), float(shift[1])
    # Sanity check: > 5 pixels of "sub-pixel" shift means alignment was already
    # off — apply nothing and let sigma-clipping pick up the slack.
    if abs(dy) > 5.0 or abs(dx) > 5.0:
        return aligned

    out = np.empty_like(aligned)
    for c in range(3):
        ch = aligned[..., c]
        # Apply the shift; NaN regions stay NaN because nd_shift propagates them.
        ch_clean = np.where(np.isfinite(ch), ch, 0.0)
        out[..., c] = nd_shift(ch_clean, shift=(dy, dx), order=1,
                               mode="constant", cval=0.0)
        # Restore NaN in pixels that were originally NaN.
        nan_mask = ~np.isfinite(ch)
        if nan_mask.any():
            nan_shifted = nd_shift(nan_mask.astype(np.float32), shift=(dy, dx),
                                   order=0, mode="constant", cval=1.0) > 0.5
            out[..., c] = np.where(nan_shifted, np.nan, out[..., c])
    return out


def _apply_subpixel_shift_windowed(
    win_rgb: np.ndarray,
    win_y0: int,
    win_x0: int,
    ref_patch: np.ndarray,
    ref_origin: tuple[int, int],
) -> np.ndarray:
    """
    Sub-pixel refine a *windowed* aligned frame.

    The reference patch lives in canvas coordinates at ``ref_origin``. We
    intersect it with this frame's window, phase-correlate the overlapping
    region, and apply the resulting shift to the whole window. If the overlap
    is too small to give a reliable correlation (e.g. a mosaic panel that
    doesn't touch the reference panel), refinement is skipped for that frame.
    """
    try:
        from skimage.registration import phase_cross_correlation
    except ImportError:
        return win_rgb
    from scipy.ndimage import shift as nd_shift

    rpy0, rpx0 = ref_origin
    rph, rpw = ref_patch.shape
    wh, ww = win_rgb.shape[:2]

    # Overlap rectangle in canvas coords.
    oy0 = max(win_y0, rpy0)
    oy1 = min(win_y0 + wh, rpy0 + rph)
    ox0 = max(win_x0, rpx0)
    ox1 = min(win_x0 + ww, rpx0 + rpw)
    if (oy1 - oy0) < 64 or (ox1 - ox0) < 64:
        # Not enough common area to correlate reliably.
        return win_rgb

    # Crop both to the overlap.
    win_sl = (slice(oy0 - win_y0, oy1 - win_y0), slice(ox0 - win_x0, ox1 - win_x0))
    ref_sl = (slice(oy0 - rpy0, oy1 - rpy0), slice(ox0 - rpx0, ox1 - rpx0))
    frame_patch = (
        0.299 * win_rgb[win_sl][..., 0]
        + 0.587 * win_rgb[win_sl][..., 1]
        + 0.114 * win_rgb[win_sl][..., 2]
    )
    finite = np.isfinite(frame_patch)
    if not finite.any():
        return win_rgb
    frame_patch = np.where(finite, frame_patch, np.nanmedian(frame_patch))
    ref_crop = ref_patch[ref_sl]

    try:
        shift, _, _ = phase_cross_correlation(
            ref_crop, frame_patch.astype(np.float32, copy=False),
            upsample_factor=10,
        )
    except Exception as exc:  # noqa: BLE001
        log.debug("windowed phase_cross_correlation failed: %s", exc)
        return win_rgb

    dy, dx = float(shift[0]), float(shift[1])
    if abs(dy) > 5.0 or abs(dx) > 5.0:
        return win_rgb

    out = np.empty_like(win_rgb)
    for c in range(3):
        ch = win_rgb[..., c]
        ch_clean = np.where(np.isfinite(ch), ch, 0.0)
        out[..., c] = nd_shift(ch_clean, shift=(dy, dx), order=1,
                               mode="constant", cval=0.0)
        nan_mask = ~np.isfinite(ch)
        if nan_mask.any():
            nan_shifted = nd_shift(nan_mask.astype(np.float32), shift=(dy, dx),
                                   order=0, mode="constant", cval=1.0) > 0.5
            out[..., c] = np.where(nan_shifted, np.nan, out[..., c])
    return out


def _reproject_rgb_cpu(src_rgb: np.ndarray, src_y: np.ndarray, src_x: np.ndarray,
                       order: int) -> np.ndarray:
    from scipy.ndimage import map_coordinates

    coords = np.stack([src_y, src_x], axis=0)
    h_dst, w_dst = src_y.shape
    aligned = np.empty((h_dst, w_dst, 3), dtype=np.float32)
    for c in range(3):
        aligned[..., c] = map_coordinates(
            src_rgb[..., c], coords, order=order, mode="constant", cval=np.nan,
            prefilter=(order > 1),
        )
    return aligned


def _reproject_rgb_gpu(src_rgb: np.ndarray, src_y: np.ndarray, src_x: np.ndarray,
                       order: int) -> np.ndarray:
    """GPU map_coordinates path. Falls back to CPU if cupy import fails at runtime."""
    try:
        import cupy as cp  # type: ignore[import-not-found]
        from cupyx.scipy.ndimage import map_coordinates as gpu_map_coordinates  # type: ignore[import-not-found]
    except ImportError:
        log.debug("cupy.scipy.ndimage unavailable; falling back to CPU reproject")
        return _reproject_rgb_cpu(src_rgb, src_y, src_x, order)

    src_gpu = to_device(src_rgb)
    coords_gpu = to_device(np.stack([src_y, src_x], axis=0))
    h_dst, w_dst = src_y.shape
    aligned_gpu = cp.empty((h_dst, w_dst, 3), dtype=np.float32)
    # CuPy's map_coordinates kernel can't compile with cval=NaN. Use 0 here;
    # the caller already overwrites out-of-bounds pixels with NaN via the
    # explicit ``valid`` mask, so the cval doesn't actually matter.
    for c in range(3):
        aligned_gpu[..., c] = gpu_map_coordinates(
            src_gpu[..., c], coords_gpu, order=order, mode="constant", cval=0.0,
            prefilter=(order > 1),
        )
    return to_cpu(aligned_gpu)
