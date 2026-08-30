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
import math
from dataclasses import dataclass

import numpy as np

log = logging.getLogger(__name__)

# Below this many *strided* sky pixels a per-level median is meaningless noise,
# so we never *measure* a level with fewer — even on a heavily-decimated proxy
# where scaling ``min_pixels_per_level`` down would otherwise reach into single
# digits. It is deliberately a floor on **measuring**, not on *considering*: a
# level that clears the export's own full-res-equivalent floor but not this one
# is still leveled, from its neighbours' interpolated offset (see
# ``include_min`` in :func:`_level_context`).
_MIN_STRIDED_PIXELS = 12

# A starved coverage level is only re-measured against its own statistics when
# it actually *looks* like sky: its own sigma-clipped spread must be no more
# than this multiple of the canvas-wide sky spread. Sky is flat; a region full
# of nebula or a galaxy is not, and re-measuring one of those would read the
# object's own level as "sky" and subtract real flux. The canvas-wide σ is
# itself inflated by the between-level offsets on a mosaic, so 3× is a generous
# bound that still rejects structured regions by orders of magnitude.
_RESCUE_MAX_SIGMA_RATIO = 3.0


# How much noisier a level's *sky-mode estimate* is than the plain standard
# error of its pixels. ``_sky_mode`` returns the SExtractor approximation
# ``2.5·median − 1.5·mean``, whose variance works out at ``4.57·σ²/n`` for
# Gaussian noise — i.e. ``2.14·σ/√n`` — and a direct measurement of
# :func:`_sky_mode` on Gaussian samples agrees (2.07–2.22 across n = 200…10000).
# Used to say how precisely a level's sky was actually pinned down, so
# :func:`measure_seam_residual` can tell a real step from the scatter of its own
# estimates.
_MODE_SE_FACTOR = 2.15

# How many standard errors of slack each level's sky estimate gets before a
# level-to-level difference counts as a *step*. The seam spread is a max−min
# over every measured level, and the max−min of K noisy estimates grows with K
# (≈ 3.1·SE at K = 10, ≈ 3.9·SE at K = 80) even when the true sky is identical
# everywhere — so without this the measurement reports its own estimator noise
# as a seam. Two SE per level covers that growth to well past the level count a
# real mosaic reaches, while costing a genuinely stepped level almost nothing:
# a level measured from thousands of sky pixels has an SE far below the grain,
# so the deduction is invisible on every scene this measurement was calibrated
# on.
_SEAM_SE_Z = 2.0


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


def _sky_mode(sky_pixels: np.ndarray) -> float | None:
    """The SExtractor sky-mode estimate (``2.5·median − 1.5·mean``) of a sky sample.

    Mode is robust to faint diffuse signal that would bias the plain median
    upward by a coverage-dependent amount — which is exactly the residual bias
    that re-emerges as panel steps after stretching. If the skew is implausibly
    extreme the approximation no longer holds, so it falls back to the median;
    its own trust criterion (mean−median within 0.3·σ) decides. Returns ``None``
    when the sample has no usable statistics at all, so the caller can skip the
    level rather than shift it by a nonsense offset.
    """
    from astropy.stats import sigma_clipped_stats

    sc_mean, sc_med, sc_std = sigma_clipped_stats(sky_pixels, sigma=3.0, maxiters=5)
    if not (np.isfinite(sc_mean) and np.isfinite(sc_med)):
        return None
    mode_est = 2.5 * sc_med - 1.5 * sc_mean
    # The earlier `abs(mode−med) > 5·abs(med−mean)` form was algebraically inert
    # (that is exactly `1.5·X > 5·X`, never true), so the backstop was dead.
    if (not np.isfinite(mode_est)
            or (np.isfinite(sc_std) and sc_std > 0.0
                and abs(sc_mean - sc_med) > 0.3 * sc_std)):
        mode_est = sc_med
    return float(mode_est)


@dataclass(frozen=True)
class _LevelContext:
    """The per-coverage-level bookkeeping both this module's passes share.

    Building it is the expensive half of the work (one canvas-wide object mask
    plus locating statistics per level), and both :func:`level_by_coverage` and
    :func:`measure_seam_residual` need exactly the same view of the canvas — so
    the "which pixels belong to which level, and which of them are sky" question
    is answered once, here, and the two passes differ only in what they do with
    the answer.
    """

    cov_int: np.ndarray        # per-pixel integer coverage level
    valid_pix: np.ndarray      # covered AND finite
    big_levels: list[int]      # levels with enough pixels to be worth correcting
    luma: np.ndarray           # raw luminance (what a level-local rescue re-thresholds)
    detect: np.ndarray         # luminance the object mask was measured on
    object_mask: np.ndarray    # stars/nebulosity — excluded from every sky sample
    max_level_sigma: float     # above this spread a level is structure, not sky
    # Floor on *measuring* a level's own sky median. The separate, lower floor on
    # *considering* a level at all (the export-equivalent count) is applied when
    # ``big_levels`` is built — see :func:`_level_context`.
    effective_min: int


def _level_context(
    img: np.ndarray,
    coverage: np.ndarray,
    frame_coverage: np.ndarray | None,
    object_sigma: float,
    min_pixels_per_level: int,
    dilate_object_mask_px: int,
    proxy_scale: float,
) -> _LevelContext | None:
    """Bin ``img`` by coverage level and locate its sky, or ``None`` if it can't.

    ``None`` means there is nothing to measure at all — an all-NaN canvas, no
    covered pixels, or degenerate luminance statistics — and every caller should
    then leave the image exactly as it found it.
    """
    from astropy.stats import sigma_clipped_stats
    from scipy.ndimage import binary_dilation

    # Select the *same set* of coverage levels the full-res export would, by
    # gating on the full-resolution-equivalent pixel count: a strided proxy pixel
    # stands in for ``step²`` full-res pixels, so scale the floor by 1/step².
    step = max(1, int(round(float(proxy_scale))))
    include_min = max(1, int(round(min_pixels_per_level / (step * step))))
    # ...but never *measure* a level's own sky median from a handful of pixels:
    # a median over 3 samples is noise, whatever it stands in for. On a heavily
    # decimated proxy (step ≥ 5, i.e. a canvas over ~7500 px — a big mosaic) the
    # two part company, and the gap used to be silent divergence: a level that
    # cleared the export's floor but not this one dropped out of ``big_levels``
    # entirely, so the preview neither measured **nor filled** it while the export
    # leveled it — the panel kept its whole residual in the preview only. Keeping
    # it *included* but unmeasurable routes it to the interpolated fill below,
    # which is exactly what the export does for a level it can't measure either.
    # At step ≤ 4 the two floors coincide, so the ordinary path is unchanged.
    effective_min = max(_MIN_STRIDED_PIXELS, include_min)

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
    luma = (0.299 * img[..., 0] + 0.587 * img[..., 1]
            + 0.114 * img[..., 2]).astype(np.float32, copy=False)
    finite = np.isfinite(luma)
    if not finite.any():
        return None

    # Bin coverage values. ``cov2d`` is the true integer frame count when the
    # caller passed ``frame_coverage`` (already integral); on the fallback path
    # it's the Σ-weight map, so round to the nearest integer — the
    # **integer-rounded** bin is what carries the visible panel structure.
    # (Binned *before* the object mask: the threshold below is measured per
    # coverage level, so it needs the bins.)
    cov_int = np.rint(cov2d).astype(np.int32, copy=False)
    valid_pix = (cov_int > 0) & finite
    if not valid_pix.any():
        return None

    # Every coverage value actually present on the canvas — taken over
    # ``valid_pix`` rather than the sky mask so a level the object mask has
    # entirely swallowed is still *considered* (and rescued below) instead of
    # dropping out of the list unnoticed.
    levels, region_counts = np.unique(cov_int[valid_pix], return_counts=True)
    # The levels big enough to be worth correcting at all — gated on the
    # export-equivalent count, so the preview considers exactly the levels the
    # full-res export does at any stride. A coverage value covering fewer than
    # that in *total* is a sliver, not a panel: it carries no reliable median,
    # and it is left untouched — neither measured nor filled — exactly as it
    # always has been.
    big_levels = [
        int(lv) for lv, n in zip(levels, region_counts)
        if lv > 0 and n >= include_min
    ]

    _, med, std = sigma_clipped_stats(luma, mask=~finite, sigma=3.0, maxiters=5)
    if not (np.isfinite(med) and np.isfinite(std) and std > 0):
        return None

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

    return _LevelContext(
        cov_int=cov_int,
        valid_pix=valid_pix,
        big_levels=big_levels,
        luma=luma,
        detect=detect,
        object_mask=object_mask,
        max_level_sigma=_RESCUE_MAX_SIGMA_RATIO * sky_sigma,
        effective_min=effective_min,
    )


def _level_sky_mask(
    ctx: _LevelContext,
    level: int,
    object_sigma: float,
    dilate_object_mask_px: int,
) -> tuple[np.ndarray, bool] | None:
    """One coverage level's sky pixels + whether a rescue found them.

    ``None`` when the level has no usable sky at all. Applies the same two
    guards both passes need: a level the canvas-wide object threshold has
    *starved* is re-thresholded against its own statistics (see
    :func:`_local_sky_mask`), and a level whose retained sample is far more
    spread out than the canvas's own sky is refused outright — it is filled by
    real structure, and reading an object's level as a sky offset would subtract
    real flux.
    """
    region_mask = (ctx.cov_int == level) & ctx.valid_pix
    region_sky_mask = region_mask & ~ctx.object_mask
    rescued_level = int(region_sky_mask.sum()) < ctx.effective_min
    if rescued_level:
        # The global object threshold has starved this level's sky sample.
        # Most often that is not because the region *is* an object but
        # because its residual sky sits above the canvas-wide median + σ —
        # the offset the leveling pass exists to subtract. Re-threshold it
        # against its own statistics before giving up; a level that already had
        # enough sky pixels never reaches here, so nothing that is leveled today
        # changes.
        rescued = _local_sky_mask(
            ctx.luma, region_mask, object_sigma, dilate_object_mask_px,
            ctx.max_level_sigma)
        if rescued is None or int(rescued.sum()) < ctx.effective_min:
            return None
        region_sky_mask = rescued
    # The retained sample has to look like sky before we call its mode a sky
    # level. A coverage region genuinely *filled* by a galaxy or nebula leaves
    # behind a sample far more spread out than the canvas's own retained sky.
    _, level_sigma = _robust_stats(ctx.detect[region_sky_mask])
    if not np.isfinite(level_sigma) or level_sigma > ctx.max_level_sigma:
        return None
    return region_sky_mask, rescued_level


@dataclass(frozen=True)
class SeamResidual:
    """How flat a mosaic's panel joins actually came out, measured on the result.

    ``ratio`` is the number that matters: the worst channel's remaining
    level-to-level sky spread expressed in units of that channel's own noise. A
    coherent step of about the grain's size is where a seam starts to become
    visible once the picture is stretched, so ``ratio`` around 1 is the
    interesting scale; a well-flattened mosaic measures a small fraction of it.
    It is unit-free by construction, so it means the same thing whatever the
    stack's exposure, gain or normalisation: rescaling the picture moves the
    step and the grain together and leaves the number exactly where it was.

    ``spread_adu`` is the step the levels are *confidently* apart by: each
    level's sky estimate carries its own standard error, and only the part of
    the max−min that survives that slack is reported (see ``_SEAM_SE_Z``). On a
    deep, heavily-dithered mosaic the coverage map ramps through dozens of thin,
    low-coverage levels whose sky is both the noisiest and the least sampled, so
    without the deduction their scatter alone reads as a seam that grows with
    the sub count.
    """

    n_levels: int        # coverage levels the measurement could actually read
    spread_adu: float    # worst channel's max−min sky level across those levels
    noise_sigma: float   # that same channel's sky noise σ
    ratio: float         # spread_adu / noise_sigma


def measure_seam_residual(
    rgb: np.ndarray,
    coverage: np.ndarray,
    *,
    frame_coverage: np.ndarray | None = None,
    object_sigma: float = 2.0,
    min_pixels_per_level: int = 200,
    dilate_object_mask_px: int = 4,
    proxy_scale: float = 1.0,
) -> SeamResidual | None:
    """Measure the panel-seam step a *finished* mosaic still carries.

    :func:`level_by_coverage` pushes every coverage level's sky to zero, but it
    cannot always succeed: a level whose sky sample is unreadable takes a
    neighbour's interpolated offset, and a level filled by real structure is
    deliberately left alone. Nothing downstream checks whether the panels
    actually came out flat — the one mosaic failure mode a beginner can *see*
    but not diagnose — so this measures it on the result and hands back a
    number the app can say out loud.

    Run it on the image **after** leveling (and after any final gradient pass),
    with the same coverage map. Returns ``None`` whenever there is nothing
    meaningful to report: a single-coverage-level (ordinary single-field) stack
    has no joins to compare, and a canvas whose levels can't be measured says
    nothing rather than guessing.
    """
    img = np.asarray(rgb, dtype=np.float32)
    ctx = _level_context(
        img, coverage, frame_coverage, object_sigma, min_pixels_per_level,
        dilate_object_mask_px, proxy_scale)
    # One level is a single-field stack: no join, nothing to compare, no verdict.
    if ctx is None or len(ctx.big_levels) < 2:
        return None

    per_level: dict[int, list[float]] = {}
    per_level_sigma: dict[int, list[float]] = {}
    per_level_n: dict[int, int] = {}
    for level in ctx.big_levels:
        found = _level_sky_mask(ctx, level, object_sigma, dilate_object_mask_px)
        if found is None:
            continue
        region_sky_mask, _rescued = found
        skies = [_sky_mode(img[..., c][region_sky_mask]) for c in range(3)]
        if any(s is None or not np.isfinite(s) for s in skies):
            continue
        per_level[level] = [float(s) for s in skies]  # type: ignore[arg-type]
        per_level_sigma[level] = [
            _robust_stats(img[..., c][region_sky_mask])[1] for c in range(3)]
        # How many sky pixels that estimate rests on — the other half of its
        # standard error, and the reason a thin dither-ramp level must not be
        # allowed to set the spread on its own.
        per_level_n[level] = int(region_sky_mask.sum())

    # Two readable levels is the minimum for a *difference* to exist at all.
    if len(per_level) < 2:
        return None

    worst: tuple[float, float, float] | None = None
    for c in range(3):
        # The step the levels are *confidently* apart by. A plain max−min over
        # the per-level sky modes charges every level's own estimation noise to
        # the seam, and that noise is neither small nor even: a deep mosaic's
        # coverage map ramps from 1 frame at the fringe to hundreds in a panel
        # body, so the thin low-coverage levels carry ~√N times the grain of the
        # deep ones on a fraction of the pixels. Their scatter alone then reads
        # as a step — one that *grows* with the sub count while the yardstick
        # (the median level's grain) shrinks, which is how a perfectly flat
        # mosaic came to measure 0.27 grain-widths at 4 subs a panel and 1.56 at
        # 128 (past the "faint seams may show" bar). Giving each level's
        # estimate its own ± slack and taking the largest gap between those
        # intervals reports only what the noise can't explain. On a level
        # measured from thousands of sky pixels the slack is a small fraction of
        # the grain, so a real seam is untouched.
        his: list[float] = []
        los: list[float] = []
        for lvl, vals_c in per_level.items():
            v = float(vals_c[c])
            sig_l = per_level_sigma[lvl][c]
            n_l = per_level_n[lvl]
            se = (_MODE_SE_FACTOR * float(sig_l) / math.sqrt(n_l)
                  if np.isfinite(sig_l) and sig_l > 0 and n_l > 0 else 0.0)
            his.append(v - _SEAM_SE_Z * se)
            los.append(v + _SEAM_SE_Z * se)
        spread = max(0.0, float(max(his) - min(los)))
        # The yardstick is the grain *within* a level, taken as the median of the
        # per-level spreads — not the canvas-wide σ. A canvas-wide σ is itself
        # inflated by the very level-to-level offsets being measured, so on the
        # badly-seamed stack this check exists to catch it would quietly deflate
        # the ratio towards 1 and understate the problem.
        sigmas = [s[c] for s in per_level_sigma.values()
                  if np.isfinite(s[c]) and s[c] > 0]
        if not sigmas:
            continue
        sigma_c = float(np.median(sigmas))
        ratio = spread / sigma_c
        if worst is None or ratio > worst[0]:
            worst = (ratio, spread, sigma_c)
    if worst is None:
        return None

    ratio, spread, sigma = worst
    log.info(
        "Seam residual: %d coverage levels, worst channel spread %.4f on noise "
        "σ %.4f (%.2f×)", len(per_level), spread, sigma, ratio,
    )
    return SeamResidual(
        n_levels=len(per_level), spread_adu=spread, noise_sigma=sigma, ratio=ratio,
    )


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

        Beyond ~×4 the scaled floor would drop below the handful of pixels a
        median needs, so measuring stops there (``_MIN_STRIDED_PIXELS``) — but
        *considering* the level does not: a level that clears the export's
        full-res-equivalent floor without clearing the measurement floor is
        given its neighbours' interpolated offset, exactly as the export does
        for a level whose sky it cannot read. A level below the
        export-equivalent floor is a genuine sliver and stays untouched at every
        stride.
    """
    out = rgb.astype(np.float32, copy=True)

    ctx = _level_context(
        out, coverage, frame_coverage, object_sigma, min_pixels_per_level,
        dilate_object_mask_px, proxy_scale)
    if ctx is None:
        return out
    cov_int, valid_pix, big_levels = ctx.cov_int, ctx.valid_pix, ctx.big_levels

    # First pass: compute the per-channel SKY MODE for each coverage level
    # using the SExtractor approximation (2.5·median − 1.5·sigma-clipped-mean).
    # Mode is robust to faint diffuse signal that would bias the plain median
    # upward by a coverage-dependent amount (which is exactly the residual
    # bias that re-emerges as panel steps after stretching).
    offsets: dict[int, list[float]] = {}  # level -> [R_off, G_off, B_off]
    sky_counts: dict[int, int] = {}
    n_rescued = 0
    for level in big_levels:
        # A starved level is re-thresholded against its own statistics, and a
        # level too structured to be sky is refused outright — both handled by
        # ``_level_sky_mask``, so the leveling pass and the seam-residual check
        # can never disagree about which levels are measurable.
        found = _level_sky_mask(ctx, level, object_sigma, dilate_object_mask_px)
        if found is None:
            # Unmeasurable: left to the interpolated fill below, which shifts it
            # by its neighbours' offset and so preserves whatever structure
            # filled it.
            continue
        region_sky_mask, was_rescued = found
        if was_rescued:
            n_rescued += 1
        n_sky = int(region_sky_mask.sum())
        ch_offsets: list[float] = []
        ok = True
        for c in range(3):
            mode_est = _sky_mode(out[..., c][region_sky_mask])
            if mode_est is None:
                ok = False
                break
            ch_offsets.append(mode_est)
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
    # The fitted trend per channel, kept so the fill below can put an
    # *unmeasurable* level on the very same curve the measured levels were moved
    # onto. ``(coeffs, lo, hi)``, or None when no fit was made (too few measured
    # levels, smoothing off, or a degenerate fit) — the fill then falls back to a
    # straight interpolation between neighbours.
    fitted: list[tuple[np.ndarray, float, float] | None] = [None, None, None]
    if smooth_across_levels and len(offsets) >= 3:
        lvls = np.array(sorted(offsets.keys()), dtype=np.float32)
        weights = np.array([sky_counts[int(l)] for l in lvls], dtype=np.float32)
        for c in range(3):
            ys = np.array([offsets[int(l)][c] for l in lvls], dtype=np.float32)
            # Quadratic fit weighted by sky-pixel count — flexible enough for
            # the usual gentle dependence but won't chase per-level noise.
            coeffs: np.ndarray | None
            try:
                coeffs = np.polyfit(lvls, ys, deg=2, w=weights)
                smoothed = np.polyval(coeffs, lvls)
            except (np.linalg.LinAlgError, ValueError):
                coeffs, smoothed = None, ys
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
            if coeffs is not None:
                fitted[c] = (coeffs, lo, hi)
            for i, l in enumerate(lvls):
                offsets[int(l)][c] = float(smoothed[i])

    # Fill in the levels we *still* could not measure by interpolating the ones
    # we could. Leaving a level at "no offset" while its neighbours are pushed
    # to zero sky doesn't leave it alone in any meaningful sense — it leaves it
    # holding its full residual next to regions that no longer hold theirs, so
    # the pass manufactures a panel step (a coloured one, since the offsets are
    # per channel) exactly where it is supposed to remove one. A neighbour-derived
    # offset is the best available estimate and, crucially, restores continuity
    # across the boundary.
    #
    # It is taken from the **same curve the measured levels were moved onto**.
    # Sky-vs-coverage is a single physical trend, so evaluating the fitted
    # quadratic at the gap keeps every level on one curve; a separate straight
    # line between neighbours would land a filled level slightly off it wherever
    # that trend is curved — a small low-frequency inconsistency tracing exactly
    # the coverage map this pass exists to erase. (Measured on a synthetic
    # quadratic sky-vs-level trend with level 4 unmeasurable: the straight line
    # gives 125.6 against a true 124.8 — 0.8 ADU on a 1.5 ADU noise floor — while
    # the fitted curve lands on 124.8.) The fitted value is clamped to the same
    # measured envelope the smoothed levels are, so a filled offset still can
    # never leave the range actually measured, and a gap outside that range can't
    # extrapolate a seam into existence.
    #
    # When no fit was made — smoothing off, fewer than three measured levels, or
    # a degenerate fit — there is no curve to sit on, and the fill falls back to
    # ``np.interp``: linear between measured levels and flat outside them, which
    # is likewise inside the measured envelope.
    #
    # Levels that *were* measured keep their own (smoothed) value either way, so
    # a stack in which every present level was measurable — the ordinary
    # single-field case — is byte-for-byte unchanged. Only levels that cleared
    # the pixel floor are filled: a sliver too small to measure is also too small
    # to be worth shifting, and stays untouched.
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
        filled = []
        for c in range(3):
            fit = fitted[c]
            if fit is not None:
                coeffs, lo, hi = fit
                filled.append(np.clip(np.polyval(coeffs, targets), lo, hi))
            else:
                filled.append(np.interp(targets, xs, ys_per_channel[c]))
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
