"""Streaming accumulators."""

import numpy as np
import pytest

from seestack.stack.accumulator import (
    MinMaxRejectAccumulator,
    WeightedSumAccumulator,
    WelfordAccumulator,
)


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


# --------------------------------------------------------------------------- #
# MinMaxRejectAccumulator
# --------------------------------------------------------------------------- #

def test_min_max_reject_drops_one_min_and_one_max():
    acc = MinMaxRejectAccumulator((1, 1))
    # Values 1,2,3,4,100 → drop min(1) and max(100), mean of {2,3,4} = 3.
    for v in (1.0, 2.0, 3.0, 4.0, 100.0):
        acc.add(np.full((1, 1), v))
    np.testing.assert_allclose(acc.result(), 3.0)
    assert acc.coverage[0, 0] == 5


def test_min_max_reject_kills_lone_satellite_in_small_stack():
    # The motivating case: a 6-frame stack where one frame has a bright trail at
    # a pixel. κ-σ (κ=3) mathematically can't reject it (deviation < κ·σ for
    # n<11), but min/max reject removes it: {10,10,10,10,10,500} → drop 500 & one
    # 10 → mean of four 10s = 10, not the mean-inflated ~91.7.
    acc = MinMaxRejectAccumulator((1, 1))
    for v in (10.0, 10.0, 10.0, 10.0, 10.0, 500.0):
        acc.add(np.full((1, 1), v))
    np.testing.assert_allclose(acc.result(), 10.0)


def test_min_max_reject_tie_safe_on_saturated_core():
    # Several frames share the per-pixel max (a saturated star core). Only ONE
    # max value is subtracted, not every tied frame: {50,90,100,100,100} →
    # drop min 50 and one max 100 → mean of {90,100,100} = 96.667.
    acc = MinMaxRejectAccumulator((1, 1))
    for v in (50.0, 90.0, 100.0, 100.0, 100.0):
        acc.add(np.full((1, 1), v))
    np.testing.assert_allclose(acc.result(), (90.0 + 100.0 + 100.0) / 3.0)


def test_min_max_reject_small_coverage_falls_back_to_mean():
    acc = MinMaxRejectAccumulator((1, 3))
    # col0: one sample → mean=7; col1: two samples → mean; col2: none → NaN.
    acc.add(np.array([[7.0, 4.0, np.nan]]))
    acc.add(np.array([[np.nan, 8.0, np.nan]]))
    out = acc.result()
    assert out[0, 0] == 7.0
    np.testing.assert_allclose(out[0, 1], 6.0)  # (4+8)/2, can't spare two
    assert np.isnan(out[0, 2])


def test_min_max_reject_nan_aware_extremes():
    # NaNs must not corrupt the running min/max: a masked-out (NaN) sample is
    # simply skipped, never treated as -inf/+inf or 0.
    acc = MinMaxRejectAccumulator((1, 1))
    for v in (5.0, np.nan, 1.0, 9.0, 5.0):  # valid {5,1,9,5}: drop 1 & 9 → {5,5}=5
        acc.add(np.full((1, 1), v))
    np.testing.assert_allclose(acc.result(), 5.0)
    assert acc.coverage[0, 0] == 4


def test_min_max_reject_windowed_matches_full():
    rng = np.random.default_rng(7)
    frames = [rng.normal(100, 5, size=(6, 6)).astype(np.float32) for _ in range(5)]
    # Inject a hot outlier into one frame at (2, 3).
    frames[2][2, 3] = 9000.0

    full = MinMaxRejectAccumulator((6, 6))
    for f in frames:
        full.add(f)

    win = MinMaxRejectAccumulator((6, 6))
    for f in frames:
        win.add_window(f[1:5, 1:5], 1, 1)  # only the interior covered

    fr, wr = full.result(), win.result()
    # The outlier pixel is rejected in both, and the interior agrees.
    np.testing.assert_allclose(fr[2, 3], wr[2, 3], rtol=1e-5)
    assert fr[2, 3] < 200.0  # 9000 was dropped
    np.testing.assert_allclose(fr[1:5, 1:5], wr[1:5, 1:5], rtol=1e-5)
    # Windowed accumulator never touched the margin.
    assert np.isnan(wr[0, 0])
