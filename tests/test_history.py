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


def test_v7_schema_migrates_to_v8_adds_is_mosaic(tmp_path):
    """A v7 stack_runs table (no is_mosaic) must migrate additively: old rows read
    as None (unknown → editor falls back to the coverage distribution), and new
    inserts persist the stacker's authoritative mosaic verdict."""
    import sqlite3

    db_path = tmp_path / "old.sqlite"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        PRAGMA user_version = 7;
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
            notes TEXT, total_exposure_s REAL, transparency_ratio REAL,
            noise_sigma REAL, calstat TEXT
        );
        INSERT INTO project_meta(key, value) VALUES('name', 'OldProject');
        INSERT INTO stack_runs(timestamp_utc, output_basename, n_frames_used,
            canvas_h, canvas_w, coverage_min, coverage_max, options_json)
            VALUES('2026-01-01T00:00:00+00:00', 'old_run', 42, 320, 480, 0, 6, '{}');
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
        assert "is_mosaic" in cols
        # The pre-existing run survives and reads its new column as None (unknown).
        rows = {r.output_basename: r for r in proj.iter_stack_runs()}
        assert rows["old_run"].n_frames_used == 42
        assert rows["old_run"].is_mosaic is None
        # New inserts persist the authoritative mosaic verdict (as 0/1, read as bool).
        proj.add_stack_run(StackRunRow(
            id=None, timestamp_utc="2026-02-01T00:00:00+00:00",
            output_basename="mosaic_run", fits_path=None, tiff_path=None,
            preview_path=None, n_frames_used=10, canvas_h=10, canvas_w=10,
            coverage_min=0, coverage_max=10, options_json="{}", is_mosaic=True,
        ))
        proj.add_stack_run(StackRunRow(
            id=None, timestamp_utc="2026-02-02T00:00:00+00:00",
            output_basename="single_run", fits_path=None, tiff_path=None,
            preview_path=None, n_frames_used=10, canvas_h=10, canvas_w=10,
            coverage_min=0, coverage_max=10, options_json="{}", is_mosaic=False,
        ))
        rows = {r.output_basename: r for r in proj.iter_stack_runs()}
        assert rows["mosaic_run"].is_mosaic is True
        assert rows["single_run"].is_mosaic is False
    finally:
        proj.close()


def test_v8_schema_migrates_to_v9_adds_engine_version(tmp_path):
    """A v8 stack_runs table (no engine_version) must migrate additively: old rows
    read the new column as None (version unknown), and new inserts persist the
    producing app version for provenance."""
    import sqlite3

    db_path = tmp_path / "old.sqlite"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        PRAGMA user_version = 8;
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
            notes TEXT, total_exposure_s REAL, transparency_ratio REAL,
            noise_sigma REAL, calstat TEXT, is_mosaic INTEGER
        );
        INSERT INTO project_meta(key, value) VALUES('name', 'OldProject');
        INSERT INTO stack_runs(timestamp_utc, output_basename, n_frames_used,
            canvas_h, canvas_w, coverage_min, coverage_max, options_json)
            VALUES('2026-01-01T00:00:00+00:00', 'old_run', 42, 320, 480, 0, 6, '{}');
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
        assert "engine_version" in cols
        # The pre-existing run survives and reads its new column as None (unknown).
        rows = {r.output_basename: r for r in proj.iter_stack_runs()}
        assert rows["old_run"].n_frames_used == 42
        assert rows["old_run"].engine_version is None
        # New inserts persist the producing app version.
        proj.add_stack_run(StackRunRow(
            id=None, timestamp_utc="2026-02-01T00:00:00+00:00",
            output_basename="new_run", fits_path=None, tiff_path=None,
            preview_path=None, n_frames_used=10, canvas_h=10, canvas_w=10,
            coverage_min=0, coverage_max=10, options_json="{}",
            engine_version="0.75.0",
        ))
        rows = {r.output_basename: r for r in proj.iter_stack_runs()}
        assert rows["new_run"].engine_version == "0.75.0"
    finally:
        proj.close()


def test_v4_schema_migrates_to_v5_adds_transparency_ratio(tmp_path):
    """A v4 stack_runs table (no transparency_ratio) must migrate additively: old
    rows read as None, new inserts carry the column, and no data is lost."""
    import sqlite3

    db_path = tmp_path / "old.sqlite"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        PRAGMA user_version = 4;
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
            notes TEXT, total_exposure_s REAL
        );
        INSERT INTO project_meta(key, value) VALUES('name', 'OldProject');
        INSERT INTO stack_runs(timestamp_utc, output_basename, n_frames_used,
            canvas_h, canvas_w, options_json, total_exposure_s)
            VALUES('2026-01-01T00:00:00+00:00', 'old_run', 42, 320, 480, '{}', 900.0);
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
        assert "transparency_ratio" in cols
        # The pre-existing run survives and reads its new column as None.
        rows = {r.output_basename: r for r in proj.iter_stack_runs()}
        assert rows["old_run"].n_frames_used == 42
        assert rows["old_run"].total_exposure_s == 900.0
        assert rows["old_run"].transparency_ratio is None
        # New inserts carry the transparency verdict.
        proj.add_stack_run(StackRunRow(
            id=None, timestamp_utc="2026-02-01T00:00:00+00:00",
            output_basename="new_run", fits_path=None, tiff_path=None,
            preview_path=None, n_frames_used=10, canvas_h=10, canvas_w=10,
            coverage_min=0, coverage_max=10, options_json="{}",
            total_exposure_s=1200.0, transparency_ratio=0.45,
        ))
        rows = {r.output_basename: r for r in proj.iter_stack_runs()}
        assert rows["new_run"].transparency_ratio == 0.45
    finally:
        proj.close()


def test_v5_schema_migrates_to_v6_adds_noise_sigma(tmp_path):
    """A v5 stack_runs table (no noise_sigma) must migrate additively: old rows
    read as None, new inserts carry the column, and no data is lost."""
    import sqlite3

    db_path = tmp_path / "old.sqlite"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        PRAGMA user_version = 5;
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
            notes TEXT, total_exposure_s REAL, transparency_ratio REAL
        );
        INSERT INTO project_meta(key, value) VALUES('name', 'OldProject');
        INSERT INTO stack_runs(timestamp_utc, output_basename, n_frames_used,
            canvas_h, canvas_w, options_json, total_exposure_s, transparency_ratio)
            VALUES('2026-01-01T00:00:00+00:00', 'old_run', 42, 320, 480, '{}',
                   900.0, 0.7);
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
        assert "noise_sigma" in cols
        # The pre-existing run survives and reads its new column as None.
        rows = {r.output_basename: r for r in proj.iter_stack_runs()}
        assert rows["old_run"].n_frames_used == 42
        assert rows["old_run"].transparency_ratio == 0.7
        assert rows["old_run"].noise_sigma is None
        # New inserts carry the recorded noise σ.
        proj.add_stack_run(StackRunRow(
            id=None, timestamp_utc="2026-02-01T00:00:00+00:00",
            output_basename="new_run", fits_path=None, tiff_path=None,
            preview_path=None, n_frames_used=10, canvas_h=10, canvas_w=10,
            coverage_min=0, coverage_max=10, options_json="{}",
            total_exposure_s=1200.0, transparency_ratio=0.45, noise_sigma=0.018,
        ))
        rows = {r.output_basename: r for r in proj.iter_stack_runs()}
        assert rows["new_run"].noise_sigma == 0.018
    finally:
        proj.close()


def test_v6_schema_migrates_to_v7_adds_calstat(tmp_path):
    """A v6 stack_runs table (no calstat) must migrate additively: old rows read
    as None, new inserts carry the calibration string, and no data is lost."""
    import sqlite3

    db_path = tmp_path / "old.sqlite"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        PRAGMA user_version = 6;
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
            notes TEXT, total_exposure_s REAL, transparency_ratio REAL,
            noise_sigma REAL
        );
        INSERT INTO project_meta(key, value) VALUES('name', 'OldProject');
        INSERT INTO stack_runs(timestamp_utc, output_basename, n_frames_used,
            canvas_h, canvas_w, options_json, noise_sigma)
            VALUES('2026-01-01T00:00:00+00:00', 'old_run', 42, 320, 480, '{}',
                   0.02);
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
        assert "calstat" in cols
        # The pre-existing run survives and reads its new column as None.
        rows = {r.output_basename: r for r in proj.iter_stack_runs()}
        assert rows["old_run"].n_frames_used == 42
        assert rows["old_run"].noise_sigma == 0.02
        assert rows["old_run"].calstat is None
        # New inserts carry the recorded calibration string.
        proj.add_stack_run(StackRunRow(
            id=None, timestamp_utc="2026-02-01T00:00:00+00:00",
            output_basename="new_run", fits_path=None, tiff_path=None,
            preview_path=None, n_frames_used=10, canvas_h=10, canvas_w=10,
            coverage_min=0, coverage_max=10, options_json="{}",
            calstat="dark+flat",
        ))
        rows = {r.output_basename: r for r in proj.iter_stack_runs()}
        assert rows["new_run"].calstat == "dark+flat"
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


def _legacy_frames_db(db_path, *, user_version: int):
    """A project whose ``frames`` table predates the QC columns (no
    transparency_score / streak_* / eccentricity_median / user_override /
    aligned_cache_path / mosaic_panel_id) but carries a real frame row."""
    import sqlite3

    conn = sqlite3.connect(db_path)
    conn.executescript(
        f"""
        PRAGMA user_version = {user_version};
        CREATE TABLE project_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE frames (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_path TEXT NOT NULL UNIQUE,
            cached_path TEXT,
            timestamp_utc TEXT,
            exposure_s REAL, gain REAL, sensor_temp_c REAL,
            width_px INTEGER, height_px INTEGER, bayer_pattern TEXT,
            ra_hint_deg REAL, dec_hint_deg REAL,
            wcs_json TEXT, ra_center_deg REAL, dec_center_deg REAL,
            pixscale_arcsec REAL, rotation_deg REAL,
            fwhm_px REAL, star_count INTEGER, sky_adu_median REAL,
            accept INTEGER NOT NULL DEFAULT 1, reject_reason TEXT
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
        INSERT INTO frames(source_path, accept) VALUES('/data/f1.fit', 1);
        """
    )
    conn.commit()
    conn.close()


def test_legacy_frames_table_backfills_qc_columns_and_reads(tmp_path):
    """A project created before the QC frame columns existed must still be
    readable after an in-place upgrade. Regression: the migration only ALTERed
    frames for the v3 ra/dec hints, so a genuine pre-QC-columns frames table
    stamped current but never gained transparency_score / streak_* / etc. —
    then every `iter_frames()` raised `IndexError: No item with that key` and,
    because the version was already stamped, re-opening never repaired it."""
    from seestack.io.project import SCHEMA_VERSION

    db_path = tmp_path / "old.sqlite"
    _legacy_frames_db(db_path, user_version=3)

    proj = Project(tmp_path)
    proj.db_path = db_path
    proj._open()
    proj._check_schema()
    try:
        # The missing QC columns are backfilled additively.
        cols = {r[1] for r in proj._conn.execute("PRAGMA table_info(frames)")}
        assert {
            "aligned_cache_path", "eccentricity_median", "transparency_score",
            "streak_detected", "streak_count", "mosaic_panel_id", "user_override",
        } <= cols
        # The pre-existing frame row survives and now reads without raising, its
        # backfilled columns coming back as the schema defaults.
        frames = list(proj.iter_frames())
        assert len(frames) == 1
        f = frames[0]
        assert f.source_path == "/data/f1.fit"
        assert f.transparency_score is None
        assert f.eccentricity_median is None
        assert f.streak_detected is False   # NOT NULL DEFAULT 0
        assert f.streak_count == 0
        assert f.user_override is False
        assert proj._conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    finally:
        proj.close()


def test_current_version_but_missing_column_self_heals(tmp_path):
    """A DB a *previous* build already stamped at the current version but which
    is missing a later frames column must still self-heal on open — the column
    backfill runs even when `user_version == SCHEMA_VERSION`, so an
    already-bricked project recovers rather than staying unreadable forever."""
    from seestack.io.project import SCHEMA_VERSION

    db_path = tmp_path / "bricked.sqlite"
    # Stamp it at the current version despite the pre-QC-columns frames shape —
    # exactly what the buggy migration did on the first upgrade open.
    _legacy_frames_db(db_path, user_version=SCHEMA_VERSION)

    proj = Project(tmp_path)
    proj.db_path = db_path
    proj._open()
    proj._check_schema()
    try:
        frames = list(proj.iter_frames())
        assert len(frames) == 1
        assert frames[0].source_path == "/data/f1.fit"
        cols = {r[1] for r in proj._conn.execute("PRAGMA table_info(frames)")}
        assert "transparency_score" in cols and "user_override" in cols
    finally:
        proj.close()
