"""Robust noise estimation → denoise-strength suggestion (seestack/edit/noise.py)."""

from __future__ import annotations

import numpy as np

from seestack.edit.noise import estimate_noise_sigma, suggest_denoise_strength


def _scene(noise: float, h=120, w=160, seed=0):
    """A smooth bright blob on a flat sky plus Gaussian read-noise of the given σ
    (in raw units), so more noise → higher estimated σ / suggested strength."""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:h, 0:w]
    signal = 0.6 * np.exp(-(((xx - w / 2) / 20) ** 2 + ((yy - h / 2) / 20) ** 2))
    img = 0.1 + signal[..., None] + rng.normal(0.0, noise, (h, w, 3))
    return img.astype("float32")


def test_noisier_image_gets_higher_sigma_and_strength():
    clean = _scene(0.005)
    noisy = _scene(0.05)
    s_clean = estimate_noise_sigma(clean)
    s_noisy = estimate_noise_sigma(noisy)
    assert s_clean is not None and s_noisy is not None
    assert s_noisy > s_clean

    _, str_clean = suggest_denoise_strength(clean)
    _, str_noisy = suggest_denoise_strength(noisy)
    assert str_clean is not None and str_noisy is not None
    assert str_noisy > str_clean


def test_strength_stays_in_op_range_and_step():
    # A very noisy image saturates at the op's max; the value is a valid slider step.
    sigma, strength = suggest_denoise_strength(_scene(0.3))
    assert sigma is not None and strength is not None
    assert 0.1 <= strength <= 1.0
    # multiple of 0.05 (the op's step)
    assert abs((strength / 0.05) - round(strength / 0.05)) < 1e-9


def test_nan_uncovered_pixels_are_ignored():
    # A mosaic-edge NaN band must not crash or poison the estimate.
    img = _scene(0.02)
    img[:20, :, :] = np.nan
    sigma, strength = suggest_denoise_strength(img)
    assert sigma is not None and strength is not None
    assert np.isfinite(sigma)


def test_returns_none_when_not_measurable():
    # All-NaN and flat (no dynamic range) images yield no suggestion.
    allnan = np.full((40, 40, 3), np.nan, dtype="float32")
    assert suggest_denoise_strength(allnan) == (None, None)
    flat = np.full((40, 40, 3), 0.3, dtype="float32")
    assert suggest_denoise_strength(flat) == (None, None)
