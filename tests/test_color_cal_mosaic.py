"""
Color calibration on a mosaic-style canvas (large NaN no-data regions).

Regression for the "stuck on photometric color calibration 0/1" hang: on the
mosaic union canvas, zero-filling the uncovered NaN regions collapsed the sky
sigma estimate, the detection threshold went to ~0, and DAOStarFinder flagged
hundreds of thousands of noise pixels — then aperture photometry crawled
through all of them.
"""

import time

import numpy as np
import pytest

pytest.importorskip("astropy")
pytest.importorskip("photutils")

from seestack.post.color_cal import (
    MAX_CALIBRATION_STARS,
    ColorCalibrationOptions,
    _detect_calibration_stars,
    calibrate_color,
)


def _mosaic_like_image(h=600, w=900, *, gap_fraction=0.55, n_stars=120, seed=0):
    """A starfield where ``gap_fraction`` of the canvas is NaN (uncovered)."""
    rng = np.random.default_rng(seed)
    img = rng.normal(1000.0, 25.0, size=(h, w, 3)).astype(np.float32)
    # Real stars only in the covered region (right side).
    gap_cols = int(w * gap_fraction)
    for _ in range(n_stars):
        y = int(rng.integers(6, h - 6))
        x = int(rng.integers(gap_cols + 6, w - 6))
        peak = float(rng.uniform(4000, 20000))
        for dy in range(-3, 4):
            for dx in range(-3, 4):
                img[y + dy, x + dx, :] += peak * np.exp(-(dy * dy + dx * dx) / 3.0)
    # Carve the uncovered region.
    img[:, :gap_cols, :] = np.nan
    return img


def test_detection_does_not_explode_on_nan_canvas():
    """With the NaN region masked, detection finds a sane number of stars and
    returns quickly — not hundreds of thousands."""
    img = _mosaic_like_image()
    t0 = time.perf_counter()
    sources = _detect_calibration_stars(img, ColorCalibrationOptions(enabled=True))
    elapsed = time.perf_counter() - t0
    assert sources is not None
    # Sane count — nowhere near the pathological explosion, and capped.
    assert len(sources) <= MAX_CALIBRATION_STARS
    assert len(sources) < 5000
    # Should be fast — detection on a 600×900 image is sub-second.
    assert elapsed < 10.0


def test_calibrate_color_completes_on_mosaic_canvas():
    """End-to-end gray-star calibration on a mosaic-like image must finish."""
    img = _mosaic_like_image(seed=3)
    t0 = time.perf_counter()
    out, result = calibrate_color(
        img, options=ColorCalibrationOptions(
            enabled=True, mode="gray_star", min_stars=10,
        ),
    )
    elapsed = time.perf_counter() - t0
    assert result.mode_used in ("gray_star", "none")
    assert out.shape == img.shape
    # Uncovered region must stay NaN (calibration only scales finite pixels).
    assert np.isnan(out[0, 0, 0])
    assert elapsed < 20.0


def test_detection_caps_at_max_stars():
    """Even a noisy low-threshold detection is capped to MAX_CALIBRATION_STARS."""
    rng = np.random.default_rng(9)
    # No NaN, but a very low threshold to force many detections.
    img = rng.normal(1000.0, 50.0, size=(400, 400, 3)).astype(np.float32)
    for _ in range(50):
        y, x = rng.integers(5, 395), rng.integers(5, 395)
        img[y - 2:y + 3, x - 2:x + 3, :] += 15000
    opts = ColorCalibrationOptions(enabled=True, detect_threshold_sigma=1.0)
    sources = _detect_calibration_stars(img, opts)
    if sources is not None:
        assert len(sources) <= MAX_CALIBRATION_STARS
