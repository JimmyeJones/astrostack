"""
Per-coverage sky leveling.

In a mosaic stack the canvas has many distinct coverage values: corners of
the union might be covered by 1 frame, panel-centers by 6, panel-overlaps
by 12+. If anything in the upstream pipeline (per-frame bg fit residual,
reproject interpolation, slight sky-level differences between sessions)
leaves *any* coverage-dependent bias in the output, that bias shows up as
visible rectangular "panel" steps tracing the coverage map.

This pass directly cancels that. For each distinct coverage value:

  1. Mask out bright objects (stars, nebulosity) using sigma-clipped stats
     of the luminance so the median we measure is genuine sky.
  2. Compute the per-channel median of the unmasked pixels at that
     coverage value.
  3. Subtract that median from all pixels at that coverage value.

The net effect: every coverage region's sky lands at exactly zero, panel
steps vanish, and bright objects keep their relative brightness because we
masked them out of the median calculation.

Cost: one mask + one pass per (channel, coverage value). On a typical
mosaic with maybe a dozen distinct coverage values, this is well under a
second on the stacked canvas.
"""

from __future__ import annotations

import logging

import numpy as np

log = logging.getLogger(__name__)

# Below this many *strided* sky pixels a per-level median is meaningless noise,
# so we never level a level with fewer — even on a heavily-decimated proxy where
# scaling ``min_pixels_per_level`` down would otherwise reach into single digits.
_MIN_STRIDED_PIXELS = 12


def level_by_coverage(
    rgb: np.ndarray,
    coverage: np.ndarray,
    *,
    object_sigma: float = 2.0,
    min_pixels_per_level: int = 200,
    dilate_object_mask_px: int = 4,
    smooth_across_levels: bool = True,
    proxy_scale: float = 1.0,
) -> np.ndarray:
    """
    Equalise the sky background across every distinct coverage value.

    Parameters
    ----------
    rgb
        (H, W, 3) stacked image, NaN allowed in uncovered regions.
    coverage
        (H, W) or (H, W, 3) per-pixel weight from the accumulator. Pixels with
        coverage == 0 are no-data and are skipped.
    object_sigma
        Pixels above ``median + object_sigma · σ`` of the luminance are masked
        out of the per-coverage median calculation — that's stars and
        nebulosity, which should not bias the sky estimate.
    min_pixels_per_level
        A coverage value with fewer than this many *full-resolution* sky pixels
        is skipped (no reliable median).
    proxy_scale
        When called on a strided live-preview proxy (``proxy_scale > 1``), the
        image and coverage map carry ~``proxy_scale²`` fewer pixels than the
        full-resolution export, so the pixel-count floor is scaled down by the
        same factor. Without this a coverage level with, say, 800 full-res sky
        pixels has only ~50 on a ×4 proxy and would be **skipped in the preview
        but leveled in the export** — a visible mosaic panel-step mismatch
        between the live preview and the exported image. Default ``1.0`` (the
        full-res export) leaves the behaviour unchanged.
    """
    from astropy.stats import sigma_clipped_stats
    from scipy.ndimage import binary_dilation

    # Select the *same set* of coverage levels the full-res export would, by
    # gating on the full-resolution-equivalent pixel count: a strided proxy pixel
    # stands in for ``step²`` full-res pixels, so scale the floor by 1/step²
    # (never below a handful of pixels — a median over 3 pixels is noise).
    step = max(1, int(round(float(proxy_scale))))
    effective_min = max(
        _MIN_STRIDED_PIXELS, int(round(min_pixels_per_level / (step * step))))

    out = rgb.astype(np.float32, copy=True)

    if coverage.ndim == 3:
        # WeightedSumAccumulator's coverage is per-channel but identical across
        # channels for our pipeline; collapse to 2D.
        cov2d = coverage[..., 0]
    else:
        cov2d = coverage

    # Luminance + object mask. We dilate the mask so star halos and nebula
    # *edges* are also excluded — after stretching, even mildly bright pixels
    # near a source bias the per-level median enough to show up as a step.
    luma = (0.299 * out[..., 0] + 0.587 * out[..., 1]
            + 0.114 * out[..., 2]).astype(np.float32, copy=False)
    finite = np.isfinite(luma)
    if not finite.any():
        return out
    _, med, std = sigma_clipped_stats(luma, mask=~finite, sigma=3.0, maxiters=5)
    if not (np.isfinite(med) and np.isfinite(std) and std > 0):
        return out
    object_mask = luma > (med + object_sigma * float(std))
    if dilate_object_mask_px > 0:
        object_mask = binary_dilation(object_mask, iterations=dilate_object_mask_px)

    # Bin coverage values. For float weights round to nearest integer; with
    # quality weighting on, exact values might be e.g. 4.7 but the
    # **integer-rounded** bin is what carries the visible panel structure.
    cov_int = np.rint(cov2d).astype(np.int32, copy=False)
    valid_pix = (cov_int > 0) & finite
    if not valid_pix.any():
        return out

    sky_mask = valid_pix & ~object_mask

    # Most common coverage values dominate; only level the ones with enough
    # sky pixels to have a reliable sky estimate.
    levels, counts = np.unique(cov_int[sky_mask], return_counts=True)

    # First pass: compute the per-channel SKY MODE for each coverage level
    # using the SExtractor approximation (2.5·median − 1.5·sigma-clipped-mean).
    # Mode is robust to faint diffuse signal that would bias the plain median
    # upward by a coverage-dependent amount (which is exactly the residual
    # bias that re-emerges as panel steps after stretching).
    offsets: dict[int, list[float]] = {}  # level -> [R_off, G_off, B_off]
    sky_counts: dict[int, int] = {}
    for level, count in zip(levels, counts):
        if level <= 0 or count < effective_min:
            continue
        region_mask = (cov_int == level) & valid_pix
        region_sky_mask = region_mask & ~object_mask
        n_sky = int(region_sky_mask.sum())
        if n_sky < effective_min:
            continue
        ch_offsets: list[float] = []
        ok = True
        for c in range(3):
            sky_pixels = out[..., c][region_sky_mask]
            sc_mean, sc_med, _ = sigma_clipped_stats(sky_pixels, sigma=3.0, maxiters=5)
            if not (np.isfinite(sc_mean) and np.isfinite(sc_med)):
                ok = False
                break
            mode_est = 2.5 * sc_med - 1.5 * sc_mean
            # If the skew is implausibly extreme, fall back to the median —
            # the SExtractor approximation only holds for mild positive skew.
            if (not np.isfinite(mode_est)
                    or abs(mode_est - sc_med) > 5.0 * abs(sc_med - sc_mean + 1e-9)):
                mode_est = sc_med
            ch_offsets.append(float(mode_est))
        if ok:
            offsets[int(level)] = ch_offsets
            sky_counts[int(level)] = n_sky

    if not offsets:
        log.info("Coverage-leveling: no coverage levels had enough sky pixels")
        return out

    # Smooth offsets across coverage levels. Physical sky should not jump
    # between coverage = k and coverage = k+1; any per-level "step" that
    # large is noise in that level's small sky sample. We fit a robust low-
    # order trend (weighted by sky pixel count) across levels and use the
    # fitted value, which kills the residual high-frequency wobble that
    # otherwise traces the coverage map.
    if smooth_across_levels and len(offsets) >= 3:
        lvls = np.array(sorted(offsets.keys()), dtype=np.float32)
        weights = np.array([sky_counts[int(l)] for l in lvls], dtype=np.float32)
        for c in range(3):
            ys = np.array([offsets[int(l)][c] for l in lvls], dtype=np.float32)
            # Quadratic fit weighted by sky-pixel count — flexible enough for
            # the usual gentle dependence but won't chase per-level noise.
            try:
                coeffs = np.polyfit(lvls, ys, deg=2, w=weights)
                smoothed = np.polyval(coeffs, lvls)
            except (np.linalg.LinAlgError, ValueError):
                smoothed = ys
            for i, l in enumerate(lvls):
                offsets[int(l)][c] = float(smoothed[i])

    # Second pass: subtract the (smoothed) per-channel offset from every pixel
    # at each coverage level. Objects shift by the same constant, so relative
    # brightness is preserved.
    n_leveled = 0
    n_skipped = int(len(levels) - len(offsets))
    max_shift = 0.0
    for level_i, ch_offsets in offsets.items():
        region_mask = (cov_int == level_i) & valid_pix
        for c in range(3):
            off = ch_offsets[c]
            if not np.isfinite(off):
                continue
            out[..., c][region_mask] -= np.float32(off)
            if abs(off) > max_shift:
                max_shift = abs(off)
        n_leveled += 1

    log.info(
        "Coverage-leveling: equalised %d coverage levels, %d skipped "
        "(too few sky pixels); max shift applied = %.3f ADU",
        n_leveled, n_skipped, max_shift,
    )
    return out
