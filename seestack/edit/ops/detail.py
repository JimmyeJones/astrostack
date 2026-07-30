"""Detail operations: hot-pixel removal, denoise, sharpen, deconvolution,
colour-blotch smoothing.

scipy/skimage routines don't tolerate NaN, so the denoise/sharpen/deconvolve ops
fill uncovered pixels with the finite median, process, then restore NaN.
"""

from __future__ import annotations

import numpy as np

from seestack.edit.registry import (
    EditContext,
    EditParam,
    OpSpec,
    as_rgb,
    finite_mask,
    luminance,
    register,
)


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
                # BayesShrink sets each wavelet subband's soft threshold from the
                # signal variance (T = σ_noise² / σ_signal). An *unclipped* bright
                # star (norm ≫ 1, because we deliberately don't clip highlights
                # above) inflates σ_signal, driving T → ~0 — so soft-thresholding
                # removes almost nothing and the sky noise survives. On any real
                # starfield that makes the recommended wavelet denoise a near-no-op
                # (measured: ~2% sky-noise reduction with a star present vs ~93%
                # with it removed). Clip the highlights to the sky's own range *for
                # the wavelet estimate only* so the threshold reflects the sky
                # noise, then reinstate the unclipped star pixels so the blend never
                # crushes them toward the clip.
                clipped = np.minimum(norm, 1.0)
                full = restoration.denoise_wavelet(
                    clipped, channel_axis=-1, rescale_sigma=True,
                    method="BayesShrink", mode="soft")
                full = np.where(norm > 1.0, norm, full)
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


# ---- Chroma (colour-blotch) smoothing -----------------------------------
#
# The visible sky defect left on a thin OSC stack after ordinary denoise isn't
# fine grain — the wavelet pass already handles that — but a *low-frequency
# colour blotch*: patches of sky drifting green or magenta over tens of pixels.
# Wavelet denoise only shrinks fine scales, so cranking its strength waxes the
# luminance grain (a plastic sky) without touching the blotch at all.
#
# This op removes it the way every mature tool does: split the image into
# luminance + chroma, smooth *only* the chroma with a wide kernel, and put the
# untouched luminance back. Detail, stars and grain live in the luminance, so
# they survive bit-exactly (see ``_chroma_denoise`` for the proof).

# Default chroma kernel width, in *full-resolution* pixels. Wide on purpose — the
# blotch is tens of px across, and anything narrow enough to preserve fine colour
# detail is also narrow enough to leave the blotch behind. 24 px is the measured
# middle: on a synthetic S30 sky carrying a 25 px-scale colour drift it removes
# ~⅓ of the sky's colour spread at full strength while a *faint* (0.6σ) extended
# nebula still keeps ~89 % of its own colour; doubling it to 48 px removes half
# again as much but drops the faint nebula to ~72 %.
_CHROMA_RADIUS_PX = 24.0
# Floor for the proxy-scaled kernel: below ~1 px a Gaussian collapses to a
# near-delta and the live preview would show nothing while the export smooths for
# real (the preview↔export mismatch the editor works hard to avoid).
_CHROMA_SIGMA_FLOOR = 1.0
# Pixels this many robust sigmas above the sky start losing protection from the
# smoothing, reaching none ``_STAR_PROTECT_SPAN`` sigmas further up. Stars and
# bright cores are where a wide chroma blur would visibly bleed colour, so they
# keep their own.
_STAR_PROTECT_FROM_SIGMA = 2.0
_STAR_PROTECT_SPAN_SIGMA = 4.0


def _box_blur3(arr: np.ndarray, sigma: float) -> np.ndarray:
    """Three successive box filters ≈ a Gaussian of width ``sigma``.

    A true ``gaussian_filter`` at the widths this op needs (tens of pixels) costs
    O(sigma) per pixel per axis — measured 2.7 s at radius 16 and 8.8 s at radius
    48 on a full-res 1080×1920 stack, far too slow for an editor op that also has
    to redraw the live preview. Three box passes are the standard O(1)-per-pixel
    approximation and converge on a Gaussian by the central limit theorem; for
    ``n`` passes of width ``w`` the equivalent sigma is ``n(w²−1)/12``, which
    inverts to the width chosen here. The residual difference from a true
    Gaussian is far below the colour drift this op exists to average out.
    """
    from scipy.ndimage import uniform_filter

    width = int(round((4.0 * sigma * sigma + 1.0) ** 0.5))
    if width % 2 == 0:
        width += 1
    if width < 3:
        return arr.astype(np.float32, copy=True)
    out = arr.astype(np.float32, copy=False)
    for _ in range(3):
        out = uniform_filter(out, size=width, mode="nearest")
    return out


def _coverage_weight(mask: np.ndarray, sigma: float) -> tuple[np.ndarray | None, np.ndarray]:
    """``(blurred_coverage, ok)`` for the normalised-convolution denominator.

    Blurring a gap-filled array directly drags the fill value in around a mosaic
    hole; dividing the blurred data by the blurred *mask* (the standard
    normalised convolution) makes a gap neither contribute to nor bias its
    neighbours. Computed once and shared by all three channels — it depends only
    on coverage, and it's half the filter work.

    A fully-covered image (every single-field stack) needs no denominator at all,
    so it returns ``None`` and an all-True ``ok`` — halving the cost in the common
    case.
    """
    if mask.all():
        return None, np.ones(mask.shape, dtype=bool)
    den = _box_blur3(mask.astype(np.float32), sigma)
    return den, den > 1e-6


def _nan_aware_blur(arr: np.ndarray, mask: np.ndarray, sigma: float,
                    den: np.ndarray | None, ok: np.ndarray) -> np.ndarray:
    """Wide blur of ``arr`` that treats ``~mask`` as *absent*, not as zero, using
    the shared coverage denominator from :func:`_coverage_weight`.

    Linear in ``arr`` for a fixed mask — which is what keeps the luminance
    exactly invariant in :func:`_chroma_denoise`.
    """
    num = _box_blur3(np.where(mask, arr, 0.0).astype(np.float32), sigma)
    if den is None:
        return num
    out = np.zeros_like(num)
    out[ok] = num[ok] / den[ok]
    return out


def _robust_sky(values: np.ndarray) -> tuple[float, float]:
    """``(median, MAD-derived sigma)`` of a 1-D sample, decimated for speed.

    A plain median/MAD is enough here (this only shapes *how much* smoothing a
    bright pixel keeps, never a threshold anything hinges on), and it costs a
    fraction of a sigma-clip on a full-res canvas.
    """
    if values.size == 0:
        return 0.0, 0.0
    if values.size > 200_000:
        values = values[::int(np.ceil(values.size / 200_000))]
    med = float(np.median(values))
    mad = float(np.median(np.abs(values - med))) * 1.4826
    return med, (mad if np.isfinite(mad) and mad > 0 else 0.0)


def _chroma_denoise(rgb: np.ndarray, params: dict, ctx: EditContext) -> np.ndarray:
    """Smooth the low-frequency colour blotch out of the sky, leaving luminance
    (and therefore every star, edge and grain) bit-exactly alone.

    Each channel is split into luminance ``Y`` plus its own chroma residual
    ``d_c = C − Y``; only ``d_c`` is blurred, then ``C' = Y + d_c'``. Because the
    Rec.709 luminance weights sum to 1, ``Σ w_c·d_c ≡ 0`` everywhere, and the
    smoothing is linear with the same kernel for all three channels, so
    ``Σ w_c·d_c' ≡ 0`` too — i.e. the recombined image has *exactly* the input's
    luminance. That's the whole point: it can flatten a green/magenta patch
    without softening anything you'd call detail.

    ``strength`` 0 is an exact identity. ``protect_stars`` (default on) tapers the
    effect off on pixels well above the sky so a wide chroma kernel can't bleed a
    red star's colour into its surroundings; it self-disables when the sky has no
    measurable spread (a synthetic flat), where there is nothing to tell a star
    from the background anyway.
    """
    strength = float(params.get("strength", 0.5))
    out = as_rgb(rgb).copy()
    if strength <= 0.0:
        return out  # explicit no-op so the slider has a true identity at 0
    if out.shape[0] < 2 or out.shape[1] < 2:
        return out  # a 1-px sliver has no neighbourhood to smooth over
    mask = finite_mask(out)
    if not mask.any():
        return out
    # The radius is a *full-resolution* pixel measure; shrink it on the decimated
    # live-preview proxy so the preview smooths the same physical area as the
    # export (parity), floored so it never degenerates to a no-op there.
    sigma = max(_CHROMA_SIGMA_FLOOR,
                ctx.scaled_px(float(params.get("radius", _CHROMA_RADIUS_PX))))

    y = luminance(out)
    blend = np.full(y.shape, np.float32(strength), dtype=np.float32)
    if bool(params.get("protect_stars", True)):
        med, sky_sigma = _robust_sky(y[mask])
        if sky_sigma > 0:
            lo = med + _STAR_PROTECT_FROM_SIGMA * sky_sigma
            bright = np.clip((np.where(mask, y, lo) - lo)
                             / (_STAR_PROTECT_SPAN_SIGMA * sky_sigma), 0.0, 1.0)
            blend = blend * (1.0 - bright).astype(np.float32)

    den, ok = _coverage_weight(mask, sigma)
    for c in range(3):
        d = np.where(mask, out[..., c] - y, 0.0).astype(np.float32)
        smoothed = _nan_aware_blur(d, mask, sigma, den, ok)
        d_new = np.where(ok, d + blend * (smoothed - d), d)
        out[..., c] = y + d_new
    out[~mask] = np.nan  # never invent colour over a mosaic gap
    return out


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
    id="detail.chroma_denoise", label="Colour-blotch smoothing", group="detail",
    stage="any", apply=_chroma_denoise, proxy_safe=True, heavy=True,  # wide filter
    help="Even out the patchy green/magenta colour drift across the sky that "
         "ordinary noise reduction leaves behind. It only touches colour, so "
         "stars, detail and sharpness are untouched.",
    params=[
        EditParam("strength", "Strength", "float", default=0.5, min=0.0, max=1.0,
                  step=0.05,
                  help="How much of the colour patchiness to smooth away. 0 = off."),
        EditParam("radius", "Radius (px)", "float", default=_CHROMA_RADIUS_PX,
                  min=2.0, max=48.0, step=1.0, group="advanced",
                  help="How wide the colour patches are, in pixels. Wider smooths "
                       "broader blotches; too wide can flatten real colour variation."),
        EditParam("protect_stars", "Keep star colours", "bool", default=True,
                  group="advanced",
                  help="On (recommended): leave bright stars and bright cores at "
                       "their own colour so smoothing can't bleed them into the sky."),
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
