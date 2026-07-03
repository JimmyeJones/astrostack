"""Detail operations: hot-pixel removal, denoise, sharpen, deconvolution.

skimage routines don't tolerate NaN, so the denoise/sharpen/deconvolve ops fill
uncovered pixels with the finite median, process, then restore NaN.
"""

from __future__ import annotations

import numpy as np

from seestack.edit.registry import EditContext, EditParam, OpSpec, as_rgb, finite_mask, register


def _with_nan_filled(rgb: np.ndarray, fn):
    """Run ``fn`` on a NaN-free copy (uncovered → per-channel median), restore NaN."""
    out = as_rgb(rgb).copy()
    mask = finite_mask(out)
    if not mask.any():
        return out
    filled = out.copy()
    for c in range(3):
        chan = filled[..., c]
        med = float(np.nanmedian(chan)) if np.isfinite(chan).any() else 0.0
        chan[~np.isfinite(chan)] = med
    result = fn(filled)
    result = as_rgb(result)
    result[~mask] = np.nan
    return result


def _hot_pixels(rgb: np.ndarray, params: dict, ctx: EditContext) -> np.ndarray:
    from seestack.bg.hot_pixels import suppress_hot_cold_pixels

    return suppress_hot_cold_pixels(rgb, sigma=float(params.get("sigma", 5.0)),
                                    use_gpu=ctx.use_gpu)


def _denoise(rgb: np.ndarray, params: dict, ctx: EditContext) -> np.ndarray:
    method = str(params.get("method", "wavelet"))
    strength = float(params.get("strength", 0.5))
    if strength <= 0.0:
        return as_rgb(rgb)  # explicit no-op so the slider has a true identity at 0

    def run(img: np.ndarray) -> np.ndarray:
        from skimage import restoration

        # Robust scale (NOT min/max): on linear astro data a single hot star sets
        # max(), crushing the sky noise to ~0 of the range so denoise does nothing.
        # Scale by the 0.5–99.5th percentile and DON'T clip the highlights, so the
        # sky noise occupies a meaningful fraction of the range and stars survive.
        lo = float(np.nanpercentile(img, 0.5))
        hi = float(np.nanpercentile(img, 99.5))
        if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
            lo, hi = float(img.min()), float(img.max())
        if hi <= lo:
            return img
        norm = (img - lo) / (hi - lo)  # joint scale → colour preserved; stars may exceed 1
        if method == "wavelet":
            try:
                den = restoration.denoise_wavelet(
                    norm, channel_axis=-1, rescale_sigma=True,
                    method="BayesShrink", mode="soft")
            except (ImportError, ValueError):
                den = restoration.denoise_tv_chambolle(
                    norm, weight=0.02 + 0.2 * strength, channel_axis=-1)
            den = norm + strength * (den - norm)  # blend by strength
        elif method == "bilateral":
            den = restoration.denoise_bilateral(
                norm, sigma_color=0.02 + 0.15 * strength, sigma_spatial=2.0,
                channel_axis=-1)
        else:  # tv
            den = restoration.denoise_tv_chambolle(
                norm, weight=0.02 + 0.2 * strength, channel_axis=-1)
        return (den * (hi - lo) + lo).astype(np.float32)

    return _with_nan_filled(rgb, run)


def _sharpen(rgb: np.ndarray, params: dict, ctx: EditContext) -> np.ndarray:
    amount = float(params.get("amount", 1.0))
    radius = float(params.get("radius", 2.0))

    def run(img: np.ndarray) -> np.ndarray:
        from skimage.filters import unsharp_mask
        return unsharp_mask(np.clip(img, 0.0, 1.0), radius=radius, amount=amount,
                            channel_axis=-1).astype(np.float32)

    return _with_nan_filled(rgb, run)


def _deconvolve(rgb: np.ndarray, params: dict, ctx: EditContext) -> np.ndarray:
    iterations = int(params.get("iterations", 10))
    psf_sigma = float(params.get("psf_sigma", 1.5))

    def run(img: np.ndarray) -> np.ndarray:
        from scipy.ndimage import gaussian_filter
        from skimage.restoration import richardson_lucy
        # Gaussian PSF (normalized) sized to ~3σ.
        rad = max(1, int(round(3 * psf_sigma)))
        yy, xx = np.mgrid[-rad:rad + 1, -rad:rad + 1]
        psf = np.exp(-(xx ** 2 + yy ** 2) / (2 * psf_sigma ** 2))
        psf /= psf.sum()
        # Joint robust scale (shared across channels → no colour shift); keep
        # highlights (don't clip stars away) — RL only needs non-negativity.
        lo = float(np.nanpercentile(img, 1.0))
        hi = float(np.nanpercentile(img, 99.5))
        if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
            lo, hi = float(img.min()), float(img.max())
        if hi <= lo:
            return img
        out = np.empty_like(img)
        for c in range(3):
            norm = np.clip((img[..., c] - lo) / (hi - lo), 0.0, None)
            dec = richardson_lucy(norm, psf, num_iter=iterations, clip=False)
            out[..., c] = dec * (hi - lo) + lo
        # Real ring-suppression: a sub-pixel spatial blur (NOT across channels).
        return gaussian_filter(out, sigma=(0.4, 0.4, 0)).astype(np.float32)

    return _with_nan_filled(rgb, run)


register(OpSpec(
    id="detail.hot_pixels", label="Hot-pixel removal", group="detail", stage="linear",
    apply=_hot_pixels, proxy_safe=True,
    help="Remove stray single bright or dark pixels (stuck sensor pixels) that "
         "calibration missed, without softening real stars.",
    params=[EditParam("sigma", "Threshold (σ)", "float", default=5.0, min=2.0, max=10.0,
                      step=0.5,
                      help="How far a pixel must stand out from its neighbours to count "
                           "as hot/cold. Higher = only the most extreme pixels.")],
))

register(OpSpec(
    id="detail.denoise", label="Noise reduction", group="detail", stage="linear",
    apply=_denoise, proxy_safe=True,
    help="Smooth away background grain while keeping stars and detail. Tip: use the "
         "'From your image' button to set a strength from your own noise level.",
    params=[
        EditParam("method", "Method", "enum", default="wavelet",
                  options=["wavelet", "tv", "bilateral"],
                  help="Wavelet suits most stacks; TV and bilateral are alternatives "
                       "worth trying on heavier noise."),
        EditParam("strength", "Strength", "float", default=0.5, min=0.0, max=1.0, step=0.05,
                  help="How hard to smooth. 0 = off; higher removes more noise but can "
                       "blur faint detail if pushed too far."),
    ],
))

register(OpSpec(
    id="detail.sharpen", label="Sharpen", group="detail", stage="nonlinear",
    apply=_sharpen, proxy_safe=True,
    help="Bring out fine detail and star cores by boosting local contrast. Use "
         "gently — too much amplifies noise and rings bright stars.",
    params=[
        EditParam("amount", "Amount", "float", default=1.0, min=0.0, max=3.0, step=0.1,
                  help="How strongly to sharpen. 0 = off; start low and increase."),
        EditParam("radius", "Radius (px)", "float", default=2.0, min=0.5, max=10.0, step=0.5,
                  help="Size of the detail to sharpen, in pixels. Smaller = fine detail, "
                       "larger = broad structure."),
    ],
))

register(OpSpec(
    id="detail.deconvolve", label="Deconvolution", group="detail", stage="linear",
    apply=_deconvolve, proxy_safe=False,  # heavy — apply on demand, not every drag
    help="Recover sharpness lost to seeing by reversing the star blur. Heavy, so it "
         "only runs on Export / full-res PNG (not the live preview).",
    params=[
        EditParam("iterations", "Iterations", "int", default=10, min=1, max=50, step=1,
                  help="More iterations sharpen harder but can add ringing and noise."),
        EditParam("psf_sigma", "Blur width (px)", "float", default=1.5, min=0.5, max=5.0,
                  step=0.1,
                  help="The star-blur width to reverse, in pixels. Use 'From your stars' "
                       "to set it from your measured star size."),
    ],
))
