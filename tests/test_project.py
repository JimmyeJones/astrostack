"""Project SQLite — create, open, insert, update, iterate."""

import pytest

from seestack.io.project import FrameRow, Project


@pytest.fixture
def proj(tmp_path):
    p = Project.create(tmp_path / "myproj", name="Test Project")
    yield p
    p.close()


def test_create_and_meta(proj):
    assert proj.get_meta("name") == "Test Project"
    from seestack.io.project import SCHEMA_VERSION
    assert proj.get_meta("schema_version") == str(SCHEMA_VERSION)


def test_delete_meta(proj):
    proj.set_meta("scratch", "v")
    assert proj.get_meta("scratch") == "v"
    proj.delete_meta("scratch")
    assert proj.get_meta("scratch") is None
    # Deleting an absent key is a no-op, not an error.
    proj.delete_meta("never_set")


def test_open_after_create(tmp_path):
    p = Project.create(tmp_path / "p", name="Reopen")
    p.close()
    p2 = Project.open(tmp_path / "p")
    try:
        assert p2.get_meta("name") == "Reopen"
    finally:
        p2.close()


def test_open_missing_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        Project.open(tmp_path / "nope")


def test_add_and_get_frame(proj):
    row = FrameRow(
        source_path=r"\\nas\astro\seestar\frame_001.fit",
        exposure_s=10.0,
        gain=80.0,
        width_px=1920,
        height_px=1080,
        bayer_pattern="RGGB",
    )
    fid = proj.add_frame(row)
    out = proj.get_frame(fid)
    assert out is not None
    assert out.source_path == row.source_path
    assert out.exposure_s == 10.0
    assert out.bayer_pattern == "RGGB"
    assert out.accept is True
    assert out.streak_detected is False


def test_bulk_insert_and_count(proj):
    frames = [FrameRow(source_path=f"frame_{i:04d}.fit") for i in range(100)]
    ids = proj.add_frames(frames)
    assert len(ids) == 100
    assert proj.count() == 100
    assert proj.count(accepted_only=True) == 100


def test_update_frame(proj):
    fid = proj.add_frame(FrameRow(source_path="x.fit"))
    proj.update_frame(fid, fwhm_px=2.7, accept=False, reject_reason="auto:fwhm")
    out = proj.get_frame(fid)
    assert out is not None
    assert out.fwhm_px == 2.7
    assert out.accept is False
    assert out.reject_reason == "auto:fwhm"
    assert proj.count(accepted_only=True) == 0


def test_reset_frame_qc_clears_auto_metrics_and_reject(proj):
    fid = proj.add_frame(FrameRow(source_path="x.fit"))
    proj.update_frame(fid, star_count=120, fwhm_px=3.1, sky_adu_median=800.0,
                      eccentricity_median=0.4, transparency_score=0.9,
                      streak_detected=True, streak_count=2,
                      accept=False, reject_reason="auto:streak")
    proj.reset_frame_qc(fid)
    out = proj.get_frame(fid)
    assert out is not None
    assert out.star_count is None and out.fwhm_px is None
    assert out.sky_adu_median is None and out.eccentricity_median is None
    assert out.transparency_score is None
    assert out.streak_detected is False and out.streak_count == 0
    # An auto reject is cleared so the re-QC decides fresh.
    assert out.accept is True and out.reject_reason is None


def test_reset_frame_qc_preserves_a_user_override(proj):
    fid = proj.add_frame(FrameRow(source_path="x.fit"))
    proj.update_frame(fid, star_count=50, accept=False,
                      reject_reason="user", user_override=True)
    proj.reset_frame_qc(fid)
    out = proj.get_frame(fid)
    assert out is not None
    assert out.star_count is None          # metrics still cleared for re-QC
    assert out.accept is False             # but the user's decision stands
    assert out.reject_reason == "user"


def test_reset_frame_qc_on_missing_frame_is_a_noop(proj):
    proj.reset_frame_qc(999)  # no such frame → no raise


def test_iter_frames_filters(proj):
    proj.add_frames([FrameRow(source_path=f"a{i}.fit") for i in range(5)])
    proj.update_frame(1, accept=False, reject_reason="user")
    accepted = list(proj.iter_frames(accepted_only=True))
    assert len(accepted) == 4


def test_reject_reason_counts(proj):
    proj.add_frames([FrameRow(source_path=f"a{i}.fit") for i in range(6)])
    proj.update_frame(1, accept=False, reject_reason="qc:fwhm")
    proj.update_frame(2, accept=False, reject_reason="qc:fwhm")
    proj.update_frame(3, accept=False, reject_reason="bulk:streaked")
    # A rejected frame with no explicit reason buckets under "user".
    proj.update_frame(4, accept=False, reject_reason=None)
    counts = proj.reject_reason_counts()
    assert counts == {"qc:fwhm": 2, "bulk:streaked": 1, "user": 1}
    # Accepted frames are ignored entirely.
    assert sum(counts.values()) == proj.count() - proj.count(accepted_only=True)


def test_unique_source_path(proj):
    import sqlite3

    proj.add_frame(FrameRow(source_path="dup.fit"))
    with pytest.raises(sqlite3.IntegrityError):
        proj.add_frame(FrameRow(source_path="dup.fit"))


def test_open_empty_sqlite_builds_the_base_schema(tmp_path):
    """Opening a pre-existing but empty/foreign sqlite (user_version 0, no
    `frames` table) must build the base schema during migration rather than
    stamp the version and leave a DB that raises 'no such table: frames'."""
    import sqlite3

    project_dir = tmp_path / "foreign"
    project_dir.mkdir()
    db_path = project_dir / "project.sqlite"
    # A bare, empty database file — as if a blank/corrupt sqlite were dropped in.
    sqlite3.connect(db_path).close()

    proj = Project.open(project_dir)
    try:
        # Migration built the schema, so the project is fully usable.
        fid = proj.add_frame(FrameRow(source_path="a.fit"))
        assert fid is not None
        assert proj.count() == 1
        from seestack.io.project import SCHEMA_VERSION
        version = proj._conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == SCHEMA_VERSION
    finally:
        proj.close()


def test_stack_run_rejection_tally_round_trips(proj):
    """A run's outlier-rejection tally (fraction + mode) persists and reads back —
    the data the "How's my stack?" clean-up note reads."""
    from seestack.io.project import StackRunRow

    proj.add_stack_run(StackRunRow(
        id=None, timestamp_utc="2026-07-23T00:00:00+00:00", output_basename="master",
        fits_path="m.fits", tiff_path=None, preview_path=None, n_frames_used=30,
        canvas_h=1080, canvas_w=1920, coverage_min=30, coverage_max=30,
        options_json="{}", rejection_fraction=0.012, rejection_mode="sigma-clip"))
    run = next(iter(proj.iter_stack_runs()))
    assert run.rejection_fraction == 0.012
    assert run.rejection_mode == "sigma-clip"


def test_v9_project_migrates_rejection_columns_additively(tmp_path):
    """An older (schema 9) project — whose ``stack_runs`` predates the rejection
    columns — upgrades cleanly on open: existing runs read the new fields as
    ``None`` (no clean-up claimed) and a fresh run persists them. Guards the
    live-install in-place upgrade (AGENTS.md §9)."""
    import sqlite3

    from seestack.io.project import SCHEMA_VERSION, StackRunRow

    project_dir = tmp_path / "v9"
    project_dir.mkdir()
    db_path = project_dir / "project.sqlite"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        PRAGMA user_version = 9;
        CREATE TABLE project_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE stack_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp_utc TEXT NOT NULL,
            output_basename TEXT NOT NULL, fits_path TEXT, tiff_path TEXT,
            preview_path TEXT, n_frames_used INTEGER NOT NULL, canvas_h INTEGER NOT NULL,
            canvas_w INTEGER NOT NULL, coverage_min INTEGER NOT NULL DEFAULT 0,
            coverage_max INTEGER NOT NULL DEFAULT 0, options_json TEXT NOT NULL,
            notes TEXT, total_exposure_s REAL, transparency_ratio REAL,
            noise_sigma REAL, calstat TEXT, is_mosaic INTEGER, engine_version TEXT);
        CREATE TABLE frames (id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_path TEXT NOT NULL UNIQUE, accept INTEGER NOT NULL DEFAULT 1);
        INSERT INTO stack_runs(timestamp_utc, output_basename, n_frames_used,
            canvas_h, canvas_w, options_json)
          VALUES('2026-01-01T00:00:00+00:00', 'old', 10, 1080, 1920, '{}');
        """
    )
    conn.commit()
    conn.close()

    proj = Project.open(project_dir)
    try:
        assert proj._conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        old = next(iter(proj.iter_stack_runs()))
        assert old.rejection_fraction is None and old.rejection_mode is None
        # A fresh run on the migrated DB persists the new tally.
        proj.add_stack_run(StackRunRow(
            id=None, timestamp_utc="2026-07-23T01:00:00+00:00", output_basename="new",
            fits_path=None, tiff_path=None, preview_path=None, n_frames_used=5,
            canvas_h=1, canvas_w=1, coverage_min=1, coverage_max=1, options_json="{}",
            rejection_fraction=0.03, rejection_mode="min-max-reject"))
        newest = next(iter(proj.iter_stack_runs()))
        assert newest.rejection_fraction == 0.03
        assert newest.rejection_mode == "min-max-reject"
    finally:
        proj.close()


def test_v10_project_migrates_preview_stretch_columns_additively(tmp_path):
    """An older (schema 10) project — whose ``stack_runs`` predates the saved
    preview-stretch columns — upgrades cleanly on open: existing runs read
    ``preview_stretch``/``preview_black`` as ``None`` (no custom stretch saved =
    the default STF preview) and ``set_stack_preview_stretch`` persists a fresh
    one. Guards the live-install in-place upgrade (AGENTS.md §9)."""
    import sqlite3

    from seestack.io.project import SCHEMA_VERSION, StackRunRow

    project_dir = tmp_path / "v10"
    project_dir.mkdir()
    db_path = project_dir / "project.sqlite"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        PRAGMA user_version = 10;
        CREATE TABLE project_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE stack_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp_utc TEXT NOT NULL,
            output_basename TEXT NOT NULL, fits_path TEXT, tiff_path TEXT,
            preview_path TEXT, n_frames_used INTEGER NOT NULL, canvas_h INTEGER NOT NULL,
            canvas_w INTEGER NOT NULL, coverage_min INTEGER NOT NULL DEFAULT 0,
            coverage_max INTEGER NOT NULL DEFAULT 0, options_json TEXT NOT NULL,
            notes TEXT, total_exposure_s REAL, transparency_ratio REAL,
            noise_sigma REAL, calstat TEXT, is_mosaic INTEGER, engine_version TEXT,
            rejection_fraction REAL, rejection_mode TEXT);
        CREATE TABLE frames (id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_path TEXT NOT NULL UNIQUE, accept INTEGER NOT NULL DEFAULT 1);
        INSERT INTO stack_runs(timestamp_utc, output_basename, n_frames_used,
            canvas_h, canvas_w, options_json)
          VALUES('2026-01-01T00:00:00+00:00', 'old', 10, 1080, 1920, '{}');
        """
    )
    conn.commit()
    conn.close()

    proj = Project.open(project_dir)
    try:
        assert proj._conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        old = next(iter(proj.iter_stack_runs()))
        assert old.preview_stretch is None and old.preview_black is None
        # A fresh run + a saved custom stretch persists and reads back.
        new_id = proj.add_stack_run(StackRunRow(
            id=None, timestamp_utc="2026-07-23T01:00:00+00:00", output_basename="new",
            fits_path=None, tiff_path=None, preview_path=None, n_frames_used=5,
            canvas_h=1, canvas_w=1, coverage_min=1, coverage_max=1, options_json="{}"))
        assert proj.set_stack_preview_stretch(new_id, 0.72, 0.44) is True
        newest = next(r for r in proj.iter_stack_runs() if r.id == new_id)
        assert newest.preview_stretch == 0.72
        assert newest.preview_black == 0.44
        # Clearing it back to the default STF preview.
        assert proj.set_stack_preview_stretch(new_id, None, None) is True
        cleared = next(r for r in proj.iter_stack_runs() if r.id == new_id)
        assert cleared.preview_stretch is None and cleared.preview_black is None
        # No row for an unknown id.
        assert proj.set_stack_preview_stretch(999999, 0.5, 0.5) is False
    finally:
        proj.close()


def test_open_closes_the_connection_when_schema_check_fails(tmp_path, monkeypatch):
    """A newer on-disk ``user_version`` makes ``_check_schema`` raise; ``open``
    must close the connection it opened before propagating, rather than leak it.
    The classmethod never returns the instance on this path, so the callers'
    ``if proj is not None: proj.close()`` guards can't clean it up."""
    import sqlite3

    from seestack.io import project as project_mod
    from seestack.io.project import SCHEMA_VERSION

    project_dir = tmp_path / "from_the_future"
    proj = Project.create(project_dir, name="Future")
    # Stamp a schema version this build is too old to open.
    proj._conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
    proj.close()

    # Capture every connection Project._open creates so we can assert it closed.
    opened: list[sqlite3.Connection] = []
    real_connect = sqlite3.connect

    def tracking_connect(*args, **kwargs):
        conn = real_connect(*args, **kwargs)
        opened.append(conn)
        return conn

    monkeypatch.setattr(project_mod.sqlite3, "connect", tracking_connect)

    with pytest.raises(RuntimeError, match="newer than this Seestack"):
        Project.open(project_dir)

    assert opened, "expected _open to have created a connection"
    # Operating on a closed sqlite connection raises ProgrammingError — proof the
    # handle was closed (fails before the fix, which left it open).
    with pytest.raises(sqlite3.ProgrammingError):
        opened[-1].execute("SELECT 1")
