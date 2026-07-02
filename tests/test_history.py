"""Stack-history persistence + v1→v2 schema migration."""

import json

from seestack.io.project import Project, StackRunRow


def test_record_and_iter_stack_runs(tmp_path):
    proj = Project.create(tmp_path / "p", name="t")
    try:
        ids = []
        for i in range(3):
            ids.append(proj.add_stack_run(StackRunRow(
                id=None,
                timestamp_utc=f"2026-05-{10 + i:02d}T01:00:00+00:00",
                output_basename=f"run{i}",
                fits_path=f"out/{i}.fits", tiff_path=f"out/{i}.tif",
                preview_path=f"out/{i}.png",
                n_frames_used=100 + i, canvas_h=320, canvas_w=480,
                coverage_min=1, coverage_max=100 + i,
                options_json='{"sigma_kappa": 3.0}',
                notes=f"run {i}",
            )))
        rows = list(proj.iter_stack_runs())
        # Order should be timestamp DESC.
        assert [r.output_basename for r in rows] == ["run2", "run1", "run0"]
        # Deletion.
        proj.delete_stack_run(ids[0])
        rows = list(proj.iter_stack_runs())
        assert "run0" not in [r.output_basename for r in rows]
    finally:
        proj.close()


def test_total_exposure_s_round_trips(tmp_path):
    proj = Project.create(tmp_path / "p", name="t")
    try:
        proj.add_stack_run(StackRunRow(
            id=None, timestamp_utc="2026-05-10T01:00:00+00:00",
            output_basename="withexp", fits_path=None, tiff_path=None,
            preview_path=None, n_frames_used=100, canvas_h=320, canvas_w=480,
            coverage_min=1, coverage_max=100, options_json="{}",
            total_exposure_s=3000.0,
        ))
        # A run recorded without an exposure (e.g. no header exposures) stays None.
        proj.add_stack_run(StackRunRow(
            id=None, timestamp_utc="2026-05-09T01:00:00+00:00",
            output_basename="noexp", fits_path=None, tiff_path=None,
            preview_path=None, n_frames_used=5, canvas_h=10, canvas_w=10,
            coverage_min=0, coverage_max=5, options_json="{}",
        ))
        rows = {r.output_basename: r for r in proj.iter_stack_runs()}
        assert rows["withexp"].total_exposure_s == 3000.0
        assert rows["noexp"].total_exposure_s is None
    finally:
        proj.close()


def test_v3_schema_migrates_to_v4_adds_total_exposure(tmp_path):
    """A v3 stack_runs table (no total_exposure_s) must migrate additively: old
    rows read as None, new inserts carry the column, and no data is lost."""
    import sqlite3

    db_path = tmp_path / "old.sqlite"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        PRAGMA user_version = 3;
        CREATE TABLE project_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE frames (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_path TEXT NOT NULL UNIQUE,
            accept INTEGER NOT NULL DEFAULT 1,
            ra_hint_deg REAL, dec_hint_deg REAL
        );
        CREATE TABLE stack_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp_utc TEXT NOT NULL, output_basename TEXT NOT NULL,
            fits_path TEXT, tiff_path TEXT, preview_path TEXT,
            n_frames_used INTEGER NOT NULL, canvas_h INTEGER NOT NULL,
            canvas_w INTEGER NOT NULL, coverage_min INTEGER NOT NULL DEFAULT 0,
            coverage_max INTEGER NOT NULL DEFAULT 0, options_json TEXT NOT NULL,
            notes TEXT
        );
        INSERT INTO project_meta(key, value) VALUES('name', 'OldProject');
        INSERT INTO stack_runs(timestamp_utc, output_basename, n_frames_used,
            canvas_h, canvas_w, options_json)
            VALUES('2026-01-01T00:00:00+00:00', 'old_run', 42, 320, 480, '{}');
        """
    )
    conn.commit()
    conn.close()

    proj = Project(tmp_path)
    proj.db_path = db_path
    proj._open()
    proj._check_schema()
    try:
        from seestack.io.project import SCHEMA_VERSION
        assert proj._conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        cols = {r[1] for r in proj._conn.execute("PRAGMA table_info(stack_runs)")}
        assert "total_exposure_s" in cols
        # The pre-existing run survives and reads its new column as None.
        rows = {r.output_basename: r for r in proj.iter_stack_runs()}
        assert rows["old_run"].n_frames_used == 42
        assert rows["old_run"].total_exposure_s is None
        # New inserts carry the integration time.
        proj.add_stack_run(StackRunRow(
            id=None, timestamp_utc="2026-02-01T00:00:00+00:00",
            output_basename="new_run", fits_path=None, tiff_path=None,
            preview_path=None, n_frames_used=10, canvas_h=10, canvas_w=10,
            coverage_min=0, coverage_max=10, options_json="{}",
            total_exposure_s=1200.0,
        ))
        rows = {r.output_basename: r for r in proj.iter_stack_runs()}
        assert rows["new_run"].total_exposure_s == 1200.0
    finally:
        proj.close()


def test_v1_schema_migrates_to_v2(tmp_path):
    """Open a project created with the v1 schema and verify stack_runs appears."""
    import sqlite3

    db_path = tmp_path / "old.sqlite"
    # Build a minimal v1 schema by hand: project_meta + frames + user_version=1.
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        PRAGMA user_version = 1;
        CREATE TABLE project_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE frames (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_path TEXT NOT NULL UNIQUE,
            accept INTEGER NOT NULL DEFAULT 1
        );
        INSERT INTO project_meta(key, value) VALUES('name', 'OldProject');
        """
    )
    conn.commit()
    conn.close()
    # Open via the public API — migration runs.
    proj = Project(tmp_path)
    proj.db_path = db_path
    proj._open()
    proj._check_schema()
    try:
        # stack_runs table should now exist and accept inserts.
        proj.add_stack_run(StackRunRow(
            id=None, timestamp_utc="2026-05-12T00:00:00+00:00",
            output_basename="migrated",
            fits_path=None, tiff_path=None, preview_path=None,
            n_frames_used=5, canvas_h=10, canvas_w=10,
            coverage_min=0, coverage_max=5,
            options_json="{}",
        ))
        assert len(list(proj.iter_stack_runs())) == 1
        # Version stamp updated to the current schema.
        from seestack.io.project import SCHEMA_VERSION
        version = proj._conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == SCHEMA_VERSION
        # v3 hint columns exist after migration.
        cols = {r[1] for r in proj._conn.execute("PRAGMA table_info(frames)")}
        assert {"ra_hint_deg", "dec_hint_deg"} <= cols
    finally:
        proj.close()
