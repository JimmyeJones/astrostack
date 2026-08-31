"""How much of the picture is thinly covered — the honest ragged-border measure.

``coverage_min`` is the *extreme* minimum over the canvas, so on any dithered
stack it is 1 (one fringe pixel was touched by one frame) and the ratio
``coverage_min / coverage_max`` is 1/N: it falls as the owner shoots more subs,
on a border that never changed. ``coverage_thin_fraction`` asks instead what
*share* of the covered picture is thin, which is a property of the geometry and
is stable in N.
"""

from __future__ import annotations

import numpy as np
import pytest

from seestack.stack.stacker import COVERAGE_THIN_RATIO, coverage_thin_fraction


def _dithered_coverage(n_subs: int, ramp_px: int = 6, size: int = 480):
    """A square canvas covered by ``n_subs`` frames offset by up to ``ramp_px``:
    a full-count interior with a linear ramp of that width around it."""
    cov = np.full((size, size), float(n_subs))
    for i in range(ramp_px):
        # Each ring in from the edge is covered by proportionally more frames.
        level = max(1.0, round(n_subs * (i + 1) / (ramp_px + 1)))
        cov[i, i:size - i] = level
        cov[size - 1 - i, i:size - i] = level
        cov[i:size - i, i] = level
        cov[i:size - i, size - 1 - i] = level
    return cov


def test_a_dithered_border_stays_a_couple_of_percent_however_deep_the_stack():
    """The whole point: the same geometry must give the same answer at 8 and at
    128 subs, where the old coverage_min/max ratio ran 0.125 → 0.008."""
    shares = [coverage_thin_fraction(_dithered_coverage(n))
              for n in (8, 32, 128)]
    assert all(s is not None and s < 0.05 for s in shares), shares
    # Stable, not merely small: the spread across a 16× deeper stack is tiny.
    assert max(shares) - min(shares) < 0.01, shares
    # …and the measure the old note used calls every one of these a ragged
    # border, at every depth, on a border that is a few pixels of ramp.
    old = [float(_dithered_coverage(n).min()) / n for n in (8, 32, 128)]
    assert all(ratio <= COVERAGE_THIN_RATIO for ratio in old), old


def test_a_lopsided_mosaic_reads_as_mostly_thin():
    # Two thirds of the canvas got one frame; the last third got twelve.
    cov = np.ones((300, 300))
    cov[:, 200:] = 12.0
    share = coverage_thin_fraction(cov)
    assert share == pytest.approx(2 / 3, abs=0.01)


def test_uncovered_pixels_are_not_part_of_the_picture():
    # A mosaic's canvas corners are covered by nothing at all. They are not a
    # thin border — they are outside the image — so they must not count either
    # way. (This is precisely what made coverage_min 0 on every mosaic.)
    cov = np.full((100, 100), 10.0)
    cov[:50, :50] = 0.0
    assert coverage_thin_fraction(cov) == 0.0


def test_an_entirely_even_stack_has_no_thin_share():
    assert coverage_thin_fraction(np.full((50, 50), 20.0)) == 0.0


def test_nothing_covered_is_no_answer_rather_than_zero():
    # "No thin border" and "no picture" are different claims; only the first is
    # something a health note may act on.
    assert coverage_thin_fraction(np.zeros((10, 10))) is None
    assert coverage_thin_fraction(np.array([])) is None


def test_the_threshold_is_a_share_of_the_peak():
    cov = np.array([[100.0, 100.0], [24.0, 26.0]])
    assert COVERAGE_THIN_RATIO == 0.25
    # 24 is under a quarter of 100 and 26 is over it: exactly one of four pixels.
    assert coverage_thin_fraction(cov) == 0.25


# --- the stack records it, and an older project migrates to NULL -------------


def _row(**kw):
    from seestack.io.project import StackRunRow

    base = dict(
        id=None, timestamp_utc="2026-08-31T00:00:00+00:00", output_basename="m42",
        fits_path=None, tiff_path=None, preview_path=None, n_frames_used=30,
        canvas_h=100, canvas_w=100, coverage_min=1, coverage_max=30,
        options_json="{}",
    )
    base.update(kw)
    return StackRunRow(**base)


def test_a_run_records_and_reads_back_its_thin_share(tmp_path):
    from seestack.io.project import Project

    proj = Project.create(tmp_path / "t", name="T")
    try:
        proj.add_stack_run(_row(coverage_thin_frac=0.0123))
        assert next(iter(proj.iter_stack_runs())).coverage_thin_frac == pytest.approx(
            0.0123)
    finally:
        proj.close()


def test_an_older_project_migrates_and_keeps_its_runs(tmp_path):
    """Upgrade safety (§9): a project written before the column existed must
    open, keep every row, and simply answer None."""
    import sqlite3

    from seestack.io.project import Project

    proj = Project.create(tmp_path / "t", name="T")
    try:
        proj.add_stack_run(_row(output_basename="old", coverage_thin_frac=0.5))
    finally:
        proj.close()

    # Roll the DB back to the schema-19 shape a live install would be on.
    conn = sqlite3.connect(tmp_path / "t" / "project.sqlite")
    try:
        conn.execute("ALTER TABLE stack_runs DROP COLUMN coverage_thin_frac")
        conn.execute("PRAGMA user_version = 19")
        conn.commit()
    finally:
        conn.close()

    proj = Project.open(tmp_path / "t")
    try:
        runs = list(proj.iter_stack_runs())
        assert [r.output_basename for r in runs] == ["old"]
        assert runs[0].coverage_thin_frac is None
        # …and the migrated DB records the share on the next stack.
        proj.add_stack_run(_row(output_basename="new", coverage_thin_frac=0.25))
        fresh = {r.output_basename: r for r in proj.iter_stack_runs()}
        assert fresh["new"].coverage_thin_frac == pytest.approx(0.25)
        assert fresh["old"].coverage_thin_frac is None
    finally:
        proj.close()


def test_a_real_stack_records_its_thin_share(tmp_path):
    """End-to-end wiring: the number the note reads comes off a genuine run.

    Five frames on one pointing cover the canvas identically, so nothing is thin
    — the share is a measured 0, not a missing value, and that is what lets the
    panel say "even coverage" instead of staying quiet.
    """
    pytest.importorskip("astropy")
    pytest.importorskip("PIL")
    pytest.importorskip("tifffile")

    from seestack.stack.stacker import StackOptions, run_stack
    from tests.test_stack_pipeline import _build_project

    proj = _build_project(tmp_path, n=5)
    try:
        run_stack(proj, StackOptions(sigma_clip=False, max_workers=2,
                                     output_name="cov"))
        run = next(iter(proj.iter_stack_runs()))
    finally:
        proj.close()
    assert run.coverage_thin_frac == 0.0
