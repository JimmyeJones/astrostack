"""Star mask + star-mask-aware editor ops."""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("scipy")

from seestack.edit.registry import EditContext, get_op
from seestack.edit.starmask import star_mask


def _star_and_nebula(h=80, w=80):
    """A scene with a faint extended blob (nebula) and a few sharp stars."""
    yy, xx = np.mgrid[0:h, 0:w]
    img = np.full((h, w), 0.05, dtype=np.float32)
    # Broad smooth nebula in the centre.
    img += 0.3 * np.exp(-(((xx - w / 2) / 18) ** 2 + ((yy - h / 2) / 18) ** 2))
    # A few compact bright stars.
    stars = [(15, 20), (60, 25), (40, 65)]
    for (sy, sx) in stars:
        img += 0.9 * np.exp(-(((xx - sx) / 1.0) ** 2 + ((yy - sy) / 1.0) ** 2))
    rgb = np.stack([img, img, img], axis=-1)
    return np.clip(rgb, 0, 1), stars


def test_star_mask_hot_on_stars_cold_on_nebula():
    rgb, stars = _star_and_nebula()
    m = star_mask(rgb, size_px=3.0)
    assert m.shape == rgb.shape[:2]
    assert m.min() >= 0 and m.max() <= 1.0
    # High at a star, low at the nebula centre.
    for (sy, sx) in stars:
        assert m[sy, sx] > 0.4, (sy, sx, m[sy, sx])
    assert m[40, 40] < 0.2  # nebula core


def test_star_mask_handles_nan_coverage():
    rgb, _ = _star_and_nebula()
    rgb = rgb.copy()
    rgb[:10, :, :] = np.nan
    m = star_mask(rgb, size_px=3.0)
    assert np.isfinite(m).all()
    assert (m[:10, :] == 0).all()  # uncovered → 0


def test_star_mask_empty_image_is_zero():
    rgb = np.full((20, 20, 3), np.nan, dtype=np.float32)
    m = star_mask(rgb, size_px=3.0)
    assert (m == 0).all()


def test_reduce_dims_stars_more_than_nebula():
    rgb, stars = _star_and_nebula()
    spec = get_op("stars.reduce")
    out = spec.apply(rgb, {"amount": 1.0, "size": 2}, EditContext())
    # Stars should drop noticeably.
    for (sy, sx) in stars:
        assert out[sy, sx, 0] < rgb[sy, sx, 0] - 0.1
    # Nebula core should be essentially preserved (protected by the mask).
    assert abs(out[40, 40, 0] - rgb[40, 40, 0]) < 0.05


def test_reduce_protect_off_still_runs():
    rgb, _ = _star_and_nebula()
    spec = get_op("stars.reduce")
    out = spec.apply(rgb, {"amount": 0.5, "size": 2, "protect_nebula": False}, EditContext())
    assert out.shape == rgb.shape
    assert np.isfinite(out).all()


def test_boost_nebula_lifts_background_not_stars():
    rgb, stars = _star_and_nebula()
    spec = get_op("stars.boost_nebula")
    out = spec.apply(rgb, {"amount": 0.8, "size": 4}, EditContext())
    # Nebula region brightens.
    assert out[40, 40, 0] > rgb[40, 40, 0] + 0.02
    # Star cores barely move.
    for (sy, sx) in stars:
        assert abs(out[sy, sx, 0] - rgb[sy, sx, 0]) < 0.1


def test_boost_nebula_zero_amount_is_noop():
    rgb, _ = _star_and_nebula()
    spec = get_op("stars.boost_nebula")
    out = spec.apply(rgb, {"amount": 0.0}, EditContext())
    np.testing.assert_allclose(out, rgb, atol=1e-6)


def test_ops_registered_in_schema():
    from seestack.edit.registry import all_specs
    ids = {s.id for s in all_specs()}
    assert "stars.boost_nebula" in ids
