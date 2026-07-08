"""Detail operations: hot-pixel removal, denoise, sharpen, deconvolution.

scipy/skimage routines don't tolerate NaN, so the denoise/sharpen/deconvolve ops
fill uncovered pixels with the finite median, process, then restore NaN.
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

    sigma = float(params.get("sigma", 5.0))
    # suppress_hot_cold_pixels derives its threshold from the median of the whole
    # residual, which is NaN when the image has any uncovered (mosaic) pixels — so
    # run it on a NaN-filled copy and restore NaN, exactly like the other detail
    # ops. Without this the op silently no-ops on any mosaic/partial-coverage image.
    return _with_nan_filled(
        rgb, lambda img: suppress_hot_cold_pixels(img, sigma=sigma, use_gpu=ctx.use_gpu))


def _denoise(rgb: np.ndarray, params: dict, ctx: EditContext) -> np.ndarray:
    method = str(params.get("method", "wavelet"))
    strength = float(params.get("strength", 0.5))
    if strength <= 0.0:
        return as_rgb(rgb)  # explicit no-op so the slider has a true identity at 0

    arr = as_rgb(rgb)
    if arr.shape[0] < 2 or arr.shape[1] < 2:
        # Degenerate 1-px-thin image: the wavelet path emits all-NaN in the
        # covered region (breaking the NaN=coverage invariant) and bilateral
        # raises IndexError. Return it untouched, mirroring the geometry ops'
        # degenerate-size guards — a sliver has no neighbourhood to denoise over.
        return arr

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
                full = restoration.denoise_wavelet(
                    norm, channel_axis=-1, rescale_sigma=True,
                    method="BayesShrink", mode="soft")
                # denoise_wavelet has no strength knob → blend toward it by strength.
                den = norm + strength * (full - norm)
            except (ImportError, ValueError):
                # Fallback only if PyWavelets is somehow missing. TV already bakes
                # strength into its weight, so DON'T also blend (that double-applied
                # strength and made the fallback differ from the explicit TV option).
                den = restoration.denoise_tv_chambolle(
                    norm, weight=0.02 + 0.2 * strength, channel_axis=-1)
        elif method == "bilateral":
            # sigma_spatial is a full-res pixel extent; scale it down on the
            # preview proxy so the smoothing footprint matches the export.
            den = restoration.denoise_bilateral(
                norm, sigma_color=0.02 + 0.15 * strength,
                sigma_spatial=max(0.5, ctx.scaled_px(2.0)),
                channel_axis=-1)
        else:  # tv
            den = restoration.denoise_tv_chambolle(
                norm, weight=0.02 + 0.2 * strength, channel_axis=-1)
        return (den * (hi - lo) + lo).astype(np.float32)

    return _with_nan_filled(rgb, run)


def _sharpen(rgb: np.ndarray, params: dict, ctx: EditContext) -> np.ndarray:
    amount = float(params.get("amount", 1.0))
    # The radius is in *full-resolution* pixels; on the decimated live-preview
    # proxy shrink it by proxy_scale so the preview sharpens the same physical
    # detail as the full-res export (parity), floored just above zero.
    radius = max(0.05, ctx.scaled_px(float(params.get("radius", 2.0))))

    def run(img: np.ndarray) -> np.ndarray:
        # Unsharp mask in pure numpy/scipy (per-channel Gaussian), NOT skimage's
        # unsharp_mask: on float32 + channel_axis that routine intermittently
        # returned uninitialised garbage / stray NaN in the *covered* region on
        # some scikit-image/scipy builds (took down CI — see IMPROVEMENTS.md). A
        # per-channel Gaussian blur is deterministic and identical in effect:
        # sharp = img + amount·(img − blur), matching skimage's mode="nearest".
        from scipy.ndimage import gaussian_filter
        src = np.clip(img, 0.0, 1.0)
        out = np.empty_like(src)
        for c in range(3):
            blurred = gaussian_filter(src[..., c], sigma=radius, mode="nearest")
            out[..., c] = src[..., c] + amount * (src[..., c] - blurred)
        return np.clip(out, 0.0, 1.0).astype(np.float32)

    return _with_nan_filled(rgb, run)


# The smallest PSF sigma we'll represent on the (decimated) preview proxy. A
# Gaussian narrower than this collapses to a near-delta 3x3 kernel that
# Richardson-Lucy barely acts on, so we floor the proxy PSF here — and warn the
# user (see ``deconv_understates_on_proxy``) that the preview then understates it.
_DECONV_PSF_FLOOR = 0.4


def deconv_understates_on_proxy(psf_sigma: float, proxy_scale: float) -> bool:
    """True when a deconvolution's *live preview* will visibly understate the
    full-res export.

    On the decimated preview proxy the full-res PSF sigma shrinks by
    ``proxy_scale`` (``scaled_px``). Once ``psf_sigma / proxy_scale`` falls below
    ``_DECONV_PSF_FLOOR`` the proxy PSF is clamped up to the floor and its
    Richardson-Lucy kernel becomes a near-delta 3x3 that barely sharpens — while
    the full-res export deconvolves with a real, wider kernel. So the preview
    shows far less star-sharpening than the export actually applies (the
    preview↔export mismatch the editor otherwise tries hard to avoid). This is a
    fundamental limit — the sub-pixel blur simply isn't representable on the
    decimated grid — so instead of hiding it we surface an honest advisory.
    Pure/side-effect free so the backend and tests can share the exact rule.
    """
    if not np.isfinite(psf_sigma) or not np.isfinite(proxy_scale):
        return False
    if proxy_scale <= 1.0 or psf_sigma <= 0.0:
        return False
    return (psf_sigma / proxy_scale) < _DECONV_PSF_FLOOR


def _deconvolve(rgb: np.ndarray, params: dict, ctx: EditContext) -> np.ndarray:
    iterations = int(params.get("iterations", 10))
    # The PSF width is in full-res pixels; on the decimated live-preview proxy
    # shrink it by proxy_scale so the preview reverses the same physical blur as
    # the full-res export (parity), floored just above zero so it stays a real op.
    # When the floor bites the preview understates the export — see
    # ``deconv_understates_on_proxy``, which the editor uses to caption it.
    psf_sigma = max(_DECONV_PSF_FLOOR, ctx.scaled_px(float(params.get("psf_sigma", 1.5))))
    ring = max(0.1, ctx.scaled_px(0.4))  # ring-suppression blur, same scaling

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
        return gaussian_filter(out, sigma=(ring, ring, 0)).astype(np.float32)

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
    apply=_denoise, proxy_safe=True, heavy=True,  # skimage restoration — slow on the proxy
    help="Smooth away background grain while keeping stars and detail. Tip: use the "
         "'From your image' button to set a strength from your own noise level.",
    params=[
        EditParam("method", "Method", "enum", default="wavelet",
                  options=["wavelet", "tv", "bilateral"],
                  option_labels={"wavelet": "Wavelet (recommended)",
                                 "tv": "Total-variation", "bilateral": "Bilateral"},
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
    apply=_deconvolve, proxy_safe=True, heavy=True,  # iterative Richardson-Lucy — slow on the proxy
    help="Recover sharpness lost to seeing by reversing the star blur. It's a heavy "
         "effect, so the live preview may take a moment to update while it's on.",
    params=[
        EditParam("iterations", "Iterations", "int", default=10, min=1, max=50, step=1,
                  help="More iterations sharpen harder but can add ringing and noise."),
        EditParam("psf_sigma", "Blur width (px)", "float", default=1.5, min=0.5, max=5.0,
                  step=0.1,
                  help="The star-blur width to reverse, in pixels. Use 'From your stars' "
                       "to set it from your measured star size."),
    ],
))
