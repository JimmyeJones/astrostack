"""``plan_incoming_units`` — the scan's *plan*, from a file listing alone.

The plan exists so "is anything in ``incoming/`` not in my library yet?" can be
answered without a second walk of the one tree the app may never write to. Its
whole value is that it agrees with the real scan about which folder becomes which
target and which folders are deliberately passed over — so the load-bearing test
here is the one that runs both over the same tree and compares.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("astropy")

from seestack.io.ingest import find_fits_files
from seestack.io.library import UNSORTED_TARGET_NAME, Library
from seestack.io.scanner import plan_incoming_units, scan_and_organize
from tests.synth import write_seestar_fits


def _fits(path: Path, seed: int = 1) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_seestar_fits(path, width=48, height=32, n_stars=3, seed=seed)


def _listing(root: Path) -> dict[str, float]:
    """The shape the watcher hands over: absolute path -> mtime."""
    return {str(p): p.stat().st_mtime for p in find_fits_files(root)}


def _by_folder(root: Path) -> dict[str, tuple[str, int]]:
    return {u.folder: (u.target_name, u.n_files)
            for u in plan_incoming_units(root, _listing(root))}


def _mixed_tree(root: Path) -> None:
    """Every folder shape the convention has an opinion about, in one drop."""
    _fits(root / "M 42_sub" / "frame_001.fit", 1)
    _fits(root / "M 42_sub" / "frame_002.fit", 2)
    # The Seestar's own picture, beside its raw subs -> skipped.
    _fits(root / "M 42" / "Stacked_30s.fit", 3)
    # A mosaic's raw subs -> its own, differently-named target.
    _fits(root / "NGC 7000_mosaic_sub" / "frame_001.fit", 4)
    # Captures, not deep-sky subs -> skipped.
    _fits(root / "Moon_video" / "frame_001.fit", 5)
    _fits(root / "Scenery_photo" / "frame_001.fit", 6)
    # Another program's scratch directory -> skipped.
    _fits(root / "batch_stack_tmp" / "frame_001.fit", 7)
    # A plainly-named folder with no "_sub" sibling -> ingested as itself.
    _fits(root / "Andromeda" / "night1" / "frame_001.fit", 8)
    # Loose in the root -> the Unsorted catch-all.
    _fits(root / "loose.fit", 9)


def test_the_plan_names_the_same_targets_the_scan_builds(tmp_path: Path) -> None:
    """The claim the whole feature rests on: plan and scan cannot disagree.

    Run over one tree holding every shape the convention rules on, the folders
    the plan offers and the targets a real ``scan_and_organize`` creates are the
    same set with the same frame counts — including the four it must *not* offer.
    """
    incoming = tmp_path / "incoming"
    _mixed_tree(incoming)

    planned = plan_incoming_units(incoming, _listing(incoming))

    lib = Library.open_or_create(tmp_path / "library")
    try:
        result = scan_and_organize(lib, incoming, copy_to_cache=False)
    finally:
        lib.close()

    assert (sorted((u.target_name, u.n_files) for u in planned)
            == sorted((t.target_name, t.n_frames_found) for t in result.targets))


def test_the_convention_skips_are_not_offered_as_lag(tmp_path: Path) -> None:
    """A folder the scan passes over on purpose is not something to report."""
    incoming = tmp_path / "incoming"
    _mixed_tree(incoming)

    folders = _by_folder(incoming)

    assert folders["M 42_sub"] == ("M 42", 2)
    assert folders["NGC 7000_mosaic_sub"] == ("NGC 7000 (mosaic)", 1)
    assert folders["Andromeda"] == ("Andromeda", 1)   # recursive, one level down
    assert folders[""] == (UNSORTED_TARGET_NAME, 1)   # loose in the root
    for skipped in ("M 42", "Moon_video", "Scenery_photo", "batch_stack_tmp"):
        assert skipped not in folders


def test_a_whole_device_container_is_expanded_into_its_children(
        tmp_path: Path) -> None:
    """The "I copied the whole SD card in" shape reports per target, not one
    giant folder — and its folder keys carry the container level, because that
    is how a registered frame's folder is spelled too."""
    incoming = tmp_path / "incoming"
    _fits(incoming / "MyWorks" / "M 31_sub" / "frame_001.fit", 1)
    _fits(incoming / "MyWorks" / "M 31" / "Stacked_30s.fit", 2)
    _fits(incoming / "MyWorks" / "NGC 6888_sub" / "frame_001.fit", 3)

    folders = _by_folder(incoming)

    assert folders["MyWorks/M 31_sub"] == ("M 31", 1)
    assert folders["MyWorks/NGC 6888_sub"] == ("NGC 6888", 1)
    # The device output inside the container is skipped by the same sibling rule.
    assert "MyWorks/M 31" not in folders


def test_a_bare_folder_is_only_skipped_beside_its_own_sub_sibling(
        tmp_path: Path) -> None:
    """The sibling test is parent-scoped in the real convention, and the plan
    inherits that: a root-level ``M 31/`` of real subs must not disappear merely
    because an unrelated container child is called ``M 31_sub``."""
    incoming = tmp_path / "incoming"
    _fits(incoming / "M 31" / "frame_001.fit", 1)
    _fits(incoming / "MyWorks" / "M 31_sub" / "frame_001.fit", 2)
    _fits(incoming / "MyWorks" / "Other_sub" / "frame_001.fit", 3)

    folders = _by_folder(incoming)

    assert folders["M 31"] == ("M 31", 1)
    assert folders["MyWorks/M 31_sub"] == ("M 31", 1)


def test_the_newest_mtime_is_the_folders_own_newest(tmp_path: Path) -> None:
    """A folder's age is what tells "sitting there for days" from "still being
    copied", so it is the newest file in it — recursively."""
    incoming = tmp_path / "incoming"
    _fits(incoming / "M 42_sub" / "frame_001.fit", 1)
    _fits(incoming / "M 42_sub" / "night2" / "frame_002.fit", 2)

    listing = _listing(incoming)
    old, new = sorted(listing)
    listing[old], listing[new] = 1_000.0, 9_000.0

    (unit,) = plan_incoming_units(incoming, listing)
    assert unit.newest_mtime == 9_000.0
    assert unit.n_files == 2


def test_paths_outside_the_root_and_non_fits_are_ignored(tmp_path: Path) -> None:
    """The listing is handed over, not trusted: anything that is not a FITS
    under the root contributes nothing rather than inventing a folder."""
    incoming = tmp_path / "incoming"
    _fits(incoming / "M 42_sub" / "frame_001.fit", 1)
    listing = _listing(incoming)
    listing[str(tmp_path / "elsewhere" / "frame.fit")] = 1.0
    listing[str(incoming / "M 42_sub" / "notes.txt")] = 1.0

    (unit,) = plan_incoming_units(incoming, listing)
    assert (unit.folder, unit.n_files) == ("M 42_sub", 1)


def test_an_empty_listing_plans_nothing(tmp_path: Path) -> None:
    assert plan_incoming_units(tmp_path, {}) == []


def test_the_plan_still_offers_a_calibration_folder_the_scan_skips(
    tmp_path: Path,
) -> None:
    """The one place plan and scan diverge on purpose, pinned rather than left
    to be discovered (v0.455.0).

    The scan passes over a folder whose frames declare themselves darks; that
    verdict comes from *headers*, and the plan may not read any — it runs on
    every watcher poll and its whole value is being path-only. So the plan still
    names it, and the exclusion happens one layer up, in ``webapp.incominglag``,
    off the folder list the Calibration page's build offer already holds.
    """
    from webapp.sample_data import write_sample_calibration_frames

    incoming = tmp_path / "incoming"
    write_sample_calibration_frames(incoming / "Darks 10s", "dark")
    _fits(incoming / "M 42_sub" / "frame_001.fit", 1)

    planned = {u.folder for u in plan_incoming_units(incoming, _listing(incoming))}

    lib = Library.open_or_create(tmp_path / "library")
    try:
        result = scan_and_organize(lib, incoming, copy_to_cache=False)
    finally:
        lib.close()

    assert planned == {"Darks 10s", "M 42_sub"}
    assert [t.target_name for t in result.targets] == ["M 42"]
    assert [s.target_name for s in result.skipped_calibration_folders] \
        == ["Darks 10s"]
