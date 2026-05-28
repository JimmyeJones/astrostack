"""
Windowed reproject + windowed accumulators.

These lock in the mosaic-performance optimization: each frame only touches the
sub-rectangle of the canvas its footprint covers, instead of scanning the
whole (possibly huge) union canvas.
"""

import numpy as np
import pytest

pytest.importorskip("astropy")
pytest.importorskip("scipy")

from seestack.io.wcs_io import wcs_from_text
from seestack.stack.accumulator import WeightedSumAccumulator, WelfordAccumulator
from seestack.stack.align import reproject_rgb, reproject_rgb_windowed
from tests.synth import make_synth_wcs_text


# ---- accumulator add_window ------------------------------------------------


def test_weighted_add_window_matches_full_add():
    """add_window into a sub-rect == add of a full-canvas array with that
    sub-rect filled and the rest NaN."""
    rng = np.random.default_rng(0)
    canvas = (40, 60, 3)
    win = rng.random((12, 18, 3)).astype(np.float32)
    y0, x0 = 7, 25

    acc_win = WeightedSumAccumulator(canvas)
    acc_win.add_window(win, y0, x0)

    acc_full = WeightedSumAccumulator(canvas)
    full = np.full(canvas, np.nan, dtype=np.float32)
    full[y0:y0 + 12, x0:x0 + 18] = win
    acc_full.add(full)

    np.testing.assert_allclose(
        np.nan_to_num(acc_win.result()), np.nan_to_num(acc_full.result()),
        rtol=1e-6,
    )
    np.testing.assert_array_equal(acc_win.coverage, acc_full.coverage)


def test_weighted_add_window_respects_weight():
    canvas = (10, 10, 3)
    acc = WeightedSumAccumulator(canvas)
    acc.add_window(np.full((4, 4, 3), 10.0, np.float32), 0, 0, weight=1.0)
    acc.add_window(np.full((4, 4, 3), 20.0, np.float32), 0, 0, weight=3.0)
    out = acc.result()
    # Weighted mean of 10 (w=1) and 20 (w=3) = 17.5 in the overlap region.
    np.testing.assert_allclose(out[0, 0, 0], 17.5)
    # Outside the window: untouched → NaN.
    assert np.isnan(out[8, 8, 0])


def test_welford_add_window_matches_full_add():
    rng = np.random.default_rng(1)
    canvas = (30, 40, 3)
    y0, x0 = 5, 11
    wins = [rng.random((10, 14, 3)).astype(np.float32) for _ in range(4)]

    acc_win = WelfordAccumulator(canvas)
    acc_full = WelfordAccumulator(canvas)
    for win in wins:
        acc_win.add_window(win, y0, x0)
        full = np.full(canvas, np.nan, dtype=np.float32)
        full[y0:y0 + 10, x0:x0 + 14] = win
        acc_full.add(full)

    np.testing.assert_allclose(
        np.nan_to_num(acc_win.mean()), np.nan_to_num(acc_full.mean()), rtol=1e-5,
    )
    np.testing.assert_allclose(
        np.nan_to_num(acc_win.std()), np.nan_to_num(acc_full.std()),
        rtol=1e-4, atol=1e-5,
    )


# ---- windowed reproject ----------------------------------------------------


def test_windowed_reproject_matches_full_reproject():
    """The windowed reproject, placed back at its (y0,x0), must equal the
    full-canvas reproject within the window region."""
    rng = np.random.default_rng(2)
    src_rgb = rng.random((320, 480, 3)).astype(np.float32)
    src_wcs = wcs_from_text(make_synth_wcs_text())
    # Destination shifted slightly so the footprint doesn't fill the canvas.
    dst_wcs = wcs_from_text(make_synth_wcs_text(ra_center_deg=83.6 + 0.05))
    dst_shape = (320, 480)

    full, full_valid = reproject_rgb(src_rgb, src_wcs, dst_wcs, dst_shape, use_gpu=False)
    result = reproject_rgb_windowed(src_rgb, src_wcs, dst_wcs, dst_shape, use_gpu=False)
    assert result is not None
    win, win_valid, y0, x0 = result

    wh, ww = win.shape[:2]
    # The window must be strictly smaller than the full canvas (the shift
    # pushed part of the footprint off-canvas).
    assert wh <= dst_shape[0] and ww <= dst_shape[1]
    assert (wh < dst_shape[0]) or (ww < dst_shape[1])

    full_sub = full[y0:y0 + wh, x0:x0 + ww]
    # Compare only where both agree on validity.
    both_valid = win_valid & full_valid[y0:y0 + wh, x0:x0 + ww]
    assert both_valid.any()
    np.testing.assert_allclose(
        win[both_valid], full_sub[both_valid], rtol=1e-4, atol=1e-3,
    )


def test_windowed_reproject_off_canvas_returns_none():
    rng = np.random.default_rng(3)
    src_rgb = rng.random((320, 480, 3)).astype(np.float32)
    src_wcs = wcs_from_text(make_synth_wcs_text())
    dst_wcs = wcs_from_text(make_synth_wcs_text(ra_center_deg=83.6 + 20.0))
    result = reproject_rgb_windowed(src_rgb, src_wcs, dst_wcs, (320, 480), use_gpu=False)
    assert result is None


def test_windowed_reproject_window_is_small_for_mosaic_panel():
    """A frame that lands in one corner of a big canvas should produce a
    window much smaller than the canvas — that's the whole optimization."""
    rng = np.random.default_rng(4)
    src_rgb = rng.random((320, 480, 3)).astype(np.float32)
    src_wcs = wcs_from_text(make_synth_wcs_text(ra_center_deg=50.0, dec_center_deg=10.0))
    # Big canvas centred well away from the frame, but still overlapping a corner.
    # Frame is ~0.67°×0.44°; place the canvas centre ~0.3° away so the frame
    # lands near an edge of a canvas several times larger.
    dst_wcs = wcs_from_text(
        make_synth_wcs_text(ra_center_deg=50.3, dec_center_deg=10.2,
                            width=1600, height=1200)
    )
    dst_shape = (1200, 1600)
    result = reproject_rgb_windowed(src_rgb, src_wcs, dst_wcs, dst_shape, use_gpu=False)
    assert result is not None
    win, _valid, _y0, _x0 = result
    # Window area should be a small fraction of the full canvas.
    win_area = win.shape[0] * win.shape[1]
    canvas_area = dst_shape[0] * dst_shape[1]
    assert win_area < 0.5 * canvas_area
