"""Thumbnail cache version sentinel — wipe stale thumbs on version mismatch."""

from seestack.gui.thumbnail import (
    THUMB_VERSION,
    ensure_thumb_cache_current,
    invalidate_frame_thumbs,
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


def test_invalidate_frame_thumbs_removes_only_that_frames_previews(tmp_path):
    """A refreshed frame's cached previews (Qt ``frame_NNNNNN.png`` and every web
    ``web_NNNNNN_*`` variant) must be dropped, leaving other frames untouched, so
    the next request regenerates from the frame's current pixels."""
    d = thumbs_dir(tmp_path)
    d.mkdir(parents=True)
    # Frame 1's caches: one gallery thumb + two web variants (sizes/patterns).
    (d / "frame_000001.png").write_bytes(b"old")
    (d / "web_000001_256_RGGB_v3.png").write_bytes(b"old")
    (d / "web_000001_512_RGGB_v3.png").write_bytes(b"old")
    # A different frame's caches must survive.
    (d / "frame_000002.png").write_bytes(b"keep")
    (d / "web_000002_256_RGGB_v3.png").write_bytes(b"keep")

    removed = invalidate_frame_thumbs(tmp_path, 1)

    assert removed == 3
    assert not (d / "frame_000001.png").exists()
    assert not (d / "web_000001_256_RGGB_v3.png").exists()
    assert not (d / "web_000001_512_RGGB_v3.png").exists()
    # Frame 2 untouched — the glob must not match a substring of a longer id.
    assert (d / "frame_000002.png").exists()
    assert (d / "web_000002_256_RGGB_v3.png").exists()


def test_invalidate_frame_thumbs_no_cache_dir_is_a_noop(tmp_path):
    # No thumbs dir yet (never previewed) — must not raise, returns 0.
    assert invalidate_frame_thumbs(tmp_path, 7) == 0
