"""Who placed a sub on the sky — provenance for a WCS the app *derived*.

The 2026-09-30 audit's C-F6: the bootstrap rescue (``seestack/solve/bootstrap.py``)
writes a WCS into ``frames.wcs_json`` for subs no plate solve located, composed
from a neighbour's stars (a star match) or slid from the reference by a shift —
and nothing recorded that those rows were derived rather than measured. A wrong
star lock therefore read back, forever, as a solve, with no way to find which
subs it had placed.

``frames.wcs_source`` is that record: ``star_match`` / ``registered`` for the two
ways the rescue places a sub, NULL for the solver and for every row written
before the column existed. It is reset by any later write of ``wcs_json`` that
does not say otherwise, centrally, so a real solve can never keep a stale
provenance. Added without a ``SCHEMA_VERSION`` bump (§9's rollback rule, the
same as ``rejected_utc``); the migration from an old DB is pinned here.
"""

from __future__ import annotations

import sqlite3

import pytest

from seestack.io.project import (
    SCHEMA_VERSION,
    WCS_SOURCE_REGISTERED,
    WCS_SOURCE_STAR_MATCH,
    FrameRow,
    Project,
)

# The ``frames`` DDL exactly as schema 22 wrote it before this column existed —
# frozen, so a missing ``ALTER`` step cannot be hidden by a fixture that follows
# the schema (the same reasoning as ``tests/test_project_schema_drift.py``).
_V22_FRAMES_SQL = """
CREATE TABLE frames (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    source_path          TEXT NOT NULL UNIQUE,
    cached_path          TEXT,
    aligned_cache_path   TEXT,
    source_size_bytes    INTEGER,
    source_mtime         REAL,
    timestamp_utc        TEXT,
    exposure_s           REAL,
    gain                 REAL,
    sensor_temp_c        REAL,
    width_px             INTEGER,
    height_px            INTEGER,
    bayer_pattern        TEXT,
    ra_hint_deg          REAL,
    dec_hint_deg         REAL,
    wcs_json             TEXT,
    ra_center_deg        REAL,
    dec_center_deg       REAL,
    pixscale_arcsec      REAL,
    rotation_deg         REAL,
    fwhm_px              REAL,
    star_count           INTEGER,
    sky_adu_median       REAL,
    eccentricity_median  REAL,
    transparency_score   REAL,
    streak_detected      INTEGER NOT NULL DEFAULT 0,
    streak_count         INTEGER NOT NULL DEFAULT 0,
    mosaic_panel_id      INTEGER,
    accept               INTEGER NOT NULL DEFAULT 1,
    reject_reason        TEXT,
    user_override        INTEGER NOT NULL DEFAULT 0,
    streak_cx            REAL,
    streak_cy            REAL,
    restored_utc         TEXT,
    rejected_utc         TEXT
);
CREATE TABLE project_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE stack_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp_utc TEXT NOT NULL,
    output_basename TEXT NOT NULL, fits_path TEXT, tiff_path TEXT, preview_path TEXT,
    n_frames_used INTEGER NOT NULL, canvas_h INTEGER NOT NULL, canvas_w INTEGER NOT NULL,
    coverage_min INTEGER NOT NULL DEFAULT 0, coverage_max INTEGER NOT NULL DEFAULT 0,
    options_json TEXT NOT NULL, notes TEXT
);
"""


def test_an_old_project_gains_the_column_null_and_keeps_its_rows(tmp_path, monkeypatch):
    """The migration alone — the runtime column backfill is switched off, as the
    schema-drift file does, so only the ungated ``ALTER`` can satisfy this. A
    legacy solved row reads back with ``wcs_source`` NULL: "the solver, or
    before we recorded this", which is the truth about it."""
    monkeypatch.setattr(Project, "_reconcile_table_columns", lambda self: None)
    project_dir = tmp_path / "v22"
    project_dir.mkdir()
    conn = sqlite3.connect(project_dir / "project.sqlite")
    try:
        conn.executescript(_V22_FRAMES_SQL)
        conn.execute(
            "INSERT INTO frames(source_path, wcs_json, ra_center_deg, accept) "
            "VALUES(?, ?, ?, ?)", ("sub_001.fit", "SIMPLE = T", 83.6, 1))
        conn.execute("PRAGMA user_version = 21")   # older than current: migrates
        conn.commit()
    finally:
        conn.close()

    proj = Project.open(project_dir)
    try:
        (f,) = list(proj.iter_frames())
        assert f.source_path == "sub_001.fit"
        assert f.wcs_json == "SIMPLE = T" and f.ra_center_deg == 83.6
        assert f.wcs_source is None
        assert proj._conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    finally:
        proj.close()


def test_a_current_project_written_without_the_column_self_heals_on_open(tmp_path):
    """The other route: a DB already stamped current (so ``_migrate_schema``
    never runs) gains it from ``_reconcile_table_columns``."""
    project_dir = tmp_path / "cur"
    proj = Project.create(project_dir, name="cur")
    try:
        proj.add_frame(FrameRow(source_path="a.fit", wcs_json="x"))
    finally:
        proj.close()
    conn = sqlite3.connect(project_dir / "project.sqlite")
    try:
        conn.execute("ALTER TABLE frames DROP COLUMN wcs_source")
        conn.commit()
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    finally:
        conn.close()
    proj = Project.open(project_dir)
    try:
        (f,) = list(proj.iter_frames())
        assert f.wcs_json == "x" and f.wcs_source is None
    finally:
        proj.close()


def test_the_column_needs_no_version_bump():
    assert SCHEMA_VERSION == 22, (
        "wcs_source is additive and read one-sidedly; bumping SCHEMA_VERSION for "
        "it would stop an older build opening every project this one touched")


def test_a_new_wcs_resets_the_provenance_unless_the_writer_names_it(tmp_path):
    """Central, in ``update_frame``: the solver never names a source, so its
    write clears whatever the rescue had stamped; the rescue names its source
    and keeps it; a solution reset clears both."""
    proj = Project.create(tmp_path / "t", name="T")
    try:
        fid = proj.add_frame(FrameRow(source_path="a.fit"))
        assert proj.get_frame(fid).wcs_source is None

        proj.update_frame(fid, wcs_json="derived", wcs_source=WCS_SOURCE_STAR_MATCH)
        assert proj.get_frame(fid).wcs_source == WCS_SOURCE_STAR_MATCH
        # An unrelated write leaves it alone.
        proj.update_frame(fid, fwhm_px=2.5)
        assert proj.get_frame(fid).wcs_source == WCS_SOURCE_STAR_MATCH

        # A real solve of the sub's own pixels writes wcs_json and says nothing
        # about a source: the derived provenance must not survive it.
        proj.update_frame(fid, wcs_json="measured", ra_center_deg=1.0)
        f = proj.get_frame(fid)
        assert f.wcs_json == "measured" and f.wcs_source is None

        proj.update_frame(fid, wcs_json="derived", wcs_source=WCS_SOURCE_REGISTERED)
        proj.reset_frame_solution(fid)
        f = proj.get_frame(fid)
        assert f.wcs_json is None and f.wcs_source is None
    finally:
        proj.close()


def test_the_bootstrap_rescue_stamps_which_way_it_placed_each_sub(tmp_path):
    """End to end through ``bootstrap_solve`` on the same synthetic night the
    bootstrap's own tests use: every rescued sub carries a source, every sub the
    rescue did not touch carries none. With no rotation and identical fields
    the star match places them, so the record says so; the shift fallback is
    covered by ``propagate_wcs``'s own ``star_placed`` contract."""
    pytest.importorskip("astropy")
    pytest.importorskip("skimage")
    from seestack.solve.bootstrap import bootstrap_solve
    from tests.test_bootstrap_solve import (
        _make_project_with_faint_subs,
        _ref_wcs_solver,
    )

    proj, _truth = _make_project_with_faint_subs(tmp_path, n=8)
    try:
        res = bootstrap_solve(proj, min_frames=4, deep_solver=_ref_wcs_solver)
        assert res.engaged and res.deep_solved and res.n_propagated >= 6
        placed = {f.id: f for f in proj.iter_frames() if f.id in res.propagated_frame_ids}
        assert len(placed) == res.n_propagated
        sources = {f.wcs_source for f in placed.values()}
        assert sources <= {WCS_SOURCE_STAR_MATCH, WCS_SOURCE_REGISTERED}
        assert None not in sources
        # …and the count the result reports is the count the rows say.
        assert sum(1 for f in placed.values()
                   if f.wcs_source == WCS_SOURCE_STAR_MATCH) == res.n_star_matched
        untouched = [f for f in proj.iter_frames() if f.id not in placed]
        assert all(f.wcs_source is None for f in untouched)
    finally:
        proj.close()
