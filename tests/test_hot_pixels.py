"""Hot/cold pixel suppression."""

import numpy as np
import pytest

pytest.importorskip("scipy")

from seestack.bg.hot_pixels import suppress_hot_cold_pixels


def test_hot_pixel_replaced_with_neighbourhood():
    rng = np.random.default_rng(0)
    rgb = rng.normal(loc=1000, scale=10, size=(64, 64, 3)).astype(np.float32)
    # Plant a hot pixel.
    rgb[32, 32, 1] = 60000.0
    out = suppress_hot_cold_pixels(rgb, sigma=5.0, use_gpu=False)
    # The hot pixel should be brought close to its neighbours.
    assert out[32, 32, 1] < 1500
    # Untouched neighbours.
    np.testing.assert_allclose(out[10, 10, 1], rgb[10, 10, 1], atol=1.0)


def test_cold_pixel_replaced():
    rng = np.random.default_rng(1)
    rgb = rng.normal(loc=1000, scale=10, size=(64, 64, 3)).astype(np.float32)
    rgb[40, 20, 0] = -50000.0
    out = suppress_hot_cold_pixels(rgb, sigma=5.0, use_gpu=False)
    assert out[40, 20, 0] > 500


def test_constant_image_passthrough():
    rgb = np.full((32, 32, 3), 1000.0, dtype=np.float32)
    out = suppress_hot_cold_pixels(rgb, sigma=5.0, use_gpu=False)
    np.testing.assert_array_equal(out, rgb)


def test_suppression_still_works_with_nan_coverage_gap():
    """Regression: a NaN coverage gap (mosaic / partial overlap) must not disable
    the whole suppression. Previously the noise floor was a non-NaN-aware median
    over the residual, so any NaN made the threshold NaN and the pass no-op'd —
    every hot/cold pixel survived into the stack."""
    rng = np.random.default_rng(3)
    rgb = rng.normal(loc=100.0, scale=3.0, size=(64, 64, 3)).astype(np.float32)
    rgb[20, 30, :] = 6000.0  # hot pixels away from the gap
    rgb[40, 50, :] = 6000.0
    rgb[:, :10, :] = np.nan  # an uncovered region (NaN = no coverage)
    out = suppress_hot_cold_pixels(rgb, sigma=5.0, use_gpu=False)
    # Hot pixels are repaired to the local sky despite the gap (were ~6000 before).
    assert out[20, 30, 1] < 500
    assert out[40, 50, 1] < 500
    # The coverage gap is preserved as NaN (never turned into zeros/finite values).
    assert np.isnan(out[5, 5, 0])
    assert np.isfinite(out[:, 10:, :]).all()


def test_all_nan_channel_is_left_untouched():
    """A fully-uncovered channel has no valid residual to estimate noise from —
    it must be skipped cleanly, not crash or emit spurious values."""
    rgb = np.full((16, 16, 3), np.nan, dtype=np.float32)
    out = suppress_hot_cold_pixels(rgb, sigma=5.0, use_gpu=False)
    assert np.isnan(out).all()


def test_many_hot_pixels():
    """Field of dozens of hot pixels should all get suppressed."""
    rng = np.random.default_rng(2)
    rgb = rng.normal(loc=1000, scale=10, size=(128, 128, 3)).astype(np.float32)
    # Plant 30 random hot pixels.
    ys = rng.integers(2, 126, size=30)
    xs = rng.integers(2, 126, size=30)
    rgb[ys, xs, 1] += 20000
    out = suppress_hot_cold_pixels(rgb, sigma=5.0, use_gpu=False)
    # After suppression, none of the planted pixels should still be > 10000 ADU
    # above the local sky.
    for y, x in zip(ys, xs):
        assert out[y, x, 1] - 1000 < 5000
