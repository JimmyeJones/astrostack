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
     of the luminance so the median we measure is genuine sky. The threshold
     is measured against each pixel's *own* coverage level's sky — see below.
  2. Compute the per-channel median of the unmasked pixels at that
     coverage value.
  3. Subtract that median from all pixels at that coverage value.

The net effect: every coverage region's sky lands at exactly zero, panel
steps vanish, and bright objects keep their relative brightness because we
masked them out of the median calculation.

Detecting objects is where this pass can quietly defeat itself, so the
threshold is measured **per coverage level**, not once for the whole canvas.
A single canvas-wide ``median + σ`` has its σ set by the panel-to-panel level
offsets — the very thing about to be subtracted — rather than by the noise,
and that breaks the threshold in both directions at once:

  * It floats far above the grain, so stars and nebulosity stop being masked
    and leak into every level's "sky" median. (Measured on a realistic
    4-panel scene: the threshold landed at 72 ADU on 2 ADU noise and caught
    11 % of the nebula, leaving 5.2 ADU of coloured panel step *after*
    leveling. Detrending first: 0.16 ADU.)
  * A level whose residual sky happens to sit high is flagged wholesale as
    one big "object" and loses its sky sample — and that is precisely the
    level with the most offset to remove.

So a rough per-level sky is removed before thresholding, which puts every
level on the same footing and lets the threshold measure grain again. On a
single-coverage-level image the detrend is one constant subtracted from the
pixels and the median alike, so an ordinary non-mosaic stack is unaffected.

Every level big enough to matter then gets an offset, including any whose sky
sample is still starved: leaving one alone while its neighbours are pushed to
zero doesn't preserve it, it strands it at a different zero point — a coloured
step at the very seam this pass exists to flatten. A starved level is
re-thresholded against its own statistics, and if even that can't produce a
sky sample its offset is interpolated from the levels around it. A level whose
retained sample is far more spread out than the canvas's own sky is *not*
measured — it is filled by real structure, and reading the object's level as a
sky offset would subtract real flux.

Cost: one mask + one pass per (channel, coverage value), plus per-level
locating statistics read from a capped, strided sample. On a typical mosaic
with maybe a dozen distinct coverage values, this is well under a second on
the stacked canvas.
"""

from __future__ import annotations

import logging

import numpy as np

log = logging.getLogger(__name__)

# Below this many *strided* sky pixels a per-level median is meaningless noise,
# so we never level a level with fewer — even on a heavily-decimated proxy where
# scaling ``min_pixels_per_level`` down would otherwise reach into single digits.
_MIN_STRIDED_PIXELS = 12

# A starved coverage level is only re-measured against its own statistics when
# it actually *looks* like sky: its own sigma-clipped spread must be no more
# than this multiple of the canvas-wide sky spread. Sky is flat; a region full
# of nebula or a galaxy is not, and re-measuring one of those would read the
# object's own level as "sky" and subtract real flux. The canvas-wide σ is
# itself inflated by the between-level offsets on a mosaic, so 3× is a generous
# bound that still rejects structured regions by orders of magnitude.
_RESCUE_MAX_SIGMA_RATIO = 3.0


# Sigma-clipped statistics used only to *locate* a level (its rough sky, its
# spread) converge long before they run out of pixels, so cap how many they read.
# A deterministic stride down to this many samples keeps a 100 MP mosaic's extra
# per-level statistics from costing more than the leveling itself; the median and
# σ of 250k samples are precise to well under a thousandth of the noise.
_STATS_SAMPLE_CAP = 250_000


def _robust_stats(values: np.ndarray) -> tuple[float, float]:
    """``(median, sigma)`` of ``values``, sigma-clipped, on a capped sample.

    Strided (not randomly sampled) so the answer is deterministic for a given
    input — two runs of the same stack must produce the same picture.
    """
    from astropy.stats import sigma_clipped_stats

    flat = np.asarray(values).ravel()
    if flat.size > _STATS_SAMPLE_CAP:
        flat = flat[::int(np.ceil(flat.size / _STATS_SAMPLE_CAP))]
    _, med, std = sigma_clipped_stats(flat, sigma=3.0, maxiters=5)
    return float(med), float(std)


def _local_sky_mask(
    luma: np.ndarray,
    region_mask: np.ndarray,
    object_sigma: float,
    dilate_px: int,
    max_sigma: float,
) -> np.ndarray | None:
    """Sky pixels of ONE coverage level, thresholded against *its own* stats.

    The main object mask thresholds the whole canvas against a single global
    ``median + object_sigma·σ``, which conflates "bright because it is a star or
    nebula" with "bright because this coverage region's residual sky sits higher
    than the rest of the canvas" — and the second is precisely what this pass
    exists to remove. So a mosaic's *most* offset coverage level is the one most
    likely to read as one big object, lose its sky sample, fall under the
    pixel floor, and be skipped — leaving its full offset in place. Because the
    offsets are per channel, the step it leaves is a *coloured* seam: the pass
    re-creates the panel step at the very boundary it was meant to flatten.

    Re-thresholding that level against its own sigma-clipped statistics recovers
    a genuine sky sample. Used **only** as a rescue for a level the global mask
    has starved below the floor, so a level that already had enough sky pixels
    is untouched. Returns ``None`` when the level's own statistics are
    degenerate (all-equal or non-finite) **or** when the region is too
    structured to be sky at all (its own sigma-clipped spread exceeds
    ``max_sigma``) — a coverage level genuinely filled by a galaxy or nebula
    must not have the *object's* level read as a sky offset and subtracted. In
    either case the caller falls through to the interpolated fill.
    """
    from scipy.ndimage import binary_dilation

    # Work in the level's bounding box — a coverage level is usually a thin
    # strip on a large canvas, and dilating the whole canvas per rescued level
    # would be needlessly expensive on a big mosaic.
    ys, xs = np.nonzero(region_mask)
    if ys.size == 0:
        return None
    y0, y1 = int(ys.min()), int(ys.max()) + 1
    x0, x1 = int(xs.min()), int(xs.max()) + 1
    sub_region = region_mask[y0:y1, x0:x1]
    sub_luma = luma[y0:y1, x0:x1]

    med, std = _robust_stats(sub_luma[sub_region])
    if not (np.isfinite(med) and np.isfinite(std) and std > 0):
        return None
    if float(std) > max_sigma:
        return None  # structured, not sky — see the docstring
    local_obj = sub_luma > (med + object_sigma * float(std))
    if dilate_px > 0:
        local_obj = binary_dilation(local_obj, iterations=dilate_px)
    out_mask = np.zeros_like(region_mask)
    out_mask[y0:y1, x0:x1] = sub_region & ~local_obj
    return out_mask


def level_by_coverage(
    rgb: np.ndarray,
    coverage: np.ndarray,
    *,
    frame_coverage: np.ndarray | None = None,
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
    frame_coverage
        Optional (H, W) *true integer frame count* per pixel. The panel steps
        this pass cancels trace the **frame-count** map (where footprints
        overlap), so binning should use the honest count — but with quality
        weighting on, ``coverage`` is a Σ-of-weights that no longer equals the
        count (e.g. 5 frames at weight 0.9 → Σ=4.5), so rounding it fuzzes the
        bins: two regions both covered by exactly 5 frames can split across bins,
        or two genuinely different-coverage regions collide into one. When the
        caller passes the exact per-pixel count (the accumulator already computes
        it for the honest ``coverage_min``/``max`` diagnostics), bin by *that*.
        Defaults to ``None`` → bin by ``coverage`` (unchanged); on an unweighted
        stack the two are identical, so that path is byte-for-byte unchanged.
    object_sigma
        Pixels above ``median + object_sigma · σ`` of the luminance are masked
        out of the per-coverage median calculation — that's stars and
        nebulosity, which should not bias the sky estimate.
    min_pixels_per_level
        A coverage value covering fewer than this many *full-resolution* pixels
        is skipped entirely — a sliver that small carries no reliable median and
        is not worth shifting. A level that clears the floor but whose sky sample
        is eaten by the object mask is re-thresholded against its own statistics
        (:func:`_local_sky_mask`) and, failing that, given the offset
        interpolated from the levels around it, rather than left holding its
        full residual next to neighbours that no longer hold theirs.
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

    # Bin by the true per-pixel frame count when the caller provides it (quality
    # weighting fuzzes the weighted-sum ``coverage``); otherwise fall back to the
    # coverage map. Unweighted stacks have ``frame_coverage == coverage``, so the
    # fallback path is byte-for-byte unchanged.
    cov_src = frame_coverage if frame_coverage is not None else coverage
    if cov_src.ndim == 3:
        # WeightedSumAccumulator's coverage is per-channel but identical across
        # channels for our pipeline; collapse to 2D.
        cov2d = cov_src[..., 0]
    else:
        cov2d = cov_src

    # Luminance + object mask. We dilate the mask so star halos and nebula
    # *edges* are also excluded — after stretching, even mildly bright pixels
    # near a source bias the per-level median enough to show up as a step.
    luma = (0.299 * out[..., 0] + 0.587 * out[..., 1]
            + 0.114 * out[..., 2]).astype(np.float32, copy=False)
    finite = np.isfinite(luma)
    if not finite.any():
        return out

    # Bin coverage values. ``cov2d`` is the true integer frame count when the
    # caller passed ``frame_coverage`` (already integral); on the fallback path
    # it's the Σ-weight map, so round to the nearest integer — the
    # **integer-rounded** bin is what carries the visible panel structure.
    # (Binned *before* the object mask: the threshold below is measured per
    # coverage level, so it needs the bins.)
    cov_int = np.rint(cov2d).astype(np.int32, copy=False)
    valid_pix = (cov_int > 0) & finite
    if not valid_pix.any():
        return out

    # Every coverage value actually present on the canvas — taken over
    # ``valid_pix`` rather than the sky mask so a level the object mask has
    # entirely swallowed is still *considered* (and rescued below) instead of
    # dropping out of the list unnoticed.
    levels, region_counts = np.unique(cov_int[valid_pix], return_counts=True)
    # The levels big enough to be worth correcting at all. A coverage value
    # covering fewer than the floor's worth of pixels *in total* is a sliver, not
    # a panel: it carries no reliable median, and it is left untouched — neither
    # measured nor filled — exactly as it always has been.
    big_levels = [
        int(lv) for lv, n in zip(levels, region_counts)
        if lv > 0 and n >= effective_min
    ]

    _, med, std = sigma_clipped_stats(luma, mask=~finite, sigma=3.0, maxiters=5)
    if not (np.isfinite(med) and np.isfinite(std) and std > 0):
        return out

    # Detect objects against each pixel's **own coverage level's** sky, not
    # against one canvas-wide median + σ. On the mosaic this pass exists for,
    # the canvas-wide σ is set by the panel-to-panel level offsets rather than
    # by the noise — the very thing we are about to subtract — which wrecks the
    # threshold in both directions at once: it floats far above the noise, so
    # stars and nebulosity stop being masked and leak into every level's "sky"
    # estimate; and a level whose sky happens to sit high is flagged wholesale
    # as one big object and loses its sky sample. Removing a rough per-level sky
    # first puts every level on the same footing, so the threshold measures
    # grain again. On a single-coverage-level image the detrend is one constant
    # subtracted from both the pixels and the median, so the mask is exactly the
    # one it has always been — an ordinary non-mosaic stack is unaffected.
    rough_sky = np.full(luma.shape, np.float32(med), dtype=np.float32)
    for level in big_levels:
        region = (cov_int == level) & finite
        med_level, _ = _robust_stats(luma[region])
        if np.isfinite(med_level):
            rough_sky[region] = np.float32(med_level)
    detrended = luma - rough_sky
    _, med_d, std_d = sigma_clipped_stats(
        detrended, mask=~finite, sigma=3.0, maxiters=5)
    if np.isfinite(med_d) and np.isfinite(std_d) and std_d > 0:
        detect, med, std = detrended, float(med_d), float(std_d)
    else:
        # Degenerate detrend (e.g. every level perfectly flat): fall back to the
        # canvas-wide statistics rather than refusing to mask anything.
        detect = luma

    object_mask = detect > (med + object_sigma * float(std))
    if dilate_object_mask_px > 0:
        object_mask = binary_dilation(object_mask, iterations=dilate_object_mask_px)

    # How spread out the canvas's *retained* sky is, once the object mask has
    # done its job — the yardstick for "does this level's sample actually look
    # like sky?" below. Comparing a level's retained spread against the canvas's
    # retained spread is apples to apples, and both are measured on the
    # detrended luminance so neither carries a level's own offset.
    sky_pix = valid_pix & ~object_mask
    sky_sigma = float(std)
    if sky_pix.any():
        _, s = _robust_stats(detect[sky_pix])
        if np.isfinite(s) and s > 0:
            sky_sigma = float(s)
    max_level_sigma = _RESCUE_MAX_SIGMA_RATIO * sky_sigma

    # First pass: compute the per-channel SKY MODE for each coverage level
    # using the SExtractor approximation (2.5·median − 1.5·sigma-clipped-mean).
    # Mode is robust to faint diffuse signal that would bias the plain median
    # upward by a coverage-dependent amount (which is exactly the residual
    # bias that re-emerges as panel steps after stretching).
    offsets: dict[int, list[float]] = {}  # level -> [R_off, G_off, B_off]
    sky_counts: dict[int, int] = {}
    n_rescued = 0
    for level in big_levels:
        region_mask = (cov_int == level) & valid_pix
        region_sky_mask = region_mask & ~object_mask
        n_sky = int(region_sky_mask.sum())
        if n_sky < effective_min:
            # The global object threshold has starved this level's sky sample.
            # Most often that is not because the region *is* an object but
            # because its residual sky sits above the canvas-wide median + σ —
            # the offset this pass exists to subtract. Re-threshold it against
            # its own statistics before giving up (see :func:`_local_sky_mask`);
            # a level that already had enough sky pixels never reaches here, so
            # nothing that is leveled today changes.
            rescued = _local_sky_mask(
                luma, region_mask, object_sigma, dilate_object_mask_px,
                max_level_sigma)
            if rescued is None or int(rescued.sum()) < effective_min:
                continue
            region_sky_mask = rescued
            n_sky = int(region_sky_mask.sum())
            n_rescued += 1
        # The retained sample has to look like sky before we call its mode a sky
        # level. A coverage region genuinely *filled* by a galaxy or nebula
        # leaves behind a sample far more spread out than the canvas's own
        # retained sky; measuring it would read the object's level as this
        # level's sky offset and subtract real flux from it. Leave those to the
        # interpolated fill, which shifts them by their neighbours' offset and
        # so preserves their structure.
        _, level_sigma = _robust_stats(detect[region_sky_mask])
        if not np.isfinite(level_sigma) or level_sigma > max_level_sigma:
            continue
        ch_offsets: list[float] = []
        ok = True
        for c in range(3):
            sky_pixels = out[..., c][region_sky_mask]
            sc_mean, sc_med, sc_std = sigma_clipped_stats(sky_pixels, sigma=3.0, maxiters=5)
            if not (np.isfinite(sc_mean) and np.isfinite(sc_med)):
                ok = False
                break
            mode_est = 2.5 * sc_med - 1.5 * sc_mean
            # If the skew is implausibly extreme, fall back to the median — the
            # SExtractor approximation only holds for mild positive skew. Its own
            # trust criterion (mean−median within 0.3·σ) is used here; the earlier
            # `abs(mode−med) > 5·abs(med−mean)` form was algebraically inert (that
            # is exactly `1.5·X > 5·X`, never true), so the backstop was dead.
            if (not np.isfinite(mode_est)
                    or (np.isfinite(sc_std) and sc_std > 0.0
                        and abs(sc_mean - sc_med) > 0.3 * sc_std)):
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
            # Coverage levels are often *gapped*: dense single-panel counts, then
            # a jump to the 2×/3× overlap counts, whose sky sample is far smaller.
            # A single global polynomial is dominated by the high-pixel-count
            # cluster and *extrapolates* its trend across the gap onto an isolated
            # (overlap) level — unbounded, that overrides a well-measured level
            # with a wildly wrong offset and subtracts a bright/dark seam over that
            # region: the very panel step this pass exists to remove. A physical
            # sky offset can't be more extreme than the most extreme value actually
            # *measured* across levels, so clamp the fitted value to the measured
            # envelope. It's a no-op for the normal interpolating fit (the existing
            # contiguous-level behaviour is byte-for-byte unchanged) but bounds the
            # gapped-extrapolation to the real per-level spread.
            lo, hi = float(np.min(ys)), float(np.max(ys))
            smoothed = np.clip(smoothed, lo, hi)
            for i, l in enumerate(lvls):
                offsets[int(l)][c] = float(smoothed[i])

    # Fill in the levels we *still* could not measure by interpolating the ones
    # we could. Leaving a level at "no offset" while its neighbours are pushed
    # to zero sky doesn't leave it alone in any meaningful sense — it leaves it
    # holding its full residual next to regions that no longer hold theirs, so
    # the pass manufactures a panel step (a coloured one, since the offsets are
    # per channel) exactly where it is supposed to remove one. An interpolated
    # neighbour offset is the best available estimate and, crucially, restores
    # continuity across the boundary. ``np.interp`` is linear between measured
    # levels and flat outside them, so a filled offset can never leave the
    # envelope of what was actually measured. Levels that *were* measured keep
    # their own (smoothed) value, so a stack in which every present level was
    # measurable — the ordinary single-field case — is byte-for-byte unchanged.
    # Only levels that cleared the pixel floor are filled: a sliver too small to
    # measure is also too small to be worth shifting, and stays untouched.
    measured = sorted(offsets)
    n_measured = len(measured)
    unmeasured = [lvl for lvl in big_levels if lvl not in offsets]
    if measured and unmeasured:
        xs = np.array(measured, dtype=np.float64)
        ys_per_channel = [
            np.array([offsets[m][c] for m in measured], dtype=np.float64)
            for c in range(3)
        ]
        targets = np.array(unmeasured, dtype=np.float64)
        filled = [np.interp(targets, xs, ys_per_channel[c]) for c in range(3)]
        for i, lvl in enumerate(unmeasured):
            offsets[lvl] = [float(filled[c][i]) for c in range(3)]

    # Second pass: subtract the (smoothed) per-channel offset from every pixel
    # at each coverage level. Objects shift by the same constant, so relative
    # brightness is preserved.
    n_leveled = 0
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
        "Coverage-leveling: equalised %d coverage levels (%d rescued by a "
        "level-local object threshold, %d filled from neighbouring levels); "
        "max shift applied = %.3f ADU",
        n_leveled, n_rescued, n_leveled - n_measured, max_shift,
    )
    return out
