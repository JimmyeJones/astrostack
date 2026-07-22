"""The 'stacking cut your noise ~N×' number: ``noise_ratio`` recovers the
background-noise reduction between a single sub and a stack, measured on linear,
identically-sampled arrays.
"""

from __future__ import annotations

import numpy as np
import pytest

from seestack.qc.noise_ratio import _background_sigma, noise_ratio


def _sky(sigma: float, *, seed: int, shape=(600, 600), pedestal: float = 1000.0):
    """A flat linear sky at ``pedestal`` ADU with Gaussian noise of the given σ."""
    rng = np.random.default_rng(seed)
    return (pedestal + rng.normal(0.0, sigma, size=shape)).astype(np.float32)


def test_background_sigma_recovers_known_noise():
    """The raw estimator returns the injected σ within a few percent."""
    for sigma in (5.0, 20.0, 50.0):
        est = _background_sigma(_sky(sigma, seed=int(sigma)))
        assert est is not None
        assert est == pytest.approx(sigma, rel=0.08)


def test_ratio_lands_near_sqrt_n():
    """A stack that averages N frames cuts the sky σ by ~√N, so the ratio of a
    single sub's σ to the stack's σ recovers ~√N."""
    for n in (4, 16, 64):
        sub = _sky(40.0, seed=1)
        # A mean of N independent frames has σ = 40/√N; simulate that directly.
        stack = _sky(40.0 / np.sqrt(n), seed=2, pedestal=0.0)
        rgb_sub = np.stack([sub, sub, sub], axis=-1)
        rgb_stack = np.stack([stack, stack, stack], axis=-1)
        ratio = noise_ratio(rgb_sub, rgb_stack)
        assert ratio is not None
        assert ratio == pytest.approx(np.sqrt(n), rel=0.10)


def test_ratio_is_scale_invariant_to_pedestal():
    """A different sky pedestal on each side (the sub is un-subtracted, the master
    is background-subtracted) must not change the σ ratio."""
    sub = np.stack([_sky(30.0, seed=3, pedestal=1200.0)] * 3, axis=-1)
    stack = np.stack([_sky(10.0, seed=4, pedestal=0.0)] * 3, axis=-1)
    assert noise_ratio(sub, stack) == pytest.approx(3.0, rel=0.10)


def test_bright_extended_target_does_not_inflate_the_ratio():
    """A galaxy filling a large fraction of the *stack* must not depress its
    measured σ ratio: the background-only population keeps the target's real
    texture out of the noise estimate."""
    n = 25
    sub = _sky(40.0, seed=5)
    stack = _sky(40.0 / np.sqrt(n), seed=6, pedestal=0.0)
    # Paint a bright, textured elongated target across the centre of the stack.
    rng = np.random.default_rng(7)
    yy, xx = np.mgrid[0:600, 0:600]
    blob = 3000.0 * np.exp(-(((xx - 300) / 200.0) ** 2 + ((yy - 300) / 40.0) ** 2))
    blob += rng.normal(0.0, 300.0, size=blob.shape) * (blob > 100.0)
    stack = stack + blob.astype(np.float32)
    rgb_sub = np.stack([sub, sub, sub], axis=-1)
    rgb_stack = np.stack([stack, stack, stack], axis=-1)
    ratio = noise_ratio(rgb_sub, rgb_stack)
    assert ratio is not None
    assert ratio == pytest.approx(np.sqrt(n), rel=0.15)


def test_nan_coverage_gaps_are_ignored():
    """Uncovered (NaN) mosaic-gap pixels in the stack are excluded, not treated
    as zeros that would wreck the estimate."""
    sub = _sky(40.0, seed=8)
    stack = _sky(10.0, seed=9, pedestal=0.0)
    stack[:, :100] = np.nan          # a wide uncovered border
    rgb_sub = np.stack([sub, sub, sub], axis=-1)
    rgb_stack = np.stack([stack, stack, stack], axis=-1)
    assert noise_ratio(rgb_sub, rgb_stack) == pytest.approx(4.0, rel=0.10)


def test_degenerate_inputs_return_none():
    """Too-small or noiseless-and-empty inputs yield None (the badge omits it)."""
    assert noise_ratio(np.zeros((4, 4, 3), np.float32),
                       np.zeros((4, 4, 3), np.float32)) is None
    # A finite sub but an all-NaN stack → no stack σ → None.
    sub = np.stack([_sky(40.0, seed=10)] * 3, axis=-1)
    nan_stack = np.full((600, 600, 3), np.nan, np.float32)
    assert noise_ratio(sub, nan_stack) is None
