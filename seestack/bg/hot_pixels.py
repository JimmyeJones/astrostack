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
"""

from __future__ import annotations

import logging

import numpy as np

log = logging.getLogger(__name__)

DEFAULT_SIGMA = 5.0


def suppress_hot_cold_pixels(
    rgb: np.ndarray,
    sigma: float = DEFAULT_SIGMA,
    *,
    use_gpu: bool | None = None,
) -> np.ndarray:
    """
    Per-channel local-median-filter outlier suppression.

    Replaces pixels >``sigma`` × MAD-σ away from their 3×3 neighbourhood
    median with that neighbourhood median. Returns a new array.
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


def _suppress_cpu(rgb: np.ndarray, sigma: float) -> np.ndarray:
    from scipy.ndimage import median_filter

    out = rgb.astype(np.float32, copy=True)
    for c in range(3):
        med3 = median_filter(out[..., c], size=3)
        residual = out[..., c] - med3
        # Estimate the noise floor over VALID residuals only. NaN = "no coverage"
        # (mosaic / partial-overlap gaps), and a plain median over a residual that
        # contains any NaN returns NaN, which makes the threshold NaN and turns the
        # whole suppression into a silent no-op. Restrict to finite residuals, and
        # only ever flag/replace finite-residual pixels so gaps stay NaN.
        finite = np.isfinite(residual)
        if not finite.any():
            continue
        sigma_est = 1.4826 * float(np.median(np.abs(residual[finite])))
        if sigma_est <= 0:
            continue
        mask = finite & (np.abs(residual) > sigma * sigma_est)
        out[..., c] = np.where(mask, med3, out[..., c])
    return out


def _suppress_gpu(rgb: np.ndarray, sigma: float) -> np.ndarray:
    import cupy as cp
    from cupyx.scipy.ndimage import median_filter as cp_median_filter

    rgb_gpu = cp.asarray(rgb, dtype=cp.float32)
    out = rgb_gpu.copy()
    for c in range(3):
        med3 = cp_median_filter(rgb_gpu[..., c], size=3)
        residual = rgb_gpu[..., c] - med3
        # NaN-aware noise floor over valid residuals only (see the CPU path) — a
        # plain median over a gap-containing residual is NaN and no-ops the pass.
        finite = cp.isfinite(residual)
        if not bool(finite.any()):
            continue
        sigma_est = 1.4826 * float(cp.median(cp.abs(residual[finite])))
        if sigma_est <= 0:
            continue
        mask = finite & (cp.abs(residual) > sigma * sigma_est)
        out[..., c] = cp.where(mask, med3, rgb_gpu[..., c])
    return cp.asnumpy(out)
