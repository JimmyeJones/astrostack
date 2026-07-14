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


def test_weighted_sum_frame_coverage_is_an_unweighted_frame_count():
    """``frame_coverage`` counts contributing frames regardless of weight, while
    ``coverage`` stays the Σ-of-weights map. Regression: with quality weighting
    the two diverge, and the coverage_min/max "N frames per pixel" diagnostic
    must read the frame count, not the (smaller) weight sum."""
    acc = WeightedSumAccumulator((3, 3, 3))
    for _ in range(4):
        acc.add(np.full((3, 3, 3), 10.0), weight=0.5)
    # Four frames of weight 0.5 → Σweights = 2.0, but the true frame count is 4.
    np.testing.assert_allclose(acc.coverage, 2.0)
    assert acc.frame_coverage.shape == (3, 3)
    assert (acc.frame_coverage == 4).all()
    # Unweighted, the two agree exactly (drop-in for the old coverage[...,0]).
    acc2 = WeightedSumAccumulator((3, 3, 3))
    for _ in range(4):
        acc2.add(np.full((3, 3, 3), 10.0))
    np.testing.assert_array_equal(acc2.frame_coverage, acc2.coverage[..., 0].astype("uint32"))


def test_weighted_sum_frame_coverage_respects_nan_gaps():
    """A pixel no frame covered has frame count 0; partial coverage counts only
    the frames that actually contributed (NaN = missing)."""
    acc = WeightedSumAccumulator((2, 2, 3))
    a = np.full((2, 2, 3), 5.0)
    a[0, 1] = np.nan  # one pixel missing in frame a
    b = np.full((2, 2, 3), 7.0)
    acc.add(a, weight=0.3)
    acc.add(b, weight=0.3)
    fc = acc.frame_coverage
    assert fc[0, 0] == 2 and fc[1, 0] == 2 and fc[1, 1] == 2
    assert fc[0, 1] == 1  # only frame b covered it


def test_weighted_sum_frame_coverage_windowed():
    """The windowed add path tracks the same unweighted frame count."""
    acc = WeightedSumAccumulator((4, 4, 3))
    acc.add_window(np.full((2, 2, 3), 9.0), y0=1, x0=1, weight=0.4)
    acc.add_window(np.full((2, 2, 3), 9.0), y0=1, x0=1, weight=0.4)
    fc = acc.frame_coverage
    assert (fc[1:3, 1:3] == 2).all()
    assert fc[0, 0] == 0  # outside the window — untouched


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


def test_min_max_reject_rejection_counts_full_trim():
    # 5 samples at one pixel, k=1 → full trim drops exactly 2 (one min, one max);
    # all 5 contributed. Powers the "rejection dropped ~X%" History trust line.
    acc = MinMaxRejectAccumulator((1, 1))
    for v in (1.0, 2.0, 3.0, 4.0, 100.0):
        acc.add(np.full((1, 1), v))
    contributed, rejected = acc.rejection_counts()
    assert contributed == 5
    assert rejected == 2


def test_min_max_reject_rejection_counts_k3_and_bands():
    # A row of three pixels with different coverage, k=3:
    #   col0: 7 samples (≥2k+1) → full trim drops 2k=6
    #   col1: 4 samples (3≤n<2k+1) → degrades to a single min/max drop = 2
    #   col2: 2 samples (<3) → can't spare two → 0 dropped
    acc = MinMaxRejectAccumulator((1, 3), reject_count=3)
    cols0 = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]
    cols1 = [1.0, 2.0, 3.0, 4.0]
    cols2 = [1.0, 2.0]
    for i in range(7):
        row = np.array([[
            cols0[i],
            cols1[i] if i < len(cols1) else np.nan,
            cols2[i] if i < len(cols2) else np.nan,
        ]])
        acc.add(row)
    contributed, rejected = acc.rejection_counts()
    assert contributed == 7 + 4 + 2
    assert rejected == 6 + 2 + 0


def test_min_max_reject_rejection_counts_empty_is_zero():
    acc = MinMaxRejectAccumulator((2, 2))
    assert acc.rejection_counts() == (0, 0)


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


def test_min_max_reject_k3_drops_three_each_end():
    # k=3: drop the 3 smallest and 3 largest, average the middle. Values
    # {1,2,3, 10,11,12, 98,99,100} → drop {1,2,3} and {98,99,100} → mean{10,11,12}=11.
    acc = MinMaxRejectAccumulator((1, 1), reject_count=3)
    for v in (1.0, 2.0, 3.0, 10.0, 11.0, 12.0, 98.0, 99.0, 100.0):
        acc.add(np.full((1, 1), v))
    np.testing.assert_allclose(acc.result(), 11.0)
    assert acc.coverage[0, 0] == 9


def test_min_max_reject_k3_kills_three_trails():
    # The motivating case: three separate satellite/plane trails cross one pixel
    # across a session. Single min/max drop (k=1) leaves two of them inflating the
    # mean; k=3 removes all three. {10×6, 500, 600, 700} → k=3 drops {500,600,700}
    # and three of the 10s → mean of the remaining three 10s = 10.
    vals = [10.0] * 6 + [500.0, 600.0, 700.0]
    acc = MinMaxRejectAccumulator((1, 1), reject_count=3)
    for v in vals:
        acc.add(np.full((1, 1), v))
    np.testing.assert_allclose(acc.result(), 10.0)
    # Contrast: k=1 (today's behaviour) only clips the single worst trail, so two
    # bright trails survive and badly inflate the mean.
    acc1 = MinMaxRejectAccumulator((1, 1), reject_count=1)
    for v in vals:
        acc1.add(np.full((1, 1), v))
    assert acc1.result()[0, 0] > 100.0


def test_min_max_reject_k_degrades_to_single_drop_below_2k_plus_1():
    # With k=3 but only 5 samples (< 2k+1=7), a full k-trim would leave nothing,
    # so it degrades to the proven single min/max drop: {1,4,5,6,100} → drop 1 &
    # 100 → mean{4,5,6}=5. (Tie-checked against a k=1 accumulator on the same data.)
    vals = (1.0, 4.0, 5.0, 6.0, 100.0)
    acc = MinMaxRejectAccumulator((1, 1), reject_count=3)
    for v in vals:
        acc.add(np.full((1, 1), v))
    np.testing.assert_allclose(acc.result(), 5.0)
    acc1 = MinMaxRejectAccumulator((1, 1), reject_count=1)
    for v in vals:
        acc1.add(np.full((1, 1), v))
    np.testing.assert_allclose(acc.result(), acc1.result())


def test_min_max_reject_k3_nan_aware_and_tie_safe():
    # NaNs are skipped, and tied extremes lose only k contributions. Valid values
    # {5,5,5, 20,20,20, 40} with two NaNs: 7 valid, count≥2k+1 so full k=3 trim →
    # drop three lowest {5,5,5} and three highest {40,20,20} → middle {20} = 20.
    acc = MinMaxRejectAccumulator((1, 1), reject_count=3)
    for v in (5.0, np.nan, 5.0, 5.0, 20.0, 20.0, np.nan, 20.0, 40.0):
        acc.add(np.full((1, 1), v))
    assert acc.coverage[0, 0] == 7
    np.testing.assert_allclose(acc.result(), 20.0)


def test_min_max_reject_k3_windowed_matches_full():
    rng = np.random.default_rng(11)
    frames = [rng.normal(100, 5, size=(6, 6)).astype(np.float32) for _ in range(9)]
    # Inject three hot outliers into three different frames at the same pixel.
    for fi, hot in zip((2, 5, 7), (9000.0, 8000.0, 7000.0)):
        frames[fi][2, 3] = hot

    full = MinMaxRejectAccumulator((6, 6), reject_count=3)
    for f in frames:
        full.add(f)
    win = MinMaxRejectAccumulator((6, 6), reject_count=3)
    for f in frames:
        win.add_window(f[1:5, 1:5], 1, 1)

    fr, wr = full.result(), win.result()
    np.testing.assert_allclose(fr[2, 3], wr[2, 3], rtol=1e-5)
    assert fr[2, 3] < 200.0  # all three trails dropped
    np.testing.assert_allclose(fr[1:5, 1:5], wr[1:5, 1:5], rtol=1e-5)
    assert np.isnan(wr[0, 0])  # margin never touched


def test_min_max_reject_k_default_is_one():
    # Default reject_count preserves exactly the classic single min/max drop.
    default = MinMaxRejectAccumulator((1, 1))
    k1 = MinMaxRejectAccumulator((1, 1), reject_count=1)
    for v in (1.0, 2.0, 3.0, 4.0, 100.0):
        default.add(np.full((1, 1), v))
        k1.add(np.full((1, 1), v))
    np.testing.assert_allclose(default.result(), k1.result())
    np.testing.assert_allclose(default.result(), 3.0)


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


def test_weighted_sum_accepts_a_2d_per_pixel_mask():
    """The docstring promises a "broadcastable" mask; a natural per-pixel 2-D
    ``(H, W)`` mask against an ``(H, W, C)`` image must mask that pixel across
    *all* channels rather than raising a broadcasting ``ValueError`` (trailing
    dims ``W`` vs ``C`` don't align). Regression for the latent accumulator trap."""
    acc = WeightedSumAccumulator((2, 2, 3))
    img = np.full((2, 2, 3), 10.0, dtype=np.float32)
    mask2d = np.array([[True, False], [True, True]])  # skip pixel (0, 1) everywhere
    acc.add(img, mask=mask2d)  # would raise ValueError before the fix
    acc.add(img, mask=mask2d)
    out = acc.result()
    # Unmasked pixels averaged normally over two frames…
    np.testing.assert_allclose(out[0, 0], 10.0)
    np.testing.assert_allclose(out[1, 1], 10.0)
    # …and the masked pixel got no coverage on any channel → NaN, count 0.
    assert np.isnan(out[0, 1]).all()
    assert acc.frame_coverage[0, 1] == 0
    assert (acc.frame_coverage[[0, 1, 1], [0, 0, 1]] == 2).all()
    # A same-shape (H, W, C) mask still behaves identically (unchanged contract).
    acc3 = WeightedSumAccumulator((2, 2, 3))
    acc3.add(img, mask=np.broadcast_to(mask2d[..., None], (2, 2, 3)))
    np.testing.assert_array_equal(acc3.frame_coverage, acc.frame_coverage // 2)


def test_weighted_sum_window_accepts_a_2d_per_pixel_mask():
    """``add_window`` honours the same 2-D per-pixel mask contract as ``add``."""
    acc = WeightedSumAccumulator((4, 4, 3))
    win = np.full((2, 2, 3), 7.0, dtype=np.float32)
    mask2d = np.array([[True, False], [False, True]])
    acc.add_window(win, 1, 1, mask=mask2d)  # would raise ValueError before the fix
    cov = acc.frame_coverage
    assert cov[1, 1] == 1 and cov[2, 2] == 1
    assert cov[1, 2] == 0 and cov[2, 1] == 0
    assert cov[0, 0] == 0  # window never touched the margin


def test_min_max_reject_accepts_a_2d_per_pixel_mask():
    """The MinMaxReject accumulator shares the mask contract via ``_add_into``."""
    acc = MinMaxRejectAccumulator((2, 2, 3))
    img = np.full((2, 2, 3), 5.0, dtype=np.float32)
    mask2d = np.array([[True, True], [False, True]])
    for _ in range(3):
        acc.add(img, mask=mask2d)  # would raise ValueError before the fix
    out = acc.result()
    np.testing.assert_allclose(out[0, 0], 5.0)
    assert np.isnan(out[1, 0]).all()  # masked pixel never covered → NaN
