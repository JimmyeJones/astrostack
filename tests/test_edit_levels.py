"""Data-driven black/white points for the Levels op (seestack/edit/levels.py)."""

from __future__ import annotations

import numpy as np

from seestack.edit.levels import suggest_levels_points


def _scene(black_floor=0.15, bright=0.9, h=120, w=160, seed=0):
    """A display-space image: a dim sky floor with a bright blob, so the low
    percentile lands near the floor and the high one near the highlight."""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:h, 0:w]
    signal = (bright - black_floor) * np.exp(
        -(((xx - w / 2) / 15) ** 2 + ((yy - h / 2) / 15) ** 2))
    img = black_floor + signal[..., None] + rng.normal(0.0, 0.01, (h, w, 3))
    return np.clip(img, 0.0, 1.0).astype("float32")


def test_black_tracks_sky_and_white_tracks_highlights():
    pts = suggest_levels_points(_scene(black_floor=0.15, bright=0.9))
    assert pts is not None
    black, white = pts
    # Black lands just above the sky floor; white just below the brightest cores.
    assert 0.1 < black < 0.25
    assert 0.5 < white <= 1.0
    assert white > black


def test_brighter_sky_raises_the_black_point():
    dim = suggest_levels_points(_scene(black_floor=0.1))
    bright = suggest_levels_points(_scene(black_floor=0.35))
    assert dim is not None and bright is not None
    assert bright[0] > dim[0]


def test_points_are_clamped_and_rounded():
    black, white = suggest_levels_points(_scene())
    assert 0.0 <= black <= 1.0 and 0.0 <= white <= 1.0
    # rounded to 3 decimals
    assert round(black, 3) == black and round(white, 3) == white


def test_nan_uncovered_pixels_are_ignored():
    img = _scene()
    img[:20, :, :] = np.nan  # a mosaic-edge NaN band
    pts = suggest_levels_points(img)
    assert pts is not None
    assert np.isfinite(pts[0]) and np.isfinite(pts[1])


def test_returns_none_when_range_is_degenerate():
    # A flat image (no dynamic range) → black≈white → no useful suggestion.
    flat = np.full((60, 60, 3), 0.3, dtype="float32")
    assert suggest_levels_points(flat) is None
    # All-NaN (uncovered) → too few finite pixels.
    allnan = np.full((60, 60, 3), np.nan, dtype="float32")
    assert suggest_levels_points(allnan) is None
