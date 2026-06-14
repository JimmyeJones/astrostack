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

    def run(img: np.ndarray) -> np.ndarray:
        from skimage import restoration
        lo = float(img.min())
        hi = float(img.max())
        if hi <= lo:
            return img
        norm = (img - lo) / (hi - lo)
        if method == "wavelet":
            try:
                den = restoration.denoise_wavelet(
                    norm, channel_axis=-1, rescale_sigma=True,
                    method="BayesShrink", mode="soft")
                den = norm + strength * (den - norm)  # blend by strength
                return (den * (hi - lo) + lo).astype(np.float32)
            except ImportError:
                pass  # PyWavelets missing → fall through to TV
        if method == "bilateral":
            den = restoration.denoise_bilateral(
                norm, sigma_color=0.02 + 0.15 * strength, sigma_spatial=2.0,
                channel_axis=-1)
        else:  # tv (also the wavelet fallback)
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
        lo = float(img.min())
        hi = float(img.max())
        if hi <= lo:
            return img
        out = np.empty_like(img)
        for c in range(3):
            norm = np.clip((img[..., c] - lo) / (hi - lo), 0.0, 1.0)
            dec = richardson_lucy(norm, psf, num_iter=iterations, clip=True)
            out[..., c] = dec * (hi - lo) + lo
        # mild guard against ringing blow-ups
        return gaussian_filter(out, sigma=0).astype(np.float32)

    return _with_nan_filled(rgb, run)


register(OpSpec(
    id="detail.hot_pixels", label="Hot-pixel removal", group="detail", stage="linear",
    apply=_hot_pixels, proxy_safe=True, help="Suppress isolated hot/cold pixels.",
    params=[EditParam("sigma", "σ", "float", default=5.0, min=2.0, max=10.0, step=0.5)],
))

register(OpSpec(
    id="detail.denoise", label="Noise reduction", group="detail", stage="linear",
    apply=_denoise, proxy_safe=True, help="Wavelet / bilateral / TV denoise.",
    params=[
        EditParam("method", "Method", "enum", default="tv",
                  options=["tv", "bilateral", "wavelet"]),
        EditParam("strength", "Strength", "float", default=0.5, min=0.0, max=1.0, step=0.05),
    ],
))

register(OpSpec(
    id="detail.sharpen", label="Sharpen", group="detail", stage="nonlinear",
    apply=_sharpen, proxy_safe=True, help="Unsharp mask.",
    params=[
        EditParam("amount", "Amount", "float", default=1.0, min=0.0, max=3.0, step=0.1),
        EditParam("radius", "Radius (px)", "float", default=2.0, min=0.5, max=10.0, step=0.5),
    ],
))

register(OpSpec(
    id="detail.deconvolve", label="Deconvolution", group="detail", stage="linear",
    apply=_deconvolve, proxy_safe=False,  # heavy — apply on demand, not every drag
    help="Richardson–Lucy deconvolution (Gaussian PSF). Heavy; runs on Apply/Export.",
    params=[
        EditParam("iterations", "Iterations", "int", default=10, min=1, max=50, step=1),
        EditParam("psf_sigma", "PSF σ (px)", "float", default=1.5, min=0.5, max=5.0, step=0.1),
    ],
))
