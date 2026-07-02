"""Direct pixel-transform tests for editor ops that had none.

seestack/bg/per_frame.py, final_gradient.py, and coverage_leveling.py each
have their own dedicated test files already covering the underlying math.
What's untested is the thin seestack/edit/ops wrapper around them: does it
actually forward recipe params through to the underlying function, and does
its own wrapper-only logic (the ctx.coverage-is-None early return, NaN
handling) behave correctly? seestack/edit/ops/stars.py has no underlying
module test at all — its erosion-based reduction is only exercised here.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("astropy")
pytest.importorskip("photutils")
pytest.importorskip("scipy")

from seestack.edit.registry import EditContext, get_op


def _flat_field_with_star(h=40, w=40, sky=0.2, peak=0.9, cx=20, cy=20):
    rgb = np.full((h, w, 3), sky, dtype=np.float32)
    rgb[cy - 1:cy + 2, cx - 1:cx + 2, :] = peak
    return rgb


# ---- stars.reduce ---------------------------------------------------------

def test_stars_reduce_shrinks_peak_leaves_background():
    rgb = _flat_field_with_star()
    op = get_op("stars.reduce")
    out = op.apply(rgb, {"amount": 0.8, "size": 2}, EditContext())

    assert out[20, 20, 0] < rgb[20, 20, 0], "star core should be pulled down"
    # Far from the star, the flat background must be untouched.
    assert np.allclose(out[2:6, 2:6, :], rgb[2:6, 2:6, :])


def test_stars_reduce_amount_zero_is_noop():
    rgb = _flat_field_with_star()
    op = get_op("stars.reduce")
    out = op.apply(rgb, {"amount": 0.0, "size": 2}, EditContext())
    assert np.array_equal(out, rgb)


def test_stars_reduce_larger_amount_reduces_more():
    rgb = _flat_field_with_star()
    op = get_op("stars.reduce")
    mild = op.apply(rgb, {"amount": 0.2, "size": 2}, EditContext())
    strong = op.apply(rgb, {"amount": 1.0, "size": 2}, EditContext())
    assert strong[20, 20, 0] < mild[20, 20, 0]


def test_stars_reduce_preserves_nan_gaps():
    rgb = _flat_field_with_star()
    rgb[:5, :, :] = np.nan  # e.g. an uncovered mosaic border
    op = get_op("stars.reduce")
    out = op.apply(rgb, {"amount": 0.8, "size": 2}, EditContext())
    assert np.all(np.isnan(out[:5, :, :]))


# ---- background.subtract ---------------------------------------------------

def _gradient_field(h=200, w=280, seed=7):
    rng = np.random.default_rng(seed)
    yy, xx = np.indices((h, w), dtype=np.float32)
    grad = (xx / w) * 200 + 1000
    noise = rng.normal(0, 8, size=(h, w)).astype(np.float32)
    return np.repeat((grad + noise)[..., None], 3, axis=-1)


def test_background_subtract_flattens_gradient():
    rgb = _gradient_field()
    op = get_op("background.subtract")
    out = op.apply(rgb, {"box_size": 32, "mode": "per_channel"}, EditContext())
    # Flattening should shrink the corner-to-corner spread a lot.
    assert (out[:, -1, 0].mean() - out[:, 0, 0].mean()) < (rgb[:, -1, 0].mean() - rgb[:, 0, 0].mean()) * 0.3


def test_background_subtract_forwards_box_size_param():
    rgb = _gradient_field()
    op = get_op("background.subtract")
    small_box = op.apply(rgb, {"box_size": 32}, EditContext())
    large_box = op.apply(rgb, {"box_size": 256}, EditContext())
    # Different box sizes fit a different background model — results diverge.
    assert not np.allclose(small_box, large_box, atol=1e-3)


# ---- background.final_gradient --------------------------------------------

def _gradient_with_bright_object(h=200, w=280, seed=3):
    rgb = _gradient_field(h, w, seed)
    rgb[h // 2 - 10:h // 2 + 10, w // 2 - 10:w // 2 + 10, :] += 4000.0
    return rgb


def test_final_gradient_flattens_sky_and_keeps_object_bright():
    rgb = _gradient_with_bright_object()
    op = get_op("background.final_gradient")
    out = op.apply(rgb, {"mode": "luminance", "box_size": 64}, EditContext())
    # The fitted background model should collapse the whole-frame median
    # close to zero even though the input had a ~200 ADU gradient baseline.
    assert abs(float(np.median(out[..., 0]))) < 60
    # The masked object should still stand out above the flattened sky.
    obj = out[90:110, 130:150, 0].mean()
    sky = out[5:15, 5:15, 0].mean()
    assert obj - sky > 2000.0


# ---- background.level_coverage ---------------------------------------------

def test_level_coverage_is_noop_without_coverage_in_context():
    rgb = _gradient_field()
    op = get_op("background.level_coverage")
    out = op.apply(rgb, {}, EditContext(coverage=None))
    assert np.array_equal(out, rgb)


def test_level_coverage_uses_context_coverage_to_flatten_panel_offsets():
    h, w = 120, 240
    rng = np.random.default_rng(1)
    rgb = rng.normal(0.0, 5.0, size=(h, w, 3)).astype(np.float32)
    coverage = np.zeros((h, w), dtype=np.int32)
    coverage[:, w // 2:] = 3
    rgb[:, w // 2:, :] += 200.0  # right half panel sits 200 ADU brighter

    op = get_op("background.level_coverage")
    out = op.apply(rgb, {}, EditContext(coverage=coverage))

    before_gap = abs(rgb[:, w // 2:, 0].mean() - rgb[:, :w // 2, 0].mean())
    after_gap = abs(out[:, w // 2:, 0].mean() - out[:, :w // 2, 0].mean())
    assert after_gap < before_gap * 0.3
