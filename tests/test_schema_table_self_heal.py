"""A whole table lost from a *current-version* DB heals on open — both stores.

``Project._reconcile_table_columns`` and ``Library._ensure_columns`` repair a
missing **column** on every open (the v0.119.8 live-install brick — see
``tests/test_project_schema_drift.py``), and both skipped a table that was absent
entirely with the same comment: *"handled by the base-schema recreate"*. That
recreate only ran when the stamped ``user_version`` was **behind**
(``Project._migrate_schema`` / ``Library._check_schema``'s older-version branch),
so for a DB already stamped *current* it never ran at all: the open succeeded,
every read of the lost table raised ``no such table``, and nothing ever healed
it. That is the shape ``tests/webapp/test_sky_broken_project.py`` had to build by
hand, and it needs no image rollback to reach — one bad block, a power loss
mid-write or a partially-restored copy is enough.

The two halves are not equally bad. A project missing ``stack_runs`` costs one
target; a **registry** missing ``targets`` costs the whole app, because every page
starts from ``list_targets()``. So the registry heal also re-adopts the target
folders still on disk — exactly what ``Library.open`` already does when the
registry *file* is missing, which is the same situation with the same remedy.

Both heals are additive: ``CREATE TABLE IF NOT EXISTS`` from the authoritative
schema, no ``SCHEMA_VERSION`` bump (so a rollback to the previous image still
opens the DB — AGENTS.md §9), and no row is ever dropped or rewritten. A healthy
open pays one ``sqlite_master`` read and writes nothing, which is why it can run
unconditionally.
"""

from __future__ import annotations

import sqlite3

from seestack.io.library import LIBRARY_SCHEMA_VERSION, Library
from seestack.io.project import SCHEMA_VERSION, FrameRow, Project, StackRunRow


def _run(basename: str) -> StackRunRow:
    return StackRunRow(
        id=None, timestamp_utc="2026-05-01T00:00:00Z", output_basename=basename,
        fits_path=None, tiff_path=None, preview_path=None, n_frames_used=9,
        canvas_h=10, canvas_w=10, coverage_min=0, coverage_max=9,
        options_json="{}",
    )


def _drop(db_path, table: str, *, expect_version: int) -> None:
    """Drop one table and assert the DB is left stamped *current*.

    The version assertion is the whole point: at an older version both stores
    already rebuild the base schema, so a fixture that quietly left the version
    behind would prove a path that was never broken.
    """
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(f"DROP TABLE {table}")
        conn.commit()
        assert conn.execute("PRAGMA user_version").fetchone()[0] == expect_version
    finally:
        conn.close()


# ---- the per-target project DB ---------------------------------------------

def test_a_project_missing_stack_runs_heals_on_open(tmp_path):
    """The exact shape the Sky guards were written for: reads raised forever."""
    proj_dir = tmp_path / "t"
    proj = Project.create(proj_dir, name="M 42")
    try:
        fid = proj.add_frame(FrameRow(source_path="a.fit"))
        proj.add_stack_run(_run("m"))
    finally:
        proj.close()

    _drop(proj_dir / "project.sqlite", "stack_runs",
          expect_version=SCHEMA_VERSION)

    proj = Project.open(proj_dir)
    try:
        # No raise, and the table is usable again rather than merely present.
        assert list(proj.iter_stack_runs()) == []
        new_id = proj.add_stack_run(_run("m2"))
        assert [r.output_basename for r in proj.iter_stack_runs()] == ["m2"]
        assert new_id is not None
        # The untouched table kept its rows: healing is additive, never a reset.
        assert proj.get_frame(fid) is not None
        assert proj.count() == 1
    finally:
        proj.close()


def test_a_project_missing_project_meta_heals_on_open(tmp_path):
    """``project_meta`` is excluded from the column reconcile (it is a static
    key/value store), so nothing watched it at all."""
    proj_dir = tmp_path / "t"
    proj = Project.create(proj_dir, name="M 42")
    try:
        proj.add_frame(FrameRow(source_path="a.fit"))
    finally:
        proj.close()

    _drop(proj_dir / "project.sqlite", "project_meta",
          expect_version=SCHEMA_VERSION)

    proj = Project.open(proj_dir)
    try:
        assert proj.get_meta("name") is None   # the value is gone with the table
        proj.set_meta("name", "M 42")          # but the store works again
        assert proj.get_meta("name") == "M 42"
        assert proj.count() == 1
    finally:
        proj.close()


def test_a_healthy_project_open_recreates_nothing(tmp_path):
    """The heal must be free on every ordinary open — it is on the path every
    cross-target page pays once per target."""
    proj_dir = tmp_path / "t"
    Project.create(proj_dir, name="M 42").close()
    proj = Project.open(proj_dir)
    try:
        assert proj._recreate_missing_tables() == set()
    finally:
        proj.close()


class _RefusingConn:
    """A connection whose every statement raises, like a DB whose schema page is
    the damaged one."""

    def execute(self, *_a, **_k):
        raise sqlite3.DatabaseError("database disk image is malformed")

    def executescript(self, *_a, **_k):
        raise sqlite3.DatabaseError("database disk image is malformed")


def test_a_project_whose_schema_cannot_be_read_is_left_exactly_as_it_was(tmp_path):
    """A self-heal must never turn an open that works into one that raises.

    ``_reconcile_table_columns`` already promises that for its ``ALTER``s ("never
    let reconciliation itself fail an open"); the table heal adds one
    ``sqlite_master`` read, which is one more read a damaged DB can refuse — and
    the four cross-target walks and the three Sky guards (v0.492.22/.23) are what
    handle the picture from there.
    """
    proj_dir = tmp_path / "t"
    Project.create(proj_dir, name="M 42").close()
    proj = Project.open(proj_dir)
    try:
        real, proj._conn = proj._conn, _RefusingConn()
        try:
            assert proj._recreate_missing_tables() == set()
        finally:
            proj._conn = real
    finally:
        proj.close()


def test_a_registry_whose_schema_cannot_be_read_is_left_exactly_as_it_was(tmp_path):
    """The registry half of the same promise."""
    root = tmp_path / "lib"
    Library.create(root).close()
    lib = Library.open(root)
    try:
        real, lib._conn = lib._conn, _RefusingConn()
        try:
            assert lib._recreate_missing_tables() == set()
        finally:
            lib._conn = real
    finally:
        lib.close()


# ---- the library registry --------------------------------------------------

def test_a_library_missing_targets_heals_and_re_adopts_the_folders(tmp_path):
    """The whole-app case: without ``targets`` every page starts with a raise."""
    root = tmp_path / "lib"
    lib = Library.create(root)
    try:
        for name in ("M 42", "NGC 7000"):
            _entry, proj = lib.create_target(name)
            try:
                proj.add_frame(FrameRow(source_path=f"{name}.fit"))
            finally:
                proj.close()
        assert sorted(t.safe_name for t in lib.list_targets()) == ["M_42", "NGC_7000"]
    finally:
        lib.close()

    _drop(root / "library.sqlite", "targets",
          expect_version=LIBRARY_SCHEMA_VERSION)

    lib = Library.open(root)
    try:
        # Healed *and* repopulated from the folders that are still on disk —
        # the registry is a derived index, the target folders are the data.
        assert sorted(t.safe_name for t in lib.list_targets()) == ["M_42", "NGC_7000"]
        assert sorted(t.name for t in lib.list_targets()) == ["M 42", "NGC 7000"]
        assert lib.find_target("M_42") is not None
    finally:
        lib.close()


def test_a_library_missing_library_meta_heals_on_open(tmp_path):
    root = tmp_path / "lib"
    Library.create(root).close()

    _drop(root / "library.sqlite", "library_meta",
          expect_version=LIBRARY_SCHEMA_VERSION)

    lib = Library.open(root)
    try:
        assert lib.get_meta("last_scan_root") is None
        lib.set_meta("last_scan_root", "/data/incoming")
        assert lib.get_meta("last_scan_root") == "/data/incoming"
    finally:
        lib.close()


def test_a_healthy_library_open_recreates_nothing(tmp_path):
    root = tmp_path / "lib"
    Library.create(root).close()
    lib = Library.open(root)
    try:
        assert lib._recreate_missing_tables() == set()
    finally:
        lib.close()
