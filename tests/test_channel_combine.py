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
