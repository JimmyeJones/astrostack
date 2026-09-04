"""
Per-frame background flattening.

Why this is the single biggest noise-reduction change in the pipeline:

A Seestar frame at a light-polluted site has a large-scale sky-glow gradient
running across it (often 5-15% of the sky brightness). Stacking by itself
**does not** remove this gradient — the gradient is similar from frame to
frame, so it averages coherently into the final stack. What stacking averages
out is *random* noise; coherent gradients survive intact.

Subtracting a fitted background model from each frame *before* stacking turns
each sub into a near-zero-mean residual, so:

  - Sky in the stack ends up flat (no mottled, low-frequency texture).
  - The autostretch can lift faint nebulosity without pushing gradients up.
  - Noise looks like noise (random, fine-grained) instead of "dirty sky".

Implementation: ``photutils.background.Background2D`` fits a low-order surface
through sigma-clipped sky samples on a coarse grid, then interpolates between
grid points to produce a per-pixel background map. Subtracting that leaves
only stars, nebulosity, and pixel noise.

We fit *per channel* because the gradients differ between R, G, B (light
pollution is usually warm-coloured, so red is the strongest). Doing one
combined fit on luminance would leave residual colour gradients.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace

import numpy as np

log = logging.getLogger(__name__)

# Set once (per process) if a GPU background-flatten attempt fails, so we stop
# retrying the GPU path — and stop logging the warning — for every frame.
_gpu_bg_disabled = False


MODE_PER_CHANNEL = "per_channel"
MODE_LUMINANCE = "luminance"
MODE_OFF = "off"

# Smallest detection (full-res px) taken seriously as an object in the sky-fit
# mask. A star spans several pixels at Seestar seeing (~2 px FWHM); a
# single-pixel spike is noise, and dilating those is what used to swell the mask
# over most of the frame. Mirrors the final gradient pass's own minimum area
# (and the classic source-extraction one).
_MIN_DETECT_AREA = 4
# Block size (full-res px) for the faint-extended-structure detection pass. A
# single sub's noise buries diffuse nebulosity — a Seestar sub's sky sigma is
# larger than the nebula it is pointed at — so it is invisible to any per-pixel
# threshold. Averaging 8x8 blocks cuts the noise ~8x, which is enough to see it,
# and costs ~30 ms on a 1080x1920 sub (a full-res Gaussian smooth would cost 4x
# that on the hot path).
_EXT_BLOCK = 8
# Floor on the extended pass's threshold, as a fraction of the *unblocked* sky
# noise. Blocking shrinks the noise ~8x, so a pure sigma threshold on the blocked
# frame would flag ordinary trend-fit residual as "object" and mask the sky away
# again. Half a sub's sigma keeps the pass to structure a stack would actually
# show, and leaves genuine mesh-scale sky features (amp glow, vignetting) for the
# fit to remove rather than masking them out of it.
_EXT_NOISE_FLOOR = 0.5
# Target number of pixels used for the mask's sky median/sigma. The estimate is a
# robust statistic of a noise field, so a regular subsample of a few hundred
# thousand pixels pins it to a fraction of a percent — and it makes the clip cost
# ~15 ms instead of ~145 ms on a 1080x1920 sub, which is what pays for the
# detrend and the extended pass on the hot path.
_STATS_SAMPLES = 200_000


@dataclass
class BackgroundOptions:
    """Knobs for ``subtract_background``."""

    box_size: int = 128      # tile size for the sky-sample grid (pixels)
    filter_size: int = 3     # smoothing window across grid samples
    sigma_clip_n: float = 3.0  # sigma for the per-tile sky estimate
    # Dilation (px) of the object mask that keeps stars/nebulosity out of the sky
    # fit. A full-resolution pixel measure: the editor scales it by proxy_scale so
    # the masked halo is the same physical size in the decimated live preview as
    # in the export (preview↔export parity). The stack/export path leaves the
    # default 4, so it is byte-for-byte unchanged.
    dilate_object_mask_px: int = 4
    enabled: bool = True
    # 'per_channel': fit a separate bg model for R, G, B. Best for star fields
    #     and small targets where most tiles are sky.
    # 'luminance': fit ONE bg model from the luminance, subtract the same
    #     spatial pattern from all channels (scaled by per-channel level).
    #     Required for extended emission nebulas (M42, Lagoon, North America)
    #     where each channel has different morphology and per-channel fits
    #     create false colour artefacts.
    mode: str = MODE_PER_CHANNEL
    # full_w / render_w for a decimated live-preview proxy (1.0 on the export /
    # stack path). Full-res pixel measures derived *internally* — the object
    # mask's minimum detection area — are scaled by it so the preview and the
    # export detect the same objects, exactly as the caller already does for
    # box_size and dilate_object_mask_px.
    proxy_scale: float = 1.0

    def for_image_size(self, h: int, w: int) -> "BackgroundOptions":
        """Adjust box_size for tiny test images so the grid still has cells."""
        max_box = max(8, min(h // 4, w // 4))
        if self.box_size > max_box:
            # dataclasses.replace so a newly-added field can't be silently
            # dropped here (it was hand-copied field by field before).
            return replace(self, box_size=max_box)
        return self


def subtract_background(
    rgb: np.ndarray,
    options: BackgroundOptions | None = None,
    *,
    use_gpu: bool | None = None,
    errors: list[str] | None = None,
) -> np.ndarray:
    """
    Fit and subtract a 2D background per channel. Returns a new array.

    The output has zero-median sky (per channel). Stars and nebulosity stand
    above the new zero; noise straddles it.

    ``errors`` (opt-in): pass a list to make a per-channel fit failure *surface*
    instead of being silently skipped. The stack path leaves it ``None``
    (best-effort: skip a failed channel), which is unchanged. The editor passes a
    collector so a failed fit reaches the UI rather than the control looking like
    a silent no-op (and a per-channel failure becomes all-or-nothing, so a
    partial subtract can't leave a colour cast).

    GPU path
    --------
    photutils' ``Background2D`` is CPU-only and is the dominant cost in the
    per-frame pipeline (~300 ms for a Seestar frame). When CuPy is available
    we use a faster, simpler median-tile-then-bicubic-upsample method on the
    GPU, which produces visually equivalent results on real sky data at
    ~10× lower latency. Set ``use_gpu=False`` to force the photutils path.
    """
    from seestack.core.xp import GPU_AVAILABLE

    if options is None:
        options = BackgroundOptions()
    if not options.enabled or options.mode == MODE_OFF:
        return rgb

    h, w = rgb.shape[:2]
    options = options.for_image_size(h, w)

    if use_gpu is None:
        use_gpu = GPU_AVAILABLE and (h * w >= 500_000)

    if options.mode == MODE_LUMINANCE:
        return _subtract_background_luminance(rgb, options, use_gpu=use_gpu, errors=errors)

    # MODE_PER_CHANNEL
    return _flatten_gpu_or_cpu(rgb, options, use_gpu=use_gpu, errors=errors)


def _flatten_gpu_or_cpu(
    rgb: np.ndarray,
    options: "BackgroundOptions",
    *,
    use_gpu: bool,
    errors: list[str] | None = None,
) -> np.ndarray:
    """Flatten one image, preferring the GPU path but degrading to CPU on any
    cupy/CUDA hiccup, so a GPU failure never aborts the whole stack.

    Shared by the per-channel dispatch and the luminance path so **both** modes
    degrade identically — previously only per-channel had this guard, so the same
    GPU failure that per-channel recovered from crashed a luminance-mode run (the
    mode recommended for extended-emission nebulae). The disable is latched per
    worker via ``_gpu_bg_disabled`` and warned once (it fired hundreds of times a
    minute when cupy isn't importable in the worker process).
    """
    global _gpu_bg_disabled
    if use_gpu and not _gpu_bg_disabled:
        try:
            return _subtract_background_gpu(rgb, options)
        except Exception as exc:  # noqa: BLE001 — fall back if cupy hiccups
            _gpu_bg_disabled = True
            log.warning(
                "GPU bg flatten unavailable (%s); using CPU for this and all "
                "subsequent frames in this worker", exc,
            )
    return _subtract_background_cpu(rgb, options, errors=errors)


def _subtract_background_luminance(
    rgb: np.ndarray,
    options: "BackgroundOptions",
    *,
    use_gpu: bool,
    errors: list[str] | None = None,
) -> np.ndarray:
    """
    Fit ONE 2D gradient model from the luminance channel and subtract the
    **same spatial shape** from every colour channel.

    Why this preserves colour where per-channel fails:
      - Per-channel mode fits a separate model in R, G, B. For extended
        emission objects (Hα-bright nebulas) the per-channel models differ
        wildly because the nebula's morphology differs across channels —
        leading to cyan cores, red halos, black "holes".
      - Luminance mode fits one shared shape. Whatever the fit subtracts, it
        subtracts equally from R/G/B, so colour ratios in extended structure
        are preserved.

    Note: if the nebula fills more than ~half the frame and box_size is
    smaller than the nebula, the luminance model will *still* include the
    nebula and you'll get black "holes" in all three channels equally. In
    that case the right answer is to turn bg flatten OFF (use ``mode='off'``)
    and remove residual gradients on the final stack instead.
    """
    luma = (0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]).astype(
        np.float32, copy=False
    )
    # Reuse the per-channel path by feeding a 3-channel copy of luma, through the
    # same GPU-with-CPU-fallback guard so a GPU hiccup degrades gracefully here
    # too instead of aborting the stack.
    fake_rgb = np.stack([luma, luma, luma], axis=-1)
    flat_fake = _flatten_gpu_or_cpu(fake_rgb, options, use_gpu=use_gpu, errors=errors)
    bg_luma = (luma - flat_fake[..., 0]).astype(np.float32)

    out = rgb.astype(np.float32, copy=True)
    for c in range(3):
        out[..., c] -= bg_luma
    # Force each channel's residual sky to exactly zero (sigma-clipped median)
    # so mosaic frames from different panels can't drift apart.
    _zero_sky_per_channel(out)
    return out


# exclude_percentile ladder: how much of a box may be masked before the box is
# dropped. We start at the tuned-for-look 80 and, only if the fit *fails* (every
# box is more masked than that — a dense star/cluster field swells the object
# mask past the threshold, or a sparse mosaic canvas is mostly uncovered NaN),
# degrade to progressively more tolerant fits and finally a half-size box, so a
# busy/sparse frame still gets a coarse flatten instead of the whole op failing.
# A succeeding fit at 80 is untouched, so a normal frame is byte-for-byte
# unchanged. Mirrors ``final_gradient._fit_background_2d``'s ladder (v0.89.2).
_EXCLUDE_PERCENTILE_LADDER = (80.0, 95.0, 100.0)


def _fit_bg2d_ladder(channel: np.ndarray, *, box_size: int, filter_size: int,
                     sigma_clip, estimator, mask: np.ndarray) -> np.ndarray:
    """``Background2D`` with the ``exclude_percentile`` degradation ladder.

    On a dense field (object mask covers >80% of every box) or a sparse mosaic
    proxy (mostly-uncovered NaN canvas), the strict ``exclude_percentile=80``
    fit raises ``ValueError``. Rather than give up (dropping the op — a silent
    no-op on the stack path, a hard editor failure on the editor path), we retry
    with more tolerant percentiles and, last, a half-size box. Returns the fitted
    background as a same-shape array; re-raises the last failure if none succeed.
    """
    from photutils.background import Background2D

    h, w = channel.shape[:2]
    box = max(1, min(int(box_size), h, w))
    half = max(1, min(box // 2, h, w))
    attempts: list[tuple[int, float]] = [(box, p) for p in _EXCLUDE_PERCENTILE_LADDER]
    if half < box:
        attempts.append((half, _EXCLUDE_PERCENTILE_LADDER[-1]))

    last_exc: Exception | None = None
    for fit_box, excl in attempts:
        try:
            bkg = Background2D(
                channel,
                box_size=(fit_box, fit_box),
                filter_size=(filter_size, filter_size),
                sigma_clip=sigma_clip,
                bkg_estimator=estimator,
                mask=mask,
                exclude_percentile=excl,
            )
            return bkg.background.astype(np.float32, copy=False)
        except Exception as exc:  # noqa: BLE001 — degrade, then re-raise the last
            last_exc = exc
    assert last_exc is not None
    raise last_exc


def _subtract_background_cpu(rgb: np.ndarray, options: "BackgroundOptions",
                             *, errors: list[str] | None = None) -> np.ndarray:
    from astropy.stats import SigmaClip
    from photutils.background import MMMBackground

    out = rgb.astype(np.float32, copy=True)
    sigma_clip = SigmaClip(sigma=options.sigma_clip_n)
    # MMM (mode-mean-median) estimator approximates the histogram mode rather
    # than the median, which is what we want: faint diffuse nebulosity above
    # sky doesn't bias the estimate upward, so we don't over-subtract and
    # leave coverage-shaped darkening in the stacked mosaic.
    estimator = MMMBackground()

    # Detect bright structure (stars + nebulosity above ~2σ) and mask it out
    # of the bg fit. Without this, tiles that lie inside a nebula sample the
    # nebula itself as "sky" and the subtraction eats it. The mask is cheap
    # (one luminance pass + dilation) and only stops the *bg estimator* from
    # seeing those pixels — the actual subtraction still applies everywhere.
    obj_mask = _build_object_mask_for_bg(
        out, dilate_px=options.dilate_object_mask_px,
        proxy_scale=options.proxy_scale,
    )

    # Fit all three channels first, then subtract — a per-channel *partial*
    # subtraction (some channels flattened, some not) shifts the colour balance,
    # a coherent per-frame bias stacking does NOT average out. So if any channel
    # can't be fit, abandon the whole subtraction rather than leave a colour cast
    # (the editor path already did this; the stack path used to skip only the
    # failed channel and keep the others, casting the stacked frame).
    bgs = []
    for c in range(3):
        try:
            bgs.append(_fit_bg2d_ladder(
                out[..., c],
                box_size=options.box_size,
                filter_size=options.filter_size,
                sigma_clip=sigma_clip,
                estimator=estimator,
                mask=obj_mask,
            ))
        except Exception as exc:  # noqa: BLE001 — degenerate inputs (constant arrays)
            if errors is not None:
                # Editor path: surface the failure and don't leave a partial
                # (per-channel) subtraction that would colour-shift the image.
                errors.append(f"background fit failed: {exc}")
            else:
                # Stack path: degrade to no subtraction (leave gradients) rather
                # than a per-channel-asymmetric one that would colour-cast.
                log.warning("background fit failed for channel %d: %s; leaving "
                            "this frame un-flattened to avoid a colour cast",
                            c, exc)
            return rgb.astype(np.float32, copy=True)

    for c in range(3):
        out[..., c] -= bgs[c]

    _zero_sky_per_channel(out)
    return out


def _build_object_mask_for_bg(rgb: np.ndarray, sigma_above: float = 2.0,
                              dilate_px: int = 4,
                              proxy_scale: float = 1.0) -> np.ndarray:
    """
    Build a boolean object mask for use with ``Background2D(mask=…)``.

    True where the luminance stands ``sigma_above`` MAD-σ above the **local**
    sky. Dilated by a few pixels so the bright halo around stars and the edge of
    nebulosity also get excluded. The aim is *not* perfect source segmentation —
    we just need the per-tile background estimator not to see the bright stuff as
    "sky".

    "Local" is the whole point, and it used to be global. Thresholding against
    the whole-frame median is self-defeating on the very frames this op exists
    for: a raw sub still carrying its light-pollution gradient has a global σ
    dominated by *the gradient*, so the threshold sits far above the dim side and
    below the bright side, and the bright half is classified as "object" —
    excluded from the very fit meant to remove it. Measured on a realistic S30
    sub, mask coverage dim→bright fifth was 0.4 %…59.7 % on an 18 % gradient (a
    150× skew) and 1.0 %…84.3 % on an 8 % one. Detrending the luminance by a
    robust low-order polynomial first (:func:`fit_sky_poly` — light pollution is
    low-order, a star or nebula is not) makes the threshold follow the sky
    instead, without hiding real objects.

    The second half of the same defect: a 2 σ threshold flags ~2 % of pixels
    *wherever* you put it, and ``dilate_px`` grows each isolated noise spike into
    a ~50 px blob — which swallowed 60 % of a **gradient-free** sub. So
    detections smaller than ``_MIN_DETECT_AREA`` (a full-res pixel measure,
    scaled by ``proxy_scale`` like the dilation) are dropped before dilation; a
    real star spans several pixels at Seestar seeing, a single-pixel spike is
    noise.

    Finally, a **block-averaged** pass detects faint *extended* structure the
    per-pixel threshold cannot see (a Seestar sub's grain is larger than the
    nebula it is pointed at). Without it, a now-honest sky fit follows the nebula
    into the "background" and eats it: measured on a gradient-free realistic sub,
    a large faint nebula kept only 44 % of its amplitude through the flatten. It
    is done on 8x8 blocks rather than a full-res Gaussian so it stays affordable
    on the hot path (~30 ms/sub).
    """
    from astropy.stats import sigma_clipped_stats
    from scipy.ndimage import binary_dilation, label

    from seestack.bg.sky_poly import fit_sky_poly

    luma = (0.299 * rgb[..., 0] + 0.587 * rgb[..., 1]
            + 0.114 * rgb[..., 2]).astype(np.float32, copy=False)
    finite = np.isfinite(luma)
    if not finite.any():
        return np.zeros(luma.shape, dtype=bool)
    # Detrend against the smooth sky shape. `fit_sky_poly` returns None when
    # there is too little sky to fit (tiny or mostly-NaN frames), in which case
    # we fall back to the historical global threshold rather than guess.
    luma_filled = np.where(finite, luma, np.nan)
    trend = fit_sky_poly(luma_filled, finite)
    resid = luma_filled if trend is None else luma_filled - trend
    step = max(1, int(round(np.sqrt(resid.size / _STATS_SAMPLES))))
    sample = resid[::step, ::step]
    _, med, std = sigma_clipped_stats(
        sample, mask=~np.isfinite(sample), sigma=3.0, maxiters=3)
    if not (np.isfinite(med) and np.isfinite(std) and std > 0):
        return np.zeros(luma.shape, dtype=bool)
    mask = np.where(finite, resid, -np.inf) > (med + sigma_above * float(std))

    # Drop noise-sized detections before dilating them into blobs.
    scale = max(float(proxy_scale), 1e-3)
    min_area = max(1, int(round(_MIN_DETECT_AREA / (scale * scale))))
    if min_area > 1:
        labels, n_found = label(mask)
        if n_found:
            big_enough = np.bincount(labels.ravel()) >= min_area
            big_enough[0] = False           # label 0 is the background
            mask = big_enough[labels]

    mask |= _extended_structure_mask(resid - med, finite, sigma_above, std, scale)

    mask |= ~finite
    if dilate_px > 0:
        mask = binary_dilation(mask, iterations=dilate_px)
    return mask


def _extended_structure_mask(resid: np.ndarray, finite: np.ndarray,
                             sigma_above: float, std: float,
                             proxy_scale: float) -> np.ndarray:
    """Faint-extended detections from a block-averaged copy of ``resid``.

    NaN-aware (the block mean is taken over the finite pixels only), so a mosaic
    gap can't drag its block down and mask a false halo. Returns a full-size
    boolean mask; blocks are nearest-neighbour expanded back, which is enough
    precision for something that then gets dilated anyway.
    """
    from seestack.core.skystats import sigma_clipped_stats_finite

    block = max(2, int(round(_EXT_BLOCK / proxy_scale)))
    h, w = resid.shape[:2]
    bh, bw = h // block, w // block
    out = np.zeros((h, w), dtype=bool)
    if bh < 2 or bw < 2:
        return out                      # too small to block-average meaningfully

    hh, ww = bh * block, bw * block
    weight = finite[:hh, :ww].astype(np.float32)
    vals = np.where(finite[:hh, :ww], resid[:hh, :ww], 0.0).astype(np.float32)
    shape = (bh, block, bw, block)
    n = weight.reshape(shape).sum(axis=(1, 3))
    coarse = np.where(n > 0, vals.reshape(shape).sum(axis=(1, 3)) / np.maximum(n, 1.0),
                      np.nan)
    _, c_med, c_std = sigma_clipped_stats_finite(coarse, sigma=3.0, maxiters=5)
    if not (np.isfinite(c_med) and np.isfinite(c_std) and c_std > 0):
        return out
    threshold = c_med + max(sigma_above * float(c_std), _EXT_NOISE_FLOOR * std)
    hits = np.where(np.isfinite(coarse), coarse, -np.inf) > threshold
    out[:hh, :ww] = np.repeat(np.repeat(hits, block, axis=0), block, axis=1)
    return out


def _zero_sky_per_channel(rgb: np.ndarray) -> None:
    """
    In-place: subtract each channel's **sky-mode** estimate so the post-flatten
    sky lands at exactly zero — and stays there even with faint diffuse
    nebulosity in the field.

    Why mode and not median: the 3σ-clipped median treats anything above the
    noise floor as "sky-ish", including faint diffuse nebulosity. On a field
    full of background ISM (faint H-alpha, integrated flux nebulae, etc.) the
    median ends up *above* the true sky, so subtracting it over-subtracts.
    In a stack that shows as a darkening proportional to coverage —
    higher-coverage regions accumulate more negative residuals, lower-coverage
    regions accumulate fewer, and the result is the classic "panel rectangles
    at different brightness" mosaic artefact.

    The mode of the per-channel histogram is the most common pixel value —
    the genuine sky peak. Faint diffuse signal above sky doesn't pull it up.
    We use the SExtractor approximation ``mode ≈ 2.5·median − 1.5·mean``,
    which is reliable for slightly-positive-skewed distributions (i.e. real
    sky data). For a perfectly symmetric histogram this collapses back to
    the median, so it's a strict improvement.
    """
    from astropy.stats import sigma_clipped_stats

    for c in range(3):
        ch = rgb[..., c]
        finite = np.isfinite(ch)
        if not finite.any():
            continue
        mean, median, std = sigma_clipped_stats(
            ch, mask=~finite, sigma=3.0, maxiters=5,
        )
        if not (np.isfinite(mean) and np.isfinite(median)):
            continue
        # SExtractor sky-mode estimate. Falls back to the median when the skew is
        # too extreme to trust (heavy bright-object contamination in the tile).
        # Trust test = SExtractor's own criterion: the mode approximation only
        # holds while the clipped mean and median stay within ~0.3·σ; beyond that
        # the field is too crowded. (The earlier `abs(sky-median) > 5·abs(median-
        # mean)` form was algebraically inert — `sky-median` is *by construction*
        # `1.5·(median-mean)`, so `1.5·X > 5·X` never fired — leaving no real
        # backstop. This restores it while staying a no-op on realistic clipped
        # sky, where the 3σ-clip keeps mean−median well inside the 0.3·σ band.)
        sky = 2.5 * median - 1.5 * mean
        if (not np.isfinite(sky)
                or (np.isfinite(std) and std > 0.0
                    and abs(mean - median) > 0.3 * std)):
            sky = median
        ch -= np.float32(sky)


def _subtract_background_gpu(rgb: np.ndarray, options: "BackgroundOptions") -> np.ndarray:
    """
    Tile-median + bicubic interpolation, all on GPU.

    Produces a smooth low-frequency background model very similar to
    photutils' MedianBackground. Per tile we take the sigma-clipped median
    of the pixels, then sample a bicubic spline through the **tile centres**
    (not tile origins — half-tile phase matters!) at every full-resolution
    pixel position, and subtract that from the channel.
    """
    import cupy as cp
    from cupyx.scipy.ndimage import map_coordinates as cp_map_coordinates

    box = options.box_size
    sigma_n = options.sigma_clip_n
    h, w = rgb.shape[:2]

    nh = h // box
    nw = w // box
    if nh < 2 or nw < 2:
        return _subtract_background_cpu(rgb, options)
    cropped_h = nh * box
    cropped_w = nw * box

    rgb_gpu = cp.asarray(rgb, dtype=cp.float32)
    out = rgb_gpu.copy()

    # Bright-object mask: NaN-out those pixels before tiling, so the per-tile
    # median sees only sky. Without this, tiles that lie inside a nebula sample
    # the nebula as "sky" and the subtraction eats it. We use nanmedian below so
    # masked pixels are ignored cleanly.
    #
    # The mask comes from the **shared CPU builder** rather than a GPU-side
    # approximation of it. It used to be a global-median/MAD threshold here,
    # which is the starved-mask bug (a light-polluted sub's bright half reads as
    # "object" and is excluded from the fit meant to remove it) *plus* a silent
    # divergence from what the CPU backend masks — the same class of GPU/CPU
    # parity gap as the hardcoded dilation fixed in v0.119.7. One tested
    # implementation for both backends is worth the host-side cost: it is bounded
    # (~1 pass over the frame, subsampled statistics) and buys the detrended
    # threshold, the noise-sized-detection filter and the faint-extended pass.
    luma_gpu = (0.299 * rgb_gpu[..., 0] + 0.587 * rgb_gpu[..., 1]
                + 0.114 * rgb_gpu[..., 2])
    luma_med = cp.nanmedian(luma_gpu)
    obj_mask = cp.asarray(_build_object_mask_for_bg(
        rgb, dilate_px=int(options.dilate_object_mask_px),
        proxy_scale=options.proxy_scale,
    ))

    # Coordinate map: for each full-res pixel (y, x), compute the fractional
    # *tile* index whose centre lies at that location. Tile (i, j) is centred
    # at full-res ((i + 0.5)·box - 0.5, (j + 0.5)·box - 0.5), so the inverse
    # mapping is lo_idx = (full + 0.5)/box - 0.5.
    yy, xx = cp.indices((h, w), dtype=cp.float32)
    ly = (yy + 0.5) / box - 0.5
    lx = (xx + 0.5) / box - 0.5
    coords = cp.stack([ly, lx], axis=0)

    for c in range(3):
        ch = rgb_gpu[:cropped_h, :cropped_w, c]
        ch_masked = cp.where(obj_mask[:cropped_h, :cropped_w], cp.nan, ch)
        # (nh, box, nw, box) -> (nh, nw, box*box)
        tiles = ch_masked.reshape(nh, box, nw, box).transpose(0, 2, 1, 3).reshape(
            nh, nw, box * box,
        )
        # nanmedian ignores the masked (NaN) pixels — tiles that are fully
        # masked (entirely inside a bright object) come out as NaN; we
        # interpolate over them via map_coordinates' nearest-neighbour mode.
        med = cp.nanmedian(tiles, axis=-1, keepdims=True)
        mad = cp.nanmedian(cp.abs(tiles - med), axis=-1, keepdims=True)
        sigma = 1.4826 * mad + 1e-6
        for _ in range(2):
            clip_mask = cp.abs(tiles - med) < sigma_n * sigma
            tiles = cp.where(clip_mask, tiles, cp.nan)
            med = cp.nanmedian(tiles, axis=-1, keepdims=True)
        # Mode-like sky estimate per tile (SExtractor: 2.5·median − 1.5·mean).
        clipped_mean = cp.nanmean(tiles, axis=-1, keepdims=True)
        mode_est = 2.5 * med - 1.5 * clipped_mean
        # Same SExtractor trust test as the CPU path (_zero_sky_per_channel):
        # keep the mode only while the clipped mean/median stay within 0.3·σ of
        # each other, else fall back to the median (too crowded to trust the
        # mode). `sigma` (the robust 1.4826·MAD spread computed above) is the
        # per-tile σ scale — no need for a fresh nanstd (which also warns on the
        # ≤1-valid-pixel tiles the nearest-neighbour fill handles anyway).
        skew = cp.abs(clipped_mean - med)
        trust = cp.isfinite(mode_est) & (skew <= 0.3 * sigma)
        sky_est = cp.where(trust, mode_est, med)
        # If a tile was fully masked (NaN), fill from neighbouring tiles by
        # forward+backward replacement.
        sky_est = cp.where(cp.isfinite(sky_est), sky_est, luma_med)
        bg_lo = sky_est.squeeze(-1)  # (nh, nw)
        bg_full = cp_map_coordinates(bg_lo, coords, order=3, mode="nearest")
        out[..., c] = rgb_gpu[..., c] - bg_full

    result = cp.asnumpy(out)
    # Same zero-sky pull as the CPU path. Crucial for mosaics; cheap on CPU.
    _zero_sky_per_channel(result)
    return result
