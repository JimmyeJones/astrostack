"""``_LEVEL_MAX_SIGMA_RATIO = 3.0`` — the two populations it separates, measured.

:data:`seestack.edit.presets._LEVEL_MAX_SIGMA_RATIO` is the guard that keeps
:func:`~seestack.edit.presets._delevelled_luminance` from subtracting an
*object's* level out of a mosaic panel as if it were a sky offset: each coverage
level's retained sample is refused when its spread exceeds this many times the
image's own grain. It is on the on-by-default Auto path — ``auto_recipe``
prepends ``background.level_coverage`` on every mosaic, and ``analyze_proxy``
reads the sky level Auto's stretch target comes from off this de-stepped plane.

**Why this file exists.** The constant's justification was prose: *"Measured
across six scenes it reads 0.24-0.36 where the canvas is sky carrying an object
and 5.1-12.5 where the canvas is the object, so this separates two populations
rather than tuning a margin."* Nothing checked those figures, and **neither
reproduces**: on fixtures whose panel steps and coverage map describe the *same*
mosaic it reads **0.89-0.95** and **16.4-25.5**. The conclusion survives — 3.0 is
still a separation, with ~17x between the populations — but the *margin* does
not. A reader taking 0.24-0.36 at face value would think 3.0 sits 8-12x above
anything sky can produce. It sits **3.2x** above a quiet sky and **1.5x** above
one under a bright gradient, which is a different constant to reason about.

That is the same lesson v0.493.9 drew one subsystem over: a list whose
justification is prose has nothing checking it, and neither does a *figure*
inside an asserted claim. So the figures are asserted here, with the window they
occur on, and :func:`test_a_smooth_gradient_no_longer_walks_a_sky_level_into_the_guard`
pins what reading the real margin turned up.

**v0.493.13 fixed what that reading found, and the numbers below moved with it.**
The guard used to be asked of a plane that still carried the light-pollution
gradient, so a ramp of only ~49 % of the sky pushed **every** genuine sky level
past 3.0 and the whole pass declined — reported sky 2.08x the truth. It is now
asked of the residual from a smooth sky surface that is fitted jointly with the
per-level steps (see :func:`~seestack.edit.presets._delevelled_luminance`), which
is the only plane on which "does this look like sky?" is well posed. What changed
in the two populations, measured on this file's own fixtures:

===========================  ==================  ==================
population                   before v0.493.13    now
===========================  ==================  ==================
quiet sky                    0.89-0.95           0.90-0.98
sky under a 49 % ramp        **3.82** (refused)  **0.95-1.13**
canvas is the object (0.6)   16.42-25.50         6.43-11.34
===========================  ==================  ==================

So the sky end is where it was, the gradient no longer reaches the object end at
all, and the object end came down by ~2.3x — it is measured against a residual
now rather than against the object's own unexplained profile. The separation is
3.5x rather than ~17x, and :func:`test_the_window_the_guard_reopened_is_harmless`
is why that is a smaller loss than it looks: the step the pass subtracts is a
residual from the surface too, so levelling a canvas the object fills no longer
subtracts the object's own level, and every amplitude that newly levels measures
a **lower** ``target_bg`` error than refusing it did. The whole sweep behind the
change is in ``tests/test_auto_delevel_joint_fit.py``.
"""

from __future__ import annotations

import numpy as np
import pytest

from seestack.edit import presets as P
from seestack.edit.pipeline import apply_recipe
from seestack.edit.presets import _delevelled_luminance, analyze_proxy, auto_recipe
from seestack.edit.registry import EditContext

H, W = 300, 600

#: The flat sky every scene here is built on, so a gradient can be quoted as a
#: share of it (which is how light pollution is actually talked about).
_SKY = 0.103

#: A four-panel raster's per-panel offsets and frame counts, the shape
#: ``tests/test_auto_noise_measure.py`` uses. The two agree here on purpose: a
#: coverage map that does **not** describe the image's own steps puts two
#: different panel offsets inside one level, and the guard then (correctly)
#: refuses that level — which looks exactly like this file's finding and is not
#: it. Mismatched fixtures are why the first measurement of this was wrong.
_OFFSETS = (0.0, 0.012, -0.008, 0.016)
_FRAMES = (12, 9, 15, 6)


def _scene(*, offsets=_OFFSETS, gradient: float = 0.0, axis: str = "y",
           sigma: float = 0.004, blob: float = 0.0, seed: int = 13) -> np.ndarray:
    """A linear mosaic proxy: flat sky, a faint extended object, stars, grain,
    optional light-pollution ramp, optional canvas-filling object, panel steps.

    ``axis="y"`` puts the ramp **perpendicular** to the panel strips, so every
    panel sees all of it and it adds nothing to the panel-to-panel differences —
    the case that matters, and the worst one.
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
        ramp = (xx / W) if axis == "x" else (yy / H)
        img += (gradient * ramp).astype(np.float32)
    if blob:
        img += (blob * np.exp(-(((xx - W / 2) / (W / 3)) ** 2
                                + ((yy - H / 2) / (H / 2)) ** 2))).astype(np.float32)
    pw = W // len(offsets)
    for i, off in enumerate(offsets):
        img[:, i * pw:(i + 1) * pw] += np.float32(off)
    return img


def _coverage(frames=_FRAMES) -> np.ndarray:
    cov = np.zeros((H, W), dtype=np.float32)
    pw = W // len(frames)
    for i, n in enumerate(frames):
        cov[:, i * pw:(i + 1) * pw] = float(n)
    return cov


def _sigma_ratios(lum: np.ndarray, cov: np.ndarray) -> list[float]:
    """Every coverage level's ``level_sigma / grain`` — the quantity
    ``_LEVEL_MAX_SIGMA_RATIO`` is compared against, read out of a replica of
    ``_delevelled_luminance``'s own arithmetic up to the guard.

    A replica rather than an instrumented call because the function returns
    pixels, not its own intermediates; it is checked against the real thing by
    :func:`test_the_replica_agrees_with_the_function_it_replicates`, which
    compares which levels each one refuses.
    """
    from seestack.bg.coverage_leveling import _robust_stats
    from seestack.bg.sky_poly import fit_sky_poly
    from seestack.edit.noise import estimate_noise_sigma

    finite = np.isfinite(lum)
    cov_int = np.rint(np.nan_to_num(cov.astype(np.float64), nan=0.0)).astype(np.int64)
    valid = (cov_int > 0) & finite
    floor = max(P._LEVEL_MIN_PIXELS,
                int(round(P._LEVEL_MIN_SHARE * int(valid.sum()))))
    levels, counts = np.unique(cov_int[valid], return_counts=True)
    regions = {int(lv): (cov_int == int(lv)) & valid
               for lv, n in zip(levels, counts, strict=True) if n >= floor}
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
    # v0.493.13: the smooth sky surface and the per-level steps, fitted against
    # each other — the guard is asked of the residual from that surface, not of
    # the raw plane. Same loop, same stopping rule, as the function's own.
    steps = {level: 0.0 for level in regions}
    surface = None
    for _ in range(P._LEVEL_FIT_PASSES):
        step_map = np.zeros(lum.shape, dtype=np.float32)
        for level, region in regions.items():
            step_map[region] = np.float32(steps[level])
        fitted = fit_sky_poly(lum - step_map, sky)
        if fitted is None or not np.all(np.isfinite(fitted)):
            break
        surface = fitted
        residual = lum - surface
        moved = 0.0
        for level, region in regions.items():
            region_sky = region & sky
            if lum[region_sky].size < P._LEVEL_MIN_PIXELS:
                continue
            med, _ = _robust_stats(residual[region_sky])
            if np.isfinite(med):
                moved = max(moved, abs(float(med) - steps[level]))
                steps[level] = float(med)
        if moved <= P._LEVEL_FIT_SETTLED * grain:
            break
    assert surface is not None, "no sky surface could be fitted"
    residual = lum - surface
    out = []
    for region in regions.values():
        region_sky = region & sky
        if lum[region_sky].size < P._LEVEL_MIN_PIXELS:
            continue
        _, level_sigma = _robust_stats(residual[region_sky])
        out.append(float(level_sigma) / grain)
    return out


def _levelled(lum: np.ndarray, cov: np.ndarray) -> bool:
    """Did ``_delevelled_luminance`` actually remove the steps, or stand aside?"""
    return not np.array_equal(_delevelled_luminance(lum, cov), lum)


def _panel_spread(lum: np.ndarray, n: int = len(_OFFSETS)) -> float:
    pw = W // n
    meds = [float(np.median(lum[:, i * pw:(i + 1) * pw])) for i in range(n)]
    return max(meds) - min(meds)


# --- the two populations, as the constant's comment claims them ---------------

def test_the_replica_agrees_with_the_function_it_replicates():
    """:func:`_sigma_ratios` is only evidence if it refuses what the real guard
    refuses. Checked at both ends of the separation and across the gradient range
    that used to walk sky into the guard, which is where the two could disagree."""
    cov = _coverage()
    for label, lum in (
        ("quiet sky", _scene()),
        ("canvas is object", _scene(blob=0.6)),
        ("gradient 0.02", _scene(gradient=0.02)),
        ("gradient 0.05", _scene(gradient=0.05)),
        ("gradient 0.20", _scene(gradient=0.20)),
    ):
        ratios = _sigma_ratios(lum, cov)
        kept = [r for r in ratios if r <= P._LEVEL_MAX_SIGMA_RATIO]
        # ``_delevelled_luminance`` needs two surviving levels to do anything.
        assert _levelled(lum, cov) == (len(kept) >= 2), (label, ratios)


@pytest.mark.parametrize("seed", [13, 5, 21, 3])
def test_a_sky_carrying_an_object_reads_well_under_the_bar(seed):
    """Population one: an ordinary mosaic. **0.90-0.98**, not the 0.24-0.36 the
    constant's comment recorded — so the headroom above sky is ~3.1x, not 8-12x.

    Unmoved by v0.493.13: on a quiet mosaic there is no smooth shape for the
    jointly-fitted surface to take out, so the residual the guard is asked of is
    the same grain it always was (0.89-0.95 before, 0.90-0.98 now).
    """
    ratios = _sigma_ratios(_scene(seed=seed), _coverage())
    assert len(ratios) == len(_FRAMES)
    assert min(ratios) > 0.80, ratios
    assert max(ratios) < 1.05, ratios
    assert max(ratios) < P._LEVEL_MAX_SIGMA_RATIO / 3.0, ratios
    assert _levelled(_scene(seed=seed), _coverage())


#: Population two, as ``{object amplitude: (worst, best) level}``. Against the
#: 5.1-12.5 the constant's comment recorded, and monotone in the object, as it
#: should be — the quantity is "how much structure is left in this level".
#:
#: **v0.493.13 moved this end down by ~2.3x** (it was 8.57-13.19 / 16.42-25.50 /
#: 29.39-45.97): the guard is now asked of the residual from a jointly-fitted
#: smooth surface, and a canvas-filling object is partly explainable by a degree-2
#: surface, so what is left of it is smaller. The faintest amplitude here is still
#: refused, and :func:`test_the_window_the_guard_reopened_is_harmless` measures
#: what the narrower margin costs where it does let a level through.
_OBJECT_FILLED: dict[float, tuple[float, float]] = {
    0.3: (3.39, 6.05),
    0.6: (6.43, 11.34),
    1.2: (11.64, 19.96),
}


@pytest.mark.parametrize("blob", sorted(_OBJECT_FILLED))
def test_a_canvas_that_is_the_object_reads_far_over_the_bar(blob):
    """Population two: the canvas the guard exists for."""
    lo, hi = _OBJECT_FILLED[blob]
    lum = _scene(blob=blob)
    ratios = _sigma_ratios(lum, _coverage())
    assert min(ratios) == pytest.approx(lo, rel=0.15), (blob, ratios)
    assert max(ratios) == pytest.approx(hi, rel=0.15), (blob, ratios)
    # The faintest canvas-filling object this sweep uses is still clear of the
    # bar, and monotone in the object above it.
    assert min(ratios) > P._LEVEL_MAX_SIGMA_RATIO, (blob, ratios)
    assert not _levelled(lum, _coverage()), "a canvas that is object was levelled"


def test_the_separation_is_wide_and_the_constant_sits_between_the_populations():
    """The claim the comment draws, asserted rather than argued: the two
    populations are ~6.5x apart and 3.0 is inside the gap, not on either edge.

    **It was ~17x before v0.493.13**, and both margins are recorded because that
    is the point of this file: the figure the comment used to carry implied the
    sky-end margin was 8-12x when it was 3.2x, and nobody tightening 3.0 should
    have to take a paragraph's word for either end.
    """
    sky = max(_sigma_ratios(_scene(), _coverage()))
    obj = min(_sigma_ratios(_scene(blob=0.6), _coverage()))
    assert obj / sky > 5.0, (sky, obj)
    assert sky < P._LEVEL_MAX_SIGMA_RATIO < obj, (sky, obj)
    # 3.1x above a quiet sky and 2.1x below a filled canvas.
    assert P._LEVEL_MAX_SIGMA_RATIO / sky == pytest.approx(3.1, rel=0.15)
    assert obj / P._LEVEL_MAX_SIGMA_RATIO == pytest.approx(2.1, rel=0.15)


# --- what reading the real margin turned up, and what v0.493.13 did with it ---

#: The gradient sweep, as ``{ramp as a share of the sky: (worst ratio, levelled)}``.
#: ``axis="y"`` — the ramp runs across the panel strips, so every panel sees all
#: of it. **It adds nothing to the panel-to-panel differences** (asserted below),
#: so refusing to level would be pure loss.
#:
#: **Before v0.493.13 this table read 0.95/1.81/3.82/7.14/13.96 and levelled only
#: the first two**: the guard was asked of a plane that still carried the ramp, so
#: a level's spread grew linearly with the gradient while the grain it was judged
#: against did not, and at a ramp of only 0.05 on a 0.103 sky (49 %) every genuine
#: sky level crossed 3.0 and the pass declined outright. It is now asked of the
#: residual from a smooth surface fitted jointly with the steps, so the ramp is
#: not in the quantity at all and the ratio is flat in it.
_GRADIENT_SWEEP: dict[float, tuple[float, bool]] = {
    0.00: (0.97, True),
    0.02: (1.10, True),
    0.05: (1.11, True),
    0.10: (1.12, True),
    0.20: (1.12, True),
}


@pytest.mark.parametrize("gradient", sorted(_GRADIENT_SWEEP))
def test_a_smooth_gradient_no_longer_walks_a_sky_level_into_the_guard(gradient):
    """**A filed bug's repro, now pinned as the fix** (docs/IMPROVEMENTS.md's ⭐
    first Bugs entry, reproduced in v0.493.10, one candidate measured and ruled
    out in v0.493.12, fixed in v0.493.13).

    The guard's stated purpose is a level *"a nebula or a galaxy fills"*. A smooth
    sky gradient is not that, and it is the one thing the next function in the
    chain is about to remove anyway — so the quantity the guard is given must not
    contain it. It does not any more: the ratio is **flat in the gradient** across
    a factor of ten of ramp strength, and every level is still measured.
    """
    want_worst, want_levelled = _GRADIENT_SWEEP[gradient]
    lum = _scene(gradient=gradient, axis="y")
    ratios = _sigma_ratios(lum, _coverage())
    assert max(ratios) == pytest.approx(want_worst, rel=0.15), ratios
    assert _levelled(lum, _coverage()) is want_levelled, (gradient, ratios)
    # The ramp is perpendicular to the strips, so it contributes nothing to what
    # the delevel exists to remove: the steps are the same size at every gradient.
    assert _panel_spread(lum) == pytest.approx(_panel_spread(_scene()), rel=0.15)
    # And the ratio stays inside the sky population at every strength, rather
    # than climbing through the bar — which is the property that was broken.
    assert max(ratios) < P._LEVEL_MAX_SIGMA_RATIO / 2.0, ratios


def _reported_sky(lum: np.ndarray, cov: np.ndarray) -> float:
    rgb = np.stack([lum * 0.95, lum, lum * 1.05], axis=-1).astype(np.float32)
    return float(analyze_proxy(rgb, coverage=cov)["sky"])


def _target_bg(lum: np.ndarray, cov: np.ndarray) -> float:
    rgb = np.stack([lum * 0.95, lum, lum * 1.05], axis=-1).astype(np.float32)
    stretch = next(op for op in auto_recipe(rgb, median_fwhm=2.5, is_mosaic=True,
                                            coverage=cov).ops
                   if op.id == "tone.stretch")
    return float(stretch.params["target_bg"])


def _finished_sky(lum: np.ndarray, cov: np.ndarray) -> float:
    rgb = np.stack([lum * 0.95, lum, lum * 1.05], axis=-1).astype(np.float32)
    recipe = auto_recipe(rgb, median_fwhm=2.5, is_mosaic=True, coverage=cov)
    out = apply_recipe(rgb, recipe,
                       EditContext(coverage=cov, frame_coverage=cov))
    return float(np.percentile(out[..., :3].mean(axis=2), 30.0))


@pytest.mark.parametrize("gradient", [0.02, 0.05, 0.20])
def test_the_goal_auto_sets_is_the_same_goal_the_single_field_gets(gradient):
    """And v0.409.0's own defect is closed again, measured its own way.

    v0.409.0 shipped the delevel because *"the level Auto sets its stretch target
    from still read 0.075 for a mosaic against 0.024 for the identical stack laid
    out as a single field"*. Same comparison here, with the ramp held equal on
    both sides so the only difference is the panel steps:

    ======================  ============  ===================  ==========
    ramp (share of sky)     mosaic sky    same stack, 1 field  target_bg
    ======================  ============  ===================  ==========
    0.02 (19 %)             0.0408        0.0404               0.2237
    0.05 (49 %)             0.0408        0.0404               0.2237
    0.20 (194 %)            0.0408        0.0404               0.2237
    ======================  ============  ===================  ==========

    **Before v0.493.13 the 49 % row read 0.0838 — 2.08x the truth — a 7.8 % lower
    stretch goal and a finished picture 7.1 % darker than the identical single
    field.** The reported sky is now within 1.1 % and ``target_bg`` within 0.0002
    (a fiftieth of its own slider step) at every strength, and the ratio no longer
    steps: it is flat across a factor of ten of ramp.
    """
    cov = _coverage()
    flat = np.full((H, W), float(_FRAMES[0]), dtype=np.float32)
    mosaic = _scene(gradient=gradient, axis="y")
    single = _scene(offsets=(0.0,) * len(_OFFSETS), gradient=gradient, axis="y")

    m_sky, s_sky = _reported_sky(mosaic, cov), _reported_sky(single, flat)
    assert m_sky == pytest.approx(s_sky, rel=0.03), (m_sky, s_sky)
    assert _target_bg(mosaic, cov) == pytest.approx(
        _target_bg(single, flat), abs=0.002)
    assert _finished_sky(mosaic, cov) == pytest.approx(
        _finished_sky(single, flat), rel=0.03)


def test_the_window_the_guard_reopened_is_harmless():
    """What the narrower object-end margin actually costs, measured.

    v0.493.13 brought the object end of the separation down by ~2.3x, so a band of
    faint canvas-filling objects that used to be refused is now measured and
    levelled (amplitude ~0.10-0.25 on this fixture). That sounds like exactly the
    failure the guard exists to prevent — *"reading the object's level as a sky
    offset would subtract real flux"* — and it is not, because the step the pass
    subtracts is now a residual from the surface too: the object's own smooth
    profile is in the surface, so it is not in the step. Measured as the error in
    the ``target_bg`` Auto emits, against the identical stack laid out as a single
    field, every newly-levelled amplitude is **better** than refusing it was:

    =========  ==================  =================
    amplitude  refused (before)    levelled (now)
    =========  ==================  =================
    0.10       0.0158              **0.0003**
    0.15       0.0134              **0.0100**
    0.20       0.0110              **0.0095**
    0.25       0.0088              **0.0081**
    =========  ==================  =================

    So the loss of margin is not a loss of the protection the margin was for. The
    amplitudes above the band are refused exactly as before (0.30 and up), which
    :func:`test_a_canvas_that_is_the_object_reads_far_over_the_bar` holds.
    """
    cov = _coverage()
    flat = np.full((H, W), float(_FRAMES[0]), dtype=np.float32)
    worst = 0.0
    for blob in (0.10, 0.15, 0.20, 0.25):
        mosaic = _scene(blob=blob)
        single = _scene(offsets=(0.0,) * len(_OFFSETS), blob=blob)
        assert _levelled(mosaic, cov), blob
        err = abs(_target_bg(mosaic, cov) - _target_bg(single, flat))
        worst = max(worst, err)
    # Every one of them is inside the 0.0134 the *refusal* used to cost at 0.15,
    # so nothing in this band got worse by being measured.
    assert worst < 0.0134, worst
