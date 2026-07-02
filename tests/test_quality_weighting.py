"""Quality-weighted stacking."""

import numpy as np
import pytest

from seestack.io.project import FrameRow
from seestack.stack.accumulator import WeightedSumAccumulator
from seestack.stack.weighting import compute_frame_weights, unit_weights


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
