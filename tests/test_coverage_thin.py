"""What "thin coverage" is measured against — a panel's depth, not the peak.

``coverage_thin_fraction`` is the number "How's my stack?" judges a ragged border
on, and the note it drives offers a "Trim border" as the fix. Until v0.389.2 the
two disagreed on every mosaic: the share was measured against the coverage map's
**peak**, which on a tiled mosaic is the band where panels *overlap*, so a
quarter of it sits at or above whole panel interiors and ordinary panels counted
as border. The trim itself stopped measuring against the peak in D1
(``panel_coverage_level``), so the app was telling the owner that up to
three-quarters of his picture was a ragged edge and offering an action that kept
all of it.

The shapes below are the ones the owner actually shoots (a heavy mosaic user,
3x3 and larger rasters, uneven panel depth across many nights, quality weighting
on so coverage is a sum of *weights* rather than an integer count). Each is
checked against the trim the note offers, so the two can never drift apart again.
"""

from __future__ import annotations

import numpy as np
import pytest

from seestack.edit.coverage_trim import largest_covered_rect
from seestack.stack.stacker import (
    COVERAGE_SHARES_VERSION,
    coverage_median_depth,
    coverage_panel_depth,
    coverage_thin_fraction,
)


def _mosaic_cov(rows: int, cols: int, depths: dict[tuple[int, int], float],
                panel: int = 120, overlap: float = 0.10,
                jitter: float = 0.0, seed: int = 1) -> np.ndarray:
    """Weighted coverage map of a ``rows x cols`` raster of panels overlapping by
    ``overlap`` of a panel's side, ``depths[(r, c)]`` frames deep each.

    What this fixture can vouch for: **integer or weighted** panel depths, uneven
    depth between panels, and genuine two- and four-way overlap bands (the four-way
    corner is what makes the peak 4x a panel — the mechanism under test). What it
    cannot: anything about pixels, stars or seams — it is a coverage map, not a
    stack.
    """
    rng = np.random.default_rng(seed)
    step = int(round(panel * (1.0 - overlap)))
    h = step * (rows - 1) + panel
    w = step * (cols - 1) + panel
    cov = np.zeros((h, w), dtype=np.float64)
    for r in range(rows):
        for c in range(cols):
            n = float(depths[(r, c)])
            cov[r * step:r * step + panel, c * step:c * step + panel] += (
                n * (1.0 + jitter * rng.normal()) if jitter else n)
    return cov


def _trim_keeps(cov: np.ndarray) -> float:
    """The share of the canvas the "Trim border" this note offers would keep."""
    rect = largest_covered_rect(cov)
    if rect is None:
        return 1.0                      # nothing worth trimming — keeps it all
    x0, y0, x1, y1 = rect
    return (x1 - x0) * (y1 - y0)


def _uneven(rows: int, cols: int, lo: int, hi: int, seed: int):
    rng = np.random.default_rng(seed)
    return {(r, c): int(rng.integers(lo, hi + 1))
            for r in range(rows) for c in range(cols)}


# The shapes, and what the *old* peak-referenced rule reported for each. Every
# one of these fired the note (>= 5%) and offered a trim that keeps the whole
# canvas — which is the bug, stated as data.
MOSAIC_SHAPES = [
    ("2x2 sample, 6/6/6/3 subs",
     _mosaic_cov(2, 2, {(0, 0): 6, (0, 1): 6, (1, 0): 6, (1, 1): 3}), 0.22),
    ("3x3 equal 30 subs, 8% weight jitter",
     _mosaic_cov(3, 3, {(r, c): 30 for r in range(3) for c in range(3)},
                 jitter=0.08), 0.68),
    ("3x3 uneven 20-45 subs (a multi-night mosaic)",
     _mosaic_cov(3, 3, _uneven(3, 3, 20, 45, 7)), 0.47),
    ("12x8 raster, uneven 15-45 subs",
     _mosaic_cov(8, 12, _uneven(8, 12, 15, 45, 11), panel=60), 0.64),
    ("12x8 raster, uneven + 8% jitter",
     _mosaic_cov(8, 12, _uneven(8, 12, 15, 45, 11), panel=60,
                 jitter=0.08, seed=5), 0.74),
    ("1x2, 400 vs 100 subs",
     _mosaic_cov(1, 2, {(0, 0): 400, (0, 1): 100}), 0.47),
    ("lopsided 1x3, 12/1/1 subs",
     _mosaic_cov(1, 3, {(0, 0): 12, (0, 1): 1, (0, 2): 1}), 0.64),
]


@pytest.mark.parametrize("name,cov,old_share",
                         MOSAIC_SHAPES, ids=[s[0] for s in MOSAIC_SHAPES])
def test_a_mosaics_own_panels_are_not_a_ragged_border(name, cov, old_share):
    """Fails before: each of these reported 22-74 % of the picture "thin"."""
    # The fixture really is the shape it claims — a four-way (or, on the 1xN
    # strips, a two-way) overlap band above the panel depth, which is what makes
    # the peak the wrong reference in the first place.
    covered = cov[cov > 0]
    assert covered.max() > 1.3 * coverage_panel_depth(cov)
    # The old rule, reproduced here rather than asserted from memory.
    peak_referenced = float(np.count_nonzero(
        (cov > 0) & (cov < 0.25 * covered.max()))) / covered.size
    assert peak_referenced == pytest.approx(old_share, abs=0.05)

    assert coverage_thin_fraction(cov) < 0.02
    # …and the reason it must be: the action the note offers keeps the canvas.
    assert _trim_keeps(cov) > 0.98


def test_a_single_field_is_unchanged_to_the_digit():
    """The other half of the claim: the reference only moves on a mosaic. On a
    single field the panel depth *is* the peak, so every stack the owner has of
    one field grades exactly as it did."""
    cov = np.full((200, 200), 32.0)
    cov[0, :] = 3.0                       # a genuinely thin one-pixel fringe
    cov[:, 0] = 3.0
    peak_referenced = float(np.count_nonzero(
        (cov > 0) & (cov < 0.25 * cov.max()))) / np.count_nonzero(cov > 0)
    assert coverage_thin_fraction(cov) == pytest.approx(peak_referenced)
    assert coverage_panel_depth(cov) == pytest.approx(32.0)


def test_a_dithered_fringe_is_still_reported_on_a_single_field():
    """The measure still does its job: a real ramp of thinly-covered edge pixels
    is what it exists to find."""
    cov = np.full((100, 100), 40.0)
    cov[:5, :] = 4.0                      # 5 % of the picture, a tenth as deep
    assert coverage_thin_fraction(cov) == pytest.approx(0.05)


def test_a_mosaic_with_a_genuine_ragged_fringe_still_reports_it():
    """The panel reference is not a way of never firing on a mosaic: a union
    canvas' single-frame fringe is below a quarter of a panel too."""
    cov = _mosaic_cov(2, 2, {(0, 0): 30, (0, 1): 30, (1, 0): 30, (1, 1): 30})
    cov[:6, :] = 1.0                      # the ragged top edge of the canvas
    share = coverage_thin_fraction(cov)
    assert share is not None and share > 0.02
    assert _trim_keeps(cov) < 0.98        # …and trimming it genuinely helps


def test_nothing_covered_is_still_no_answer():
    assert coverage_thin_fraction(np.zeros((10, 10))) is None
    assert coverage_panel_depth(np.zeros((10, 10))) is None
    assert coverage_median_depth(np.zeros((10, 10))) is None


def test_the_panel_depth_estimate_is_bounded_on_a_big_canvas():
    """It runs at stack time on the full canvas, and ``panel_coverage_level``
    sorts a float64 copy of whatever it is handed — so what it is handed is a
    strided sample, and the sample must give the same answer."""
    from seestack.stack.stacker import _covered_depth_sample

    cov = _mosaic_cov(3, 3, {(r, c): 30 for r in range(3) for c in range(3)},
                      panel=1200)
    assert cov.size > 2_000_000
    assert _covered_depth_sample(cov).size <= 2_000_000
    assert coverage_panel_depth(cov) == pytest.approx(30.0)
    assert coverage_thin_fraction(cov) < 0.02


# --- the median depth: what a mosaic's κ-σ reach is really judged on ----------


def test_the_median_depth_describes_the_canvas_where_the_peak_describes_a_corner():
    """A 2x2 mosaic three subs deep presents a peak of 12 — the corner where four
    panels meet — to a question whose answer nearly everywhere is 3."""
    cov = _mosaic_cov(2, 2, {(0, 0): 3, (0, 1): 3, (1, 0): 3, (1, 1): 3})
    assert cov.max() == pytest.approx(12.0)
    assert coverage_median_depth(cov) == pytest.approx(3.0)


def test_on_a_single_field_the_median_is_the_peak():
    cov = np.full((100, 100), 18.0)
    cov[0, :] = 2.0
    assert coverage_median_depth(cov) == pytest.approx(18.0)


# --- the stack stamps the rule it measured by --------------------------------


def test_a_run_records_and_reads_back_the_rule_and_the_median_depth(tmp_path):
    from seestack.io.project import Project, StackRunRow

    proj = Project.create(tmp_path / "t", name="T")
    try:
        proj.add_stack_run(StackRunRow(
            id=None, timestamp_utc="2026-09-08T00:00:00+00:00",
            output_basename="m42", fits_path=None, tiff_path=None,
            preview_path=None, n_frames_used=30, canvas_h=10, canvas_w=10,
            coverage_min=0, coverage_max=30, options_json="{}",
            coverage_thin_frac=0.01,
            coverage_shares_version=COVERAGE_SHARES_VERSION,
            coverage_median_depth=7.5,
        ))
        run = next(iter(proj.iter_stack_runs()))
        assert run.coverage_shares_version == COVERAGE_SHARES_VERSION
        assert run.coverage_median_depth == pytest.approx(7.5)
    finally:
        proj.close()


def test_an_older_project_gains_both_columns_on_open_without_a_version_bump(tmp_path):
    """Upgrade safety (§9), and specifically *rollback* safety: both columns are
    additive through ``_reconcile_table_columns`` rather than through a
    ``SCHEMA_VERSION`` bump, so a build that has never heard of them can still
    open a DB this build wrote."""
    import sqlite3

    from seestack.io.project import Project, StackRunRow

    def _row(**kw):
        base = dict(
            id=None, timestamp_utc="2026-09-08T00:00:00+00:00",
            output_basename="old", fits_path=None, tiff_path=None,
            preview_path=None, n_frames_used=30, canvas_h=10, canvas_w=10,
            coverage_min=0, coverage_max=30, options_json="{}")
        base.update(kw)
        return StackRunRow(**base)

    proj = Project.create(tmp_path / "t", name="T")
    try:
        proj.add_stack_run(_row(coverage_thin_frac=0.4))
        version_before = proj._conn.execute(  # noqa: SLF001 — the point of the test
            "PRAGMA user_version").fetchone()[0]
    finally:
        proj.close()

    db = tmp_path / "t" / "project.sqlite"
    conn = sqlite3.connect(db)
    try:
        conn.execute("ALTER TABLE stack_runs DROP COLUMN coverage_shares_version")
        conn.execute("ALTER TABLE stack_runs DROP COLUMN coverage_median_depth")
        conn.commit()
    finally:
        conn.close()

    proj = Project.open(tmp_path / "t")
    try:
        runs = list(proj.iter_stack_runs())
        assert [r.output_basename for r in runs] == ["old"]
        assert runs[0].coverage_shares_version is None   # "an older rule"
        assert runs[0].coverage_median_depth is None
        assert runs[0].coverage_thin_frac == pytest.approx(0.4)  # kept, never reset
        proj.add_stack_run(_row(output_basename="new",
                                coverage_shares_version=COVERAGE_SHARES_VERSION,
                                coverage_median_depth=4.0))
        fresh = {r.output_basename: r for r in proj.iter_stack_runs()}
        assert fresh["new"].coverage_shares_version == COVERAGE_SHARES_VERSION
    finally:
        proj.close()

    conn = sqlite3.connect(db)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == version_before
    finally:
        conn.close()
