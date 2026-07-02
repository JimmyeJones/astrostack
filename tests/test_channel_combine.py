"""LRGB / RGB channel combination."""

from __future__ import annotations

import numpy as np
import pytest

from seestack.stack.channel_combine import combine_channels


def test_rgb_combine_places_channels():
    r = np.full((4, 4), 0.8, dtype=np.float32)
    g = np.full((4, 4), 0.4, dtype=np.float32)
    b = np.full((4, 4), 0.2, dtype=np.float32)
    out = combine_channels({"R": r, "G": g, "B": b})
    assert out.shape == (4, 4, 3)
    np.testing.assert_allclose(out[..., 0], 0.8)
    np.testing.assert_allclose(out[..., 1], 0.4)
    np.testing.assert_allclose(out[..., 2], 0.2)


def test_weights_scale_channels():
    r = np.ones((2, 2), dtype=np.float32)
    out = combine_channels({"R": r, "G": r, "B": r}, weights={"R": 2.0, "B": 0.5})
    np.testing.assert_allclose(out[..., 0], 2.0)
    np.testing.assert_allclose(out[..., 1], 1.0)
    np.testing.assert_allclose(out[..., 2], 0.5)


def test_lum_only_is_grayscale():
    lum = np.array([[0.1, 0.2], [0.3, 0.4]], dtype=np.float32)
    out = combine_channels({"L": lum})
    for c in range(3):
        np.testing.assert_allclose(out[..., c], lum)


def test_lrgb_sets_luminance_keeps_colour_ratio():
    # RGB with a fixed colour ratio; L doubles the brightness.
    r = np.full((3, 3), 0.4, dtype=np.float32)
    g = np.full((3, 3), 0.2, dtype=np.float32)
    b = np.full((3, 3), 0.2, dtype=np.float32)
    rgb = combine_channels({"R": r, "G": g, "B": b})
    base_lum = 0.2126 * 0.4 + 0.7152 * 0.2 + 0.0722 * 0.2
    target = np.full((3, 3), base_lum * 2.0, dtype=np.float32)
    out = combine_channels({"R": r, "G": g, "B": b, "L": target})
    # Luminance is now 2× and colour ratios are preserved (each channel doubled).
    np.testing.assert_allclose(out[..., 0], 0.8, rtol=1e-4)
    np.testing.assert_allclose(out[..., 1], 0.4, rtol=1e-4)
    np.testing.assert_allclose(out[..., 2], 0.4, rtol=1e-4)


def test_shape_mismatch_raises():
    with pytest.raises(ValueError, match="same canvas"):
        combine_channels({"R": np.ones((4, 4), np.float32),
                          "G": np.ones((2, 2), np.float32)})


def test_empty_raises():
    with pytest.raises(ValueError):
        combine_channels({})


def test_missing_colour_channel_is_zero():
    out = combine_channels({"R": np.ones((2, 2), np.float32),
                            "B": np.ones((2, 2), np.float32)})
    np.testing.assert_allclose(out[..., 1], 0.0)  # no green supplied


# ---- NaN / coverage semantics (NaN = "no coverage") ---------------------

def test_rgb_uncovered_pixel_stays_nan():
    # A pixel uncovered (NaN) in every supplied colour channel must remain NaN
    # across all output channels — never silently become 0 (a valid dark pixel).
    nan = np.nan
    r = np.array([[1.0, nan]], np.float32)
    g = np.array([[1.0, nan]], np.float32)
    b = np.array([[1.0, nan]], np.float32)
    out = combine_channels({"R": r, "G": g, "B": b})
    assert np.all(np.isnan(out[0, 1]))
    assert np.all(np.isfinite(out[0, 0]))


def test_lum_only_preserves_nan():
    lum = np.array([[0.3, np.nan]], np.float32)
    out = combine_channels({"L": lum})
    assert np.all(np.isnan(out[0, 1]))
    np.testing.assert_allclose(out[0, 0], 0.3)


def test_lrgb_uncovered_luminance_pixel_is_nan():
    # L uncovered at a pixel → that pixel has no defined brightness → NaN.
    r = np.full((1, 2), 0.4, np.float32)
    g = np.full((1, 2), 0.2, np.float32)
    b = np.full((1, 2), 0.2, np.float32)
    lum = np.array([[0.3, np.nan]], np.float32)
    out = combine_channels({"R": r, "G": g, "B": b, "L": lum})
    assert np.all(np.isnan(out[0, 1]))
    assert np.all(np.isfinite(out[0, 0]))


def test_lrgb_partial_colour_coverage_pixel_is_fully_nan():
    # Regression: at a mosaic-edge pixel covered in G/B/L but NOT R, the colour
    # is undefined. It must become fully uncovered (all NaN), not [NaN, 0, 0]
    # which would zero-out the G/B signal that *was* covered.
    r = np.array([[0.4, np.nan]], np.float32)
    g = np.array([[0.2, 0.2]], np.float32)
    b = np.array([[0.2, 0.2]], np.float32)
    lum = np.array([[0.3, 0.3]], np.float32)
    out = combine_channels({"R": r, "G": g, "B": b, "L": lum})
    assert np.all(np.isnan(out[0, 1]))  # not [nan, 0, 0]


def test_lrgb_black_but_covered_pixel_stays_black_not_nan():
    # A genuinely dark (RGB≈0) but *covered* pixel must stay finite (0), not be
    # confused with an uncovered NaN pixel.
    zeros = np.zeros((1, 1), np.float32)
    lum = np.array([[0.5]], np.float32)
    out = combine_channels({"R": zeros, "G": zeros, "B": zeros, "L": lum})
    assert np.all(np.isfinite(out[0, 0]))
    np.testing.assert_allclose(out[0, 0], 0.0)


def test_single_pixel_combine():
    # Degenerate 1×1 canvas must not crash any path.
    out = combine_channels({"R": np.array([[0.5]], np.float32),
                            "G": np.array([[0.4]], np.float32),
                            "B": np.array([[0.3]], np.float32),
                            "L": np.array([[0.6]], np.float32)})
    assert out.shape == (1, 1, 3)
    assert np.all(np.isfinite(out))
