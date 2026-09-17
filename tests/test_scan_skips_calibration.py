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

from pathlib import Path

import pytest

pytest.importorskip("astropy")

from seestack.calibrate.discover import MIN_FRAMES
from seestack.io.library import Library
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
    """Stated as the invariant rather than as two lists that happen to match:
    both sides ask ``discover``'s own rule, so a folder cannot fall between
    them."""
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
