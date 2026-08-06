"""The "Hold back highlights" knob's from-your-image partner.

``tone.stretch``'s ``highlights`` slider only ever moved when the owner noticed a
washed-out core; ``seestack.edit.highlights`` measures whether the core really is
blown *by the stretch* (rather than saturated at capture) and solves the smallest
slider step that reopens it, so the knob gets the same one-click partner sharpen
and denoise have.
"""

import numpy as np
import pytest

from seestack.edit import highlights as hl
from seestack.render.thumbnail import asinh_stretch, autostretch


def _target(h=300, w=300, core_sigma=4.0, core_amp=60000.0, saturate_at=None):
    """Bright compact core on a faint extended disk on a noisy sky — the
    M31-style shape that blows out. ``saturate_at`` clips the *linear* data, i.e.
    a core that was already saturated at capture."""
    yy, xx = np.mgrid[0:h, 0:w]
    r2 = (yy - h / 2) ** 2 + (xx - w / 2) ** 2
    disk = 1500.0 * np.exp(-r2 / (2 * 60.0**2))
    core = core_amp * np.exp(-r2 / (2 * core_sigma**2))
    rng = np.random.default_rng(0)
    base = 1000.0 + disk + core + rng.normal(0.0, 20.0, size=(h, w))
    if saturate_at is not None:
        base = np.minimum(base, saturate_at)
    return np.stack([base, base, base], axis=-1).astype(np.float32)


def _stf(img):
    return lambda p: autostretch(img, highlight_protect=p)


def _asinh(img):
    return lambda p: asinh_stretch(img, highlight_protect=p)


def test_suggests_a_strength_for_a_stretch_blown_core():
    """The case the knob exists for: a core with real structure in the linear
    data that the stretch renders as flat white."""
    img = _target()
    found = hl.suggest_highlight_protect(img, _stf(img))
    assert found is not None
    assert 0.0 < found.strength <= 1.0
    assert found.flat_fraction >= hl._MIN_SEVERITY
    assert found.core_px > 0


def test_the_suggested_strength_really_reopens_the_core():
    """The number is *solved*, not mapped — so applying it must do the thing the
    button promises, and the step below it must not already have."""
    img = _target()
    found = hl.suggest_highlight_protect(img, _stf(img))
    assert found is not None
    core, structure, area = hl.measure_blown_core(autostretch(img), img)

    def flat_at(p):
        return hl._recoverable_flat_fraction(
            autostretch(img, highlight_protect=p), core, structure, area)

    assert flat_at(found.strength) <= hl._TARGET_FLAT
    # Smallest step that does the job: one step down still leaves the core blown
    # (unless the suggestion is already the slider's floor).
    below = round(found.strength - hl._STRENGTH_STEP, 2)
    if below >= hl._STRENGTH_MIN:
        assert flat_at(below) > hl._TARGET_FLAT


def test_a_core_saturated_at_capture_gets_no_suggestion():
    """Holding the highlights back can't recover a gradient the data never had —
    it would only darken the core. Say nothing instead of promising a rescue."""
    img = _target(core_sigma=12.0, saturate_at=3000.0)
    assert hl.suggest_highlight_protect(img, _stf(img)) is None


def test_an_image_with_no_bright_core_gets_no_suggestion():
    """The button must self-hide rather than imply the picture has a problem."""
    img = _target(core_amp=0.0)
    assert hl.suggest_highlight_protect(img, _stf(img)) is None
    assert hl.suggest_highlight_protect(img, _asinh(img)) is None


def test_a_star_field_is_not_mistaken_for_a_blown_core():
    """Saturated *stars* are normal and are not what the knob is for — only a
    core big enough to be an object qualifies."""
    rng = np.random.default_rng(3)
    base = 1000.0 + rng.normal(0.0, 20.0, size=(300, 300))
    for _ in range(80):
        y, x = rng.integers(5, 295, 2)
        base[y - 1:y + 2, x - 1:x + 2] += 60000.0
    img = np.stack([base, base, base], axis=-1).astype(np.float32)
    assert hl.suggest_highlight_protect(img, _stf(img)) is None


def test_no_suggestion_when_the_knob_cannot_meaningfully_help():
    """On a very high-contrast frame the midtones transfer squashes the whole
    shoulder back together, so even full strength barely moves the core. A button
    that does nothing is worse than no button."""
    img = _target(core_sigma=22.0, core_amp=6e6)
    assert hl.suggest_highlight_protect(img, _stf(img)) is None


def test_works_on_the_manual_asinh_curve_too():
    """The blow-out is a property of the shared highlight shoulder, so the
    suggestion is not STF-only."""
    img = _target()
    found = hl.suggest_highlight_protect(img, _asinh(img))
    assert found is not None
    assert 0.0 < found.strength <= 1.0


def test_uncovered_mosaic_pixels_do_not_break_the_measurement():
    """NaN = no coverage. It must neither count as a flat core nor poison the
    gradient of its neighbours."""
    img = _target()
    img[:40, :] = np.nan
    found = hl.suggest_highlight_protect(img, _stf(img))
    assert found is not None
    assert found.core_px > 0


def test_degenerate_inputs_return_no_suggestion_rather_than_raising():
    """The proxy can be tiny, empty, or all-NaN — none of that may raise."""
    for img in (np.zeros((4, 4, 3), np.float32),
                np.full((80, 80, 3), np.nan, np.float32),
                np.ones((80, 80, 3), np.float32)):
        assert hl.suggest_highlight_protect(img, _stf(img)) is None


def test_strength_grid_is_the_ops_own_slider_steps():
    """A suggestion the slider can't represent would show as 'not at the
    suggestion' forever."""
    grid = hl._strength_grid()
    assert grid[0] == pytest.approx(hl._STRENGTH_MIN)
    assert grid[-1] == pytest.approx(hl._STRENGTH_MAX)
    assert all(round(v / hl._STRENGTH_STEP) * hl._STRENGTH_STEP == pytest.approx(v)
               for v in grid)


def test_local_gradient_ignores_non_finite_neighbours():
    """A NaN neighbour contributes no information instead of making the whole
    neighbourhood NaN (which np.gradient would)."""
    values = np.array([[1.0, 1.0, 1.0],
                       [1.0, np.nan, 1.0],
                       [1.0, 1.0, 5.0]], dtype=np.float32)
    grad = hl._local_gradient(values)
    assert np.isfinite(grad).all()
    assert grad[0, 0] == pytest.approx(0.0)      # flat corner stays flat
    assert grad[2, 2] > 3.0                      # the real step is still seen
