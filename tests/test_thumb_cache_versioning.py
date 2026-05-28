"""Thumbnail cache version sentinel — wipe stale thumbs on version mismatch."""

from seestack.gui.thumbnail import (
    THUMB_VERSION,
    ensure_thumb_cache_current,
    thumbs_dir,
)


def test_first_run_creates_sentinel(tmp_path):
    # No existing cache; ensure_current should create the dir + sentinel.
    wiped = ensure_thumb_cache_current(tmp_path)
    assert wiped is False
    sentinel = thumbs_dir(tmp_path) / ".version"
    assert sentinel.exists()
    assert sentinel.read_text().strip() == str(THUMB_VERSION)


def test_matching_version_keeps_cache(tmp_path):
    d = thumbs_dir(tmp_path)
    d.mkdir(parents=True)
    (d / ".version").write_text(str(THUMB_VERSION))
    (d / "frame_000001.png").write_bytes(b"fake")
    wiped = ensure_thumb_cache_current(tmp_path)
    assert wiped is False
    assert (d / "frame_000001.png").exists()


def test_stale_version_wipes_cache(tmp_path):
    d = thumbs_dir(tmp_path)
    d.mkdir(parents=True)
    (d / ".version").write_text("0")
    (d / "frame_000001.png").write_bytes(b"fake")
    wiped = ensure_thumb_cache_current(tmp_path)
    assert wiped is True
    assert not (d / "frame_000001.png").exists()
    # Sentinel updated.
    assert (d / ".version").read_text().strip() == str(THUMB_VERSION)
