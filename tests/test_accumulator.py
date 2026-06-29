"""Streaming accumulators."""

import numpy as np
import pytest

from seestack.stack.accumulator import WeightedSumAccumulator, WelfordAccumulator


def test_weighted_sum_basic():
    acc = WeightedSumAccumulator((4, 4, 3))
    acc.add(np.full((4, 4, 3), 10.0))
    acc.add(np.full((4, 4, 3), 20.0))
    out = acc.result()
    np.testing.assert_allclose(out, 15.0)
    assert (acc.coverage == 2).all()


def test_weighted_sum_with_nans():
    acc = WeightedSumAccumulator((2, 2))
    a = np.array([[1.0, np.nan], [3.0, 4.0]])
    b = np.array([[np.nan, 5.0], [6.0, 7.0]])
    acc.add(a)
    acc.add(b)
    # (0,0) = (1)/1 = 1; (0,1) = 5/1 = 5; (1,0)=(3+6)/2=4.5; (1,1)=(4+7)/2=5.5
    out = acc.result()
    np.testing.assert_allclose(out, [[1.0, 5.0], [4.5, 5.5]])


def test_weighted_sum_empty_pixel_is_nan():
    acc = WeightedSumAccumulator((2, 2))
    acc.add(np.array([[1.0, np.nan], [np.nan, 4.0]]))
    out = acc.result()
    assert np.isnan(out[0, 1])
    assert np.isnan(out[1, 0])
    assert out[0, 0] == 1.0
    assert out[1, 1] == 4.0


def test_welford_mean_matches_numpy():
    rng = np.random.default_rng(1)
    samples = [rng.normal(loc=10.0, scale=2.0, size=(8, 8)).astype(np.float32)
               for _ in range(50)]
    acc = WelfordAccumulator((8, 8))
    for s in samples:
        acc.add(s)
    expected_mean = np.mean(samples, axis=0)
    expected_std = np.std(samples, axis=0, ddof=1)  # unbiased sample std (matches accumulator)
    np.testing.assert_allclose(acc.mean(), expected_mean, rtol=1e-3)
    np.testing.assert_allclose(acc.std(), expected_std, rtol=1e-3)


def test_welford_single_coverage_std_is_nan():
    # n=1 (and n=0) → NaN std, so the sigma-clip pass widens the tolerance and
    # never spuriously rejects a single-coverage (mosaic-edge) pixel.
    acc = WelfordAccumulator((2, 2))
    one = np.array([[1.0, np.nan], [np.nan, np.nan]], dtype=np.float32)
    acc.add(one)
    std = acc.std()
    assert np.isnan(std[0, 0])  # one sample → undefined variance → NaN
    assert np.isnan(std[0, 1])  # never sampled → NaN


def test_welford_handles_nan():
    acc = WelfordAccumulator((2, 2))
    acc.add(np.array([[1.0, np.nan], [3.0, 5.0]]))
    acc.add(np.array([[3.0, 4.0], [np.nan, 7.0]]))
    mean = acc.mean()
    assert mean[0, 0] == 2.0   # avg of 1 and 3
    assert mean[0, 1] == 4.0   # only one sample
    assert mean[1, 0] == 3.0   # only one sample
    assert mean[1, 1] == 6.0   # avg of 5 and 7


def test_welford_no_data_returns_nan():
    acc = WelfordAccumulator((2, 2))
    out = acc.mean()
    assert np.isnan(out).all()
