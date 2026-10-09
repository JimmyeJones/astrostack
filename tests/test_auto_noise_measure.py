"""How the one-click Auto chain measures "how noisy is this stack?".

Everything Auto decides about grain — how much to denoise, how much to sharpen,
how hard to run the colour-blotch smoother, how much saturation to add — hangs
off the single ``sky_sigma`` number ``analyze_proxy`` reports. This file pins the
property that number must have: it measures **grain**, not **structure**.

Owner-reported regression (2026-07-30, S30, real data): a deep ~400-sub mosaic
that rendered clean on an older build came out with a "multicolour grid" keyed to
the panel seams. The old estimator was the MAD of the sky's *levels*, which
counts a mosaic's per-panel level/colour offsets (and any residual light-pollution
gradient) as if they were noise — so a genuinely clean mosaic read as one of the
noisiest images the app had seen and got the wide-kernel chroma smoothing at full
strength, smearing colour across the seams.

The same property is owed to the **sky level** ``analyze_proxy`` reports beside
it — the number ``auto_recipe`` turns into the stretch's target grey — and it did
not have it until v0.409.0: a light-pollution gradient that Auto's own first op
removes used to drag the level up and the finished picture down. Those tests live
at the bottom of this file, on the same scene, because it is the same claim.
"""

from __future__ import annotations

import numpy as np
import pytest

from seestack.edit.coverage_trim import largest_covered_rect
from seestack.edit.pipeline import apply_recipe
from seestack.edit.presets import (
    _AUTO_CHROMA_MAX,
    _delevelled_luminance,
    _detrended_luminance,
    _noise_fraction,
    analyze_auto_inputs,
    analyze_proxy,
    auto_recipe,
    classify_target,
    measured_region,
)
from seestack.edit.registry import EditContext

H, W = 300, 600
_PANEL_OFFSETS = (0.0, 0.012, -0.008, 0.016)
_PANEL_CHROMA = (
    (0.000, 0.000, 0.000),
    (0.004, -0.002, 0.000),
    (-0.003, 0.001, 0.002),
    (0.002, 0.003, -0.004),
)


def _scene(
    sigma: float, *, seed: int = 0, mosaic: bool = False, gradient: float = 0.0,
    nan_border: bool = False,
) -> np.ndarray:
    """A realistic linear proxy: sky + a faint extended object + stars + noise.

    ``mosaic=True`` adds the thing that matters — small per-panel level and
    colour offsets, exactly what photometric matching leaves behind at a mosaic's
    seams. The *pixel noise* is identical either way, so any difference in the
    measured σ is the estimator reacting to structure.
    """
    rng = np.random.default_rng(seed)
    img = np.broadcast_to(
        np.array([0.10, 0.12, 0.09], dtype=np.float32), (H, W, 3),
    ).astype(np.float32).copy()
    yy, xx = np.mgrid[0:H, 0:W]
    obj = np.exp(-(((xx - W / 2) / 50.0) ** 2 + ((yy - H / 2) / 35.0) ** 2))
    img += (obj[..., None] * np.array([0.05, 0.03, 0.02])).astype(np.float32)
    for _ in range(150):
        cy, cx = int(rng.integers(8, H - 8)), int(rng.integers(8, W - 8))
        amp = float(rng.uniform(0.2, 0.9))
        gy, gx = np.mgrid[cy - 6:cy + 7, cx - 6:cx + 7]
        star = amp * np.exp(-(((gx - cx) / 1.6) ** 2 + ((gy - cy) / 1.6) ** 2))
        img[cy - 6:cy + 7, cx - 6:cx + 7] += star[..., None].astype(np.float32)
    img += rng.normal(0.0, sigma, img.shape).astype(np.float32)
    if gradient:
        img += (gradient * (xx / W))[..., None].astype(np.float32)
    if mosaic:
        pw = W // len(_PANEL_OFFSETS)
        for i, off in enumerate(_PANEL_OFFSETS):
            sl = slice(i * pw, (i + 1) * pw)
            img[:, sl] += off
            img[:, sl] += np.array(_PANEL_CHROMA[i], dtype=np.float32)
    if nan_border:
        img[:15, :] = np.nan
        img[-15:, :] = np.nan
    return img


@pytest.mark.parametrize("sigma", [0.004, 0.01, 0.02, 0.05, 0.09])
def test_sky_sigma_matches_the_old_level_mad_on_pure_noise(sigma):
    """Upgrade safety: on a structure-free frame the local estimator must report
    what the old level-MAD reported, or every constant calibrated against it
    (the crossfade band, the "noisy" verdict, the saturation term) silently
    changes meaning and ordinary single-field stacks render differently.
    """
    img = _scene(sigma, seed=3)

    # The old estimator, verbatim, for comparison.
    lum = img[..., :3].mean(axis=2)
    finite = lum[np.isfinite(lum)]
    lo, hi = float(np.percentile(finite, 0.5)), float(np.percentile(finite, 99.5))
    norm = np.clip((finite - lo) / (hi - lo), 0.0, 1.0)
    med = float(np.median(norm))
    sky = norm[norm <= med]
    old = float(1.4826 * np.median(np.abs(sky - np.median(sky))))

    new = analyze_proxy(img)["sky_sigma"]
    # Within 3 % at every σ. What difference remains is largest at the *cleanest*
    # end (2.2 % at σ = 0.004), and it is the old estimator reading slightly high
    # because the faint extended object's own structure lands in its level MAD —
    # i.e. the very effect being removed, just small here.
    assert new == pytest.approx(old, rel=0.03), f"{new=} {old=}"


def test_a_deep_mosaics_panel_offsets_are_not_counted_as_noise():
    """The regression itself: the same deep stack, laid out as a mosaic.

    Only per-panel level/colour offsets differ — the pixel noise is identical —
    so the measured σ must barely move. Before the fix it more than tripled.
    """
    single = analyze_proxy(_scene(0.004, seed=5))["sky_sigma"]
    mosaic = analyze_proxy(_scene(0.004, seed=5, mosaic=True))["sky_sigma"]
    assert mosaic == pytest.approx(single, rel=0.25), f"{mosaic=} {single=}"


def test_a_deep_mosaic_does_not_get_the_colour_smoother_at_all():
    """End to end: a clean mosaic's one-click Auto must not contain the
    wide-kernel ``detail.chroma_denoise`` op — the one that smeared colour across
    the owner's panel seams — nor lose its sharpening to a phantom noise read."""
    mosaic = _scene(0.004, seed=7, mosaic=True)
    a = analyze_proxy(mosaic)
    assert _noise_fraction(a["sky_sigma"]) == 0.0
    assert a["noisy"] is False

    ids = [o.id for o in auto_recipe(mosaic).ops]
    assert "detail.chroma_denoise" not in ids
    assert "detail.denoise" not in ids
    assert "detail.sharpen" in ids


def test_the_same_stack_gets_the_same_recipe_whether_or_not_it_is_a_mosaic():
    """The property behind the fix, stated whole.

    Panel offsets are a *layout* artefact, not a property of the data's quality,
    so laying the identical stack out as a mosaic must not change what Auto does
    to it. Before the fix the mosaic lost its sharpening entirely
    (``amount`` 0.5 → 0.0), had its colour boost cut back, and gained a full-
    strength colour smoother.
    """
    single = {o.id: o.params for o in auto_recipe(_scene(0.004, seed=7)).ops}
    mosaic = {o.id: o.params for o in auto_recipe(_scene(0.004, seed=7, mosaic=True)).ops}
    assert list(single) == list(mosaic)
    assert float(mosaic["detail.sharpen"]["amount"]) == pytest.approx(
        float(single["detail.sharpen"]["amount"]), rel=0.05)
    assert float(mosaic["tone.saturation"]["amount"]) == pytest.approx(
        float(single["tone.saturation"]["amount"]), rel=0.05)


def test_a_genuinely_noisy_mosaic_still_gets_denoised():
    """The fix must not swing the other way: a thin, noisy mosaic is still noisy,
    and still gets the denoise + colour smoothing it needs."""
    noisy = _scene(0.05, seed=11, mosaic=True)
    a = analyze_proxy(noisy)
    assert _noise_fraction(a["sky_sigma"]) > 0.9
    assert a["noisy"] is True

    ops = {o.id: o for o in auto_recipe(noisy).ops}
    assert "detail.denoise" in ops
    chroma = ops.get("detail.chroma_denoise")
    assert chroma is not None
    assert 0.0 < float(chroma.params["strength"]) <= _AUTO_CHROMA_MAX


def test_a_residual_light_pollution_gradient_is_not_counted_as_noise():
    """The same failure mode on a single field: a smooth gradient is structure,
    not grain, and must not conjure a denoise pass onto a clean stack."""
    flat = analyze_proxy(_scene(0.004, seed=13))["sky_sigma"]
    tilted = analyze_proxy(_scene(0.004, seed=13, gradient=0.08))["sky_sigma"]
    assert tilted == pytest.approx(flat, rel=0.25), f"{tilted=} {flat=}"
    assert _noise_fraction(tilted) == 0.0


def test_uncovered_mosaic_border_does_not_inflate_the_measurement():
    """A mosaic's ragged NaN border is "no coverage", never a noisy sky."""
    covered = analyze_proxy(_scene(0.004, seed=17, mosaic=True))["sky_sigma"]
    ragged = analyze_proxy(
        _scene(0.004, seed=17, mosaic=True, nan_border=True),
    )["sky_sigma"]
    assert ragged == pytest.approx(covered, rel=0.25)


def test_a_strong_gradient_never_costs_a_clean_stack_its_sharpening():
    """The deferred "does the denoise↔sharpen crossfade over-read a sky gradient
    as noise?" question, run as its own experiment and pinned.

    Filed 2026-07-08 against the *old* level-MAD estimator and deferred three
    times as real-data-gated. Its recorded measurement was a gradient of
    0.00→0.05→0.10→0.20 of range moving ``sky_sigma`` 0.015→0.028→0.054→0.098 at
    a fixed low noise — flipping Auto from ``sharpen≈0.40`` to **sharpen 0.0 /
    full denoise** by a gradient of only ~0.05, on exactly the
    light-polluted-but-deeply-stacked frame the owner shoots.

    The local estimator (v0.225.0) closed it by construction, and this walks the
    entry's own ladder to say so with numbers rather than by argument: measured
    at σ=0.003, ``sky_sigma`` now goes 0.0042→0.0039→0.0035→0.0030 — it does not
    rise with the gradient at all (it drifts *down*, because the tilt lifts the
    99.5th-percentile ceiling the frame is normalised against), the crossfade
    stays hard at "not noisy", and Auto keeps the same sharpening with no denoise
    pass added. The sibling test above pins the σ property at one gradient; this
    pins the *decision* across the whole range the entry feared.

    **Not a vacuous pin:** re-measured on these very scenes, the old level-MAD
    estimator gives 0.0078→0.0722→0.1121→0.1610, i.e. ``_noise_fraction`` **1.0
    from a gradient of 0.05** — this test fails on the first step of the ladder
    against the estimator the entry was filed about, which is what makes it a
    guard rather than a restatement of today's numbers.
    """
    baseline = None
    for gradient in (0.0, 0.05, 0.10, 0.20):
        sigma = analyze_proxy(_scene(0.003, seed=5, gradient=gradient))["sky_sigma"]
        assert _noise_fraction(sigma) == 0.0, f"{gradient=} {sigma=}"
        ops = {op.id: op for op in auto_recipe(
            _scene(0.003, seed=5, gradient=gradient), median_fwhm=3.0).ops}
        sharpen = ops.get("detail.sharpen")
        assert sharpen is not None and sharpen.enabled, f"{gradient=} lost sharpening"
        # A gradient must not conjure a grain pass onto a clean stack either.
        assert "detail.denoise" not in ops, f"{gradient=} gained a denoise pass"
        if baseline is None:
            baseline = sharpen.params["amount"]
        assert sharpen.params["amount"] == pytest.approx(baseline), f"{gradient=}"


def test_an_unmeasurable_image_still_reads_as_clean():
    """The 'can't tell' convention the rest of the auto chain relies on."""
    assert analyze_proxy(np.zeros((4, 4, 3), np.float32))["sky_sigma"] == 0.0
    assert analyze_proxy(np.full((40, 40, 3), 0.2, np.float32))["sky_sigma"] == 0.0
    all_nan = analyze_proxy(np.full((40, 40, 3), np.nan, np.float32))
    assert all_nan["sky_sigma"] == 0.0
    assert all_nan["noisy"] is False


# --------------------------------------------------------------------------
# The same claim, for the sky *level* (v0.409.0)
#
# ``analyze_proxy``'s ``sky`` is the *only* input to Auto's stretch target
# (``target_bg = 0.24 - sky*0.4``), and it read the whole-image normalized
# median — which a residual light-pollution gradient moves bodily, exactly the
# way the old level-MAD moved the σ above. The gradient is gone before the
# stretch sees a pixel (``background.final_gradient`` is the recipe's first op),
# so the same picture with and without one must be measured, and finished, the
# same.
# --------------------------------------------------------------------------


def _target_bg(img: np.ndarray) -> float:
    """The grey Auto aims this stack's sky at, off its own recipe."""
    stretch = next(op for op in auto_recipe(img, median_fwhm=2.5).ops
                   if op.id == "tone.stretch")
    return float(stretch.params["target_bg"])


def _finished_sky(img: np.ndarray) -> float:
    """A low percentile of the finished one-click picture's luminance — i.e. how
    dark the sky the owner is handed actually came out."""
    out = apply_recipe(img, auto_recipe(img, median_fwhm=2.5), EditContext())
    return float(np.percentile(out[..., :3].mean(axis=2), 30.0))


@pytest.mark.parametrize("gradient", [0.02, 0.05, 0.08])
def test_a_light_pollution_gradient_does_not_move_the_measured_sky_level(gradient):
    """The level owes the same "structure is not a sky" property the σ has.

    Before v0.409.0 the same scene read 0.024 flat and 0.153 at gradient 0.08 —
    a six-fold move caused entirely by a tilt Auto removes itself.
    """
    flat = analyze_proxy(_scene(0.004, seed=13))["sky"]
    tilted = analyze_proxy(_scene(0.004, seed=13, gradient=gradient))["sky"]
    assert tilted == pytest.approx(flat, rel=0.10), f"{gradient=} {tilted=} {flat=}"


def test_a_gradient_does_not_pull_down_the_one_click_stretch_target():
    """One step downstream, in the number the recipe actually carries: the
    stretch target went 0.230 → 0.179 for the same picture."""
    flat = _target_bg(_scene(0.004, seed=13))
    tilted = _target_bg(_scene(0.004, seed=13, gradient=0.08))
    assert tilted == pytest.approx(flat, rel=0.02), f"{tilted=} {flat=}"


def test_a_gradient_does_not_darken_the_finished_one_click_picture():
    """And the consequence the owner would actually see: the finished picture's
    sky came out 23 % darker (p30 0.190 → 0.147) purely because the stack had a
    gradient in it — one the recipe's own first op takes straight back out."""
    flat = _finished_sky(_scene(0.004, seed=13))
    tilted = _finished_sky(_scene(0.004, seed=13, gradient=0.08))
    assert tilted == pytest.approx(flat, rel=0.05), f"{tilted=} {flat=}"


def test_detrending_leaves_a_stack_with_no_gradient_where_it_already_was():
    """The upgrade-safety half, stated as a property rather than a promise: the
    detrend removes a *shape*, so a stack that has no shape to remove is
    measured exactly as it was before this existed — while a tilted one really
    is flattened. (Measured: 0.17 % of the image's own robust range against
    13.6 %.)"""
    def lum_of(img):
        return np.asarray(img, np.float32)[..., :3].mean(axis=2)

    flat = lum_of(_scene(0.004, seed=13))
    span = float(np.percentile(flat, 99.5) - np.percentile(flat, 0.5))
    assert float(np.max(np.abs(_detrended_luminance(flat) - flat))) < 0.01 * span

    tilted = lum_of(_scene(0.004, seed=13, gradient=0.08))
    assert float(np.max(np.abs(_detrended_luminance(tilted) - tilted))) > 0.05 * span


def test_the_detrend_declines_rather_than_inventing_a_surface():
    """It stands aside wherever the shared sky fit does, so an image it cannot
    measure keeps today's number instead of a fabricated one."""
    tiny = np.linspace(0.0, 1.0, 64, dtype=np.float32).reshape(8, 8)
    assert np.array_equal(_detrended_luminance(tiny), tiny)

    all_nan = np.full((40, 40), np.nan, np.float32)
    out = _detrended_luminance(all_nan)
    assert out.shape == all_nan.shape and not np.isfinite(out).any()


def test_a_genuinely_bright_sky_is_still_reported_as_bright():
    """The fix must not swing the other way and flatten every stack to "dark
    sky": a thin, bright-sky stack still reads bright and still gets the low
    stretch target that goes with it."""
    bright = analyze_proxy(_scene(0.05, seed=11, mosaic=True))["sky"]
    assert bright > 0.2
    assert _target_bg(_scene(0.05, seed=11, mosaic=True)) < 0.16


# --------------------------------------------------------------------------
# ...and for the *mosaic* half of the same claim (v0.410.0)
#
# v0.409.0 took the smooth, frame-scale sky shape out of the plane the level is
# read from, and said explicitly what it had *not* answered: a mosaic's per-panel
# offsets are steps, not a degree-2 surface, so the identical stack still read
# 0.075 laid out as a mosaic against 0.024 as a single field. Those steps are
# removed by ``background.level_coverage``, which ``auto_recipe`` prepends on
# every mosaic — i.e. before ``tone.stretch`` sees a pixel, exactly like the
# gradient. So the level is now measured with them taken out too, by binning on
# the run's own coverage map the way that op does.
# --------------------------------------------------------------------------

#: Frame counts for the four panels of ``_scene(mosaic=True)`` — uneven, the way
#: a real mosaic's panels are (the bundled ``--mosaic`` sample is 6/6/6/3).
_PANEL_FRAMES = (12, 9, 15, 6)


def _panel_coverage(frames: tuple[int, ...] = _PANEL_FRAMES) -> np.ndarray:
    """The coverage map that describes ``_scene(mosaic=True)``: one integer frame
    count per panel, on the same grid as the proxy."""
    cov = np.zeros((H, W), dtype=np.float32)
    pw = W // len(frames)
    for i, n in enumerate(frames):
        cov[:, i * pw:(i + 1) * pw] = float(n)
    return cov


def _mosaic_target_bg(img: np.ndarray, coverage: np.ndarray | None) -> float:
    """The grey Auto aims a *mosaic's* sky at, off its own recipe."""
    stretch = next(op for op in auto_recipe(img, median_fwhm=2.5, is_mosaic=True,
                                            coverage=coverage).ops
                   if op.id == "tone.stretch")
    return float(stretch.params["target_bg"])


def _finished_mosaic_sky(img: np.ndarray, coverage: np.ndarray | None) -> float:
    """A low percentile of the finished one-click picture, rendered the way a
    mosaic actually is — with the coverage map the leveling op needs in the
    context, so the steps really are gone by the time the stretch runs."""
    recipe = auto_recipe(img, median_fwhm=2.5, is_mosaic=True, coverage=coverage)
    ctx = EditContext(coverage=_panel_coverage(), frame_coverage=_panel_coverage())
    out = apply_recipe(img, recipe, ctx)
    return float(np.percentile(out[..., :3].mean(axis=2), 30.0))


@pytest.mark.parametrize("seed", [13, 5, 21])
def test_a_mosaics_panel_steps_do_not_move_the_measured_sky_level(seed):
    """The residual v0.409.0 filed rather than guessed at: the *same stack*, laid
    out as a mosaic, must report the same sky level.

    Before this, the panel offsets alone took it 0.024 → 0.075 (seed 13) — a
    layout artefact deciding how bright the owner's picture comes out.
    """
    single = analyze_proxy(_scene(0.004, seed=seed))["sky"]
    mosaic = analyze_proxy(_scene(0.004, seed=seed, mosaic=True),
                           _panel_coverage())["sky"]
    assert mosaic == pytest.approx(single, rel=0.05), f"{seed=} {mosaic=} {single=}"


def test_panel_steps_do_not_pull_down_the_one_click_stretch_target():
    """One step downstream, in the number the recipe carries: the stretch target
    read 0.210 for the mosaic against 0.230 for the identical single field."""
    single = _target_bg(_scene(0.004, seed=13))
    mosaic = _mosaic_target_bg(_scene(0.004, seed=13, mosaic=True), _panel_coverage())
    assert mosaic == pytest.approx(single, rel=0.02), f"{mosaic=} {single=}"


def test_panel_steps_do_not_darken_the_finished_one_click_picture():
    """And the consequence the owner would see on the shape he actually shoots:
    the finished mosaic's sky came out **11.2 %** darker than the identical stack
    laid out as a single field (p30 0.190 → 0.169). After, 1.1 %."""
    single = _finished_sky(_scene(0.004, seed=13))
    mosaic = _finished_mosaic_sky(_scene(0.004, seed=13, mosaic=True),
                                  _panel_coverage())
    assert mosaic == pytest.approx(single, rel=0.05), f"{mosaic=} {single=}"


def test_a_single_field_stacks_auto_is_untouched_by_a_coverage_map():
    """Upgrade safety, as the property rather than a promise: the steps are only
    measured out where the recipe removes them, so a run that gets no
    ``background.level_coverage`` gets byte-for-byte the recipe it got before this
    existed — whatever map is handed in."""
    img = _scene(0.004, seed=13, mosaic=True)
    without = auto_recipe(img, median_fwhm=2.5)
    withmap = auto_recipe(img, median_fwhm=2.5, coverage=_panel_coverage())
    assert [(o.id, o.params) for o in withmap.ops] == [
        (o.id, o.params) for o in without.ops]


def test_delevelling_leaves_a_mosaic_with_no_steps_where_it_already_was():
    """The other half of upgrade safety: it removes *steps*, so a canvas whose
    panels are already level is measured exactly as it was — while a stepped one
    really is flattened."""
    cov = _panel_coverage()

    def panel_medians(plane):
        pw = W // len(_PANEL_FRAMES)
        return [float(np.median(plane[:, i * pw:(i + 1) * pw]))
                for i in range(len(_PANEL_FRAMES))]

    level = _scene(0.004, seed=13)[..., :3].mean(axis=2)
    span = float(np.percentile(level, 99.5) - np.percentile(level, 0.5))
    # Nothing to remove: the plane comes back where it was.
    assert float(np.max(np.abs(_delevelled_luminance(level, cov) - level))) < 0.01 * span

    # Something to remove: the panels really do end up on one level. `_scene`
    # injects offsets spanning 0.024 (−0.008 … +0.016).
    stepped = _scene(0.004, seed=13, mosaic=True)[..., :3].mean(axis=2)
    before = panel_medians(stepped)
    after = panel_medians(_delevelled_luminance(stepped, cov))
    assert max(before) - min(before) > 0.02, before
    assert max(after) - min(after) < 0.002, after


def test_a_canvas_the_object_fills_is_left_alone_rather_than_flattened():
    """The stand-down that makes the correction safe to run at all.

    A panel a nebula genuinely *fills* has a median that is the **nebula's**, so
    shifting the panel by it subtracts real flux. Measured on an early version:
    the per-panel means of a canvas-filling object went 0.109/0.299/0.283/0.128 →
    0.166/0.183/0.184/0.167 — the object's own profile levelled into the sky, and
    ``classify_target`` stopped reading it as a nebula at all.

    Each level's retained sample is therefore checked against the image's own
    **grain**, measured structure-blind: an object-dominated canvas inflates a
    sigma-clipped spread until the guard can never fire (that is why the yardstick
    is not the one the op next door uses), while the grain stays the grain.
    """
    rng = np.random.default_rng(3)
    yy, xx = np.mgrid[0:H, 0:W]
    blob = np.exp(-(((xx - W / 2) / (W / 3)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2))
    filled = (_scene(0.004, seed=13, mosaic=True)[..., :3].mean(axis=2)
              + (0.6 * blob).astype(np.float32)
              + rng.normal(0.0, 0.002, (H, W)).astype(np.float32))
    out = _delevelled_luminance(filled, _panel_coverage())
    assert np.array_equal(out, filled), "a canvas that is object was 'levelled'"


def test_the_delevel_declines_rather_than_inventing_a_step():
    """It stands aside wherever it cannot honestly bin: no map, a map of the
    wrong shape, a canvas with only one level, and an unmeasurable one."""
    lum = _scene(0.004, seed=13, mosaic=True)[..., :3].mean(axis=2)
    assert _delevelled_luminance(lum, None) is lum
    assert np.array_equal(_delevelled_luminance(lum, np.ones((5, 5), np.float32)), lum)
    # One coverage level is not a mosaic, however big the canvas.
    flat = np.full((H, W), 8.0, dtype=np.float32)
    assert np.array_equal(_delevelled_luminance(lum, flat), lum)
    # Uncovered pixels are no-data, never a level of their own.
    assert np.array_equal(_delevelled_luminance(lum, np.zeros((H, W), np.float32)), lum)
    all_nan = np.full((H, W), np.nan, np.float32)
    out = _delevelled_luminance(all_nan, _panel_coverage())
    assert out.shape == all_nan.shape and not np.isfinite(out).any()


def test_two_panels_that_share_a_frame_count_are_one_bin():
    """The limit of this fix, pinned so nobody reads more into it than it does.

    It removes the steps ``background.level_coverage`` removes, by binning the way
    that op bins — so two panels that happen to be equally deep are one bin here
    exactly as they are one bin there, and a step between them survives both. The
    honest claim is "Auto measures the picture its own recipe will hand the
    stretch", not "Auto sees every seam".
    """
    img = _scene(0.004, seed=13, mosaic=True)
    # Every panel the same depth: nothing to bin by, nothing removed.
    same = analyze_proxy(img, _panel_coverage((10, 10, 10, 10)))["sky"]
    assert same == pytest.approx(analyze_proxy(img)["sky"], rel=1e-6)
    # Distinguishable depths: the steps go.
    apart = analyze_proxy(img, _panel_coverage())["sky"]
    assert apart < 0.5 * same


def test_a_genuinely_bright_sky_mosaic_is_still_reported_as_bright():
    """The fix must not swing the other way either: a thin, bright-sky mosaic
    still reads bright and still gets the low stretch target that goes with it."""
    bright = _scene(0.05, seed=11, mosaic=True)
    assert analyze_proxy(bright, _panel_coverage())["sky"] > 0.2
    assert _mosaic_target_bg(bright, _panel_coverage()) < 0.16


# ...and the fringe the recipe *deletes* is not the picture it makes (v0.492.x)
#
# v0.409.0 took the sky gradient out of the plane the level is read from and
# v0.410.0 the mosaic's panel steps, both because `background.final_gradient` and
# `background.level_coverage` are Auto's own *first* ops: those features are gone
# before `tone.stretch` sees a pixel, so measuring them is measuring a picture
# the recipe does not produce. Auto's **last** op is the same argument at the
# other end — `geometry.crop` to the largest well-covered rectangle deletes the
# union canvas's ragged border — and it had not been made there.
#
# The fixture above is why it hid: `_scene(mosaic=True)`'s canvas is a full
# rectangle, every panel covered edge to edge, so there is nothing for a trim to
# cut and the two measurements coincide by construction (the test right below
# states that, so the next reader does not have to re-derive it). Give the scene
# the ragged border a real union canvas has and they do not.
# --------------------------------------------------------------------------

#: Depth a fringe pixel of `_ragged` is covered to, drawn from 1..3 — against the
#: panels' 6..15. Grain goes as 1/sqrt(depth), so the fringe really is several
#: times grainier than the picture inside it, which is the whole point.
_FRINGE_DEPTH_MAX = 4

#: Share of the fringe band that is *covered at all*. The rest is NaN. 39 % is
#: what the bundled `--mosaic` sample's own trim region measures, so the fixture
#: is ragged the way a union canvas is ragged rather than the way a band is.
_FRINGE_COVERED_SHARE = 0.39


def _ragged(seed: int = 13, *, sigma: float = 0.004, band: int = 10):
    """``(rgb, coverage, trim_crop)`` for the mosaic scene on the ragged canvas a
    real mosaic stacks onto: a perimeter band that is mostly **uncovered** (NaN),
    whose covered remainder is thin — one to three subs where the panels have six
    to fifteen — and therefore ``sqrt(depth)`` grainier. ``trim_crop`` is the real
    ``largest_covered_rect`` answer for that coverage map, not a hand-written
    rectangle, so the test and the app agree about what is being thrown away.
    """
    from scipy.ndimage import uniform_filter

    img = _scene(sigma, seed=seed, mosaic=True)
    cov = _panel_coverage()
    edge = np.zeros((H, W), bool)
    edge[:band, :] = edge[-band:, :] = True
    edge[:, :band] = edge[:, -band:] = True
    rng = np.random.default_rng(seed + 7717)
    # A spatially-correlated keep mask, so the covered part of the fringe is a
    # ragged outline rather than salt-and-pepper (which `largest_covered_rect`
    # would read quite differently).
    field = uniform_filter(rng.random((H, W)).astype(np.float32), size=9)
    keep = edge & (field <= np.quantile(field[edge], _FRINGE_COVERED_SHARE))
    img[edge & ~keep] = np.nan
    cov[edge & ~keep] = 0.0
    depth = rng.integers(1, _FRINGE_DEPTH_MAX, size=int(keep.sum())).astype(np.float32)
    cov[keep] = depth
    panel_depth = float(np.median(_PANEL_FRAMES))
    img[keep] += (rng.normal(0.0, 1.0, (int(keep.sum()), 3))
                  * (sigma * np.sqrt(panel_depth / depth))[:, None]).astype(np.float32)
    return img, cov, largest_covered_rect(cov)


def _ragged_target_bg(img, cov, trim, **kw) -> float:
    """The grey Auto aims a ragged mosaic's sky at, off its own recipe."""
    rec = auto_recipe(img, median_fwhm=2.5, is_mosaic=True, trim_crop=trim,
                      coverage=cov, **kw)
    return float(next(op.params["target_bg"] for op in rec.ops
                      if op.id == "tone.stretch"))


def test_the_mosaic_scene_is_a_full_rectangle_and_cannot_see_a_border_trim():
    """Why every test above is silent about the border: this file's mosaic canvas
    has **no uncovered pixel**, so ``largest_covered_rect`` declines on it and
    Auto's own ``geometry.crop`` never runs. Stated as an assertion rather than a
    comment, in the spirit of ``tests/shapes.py``: a mosaic fixture that does not
    say what its *canvas* can vouch for cannot vouch for it.
    """
    cov = _panel_coverage()
    assert int((cov <= 0).sum()) == 0
    assert largest_covered_rect(cov) is None
    # ...while the ragged one below really is trimmable.
    _img, ragged_cov, trim = _ragged()
    assert int((ragged_cov <= 0).sum()) > 0
    assert trim is not None


def test_the_border_auto_crops_away_does_not_set_the_stretch_target():
    """The headline: the same stack, on a canvas carrying the ragged border Auto's
    own last op deletes, must aim its stretch at the same grey.

    Before this, the fringe was measured and the target grey landed **3.1 %** off
    the identical stack's at a 10 % trim (0.2243 against 0.2312) — 1.8 % at a 6 %
    trim, 3.3 % at 14 %, 8.0 % at 36 %. Two mechanisms, both in the fringe: it is
    several times grainier (thin coverage), and its coverage counts are *overlap*
    counts rather than panel identities, so one fringe bin spans several panels
    and ``_delevelled_luminance`` cannot flatten it — the panel steps v0.410.0
    removed survive inside the strip.
    """
    single = _target_bg(_scene(0.004, seed=13))
    img, cov, trim = _ragged(seed=13)
    assert _ragged_target_bg(img, cov, trim) == pytest.approx(single, rel=0.015)


@pytest.mark.parametrize("band", [6, 14])
def test_the_border_does_not_set_the_stretch_target_at_other_depths(band):
    """The same claim either side of the measured band, so the fix is a rule and
    not a constant tuned to one fixture."""
    single = _target_bg(_scene(0.004, seed=13))
    img, cov, trim = _ragged(seed=13, band=band)
    assert trim is not None
    assert _ragged_target_bg(img, cov, trim) == pytest.approx(single, rel=0.015)


def test_the_border_does_not_darken_the_finished_one_click_picture():
    """And the consequence the owner would see, on the shape he actually shoots:
    the finished one-click picture's own sky, the recipe's own crop included.

    Measured at a 10 % trim: **p30 0.1854 against the identical stack's 0.1899
    (-2.4 %)** before, 0.1913 (+0.7 %) after.
    """
    img, cov, trim = _ragged(seed=13, band=10)
    rec = auto_recipe(img, median_fwhm=2.5, is_mosaic=True, trim_crop=trim,
                      coverage=cov)
    out = apply_recipe(img, rec, EditContext(coverage=cov, frame_coverage=cov))
    sky = float(np.nanpercentile(out[..., :3].mean(axis=2), 30.0))
    assert sky == pytest.approx(_finished_sky(_scene(0.004, seed=13)), rel=0.015)


def test_auto_builds_the_recipe_the_kept_picture_itself_would_get():
    """The whole fix as one equality, and the strongest form the claim has: the
    recipe Auto builds for a ragged canvas it is going to crop must be *exactly*
    the recipe it builds when handed the cropped picture directly — same ops,
    same measured params — plus the crop that gets it there.

    That covers the grain half the stretch-target tests above do not: the denoise
    strength, the denoise↔sharpen crossfade weights and the chroma smoother's
    strength are all read from the same ``sky_sigma``, and a fringe covered once
    or twice over is several times grainier than the picture inside it. The σ this
    fixture's fringe added was enough to put ``detail.denoise`` on a picture whose
    own grain does not ask for it — the neighbour of the owner-reported
    "multicolour grid" (``detail.chroma_denoise``) at the top of this file.
    """
    img, cov, trim = _ragged(seed=13, sigma=0.012, band=14)
    h, w = img.shape[:2]
    x0, y0, x1, y1 = trim
    rows = slice(int(round(y0 * h)), int(round(y1 * h)))
    cols = slice(int(round(x0 * w)), int(round(x1 * w)))

    ragged = auto_recipe(img, median_fwhm=2.5, is_mosaic=True, trim_crop=trim,
                         coverage=cov)
    kept = auto_recipe(img[rows, cols], median_fwhm=2.5, is_mosaic=True,
                       coverage=cov[rows, cols])
    assert [(o.id, o.params) for o in ragged.ops if o.id != "geometry.crop"] == [
        (o.id, o.params) for o in kept.ops]
    # ...and the crop is the one op that is not in both, by construction.
    assert [o.id for o in ragged.ops][-1] == "geometry.crop"


def test_with_auto_crop_off_the_whole_canvas_is_measured_again():
    """The rule is "measure what the recipe keeps", not "measure the middle": with
    the owner's border-trim preference off, the fringe stays in his picture, so it
    is part of what Auto has to answer for."""
    img, cov, trim = _ragged(seed=13)
    off = auto_recipe(img, median_fwhm=2.5, is_mosaic=True, trim_crop=trim,
                      coverage=cov, auto_crop=False)
    whole = auto_recipe(img, median_fwhm=2.5, is_mosaic=True, trim_crop=None,
                        coverage=cov)
    assert [(o.id, o.params) for o in off.ops] == [
        (o.id, o.params) for o in whole.ops]


def test_a_single_field_stacks_auto_is_untouched_by_the_narrowing():
    """Upgrade safety as a property: no trim rectangle, nothing narrowed — a
    single-field stack gets byte-for-byte the recipe it got before this existed."""
    img = _scene(0.004, seed=13)
    assert [(o.id, o.params) for o in auto_recipe(img, median_fwhm=2.5).ops] == [
        (o.id, o.params)
        for o in auto_recipe(img, median_fwhm=2.5, trim_crop=None).ops]


def test_a_rectangle_with_nothing_in_it_is_declined_not_measured():
    """A sky level read off a few hundred pixels is worse than one read off a
    canvas with a fringe in it, so a degenerate rectangle — and one that keeps
    everything — both fall back to the whole canvas."""
    img, cov, _trim = _ragged(seed=13)
    whole = _ragged_target_bg(img, cov, None)
    assert _ragged_target_bg(img, cov, (0.5, 0.5, 0.51, 0.51)) == pytest.approx(
        whole, rel=1e-9)
    assert _ragged_target_bg(img, cov, (0.0, 0.0, 1.0, 1.0)) == pytest.approx(
        whole, rel=1e-9)


@pytest.mark.parametrize("bad", [
    (0.0, 0.0, float("nan"), 1.0),
    (float("inf"), 0.0, 1.0, 1.0),
    ("a", 0.0, 1.0, 1.0),
    None,
])
def test_a_rectangle_that_is_not_four_finite_numbers_is_declined(bad):
    """This sits on the editor's Auto button, so an unusable rectangle degrades to
    today's whole-canvas measurement rather than raising a 500 at a user. (A
    rectangle of the wrong *length* is a different line — ``auto_recipe``'s own
    unpack where it emits the crop — and is left exactly as it was; the only
    caller, ``editor._trim_rect_for_run``, always answers four values.)"""
    img, cov, _trim = _ragged(seed=13)
    assert _ragged_target_bg(img, cov, bad) == pytest.approx(
        _ragged_target_bg(img, cov, None), rel=1e-9)


def test_analyze_auto_inputs_reports_the_region_the_recipe_measured():
    """The reported cues exist to explain the recipe, so they have to come off the
    same pixels — otherwise the "What Auto did" note quotes a sky level the
    stretch target it sits beside cannot be derived from."""
    img, cov, trim = _ragged(seed=13)
    cues = analyze_auto_inputs(img, median_fwhm=2.5, is_mosaic=True,
                               trim_crop=trim, coverage=cov)
    kept = analyze_auto_inputs(_scene(0.004, seed=13), median_fwhm=2.5)
    assert cues["sky"] == pytest.approx(kept["sky"], abs=0.004)
    # ...and what it says was trimmed is still the whole rectangle's share.
    assert cues["trim_fraction"] == pytest.approx(
        round(1.0 - (trim[2] - trim[0]) * (trim[3] - trim[1]), 3))


# --------------------------------------------------------------------------
# ...and the *archetype* is the fourth measurement on the same pixels, which the
# first instalment did not check. `classify_target` keys Auto's taste profile
# AND the editor's "try this preset?" chip, and the chip asks it from the webapp
# (`editor.build_preset_suggestion_for_run`) rather than through `auto_recipe`,
# so it was left reading the canvas while the three measurements inside this
# module moved to the kept rectangle.
# --------------------------------------------------------------------------

def _archetypes(band: int, seed: int, sigma: float = 0.02):
    """``(whole_canvas, kept_rectangle)`` verdicts for one ragged canvas."""
    img, cov, trim = _ragged(seed=seed, sigma=sigma, band=band)
    assert trim is not None
    return (classify_target(img, cov),
            classify_target(*measured_region(img, cov, trim)))


def test_the_fringe_really_does_walk_the_archetype_toward_a_star_cluster():
    """The premise, so this fixture cannot go blind the way the editor's re-audits
    did (``docs/HISTORY.md``): the ragged border has to be *able* to change the
    verdict, or the invariance below holds for nothing.

    The mechanism is the one ``classify_target``'s own docstring records for a
    mosaic's panel steps, arriving by the other door: the fringe is one to three
    subs deep where the panels are six to fifteen, that grain inflates the
    ``6·sky_sigma`` term of the signal threshold, and faint diffuse structure
    disappears under it — so ``ext_frac`` falls, ``star_share`` rises, and a
    nebulous field reads as a star cluster. Measured over these six canvases
    (σ = 0.02): whole-canvas **cluster on 5**, kept-rectangle on **0**.
    """
    pairs = [_archetypes(band, seed)
             for band in (14, 20, 24) for seed in (34, 89)]
    whole_cluster = sum(1 for w, _k in pairs if w["cls"] == "cluster")
    kept_cluster = sum(1 for _w, k in pairs if k["cls"] == "cluster")
    assert whole_cluster >= 4, whole_cluster      # the fringe can say "cluster"
    assert kept_cluster < whole_cluster           # ...and the kept picture does not
    # The direction of both cues, on every one of them — the mechanism, not the
    # tally, so a numerics change that moves a verdict still has to move these.
    for w, k in pairs:
        assert k["cues"]["star_share"] < w["cues"]["star_share"]
        assert k["cues"]["ext_frac"] >= w["cues"]["ext_frac"]


def test_classifying_a_ragged_canvas_answers_what_the_kept_picture_answers():
    """The archetype half of ``test_auto_builds_the_recipe_the_kept_picture_itself
    _would_get``: narrowing and then classifying must give *exactly* what handing
    the classifier the cropped picture gives, cues included — which is also what
    pins ``measured_region``'s rounding against a plain slice.
    """
    img, cov, trim = _ragged(seed=89, sigma=0.02, band=20)
    h, w = img.shape[:2]
    x0, y0, x1, y1 = trim
    rows = slice(int(round(y0 * h)), int(round(y1 * h)))
    cols = slice(int(round(x0 * w)), int(round(x1 * w)))

    assert (classify_target(*measured_region(img, cov, trim))
            == classify_target(img[rows, cols], cov[rows, cols]))


def test_with_auto_crop_off_the_whole_canvas_is_classified_again():
    """Same rule as the recipe's: with the owner's border-trim preference off no
    crop runs, the fringe stays in the picture the editor shows, and the whole
    canvas is the honest thing to classify. ``measured_region`` is handed ``None``
    for the rectangle in that case, which is what makes this one line."""
    img, cov, _trim = _ragged(seed=89, sigma=0.02, band=20)
    assert (classify_target(*measured_region(img, cov, None))
            == classify_target(img, cov))
