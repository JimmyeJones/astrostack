"""Schema-completeness drift guards for the per-target project DB.

These tests exist because of the v0.119.8 live-install brick: a ``frames``
column was added that every reader (`_row_to_frame`) referenced, but it reached
the base ``SCHEMA_SQL`` with no matching ``ALTER`` migration — so an older
project that a later build had already stamped at the current ``user_version``
was *missing* that column, and the first ``row["<col>"]`` read raised on open,
bricking the target until the runtime ``_reconcile_table_columns`` backfill was
added (see AGENTS.md §9).

The runtime reconcile now repairs any such drift, but that is a safety net. A
*cheap* commit-time guard documents the invariant and turns "did someone forget
the migration?" from a latent live-install brick into a red test:

  (a) every column a reader/writer references (the ``FrameRow`` / ``StackRunRow``
      read contracts + ``_INSERT_COLS``) exists in the authoritative schema — so
      the additive backfill (which derives its expected columns from the same
      schema) knows to restore it on any older DB; and
  (b) a project created at an *old* ``user_version`` with a pre-QC-columns
      ``frames`` table (and no ``stack_runs`` table) opens and round-trips a
      frame **and** a stack-run read/write without raising.

Pure test infrastructure — no product code changes.
"""

from __future__ import annotations

import dataclasses
import sqlite3

from seestack.io.project import (
    _EXPECTED_COLUMNS,
    _INSERT_COLS,
    FrameRow,
    Project,
    SCHEMA_SQL,
    StackRunRow,
)


def _schema_columns(table: str) -> set[str]:
    """The column names of ``table`` as the authoritative SCHEMA_SQL defines it,
    read from a throwaway in-memory build (the same source the runtime column
    reconcile trusts)."""
    conn = sqlite3.connect(":memory:")
    try:
        conn.executescript(SCHEMA_SQL)
        return {
            r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
    finally:
        conn.close()


# --- (a) reader/writer columns are all present in the base schema -------------


def test_frame_reader_columns_all_exist_in_schema():
    """Every ``frames`` column ``FrameRow`` (i.e. ``_row_to_frame``) reads and
    ``_INSERT_COLS`` writes must exist in ``SCHEMA_SQL``. If a field were added
    to the read contract without the column reaching the schema, the runtime
    reconcile (which derives its expected columns from the schema) wouldn't know
    to restore it and the read would raise on an older DB — the v0.119.8 bug."""
    schema_cols = _schema_columns("frames")
    reader_cols = {f.name for f in dataclasses.fields(FrameRow)}
    missing = reader_cols - schema_cols
    assert not missing, f"FrameRow reads columns absent from SCHEMA_SQL: {sorted(missing)}"
    missing_insert = set(_INSERT_COLS) - schema_cols
    assert not missing_insert, (
        f"_INSERT_COLS writes columns absent from SCHEMA_SQL: {sorted(missing_insert)}")


def test_stack_run_reader_columns_all_exist_in_schema():
    """Every ``stack_runs`` column ``StackRunRow`` (the ``iter_stack_runs`` read
    contract + ``add_stack_run`` write) references must exist in ``SCHEMA_SQL``,
    for the same reason as the frames guard above."""
    schema_cols = _schema_columns("stack_runs")
    reader_cols = {f.name for f in dataclasses.fields(StackRunRow)}
    missing = reader_cols - schema_cols
    assert not missing, (
        f"StackRunRow reads columns absent from SCHEMA_SQL: {sorted(missing)}")


def test_reconcile_expected_columns_cover_every_reader_column():
    """The runtime backfill (``_reconcile_table_columns``) restores exactly the
    columns in ``_EXPECTED_COLUMNS``. Assert that set covers every column the
    readers need, so an older DB missing any of them is self-healed on open
    rather than left to raise — this is the guard that ties the read contracts
    to the machinery that repairs drift."""
    expected_frames = {c[0] for c in _EXPECTED_COLUMNS["frames"]}
    expected_runs = {c[0] for c in _EXPECTED_COLUMNS["stack_runs"]}
    assert {f.name for f in dataclasses.fields(FrameRow)} <= expected_frames
    assert set(_INSERT_COLS) <= expected_frames
    assert {f.name for f in dataclasses.fields(StackRunRow)} <= expected_runs


# --- (b) an old, pre-QC-columns project opens and round-trips -----------------


# A faithful *early* ``frames`` table: it predates the plate-solve hint columns
# (schema < 3), the QC metric columns, and the streak columns — exactly the kind
# of pre-QC on-disk shape a long-lived install still carries. ``id`` +
# ``source_path`` + the tone/geometry/accept columns only.
_OLD_FRAMES_SQL = """
CREATE TABLE frames (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    source_path         TEXT NOT NULL UNIQUE,
    cached_path         TEXT,
    aligned_cache_path  TEXT,
    timestamp_utc       TEXT,
    exposure_s          REAL,
    gain                REAL,
    sensor_temp_c       REAL,
    width_px            INTEGER,
    height_px           INTEGER,
    bayer_pattern       TEXT,
    wcs_json            TEXT,
    ra_center_deg       REAL,
    dec_center_deg      REAL,
    pixscale_arcsec     REAL,
    rotation_deg        REAL,
    mosaic_panel_id     INTEGER,
    accept              INTEGER NOT NULL DEFAULT 1,
    reject_reason       TEXT,
    user_override       INTEGER NOT NULL DEFAULT 0
);
"""


def _write_old_project(project_dir):
    """Hand-build a project.sqlite at an *old* schema (user_version 1): a
    pre-QC-columns ``frames`` table with one row, and **no** ``stack_runs``
    table (v1 predates it) — so opening must both migrate (create stack_runs +
    add the version columns) and reconcile (backfill the missing frames
    columns)."""
    project_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(project_dir / "project.sqlite")
    try:
        conn.executescript(_OLD_FRAMES_SQL)
        conn.execute(
            "INSERT INTO frames(source_path, exposure_s, gain, width_px, height_px, "
            "bayer_pattern, accept) VALUES(?, ?, ?, ?, ?, ?, ?)",
            ("old_frame_001.fit", 10.0, 80.0, 1920, 1080, "RGGB", 1),
        )
        conn.execute("PRAGMA user_version = 1")
        conn.commit()
    finally:
        conn.close()


def test_old_pre_qc_project_opens_and_round_trips(tmp_path):
    project_dir = tmp_path / "legacy"
    _write_old_project(project_dir)

    proj = Project.open(project_dir)
    try:
        # The pre-existing (pre-QC) frame reads back — every column the reader
        # references now exists (reconcile backfilled the missing ones), with
        # sane defaults for the columns this old row never had.
        frames = list(proj.iter_frames())
        assert len(frames) == 1
        f = frames[0]
        assert f.source_path == "old_frame_001.fit"
        assert f.exposure_s == 10.0
        assert f.bayer_pattern == "RGGB"
        assert f.accept is True
        # Backfilled columns default cleanly rather than raising on read.
        assert f.fwhm_px is None
        assert f.streak_detected is False
        assert f.streak_count == 0
        assert f.ra_hint_deg is None

        # A stack-run write + read round-trips too: the stack_runs table was
        # created and reconciled to the current shape, so add/iter don't raise.
        run_id = proj.add_stack_run(StackRunRow(
            id=None, timestamp_utc="2020-01-01T00:00:00Z", output_basename="master",
            fits_path=None, tiff_path=None, preview_path=None, n_frames_used=1,
            canvas_h=8, canvas_w=8, coverage_min=0, coverage_max=1, options_json="{}",
        ))
        assert run_id is not None
        runs = list(proj.iter_stack_runs())
        assert len(runs) == 1
        assert runs[0].output_basename == "master"
        # A column that only exists post-migration reads back as its default.
        assert runs[0].engine_version is None

        # The migration + reconcile leaves the DB stamped current.
        from seestack.io.project import SCHEMA_VERSION
        version = proj._conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == SCHEMA_VERSION
    finally:
        proj.close()


# --- (c) the two newest migration steps, each standing on its own -------------

# A **frozen snapshot** of the ``frames`` and ``stack_runs`` DDL as schema 20 had
# it: today's shape minus ``streak_cx``/``streak_cy`` (added at v21) and
# ``restored_utc`` (added at v22). The v21 fixture below is this plus the two
# streak columns.
#
# Frozen, rather than ``SCHEMA_SQL`` with the new columns dropped back off, and
# that is the whole point of the rewrite (fourth external audit, 2026-09-10).
# Deriving the old shape from the current schema makes the fixture track it: the
# next column added to either table arrives in the fixture too, so a missing
# ``ALTER`` step cannot make any test here go red. A literal cannot follow the
# schema, so ``_assert_tables_are_fully_migrated`` fails the moment a new column
# exists in ``SCHEMA_SQL`` with no migration step to put it on an old DB — which
# is exactly the v0.119.8 live-install brick this file was written for.
#
# So: when you add a column, add its ALTER step, and leave these literals alone.
_V20_FRAMES_SQL = """
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
    user_override        INTEGER NOT NULL DEFAULT 0
);
"""

# v21 = v20 + the streak-position columns, in the position the ALTER leaves them
# (appended, which is where ``ALTER TABLE ADD COLUMN`` puts them — column *order*
# is not part of the contract, only the set).
_V21_FRAMES_SQL = _V20_FRAMES_SQL.replace(
    "    user_override        INTEGER NOT NULL DEFAULT 0\n",
    "    user_override        INTEGER NOT NULL DEFAULT 0,\n"
    "    streak_cx            REAL,\n"
    "    streak_cy            REAL\n",
)

_V20_STACK_RUNS_SQL = """
CREATE TABLE stack_runs (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp_utc           TEXT NOT NULL,
    output_basename         TEXT NOT NULL,
    fits_path               TEXT,
    tiff_path               TEXT,
    preview_path            TEXT,
    n_frames_used           INTEGER NOT NULL,
    canvas_h                INTEGER NOT NULL,
    canvas_w                INTEGER NOT NULL,
    coverage_min            INTEGER NOT NULL DEFAULT 0,
    coverage_max            INTEGER NOT NULL DEFAULT 0,
    options_json            TEXT NOT NULL,
    notes                   TEXT,
    total_exposure_s        REAL,
    transparency_ratio      REAL,
    noise_sigma             REAL,
    calstat                 TEXT,
    is_mosaic               INTEGER,
    engine_version          TEXT,
    rejection_fraction      REAL,
    rejection_mode          TEXT,
    preview_stretch         REAL,
    preview_black           REAL,
    n_roughly_aligned       INTEGER,
    stack_fwhm_px           REAL,
    seam_residual           REAL,
    preview_north_up_deg    REAL,
    preview_crop_json       TEXT,
    capture_start_utc       TEXT,
    capture_end_utc         TEXT,
    capture_hours_json      TEXT,
    coverage_thin_frac      REAL,
    uncovered_frac          REAL,
    coverage_shares_version INTEGER,
    coverage_median_depth   REAL,
    duration_s              REAL,
    grain_ratio             REAL,
    grain_thin_frames       INTEGER,
    grain_deep_frames       INTEGER,
    grain_thin_share        REAL
);
"""

_PROJECT_META_SQL = (
    "CREATE TABLE project_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);\n"
)


def _write_frozen_project(project_dir, *, user_version: int, frames_sql: str) -> None:
    """Build a project DB at *user_version* from frozen DDL, with one real frame."""
    project_dir.mkdir(parents=True)
    conn = sqlite3.connect(project_dir / "project.sqlite")
    try:
        conn.executescript(_PROJECT_META_SQL + _V20_STACK_RUNS_SQL + frames_sql)
        conn.execute(
            "INSERT INTO frames(source_path, exposure_s, star_count, "
            "streak_detected, accept, reject_reason) VALUES(?,?,?,?,?,?)",
            ("sub_001.fit", 10.0, 90, 1, 0, "auto:streak"),
        )
        conn.execute(f"PRAGMA user_version = {user_version}")
        conn.commit()
    finally:
        conn.close()


def _assert_tables_are_fully_migrated(proj) -> None:
    """Every authoritative column exists on the opened DB.

    With the runtime backfill switched off this is a statement about
    ``_migrate_schema`` alone: a column in ``SCHEMA_SQL`` whose ``ALTER`` step was
    never written cannot be here, because the fixture's DDL is frozen and cannot
    have grown it either.
    """
    for table, expected in _EXPECTED_COLUMNS.items():
        present = {
            r[1] for r in proj._conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
        missing = {c[0] for c in expected} - present
        assert not missing, (
            f"{table} is missing {sorted(missing)} after _migrate_schema alone — "
            "a column reached SCHEMA_SQL with no matching ALTER migration step "
            "(the v0.119.8 live-install brick). Add the step; do not widen the "
            "frozen fixture DDL above."
        )


def _disable_the_runtime_backfill(monkeypatch):
    """Make ``Project.open`` rely on ``_migrate_schema`` alone.

    **Why these two tests need this** (filed by the fourth external audit,
    2026-09-10, and reproduced before fixing): a purely additive nullable-column
    migration and the runtime ``_reconcile_table_columns`` net produce the *same*
    observable schema, and the net derives its column list from the same
    ``SCHEMA_SQL`` the migration does. So a test that opens a project and checks
    the columns arrived cannot tell which one did the work — both of these passed
    with their ``if from_version < 21`` / ``< 22`` blocks **deleted outright**,
    which is precisely the v0.119.8 mistake this file exists to catch.

    Switching the net off for the duration makes the migration step the only thing
    that can satisfy the assertions. The net keeps its own direct coverage in
    ``test_the_backfill_covers_every_column_a_reader_needs`` above and in the
    pre-QC-shape round-trip below, so nothing is left unguarded.
    """
    monkeypatch.setattr(Project, "_reconcile_table_columns", lambda self: None)


def test_a_schema_20_project_gains_the_streak_positions_without_losing_rows(
    tmp_path, monkeypatch
):
    """The v20 → v21 step, from the shape a live install actually has: a
    current-at-the-time project with real frames, opened by a build that wants
    the streak-position columns. They must arrive as NULL (= "no evidence", so
    the reconciliation stays quiet on this data) with every row and every
    existing value untouched — §9's "databases migrate, never reset".

    Run with the runtime backfill disabled, so this is a test of the *migration*
    — see :func:`_disable_the_runtime_backfill`."""
    _disable_the_runtime_backfill(monkeypatch)
    project_dir = tmp_path / "v20"
    _write_frozen_project(project_dir, user_version=20, frames_sql=_V20_FRAMES_SQL)

    proj = Project.open(project_dir)
    try:
        _assert_tables_are_fully_migrated(proj)
        frames = list(proj.iter_frames())
        assert len(frames) == 1
        f = frames[0]
        assert f.source_path == "sub_001.fit"
        assert f.exposure_s == 10.0
        assert f.star_count == 90
        assert f.streak_detected is True
        assert f.accept is False
        assert f.reject_reason == "auto:streak"
        assert f.streak_cx is None and f.streak_cy is None
    finally:
        proj.close()


def test_a_schema_21_project_gains_the_restoration_stamp_without_losing_rows(
    tmp_path, monkeypatch
):
    """The v21 → v22 step. ``frames.restored_utc`` must arrive as NULL on every
    existing row — which reads as "this sub was never put back", so the Target
    page's restored-subs nudge stays silent on a pre-upgrade install rather than
    inventing a restoration out of a legacy row — with nothing else disturbed.

    Run with the runtime backfill disabled, so this is a test of the *migration*
    — see :func:`_disable_the_runtime_backfill`."""
    _disable_the_runtime_backfill(monkeypatch)
    project_dir = tmp_path / "v21"
    _write_frozen_project(project_dir, user_version=21, frames_sql=_V21_FRAMES_SQL)
    # This step's claim is about an *existing* value surviving, so give the row the
    # streak position v21 could record. (The accept/reject flip keeps the rest of
    # the assertions below reading the same row shape they always did.)
    conn = sqlite3.connect(project_dir / "project.sqlite")
    try:
        conn.execute(
            "UPDATE frames SET streak_cx = 0.5, accept = 1, reject_reason = NULL")
        conn.commit()
    finally:
        conn.close()

    proj = Project.open(project_dir)
    try:
        _assert_tables_are_fully_migrated(proj)
        frames = list(proj.iter_frames())
        assert len(frames) == 1
        f = frames[0]
        assert f.source_path == "sub_001.fit"
        assert f.exposure_s == 10.0
        assert f.star_count == 90
        assert f.streak_detected is True
        assert f.streak_cx == 0.5
        assert f.accept is True
        assert f.restored_utc is None
        # And the read side agrees: nothing to say about a legacy row.
        assert proj.restored_frame_stamps() == []

        from seestack.io.project import SCHEMA_VERSION
        assert proj._conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    finally:
        proj.close()
