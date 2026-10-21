"""The border trim on a **strided** coverage map must be true of the full-res map.

``editor._trim_rect_for_run`` measures a mosaic's coverage point-sampled
``[::step, ::step]`` (``_TRIM_MAX_DIM``), and ``coverage_trim._rect_from_mask``
answers ``c1 / w`` with ``c1`` exclusive — so the crop used to end at full-res
column ``c1·step`` while only ``(c1-1)·step`` was ever seen covered. On a canvas
whose panel edge falls between two samples that kept a band of no-coverage
(black) pixels along the trimmed picture's right/bottom edge (Scout 2026-10-21:
a 7-row band across a 7200×4800 mosaic). A field-rotated panel's slanted edge
can do the same between sampled rows, on any side.
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest
from astropy.io import fits

from seestack.edit.coverage_trim import (
    sampled_rect_to_full_res,
    shrink_rect_to_covered,
)
from seestack.edit.ops.geometry import crop_bounds
from webapp.routers import editor


def _mosaic_frame_counts(h: int, w: int, *, dither: int, rot_deg: float,
                         seed: int) -> np.ndarray:
    """A sharp-edged 2×2 S30-shaped frame-count map: four panels of 25 subs,
    each re-pointed by up to ``dither`` px and rotated by up to ``rot_deg``,
    NaN where no panel reached."""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    count = np.zeros((h, w), np.float32)
    ph, pw = 0.56 * h, 0.56 * w
    for cy, cx in ((0.28 * h, 0.28 * w), (0.28 * h, 0.72 * w),
                   (0.72 * h, 0.28 * w), (0.72 * h, 0.72 * w)):
        cy += rng.uniform(-dither, dither)
        cx += rng.uniform(-dither, dither)
        t = np.deg2rad(rng.uniform(-rot_deg, rot_deg))
        u = (xx - cx) * np.cos(t) + (yy - cy) * np.sin(t)
        v = -(xx - cx) * np.sin(t) + (yy - cy) * np.cos(t)
        count += 25.0 * ((np.abs(u) < pw / 2) & (np.abs(v) < ph / 2))
    count[count == 0] = np.nan
    return count


def _run_with_framecov(tmp_path, cov: np.ndarray):
    fits_path = tmp_path / "stack.fits"
    fits.PrimaryHDU(cov.astype(np.float32)).writeto(
        tmp_path / "stack_framecov.fits", overwrite=True)
    return SimpleNamespace(fits_path=str(fits_path), is_mosaic=True)


def _uncovered_inside(cov: np.ndarray, rect) -> int:
    h, w = cov.shape
    x0, y0, x1, y1 = rect
    b = crop_bounds(h, w, {"x0": x0, "y0": y0, "x1": x1, "y1": y1})
    assert b is not None
    bx0, bx1, by0, by1 = b
    inside = cov[by0:by1, bx0:bx1]
    return int((~(np.isfinite(inside) & (inside > 0))).sum())


# Each of these kept 31–3231 no-coverage pixels inside the old point-sampled crop.
@pytest.mark.parametrize("dither,rot_deg,seed", [
    (16, 0.0, 1), (16, 0.0, 3), (24, 0.0, 8), (30, 0.0, 6),
    (16, 1.0, 7), (20, 3.0, 3), (20, 3.0, 8), (40, 3.0, 3),
])
def test_strided_trim_keeps_no_uncovered_pixel(tmp_path, dither, rot_deg, seed):
    # 1503 × 2297 → step 5: panel edges land between samples.
    cov = _mosaic_frame_counts(1503, 2297, dither=dither, rot_deg=rot_deg, seed=seed)
    run = _run_with_framecov(tmp_path, cov)
    assert editor._trim_step_for(tmp_path / "stack_framecov.fits") == 5
    rect = editor._trim_rect_for_run(run)
    assert rect is not None
    assert _uncovered_inside(cov, rect) == 0
    # …and it is still the border trim, not a collapse: within half a percent of
    # the canvas of the point-sampled answer (≈ one stride per edge).
    old = editor.largest_covered_rect(cov[::5, ::5])
    keep = (rect[2] - rect[0]) * (rect[3] - rect[1])
    assert keep > (old[2] - old[0]) * (old[3] - old[1]) - 0.005


def test_small_unstrided_map_keeps_its_exact_answer(tmp_path):
    # ≤ _TRIM_MAX_DIM → step 1: the map *is* full-res and nothing re-reads it.
    cov = _mosaic_frame_counts(300, 400, dither=8, rot_deg=0.0, seed=1)
    run = _run_with_framecov(tmp_path, cov)
    assert editor._trim_step_for(tmp_path / "stack_framecov.fits") == 1
    rect = editor._trim_rect_for_run(run)
    assert rect is not None and _uncovered_inside(cov, rect) == 0


def test_sampled_rect_ends_at_the_last_sample_not_one_stride_past():
    # Samples 0..9 of a 10-wide grid at step 5 over a 48-wide map; a rect over
    # samples 2..7 (c1 = 8, exclusive) last *saw* column 35, so it ends at 36.
    x0, y0, x1, y1 = sampled_rect_to_full_res((0.2, 0.0, 0.8, 1.0), (4, 10), (18, 48), 5)
    assert (x0, x1) == (10, 36)
    assert (y0, y1) == (0, 16)


def test_shrink_walks_only_the_edge_that_holds_the_gap():
    cov = np.full((60, 80), 25.0, np.float32)
    cov[53:, :] = np.nan  # a band along the bottom
    cov[:, 77:] = 0.0  # and a no-coverage column strip on the right
    out = shrink_rect_to_covered(cov, (0, 0, 80, 60), band=3)
    # The bottom costs only the bottom rows and the right only its columns —
    # never a column off each side for the bottom band.
    assert out == (0, 0, 77, 53)


def test_shrink_reads_again_when_the_gap_is_deeper_than_its_band():
    cov = np.full((60, 80), 25.0, np.float32)
    cov[40:, :] = np.nan  # 20 rows deep, band 3
    assert shrink_rect_to_covered(cov, (0, 0, 80, 60), band=3) == (0, 0, 80, 40)


def test_shrink_answers_none_when_nothing_is_covered():
    cov = np.full((8, 8), np.nan, np.float32)
    assert shrink_rect_to_covered(cov, (0, 0, 8, 8), band=2) is None
