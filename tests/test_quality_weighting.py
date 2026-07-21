"""Quality-weighted stacking."""

import numpy as np
import pytest

from seestack.io.project import FrameRow
from seestack.stack.accumulator import WeightedSumAccumulator
from seestack.stack.weighting import (
    combine_weights_with_photometric,
    compute_frame_weights,
    unit_weights,
)


def _f(id_, fwhm, stars, sky, transp=None, ecc=None):
    return FrameRow(id=id_, source_path=f"x{id_}.fit",
                    fwhm_px=fwhm, star_count=stars, sky_adu_median=sky,
                    transparency_score=transp, eccentricity_median=ecc)


def test_weights_favour_sharper_frames():
    frames = [
        _f(1, fwhm=2.0, stars=100, sky=1000),  # best
        _f(2, fwhm=3.0, stars=100, sky=1000),
        _f(3, fwhm=4.0, stars=100, sky=1000),  # worst
    ]
    w, _ = compute_frame_weights(frames)
    assert w[1] > w[2] > w[3]


def test_weights_penalise_low_star_count():
    frames = [
        _f(1, fwhm=3.0, stars=200, sky=1000),  # above-median (capped at 1.0)
        _f(2, fwhm=3.0, stars=100, sky=1000),  # at median (1.0)
        _f(3, fwhm=3.0, stars=20, sky=1000),   # below-median, cloud-affected
    ]
    w, _ = compute_frame_weights(frames)
    # Above-median frames are not rewarded (capped), but below-median is penalised.
    assert w[1] == w[2]
    assert w[2] > w[3]


def test_weights_penalise_low_transparency():
    # All else equal, a hazy frame (below-median transparency) is down-weighted,
    # while an above-median-transparency frame is capped at the neutral factor.
    frames = [
        _f(1, fwhm=3.0, stars=100, sky=1000, transp=8000),  # clearest (capped)
        _f(2, fwhm=3.0, stars=100, sky=1000, transp=5000),  # at median
        _f(3, fwhm=3.0, stars=100, sky=1000, transp=1000),  # hazy
    ]
    w, _ = compute_frame_weights(frames)
    assert w[1] == w[2]      # above-median transparency isn't rewarded
    assert w[2] > w[3]       # hazy frame is penalised


def test_transparency_missing_is_not_penalised():
    # A frame with no transparency score keeps the neutral factor for it and is
    # not dragged below an otherwise-identical frame that does carry a score.
    frames = [
        _f(1, fwhm=3.0, stars=100, sky=1000, transp=None),
        _f(2, fwhm=3.0, stars=100, sky=1000, transp=5000),
    ]
    w, _ = compute_frame_weights(frames)
    assert w[1] == w[2] == 1.0


def test_weights_penalise_elongated_stars():
    # All else equal, a frame with more-elongated stars (above-median
    # eccentricity — tracking error / wind) is down-weighted, while a
    # rounder-than-median frame caps at the neutral factor.
    frames = [
        _f(1, fwhm=3.0, stars=100, sky=1000, ecc=0.2),  # roundest (capped)
        _f(2, fwhm=3.0, stars=100, sky=1000, ecc=0.4),  # at median
        _f(3, fwhm=3.0, stars=100, sky=1000, ecc=0.8),  # trailed
    ]
    w, _ = compute_frame_weights(frames)
    assert w[1] == w[2]      # rounder-than-median isn't rewarded
    assert w[2] > w[3]       # elongated frame is penalised


def test_eccentricity_missing_is_not_penalised():
    # A frame with no eccentricity keeps the neutral factor and isn't dragged
    # below an otherwise-identical frame that does carry one.
    frames = [
        _f(1, fwhm=3.0, stars=100, sky=1000, ecc=None),
        _f(2, fwhm=3.0, stars=100, sky=1000, ecc=0.4),
    ]
    w, _ = compute_frame_weights(frames)
    assert w[1] == w[2] == 1.0


def test_eccentricity_zero_is_best_case_not_divide_error():
    # A perfectly-round frame (ecc == 0) is the best case: it must not trigger a
    # divide-by-zero, and it should not be penalised relative to the median.
    frames = [
        _f(1, fwhm=3.0, stars=100, sky=1000, ecc=0.0),
        _f(2, fwhm=3.0, stars=100, sky=1000, ecc=0.5),
    ]
    w, _ = compute_frame_weights(frames)
    assert w[1] == 1.0       # round frame keeps the neutral factor
    assert w[2] < 1.0        # more-elongated-than-median frame is penalised


def test_sky_zero_is_neutral_not_divide_error():
    # A frame whose stored sky level is exactly 0 (a black / corrupt sub, or a
    # non-Seestar frame with no ADU pedestal) must not crash the whole
    # quality-weighted stack with a divide-by-zero: the sky factor divides by
    # the per-frame sky, so a 0 there has to be guarded like every sibling
    # factor's denominator. The frame keeps the neutral sky factor.
    frames = [
        _f(1, fwhm=3.0, stars=100, sky=1000),
        _f(2, fwhm=3.0, stars=100, sky=0.0),
    ]
    w, _ = compute_frame_weights(frames)  # must not raise ZeroDivisionError
    # Both share fwhm/stars; frame 2's only differing metric (sky) is dropped as
    # unmeasurable, so it isn't penalised relative to frame 1.
    assert w[1] == w[2] == 1.0


def test_sky_negative_is_neutral_not_complex_weight():
    # A negative stored sky (nonsense, but reachable from an odd calibration /
    # import) would make ``(median_sky / frame_sky) ** 0.5`` complex and get
    # silently cast to a bogus real weight; guard it as neutral instead.
    frames = [
        _f(1, fwhm=3.0, stars=100, sky=1000),
        _f(2, fwhm=3.0, stars=100, sky=-50.0),
    ]
    w, _ = compute_frame_weights(frames)
    assert w[1] == w[2] == 1.0


def test_missing_metrics_get_neutral_weight():
    frames = [
        _f(1, fwhm=None, stars=None, sky=None),
        _f(2, fwhm=3.0, stars=100, sky=1000),
    ]
    w, stats = compute_frame_weights(frames)
    assert w[1] == 1.0
    assert stats.n_neutral == 1


def test_stats_count_downweighted_frames():
    # Two below-median-sharpness frames get pulled below full weight; the
    # best (capped-at-1.0) frame does not count as down-weighted.
    frames = [
        _f(1, fwhm=2.0, stars=100, sky=1000),  # best → weight 1.0
        _f(2, fwhm=3.0, stars=100, sky=1000),  # demoted
        _f(3, fwhm=4.0, stars=100, sky=1000),  # demoted more
    ]
    w, stats = compute_frame_weights(frames)
    assert stats.n_downweighted == 2
    assert w[1] == 1.0


def test_unit_weights_are_all_one():
    frames = [_f(i, 3.0, 100, 1000) for i in range(5)]
    w = unit_weights(frames)
    assert all(v == 1.0 for v in w.values())


def test_accumulator_respects_per_frame_weight():
    """Weighted mean of (10 with weight 1) and (20 with weight 3) = 17.5."""
    acc = WeightedSumAccumulator((2, 2))
    acc.add(np.full((2, 2), 10.0), weight=1.0)
    acc.add(np.full((2, 2), 20.0), weight=3.0)
    out = acc.result()
    np.testing.assert_allclose(out, 17.5)


def test_min_weight_floor():
    """Even a terrible frame gets at least min_weight in each factor."""
    frames = [
        _f(1, fwhm=2.0, stars=100, sky=1000),
        _f(2, fwhm=20.0, stars=1, sky=10000),  # terrible across the board
    ]
    w, _ = compute_frame_weights(frames, min_weight=0.1)
    # 0.1 * 0.1 * 0.1 (= 0.001) under naïve product; geometric mean = 0.1.
    assert w[2] >= 0.1


# ---- Inverse-variance combine weight (photometric scaling) ------------------

def test_combine_weights_no_photometric_is_identity_object():
    """With no scales the combine weight IS the quality weight (same object) —
    the guarantee that a run with photometric scaling off is byte-for-byte
    unchanged."""
    w = {1: 0.8, 2: 1.0, 3: 0.5}
    assert combine_weights_with_photometric(w, None) is w
    assert combine_weights_with_photometric(w, {}) is w


def test_combine_weights_scaled_up_frame_loses_1_over_s_squared():
    """A frame gain-matched up by s carries its noise up by s too, so its combine
    weight drops by 1/s²; a neutral (1.0) scale is untouched."""
    w = {1: 1.0, 2: 1.0, 3: 1.0}
    scales = {1: 1.0, 2: 2.0, 3: 1.0}  # frame 2 scaled ×2 (hazy)
    cw = combine_weights_with_photometric(w, scales)
    assert cw[1] == 1.0
    assert cw[2] == pytest.approx(0.25)  # 1 / 2²
    assert cw[3] == 1.0
    # Pure function: the input dict is not mutated.
    assert w == {1: 1.0, 2: 1.0, 3: 1.0}


def test_combine_weights_scaled_down_frame_gains_weight():
    """A transparent frame scaled *down* (s < 1) has less noise, so it is trusted
    *more* — its combine weight rises above the base (can exceed 1.0)."""
    w = {1: 1.0}
    cw = combine_weights_with_photometric(w, {1: 0.5})
    assert cw[1] == pytest.approx(4.0)  # 1 / 0.5²


def test_combine_weights_scale_on_quality_weighted_base():
    """The 1/s² factor composes multiplicatively with an existing quality
    weight, not replacing it."""
    w = {7: 0.6}
    cw = combine_weights_with_photometric(w, {7: 2.0})
    assert cw[7] == pytest.approx(0.6 / 4.0)  # base 0.6 × 1/s²


def test_combine_weights_reduce_combined_noise_vs_equal_weight():
    """The point of the fix: inverse-variance weighting a scaled (noisier) frame
    yields a lower-variance combined estimate than equal weighting.

    One 'good' frame (noise σ=1, scale 1) and one 'hazy' frame gain-matched ×2
    (so its noise is 2σ). Closed-form combined variances:
      equal weights      → (1² + 2²) / 2² = 1.25
      inverse-variance   → (1 + 0.25²·4) / 1.25² = 0.8
    A fixed-seed Monte-Carlo over the real ``WeightedSumAccumulator`` confirms it.
    """
    rng = np.random.default_rng(1234)
    n_trials = 40000
    base = {1: 1.0, 2: 1.0}
    scales = {1: 1.0, 2: 2.0}
    cw = combine_weights_with_photometric(base, scales)

    eq_est = np.empty(n_trials, dtype=np.float64)
    iv_est = np.empty(n_trials, dtype=np.float64)
    for t in range(n_trials):
        x_good = rng.normal(0.0, 1.0)   # good frame around true 0
        x_hazy = rng.normal(0.0, 2.0)   # scaled-up frame, 2× noise, same signal
        # Equal weighting (pre-fix): both weight 1.
        eq = WeightedSumAccumulator((1, 1))
        eq.add(np.full((1, 1), x_good), weight=base[1])
        eq.add(np.full((1, 1), x_hazy), weight=base[2])
        eq_est[t] = float(eq.result()[0, 0])
        # Inverse-variance weighting (the fix): hazy frame down-weighted 1/s².
        iv = WeightedSumAccumulator((1, 1))
        iv.add(np.full((1, 1), x_good), weight=cw[1])
        iv.add(np.full((1, 1), x_hazy), weight=cw[2])
        iv_est[t] = float(iv.result()[0, 0])

    # Inverse-variance should cut the combined variance well below equal-weight
    # (theory 0.8 vs 1.25 = 0.64×); assert a comfortable margin so the fixed seed
    # never makes this flaky.
    assert iv_est.var() < 0.85 * eq_est.var()
