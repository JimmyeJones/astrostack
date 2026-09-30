"""A target the owner combined stays combined when the folders are scanned again.

The Seestar writes a new folder per night and ``incoming/`` is strictly
read-only (AGENTS.md §10), so after "Combine into one deep target" both source
folders are still sitting there with every sub in them. Nothing recorded that
they had been combined, so the next whole-incoming scan — the watcher runs one
on any new file, and "Scan now" is one click — re-created the source target from
its folder: the library was split again, ``auto_stack`` re-stacked the shallow
night, and the merge nudge re-offered the identical group. The owner was told
not to use the button until this shipped.

These are that second scan, as a test. The redirect lives in the registry
(``merged_folders``), so nothing under ``incoming/`` is touched to achieve it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("astropy")

from seestack.io.library import Library, TargetEntry
from seestack.io.scanner import scan_and_organize
from tests.synth import write_seestar_fits


def _two_nights(root: Path) -> Path:
    """``incoming/`` with one object in two Seestar folders, as the owner has it.

    ``<T>_sub`` is the Seestar's own naming, and the second night lands in a
    folder of its own — which is exactly what makes two targets out of one
    object.
    """
    root.mkdir(parents=True, exist_ok=True)
    first = root / "M 31_sub"
    first.mkdir()
    for i in range(3):
        write_seestar_fits(first / f"Light_{i:03d}.fit", n_stars=6, seed=10 + i)
    second = root / "M 31_night_2_sub"
    second.mkdir()
    for i in range(2):
        write_seestar_fits(second / f"Light_{i:03d}.fit", n_stars=6, seed=40 + i)
    return root


def _safe_names(lib: Library) -> list[str]:
    return sorted(t.safe_name for t in lib.list_targets())


def test_rescan_after_combine_keeps_one_target(tmp_path):
    incoming = _two_nights(tmp_path / "incoming")
    lib = Library.create(tmp_path / "lib")
    try:
        scan_and_organize(lib, incoming)
        assert _safe_names(lib) == ["M_31", "M_31_night_2"]

        assert lib.merge_targets("M_31", ["M_31_night_2"]) == 2
        assert _safe_names(lib) == ["M_31"]

        # The second scan is the bug: the source folder is still in incoming/.
        scan_and_organize(lib, incoming)
        assert _safe_names(lib) == ["M_31"]

        # And the merged subs are still there exactly once.
        proj = lib.open_target("M_31")
        try:
            assert proj.count(accepted_only=False) == 5
        finally:
            proj.close()
    finally:
        lib.close()


def test_a_new_sub_in_a_combined_folder_lands_in_the_deep_target(tmp_path):
    """The folder is not just ignored — it keeps feeding the target it joined.

    Skipping the folder would be the easy half of this fix and the wrong one: the
    Seestar appends to a night's folder, and a sub that lands after the merge has
    to reach the deep target rather than sit in ``incoming/`` forever.
    """
    incoming = _two_nights(tmp_path / "incoming")
    lib = Library.create(tmp_path / "lib")
    try:
        scan_and_organize(lib, incoming)
        lib.merge_targets("M_31", ["M_31_night_2"])

        late = incoming / "M 31_night_2_sub" / "Light_late.fit"
        write_seestar_fits(late, n_stars=6, seed=99)
        scan_and_organize(lib, incoming)

        assert _safe_names(lib) == ["M_31"]
        proj = lib.open_target("M_31")
        try:
            paths = {Path(f.source_path).name for f in proj.iter_frames(accepted_only=False)}
        finally:
            proj.close()
        assert "Light_late.fit" in paths
    finally:
        lib.close()


def test_combining_the_combined_target_onward_follows_the_chain(tmp_path):
    """A → B → C: the first folder's subs follow B into C, not into a new target."""
    incoming = tmp_path / "incoming"
    incoming.mkdir()
    for n, seed in (("M 31_sub", 10), ("M 31_night_2_sub", 40), ("M 31_night_3_sub", 70)):
        folder = incoming / n
        folder.mkdir()
        write_seestar_fits(folder / "Light_001.fit", n_stars=6, seed=seed)
    lib = Library.create(tmp_path / "lib")
    try:
        scan_and_organize(lib, incoming)
        lib.merge_targets("M_31_night_2", ["M_31"])          # A → B
        lib.merge_targets("M_31_night_3", ["M_31_night_2"])  # B → C
        assert _safe_names(lib) == ["M_31_night_3"]

        scan_and_organize(lib, incoming)
        assert _safe_names(lib) == ["M_31_night_3"]
    finally:
        lib.close()


def test_deleting_the_deep_target_lets_the_folders_come_back(tmp_path):
    """A redirect whose destination is gone is no redirect at all.

    Otherwise deleting the combined target would strand both folders: the scan
    would route them at a target that no longer exists, and the owner's subs
    would have nowhere to land.
    """
    incoming = _two_nights(tmp_path / "incoming")
    lib = Library.create(tmp_path / "lib")
    try:
        scan_and_organize(lib, incoming)
        lib.merge_targets("M_31", ["M_31_night_2"])
        assert lib.delete_target("M_31", remove_files=True) is True

        scan_and_organize(lib, incoming)
        assert _safe_names(lib) == ["M_31", "M_31_night_2"]
    finally:
        lib.close()


def test_a_renamed_source_target_is_still_routed_by_its_folder_name(tmp_path):
    """The scanner re-offers the *folder's* name, not the display name.

    A target renamed after the plate solve worked out what it really is keeps
    answering to its folder name (``TargetEntry.folder_name``), so the redirect
    has to be recorded under that name too or the rename re-opens the bug.
    """
    incoming = _two_nights(tmp_path / "incoming")
    lib = Library.create(tmp_path / "lib")
    try:
        scan_and_organize(lib, incoming)
        lib.rename_target("M_31_night_2", "Andromeda, second night")
        lib.merge_targets("M_31", ["M_31_night_2"])

        scan_and_organize(lib, incoming)
        assert _safe_names(lib) == ["M_31"]
    finally:
        lib.close()


def test_the_redirect_never_shadows_a_live_target(tmp_path):
    """A target that exists under the offered name always wins over a redirect.

    The redirect only ever replaces *minting a new target*, so it can never
    divert subs away from a target the owner is looking at.
    """
    incoming = _two_nights(tmp_path / "incoming")
    lib = Library.create(tmp_path / "lib")
    try:
        scan_and_organize(lib, incoming)
        lib.merge_targets("M_31", ["M_31_night_2"])
        # The owner makes a target of that name again, by hand.
        _entry, proj = lib.create_target("M 31_night_2")
        proj.close()

        scan_and_organize(lib, incoming)
        assert _safe_names(lib) == ["M_31", "M_31_night_2"]
        again = lib.open_target("M_31_night_2")
        try:
            assert again.count(accepted_only=False) == 2
        finally:
            again.close()
    finally:
        lib.close()


def test_an_old_library_gains_the_merged_folders_table_on_open(tmp_path):
    """The live-install invariant (§9): a registry written by a build that had
    never heard of this table gains it on open, with no data loss and no
    schema-version bump — a bump would make the *previous* Docker image refuse to
    open the library, turning a rollback into a bricked install.
    """
    import sqlite3

    root = tmp_path / "lib"
    root.mkdir()
    (root / "targets").mkdir()
    con = sqlite3.connect(root / "library.sqlite")
    con.executescript(
        """
        PRAGMA user_version = 2;
        CREATE TABLE library_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE targets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE, safe_name TEXT NOT NULL UNIQUE,
            ra_deg REAL, dec_deg REAL, created_utc TEXT NOT NULL,
            last_activity_utc TEXT, n_frames INTEGER NOT NULL DEFAULT 0,
            n_frames_accepted INTEGER NOT NULL DEFAULT 0,
            total_exposure_s REAL NOT NULL DEFAULT 0,
            last_stack_preview TEXT, notes TEXT
        );
        INSERT INTO targets(name, safe_name, created_utc)
            VALUES('M 31','M_31','2026-01-01T00:00:00Z');
        """
    )
    con.commit()
    con.close()

    lib = Library.open(root)
    try:
        assert lib.merged_folder_destination("M 31_night_2") is None
        entry = lib.find_target("M_31")
        assert entry is not None
        lib.record_merged_folder(
            TargetEntry(
                id=-1, name="M 31_night_2", safe_name="M_31_night_2",
                ra_deg=None, dec_deg=None, created_utc="2026-01-01T00:00:00Z",
                last_activity_utc=None, n_frames=0, n_frames_accepted=0,
                total_exposure_s=0.0, last_stack_preview=None, notes=None,
            ),
            "M_31",
        )
        assert lib.merged_folder_destination("M 31_night_2") == "M_31"
        # The pre-existing target survived the open untouched.
        assert [t.safe_name for t in lib.list_targets()] == ["M_31"]
    finally:
        lib.close()


def test_a_current_library_written_without_the_table_self_heals(tmp_path):
    """Belt and braces: the table is created on *every* open, so a registry
    already stamped at the current version but missing it is repaired rather
    than raising ``no such table`` on the first scan."""
    root = tmp_path / "lib"
    lib = Library.create(root)
    try:
        lib._conn.execute("DROP TABLE merged_folders")
    finally:
        lib.close()

    lib = Library.open(root)
    try:
        assert lib.merged_folder_destination("anything") is None
    finally:
        lib.close()


# ------------------------------------------------------------------------------
# 2026-09-30 audit, C-F3: the delete that ends a Combine can fail part way (on a
# NAS where the files belong to another local account), and it used to fail
# *silently* — ``rmtree(..., ignore_errors=True)`` — leaving a folder with a
# ``project.sqlite`` under ``targets/``. The next scan then re-adopted that
# unregistered folder *before* consulting the redirect, so the combined-away
# target came back from its own corpse with its stale rows. Two fixes: the
# redirect is asked before an unregistered folder is adopted, and the delete
# says what it could not do. Nothing here touches ``incoming/``.


def _fingerprint(root: Path) -> dict[str, tuple[int, float]]:
    return {str(p.relative_to(root)): (p.stat().st_size, p.stat().st_mtime)
            for p in sorted(root.rglob("*")) if p.is_file()}


def test_a_leftover_source_folder_is_not_adopted_back_by_the_next_scan(tmp_path):
    """The corpse case, staged directly: the merge's delete left the source
    target's folder behind. Fails before: the scan re-adopted it and the
    library split back in two."""
    import shutil

    incoming = _two_nights(tmp_path / "incoming")
    before = _fingerprint(incoming)
    lib = Library.create(tmp_path / "lib")
    try:
        scan_and_organize(lib, incoming)
        # Keep a copy of the source target's folder, then put it back after the
        # merge — exactly what a part-failed delete leaves on disk.
        src_dir = lib.target_dir(lib.find_target("M_31_night_2"))
        corpse = tmp_path / "corpse"
        shutil.copytree(src_dir, corpse)
        lib.merge_targets("M_31", ["M_31_night_2"])
        assert not src_dir.exists()
        shutil.copytree(corpse, src_dir)
        assert (src_dir / "project.sqlite").exists()

        scan_and_organize(lib, incoming)
        assert _safe_names(lib) == ["M_31"]
        # …and the folder is left exactly where it was: not adopted, not touched.
        assert (src_dir / "project.sqlite").exists()

        # A sub landing in that folder later still reaches the deep target.
        write_seestar_fits(incoming / "M 31_night_2_sub" / "Light_late.fit",
                           n_stars=6, seed=99)
        scan_and_organize(lib, incoming)
        assert _safe_names(lib) == ["M_31"]
        proj = lib.open_target("M_31")
        try:
            names = {Path(f.source_path).name for f in proj.iter_frames(accepted_only=False)}
        finally:
            proj.close()
        assert "Light_late.fit" in names
    finally:
        lib.close()
    # AGENTS.md §10: the drop folder is read-only — one addition, nothing else.
    after = _fingerprint(incoming)
    assert set(before) <= set(after)
    assert all(after[k] == before[k] for k in before)
    assert set(after) - set(before) == {"M 31_night_2_sub/Light_late.fit"}


def test_a_delete_that_fails_part_way_is_said_and_the_library_stays_whole(
        tmp_path, monkeypatch, caplog):
    """The merge itself, with the delete refused the way a foreign-owned file
    refuses it. The registry must end consistent (one target, the redirect in
    place), the result must say a folder was left, and the next scan must not
    bring the source back. Fails before: ``ignore_errors=True`` hid the
    failure, ``folders_left`` did not exist, and the scan re-adopted the folder."""
    import logging
    import shutil

    incoming = _two_nights(tmp_path / "incoming")
    before = _fingerprint(incoming)
    lib = Library.create(tmp_path / "lib")
    try:
        scan_and_organize(lib, incoming)
        src_dir = lib.target_dir(lib.find_target("M_31_night_2"))
        real_rmtree = shutil.rmtree

        def refuse(path, *a, **kw):
            if Path(path) == src_dir:
                raise PermissionError(13, "Permission denied", str(path))
            return real_rmtree(path, *a, **kw)

        monkeypatch.setattr(shutil, "rmtree", refuse)
        with caplog.at_level(logging.WARNING, logger="seestack.io.library"):
            result = lib.merge_targets_result("M_31", ["M_31_night_2"])

        assert result.frames_added == 2
        assert result.folders_left == 1
        assert any("could not remove target folder" in r.getMessage()
                   for r in caplog.records)
        assert _safe_names(lib) == ["M_31"]
        assert (src_dir / "project.sqlite").exists()
        assert lib.merged_folder_destination("M 31_night_2") == "M_31"

        scan_and_organize(lib, incoming)
        assert _safe_names(lib) == ["M_31"]
        proj = lib.open_target("M_31")
        try:
            assert proj.count(accepted_only=False) == 5
        finally:
            proj.close()
    finally:
        lib.close()
    assert _fingerprint(incoming) == before


def test_a_merge_whose_delete_succeeds_reports_no_folder_left(tmp_path):
    incoming = _two_nights(tmp_path / "incoming")
    lib = Library.create(tmp_path / "lib")
    try:
        scan_and_organize(lib, incoming)
        result = lib.merge_targets_result("M_31", ["M_31_night_2"])
        assert result.folders_left == 0
        assert not (lib.targets_dir / "M_31_night_2").exists()
    finally:
        lib.close()


def test_deleting_a_target_whose_files_refuse_to_go_still_unregisters_it(
        tmp_path, monkeypatch, caplog):
    """The plain delete path shares the rule: the registry row goes, the
    failure is logged, and nothing raises into the caller."""
    import logging
    import shutil

    lib = Library.create(tmp_path / "lib")
    try:
        entry, proj = lib.create_target("M 31")
        proj.close()
        folder = lib.target_dir(entry)
        monkeypatch.setattr(shutil, "rmtree", lambda *a, **kw: (_ for _ in ()).throw(
            PermissionError(13, "Permission denied")))
        with caplog.at_level(logging.WARNING, logger="seestack.io.library"):
            assert lib.delete_target("M_31", remove_files=True) is True
        assert lib.find_target("M_31") is None
        assert folder.exists()
        assert any("could not remove target folder" in r.getMessage()
                   for r in caplog.records)
    finally:
        lib.close()
