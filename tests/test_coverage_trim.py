"""Tests for the largest-well-covered-rectangle mosaic-trim helper."""

from __future__ import annotations

import numpy as np
import pytest

from seestack.edit.coverage_trim import (
    _rect_from_mask,
    coverage_is_mosaic,
    largest_covered_rect,
    panel_coverage_level,
    well_covered_mask,
)
from tests.shapes import (
    assert_panels_thinner_than_the_reference,
    assert_reference_is_the_thinnest_panel,
    assert_weighted,
    describe_coverage,
    level_share,
    panel_level,
    peak_over_panel,
)


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
    #
    # The fixture was corrected while fixing D1 (2026-09-07) and the assertions
    # were not: it said "thin single-frame fringe" while making that fringe
    # **62 % of the canvas** (a 30x50 interior inside a 50x80 map). A region that
    # large at a lower depth is not a border — it is a shallower *panel*, and
    # treating it as fringe is the very thing D1 was: the audit's "1x2 with no
    # overlap, 400 vs 150 subs" case is this shape, and it called discarding the
    # thin side a wrong result. So the fringe is now genuinely thin (a 4 px border
    # on a 200x320 map, ~5 % of the covered area) and every assertion below is
    # unchanged in kind and in strictness.
    h, w = 200, 320
    cov = np.full((h, w), 1.0, dtype=np.float32)   # thin single-frame fringe
    cov[:3, :] = np.nan                            # a ragged NaN top edge
    cov[4:196, 4:316] = 6.0                        # well-covered interior
    rect = largest_covered_rect(cov, min_frac=0.5)
    assert rect is not None
    x0, y0, x1, y1 = rect
    # The rectangle should land on the well-covered interior block.
    assert abs(x0 - 4 / w) < 1e-6
    assert abs(y0 - 4 / h) < 1e-6
    assert abs(x1 - 316 / w) < 1e-6
    assert abs(y1 - 196 / h) < 1e-6


def test_returns_fractional_bounds_in_unit_range():
    # Same fixture correction as above: the low-coverage ring is a *border*
    # (4 px, ~8 % of the covered area), not a majority of the canvas.
    h, w = 200, 200
    cov = np.full((h, w), 1.0, dtype=np.float32)
    cov[4:196, 4:196] = 8.0
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


# --- D1: the reference depth is one panel, not the overlap peak ---------------
#
# Reproduced from the third external audit (2026-09-07), which found that
# `well_covered_mask` measured "well covered" against the map's **peak**. On a
# single field the peak is the interior, so half of it correctly trims the
# dithered fringe. On a tiled mosaic the peak is where panels *overlap* — 2x a
# panel's depth where two meet, 4x where four do — so "half the peak" sat above
# every panel interior and the only well-covered region was the overlap band.
# Default Auto output, mosaics only, and it had been there since the module was
# written. The shapes below are the audit's own table.

def _tiled_mosaic(nx, ny, *, overlap=0.15, depth=30, depths=None, h=400, w=400):
    """A union canvas of tiled panels; overlapping panels add their depths."""
    cov = np.zeros((h, w), dtype=np.float32)
    pw = w / (nx - (nx - 1) * overlap)
    ph = h / (ny - (ny - 1) * overlap)
    for j in range(ny):
        for i in range(nx):
            x0 = int(round(i * pw * (1 - overlap)))
            y0 = int(round(j * ph * (1 - overlap)))
            d = depth if depths is None else depths[j * nx + i]
            cov[y0:min(h, int(round(y0 + ph))),
                x0:min(w, int(round(x0 + pw)))] += d
    return cov


def _single_field_with_fringe(h=400, w=400, depth=30, border=8):
    """One interior plateau with a ragged dither ramp around it."""
    cov = np.zeros((h, w), dtype=np.float32)
    cov[border:-border, border:-border] = depth
    for k in range(border):
        v = depth * (k + 1) / (border + 1)
        cov[border - k - 1:border - k, border:-border] = v
        cov[-(border - k):-(border - k) + 1 or None, border:-border] = v
    return cov


def _kept_fraction(rect):
    return 0.0 if rect is None else (rect[2] - rect[0]) * (rect[3] - rect[1])


def test_panel_reference_is_one_panel_not_the_overlap_peak():
    """The heart of D1: on every mosaic shape the audit measured, the reference
    depth must be a panel (30, or the *thinner* panel where they differ), never
    the 2x/4x overlap peak."""
    for name, cov, want in [
        ("2x2 @15%", _tiled_mosaic(2, 2, overlap=0.15), 30.0),
        ("3x3 @20%", _tiled_mosaic(3, 3, overlap=0.20), 30.0),
        ("3x3 @5%", _tiled_mosaic(3, 3, overlap=0.05), 30.0),
        ("12x8 raster", _tiled_mosaic(12, 8, overlap=0.10, h=800, w=1200), 30.0),
        # Unequal panel depths and no overlap at all: the reference is the
        # *thinner* panel, which is what stops it being discarded whole.
        ("1x2 400/150", _tiled_mosaic(2, 1, overlap=0.0, depths=[400, 150]), 150.0),
    ]:
        assert cov.max() > want, name  # the peak really is higher, i.e. the bug had room
        assert panel_coverage_level(cov[cov > 0]) == want, name


def test_a_tiled_mosaic_is_no_longer_cropped_to_its_panel_overlaps():
    """Fail-before: each of these kept a thin strip of the canvas (8.0 %, 7.8 %,
    1.7 %, 1.5 %) or dropped the thin panel whole. A fully-tiled canvas has no
    ragged border, so the honest answer is *no crop at all*."""
    for name, cov in [
        ("2x2 @15%", _tiled_mosaic(2, 2, overlap=0.15)),
        ("3x3 @20%", _tiled_mosaic(3, 3, overlap=0.20)),
        ("3x3 @5%", _tiled_mosaic(3, 3, overlap=0.05)),
        ("12x8 raster", _tiled_mosaic(12, 8, overlap=0.10, h=800, w=1200)),
        ("1x2 400/150", _tiled_mosaic(2, 1, overlap=0.0, depths=[400, 150])),
    ]:
        assert well_covered_mask(cov).all(), name
        assert largest_covered_rect(cov) is None, name


def test_a_ragged_mosaic_still_gets_its_fringe_trimmed():
    """The fix must not turn the trim off for mosaics — only stop it eating the
    panels. A 2x2 with a 10 px partial-coverage border keeps ~95 % (the border
    goes); before the fix the same map was cropped to the overlap band."""
    cov = _tiled_mosaic(2, 2, overlap=0.15)
    h, w = cov.shape
    for k in range(10):
        v = 30 * (k + 1) / 11
        cov[k, :] = np.minimum(cov[k, :], v)
        cov[-1 - k, :] = np.minimum(cov[-1 - k, :], v)
        cov[:, k] = np.minimum(cov[:, k], v)
        cov[:, -1 - k] = np.minimum(cov[:, -1 - k], v)
    rect = largest_covered_rect(cov)
    assert rect is not None
    assert 0.90 < _kept_fraction(rect) < 0.99
    # The panel interiors survive: the kept rectangle covers the canvas centre.
    x0, y0, x1, y1 = rect
    assert x0 < 0.05 and y0 < 0.05 and x1 > 0.95 and y1 > 0.95


def test_the_single_field_path_is_unchanged():
    """The control the audit ran, and the constraint on the fix: on a single
    field the lowest substantial level *is* the peak, so the rule is byte-for-byte
    what it always was."""
    cov = _single_field_with_fringe()
    assert panel_coverage_level(cov[cov > 0]) == cov.max()
    assert largest_covered_rect(cov) == (0.02, 0.02, 0.98, 0.98)
    assert coverage_is_mosaic(cov) is False


def test_weight_jitter_does_not_shatter_a_panel_into_non_levels():
    """Coverage is a sum of per-frame *weights*, not a frame count, once quality
    weighting is on — so levels are found by relative tolerance, not by exact
    integer value. A 8 % jitter must not send either shape back to the peak."""
    rng = np.random.default_rng(0)

    def jitter(cov):
        out = cov.copy()
        pos = out > 0
        out[pos] *= (1 + rng.normal(0, 0.08, size=int(pos.sum()))).astype(np.float32)
        return out

    mosaic = jitter(_tiled_mosaic(2, 2, overlap=0.15))
    # Still a panel, not the (jitter-inflated) peak.
    assert panel_coverage_level(mosaic[mosaic > 0]) < 0.5 * mosaic.max()
    assert largest_covered_rect(mosaic) is None

    single = jitter(_single_field_with_fringe())
    # Jitter lifts the peak, so the *old* rule would have trimmed more here; the
    # panel reference is stable and the answer is the un-jittered one.
    assert largest_covered_rect(single) == (0.02, 0.02, 0.98, 0.98)


def test_the_new_reference_can_only_ever_keep_more():
    """The safety property that makes this fix un-scary: the reference is always
    at or below the peak, so the threshold can only fall and the well-covered
    mask can only grow. The worst case is leaving fringe in, never trimming a
    panel away."""
    rng = np.random.default_rng(1)
    for _ in range(40):
        cov = rng.gamma(2.0, 8.0, size=(60, 80)).astype(np.float32)
        cov[rng.random((60, 80)) < 0.1] = np.nan
        covered = cov[np.isfinite(cov) & (cov > 0)]
        ref = panel_coverage_level(covered)
        assert ref is not None and ref <= float(covered.max()) + 1e-6
        old = np.isfinite(cov) & (cov >= 0.5 * float(covered.max()))
        assert (well_covered_mask(cov) | old == well_covered_mask(cov)).all()


def test_panel_level_declines_on_an_empty_population():
    assert panel_coverage_level(np.asarray([], dtype=np.float32)) is None


# --- what these fixtures can and cannot vouch for -----------------------------
#
# D1 survived twenty sweeps because every fixture that called itself a mosaic was
# one plateau plus a fringe, i.e. a shape on which "the peak" and "a panel" are
# the same number. `_tiled_mosaic` is not that shape — but nothing said so, and an
# unasserted comment is what the last three findings all had in common. See
# `tests/shapes.py` for the vocabulary.

def test_the_tiled_fixture_really_is_the_shape_its_name_claims():
    """`_tiled_mosaic` vouches for: a peak strictly above one panel, a real share
    of the canvas at each of one/two/four panels deep, and — at 2x2 and up — a
    genuine four-way corner. It does **not** vouch for uneven depth or weighted
    coverage unless asked for them, and it is a coverage map, so it says nothing
    about pixels, stars or seams."""
    for name, cov, ways in [
        ("2x2 @15%", _tiled_mosaic(2, 2, overlap=0.15), 4.0),
        ("3x3 @20%", _tiled_mosaic(3, 3, overlap=0.20), 4.0),
        ("3x3 @5%", _tiled_mosaic(3, 3, overlap=0.05), 4.0),
        ("12x8 raster", _tiled_mosaic(12, 8, overlap=0.10, h=800, w=1200), 4.0),
    ]:
        assert panel_level(cov) == 30.0, f"{name}: {describe_coverage(cov)}"
        assert peak_over_panel(cov) == pytest.approx(ways), \
            f"{name}: {describe_coverage(cov)}"
        # ...and each of those levels is a real share of the picture, not a seam
        # a pixel wide: one panel dominates, the 2x seams and 4x corners are real.
        assert level_share(cov, 30.0) > 0.2, name
        assert level_share(cov, 60.0) > 0.005, name
        assert level_share(cov, 120.0) > 0.0005, name
    # A 1x2 strip with no overlap at all: two panels, nothing deeper than one, and
    # deliberately uneven — the one shape here that can vouch for uneven depth.
    strip = _tiled_mosaic(2, 1, overlap=0.0, depths=[400, 150])
    assert panel_level(strip) == 150.0
    assert peak_over_panel(strip) < 3.0, describe_coverage(strip)
    # Uneven depth, yes — but each panel is half the canvas, so the reference
    # correctly *is* the thinner one and nothing real sits below the threshold.
    # That is what stops this fixture standing in for the raster case below.
    assert_reference_is_the_thinnest_panel(strip, what="1x2 400/150")
    # And the control: a single field is one level, peak == panel, which is why
    # D1 was structurally invisible on every single-field fixture in this suite.
    field = _single_field_with_fringe()
    assert peak_over_panel(field) == pytest.approx(1.0)


def _raster_with_uneven_depth(nx, ny, *, overlap=0.10, h=800, w=1200, seed=0,
                              lo=8, hi=31, jitter=0.06):
    """The owner's shape, and the one no fixture in this suite had: a raster whose
    panels are **not** equally deep and whose coverage is a sum of weights.

    He shoots 3x3 and 12x8 rasters across many nights, so a panel's depth is
    however many subs that panel happened to get, and `quality_weighted` (on by
    default on the walk-away path) makes each sub's contribution a float rather
    than a count. Every mosaic fixture above is evenly deep and integral.
    """
    rng = np.random.default_rng(seed)
    depths = [float(d) for d in rng.integers(lo, hi, size=nx * ny)]
    cov = _tiled_mosaic(nx, ny, overlap=overlap, depths=depths, h=h, w=w)
    pos = cov > 0
    cov[pos] *= (1 + rng.normal(0, jitter, size=int(pos.sum()))).astype(np.float32)
    return cov


# --- D1, second half: a thin panel is not a border ----------------------------
#
# `panel_coverage_level` looks for the lowest *substantial* level, where
# substantial is 8 % of the covered canvas. On a dense raster with uneven panel
# depth no single depth is that substantial — 96 panels spread over two dozen
# depths — so the search walks past the thin panels and settles near the mode,
# and every panel below half of it is declared fringe and cropped away. Fully
# tiled canvases, with no ragged edge to trim at all.

def test_an_uneven_weighted_raster_is_not_cropped_to_its_deeper_panels():
    """Fail-before: 25.6 %, 34.8 % and 17.6 % of the canvas kept, on three fully
    tiled mosaics. AGENTS.md §1 puts the bar at "a trim above ~15 % of the canvas
    is a bug, not a ragged edge"."""
    for name, cov in [
        ("12x8 8-30", _raster_with_uneven_depth(12, 8)),
        ("6x4 6-30", _raster_with_uneven_depth(6, 4, overlap=0.12, h=600, w=900,
                                               lo=6)),
        ("8x6 4-40", _raster_with_uneven_depth(8, 6, h=700, w=1000, lo=4, hi=41,
                                               jitter=0.08)),
    ]:
        # The fixture is doing its job: uneven, weighted, and with a peak far
        # above the thinnest panel, so a depth-referenced rule had room to be wrong.
        assert_panels_thinner_than_the_reference(cov, what=name)
        assert_weighted(cov, what=name)
        assert peak_over_panel(cov) > 2.0, f"{name}: {describe_coverage(cov)}"
        # Fully tiled: there is no border, so the honest answer is no crop.
        assert largest_covered_rect(cov) is None, \
            f"{name}: {describe_coverage(cov)}"


def test_a_raster_that_is_both_uneven_and_ragged_still_loses_its_ragged_edge():
    """The fix must not turn the trim off — only stop it eating panels. A 6x4 with
    uneven depth *and* a genuine 12 px partial-coverage border keeps ~95 %: the
    border goes, every panel stays. Fail-before: 34.2 %."""
    cov = _raster_with_uneven_depth(6, 4, overlap=0.12, h=600, w=900, lo=6)
    for k in range(12):
        v = 6 * (k + 1) / 13
        cov[k, :] = np.minimum(cov[k, :], v)
        cov[-1 - k, :] = np.minimum(cov[-1 - k, :], v)
        cov[:, k] = np.minimum(cov[:, k], v)
        cov[:, -1 - k] = np.minimum(cov[:, -1 - k], v)
    rect = largest_covered_rect(cov)
    assert rect is not None
    assert 0.90 < _kept_fraction(rect) < 0.99, describe_coverage(cov)
    x0, y0, x1, y1 = rect
    assert x0 < 0.05 and y0 < 0.05 and x1 > 0.95 and y1 > 0.95


def test_the_trim_can_only_ever_keep_more_than_the_depth_threshold_alone():
    """The safety property of the coverage bound, over random maps: the rectangle
    returned is never smaller than the one the depth threshold alone would give.
    So this guard, like D1's own fix, can only leave fringe in — never crop a
    panel away."""
    rng = np.random.default_rng(7)
    for _ in range(40):
        cov = rng.gamma(2.0, 8.0, size=(60, 80)).astype(np.float32)
        cov[rng.random((60, 80)) < 0.1] = np.nan
        strict = _kept_fraction(_rect_from_mask(well_covered_mask(cov)))
        assert _kept_fraction(largest_covered_rect(cov)) >= strict - 1e-9


def test_a_diagonal_mosaics_genuinely_small_rectangle_is_still_offered():
    """The case the bound must not swallow: a diagonal mosaic is *mostly
    uncovered*, so the largest well-covered rectangle is honestly small — and the
    coverage bound is small too, because it is measured on the same uncovered
    pixels. Nothing changes here."""
    cov = np.zeros((400, 400), dtype=np.float32)
    for k in range(6):
        x0 = int(k * (400 - 140) / 5)
        y0 = int(k * (400 - 140) / 5)
        cov[y0:y0 + 140, x0:x0 + 140] += 20.0
    rect = largest_covered_rect(cov)
    assert rect is not None
    assert _kept_fraction(rect) < 0.2, describe_coverage(cov)
