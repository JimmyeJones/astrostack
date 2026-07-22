"""Target tags/notes: update_target round-trip + the additive column migration."""

from __future__ import annotations

import sqlite3

import pytest

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


def test_open_closes_the_connection_when_schema_check_fails(tmp_path, monkeypatch):
    """A newer on-disk registry ``user_version`` makes ``_check_schema`` raise;
    ``Library.open`` must close the connection it opened before propagating,
    rather than leak it (the classmethod never returns the instance on this
    path, so no caller can clean it up)."""
    from seestack.io import library as library_mod
    from seestack.io.library import LIBRARY_SCHEMA_VERSION

    root = tmp_path / "lib"
    lib = Library.create(root)
    # Stamp a registry version this build is too old to open.
    lib._conn.execute(f"PRAGMA user_version = {LIBRARY_SCHEMA_VERSION + 1}")
    lib.close()

    opened: list[sqlite3.Connection] = []
    real_connect = sqlite3.connect

    def tracking_connect(*args, **kwargs):
        conn = real_connect(*args, **kwargs)
        opened.append(conn)
        return conn

    monkeypatch.setattr(library_mod.sqlite3, "connect", tracking_connect)

    with pytest.raises(RuntimeError, match="newer than this Seestack"):
        Library.open(root)

    assert opened, "expected _open to have created a connection"
    with pytest.raises(sqlite3.ProgrammingError):
        opened[-1].execute("SELECT 1")


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


def test_old_library_missing_a_non_tags_column_is_self_healed(tmp_path):
    """The generic column reconcile must backfill ANY missing targets column,
    not just ``tags`` — so a future additive column can never strand an old
    library (the §9 live-in-place-upgrade invariant). ``_row_to_target`` reads
    ``last_stack_preview``/``notes`` by name with no guard, so a registry missing
    one would raise IndexError on ``list_targets`` without the self-heal."""
    root = tmp_path / "lib"
    root.mkdir()
    (root / "targets").mkdir()
    db = root / "library.sqlite"
    # A version-stamped-but-incomplete registry: current user_version, but a
    # targets table missing three columns the authoritative schema declares
    # (last_stack_preview, notes, tags) and with no explicit ALTER for them —
    # exactly the "future column reached the base schema without a migration"
    # gap the generic reconcile exists to repair.
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
            total_exposure_s REAL NOT NULL DEFAULT 0
        );
        INSERT INTO targets(name, safe_name, created_utc)
            VALUES('M 42','M_42','2026-01-01T00:00:00Z');
        """
    )
    con.commit()
    con.close()

    lib = Library.open(root)
    try:
        cols = {r["name"] for r in lib._conn.execute("PRAGMA table_info(targets)")}
        # Every authoritative column is now present, not only tags.
        for want in ("last_stack_preview", "notes", "tags"):
            assert want in cols, want
        # And the library opens + lists cleanly (the IndexError-on-list_targets
        # brick the reconcile prevents), with backfilled columns defaulting.
        targets = lib.list_targets()
        assert [t.safe_name for t in targets] == ["M_42"]
        assert targets[0].last_stack_preview is None
        assert targets[0].notes is None
        assert targets[0].tags == []
    finally:
        lib.close()
