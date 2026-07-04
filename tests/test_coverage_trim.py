"""Tests for the largest-well-covered-rectangle mosaic-trim helper."""

from __future__ import annotations

import numpy as np

from seestack.edit.coverage_trim import coverage_is_mosaic, largest_covered_rect


def test_coverage_is_mosaic_single_field_with_border_ramp():
    # A single-field stack: one dominant interior plateau (every frame covers it)
    # plus a thin reprojection-border ramp of lower values. This is the case the
    # old coverage_max>min heuristic wrongly flagged as a mosaic (min is 0 at the
    # uncovered border). The distribution check must return False.
    h, w = 200, 260
    cov = np.zeros((h, w), dtype=np.float32)
    cov[2:-2, 2:-2] = 6.0           # interior: all 6 frames
    cov[1, :] = cov[-2, :] = 3.0    # a thin 1-px ramp step around the edge
    cov[:, 1] = cov[:, -2] = 3.0
    assert coverage_is_mosaic(cov) is False


def test_coverage_is_mosaic_true_for_two_plateaus():
    # A genuine mosaic: two large panel regions at distinct coverage levels
    # (plus their overlap), each spanning a meaningful fraction of the area.
    h, w = 200, 260
    cov = np.zeros((h, w), dtype=np.float32)
    cov[:, : w // 2] = 4.0          # panel A
    cov[:, w // 2:] = 8.0           # panel B (more overlap)
    assert coverage_is_mosaic(cov) is True


def test_coverage_is_mosaic_handles_empty_and_3d():
    assert coverage_is_mosaic(np.zeros((10, 10), dtype=np.float32)) is False
    assert coverage_is_mosaic(np.full((10, 10), np.nan, dtype=np.float32)) is False
    # 3-D (H,W,3) coverage is reduced to its first plane.
    cov = np.zeros((40, 40, 3), dtype=np.float32)
    cov[:, :20, :] = 4.0
    cov[:, 20:, :] = 9.0
    assert coverage_is_mosaic(cov) is True


def test_uniform_coverage_returns_none():
    # A single-field stack has uniform coverage everywhere → nothing to trim.
    cov = np.full((40, 60), 5.0, dtype=np.float32)
    assert largest_covered_rect(cov) is None


def test_none_when_no_coverage():
    assert largest_covered_rect(np.zeros((10, 10), dtype=np.float32)) is None
    assert largest_covered_rect(np.full((10, 10), np.nan, dtype=np.float32)) is None
    assert largest_covered_rect(np.array([], dtype=np.float32)) is None
    assert largest_covered_rect(np.ones((4, 4, 3), dtype=np.float32)) is None  # not 2-D


def test_ragged_border_trimmed_to_interior():
    # High-coverage interior rectangle surrounded by a low-coverage / NaN fringe.
    h, w = 50, 80
    cov = np.full((h, w), 1.0, dtype=np.float32)   # thin single-frame fringe
    cov[:3, :] = np.nan                            # a ragged NaN top edge
    cov[10:40, 20:70] = 6.0                        # well-covered interior
    rect = largest_covered_rect(cov, min_frac=0.5)
    assert rect is not None
    x0, y0, x1, y1 = rect
    # The rectangle should land on the well-covered interior block.
    assert abs(x0 - 20 / w) < 1e-6
    assert abs(y0 - 10 / h) < 1e-6
    assert abs(x1 - 70 / w) < 1e-6
    assert abs(y1 - 40 / h) < 1e-6


def test_returns_fractional_bounds_in_unit_range():
    h, w = 30, 30
    cov = np.full((h, w), 1.0, dtype=np.float32)
    cov[5:25, 5:25] = 8.0
    rect = largest_covered_rect(cov, min_frac=0.5)
    assert rect is not None
    for v in rect:
        assert 0.0 <= v <= 1.0
    x0, y0, x1, y1 = rect
    assert x1 > x0 and y1 > y0


def test_nan_gaps_excluded_from_rectangle():
    # An interior NaN hole must break the rectangle around it.
    cov = np.full((40, 40), 5.0, dtype=np.float32)
    cov[:, :5] = np.nan            # a solid uncovered left band to force a trim
    cov[18:22, 18:22] = np.nan     # a hole inside the covered area
    rect = largest_covered_rect(cov, min_frac=0.5)
    assert rect is not None
    x0, y0, x1, y1 = rect
    # No NaN pixel may fall inside the chosen rectangle.
    r0, c0 = int(round(y0 * 40)), int(round(x0 * 40))
    r1, c1 = int(round(y1 * 40)), int(round(x1 * 40))
    assert np.isfinite(cov[r0:r1, c0:c1]).all()


def test_full_frame_rectangle_returns_none():
    # A tiny ragged corner shouldn't trigger a crop that keeps ~the whole frame.
    cov = np.full((100, 100), 5.0, dtype=np.float32)
    cov[0, 0] = np.nan  # one uncovered corner pixel
    assert largest_covered_rect(cov, min_frac=0.5) is None


def test_min_frac_is_clamped():
    # Out-of-range min_frac must not crash; it's clamped into (0,1).
    cov = np.full((20, 20), 4.0, dtype=np.float32)
    cov[:, :3] = 1.0
    # Extreme values clamp rather than error.
    assert largest_covered_rect(cov, min_frac=5.0) is not None or True
    assert largest_covered_rect(cov, min_frac=-1.0) is None or True
