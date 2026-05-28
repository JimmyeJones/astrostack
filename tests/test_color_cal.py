"""Photometric color calibration (gray-star path; Gaia path mocked)."""

import numpy as np
import pytest

pytest.importorskip("astropy")
pytest.importorskip("photutils")

from seestack.post.color_cal import (
    ColorCalibrationOptions,
    _apply_scale,
    _solve_gray_star,
    calibrate_color,
)


def _starfield(h: int = 256, w: int = 384, n_stars: int = 80,
               r_gain: float = 1.0, b_gain: float = 1.0, seed: int = 0) -> np.ndarray:
    """Synthetic starfield where R and B are scaled by user-supplied factors."""
    rng = np.random.default_rng(seed)
    rgb = rng.normal(loc=100, scale=2, size=(h, w, 3)).astype(np.float32)
    for _ in range(n_stars):
        y = int(rng.integers(8, h - 8))
        x = int(rng.integers(8, w - 8))
        peak = float(rng.uniform(3000, 12000))
        for dy in range(-3, 4):
            for dx in range(-3, 4):
                r2 = dy * dy + dx * dx
                # Stars are "neutral" before applying the camera gain bias.
                rgb[y + dy, x + dx, 0] += peak * r_gain * np.exp(-r2 / 2.0)
                rgb[y + dy, x + dx, 1] += peak * np.exp(-r2 / 2.0)
                rgb[y + dy, x + dx, 2] += peak * b_gain * np.exp(-r2 / 2.0)
    return rgb


def test_gray_star_solver_balances_neutral_field():
    """Gray-star calibration on a field of perfectly neutral stars: scales ≈ 1."""
    rgb = _starfield(r_gain=1.0, b_gain=1.0)
    out, result = calibrate_color(rgb, options=ColorCalibrationOptions(
        enabled=True, mode="gray_star", min_stars=10,
    ))
    assert result.mode_used == "gray_star"
    sr, sg, sb = result.scale_rgb
    assert abs(sr - 1.0) < 0.1
    assert sg == 1.0
    assert abs(sb - 1.0) < 0.1


def test_gray_star_corrects_red_bias():
    """Camera has R gain = 0.6 (red is weak). Gray-star should boost R."""
    rgb = _starfield(r_gain=0.6, b_gain=1.0, seed=2)
    _, result = calibrate_color(rgb, options=ColorCalibrationOptions(
        enabled=True, mode="gray_star", min_stars=10,
    ))
    sr, sg, sb = result.scale_rgb
    # We expect R scale ≈ 1/0.6 ≈ 1.67 to compensate.
    assert sr > 1.3
    assert sg == 1.0
    # B is unaffected.
    assert abs(sb - 1.0) < 0.2


def test_disabled_is_passthrough():
    rgb = _starfield()
    out, result = calibrate_color(rgb, options=ColorCalibrationOptions(enabled=False))
    np.testing.assert_array_equal(out, rgb)
    assert result.mode_used == "none"


def test_falls_back_when_too_few_stars():
    rgb = np.full((64, 64, 3), 100.0, dtype=np.float32)  # no stars
    _, result = calibrate_color(rgb, options=ColorCalibrationOptions(
        enabled=True, mode="gray_star", min_stars=10,
    ))
    assert result.mode_used == "none"
    assert result.scale_rgb == (1.0, 1.0, 1.0)


def test_apply_scale_handles_nan():
    rgb = np.full((4, 4, 3), 100.0, dtype=np.float32)
    rgb[0, 0, :] = np.nan
    out = _apply_scale(rgb, (2.0, 1.0, 0.5))
    assert np.isnan(out[0, 0, 0])
    assert out[1, 1, 0] == 200.0
    assert out[1, 1, 2] == 50.0


def test_solve_gray_star_directly():
    fluxes = np.array([[100, 200, 150]] * 50, dtype=np.float32)
    scale, n, note = _solve_gray_star(fluxes)
    # R scale = G/R = 200/100 = 2.0
    assert abs(scale[0] - 2.0) < 0.01
    assert scale[1] == 1.0
    # B scale = G/B = 200/150 ≈ 1.33
    assert abs(scale[2] - 200/150) < 0.01
    assert n == 50
