"""Largest well-covered rectangle for one-click mosaic-border trimming.

A Seestar mosaic's union canvas has ragged, low-coverage edges — corners touched
by a single frame, NaN gaps where no frame reached — that look messy and are
noisier than the well-covered interior. This module finds the largest
axis-aligned rectangle whose pixels are all *well covered* (per-pixel frame
coverage at or above a fraction of the peak), so the editor can offer a single
"Trim to well-covered area" button that sets a ``geometry.crop`` op to that
rectangle. It's a pure geometry helper (no I/O); the coverage map is loaded and
downsampled by the caller.
"""

from __future__ import annotations

import numpy as np

# Below this coverage fraction of the reference depth a pixel is treated as
# fringe/uncovered. (Of the *reference*, not the peak — see `panel_coverage_level`.)
DEFAULT_MIN_FRAC = 0.5
# A coverage level must span at least this fraction of the covered area to count
# as a genuine panel plateau (rather than a thin reprojection-border ramp step)
# when classifying a run as a mosaic from its coverage distribution.
MOSAIC_LEVEL_MIN_FRAC = 0.08
# The same "is this a real plateau or a border ramp step?" floor, used to pick the
# reference depth in `panel_coverage_level`. Deliberately its own name rather than
# a reuse of the constant above: they answer different questions (is this a mosaic
# at all? vs. how deep is one panel?) and a future run should be able to tune one
# without silently moving the other.
PANEL_LEVEL_MIN_FRAC = 0.08
# How wide a plateau is allowed to be, as a fraction of its own level, before it
# stops being one level. Coverage is a sum of *weights*, not a frame count, once
# quality weighting is on, so a 30-sub panel reads as 30±jitter and exact-integer
# bucketing would shatter it. Two coverage levels that matter here are a factor of
# two apart (one panel vs. two overlapping panels), so 10 % cannot merge them.
PANEL_LEVEL_TOL = 0.10
# …and a level must also be this many pixels, not just this fraction of them. On a
# map of a few dozen covered pixels the fraction above rounds down to "one pixel is
# a plateau", which is an artefact of the sample size rather than a statement about
# the picture. Below this the function declines to have an opinion and the peak
# stands — i.e. small and legacy maps keep exactly the behaviour they have today.
# A real coverage map is read strided to ~10^5-10^6 pixels, where 8 % of it is
# three orders of magnitude above this floor, so it never binds in production.
PANEL_LEVEL_MIN_PIXELS = 256
# The same "is this a real plateau?" floor once more, for the **mask** rather than
# the trim — and lower, because the two are asked about mosaics of different sizes.
#
# `PANEL_LEVEL_MIN_FRAC` calls a level substantial at 8 % of the covered canvas,
# which is one panel of a *twelve*-panel mosaic. The owner shoots 5x5, 10x10 and
# 12x8 rasters across many nights, where one panel is 1-4 % of the canvas and no
# panel's depth is ever that substantial — so `panel_coverage_level` walks past
# every thin panel and settles near the **mode** of the depth distribution, and
# `well_covered_mask` then calls everything below half of that fringe. On a fully
# tiled canvas, with no ragged edge anywhere.
#
# The trim has a second line of defence against exactly this (the coverage-bound
# ladder in `largest_covered_rect`, see TRIM_KEEP_RATIO) because it has a
# *rectangle* to compare against the one the coverage alone allows. A per-pixel
# mask has no such comparison: the honest fade and the broken one both simply
# remove area, and on real map shapes they overlap outright (a genuinely ragged
# 2x2 fades 8.2 % of its canvas; a broken 12x8 fades 11.4 %). So the mask is fixed
# at the reference instead, which is the only lever it has — and a safe one:
# `panel_coverage_level` is monotone in this fraction (lowering it can only widen
# the set of qualifying windows, so the level can only fall), and a lower level
# can only keep *more* of the picture. The worst case of this constant is leaving
# fringe in, never fading a panel away.
#
# Measured on the integer frame-count maps the mask actually reads (the
# `_framecov.fits` sibling — *not* the weighted coverage), over 147 fully tiled
# rasters (3x3 … 12x8, panel depths spanning 3-15 up to 50-500 subs, three seeds
# each), as the worst share of a **fully covered** canvas faded away:
#
#     min_frac   rasters affected   worst faded
#       0.08          90 of 147        26.3 %
#       0.04          10 of 147        12.8 %
#       0.03           0 of 147         0.0 %
#
# …and what it costs, on the shapes that have a real fringe to fade: **nothing
# measurable**. A single field with a dither ramp fades 2.50 % of its canvas
# before and after, and a genuinely ragged 2x2 mosaic 8.17 % before and after —
# identical, because on those shapes one level does hold 8 % of the canvas and
# the reference does not move at all. A raster that is *both* many-panelled and
# genuinely ragged fades 11.2 % rather than 22.1 %: it loses its border, and
# keeps its thin panels. The only shape where the fade shrinks to nothing is a
# heavily dithered (±80 px) single field, 1.6 % -> 0.0 %, and that is the safe
# direction — an unweighted stack writes no frame-count sibling at all, so
# `stack_detail_mask` already falls back to the plain has-data footprint and
# fades nothing whatever for it.
#
# Below ~0.02 the reference starts landing on the dither ramp itself and the
# ragged fades erode too (a ragged 12x8 goes 5.4 % -> 3.7 %), so 0.03 is not the
# bottom of a slope: it is the middle of the band between the two failures.
MASK_LEVEL_MIN_FRAC = 0.03


def coverage_is_mosaic(coverage: np.ndarray,
                       min_frac: float = MOSAIC_LEVEL_MIN_FRAC) -> bool:
    """Whether a per-pixel frame-coverage map came from a *mosaic* stack.

    A single-field stack has essentially one interior coverage plateau (every
    frame covers the whole field), with only a thin ramp of lower values along the
    reprojection border. A mosaic's panels overlap unevenly, so its coverage map
    has **two or more** large plateaus at distinct integer levels. We call it a
    mosaic when at least two distinct *covered* levels each span ``min_frac`` of
    the covered area — robust to the thin border ramp (each ramp step is tiny) and
    to NaN/uncovered pixels.

    This is the fallback the editor uses for legacy runs recorded before the
    stacker's authoritative ``is_mosaic`` flag was persisted. It replaces the old
    ``coverage_max > coverage_min`` test, which is ~always true (the reprojection
    border is uncovered, so the minimum is 0) and so mislabelled single-field
    stacks as mosaics.

    **Known false negative, deliberately left (2026-09-08).** "Two levels each
    spanning 8 % of the covered area" is a *sparse* mosaic's shape. A dense one
    dilutes it: a 3x3 at 5 % overlap and a 12x8 raster with uneven panel depth
    both return False, because no single level reaches 8 % once the depth is
    spread across a dozen of them. That is a real miss, and it is not widened
    here on purpose — this function is reached **only** for runs recorded before
    the stacker persisted ``is_mosaic`` (schema < 8), which no run the owner's
    install has made in a long time, and loosening the floor on the classifier
    that decides whether the editor treats a picture as a mosaic is a behaviour
    change to legacy runs bought for nothing. If a future change ever puts this
    back on a live path, the honest test is the one D1 settled on — a mosaic is a
    map whose :func:`panel_coverage_level` sits meaningfully below its peak — not
    a lower ``min_frac``.
    """
    cov = np.asarray(coverage)
    if cov.ndim == 3:
        cov = cov[..., 0]
    cov = cov[np.isfinite(cov)]
    covered = cov[cov > 0]
    if covered.size == 0:
        return False
    _levels, counts = np.unique(np.rint(covered).astype(np.int64), return_counts=True)
    fracs = counts / float(covered.size)
    return int(np.count_nonzero(fracs >= min_frac)) >= 2
# If the best rectangle already spans essentially the whole frame there's nothing
# worth trimming, so we return None (no crop) rather than a no-op crop.
_FULL_AREA_FRAC = 0.985

# How much of what the *coverage itself* allows the depth threshold may give up
# before it has stopped trimming a border and started discarding panels.
#
# This is the second half of D1, and it is a different failure from the first.
# D1 was "the reference is the peak"; :func:`panel_coverage_level` fixed that by
# taking the lowest *substantial* plateau instead. But "substantial" means 8 % of
# the covered canvas, and on a **dense raster with uneven panel depth** — the
# owner shoots 3x3 and 12x8, over many nights, so his panels are not equally deep
# — no single depth holds 8 % of anything: 96 panels spread across two dozen
# depths, each holding ~1 %. The search then walks past the thin panels and lands
# near the *mode*, and every panel shallower than half of that is declared fringe.
# Measured, before this guard: a 12x8 raster 8-30 subs deep with 6 % weight jitter
# was cropped to **25.6 %** of its canvas, a 6x4 to 34.8 %, an 8x6 to 17.6 %. All
# three are fully tiled — there is no ragged edge to trim at all — and AGENTS.md
# §1 puts the bar at "a trim above ~15 % of the canvas is a bug, not a ragged
# edge".
#
# The discriminator is what the discarded pixels *are*. A border is **uncovered**
# (no frame reached it) plus the thin fringe beside it; a thin panel is covered —
# real data, fewer subs. So the coverage alone fixes an upper bound on how much a
# border trim can honestly remove, and a depth threshold that does far worse than
# that bound is not describing a border. When one does, the threshold is walked
# down (each rung halves it) until it agrees with the coverage again — which on a
# raster that is *both* uneven and genuinely ragged still trims the ragged edge
# (measured: 34.2 % kept -> 95.1 %) instead of standing down altogether.
#
# Chosen, not tuned: every honest shape in this module's tests keeps within 5 % of
# its coverage bound (single field 92.2 % vs 100 %... a diagonal mosaic 12.2 % vs
# 12.2 %), and the broken ones are 3-5x below it, so anything from ~0.5 to ~0.9
# separates them identically. 0.8 sits in the middle of that gap.
TRIM_KEEP_RATIO = 0.8
# Eight halvings reach 1/256 of one panel's depth, below which every covered pixel
# passes and the rule has become the coverage itself — the bound it is converging
# on. Bounded so this can never loop on a pathological map.
_TRIM_LADDER_RUNGS = 8


def _largest_hist_rect(heights: np.ndarray, base_row: int):
    """Largest rectangle in a 1-D histogram, as ``(r0, c0, r1, c1, area)``.

    ``heights[c]`` is how many consecutive covered rows end at ``base_row`` in
    column ``c`` (the bar rising upward from the base). The returned rectangle is
    half-open in both axes (rows ``[r0, r1)``, cols ``[c0, c1)``). Classic
    monotone-stack sweep, O(w).
    """
    stack: list[int] = []  # indices of strictly-increasing bar heights
    best_area = 0
    best = None
    n = len(heights)
    for i in range(n + 1):
        cur = int(heights[i]) if i < n else 0
        while stack and int(heights[stack[-1]]) >= cur:
            top = stack.pop()
            height = int(heights[top])
            left = stack[-1] + 1 if stack else 0
            width = i - left
            area = height * width
            if height > 0 and area > best_area:
                best_area = area
                best = (base_row - height + 1, left, base_row + 1, i)
        stack.append(i)
    if best is None:
        return None
    return (*best, best_area)


def _max_rectangle(mask: np.ndarray):
    """Largest all-True axis-aligned rectangle in a 2-D boolean mask, as
    ``(r0, c0, r1, c1)`` half-open, or ``None`` when the mask is empty."""
    h, w = mask.shape
    heights = np.zeros(w, dtype=np.int64)
    best_area = 0
    best = None
    for r in range(h):
        row = mask[r]
        heights = np.where(row, heights + 1, 0)
        res = _largest_hist_rect(heights, r)
        if res is not None and res[4] > best_area:
            best_area = res[4]
            best = res[:4]
    return best


def panel_coverage_level(covered: np.ndarray,
                         min_frac: float = PANEL_LEVEL_MIN_FRAC,
                         tol: float = PANEL_LEVEL_TOL) -> float | None:
    """How deep **one panel** is, from the covered pixels' own distribution.

    This exists because "a fraction of the **peak**" is the wrong reference on a
    mosaic, and was wrong from the first version of this module. On a single field
    the peak *is* the interior — every frame covers the whole field — so half of it
    correctly trims the dithered fringe. On a tiled mosaic the peak is where panels
    **overlap**: two overlapping panels are 2× a panel's depth and four are 4×, so
    "half the peak" sits *above every panel interior* and the only "well covered"
    region is the overlap band. Measured on a 2×2 mosaic (4 panels × 30 subs, 15 %
    overlap) the old rule kept **8 %** of the canvas — a horizontal strip through
    the middle — and on a 3×3 at 5 % overlap, **1.7 %**.

    The honest reference is therefore the depth of a *typical panel*, which is the
    **lowest** coverage level that a real share of the canvas actually sits at:

    * a **single field** has exactly one such level — the interior plateau, which
      *is* the peak — so this returns the peak and the rule is **byte-for-byte
      what it always was**. The reprojection border's ramp steps are each a
      fraction of a percent of the covered area and never qualify.
    * a **mosaic** has several (one panel, two overlapping, four overlapping); the
      lowest is one panel, which is exactly the depth the trim should keep.
    * a mosaic whose panels differ in depth (400 subs on one, 150 on the other)
      has both as levels, and the lowest is the *thinner* panel — so it stops
      being discarded whole.

    Levels are found by relative tolerance rather than by exact integer value:
    coverage is a sum of per-frame *weights* once quality weighting is on, so a
    30-sub panel reads as 30 ± jitter and integer bucketing would shatter it.

    ``covered`` is the finite, strictly-positive coverage values (any shape; it is
    flattened). Returns ``None`` when there are none, and falls back to the peak
    when no level is substantial enough to name — i.e. when this function has no
    opinion, the old behaviour stands. **It can only ever return a value at or
    below the peak**, so it can only ever lower the threshold and keep *more* of
    the picture: the worst case of this rule is leaving fringe in, never trimming
    a panel away.
    """
    vals = np.sort(np.asarray(covered, dtype=np.float64).ravel())
    n = vals.size
    if n == 0:
        return None
    peak = float(vals[-1])
    need = max(PANEL_LEVEL_MIN_PIXELS, int(np.ceil(min_frac * n)))
    if need > n:
        return peak
    # A plateau is `need` consecutive sorted values that all sit within `tol` of
    # each other — i.e. that many pixels share one level. Vectorised: compare each
    # window's ends. The lowest such window is the thinnest real panel.
    lo = vals[: n - need + 1]
    hi = vals[need - 1:]
    tight = np.flatnonzero(hi - lo <= tol * np.maximum(hi, 1e-12))
    if tight.size == 0:
        return peak
    start = int(tight[0])
    # Take the level as the median of everything within `tol` of that window's
    # foot, so jitter around the plateau doesn't bias it toward either end.
    stop = int(np.searchsorted(vals, vals[start] * (1.0 + tol), side="right"))
    level = float(np.median(vals[start:max(stop, start + 1)]))
    return min(level, peak) if level > 0 else peak


def _coverage_threshold(coverage: np.ndarray,
                        min_frac: float = DEFAULT_MIN_FRAC,
                        *, level_min_frac: float | None = None) -> float | None:
    """The coverage value at or above which a pixel is "well covered", or ``None``
    when the map has no opinion to offer (non-2-D, empty, nothing finite/positive).

    Factored out of :func:`well_covered_mask` so :func:`largest_covered_rect` can
    walk the same number *down* without re-deriving the reference depth by hand.

    ``level_min_frac`` overrides how substantial a coverage level has to be before
    :func:`panel_coverage_level` will call it a panel. ``None`` — every caller but
    the mask — is :data:`PANEL_LEVEL_MIN_FRAC`, i.e. unchanged; see
    :data:`MASK_LEVEL_MIN_FRAC` for why the mask asks for a lower one.
    """
    cov = np.asarray(coverage, dtype=np.float32)
    if cov.ndim != 2 or cov.size == 0:
        return None
    finite = cov[np.isfinite(cov)]
    if finite.size == 0:
        return None
    peak = float(finite.max())
    if peak <= 0:
        return None
    reference = panel_coverage_level(
        finite[finite > 0],
        min_frac=(PANEL_LEVEL_MIN_FRAC if level_min_frac is None
                  else float(level_min_frac)))
    if reference is None or not (reference > 0):
        reference = peak
    frac = min(0.95, max(0.05, float(min_frac)))
    return frac * reference


def _rect_from_mask(mask: np.ndarray | None):
    """Fractional ``(x0, y0, x1, y1)`` of the largest all-True rectangle, or
    ``None`` for "keep the whole picture" — a uniform mask, an empty one, a
    degenerate rectangle, or one already spanning essentially the whole frame."""
    if mask is None or mask.all() or not mask.any():
        return None
    rect = _max_rectangle(mask)
    if rect is None:
        return None
    r0, c0, r1, c1 = rect
    h, w = mask.shape
    if (r1 - r0) < 2 or (c1 - c0) < 2:
        return None  # degenerate
    if (r1 - r0) * (c1 - c0) >= _FULL_AREA_FRAC * h * w:
        return None  # already spans the whole frame — nothing worth trimming
    return (c0 / w, r0 / h, c1 / w, r1 / h)


def _rect_area(rect) -> float:
    """Fraction of the canvas a rectangle keeps; ``None`` (no trim) keeps it all."""
    if rect is None:
        return 1.0
    return (rect[2] - rect[0]) * (rect[3] - rect[1])


def well_covered_mask(coverage: np.ndarray,
                      min_frac: float = DEFAULT_MIN_FRAC,
                      *, level_min_frac: float | None = None) -> np.ndarray | None:
    """Boolean mask of the pixels a coverage map calls **well covered**: finite,
    and at or above ``min_frac`` of **one panel's** coverage depth.

    This is the one place the "enough frames landed here to trust this pixel"
    rule lives. :func:`largest_covered_rect` reduces it to a rectangle for the
    editor's one-click border trim; the all-sky "My map" uses the mask itself, so
    a mosaic's ragged fringe fades out instead of smearing across the sky. Returns
    ``None`` for a non-2-D / empty map or one with no finite, positive coverage,
    which callers read as "no opinion — keep everything".

    The reference is :func:`panel_coverage_level`, **not** the map's peak — on a
    mosaic the peak is the panel *overlap* band, so measuring against it threw the
    panel interiors away. On a single field the two are the same number, so that
    path is unchanged.

    ``level_min_frac`` chooses how substantial a coverage level has to be before it
    counts as a panel. It exists because on a *many-panel* raster no single depth
    holds :data:`PANEL_LEVEL_MIN_FRAC` of the canvas, so the reference lands near
    the depth distribution's mode and whole thin panels are called fringe — see
    :data:`MASK_LEVEL_MIN_FRAC`, which is what :func:`seestack.render.thumbnail.
    stack_detail_mask` passes. ``None`` is the module default, so every other
    caller is unchanged."""
    threshold = _coverage_threshold(coverage, min_frac,
                                    level_min_frac=level_min_frac)
    if threshold is None:
        return None
    cov = np.asarray(coverage, dtype=np.float32)
    return np.isfinite(cov) & (cov >= threshold)


def largest_covered_rect(coverage: np.ndarray,
                         min_frac: float = DEFAULT_MIN_FRAC):
    """Fractional ``(x0, y0, x1, y1)`` bounds (each in 0..1) of the largest
    axis-aligned rectangle whose pixels are all well covered, or ``None`` when
    there's nothing worth trimming.

    A pixel is "well covered" when its coverage is finite and at least
    ``min_frac`` of **one panel's** coverage depth (:func:`panel_coverage_level`
    — the peak until D1, which on a mosaic is the panel-overlap band); NaN (no
    coverage) always counts as
    uncovered. ``None`` is returned when the coverage is uniform (a single-field
    stack — every pixel passes, so the rectangle is the whole frame), when the
    best rectangle already spans essentially the whole frame (nothing ragged to
    trim), or when the result would be degenerate — so the caller can treat
    ``None`` as "leave the image alone".

    **The answer is also bounded by the coverage itself** (:data:`TRIM_KEEP_RATIO`,
    where the reasoning lives). The pixels a border trim is entitled to remove are
    the *uncovered* ones and the fringe beside them; a pixel that is merely
    shallower than its neighbours is a thinner **panel**, and cropping it away is
    D1 all over again — which is exactly what a dense raster with uneven panel
    depth used to get, because no single depth there is substantial enough for
    :func:`panel_coverage_level` to find and it settles near the mode instead.
    So the rectangle the coverage alone allows is computed too, and when the depth
    threshold does far worse than that bound the threshold is halved and asked
    again. It can only ever keep **more** than it did before this guard existed.
    """
    threshold = _coverage_threshold(coverage, min_frac)
    if threshold is None:
        return None
    cov = np.asarray(coverage, dtype=np.float32)
    covered = np.isfinite(cov) & (cov > 0)
    # What the coverage alone allows: the honest ceiling on a border trim.
    bound = _rect_area(_rect_from_mask(covered))
    for _ in range(_TRIM_LADDER_RUNGS):
        rect = _rect_from_mask(np.isfinite(cov) & (cov >= threshold))
        if _rect_area(rect) >= TRIM_KEEP_RATIO * bound:
            return rect
        threshold *= 0.5
    return _rect_from_mask(covered)
