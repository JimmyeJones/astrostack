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


# --- per-night folders that repeat the Seestar's folder name ---------------
#
# Scout 2026-10-21 sweep (3): discovery keyed on the folder basename and kept
# "the first" of a repeat, so the per-night layout `_MAX_DEPTH = 2` exists for
# listed one Moon capture out of three, and a new night folder sorting earlier
# took over an already-stacked capture's id.


def _three_moon_nights(root):
    _touch(root / "2026-10-01" / "Lunar_video" / "Lunar_1001.mp4", 10)
    _touch(root / "2026-10-05" / "Lunar_video" / "Lunar_1005.mp4", 20)
    _touch(root / "Lunar_video" / "Lunar_top.mp4", 30)


def test_every_night_of_a_repeated_folder_name_is_listed(tmp_path):
    _three_moon_nights(tmp_path)
    caps = find_video_captures(tmp_path)
    assert len(caps) == 3
    by_id = {c.id: c for c in caps}
    assert len(by_id) == 3
    # The top-level folder — the Seestar's own drop — keeps the bare id; the
    # nested ones are named after their night, and labelled by it.
    assert by_id["Lunar_video"].files[0].endswith("Lunar_top.mp4")
    assert by_id["Lunar_video"].night == ""
    assert by_id["2026-10-01_Lunar_video"].night == "2026-10-01"
    assert by_id["2026-10-05_Lunar_video"].files[0].endswith("Lunar_1005.mp4")
    assert {c.label for c in caps} == {"Moon"}
    # Every id resolves back to its own folder, and survives the routes' sanitiser.
    for cap in caps:
        assert find_video_capture(tmp_path, cap.id) == cap
        assert video_capture_id(cap.id) == cap.id


def test_a_single_folder_keeps_its_bare_id_wherever_it_is_filed(tmp_path):
    _touch(tmp_path / "2026-10-01" / "Lunar_video" / "clip.mp4", 10)
    (cap,) = find_video_captures(tmp_path)
    assert cap.id == "Lunar_video" and cap.night == ""


def test_a_new_night_sorting_earlier_does_not_take_a_stacked_capture_id(tmp_path):
    """Digits sort before letters, so ``<night>/Lunar_video`` lands before a
    top-level ``Lunar_video`` — the old rule handed it the stacked one's id."""
    _touch(tmp_path / "Lunar_video" / "stacked.mp4", 10)
    _touch(tmp_path / "2026-10-05" / "Lunar_video" / "new.mp4", 20)
    by_id = {c.id: c for c in find_video_captures(tmp_path)}
    assert by_id["Lunar_video"].files[0].endswith("stacked.mp4")
    assert by_id["2026-10-05_Lunar_video"].files[0].endswith("new.mp4")


def test_a_stored_result_keeps_the_bare_id_with_its_own_clip(tmp_path):
    # Two nested nights, nothing at the top: the stored still was made from the
    # later night's clip, and must stay with it though the other sorts first.
    _touch(tmp_path / "2026-09-28" / "Lunar_video" / "older.mp4", 10)
    _touch(tmp_path / "2026-10-01" / "Lunar_video" / "stacked.mp4", 20)
    claims = {"Lunar_video": "stacked.mp4"}
    by_id = {c.id: c for c in find_video_captures(tmp_path, claimed_by=claims.get)}
    assert by_id["Lunar_video"].files[0].endswith("stacked.mp4")
    assert by_id["2026-09-28_Lunar_video"].files[0].endswith("older.mp4")
    # Nothing stored and no unique top folder: both take their night's id, which
    # stays the same as further nights are added.
    unclaimed = {c.id for c in find_video_captures(tmp_path)}
    assert unclaimed == {"2026-09-28_Lunar_video", "2026-10-01_Lunar_video"}
    _touch(tmp_path / "2026-09-01" / "Lunar_video" / "first.mp4", 5)
    assert unclaimed <= {c.id for c in find_video_captures(tmp_path)}


def test_two_spellings_of_one_name_side_by_side_are_both_listed(tmp_path):
    _touch(tmp_path / "_Lunar_video" / "a.mp4", 10)
    _touch(tmp_path / "Lunar_video" / "b.mp4", 10)
    ids = sorted(c.id for c in find_video_captures(tmp_path))
    assert ids == ["Lunar_video", "Lunar_video-2"]
