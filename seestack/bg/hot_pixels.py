"""
Hot / cold pixel suppression.

Identifies pixels whose value is more than ``sigma`` MAD-σ away from the
median of their 3×3 neighbourhood, and replaces them with that local median.
This catches:

  - **Hot pixels** that are bright in every frame (CCD defects). Sigma-clip
    can let these through because they're not random outliers — they're
    consistent across frames, so they're inliers of the per-pixel
    distribution but anomalous in their local neighbourhood.
  - **Cold / dead pixels** that are stuck at zero or near-zero.
  - **Cosmic ray hits / single-frame transients** that survive sigma-clip
    because the σ in that pixel is small enough that even big spikes only
    look like 2-3 σ.

Cheap: ~10 ms per channel for a Seestar frame on CPU. Always-on by default.

**Star-safety (why this isn't a naive median filter).** A pure "far from the
local median" test cannot tell a sharp, *undersampled* star core from a hot
pixel: on Seestar's 1.5–2.5 px-FWHM optics a real star peak also towers
thousands of ADU over its 3×3 median, so a naive pass flattens star cores and
both dims and colour-shifts every star in the stack. Worse, after a bilinear
debayer an undersampled star aliases into a single-channel checkerboard whose
3×3 median collapses to ~sky — so even an "isolated vs its neighbourhood" test
clips it. Two facts separate a genuine defect from a real star:

  1. **A single CFA defect lands in one colour channel only.** A hot/cold pixel
     is one sensor site, so after debayer it lifts (or drops) essentially one of
     R/G/B while the other two stay at sky. A real star illuminates a contiguous
     patch covering R, G *and* B sites, so all three channels are co-elevated
     there. → repair a bright outlier when the *other* two channels are still
     ~sky (``CROSS_CHANNEL_RATIO``).
  2. **A real star is extended in at least one channel.** The debayer-aliasing
     that fools the single-channel isolation test only kills *one* channel's
     neighbourhood; a star's other channels still show a raised 3×3 median.
     A genuine isolated defect (a mono/achromatic single-pixel spike, or a
     cosmic ray) is isolated in *every* channel at once. → also repair a bright
     outlier when **all three** channels have a near-sky neighbourhood there
     (``ISOLATION_RATIO``) — this handles the mono path (no debayer) and any
     achromatic single-pixel transient.

Cold / dead pixels (dark outliers) are always repaired — a stuck-low pixel is a
defect regardless of colour, and there is no "dark star" to protect.
"""

from __future__ import annotations

import logging

import numpy as np

log = logging.getLogger(__name__)

DEFAULT_SIGMA = 5.0

# A bright outlier is treated as a genuine defect when its 3×3 neighbourhood
# rises less than this fraction of the pixel's own excess above sky *in every
# channel* (fully isolated). A hot pixel / CR has a near-sky neighbourhood
# (ratio ≈ 0); even a tight 1.5 px-FWHM star spreads a large fraction of its
# peak into the 3×3 median of at least one channel (ratio ≳ 0.3), so 0.05
# cleanly separates the two with a wide margin.
ISOLATION_RATIO = 0.05
# ...or when the *other* two colour channels stay near their own sky (a single
# CFA-site defect only lifts one channel). A star is co-elevated in all three,
# so its brightest "other" channel is a large fraction of this channel's excess.
CROSS_CHANNEL_RATIO = 0.15


def suppress_hot_cold_pixels(
    rgb: np.ndarray,
    sigma: float = DEFAULT_SIGMA,
    *,
    use_gpu: bool | None = None,
) -> np.ndarray:
    """
    Star-safe local-median-filter outlier suppression.

    Replaces pixels >``sigma`` × MAD-σ away from their 3×3 neighbourhood median
    with that neighbourhood median — but only where the outlier looks like a
    genuine hot/cold/CR defect rather than an (undersampled) star core; see the
    module docstring. Returns a new array.
    """
    from seestack.core.xp import GPU_AVAILABLE

    if use_gpu is None:
        h, w = rgb.shape[:2]
        use_gpu = GPU_AVAILABLE and (h * w >= 500_000)

    if use_gpu:
        try:
            return _suppress_gpu(rgb, sigma)
        except Exception as exc:  # noqa: BLE001
            log.debug("GPU hot-pixel suppression failed (%s); CPU fallback", exc)

    return _suppress_cpu(rgb, sigma)


def _suppress(rgb, sigma, xp, median_filter):
    """Array-module-agnostic core shared by the CPU (numpy) and GPU (cupy)
    paths — see the module docstring for the algorithm."""
    out = rgb.astype(xp.float32, copy=True)
    # Pass 1: per-channel 3×3 median, noise floor, sky level and "is this
    # channel's neighbourhood near sky here?" — precomputed for all channels so
    # the cross-channel / all-channel tests in pass 2 can see every channel.
    med3, sky, sigma_est, finite = [], [], [], []
    excess = []          # value − sky, per channel (how bright each channel is)
    near_sky_nbhd = []   # 3×3 median barely above this channel's own sky
    for c in range(3):
        chan = out[..., c]
        m = median_filter(chan, size=3)
        residual = chan - m
        # NaN = "no coverage" (mosaic / partial-overlap gap). A plain median over
        # a residual that contains any NaN is NaN, which makes the threshold NaN
        # and no-ops the whole pass — so estimate the noise floor over finite
        # residuals only, and only ever flag/replace finite-residual pixels.
        f = xp.isfinite(residual)
        med3.append(m)
        finite.append(f)
        if not bool(f.any()):
            sky.append(0.0)
            sigma_est.append(0.0)
            excess.append(chan)
            near_sky_nbhd.append(xp.zeros(chan.shape, dtype=bool))
            continue
        se = 1.4826 * float(xp.median(xp.abs(residual[f])))
        s = float(xp.median(chan[xp.isfinite(chan)]))
        sky.append(s)
        sigma_est.append(se)
        excess.append(chan - s)
        this_excess = xp.maximum(chan - s, se if se > 0 else 1e-6)
        near_sky_nbhd.append(xp.maximum(m - s, 0.0) < ISOLATION_RATIO * this_excess)

    # A pixel is "fully isolated" when *every* channel's neighbourhood is near
    # sky there — a mono/achromatic single-pixel spike, not an extended star.
    fully_isolated = near_sky_nbhd[0] & near_sky_nbhd[1] & near_sky_nbhd[2]

    # Pass 2: repair the defects.
    for c in range(3):
        se = sigma_est[c]
        if se <= 0 or not bool(finite[c].any()):
            continue
        chan = out[..., c]
        residual = chan - med3[c]
        bright = residual > 0
        # Brightest of the *other* two channels' excess at this pixel. A single
        # CFA-site defect leaves them at sky; a star lifts them too.
        others = [excess[j] for j in range(3) if j != c]
        other_max = xp.maximum(others[0], others[1])
        this_excess = xp.maximum(chan - sky[c], se)
        single_channel = other_max < CROSS_CHANNEL_RATIO * this_excess
        # Repair a bright outlier only if it looks like a real defect (isolated
        # in every channel, or confined to this one channel). Dark outliers
        # (cold/dead) are always repaired.
        is_defect = single_channel | fully_isolated | ~bright
        defect = finite[c] & (xp.abs(residual) > sigma * se) & is_defect
        out[..., c] = xp.where(defect, med3[c], chan)
    return out


def _suppress_cpu(rgb: np.ndarray, sigma: float) -> np.ndarray:
    from scipy.ndimage import median_filter

    return _suppress(rgb, sigma, np, median_filter)


def _suppress_gpu(rgb: np.ndarray, sigma: float) -> np.ndarray:
    import cupy as cp
    from cupyx.scipy.ndimage import median_filter as cp_median_filter

    def _cp_median(chan, size):
        return cp_median_filter(chan, size=size)

    rgb_gpu = cp.asarray(rgb, dtype=cp.float32)
    out = _suppress(rgb_gpu, sigma, cp, _cp_median)
    return cp.asnumpy(out)
