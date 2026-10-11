"""The ⭐ gradient/de-levelling fix, and the three shapes measured before it.

``docs/IMPROVEMENTS.md``'s first Bugs entry reproduced a real defect in v0.493.10:
a light-pollution ramp of only ~49 % of the sky, running *across* a mosaic's panel
strips, pushed every genuine sky level past
:data:`~seestack.edit.presets._LEVEL_MAX_SIGMA_RATIO`, so
:func:`~seestack.edit.presets._delevelled_luminance` declined, Auto read a sky
level **2.08x** the truth and the finished mosaic came out ~7.8 % dark. v0.493.12
measured the fix that entry proposed — judge the guard on a detrended copy of the
plane — and ruled it out: it fixed that case and made a ramp running *along* the
strips **2.6x worse than the bug**.

The diagnosis v0.493.12 left is the one this file is built on: *detrending the
whole canvas removes two different things at once, the smooth shape common to
every panel (which the guard should ignore) and the smooth shape that differs
between panels (which the guard must see), and a single ``level_sigma`` on any one
plane cannot tell those apart — nor a smooth object spanning a strip from smooth
sky.* **So the quantity was under-determined, and v0.493.13 stops asking a single
plane for it:** the smooth sky surface and the per-level steps are fitted
*against each other*, and both the guard and the step are read off the result.

**What this file holds.** The shipped design measured against the arithmetic it
replaced and against the two alternatives that were ruled out, on the same
fixtures, over five raster geometries x fifteen scenes — because the thing that
made the first measurement of this subsystem wrong was a fixture, and the thing
that made the second candidate look right was measuring only the geometry the bug
was filed on. Nothing here is a paragraph: the dead ends are asserted, so neither
can be re-proposed on the strength of this file's prose.

**The yardstick is ``target_bg``, the stretch goal ``auto_recipe`` actually
emits**, taken as the difference from the goal the identical stack laid out as a
single field gets. It is the user-visible consequence, it is bounded (the knob is
clipped to 0.14-0.24) and its control's step is 0.01, so "half a slider step" is a
scale the reader can hold. The reported sky level is a worse yardstick: it is the
median's position inside a percentile window, so a sub-grain residual moves it by
10 % while moving ``target_bg`` by a thirtieth of one step.
"""

from __future__ import annotations

import numpy as np
import pytest

from seestack.bg.coverage_leveling import _robust_stats
from seestack.bg.sky_poly import fit_sky_poly
from seestack.edit import presets as P
from seestack.edit.noise import estimate_noise_sigma

H, W = 300, 600

#: The flat sky every scene is built on, so a smooth shape can be quoted as a
#: share of it (which is how light pollution is actually talked about).
_SKY = 0.103

#: Four seeds, because a single one cannot tell a finding from a fixture; the
#: grid test uses two of them to stay inside a sane runtime, the headline cases
#: use all four.
_SEEDS = (13, 5, 21, 3)


def _scene(*, rows: int = 1, cols: int = 4, offsets=(), gradient: float = 0.0,
           axis: str = "y", sigma: float = 0.004, blob: float = 0.0,
           radial: float = 0.0, seed: int = 13) -> np.ndarray:
    """A linear mosaic proxy: flat sky, a faint extended object, stars, grain,
    an optional smooth shape, and per-panel steps on a ``rows`` x ``cols`` raster.

    The three smooth shapes are deliberately different *relative to the raster*:
    ``axis="y"`` puts a ramp perpendicular to the panel strips (every panel sees
    all of it — the case the bug was filed on), ``axis="x"`` along them (each
    panel sees a different part, so the shape genuinely differs between panels),
    ``axis="xy"`` obliquely, and ``radial`` a centre-bright vignette-like residual
    that is even-symmetric and therefore the hardest of the three to tell from a
    canvas-filling object. ``blob`` is that object.
    """
    rng = np.random.default_rng(seed)
    img = np.full((H, W), _SKY, dtype=np.float32)
    yy, xx = np.mgrid[0:H, 0:W]
    img += (np.exp(-(((xx - W / 2) / 50.0) ** 2 + ((yy - H / 2) / 35.0) ** 2))
            * 0.033).astype(np.float32)
    for _ in range(150):
        cy, cx = int(rng.integers(8, H - 8)), int(rng.integers(8, W - 8))
        amp = float(rng.uniform(0.2, 0.9))
        gy, gx = np.mgrid[cy - 6:cy + 7, cx - 6:cx + 7]
        img[cy - 6:cy + 7, cx - 6:cx + 7] += (
            amp * np.exp(-(((gx - cx) / 1.6) ** 2 + ((gy - cy) / 1.6) ** 2))
        ).astype(np.float32)
    img += rng.normal(0.0, sigma, img.shape).astype(np.float32)
    if gradient:
        ramp = ((yy / H) if axis == "y"
                else (xx / W) if axis == "x"
                else 0.5 * (yy / H) + 0.5 * (xx / W))
        img += (gradient * ramp).astype(np.float32)
    if radial:
        r2 = ((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2
        img += (radial * (1.0 - 0.9 * r2)).astype(np.float32)
    if blob:
        img += (blob * np.exp(-(((xx - W / 2) / (W / 3)) ** 2
                                + ((yy - H / 2) / (H / 2)) ** 2))).astype(np.float32)
    if offsets:
        ph, pw = H // rows, W // cols
        for r in range(rows):
            for c in range(cols):
                img[r * ph:(r + 1) * ph, c * pw:(c + 1) * pw] += np.float32(
                    offsets[r * cols + c])
    return img


def _coverage(rows: int, cols: int, frames) -> np.ndarray:
    cov = np.zeros((H, W), dtype=np.float32)
    ph, pw = H // rows, W // cols
    for r in range(rows):
        for c in range(cols):
            cov[r * ph:(r + 1) * ph, c * pw:(c + 1) * pw] = float(
                frames[r * cols + c])
    return cov


#: Five raster geometries, because the identification problem this fix is about
#: depends on the raster: on a 1xN strip a ramp can be perpendicular to every
#: panel, on a 2D raster no linear gradient is, and the number of panels sets how
#: much of a staircase a degree-2 surface can mimic. The 2x2 and 2x3 are the
#: owner's own shape (AGENTS.md §1 — he is a heavy mosaic user); the 1x4 is the
#: geometry the bug was filed on and the only one the first two candidates were
#: ever measured against.
_GEOMS: dict[str, dict] = {
    "1x2 strips": dict(rows=1, cols=2, offsets=(0.0, 0.012), frames=(12, 9)),
    "1x4 strips": dict(rows=1, cols=4, offsets=(0.0, 0.012, -0.008, 0.016),
                       frames=(12, 9, 15, 6)),
    "2x2 raster": dict(rows=2, cols=2, offsets=(0.0, 0.012, -0.008, 0.016),
                       frames=(12, 9, 15, 6)),
    "2x3 raster": dict(rows=2, cols=3,
                       offsets=(0.0, 0.012, -0.008, 0.016, 0.006, -0.014),
                       frames=(12, 9, 15, 6, 18, 21)),
    "3x3 raster": dict(rows=3, cols=3,
                       offsets=(0.0, 0.012, -0.008, 0.016, 0.006, -0.014,
                                0.009, -0.004, 0.013),
                       frames=(12, 9, 15, 6, 18, 21, 24, 11, 17)),
}

#: ``(name, scene kwargs, is this a smooth sky shape?)``. The ``blob`` rows are
#: not: they are the canvas the guard exists for.
_SCENES: list[tuple[str, dict, bool]] = [
    ("quiet", {}, False),
    ("ramp across (y) 0.05", dict(gradient=0.05, axis="y"), True),
    ("ramp across (y) 0.20", dict(gradient=0.20, axis="y"), True),
    ("ramp across (y) 0.50", dict(gradient=0.50, axis="y"), True),
    ("ramp along (x) 0.20", dict(gradient=0.20, axis="x"), True),
    ("ramp along (x) 0.50", dict(gradient=0.50, axis="x"), True),
    ("ramp oblique 0.20", dict(gradient=0.20, axis="xy"), True),
    ("ramp oblique 0.50", dict(gradient=0.50, axis="xy"), True),
    ("radial 0.02", dict(radial=0.02), True),
    ("radial 0.05", dict(radial=0.05), True),
    ("radial 0.20", dict(radial=0.20), True),
    ("blob 0.15", dict(blob=0.15), False),
    ("blob 0.20", dict(blob=0.20), False),
    ("blob 0.30", dict(blob=0.30), False),
    ("blob 0.60", dict(blob=0.60), False),
]


# --------------------------------------------------------------------------- #
# The arithmetic this replaced, and the two alternatives ruled out, as replicas
# --------------------------------------------------------------------------- #

def _prologue(lum: np.ndarray, coverage: np.ndarray):
    """Everything ``_delevelled_luminance`` does before the part that changed —
    the binning, the floors, the rough per-level sky, the object mask and the
    grain — shared by all three replicas so the comparisons below are about the
    one thing that differs."""
    cov = np.asarray(coverage)
    if cov.ndim == 3:
        cov = cov[..., 0]
    finite = np.isfinite(lum)
    with np.errstate(invalid="ignore"):
        cov_int = np.rint(np.nan_to_num(cov.astype(np.float64, copy=False),
                                        nan=0.0)).astype(np.int64)
    valid = (cov_int > 0) & finite
    n_valid = int(valid.sum())
    floor = max(P._LEVEL_MIN_PIXELS, int(round(P._LEVEL_MIN_SHARE * n_valid)))
    levels, counts = np.unique(cov_int[valid], return_counts=True)
    big = [int(lv) for lv, n in zip(levels, counts, strict=True) if n >= floor]
    if len(big) < 2:
        return None
    regions = {level: (cov_int == level) & valid for level in big}
    rough = np.zeros(lum.shape, dtype=np.float32)
    for region in regions.values():
        med, _ = _robust_stats(lum[region])
        if np.isfinite(med):
            rough[region] = np.float32(med)
    destepped = lum - rough
    med0, spread = _robust_stats(destepped[valid])
    lum_c = lum[valid]
    span = float(np.percentile(lum_c, 99.5) - np.percentile(lum_c, 0.5))
    grain = float(estimate_noise_sigma(lum)) * span
    sky = valid & (destepped <= (med0 + P._LEVEL_OBJECT_SIGMA * spread))
    return valid, regions, destepped, grain, sky, spread


def _subtract(lum, valid, regions, sky, per_level):
    if len(per_level) < 2:
        return lum
    reference, _ = _robust_stats(lum[valid & sky])
    out = np.array(lum, dtype=np.float32, copy=True)
    for level, med in per_level.items():
        out[regions[level]] -= np.float32(med - reference)
    return out


def _before_v049313(lum: np.ndarray, coverage: np.ndarray) -> np.ndarray:
    """The arithmetic v0.493.13 replaced: the guard asked of the raw plane, the
    step taken as the level's own median. Both halves of the defect."""
    got = _prologue(lum, coverage)
    if got is None:
        return lum
    valid, regions, destepped, grain, sky, _ = got
    per_level: dict[int, float] = {}
    for level, region in regions.items():
        region_sky = region & sky
        if lum[region_sky].size < P._LEVEL_MIN_PIXELS:
            continue
        _, level_sigma = _robust_stats(destepped[region_sky])
        if not np.isfinite(level_sigma) or level_sigma > P._LEVEL_MAX_SIGMA_RATIO * grain:
            continue
        med, _ = _robust_stats(lum[region_sky])
        if np.isfinite(med):
            per_level[level] = float(med)
    return _subtract(lum, valid, regions, sky, per_level)


def _candidate_detrend_the_whole_canvas(lum: np.ndarray,
                                        coverage: np.ndarray) -> np.ndarray:
    """Ruled out in v0.493.12: judge the guard (and mask) on a detrended copy of
    the plane while still taking the step from the raw one."""
    got = _prologue(lum, coverage)
    if got is None:
        return lum
    valid, regions, _d, _g, _s, _sp = got
    yard = P._detrended_luminance(lum)
    rough = np.zeros(yard.shape, dtype=np.float32)
    for region in regions.values():
        med, _ = _robust_stats(yard[region])
        if np.isfinite(med):
            rough[region] = np.float32(med)
    destepped = yard - rough
    med0, spread = _robust_stats(destepped[valid])
    yc = yard[valid]
    span = float(np.percentile(yc, 99.5) - np.percentile(yc, 0.5))
    grain = float(estimate_noise_sigma(yard)) * span
    sky = valid & (destepped <= (med0 + P._LEVEL_OBJECT_SIGMA * spread))
    per_level: dict[int, float] = {}
    for level, region in regions.items():
        region_sky = region & sky
        if lum[region_sky].size < P._LEVEL_MIN_PIXELS:
            continue
        _, level_sigma = _robust_stats(destepped[region_sky])
        if not np.isfinite(level_sigma) or level_sigma > P._LEVEL_MAX_SIGMA_RATIO * grain:
            continue
        med, _ = _robust_stats(lum[region_sky])
        if np.isfinite(med):
            per_level[level] = float(med)
    return _subtract(lum, valid, regions, sky, per_level)


def _candidate_the_ops_own_bar(lum: np.ndarray,
                               coverage: np.ndarray) -> np.ndarray:
    """The other obvious move, ruled out here: mirror the real op.

    ``bg.coverage_leveling`` judges a level against ``3 x the canvas's retained
    sky spread`` (``_level_context``'s ``max_level_sigma``) rather than against
    the grain, and that bar rises with a gradient — so the op levels a mosaic the
    measurement refuses, which looks like exactly the divergence to close. It is
    not: the op's bar also rises with a canvas-filling *object*, which is why
    v0.410.0 chose the grain in the first place, and levelling by a
    gradient-contaminated step flattens a smooth ramp into a sawtooth the next
    pass cannot remove.
    """
    got = _prologue(lum, coverage)
    if got is None:
        return lum
    valid, regions, destepped, _grain, sky, spread = got
    per_level: dict[int, float] = {}
    for level, region in regions.items():
        region_sky = region & sky
        if lum[region_sky].size < P._LEVEL_MIN_PIXELS:
            continue
        _, level_sigma = _robust_stats(destepped[region_sky])
        if not np.isfinite(level_sigma) or level_sigma > P._LEVEL_MAX_SIGMA_RATIO * spread:
            continue
        med, _ = _robust_stats(lum[region_sky])
        if np.isfinite(med):
            per_level[level] = float(med)
    return _subtract(lum, valid, regions, sky, per_level)


_SHIPPED = P._delevelled_luminance


def _rgb(lum: np.ndarray) -> np.ndarray:
    return np.stack([lum * 0.95, lum, lum * 1.05], axis=-1).astype(np.float32)


def _target_bg(lum: np.ndarray, cov: np.ndarray) -> float:
    """The stretch goal Auto *measures* for this canvas.

    Read off ``measured_auto_knobs`` on exactly the pixels ``auto_recipe`` hands
    it, rather than off the built recipe, and the distinction is load-bearing
    since **v0.493.14**: the recipe's ``target_bg`` is now landed on its
    control's own 0.01 stops, and every number this file is about — the fix's own
    residual cost (0.0002-0.0008), the pass-count convergence (0.0061 -> 0.0008)
    — is *smaller than one of those stops*, so reading the recipe would return a
    column of exact zeros and measure nothing. The measurement is continuous and
    stays so; only what reaches the slider is quantised. (That the costs this
    file bounds are now literally invisible in what Auto emits is asserted in
    :func:`test_the_measured_cost_is_below_the_controls_own_resolution`.)
    """
    m_rgb, m_cov = P.measured_region(_rgb(lum), cov, None)
    return float(P.measured_auto_knobs(m_rgb, m_cov)["target_bg"])


def _emitted_target_bg(lum: np.ndarray, cov: np.ndarray) -> float:
    """What the recipe actually carries — the same number, on its control's grid."""
    stretch = next(op for op in P.auto_recipe(_rgb(lum), median_fwhm=2.5,
                                              is_mosaic=True, coverage=cov).ops
                   if op.id == "tone.stretch")
    return float(stretch.params["target_bg"])


def _goal_error(delevel, geom, scene_kw, seed) -> float:
    """``|target_bg(mosaic) - target_bg(the same stack as a single field)|``."""
    rows, cols = geom["rows"], geom["cols"]
    cov = _coverage(rows, cols, geom["frames"])
    flat = np.full(cov.shape, float(geom["frames"][0]), dtype=np.float32)
    mosaic = _scene(seed=seed, rows=rows, cols=cols,
                    offsets=geom["offsets"], **scene_kw)
    single = _scene(seed=seed, rows=rows, cols=cols,
                    offsets=tuple(0.0 for _ in geom["offsets"]), **scene_kw)
    P._delevelled_luminance = delevel
    try:
        return abs(_target_bg(mosaic, cov) - _target_bg(single, flat))
    finally:
        P._delevelled_luminance = _SHIPPED


# --------------------------------------------------------------------------- #
# The headline: the defect it was filed for
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("gradient", [0.05, 0.20, 0.50])
def test_the_filed_defect_is_fixed_at_every_gradient_strength(gradient):
    """The 1x4 strip raster the bug was filed on, at the boundary and ten times
    past it: the stretch goal is now the single field's goal to within **0.0003**
    where it was out by **0.0194-0.0196** — two slider steps.
    """
    geom = _GEOMS["1x4 strips"]
    for seed in _SEEDS:
        kw = dict(gradient=gradient, axis="y")
        after = _goal_error(_SHIPPED, geom, kw, seed)
        before = _goal_error(_before_v049313, geom, kw, seed)
        assert before > 0.015, (seed, before)
        assert after < 0.001, (seed, after)
        assert after < before / 15.0, (seed, before, after)


def test_a_quiet_mosaic_is_what_it_was_to_well_inside_a_slider_step():
    """The other half of the trade, and the only place the fix *costs* anything.

    A degree-2 surface fitted to a plane that still holds the panel staircase
    absorbs part of it, so the step this pass charges is a little low and the
    remainder is left for ``_detrended_luminance`` to take out — which it does, but
    not perfectly. On a mosaic with no smooth shape at all, where the old
    arithmetic was exact, that shows up as a residual error in the goal. Measured
    over all five geometries: **0.0002-0.0008**, i.e. under a tenth of the
    ``target_bg`` control's own 0.01 step, against the 0.0080-0.0229 the old
    arithmetic cost the moment any smooth shape was present.
    """
    worst = 0.0
    for name, geom in _GEOMS.items():
        for seed in (13, 5):
            err = _goal_error(_SHIPPED, geom, {}, seed)
            worst = max(worst, err)
            assert err < 0.001, (name, seed, err)
    # Not zero, and that is the honest statement: it is a measured cost, bounded.
    assert worst > 0.0


def test_the_measured_cost_is_below_the_controls_own_resolution():
    """And the same cost as the owner can actually see it: not at all.

    The residual above is a cost to the *measurement*. What reaches his picture
    is the measurement landed on ``tone.stretch.target_bg``'s own 0.01 stops
    (v0.493.14), and 0.0002-0.0008 is a twelfth of one of those — so on a quiet
    mosaic the recipe Auto writes is now **byte-identical** to the one it writes
    for the same stack laid out as a single field. Asserted here rather than in
    the snapping test because this is the number that makes v0.493.13's trade
    free in the output, and it is this file's figures that bound it.
    """
    for name, geom in _GEOMS.items():
        rows, cols = geom["rows"], geom["cols"]
        cov = _coverage(rows, cols, geom["frames"])
        flat = np.full(cov.shape, float(geom["frames"][0]), dtype=np.float32)
        for seed in (13, 5):
            mosaic = _scene(seed=seed, rows=rows, cols=cols,
                            offsets=geom["offsets"])
            single = _scene(seed=seed, rows=rows, cols=cols,
                            offsets=tuple(0.0 for _ in geom["offsets"]))
            assert (_emitted_target_bg(mosaic, cov)
                    == _emitted_target_bg(single, flat)), (name, seed)


# --------------------------------------------------------------------------- #
# Every geometry x every shape — the sweep the earlier candidates lacked
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("geometry", sorted(_GEOMS))
def test_no_geometry_and_no_smooth_shape_is_worse_than_it_was(geometry):
    """The grid, two seeds: fifteen scenes on each of five rasters.

    Two claims, and the first is the one that makes this safe to ship: **no case
    is worse than the arithmetic it replaced by more than 0.001** of the goal —
    a tenth of a slider step, and only ever on a canvas with no smooth shape to
    disentangle. The second is what it buys: on every *smooth-shape* scene the
    error is at least **3x** smaller, and usually far more.
    """
    geom = _GEOMS[geometry]
    worst_after = worst_before = 0.0
    for name, kw, smooth in _SCENES:
        for seed in (13, 5):
            after = _goal_error(_SHIPPED, geom, kw, seed)
            before = _goal_error(_before_v049313, geom, kw, seed)
            assert after <= before + 0.001, (geometry, name, seed, before, after)
            if smooth:
                worst_after = max(worst_after, after)
                worst_before = max(worst_before, before)
    assert worst_after < 0.004, (geometry, worst_after)
    assert worst_before > 3.0 * worst_after, (geometry, worst_before, worst_after)


@pytest.mark.parametrize("geometry", ["1x4 strips", "2x3 raster"])
def test_both_ruled_out_alternatives_are_worse_than_the_shipped_design(geometry):
    """The dead ends, asserted rather than written down.

    Each of these was the obvious next move at some point in this entry's life —
    the first is the fix the entry itself proposed, the second is "just mirror the
    op" — and each is **far** worse than both the shipped design and the
    arithmetic it replaced on a ramp that runs *along* the panels, because each
    ends up subtracting a gradient-contaminated step and flattening a smooth ramp
    into a sawtooth the detrend cannot touch. Measured here: up to **0.0844** of
    goal error, which is the whole 0.14-0.24 range of the knob.
    """
    geom = _GEOMS[geometry]
    for kw in (dict(gradient=0.20, axis="x"), dict(gradient=0.50, axis="x")):
        shipped = _goal_error(_SHIPPED, geom, kw, 13)
        detrended = _goal_error(_candidate_detrend_the_whole_canvas, geom, kw, 13)
        ops_bar = _goal_error(_candidate_the_ops_own_bar, geom, kw, 13)
        assert shipped < 0.002, (geometry, kw, shipped)
        assert detrended > 10.0 * shipped, (geometry, kw, detrended, shipped)
        assert ops_bar > 10.0 * shipped, (geometry, kw, ops_bar, shipped)


# --------------------------------------------------------------------------- #
# The parts of the design that are choices, measured
# --------------------------------------------------------------------------- #

#: ``_LEVEL_FIT_PASSES``, as ``{passes: worst goal error on a quiet 2x3}``. The
#: alternation is a geometric contraction — each pass hands the surface a flatter
#: staircase, so it absorbs less of it — and this is where the constant's own
#: comment gets its figures.
_CONVERGENCE: dict[int, float] = {1: 0.0061, 2: 0.0030, 3: 0.0019, 6: 0.0008}


def test_the_pass_count_is_a_measured_choice_not_a_round_number():
    """One pass is not enough and the sixth still pays, which is the whole
    justification for :data:`~seestack.edit.presets._LEVEL_FIT_PASSES`.

    At one pass a quiet 2x3 raster's goal is out by **0.0061** — over half a
    slider step, which is the scale the fix exists to remove — and six takes it to
    **0.0008**. Monotone the whole way, so this is a convergence rather than a
    tuned number, and the early exit means a canvas that has already settled does
    not pay for the passes it does not need.
    """
    geom = _GEOMS["2x3 raster"]
    seen: dict[int, float] = {}
    original = P._LEVEL_FIT_PASSES
    try:
        for passes in sorted(_CONVERGENCE):
            P._LEVEL_FIT_PASSES = passes
            seen[passes] = max(_goal_error(_SHIPPED, geom, {}, seed)
                               for seed in _SEEDS)
    finally:
        P._LEVEL_FIT_PASSES = original
    for passes, want in _CONVERGENCE.items():
        assert seen[passes] == pytest.approx(want, rel=0.30), (passes, seen)
    counts = sorted(seen)
    for lo, hi in zip(counts, counts[1:], strict=False):
        assert seen[hi] < seen[lo], seen
    assert seen[1] > 5.0 * seen[max(counts)], seen


def test_the_early_exit_cannot_change_the_answer_it_only_saves_passes():
    """:data:`~seestack.edit.presets._LEVEL_FIT_SETTLED` stops the loop once no
    step moved by more than a twentieth of the grain. That has to be a saving and
    not a behaviour, so the same canvas is measured with it effectively off."""
    geom = _GEOMS["2x3 raster"]
    cov = _coverage(geom["rows"], geom["cols"], geom["frames"])
    original = P._LEVEL_FIT_SETTLED
    for kw in ({}, dict(gradient=0.20, axis="x")):
        lum = _scene(seed=13, rows=geom["rows"], cols=geom["cols"],
                     offsets=geom["offsets"], **kw)
        with_exit = P._delevelled_luminance(lum, cov)
        try:
            P._LEVEL_FIT_SETTLED = 0.0
            without = P._delevelled_luminance(lum, cov)
        finally:
            P._LEVEL_FIT_SETTLED = original
        span = float(np.percentile(lum, 99.5) - np.percentile(lum, 0.5))
        assert float(np.nanmax(np.abs(with_exit - without))) < 0.002 * span, kw


#: How much of a quiet 2x2 raster's injected staircase the alternation has
#: recovered after each pass, as a share of its 0.024 spread. The first pass is
#: the entry's named prerequisite measured from the other side: a degree-2 surface
#: fitted to a plane that still holds the whole staircase absorbs most of it here,
#: so one pass alone recovers barely a quarter of the step.
_RECOVERED_BY_PASS: dict[int, float] = {1: 0.28, 2: 0.47, 3: 0.60, 6: 0.82}


def test_the_surface_and_the_steps_really_are_fitted_against_each_other():
    """The mechanism, not the outcome: the step the pass recovers has to *move* as
    the surface is refitted, or the loop is decoration.

    Read out directly, because this is the quantity the whole design turns on —
    and it is the filed entry's named prerequisite seen from the other side. That
    entry warned that *"a degree-2 surface only partly absorbs panel steps, so the
    detrended plane is not a free yardstick either"* and measured the absorption at
    35-49 % of a 0.012 step. On this 2x2 raster, where the staircase is the only
    structure a degree-2 surface has to work with, the first fit absorbs **72 %**
    of it — and that is exactly why one pass is not a fix and six are.
    """
    geom = _GEOMS["2x2 raster"]
    cov = _coverage(geom["rows"], geom["cols"], geom["frames"])
    lum = _scene(seed=13, rows=geom["rows"], cols=geom["cols"],
                 offsets=geom["offsets"])
    got = _prologue(lum, cov)
    assert got is not None
    _valid, regions, _d, grain, sky, _sp = got
    injected = max(geom["offsets"]) - min(geom["offsets"])

    recovered: dict[int, float] = {}
    steps = {level: 0.0 for level in regions}
    for passes in range(1, max(_RECOVERED_BY_PASS) + 1):
        step_map = np.zeros(lum.shape, dtype=np.float32)
        for level, region in regions.items():
            step_map[region] = np.float32(steps[level])
        surface = fit_sky_poly(lum - step_map, sky)
        assert surface is not None
        residual = lum - surface
        for level, region in regions.items():
            med, _ = _robust_stats(residual[region & sky])
            steps[level] = float(med)
        recovered[passes] = (max(steps.values()) - min(steps.values())) / injected

    for passes, want in _RECOVERED_BY_PASS.items():
        assert recovered[passes] == pytest.approx(want, rel=0.15), recovered
    counts = sorted(_RECOVERED_BY_PASS)
    for lo, hi in zip(counts, counts[1:], strict=False):
        assert recovered[hi] > recovered[lo], recovered
    # And what the loop adds — 0.013 of step on a 0.0042 grain — is ~60x the
    # scale its own stopping rule calls "settled", so the passes are not chasing
    # noise.
    moved = (recovered[6] - recovered[1]) * injected
    assert moved > 20.0 * P._LEVEL_FIT_SETTLED * grain, (moved, grain)
    assert moved > 2.5 * grain, (moved, grain)


def test_the_steps_come_out_of_the_plane_the_sky_level_is_read_off():
    """The composed claim, which is the one that matters.

    ``_delevelled_luminance`` deliberately leaves the part of a staircase its
    surface can explain *in* the surface — that is what stops a gradient being
    sawtoothed — and ``_detrended_luminance``, which both callers compose it with
    on the very next line, removes exactly that part. So the property to assert is
    about the composition, and on the plane Auto actually reads its sky level off
    the panels end up level in every geometry, with or without a smooth shape.
    """
    for name, geom in _GEOMS.items():
        rows, cols = geom["rows"], geom["cols"]
        cov = _coverage(rows, cols, geom["frames"])
        ph, pw = H // rows, W // cols

        def spread(plane, rows=rows, cols=cols, ph=ph, pw=pw):
            meds = [float(np.median(plane[r * ph:(r + 1) * ph,
                                          c * pw:(c + 1) * pw]))
                    for r in range(rows) for c in range(cols)]
            return max(meds) - min(meds)

        for kw in ({}, dict(gradient=0.20, axis="y"),
                   dict(gradient=0.20, axis="x")):
            lum = _scene(seed=13, rows=rows, cols=cols,
                         offsets=geom["offsets"], **kw)
            raw = spread(lum)
            after = spread(P._detrended_luminance(
                P._delevelled_luminance(lum, cov)))
            before = spread(P._detrended_luminance(_before_v049313(lum, cov)))
            assert raw > 0.010, (name, kw, raw)
            assert after < 0.004, (name, kw, after)
            if kw:
                # With a smooth shape present the old arithmetic left the whole
                # staircase in the plane; this is the defect, on the pixels.
                assert before > 4.0 * after, (name, kw, before, after)
