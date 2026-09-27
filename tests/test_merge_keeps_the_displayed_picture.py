"""Combining folders must not swap the deep target's picture for a shallow one.

The Seestar writes a new folder per night, so the folder being combined *in* is
usually the most recent one — and its carried stack run keeps its own
``timestamp_utc``. Everything that decides which picture a target shows takes the
newest run when nothing is pinned (``refresh_target_stats``,
``finishedpicture.displayed_picture_run``, ``routers.targets.current_picture_path``),
so the Library wall and the Target page started showing the thinner one-night
stack of the target the owner had just made deeper, until he re-stacked it.

The fix is the existing cover mechanism: a merge that carries pictures in pins the
picture the destination was *already* showing, when nothing was pinned.
"""

from __future__ import annotations

import json
from pathlib import Path

from seestack.io.library import Library
from seestack.io.project import FrameRow, StackRunRow


def _target_with_a_picture(lib: Library, name: str, *, stamp: str,
                           pixels: bytes) -> str:
    """A target holding one finished picture, stamped ``stamp``."""
    entry, proj = lib.create_target(name)
    try:
        proj.add_frame(FrameRow(
            source_path=str(Path(lib.root) / f"{entry.safe_name}_light.fit"),
            width_px=8, height_px=8, bayer_pattern="RGGB", exposure_s=10.0,
        ))
        out = Path(proj.project_dir) / "output"
        out.mkdir(parents=True, exist_ok=True)
        (out / "master.fits").write_bytes(pixels)
        (out / "master_preview.png").write_bytes(b"preview:" + pixels)
        proj.add_stack_run(StackRunRow(
            id=None, timestamp_utc=stamp, output_basename="master",
            fits_path=str(out / "master.fits"), tiff_path=None,
            preview_path=str(out / "master_preview.png"),
            n_frames_used=1, canvas_h=8, canvas_w=8,
            coverage_min=1, coverage_max=1, options_json=json.dumps({}),
        ))
    finally:
        proj.close()
    return entry.safe_name


def _displayed_preview_bytes(lib: Library, safe: str) -> bytes:
    """What the app shows for ``safe``: the pinned cover, else the newest run."""
    entry = lib.find_target(safe)
    assert entry is not None
    proj = lib.open_target(safe)
    try:
        runs = list(proj.iter_stack_runs())            # newest first
    finally:
        proj.close()
    if entry.cover_stack_run_id is not None:
        pinned = next((r for r in runs
                       if r.id == entry.cover_stack_run_id and r.preview_path), None)
        if pinned is not None:
            return Path(pinned.preview_path).read_bytes()
    newest = next((r for r in runs if r.preview_path), None)
    assert newest is not None
    return Path(newest.preview_path).read_bytes()


def test_the_deep_targets_own_picture_is_still_the_one_shown(tmp_path):
    lib = Library.create(tmp_path / "lib")
    try:
        deep = _target_with_a_picture(lib, "M 31", stamp="2026-09-01T22:00:00Z",
                                      pixels=b"the-deep-master")
        shallow = _target_with_a_picture(lib, "M 31 second night",
                                         stamp="2026-09-20T22:00:00Z",
                                         pixels=b"one-nights-master")

        result = lib.merge_targets_result(deep, [shallow])
        assert result.pictures_kept == 1

        # The carried run is the newest, so without a pin it would win.
        assert _displayed_preview_bytes(lib, deep) == b"preview:the-deep-master"
        entry = lib.find_target(deep)
        assert entry is not None and entry.cover_stack_run_id is not None
        # And the merge says so, so the confirmation can.
        assert result.picture_pinned is True
    finally:
        lib.close()


def test_a_cover_the_owner_pinned_is_left_alone(tmp_path):
    lib = Library.create(tmp_path / "lib")
    try:
        deep = _target_with_a_picture(lib, "M 31", stamp="2026-09-01T22:00:00Z",
                                      pixels=b"the-deep-master")
        proj = lib.open_target(deep)
        try:
            pinned_id = next(iter(proj.iter_stack_runs())).id
        finally:
            proj.close()
        lib.set_target_cover(deep, pinned_id)
        shallow = _target_with_a_picture(lib, "M 31 second night",
                                         stamp="2026-09-20T22:00:00Z",
                                         pixels=b"one-nights-master")

        result = lib.merge_targets_result(deep, [shallow])

        entry = lib.find_target(deep)
        assert entry is not None and entry.cover_stack_run_id == pinned_id
        # Nothing was pinned by the merge — the owner's pin already wins.
        assert result.picture_pinned is False
    finally:
        lib.close()


def test_a_destination_with_no_picture_of_its_own_shows_the_carried_one(tmp_path):
    """The one case where the carried picture *should* be what you see."""
    lib = Library.create(tmp_path / "lib")
    try:
        entry, proj = lib.create_target("M 31")
        try:
            proj.add_frame(FrameRow(
                source_path=str(tmp_path / "deep_light.fit"),
                width_px=8, height_px=8, bayer_pattern="RGGB", exposure_s=10.0,
            ))
        finally:
            proj.close()
        deep = entry.safe_name
        shallow = _target_with_a_picture(lib, "M 31 second night",
                                         stamp="2026-09-20T22:00:00Z",
                                         pixels=b"one-nights-master")

        result = lib.merge_targets_result(deep, [shallow])

        kept = lib.find_target(deep)
        assert kept is not None and kept.cover_stack_run_id is None
        assert result.picture_pinned is False
        assert _displayed_preview_bytes(lib, deep) == b"preview:one-nights-master"
    finally:
        lib.close()


def test_a_merge_that_carries_no_picture_pins_nothing(tmp_path):
    """A merge of two never-stacked folders must not invent a cover pin."""
    lib = Library.create(tmp_path / "lib")
    try:
        names = []
        for name in ("M 31", "M 31 second night"):
            entry, proj = lib.create_target(name)
            try:
                proj.add_frame(FrameRow(
                    source_path=str(tmp_path / f"{entry.safe_name}.fit"),
                    width_px=8, height_px=8, bayer_pattern="RGGB",
                    exposure_s=10.0,
                ))
            finally:
                proj.close()
            names.append(entry.safe_name)

        result = lib.merge_targets_result(names[0], [names[1]])

        kept = lib.find_target(names[0])
        assert kept is not None and kept.cover_stack_run_id is None
        assert result.picture_pinned is False
    finally:
        lib.close()
