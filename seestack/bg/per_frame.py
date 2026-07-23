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
from dataclasses import dataclass

import numpy as np

log = logging.getLogger(__name__)

# Set once (per process) if a GPU background-flatten attempt fails, so we stop
# retrying the GPU path — and stop logging the warning — for every frame.
_gpu_bg_disabled = False


MODE_PER_CHANNEL = "per_channel"
MODE_LUMINANCE = "luminance"
MODE_OFF = "off"


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

    def for_image_size(self, h: int, w: int) -> "BackgroundOptions":
        """Adjust box_size for tiny test images so the grid still has cells."""
        max_box = max(8, min(h // 4, w // 4))
        if self.box_size > max_box:
            return BackgroundOptions(
                box_size=max_box,
                filter_size=self.filter_size,
                sigma_clip_n=self.sigma_clip_n,
                dilate_object_mask_px=self.dilate_object_mask_px,
                enabled=self.enabled,
                mode=self.mode,
            )
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
    obj_mask = _build_object_mask_for_bg(out, dilate_px=options.dilate_object_mask_px)

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
                              dilate_px: int = 4) -> np.ndarray:
    """
    Build a boolean object mask for use with ``Background2D(mask=…)``.

    True where the luminance is more than ``sigma_above`` MAD-σ above the
    image median. Dilated by a few pixels so the bright halo around stars and
    the edge of nebulosity also get excluded. The aim is *not* perfect source
    segmentation — we just need the per-tile background estimator not to see
    the bright stuff as "sky".
    """
    from astropy.stats import sigma_clipped_stats
    from scipy.ndimage import binary_dilation

    luma = (0.299 * rgb[..., 0] + 0.587 * rgb[..., 1]
            + 0.114 * rgb[..., 2]).astype(np.float32, copy=False)
    finite = np.isfinite(luma)
    if not finite.any():
        return np.zeros(luma.shape, dtype=bool)
    _, med, std = sigma_clipped_stats(luma, mask=~finite, sigma=3.0, maxiters=3)
    if not (np.isfinite(med) and np.isfinite(std) and std > 0):
        return np.zeros(luma.shape, dtype=bool)
    mask = luma > (med + sigma_above * float(std))
    mask |= ~finite
    if dilate_px > 0:
        mask = binary_dilation(mask, iterations=dilate_px)
    return mask


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

    # Build a bright-object mask on GPU and NaN-out those pixels before
    # tiling, so the per-tile median sees only sky. Without this, tiles that
    # lie inside a nebula sample the nebula as "sky" and the subtraction
    # eats it. We use nanmedian below so masked pixels are ignored cleanly.
    luma_gpu = (0.299 * rgb_gpu[..., 0] + 0.587 * rgb_gpu[..., 1]
                + 0.114 * rgb_gpu[..., 2])
    luma_med = cp.nanmedian(luma_gpu)
    luma_mad = cp.nanmedian(cp.abs(luma_gpu - luma_med))
    luma_std = 1.4826 * luma_mad + 1e-6
    obj_mask = luma_gpu > (luma_med + 2.0 * luma_std)
    # Dilate the object mask by the configured amount so star halos and nebula
    # edges are excluded from the sky tiles. Mirror the CPU path's
    # ``binary_dilation(iterations=dilate_object_mask_px)`` exactly (same
    # cross structuring element, same iteration count, same ``> 0`` guard) so
    # the two backends agree on the masked region — and, crucially, so the
    # editor's proxy_scale-scaled ``dilate_object_mask_px`` is honoured on the
    # GPU path too, keeping the live preview and the full-res export in parity.
    dilate_px = int(options.dilate_object_mask_px)
    if dilate_px > 0:
        from cupyx.scipy.ndimage import binary_dilation

        obj_mask = binary_dilation(obj_mask, iterations=dilate_px)

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
