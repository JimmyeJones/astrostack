"""The streak detector reports *where* the flagged feature was.

Shape alone can't tell an edge-on galaxy from a satellite trail — both are
bright, long and elongated. Position across a session can
(``seestack.qc.runner.stationary_streak_frames``), and these pin that the
detector supplies it honestly: normalised to the frame so the numbers mean the
same thing at any sensor size, taken from the *largest* qualifying component,
and absent whenever nothing was flagged.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("skimage")

from seestack.qc.streaks import detect_streaks, detect_streaks_with_shape


def _sky(rng) -> np.ndarray:
    return rng.normal(100.0, 5.0, (540, 960)).astype(np.float32)


def _draw_streak(img, x0, y0, length=300, thickness=2, value=950.0):
    for i in range(length):
        x, y = x0 + i, y0 + i // 3
        for t in range(thickness):
            img[y + t, x] = value


def test_the_position_is_normalised_to_the_frame():
    rng = np.random.default_rng(1)
    img = _sky(rng)
    _draw_streak(img, 150, 120)
    detected, count, shape = detect_streaks_with_shape(
        img, sky_median=100.0, sky_std=5.0)
    assert detected is True and count > 0
    assert shape is not None
    # The drawn segment runs x 150→450, y 120→220 on a 960×540 plane, so its
    # centroid sits at ~(300/960, 170/540) — asserted as a box rather than to
    # the pixel, since the exact centroid depends on the bright-mask threshold.
    assert 0.28 < shape.cx < 0.35
    assert 0.28 < shape.cy < 0.36


def test_a_clean_frame_reports_no_position():
    rng = np.random.default_rng(2)
    detected, count, shape = detect_streaks_with_shape(
        _sky(rng), sky_median=100.0, sky_std=5.0)
    assert (detected, count, shape) == (False, 0, None)


def test_the_dominant_component_names_the_position():
    """With a big feature and a small one in the same frame, the position
    describes the big one — the tracked-object reading the reconciliation wants,
    not whichever component happened to be labelled first."""
    rng = np.random.default_rng(3)
    img = _sky(rng)
    _draw_streak(img, 500, 60, length=110, thickness=2)     # the small one
    _draw_streak(img, 100, 300, length=380, thickness=4)    # the big one
    _detected, _count, shape = detect_streaks_with_shape(
        img, sky_median=100.0, sky_std=5.0)
    assert shape is not None
    assert shape.cy > 0.5  # the lower, larger feature — not the one up top


def test_the_two_value_form_still_answers_the_same_way():
    """``detect_streaks`` is the historical shape of this call and is what the
    determinism test and older callers use; it must stay in step with the
    detailed form rather than becoming a second implementation."""
    rng = np.random.default_rng(4)
    img = _sky(rng)
    _draw_streak(img, 200, 100)
    detected, count, _shape = detect_streaks_with_shape(
        img, sky_median=100.0, sky_std=5.0)
    assert detect_streaks(img, sky_median=100.0, sky_std=5.0) == (detected, count)


def test_positions_are_stable_across_a_dithered_pair():
    """The reconciliation's whole premise: the same object shot twice with a
    small dither reports two positions well inside the cluster radius."""
    from seestack.qc.runner import STATIONARY_CLUSTER_RADIUS

    shapes = []
    for k, dx in enumerate((0, 6)):
        rng = np.random.default_rng(10 + k)
        img = _sky(rng)
        _draw_streak(img, 150 + dx, 120 + dx)
        _d, _c, shape = detect_streaks_with_shape(img, sky_median=100.0, sky_std=5.0)
        assert shape is not None
        shapes.append(shape)
    moved = np.hypot(shapes[0].cx - shapes[1].cx, shapes[0].cy - shapes[1].cy)
    assert moved < STATIONARY_CLUSTER_RADIUS
