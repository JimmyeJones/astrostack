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


def test_unique_source_path(proj):
    import sqlite3

    proj.add_frame(FrameRow(source_path="dup.fit"))
    with pytest.raises(sqlite3.IntegrityError):
        proj.add_frame(FrameRow(source_path="dup.fit"))
