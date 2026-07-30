"""Finding the Seestar's ``*_video/`` capture folders in the incoming tree.

These are the folders the FITS scanner deliberately skips
(``test_scanner.py::test_apply_seestar_convention_maps_sub_and_skips_output_and_video``),
so this is the other half of that decision — the two must not both claim the
same folder, and neither may claim the other's.
"""

from __future__ import annotations

from seestack.video import discover
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


def test_gives_up_on_a_directory_holding_a_dump_of_sub_frames(tmp_path, monkeypatch):
    """The walk runs on every page poll; it must not re-read a huge frame folder.

    Beyond the entry cap we stop looking for ``_video`` children *inside* that
    directory — a folder with thousands of entries is a dump of subs, not a
    container someone filed a capture under.
    """
    monkeypatch.setattr(discover, "_MAX_ENTRIES_PER_DIR", 5)
    night = tmp_path / "2026-07-30"
    for i in range(20):
        _touch(night / f"Light_{i:03d}.fit")
    _touch(night / "zzz_video" / "clip.mp4", 100)
    assert find_video_captures(tmp_path) == []
    # A normal-sized folder one level down is still found.
    _touch(tmp_path / "small" / "Lunar_video" / "clip.mp4", 100)
    assert [c.folder_name for c in find_video_captures(tmp_path)] == ["Lunar_video"]


def test_files_are_listed_in_a_stable_order(tmp_path):
    for name in ("c.mp4", "a.mp4", "b.mp4"):
        _touch(tmp_path / "Lunar_video" / name, 10)
    (cap,) = find_video_captures(tmp_path)
    assert [p.rsplit("/", 1)[-1] for p in cap.files] == ["a.mp4", "b.mp4", "c.mp4"]
