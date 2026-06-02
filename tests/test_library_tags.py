"""Target tags/notes: update_target round-trip + the additive column migration."""

from __future__ import annotations

import sqlite3

from seestack.io.library import Library


def test_update_target_notes_and_tags(tmp_path):
    lib = Library.create(tmp_path / "lib")
    try:
        entry, proj = lib.create_target("M 42")
        proj.close()
        safe = entry.safe_name
        assert entry.tags == [] and entry.notes is None

        out = lib.update_target(safe, notes="great night", tags=["galaxy", "wide", "galaxy"])
        assert out is not None
        assert out.notes == "great night"
        # Duplicates dropped, order preserved.
        assert out.tags == ["galaxy", "wide"]

        # Partial update leaves the untouched field alone.
        out2 = lib.update_target(safe, tags=["nebula"])
        assert out2.notes == "great night"
        assert out2.tags == ["nebula"]

        # Persisted across reopen.
        reread = lib.find_target(safe)
        assert reread.tags == ["nebula"]
    finally:
        lib.close()


def test_update_target_missing_returns_none(tmp_path):
    lib = Library.create(tmp_path / "lib")
    try:
        assert lib.update_target("nope", notes="x") is None
    finally:
        lib.close()


def test_old_library_without_tags_column_is_migrated(tmp_path):
    """A registry created before the tags column existed must gain it on open."""
    root = tmp_path / "lib"
    root.mkdir()
    (root / "targets").mkdir()
    db = root / "library.sqlite"
    # Hand-build a v2-style targets table (no tags column) + user_version=2.
    con = sqlite3.connect(db)
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
        INSERT INTO targets(name, safe_name, created_utc) VALUES('M 31','M_31','2026-01-01T00:00:00Z');
        """
    )
    con.commit()
    con.close()

    lib = Library.open(root)
    try:
        cols = {r["name"] for r in lib._conn.execute("PRAGMA table_info(targets)")}
        assert "tags" in cols
        # And it's usable.
        out = lib.update_target("M_31", tags=["legacy"])
        assert out.tags == ["legacy"]
    finally:
        lib.close()
