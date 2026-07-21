"""Target "cover" pin: set/clear round-trip + the additive column migration.

The cover lets a user pin their favourite stack run as a target's showcase
image instead of the app always showing the newest stack. It is stored as a
nullable ``cover_stack_run_id`` on the library ``targets`` table.
"""

from __future__ import annotations

import sqlite3

from seestack.io.library import Library


def _create_target(lib: Library, name: str):
    entry, proj = lib.create_target(name)
    proj.close()
    return entry


def test_set_and_clear_cover_round_trip(tmp_path):
    lib = Library.create(tmp_path / "lib")
    try:
        _create_target(lib, "M 31")
        # Default: unpinned.
        assert lib.find_target("M_31").cover_stack_run_id is None

        out = lib.set_target_cover("M_31", 7)
        assert out is not None and out.cover_stack_run_id == 7
        assert lib.find_target("M_31").cover_stack_run_id == 7

        # Re-pin a different run.
        assert lib.set_target_cover("M_31", 12).cover_stack_run_id == 12

        # Clear (back to "newest").
        assert lib.set_target_cover("M_31", None).cover_stack_run_id is None
        assert lib.find_target("M_31").cover_stack_run_id is None
    finally:
        lib.close()


def test_set_cover_on_missing_target_returns_none(tmp_path):
    lib = Library.create(tmp_path / "lib")
    try:
        assert lib.set_target_cover("nope", 3) is None
    finally:
        lib.close()


def test_old_library_without_cover_column_is_migrated(tmp_path):
    """A registry created before the cover column existed must gain it on open,
    so a live in-place upgrade never strands an old library (§9)."""
    root = tmp_path / "lib"
    root.mkdir()
    (root / "targets").mkdir()
    db = root / "library.sqlite"
    # Hand-build a v3-style targets table (through tags, no cover column).
    con = sqlite3.connect(db)
    con.executescript(
        """
        PRAGMA user_version = 3;
        CREATE TABLE library_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE targets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE, safe_name TEXT NOT NULL UNIQUE,
            ra_deg REAL, dec_deg REAL, created_utc TEXT NOT NULL,
            last_activity_utc TEXT, n_frames INTEGER NOT NULL DEFAULT 0,
            n_frames_accepted INTEGER NOT NULL DEFAULT 0,
            total_exposure_s REAL NOT NULL DEFAULT 0,
            last_stack_preview TEXT, notes TEXT, tags TEXT
        );
        INSERT INTO targets(name, safe_name, created_utc)
            VALUES('M 31','M_31','2026-01-01T00:00:00Z');
        """
    )
    con.commit()
    con.close()

    lib = Library.open(root)
    try:
        cols = {r["name"] for r in lib._conn.execute("PRAGMA table_info(targets)")}
        assert "cover_stack_run_id" in cols
        # Old row defaults to unpinned (newest-stack behaviour, unchanged) …
        assert lib.find_target("M_31").cover_stack_run_id is None
        # … and the new column is usable.
        assert lib.set_target_cover("M_31", 5).cover_stack_run_id == 5
    finally:
        lib.close()
