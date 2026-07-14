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
