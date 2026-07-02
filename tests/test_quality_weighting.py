"""Quality-weighted stacking."""

import numpy as np
import pytest

from seestack.io.project import FrameRow
from seestack.stack.accumulator import WeightedSumAccumulator
from seestack.stack.weighting import compute_frame_weights, unit_weights


def _f(id_, fwhm, stars, sky, transp=None):
    return FrameRow(id=id_, source_path=f"x{id_}.fit",
                    fwhm_px=fwhm, star_count=stars, sky_adu_median=sky,
                    transparency_score=transp)


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


def test_missing_metrics_get_neutral_weight():
    frames = [
        _f(1, fwhm=None, stars=None, sky=None),
        _f(2, fwhm=3.0, stars=100, sky=1000),
    ]
    w, stats = compute_frame_weights(frames)
    assert w[1] == 1.0
    assert stats.n_neutral == 1


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
