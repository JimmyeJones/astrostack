"""How much of the canvas is empty black — the measure nothing else records.

``coverage_thin_fraction`` answers "how much of the *picture* is a thin border",
and does it over the covered pixels only: uncovered pixels are in neither its
numerator nor its denominator, by construction. So a mosaic whose union canvas
is a third empty corners can report a thin share of 0.00, and every surface that
reads it stays silent about the one thing a beginner is actually staring at.
``uncovered_fraction`` is that missing quantity: the share of *every* canvas
pixel no frame reached.
"""

from __future__ import annotations

import numpy as np
import pytest

from seestack.stack.stacker import coverage_thin_fraction, uncovered_fraction


def test_an_empty_corner_is_measured_where_the_thin_share_is_blind_to_it():
    """The reason this exists, stated as a test: the same canvas, one measure
    reads zero and the other reads the black."""
    cov = np.full((100, 100), 10.0)
    cov[:50, :50] = 0.0            # a quarter of the canvas, covered by nothing
    assert coverage_thin_fraction(cov) == 0.0
    assert uncovered_fraction(cov) == pytest.approx(0.25)


def test_a_fully_covered_canvas_has_no_black():
    assert uncovered_fraction(np.full((40, 60), 7.0)) == 0.0


def test_nan_counts_as_uncovered_not_as_a_sample():
    """A coverage map holds counts, so a NaN is an absence. Comparing it the
    naive way round (``cov <= 0``) would call it covered."""
    cov = np.full((10, 10), 5.0)
    cov[0, :] = np.nan
    assert uncovered_fraction(cov) == pytest.approx(0.1)


def test_nothing_covered_is_no_answer_rather_than_one():
    """An empty canvas is not "a picture that is 100% black" — it is no picture,
    and a health note must stay silent rather than describe it."""
    assert uncovered_fraction(np.zeros((10, 10))) is None
    assert uncovered_fraction(np.full((4, 4), np.nan)) is None
    assert uncovered_fraction(np.array([])) is None


def test_it_is_a_share_of_the_whole_canvas_not_of_the_covered_part():
    """The denominators are the whole difference between the two measures: hold
    the black fixed and grow the covered area, and only this one stays put."""
    cov = np.zeros((10, 20))
    cov[:, :10] = 4.0              # half covered, half black
    assert uncovered_fraction(cov) == pytest.approx(0.5)
    wider = np.zeros((10, 30))
    wider[:, :20] = 4.0            # same 100 black pixels, twice the picture
    assert uncovered_fraction(wider) == pytest.approx(1 / 3)


def test_coverage_of_one_frame_still_counts_as_covered():
    """A fringe pixel one sub touched is thin, not empty — the two measures must
    not both claim it."""
    cov = np.full((10, 10), 12.0)
    cov[0, :] = 1.0
    assert uncovered_fraction(cov) == 0.0
    assert coverage_thin_fraction(cov) == pytest.approx(0.1)


# --- the stack records it, and an older project keeps working ----------------


def _row(**kw):
    from seestack.io.project import StackRunRow

    base = dict(
        id=None, timestamp_utc="2026-09-07T00:00:00+00:00", output_basename="m42",
        fits_path=None, tiff_path=None, preview_path=None, n_frames_used=30,
        canvas_h=100, canvas_w=100, coverage_min=0, coverage_max=30,
        options_json="{}",
    )
    base.update(kw)
    return StackRunRow(**base)


def test_a_run_records_and_reads_back_its_empty_share(tmp_path):
    from seestack.io.project import Project

    proj = Project.create(tmp_path / "t", name="T")
    try:
        proj.add_stack_run(_row(uncovered_frac=0.2345))
        assert next(iter(proj.iter_stack_runs())).uncovered_frac == pytest.approx(
            0.2345)
    finally:
        proj.close()


def test_an_older_project_gains_the_column_on_open_without_a_version_bump(tmp_path):
    """Upgrade safety (§9), and specifically *rollback* safety: the column is
    additive through ``_reconcile_table_columns`` rather than through a
    ``SCHEMA_VERSION`` bump, so an old build — which refuses to open a project
    stamped newer than itself — can still open this DB after the upgrade. Here:
    a project at the current version but missing the column must gain it on open
    and keep every row.
    """
    import sqlite3

    from seestack.io.project import Project

    proj = Project.create(tmp_path / "t", name="T")
    try:
        proj.add_stack_run(_row(output_basename="old", uncovered_frac=0.5))
    finally:
        proj.close()

    db = tmp_path / "t" / "project.sqlite"
    conn = sqlite3.connect(db)
    try:
        conn.execute("ALTER TABLE stack_runs DROP COLUMN uncovered_frac")
        conn.commit()
        version_before = conn.execute("PRAGMA user_version").fetchone()[0]
    finally:
        conn.close()

    proj = Project.open(tmp_path / "t")
    try:
        runs = list(proj.iter_stack_runs())
        assert [r.output_basename for r in runs] == ["old"]
        assert runs[0].uncovered_frac is None      # unknown, so every note hides
        # …and the reconciled DB records it on the next stack.
        proj.add_stack_run(_row(output_basename="new", uncovered_frac=0.31))
        fresh = {r.output_basename: r for r in proj.iter_stack_runs()}
        assert fresh["new"].uncovered_frac == pytest.approx(0.31)
        assert fresh["old"].uncovered_frac is None
    finally:
        proj.close()

    # The version is untouched, which is what keeps a rollback openable.
    conn = sqlite3.connect(db)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == version_before
    finally:
        conn.close()


def test_an_old_build_can_still_read_a_project_this_build_wrote(tmp_path):
    """The other direction of "additive": a build that has never heard of the
    column must still open the DB and read its runs — the check that a bumped
    ``SCHEMA_VERSION`` would have failed."""
    import sqlite3

    from seestack.io.project import Project

    proj = Project.create(tmp_path / "t", name="T")
    try:
        proj.add_stack_run(_row(output_basename="new", uncovered_frac=0.4))
    finally:
        proj.close()

    # Stand in for the old build: read the row through SQL that names only the
    # columns that build knows about.
    conn = sqlite3.connect(tmp_path / "t" / "project.sqlite")
    conn.row_factory = sqlite3.Row
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] <= 22
        row = conn.execute(
            "SELECT output_basename, coverage_thin_frac FROM stack_runs"
        ).fetchone()
        assert row["output_basename"] == "new"
    finally:
        conn.close()


def test_a_real_mosaic_stack_records_its_empty_share(tmp_path):
    """End-to-end wiring, on the geometry that motivates the whole measure: two
    pointings offset diagonally leave the union canvas' opposite corners outside
    every footprint, and the run says so."""
    pytest.importorskip("astropy")
    pytest.importorskip("photutils")
    pytest.importorskip("scipy")

    from seestack.io.project import FrameRow, Project
    from seestack.stack.stacker import StackOptions, run_stack
    from tests.synth import make_synth_wcs_text, write_seestar_fits

    proj = Project.create(tmp_path / "proj", name="Mosaic")
    for ra, dec, tag in ((83.60, -5.40, "a"), (83.95, -5.10, "b")):
        wcs_text = make_synth_wcs_text(ra_center_deg=ra, dec_center_deg=dec)
        fp = write_seestar_fits(tmp_path / f"{tag}.fit", add_wcs=True, n_stars=25,
                                seed=20, ra_center_deg=ra, dec_center_deg=dec)
        proj.add_frame(FrameRow(
            id=None, source_path=str(fp), cached_path=str(fp),
            wcs_json=wcs_text, width_px=480, height_px=320,
            bayer_pattern="RGGB", accept=True,
            ra_center_deg=ra, dec_center_deg=dec,
        ))
    try:
        run_stack(proj, StackOptions(sigma_clip=False, background_flatten=False,
                                     mosaic_canvas="union", max_workers=2,
                                     output_name="mos"))
        run = next(iter(proj.iter_stack_runs()))
    finally:
        proj.close()

    assert run.uncovered_frac is not None
    # A genuinely ragged canvas: the two frames between them leave a large share
    # of the bounding box untouched, and the thin-coverage measure cannot see it.
    assert run.uncovered_frac > 0.2
    assert (run.coverage_thin_frac or 0.0) < run.uncovered_frac
