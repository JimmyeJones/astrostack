"""Library.rename_target — give a folder-named target the name it deserves.

A rename edits the *display name* only. The safe name, the folder, the project
database and every stored path stay exactly where they were, because everything
in the app resolves a target by its safe name — so these tests mostly assert
what a rename must **not** move.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from seestack.io.library import Library


def _lib(tmp_path: Path) -> Library:
    return Library.open_or_create(tmp_path / "library")


def test_rename_changes_the_label_and_nothing_else(tmp_path: Path):
    lib = _lib(tmp_path)
    try:
        entry, proj = lib.create_target("NGC 6888_SUB")
        proj.close()
        safe, target_dir = entry.safe_name, lib.target_dir(entry)
        assert target_dir.is_dir()

        renamed = lib.rename_target(safe, "Crescent Nebula")
        assert renamed is not None
        assert renamed.name == "Crescent Nebula"
        # The folder is the identity — it must not move, or every stored path
        # (previews, stacks, masters) would point at nothing.
        assert renamed.safe_name == safe
        assert lib.target_dir(renamed) == target_dir
        assert target_dir.is_dir()
        # Reachable by the new name and by the unchanged safe name; the old
        # display name is gone, which is the point.
        assert lib.find_target(safe) is not None
        assert lib.find_target("Crescent Nebula") is not None
        assert lib.find_target("NGC 6888_SUB") is None
        # The project's own name meta follows, so a stack written after the
        # rename carries the new name.
        proj = lib.open_target(safe)
        try:
            assert proj.get_meta("name") == "Crescent Nebula"
        finally:
            proj.close()
    finally:
        lib.close()


def test_rename_survives_a_reopen_and_a_rescan_of_the_same_folder(tmp_path: Path):
    """The scanner re-offers the *folder* name on every scan. A rename that a
    rescan silently undid would be worse than no rename at all."""
    lib = _lib(tmp_path)
    try:
        entry, proj = lib.create_target("MyWorks_2026-08-14")
        proj.close()
        safe = entry.safe_name
        lib.rename_target(safe, "Orion Nebula")
    finally:
        lib.close()

    lib = _lib(tmp_path)
    try:
        assert lib.find_target(safe).name == "Orion Nebula"
        # Exactly what a rescan of the same on-disk folder does.
        again, proj = lib.open_or_create_target("MyWorks_2026-08-14")
        proj.close()
        assert again.safe_name == safe
        assert again.name == "Orion Nebula"
        assert len(lib.list_targets()) == 1
    finally:
        lib.close()


def test_a_mosaic_target_cannot_be_renamed_out_of_being_a_mosaic(tmp_path: Path):
    """Mosaic-ness is carried by the name, so the suffix travels with a rename —
    otherwise a rename would quietly turn a mosaic into a single field for
    everything that groups targets by where they point."""
    from seestack.io.scanner import is_mosaic_target_name

    lib = _lib(tmp_path)
    try:
        entry, proj = lib.create_target("NGC 6888 (mosaic)")
        proj.close()
        renamed = lib.rename_target(entry.safe_name, "Crescent Nebula")
        assert renamed.name == "Crescent Nebula (mosaic)"
        assert is_mosaic_target_name(renamed.name)
        # Idempotent: a caller that already suffixed it doesn't get it twice.
        again = lib.rename_target(entry.safe_name, "Crescent Nebula (mosaic)")
        assert again.name == "Crescent Nebula (mosaic)"
    finally:
        lib.close()


def test_rename_refuses_a_blank_name_or_one_another_target_owns(tmp_path: Path):
    lib = _lib(tmp_path)
    try:
        a, pa = lib.create_target("M 42")
        pa.close()
        b, pb = lib.create_target("Unsorted")
        pb.close()

        with pytest.raises(ValueError):
            lib.rename_target(b.safe_name, "   ")
        with pytest.raises(ValueError):
            lib.rename_target(b.safe_name, "M 42")
        # The refusals changed nothing.
        assert lib.find_target(b.safe_name).name == "Unsorted"
        assert lib.find_target(a.safe_name).name == "M 42"
        # Renaming a target to what it is already called is a no-op, not a clash.
        assert lib.rename_target(a.safe_name, "M 42").name == "M 42"
        # An unknown target reports "no such target" the way update_target does.
        assert lib.rename_target("no_such_target", "M 13") is None
    finally:
        lib.close()


def test_a_library_written_before_the_folder_name_column_renames_cleanly(tmp_path: Path):
    """§9: an existing registry must gain the column on open (additively,
    defaulting to NULL = "never renamed") and be renameable straight away, with
    the folder it came from remembered from that moment on."""
    import sqlite3

    root = tmp_path / "lib"
    (root / "targets" / "NGC_6888_SUB").mkdir(parents=True)
    con = sqlite3.connect(root / "library.sqlite")
    con.executescript(
        """
        PRAGMA user_version = 5;
        CREATE TABLE library_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE targets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE, safe_name TEXT NOT NULL UNIQUE,
            ra_deg REAL, dec_deg REAL, created_utc TEXT NOT NULL,
            last_activity_utc TEXT, n_frames INTEGER NOT NULL DEFAULT 0,
            n_frames_accepted INTEGER NOT NULL DEFAULT 0,
            total_exposure_s REAL NOT NULL DEFAULT 0,
            last_stack_preview TEXT, notes TEXT, tags TEXT,
            cover_stack_run_id INTEGER, legacy_mixed_drop INTEGER
        );
        INSERT INTO targets(name, safe_name, created_utc)
            VALUES('NGC 6888_SUB','NGC_6888_SUB','2026-01-01T00:00:00Z');
        """
    )
    con.commit()
    con.close()

    lib = Library.open(root)
    try:
        cols = {r["name"] for r in lib._conn.execute("PRAGMA table_info(targets)")}
        assert "folder_name" in cols
        assert lib.find_target("NGC_6888_SUB").folder_name is None
        renamed = lib.rename_target("NGC_6888_SUB", "Crescent Nebula")
        assert renamed.name == "Crescent Nebula"
        assert renamed.folder_name == "NGC 6888_SUB"
        # …and the folder the pre-upgrade rows came from is still claimed by it.
        assert lib._allocate_safe_name("NGC 6888_SUB") == "NGC_6888_SUB"
    finally:
        lib.close()
