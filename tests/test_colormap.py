"""Tests for the pure viridis colour map used by the coverage-map overlay."""

import numpy as np

from seestack.render.colormap import apply_viridis, viridis_lut


def test_viridis_lut_shape_and_endpoints():
    lut = viridis_lut()
    assert lut.shape == (256, 3)
    assert lut.dtype == np.uint8
    # Low end is dark blue/purple, high end is yellow (viridis endpoints).
    assert tuple(lut[0]) == (68, 1, 84)
    assert tuple(lut[-1]) == (253, 231, 37)


def test_viridis_lut_is_monotone_in_brightness():
    # Perceived brightness rises monotonically low→high across viridis.
    lut = viridis_lut().astype(np.float64)
    lum = lut @ np.array([0.299, 0.587, 0.114])
    assert np.all(np.diff(lum) >= -1e-6)


def test_apply_viridis_maps_range_and_shape():
    norm = np.array([[0.0, 0.5, 1.0]], dtype=np.float32)
    rgb = apply_viridis(norm)
    assert rgb.shape == (1, 3, 3)
    assert rgb.dtype == np.uint8
    assert tuple(rgb[0, 0]) == (68, 1, 84)      # low → dark
    assert tuple(rgb[0, 2]) == (253, 231, 37)   # high → yellow


def test_apply_viridis_handles_nan_and_out_of_range():
    norm = np.array([[np.nan, -0.5, 2.0]], dtype=np.float32)
    rgb = apply_viridis(norm)
    # NaN and negatives clamp to the low end; >1 clamps to the high end.
    assert tuple(rgb[0, 0]) == (68, 1, 84)
    assert tuple(rgb[0, 1]) == (68, 1, 84)
    assert tuple(rgb[0, 2]) == (253, 231, 37)
