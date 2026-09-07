"""My wishlist — the pure engine half plus its registry storage.

The wishlist is the one place the owner's *own* intent ("I want to shoot M31
next") is recorded, so two things matter more than anything else here: it must
survive an in-place upgrade of an existing library (§9), and "have I captured
this?" must mean exactly what it means on the life list.
"""

from __future__ import annotations

import sqlite3

from seestack.io.library import Library
from seestack.lifelist import catalog_capture_status
from seestack.nightplan import CatalogObject, load_catalog
from seestack.wishlist import wishlist_objects, wishlist_summary


class _Target:
    """A duck-typed registry row, as ``catalog_capture_status`` wants it."""

    def __init__(self, name, safe_name, ra, dec, n_frames=6):
        self.name = name
        self.safe_name = safe_name
        self.ra_deg = ra
        self.dec_deg = dec
        self.n_frames = n_frames


class _Saved:
    """A duck-typed wishlist row."""

    def __init__(self, catalog_id, added_utc, name="", ra=None, dec=None):
        self.catalog_id = catalog_id
        self.added_utc = added_utc
        self.name = name
        self.ra_deg = ra
        self.dec_deg = dec


M31 = (10.6847, 41.2687)
M42 = (83.822, -5.391)


# ---- storage (the upgrade-safety half) ---------------------------------


def test_a_fresh_library_starts_with_an_empty_wishlist(tmp_path):
    lib = Library.create(tmp_path / "lib")
    try:
        assert lib.list_wishlist() == []
    finally:
        lib.close()


def test_saving_and_unsaving_round_trips(tmp_path):
    lib = Library.create(tmp_path / "lib")
    try:
        lib.add_to_wishlist("M31", name="Andromeda Galaxy", ra_deg=M31[0], dec_deg=M31[1])
        lib.add_to_wishlist("M42", name="Orion Nebula", ra_deg=M42[0], dec_deg=M42[1])
        saved = lib.list_wishlist()
        assert [s.catalog_id for s in saved] == ["M31", "M42"]
        assert saved[0].name == "Andromeda Galaxy"
        assert saved[0].ra_deg == M31[0]

        assert lib.remove_from_wishlist("M31") is True
        assert [s.catalog_id for s in lib.list_wishlist()] == ["M42"]
        # Removing something already gone is a no-op, not an error — the star is
        # a toggle and two tabs can both untick it.
        assert lib.remove_from_wishlist("M31") is False
    finally:
        lib.close()


def test_re_saving_keeps_the_original_place_in_the_list(tmp_path):
    """A double-tap on the star must not shuffle the queue the owner built."""
    lib = Library.create(tmp_path / "lib")
    try:
        lib.add_to_wishlist("M31", name="Andromeda Galaxy", ra_deg=M31[0], dec_deg=M31[1])
        first_added = lib.list_wishlist()[0].added_utc
        lib.add_to_wishlist("M42", name="Orion Nebula", ra_deg=M42[0], dec_deg=M42[1])
        # Re-add the first one; it stays first, with its original timestamp.
        again = lib.add_to_wishlist("M31", name="Andromeda Galaxy",
                                    ra_deg=M31[0], dec_deg=M31[1])
        assert again.added_utc == first_added
        # Two rows, not three — the re-add updated in place.
        assert [s.catalog_id for s in lib.list_wishlist()] == ["M31", "M42"]
    finally:
        lib.close()


def test_an_old_library_gains_the_wishlist_table_on_open(tmp_path):
    """The live-install invariant (§9): a registry written by a build that had
    never heard of the wishlist must gain the table on open, with no data loss
    and no schema-version bump (a bump would make the *previous* Docker image
    refuse to open the library, turning a rollback into a bricked install)."""
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
        assert lib.list_wishlist() == []
        lib.add_to_wishlist("M42", name="Orion Nebula", ra_deg=M42[0], dec_deg=M42[1])
        assert [s.catalog_id for s in lib.list_wishlist()] == ["M42"]
        # The pre-existing target survived the open untouched.
        assert [t.safe_name for t in lib.list_targets()] == ["M_31"]
    finally:
        lib.close()


def test_a_current_library_written_without_the_table_self_heals(tmp_path):
    """Belt and braces: the table is created on *every* open, so a registry
    already stamped at the current version but missing it (a library last
    touched by a build between the version freeze and this feature) is repaired
    rather than raising ``no such table`` on the first page load."""
    root = tmp_path / "lib"
    lib = Library.create(root)
    try:
        lib._conn.execute("DROP TABLE wishlist")
    finally:
        lib.close()

    lib = Library.open(root)
    try:
        assert lib.list_wishlist() == []
    finally:
        lib.close()


# ---- resolution (the pure half) ----------------------------------------


def test_saved_objects_resolve_against_the_bundled_catalog():
    catalog = load_catalog()
    out = wishlist_objects(
        [_Saved("M31", "2026-01-01T00:00:00Z"), _Saved("M42", "2026-01-02T00:00:00Z")],
        catalog, [],
    )
    assert [o.catalog_id for o in out] == ["M31", "M42"]
    assert out[0].name == "Andromeda Galaxy"
    assert out[0].con == "And"
    # Nothing captured, and every field came from the live catalog rather than
    # the row's snapshot.
    assert all(o.captured is False and o.from_snapshot is False for o in out)


def test_the_list_keeps_the_order_the_owner_built_it_in():
    """Not catalog order: this is a personal queue, and re-sorting it into
    Messier order would silently discard the one thing the owner expressed."""
    catalog = load_catalog()
    out = wishlist_objects(
        [_Saved("M42", "2026-01-01T00:00:00Z"), _Saved("M31", "2026-01-02T00:00:00Z")],
        catalog, [],
    )
    assert [o.catalog_id for o in out] == ["M42", "M31"]


def test_capture_status_matches_the_life_lists_own_verdict():
    """The two screens must never disagree about whether you've got M31."""
    catalog = load_catalog()
    targets = [_Target("M 31", "M_31", *M31)]
    out = wishlist_objects([_Saved("M31", "2026-01-01T00:00:00Z")], catalog, targets)
    assert out[0].captured is True
    assert out[0].safe_name == "M_31"
    assert out[0].target_name == "M 31"

    life = {e.catalog_id: e for e in catalog_capture_status(catalog, targets)}
    assert life["M31"].captured is True
    assert life["M31"].safe_name == out[0].safe_name


def test_an_unsolved_or_empty_target_does_not_count_as_captured():
    catalog = load_catalog()
    # A registered target with frames but no plate solution, and one solved but
    # with nothing in it — neither is "I have a picture of this".
    targets = [_Target("M 31", "M_31", None, None), _Target("M 42", "M_42", *M42, n_frames=0)]
    out = wishlist_objects(
        [_Saved("M31", "2026-01-01T00:00:00Z"), _Saved("M42", "2026-01-02T00:00:00Z")],
        catalog, targets,
    )
    assert [o.captured for o in out] == [False, False]


def test_an_id_the_catalog_no_longer_knows_survives_from_its_snapshot():
    """A catalog revision must never silently delete something the owner asked
    for — the row is rebuilt from the position stored beside it and flagged."""
    catalog = [CatalogObject(id="M42", name="Orion Nebula", ra_deg=M42[0],
                             dec_deg=M42[1], type="nebula", con="Ori")]
    out = wishlist_objects(
        [_Saved("OLD1", "2026-01-01T00:00:00Z", name="Someone's Object",
                ra=M31[0], dec=M31[1]),
         _Saved("M42", "2026-01-02T00:00:00Z")],
        catalog, [_Target("M 31", "M_31", *M31)],
    )
    assert [o.catalog_id for o in out] == ["OLD1", "M42"]
    assert out[0].from_snapshot is True
    assert out[0].name == "Someone's Object"
    # It is still matched against the library like anything else.
    assert out[0].captured is True
    assert out[1].from_snapshot is False


def test_a_snapshot_row_with_no_position_is_the_one_thing_dropped():
    """Every planning surface is coordinate-based, so a row with no position is
    unusable — but the add path never writes one, so this is defence only."""
    out = wishlist_objects([_Saved("GHOST", "2026-01-01T00:00:00Z")], [], [])
    assert out == []


def test_the_summary_counts_saved_and_captured():
    catalog = load_catalog()
    out = wishlist_objects(
        [_Saved("M31", "2026-01-01T00:00:00Z"), _Saved("M42", "2026-01-02T00:00:00Z")],
        catalog, [_Target("M 31", "M_31", *M31)],
    )
    assert wishlist_summary(out) == {"saved": 2, "captured": 1}
    assert wishlist_summary([]) == {"saved": 0, "captured": 0}
