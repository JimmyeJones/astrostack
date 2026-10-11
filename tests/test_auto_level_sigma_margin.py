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
occur on, and :func:`test_a_smooth_gradient_walks_a_sky_level_into_the_guard`
pins what reading the real margin turned up.
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
    out = []
    for region in regions.values():
        region_sky = region & sky
        if lum[region_sky].size < P._LEVEL_MIN_PIXELS:
            continue
        _, level_sigma = _robust_stats(destepped[region_sky])
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
    refuses. Checked at both ends of the separation and across the boundary the
    gradient test walks, which is the only place the two could disagree."""
    cov = _coverage()
    for label, lum in (
        ("quiet sky", _scene()),
        ("canvas is object", _scene(blob=0.6)),
        ("gradient below the bar", _scene(gradient=0.02)),
        ("gradient above the bar", _scene(gradient=0.05)),
    ):
        ratios = _sigma_ratios(lum, cov)
        kept = [r for r in ratios if r <= P._LEVEL_MAX_SIGMA_RATIO]
        # ``_delevelled_luminance`` needs two surviving levels to do anything.
        assert _levelled(lum, cov) == (len(kept) >= 2), (label, ratios)


@pytest.mark.parametrize("seed", [13, 5, 21, 3])
def test_a_sky_carrying_an_object_reads_well_under_the_bar(seed):
    """Population one: an ordinary mosaic. **0.89-0.95**, not the 0.24-0.36 the
    constant's comment recorded — so the headroom above sky is ~3.2x, not 8-12x."""
    ratios = _sigma_ratios(_scene(seed=seed), _coverage())
    assert len(ratios) == len(_FRAMES)
    assert min(ratios) > 0.80, ratios
    assert max(ratios) < 1.05, ratios
    assert max(ratios) < P._LEVEL_MAX_SIGMA_RATIO / 3.0, ratios
    assert _levelled(_scene(seed=seed), _coverage())


#: Population two, as ``{object amplitude: (worst, best) level}``. Against the
#: 5.1-12.5 the constant's comment recorded, and monotone in the object, as it
#: should be — the quantity is "how much structure is left in this level".
_OBJECT_FILLED: dict[float, tuple[float, float]] = {
    0.3: (8.57, 13.19),
    0.6: (16.42, 25.50),
    1.2: (29.39, 45.97),
}


@pytest.mark.parametrize("blob", sorted(_OBJECT_FILLED))
def test_a_canvas_that_is_the_object_reads_far_over_the_bar(blob):
    """Population two: the canvas the guard exists for."""
    lo, hi = _OBJECT_FILLED[blob]
    lum = _scene(blob=blob)
    ratios = _sigma_ratios(lum, _coverage())
    assert min(ratios) == pytest.approx(lo, rel=0.15), (blob, ratios)
    assert max(ratios) == pytest.approx(hi, rel=0.15), (blob, ratios)
    # Even the faintest canvas-filling object this sweep uses is nearly 3x over
    # the bar, so the guard is not relying on a tuned margin at this end either.
    assert min(ratios) > 2.5 * P._LEVEL_MAX_SIGMA_RATIO, (blob, ratios)
    assert not _levelled(lum, _coverage()), "a canvas that is object was levelled"


def test_the_separation_is_wide_and_the_constant_sits_between_the_populations():
    """The claim the comment draws, asserted rather than argued: the two
    populations are ~17x apart and 3.0 is inside the gap, not on either edge."""
    sky = max(_sigma_ratios(_scene(), _coverage()))
    obj = min(_sigma_ratios(_scene(blob=0.6), _coverage()))
    assert obj / sky > 12.0, (sky, obj)
    assert sky < P._LEVEL_MAX_SIGMA_RATIO < obj, (sky, obj)
    # 3.2x above a quiet sky and 5.5x below a filled canvas. Recording *both*
    # margins is the point: the figure the comment used to carry implied the
    # first was 8-12x, which is the number someone tightening 3.0 would trust.
    assert P._LEVEL_MAX_SIGMA_RATIO / sky == pytest.approx(3.2, rel=0.15)
    assert obj / P._LEVEL_MAX_SIGMA_RATIO == pytest.approx(5.5, rel=0.15)


# --- what reading the real margin turned up ----------------------------------

#: The gradient sweep, as ``{ramp as a share of the sky: (worst ratio, levelled)}``.
#: ``axis="y"`` — the ramp runs across the panel strips, so every panel sees all
#: of it. **It adds nothing to the panel-to-panel differences** (asserted below),
#: so refusing to level is pure loss.
_GRADIENT_SWEEP: dict[float, tuple[float, bool]] = {
    0.00: (0.95, True),
    0.02: (1.81, True),
    0.05: (3.82, False),
    0.10: (7.14, False),
    0.20: (13.96, False),
}


@pytest.mark.parametrize("gradient", sorted(_GRADIENT_SWEEP))
def test_a_smooth_gradient_walks_a_sky_level_into_the_guard(gradient):
    """**A filed bug's repro, pinned as it behaves today** (docs/IMPROVEMENTS.md,
    "a light-pollution gradient switches the mosaic delevel off").

    ``_delevelled_luminance`` runs **before** ``_detrended_luminance`` — see
    ``analyze_proxy``'s own ``_detrended_luminance(_delevelled_luminance(...))``
    — so the plane the guard asks "does this still look like sky?" of still has
    the smooth ramp in it. A level's spread therefore grows with the gradient
    while the grain does not, and at a ramp of only **0.05 on a 0.103 sky (49 %)**
    every genuine sky level crosses 3.0 and the delevel declines outright.

    The guard's stated purpose is a level *"a nebula or a galaxy fills"*. A
    smooth sky gradient is not that, and it is the one thing the next function in
    the chain is about to remove anyway. When that ordering is fixed this test
    fails, and the numbers below are what it should be compared against.
    """
    want_worst, want_levelled = _GRADIENT_SWEEP[gradient]
    lum = _scene(gradient=gradient, axis="y")
    ratios = _sigma_ratios(lum, _coverage())
    assert max(ratios) == pytest.approx(want_worst, rel=0.15), ratios
    assert _levelled(lum, _coverage()) is want_levelled, (gradient, ratios)
    # The ramp is perpendicular to the strips, so it contributes nothing to what
    # the delevel exists to remove: the steps are the same size at every gradient.
    assert _panel_spread(lum) == pytest.approx(_panel_spread(_scene()), rel=0.15)


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


@pytest.mark.parametrize("gradient,crosses", [(0.02, False), (0.05, True)])
def test_the_refusal_reaches_the_number_auto_sets_its_goal_from(gradient, crosses):
    """And it is v0.409.0's own defect coming back, measured its own way.

    v0.409.0 shipped the delevel because *"the level Auto sets its stretch target
    from still read 0.075 for a mosaic against 0.024 for the identical stack laid
    out as a single field"*. Same comparison here, with the ramp held equal on
    both sides so the only difference is the panel steps:

    ======================  ============  ==================  ==========
    ramp (share of sky)     mosaic sky    same stack, 1 field  target_bg
    ======================  ============  ==================  ==========
    0.02 (19 %)             0.0405        0.0404               0.2238
    0.05 (49 %)             **0.0838**    0.0404               **0.2065**
    ======================  ============  ==================  ==========

    **2.08x the truth**, a 7.8 % lower stretch goal, and a finished picture
    **7.1 % darker** than the identical single field. Not a rounding error and
    not cosmetic: it is the goal for one image chosen by measuring another.
    """
    cov = _coverage()
    flat = np.full((H, W), float(_FRAMES[0]), dtype=np.float32)
    mosaic = _scene(gradient=gradient, axis="y")
    single = _scene(offsets=(0.0,) * len(_OFFSETS), gradient=gradient, axis="y")

    m_sky, s_sky = _reported_sky(mosaic, cov), _reported_sky(single, flat)
    if crosses:
        assert m_sky / s_sky > 1.8, (m_sky, s_sky)
        assert _target_bg(mosaic, cov) < _target_bg(single, flat) - 0.01
        assert _finished_sky(mosaic, cov) < 0.95 * _finished_sky(single, flat)
    else:
        assert m_sky == pytest.approx(s_sky, rel=0.02), (m_sky, s_sky)
        assert _target_bg(mosaic, cov) == pytest.approx(
            _target_bg(single, flat), abs=0.002)
        assert _finished_sky(mosaic, cov) == pytest.approx(
            _finished_sky(single, flat), rel=0.02)
