"""A folder of darks under ``incoming/`` is calibration data, not a target.

The app both **expects and invites** darks there. The Calibration page's build
form is placeheld with ``/data/incoming/darks`` and tells the owner to point at
"a Seestar ``Dark`` folder on your NAS", and ``GET /api/calibration/incoming`` is
an entire shipped feature whose premise is that they live under ``incoming/``.
The scan, meanwhile, had no notion of a calibration frame at all — so exactly the
folders one half of the app asked for, the other half turned into light targets:
a "Darks 10s" of six frames on the Library wall and in the Gallery, in the
campaign stats, offered by the planner, chipped "Not stretched yet", and
stackable into a picture of nothing.

Found by putting a scratch install into the one state no dogfood pass had ever
been in — holding calibration frames at all — which is what
``scripts/agent-dogfood.sh --calibration`` exists to reach.

The tests here are mostly about **not** skipping: a rule that swallows a night of
real subs is far worse than the bug it fixes.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

pytest.importorskip("astropy")

from seestack.calibrate.discover import MIN_FRAMES
from seestack.io.library import UNSORTED_TARGET_NAME, Library
from seestack.io.scanner import scan_and_organize
from tests.synth import write_seestar_fits
from webapp.sample_data import write_sample_calibration_frames


def _subs(folder: Path, n: int = 6) -> None:
    """A folder of ordinary Seestar lights — which declare no ``IMAGETYP``."""
    folder.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        write_seestar_fits(folder / f"frame_{i:03d}.fit",
                           width=48, height=32, n_stars=3, seed=i + 1)


def _scan(tmp_path: Path, incoming: Path):
    lib = Library.open_or_create(tmp_path / "library")
    try:
        result = scan_and_organize(lib, incoming, copy_to_cache=False)
        names = sorted(e.name for e in lib.iter_targets())
    finally:
        lib.close()
    return result, names


def test_a_folder_of_darks_does_not_become_a_target(tmp_path: Path) -> None:
    """The bug, reproduced: before this, the library gained "Darks 10s"."""
    incoming = tmp_path / "incoming"
    write_sample_calibration_frames(incoming / "Darks 10s", "dark")
    write_sample_calibration_frames(incoming / "Flats", "flat")

    result, names = _scan(tmp_path, incoming)

    assert names == []
    assert result.targets == []
    assert sorted((s.target_name, s.kind, s.n_files)
                  for s in result.skipped_calibration_folders) == [
        ("Darks 10s", "dark", 6), ("Flats", "flat", 6)]
    # What the frames actually said, carried through rather than re-derived.
    assert all(s.declared for s in result.skipped_calibration_folders)


def test_real_subs_beside_the_darks_still_land(tmp_path: Path) -> None:
    """The half that matters most: the skip must cost nobody a night of subs."""
    incoming = tmp_path / "incoming"
    write_sample_calibration_frames(incoming / "Darks 10s", "dark")
    _subs(incoming / "M 42_sub")

    result, names = _scan(tmp_path, incoming)

    assert names == ["M 42"]
    assert [t.n_frames_found for t in result.targets] == [6]
    assert [s.target_name for s in result.skipped_calibration_folders] == ["Darks 10s"]


def test_a_folder_named_darks_whose_frames_are_lights_is_still_ingested(
    tmp_path: Path,
) -> None:
    """The name decides nothing. An ordinary Seestar sub writes no ``IMAGETYP``,
    so a folder somebody called "Darks" but filled with subs is a target — which
    is the same asymmetry that stops the build offer combining somebody's sky
    into a master dark."""
    incoming = tmp_path / "incoming"
    _subs(incoming / "Darks")

    result, names = _scan(tmp_path, incoming)

    assert names == ["Darks"]
    assert result.skipped_calibration_folders == []


def test_one_light_among_the_darks_rules_the_whole_folder_back_in(
    tmp_path: Path,
) -> None:
    """Mixed is not calibration. A folder holding real subs must be ingested
    however many darks were dropped in beside them — losing a sub is the one
    outcome this rule may never produce."""
    incoming = tmp_path / "incoming"
    mixed = incoming / "Darks 10s"
    write_sample_calibration_frames(mixed, "dark")
    # Named so it sorts first: index 0 is the header the rule reads first.
    write_seestar_fits(mixed / "aaa_light.fit", width=48, height=32,
                       n_stars=3, seed=9)

    result, names = _scan(tmp_path, incoming)

    assert names == ["Darks 10s"]
    assert result.skipped_calibration_folders == []


def test_below_the_offer_floor_the_folder_is_still_ingested(tmp_path: Path) -> None:
    """The skip carries ``discover.MIN_FRAMES`` on purpose, so the set the scan
    passes over and the set the Calibration page offers to build from are the
    *same* set — which is what lets the "subs waiting in incoming/" note exclude
    them without opening anything under there itself (AGENTS.md §10). The honest
    cost is this: a fragment of one to four declared darks is still a target."""
    incoming = tmp_path / "incoming"
    write_sample_calibration_frames(incoming / "Darks 10s", "dark",
                                    n=MIN_FRAMES - 1)

    result, names = _scan(tmp_path, incoming)

    assert names == ["Darks 10s"]
    assert result.skipped_calibration_folders == []


def test_the_skip_and_the_build_offer_name_the_same_folders(tmp_path: Path) -> None:
    """Both sides ask ``discover``'s own rule, so on this tree — calibration
    frames sitting **directly** in a top-level folder, the shape the Calibration
    page's build form asks for — a folder cannot fall between them.

    **Only on this tree.** v0.455.0 read the agreement here as an invariant, and
    it is not one: the floor is per-*unit* on the skip side and per-*directory* on
    the offer side, and the two name folders at different depths besides. The
    three tests below are the shapes where they diverge (observer issue #1088),
    which is why the "subs waiting in incoming/" note is handed what the scan
    recorded rather than a reconstruction of it."""
    from seestack.calibrate.discover import find_calibration_folders

    incoming = tmp_path / "incoming"
    write_sample_calibration_frames(incoming / "Darks 10s", "dark")
    write_sample_calibration_frames(incoming / "Flats", "flat")
    write_sample_calibration_frames(incoming / "Bias fragment", "bias",
                                    n=MIN_FRAMES - 1)
    _subs(incoming / "M 42_sub")

    result, _names = _scan(tmp_path, incoming)

    offered = {f.folder_name for f in find_calibration_folders(incoming)}
    skipped = {s.target_name for s in result.skipped_calibration_folders}
    assert offered == skipped == {"Darks 10s", "Flats"}


def test_an_unreadable_header_ingests_rather_than_guesses(tmp_path: Path) -> None:
    """Getting frames in is the scan's job. A folder whose headers cannot be read
    is ingested exactly as it was before this rule existed."""
    incoming = tmp_path / "incoming"
    broken = incoming / "Something"
    broken.mkdir(parents=True)
    for i in range(MIN_FRAMES + 1):
        (broken / f"x_{i:03d}.fit").write_bytes(b"\x00" * 2048)

    result, names = _scan(tmp_path, incoming)

    assert names == ["Something"]
    assert result.skipped_calibration_folders == []


def test_a_skipped_unit_records_the_folder_it_would_have_been(tmp_path: Path) -> None:
    """The skip carries the unit's **folder**, not just the target name it would
    have become — and those are different strings in general
    (``<T>_mosaic_sub`` becomes "<T> (mosaic)").

    One consumer has to compare the two: the "subs waiting in incoming/" note
    excludes the folders the scan passed over, and it may not open anything under
    ``incoming/`` to work them out for itself (AGENTS.md §10). Recorded here, by
    the one pass that knows both the unit boundaries and the headers, rather than
    reconstructed from a directory walk that cannot agree with it — observer
    issue #1088, where that reconstruction named ``Darks/20s`` for a unit the
    scan called ``Darks``.
    """
    incoming = tmp_path / "incoming"
    write_sample_calibration_frames(incoming / "Darks 10s", "dark")
    write_sample_calibration_frames(incoming / "Darks" / "20s", "dark")
    _subs(incoming / "M 42_sub")

    result, names = _scan(tmp_path, incoming)

    assert names == ["M 42"]
    assert sorted((s.target_name, s.folder, s.n_files)
                  for s in result.skipped_calibration_folders) == [
        ("Darks", "Darks", 6), ("Darks 10s", "Darks 10s", 6)]


def test_darks_loose_in_the_drop_folder_record_the_root_unit(tmp_path: Path) -> None:
    """Loose frames are the ``Unsorted`` catch-all, whose folder is the empty
    string — a real answer, which is why ``""`` cannot also mean "the scan did
    not record it"."""
    incoming = tmp_path / "incoming"
    write_sample_calibration_frames(incoming, "dark")

    result, names = _scan(tmp_path, incoming)

    assert names == []
    assert [(s.target_name, s.folder) for s in result.skipped_calibration_folders] \
        == [(UNSORTED_TARGET_NAME, "")]


def test_a_unit_of_two_half_full_dark_directories_is_still_skipped(
    tmp_path: Path,
) -> None:
    """``MIN_FRAMES`` is this rule's floor on the whole **unit**; it is
    ``discover``'s floor on each individual **directory**. So three darks in each
    of two directories is one skipped six-frame unit that the build offer does
    not list at all — the place the "two sets are identical" claim of v0.455.0
    breaks that no string matching between the two could repair (#1088)."""
    from seestack.calibrate.discover import find_calibration_folders

    incoming = tmp_path / "incoming"
    half = MIN_FRAMES - 2
    for part in ("a", "b"):
        write_sample_calibration_frames(incoming / "Darks 20s" / part, "dark",
                                        n=half)

    result, names = _scan(tmp_path, incoming)

    assert names == []
    assert [(s.target_name, s.folder, s.n_files)
            for s in result.skipped_calibration_folders] \
        == [("Darks 20s", "Darks 20s", 2 * half)]
    assert find_calibration_folders(incoming) == []


def test_a_container_child_of_darks_records_its_nested_folder(tmp_path: Path) -> None:
    """A whole-device drop keeps its container level, and the scan expands it
    into one unit per child — so a child unit's folder is two components deep and
    the record has to say so, or the note's exact match cannot find it."""
    incoming = tmp_path / "incoming"
    _subs(incoming / "MyWorks" / "M 42_sub")
    write_sample_calibration_frames(incoming / "MyWorks" / "Darks 10s", "dark")

    result, names = _scan(tmp_path, incoming)

    assert names == ["M 42"]
    assert [(s.target_name, s.folder) for s in result.skipped_calibration_folders] \
        == [("Darks 10s", os.path.join("MyWorks", "Darks 10s"))]
