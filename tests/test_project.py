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
