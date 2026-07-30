"""Finding the Seestar's ``*_video/`` capture folders in the incoming tree.

These are the folders the FITS scanner deliberately skips
(``test_scanner.py::test_apply_seestar_convention_maps_sub_and_skips_output_and_video``),
so this is the other half of that decision — the two must not both claim the
same folder, and neither may claim the other's.
"""

from __future__ import annotations

from pathlib import Path
from unittest import mock

from seestack.video.discover import (
    find_video_capture,
    find_video_captures,
    video_capture_id,
)


def _touch(path, size: int = 16):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\0" * size)
    return path


def test_finds_lunar_and_solar_captures_and_labels_them_plainly(tmp_path):
    _touch(tmp_path / "Lunar_video" / "Lunar-2026.mp4", 100)
    _touch(tmp_path / "Solar_video" / "Solar-2026.avi", 200)
    caps = find_video_captures(tmp_path)
    by_kind = {c.kind: c for c in caps}
    assert set(by_kind) == {"lunar", "solar"}
    assert by_kind["lunar"].label == "Moon"
    assert by_kind["solar"].label == "Sun"
    assert by_kind["lunar"].n_files == 1
    assert by_kind["solar"].total_bytes == 200


def test_ignores_a_video_folder_with_no_video_files(tmp_path):
    (tmp_path / "Lunar_video").mkdir()
    _touch(tmp_path / "Lunar_video" / "readme.txt")
    assert find_video_captures(tmp_path) == []


def test_ignores_ordinary_deep_sky_sub_folders(tmp_path):
    """A ``_sub`` folder of FITS is the FITS scanner's business, never ours."""
    _touch(tmp_path / "M 31_sub" / "Light_001.fit", 100)
    _touch(tmp_path / "M 31" / "Stacked.fit", 100)
    assert find_video_captures(tmp_path) == []


def test_finds_a_capture_filed_one_level_down(tmp_path):
    _touch(tmp_path / "2026-07-30" / "Lunar_video" / "clip.mp4", 100)
    caps = find_video_captures(tmp_path)
    assert [c.folder_name for c in caps] == ["Lunar_video"]


def test_does_not_walk_arbitrarily_deep(tmp_path):
    _touch(tmp_path / "a" / "b" / "c" / "Lunar_video" / "clip.mp4", 100)
    assert find_video_captures(tmp_path) == []


def test_an_unrecognised_prefix_keeps_its_own_name(tmp_path):
    _touch(tmp_path / "Scenery_video" / "clip.mov", 100)
    (cap,) = find_video_captures(tmp_path)
    assert cap.kind == "other"
    assert cap.label == "Scenery"


def test_capture_ids_are_path_safe_and_stable(tmp_path):
    assert video_capture_id("Lunar_video") == "Lunar_video"
    assert video_capture_id("M 31_video") == "M_31_video"
    assert "/" not in video_capture_id("../../etc/passwd")
    assert video_capture_id("...") == "video"


def test_lookup_by_id_round_trips_and_rejects_unknown(tmp_path):
    _touch(tmp_path / "Lunar_video" / "clip.mp4", 100)
    (cap,) = find_video_captures(tmp_path)
    assert find_video_capture(tmp_path, cap.id) == cap
    assert find_video_capture(tmp_path, "nope") is None


def test_missing_root_is_not_an_error(tmp_path):
    assert find_video_captures(tmp_path / "does-not-exist") == []


def test_finds_a_capture_filed_beside_a_dump_of_sub_frames(tmp_path):
    """A capture must be found regardless of what else is in the folder.

    An earlier revision capped how many directory entries the walk would read,
    to bound the work done on a page poll. ``os.scandir`` returns entries in
    filesystem order, so that cap decided *at random* whether a capture sitting
    beside a few hundred sub-frames was discovered — the user's video would
    appear or vanish depending on inode order (it passed locally and failed on
    CI). Reading the whole listing is one streamed syscall; a capture going
    missing is not an acceptable price for skipping part of it.
    """
    night = tmp_path / "2026-07-30"
    for i in range(300):
        _touch(night / f"Light_{i:03d}.fit")
    _touch(night / "zzz_video" / "clip.mp4", 100)
    assert [c.folder_name for c in find_video_captures(tmp_path)] == ["zzz_video"]


def test_does_not_stat_every_file_while_walking(tmp_path):
    """The walk runs on every poll of the Moon & Sun page, so it must decide
    "is this a directory?" from the dirent rather than stat-ing each of a
    target folder's thousands of sub-frames."""
    for i in range(50):
        _touch(tmp_path / "M_42" / f"Light_{i:03d}.fit")
    _touch(tmp_path / "Lunar_video" / "clip.mp4", 100)

    stats: list[str] = []
    real_stat = Path.stat

    def counting_stat(self, *a, **kw):
        stats.append(self.name)
        return real_stat(self, *a, **kw)

    with mock.patch.object(Path, "stat", counting_stat):
        assert [c.folder_name for c in find_video_captures(tmp_path)] == ["Lunar_video"]
    # The 50 FITS in the neighbouring target folder are never touched — only the
    # roots being walked and the discovered capture's own video file are stat-ed.
    assert not [n for n in stats if n.startswith("Light_")]
    assert len(stats) < 10, stats


def test_files_are_listed_in_a_stable_order(tmp_path):
    for name in ("c.mp4", "a.mp4", "b.mp4"):
        _touch(tmp_path / "Lunar_video" / name, 10)
    (cap,) = find_video_captures(tmp_path)
    assert [p.rsplit("/", 1)[-1] for p in cap.files] == ["a.mp4", "b.mp4", "c.mp4"]
