"""Data-driven Strength + Black point for the asinh Stretch op
(seestack/edit/stretch.py)."""

from __future__ import annotations

import numpy as np

from seestack.edit.stretch import STRETCH_TARGET_BG, suggest_asinh_stretch
from seestack.render.thumbnail import asinh_stretch


def _linear_scene(sky=1000.0, sig=40.0, star_max=30000.0, n_stars=60, h=180, w=220,
                  seed=0):
    """A *linear* stacked-image proxy: a faint sky background, a soft nebula, and
    a scatter of near-saturated stars that set the dynamic-range ceiling (as a
    real Seestar stack does).

    Stars are rendered as small Gaussian PSF blobs, not single pixels: a real
    stack's bright-star population is a genuine (few-percent) tail, not a lone
    hot pixel. `asinh_stretch` (and this suggestion) scales the top of the range
    by a robust 99.5th percentile so a single non-physical outlier can't crush
    the image — so the fixture must model stars as a real population, or it would
    conflate "star" with "hot pixel" and the robust ceiling would clip them all."""
    rng = np.random.default_rng(seed)
    img = rng.normal(sky, sig, size=(h, w, 3)).astype(np.float32)
    yy, xx = np.mgrid[0:h, 0:w]
    neb = 400.0 * np.exp(-(((xx - w * 0.5) / 45) ** 2 + ((yy - h * 0.5) / 45) ** 2))
    img[..., 0] += neb
    img[..., 1] += neb * 0.7
    img[..., 2] += neb * 0.4
    r = 3
    dy, dx = np.mgrid[-r:r + 1, -r:r + 1]
    psf = np.exp(-((dy ** 2 + dx ** 2) / (2 * 1.6 ** 2)))
    for _ in range(n_stars):
        cy = int(rng.integers(r, h - r))
        cx = int(rng.integers(r, w - r))
        amp = rng.uniform(star_max * 0.3, star_max)
        img[cy - r:cy + r + 1, cx - r:cx + r + 1, :] += (amp * psf)[..., None]
    return img


def _sky_median(out: np.ndarray) -> float:
    finite = out[np.isfinite(out)]
    return float(np.median(finite))


def test_suggestion_lands_the_sky_near_the_target_grey():
    img = _linear_scene(star_max=20000.0)
    sug = suggest_asinh_stretch(img)
    assert sug is not None
    stretch, black = sug
    assert 0.0 <= stretch <= 1.0 and 0.0 <= black <= 1.0
    # Applying the suggested asinh values lands the sky median close to the
    # target — the whole point of the suggestion. (Moderate dynamic range, so it
    # doesn't clamp.)
    out = asinh_stretch(img, stretch=stretch, black=black)
    assert abs(_sky_median(out) - STRETCH_TARGET_BG) < 0.03


def test_higher_dynamic_range_needs_more_strength():
    dim = suggest_asinh_stretch(_linear_scene(star_max=20000.0, seed=1))
    bright = suggest_asinh_stretch(_linear_scene(star_max=60000.0, seed=1))
    assert dim is not None and bright is not None
    # Brighter stars compress the sky further, so more lift (strength) is needed.
    assert bright[0] >= dim[0]


def test_strength_clamps_to_max_on_extreme_dynamic_range():
    # A near-saturated star far above the sky compresses it below what even full
    # asinh strength can reach, so the suggestion correctly maxes out at 1.0.
    img = _linear_scene(sky=800.0, sig=25.0, star_max=100000.0, seed=2)
    sug = suggest_asinh_stretch(img)
    assert sug is not None
    assert sug[0] == 1.0


def test_values_are_clamped_and_rounded():
    stretch, black = suggest_asinh_stretch(_linear_scene())
    assert 0.0 <= stretch <= 1.0 and 0.0 <= black <= 1.0
    assert round(stretch, 3) == stretch and round(black, 3) == black


def test_nan_uncovered_pixels_are_ignored():
    img = _linear_scene()
    img[:30, :40, :] = np.nan  # a mosaic-gap NaN block
    sug = suggest_asinh_stretch(img)
    assert sug is not None
    assert np.isfinite(sug[0]) and np.isfinite(sug[1])


def test_returns_none_when_there_is_no_dynamic_range():
    # A flat image (hi == lo) → nothing to expose.
    flat = np.full((60, 60, 3), 1000.0, dtype=np.float32)
    assert suggest_asinh_stretch(flat) is None
    # All-NaN (uncovered) → too few finite pixels.
    allnan = np.full((60, 60, 3), np.nan, dtype=np.float32)
    assert suggest_asinh_stretch(allnan) is None
    # Too few pixels.
    assert suggest_asinh_stretch(np.ones((3, 3, 3), dtype=np.float32)) is None


def test_bad_target_returns_none():
    img = _linear_scene()
    assert suggest_asinh_stretch(img, target_bg=0.0) is None
    assert suggest_asinh_stretch(img, target_bg=1.0) is None
