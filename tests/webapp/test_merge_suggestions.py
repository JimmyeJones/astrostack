"""The read-only ``/api/targets/merge-suggestions`` endpoint that powers the
"these look like the same object — combine them?" Library nudge."""

from __future__ import annotations

from pathlib import Path

from seestack.io.library import Library
from seestack.io.project import FrameRow

# M 31 (Andromeda) and, far away, M 42 (Orion). M 32 sits ~0.4° from M 31 —
# close on the sky but a genuinely different target that must NOT be fused.
M31 = (10.685, 41.269)
M32 = (10.674, 40.865)
M42 = (83.82, -5.39)


def _make_target(
    lib: Library, name: str, ra: float, dec: float,
    source_paths: list[Path] | None = None,
) -> str:
    entry, proj = lib.create_target(name, ra_deg=ra, dec_deg=dec)
    try:
        for sp in source_paths or []:
            proj.add_frame(FrameRow(source_path=str(sp), accept=True))
    finally:
        proj.close()
    if source_paths:
        lib.refresh_target_stats(entry.safe_name)
    return entry.safe_name


def test_same_object_split_across_nights_is_suggested(client, data_root: Path):
    lib = Library.open_or_create(data_root / "library")
    try:
        _make_target(lib, "M31 night 1", *M31)
        _make_target(lib, "M31 night 2", M31[0] + 0.01, M31[1] - 0.01)
        _make_target(lib, "M42", *M42)  # lone → no suggestion
    finally:
        lib.close()

    r = client.get("/api/targets/merge-suggestions")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    sug = body[0]
    safes = {t["safe"] for t in sug["targets"]}
    assert safes == {"M31_night_1", "M31_night_2"}
    # Named from the offline catalog by its plate-solved centre (common name or
    # catalog id — best-effort, so just assert we got a friendly non-empty label).
    assert isinstance(sug["object_name"], str) and sug["object_name"]
    assert sug["max_sep_arcmin"] < 6.0  # both within the 0.1° (6′) tolerance


def test_distinct_nearby_objects_are_not_suggested(client, data_root: Path):
    lib = Library.open_or_create(data_root / "library")
    try:
        _make_target(lib, "M31", *M31)
        _make_target(lib, "M32", *M32)  # ~0.4° away — a different object
    finally:
        lib.close()

    r = client.get("/api/targets/merge-suggestions")
    assert r.status_code == 200
    assert r.json() == []


def test_no_targets_gives_empty_list(client):
    r = client.get("/api/targets/merge-suggestions")
    assert r.status_code == 200
    assert r.json() == []


def test_targets_without_a_solved_centre_are_ignored(client, data_root: Path):
    lib = Library.open_or_create(data_root / "library")
    try:
        _make_target(lib, "M31 night 1", *M31)
        _make_target(lib, "M31 night 2", M31[0] + 0.01, M31[1])
        # An un-plate-solved target (no RA/Dec) must never appear in a group.
        _entry, proj = lib.create_target("Unknown field")
        proj.close()
    finally:
        lib.close()

    r = client.get("/api/targets/merge-suggestions")
    body = r.json()
    assert len(body) == 1
    safes = {t["safe"] for t in body[0]["targets"]}
    assert "Unknown_field" not in safes


# --- known duplicates must never be offered as a merge ----------------------
# Owner-reported (2026-08-31, with a screenshot): the nudge offered to "combine"
# a target with its own leftover ``<T>_sub`` duplicate — the *same physical
# files* under two folder spellings — called it "shot on separate nights", and
# summed the same integration twice ("64 h total" over ~31 h of real data).
# Position clustering alone cannot see this; the two spellings sit at identical
# coordinates, so they always cluster. Cleanup-suggestions already calls the
# same pair a duplicate, so the two features contradicted each other.


def test_a_sub_named_duplicate_is_not_offered_as_a_merge_partner(
    client, data_root: Path,
):
    """The owner's ``M 13`` / ``M 13_SUB`` shape: the base holds the ``_sub``
    folder's frames *plus* the on-device output ones, so the duplicate adds
    nothing. The group collapses to one real member and must vanish — the
    correct nudge for it is the cleanup card, not a merge."""
    subs = data_root / "dump" / "M 13_sub"
    sub_frames = [subs / f"Light_{i:03d}.fit" for i in range(10)]
    output = data_root / "dump" / "M 13"

    lib = Library.open_or_create(data_root / "library")
    try:
        # The base target the convention now builds: the raw subs, plus the two
        # on-device output images that make its count slightly higher.
        _make_target(lib, "M 13", *M31,
                     source_paths=[*sub_frames, output / "Stacked.fit"])
        # The leftover duplicate a pre-v0.184.9 scan left behind.
        _make_target(lib, "M 13_sub", M31[0] + 0.001, M31[1],
                     source_paths=sub_frames)
    finally:
        lib.close()

    assert client.get("/api/targets/merge-suggestions").json() == []


def test_two_real_folders_of_the_same_object_are_still_offered(
    client, data_root: Path,
):
    """The guard must be evidence-based, not name-based. The owner also has
    ``NGC 6888`` (4815 subs) beside ``NGC 6888_SUB`` (3110) — different frame
    counts, so possibly two genuinely different folders. When the base does NOT
    already own every one of the other's frames, this is a real merge candidate
    and the nudge must still appear, with both members' hours summed."""
    subs = data_root / "dump" / "NGC 6888_sub"
    other = data_root / "dump" / "NGC 6888"

    lib = Library.open_or_create(data_root / "library")
    try:
        _make_target(lib, "NGC 6888", *M31,
                     source_paths=[other / f"Light_{i:03d}.fit" for i in range(6)])
        _make_target(lib, "NGC 6888_sub", M31[0] + 0.001, M31[1],
                     source_paths=[subs / f"Light_{i:03d}.fit" for i in range(4)])
    finally:
        lib.close()

    body = client.get("/api/targets/merge-suggestions").json()
    assert len(body) == 1
    assert {t["safe"] for t in body[0]["targets"]} == {
        "NGC_6888", "NGC_6888_sub"}


def test_a_mosaic_sub_duplicate_is_not_offered_as_a_merge_partner(
    client, data_root: Path,
):
    """The same for a mosaic, whose duplicate's base is the ``<T> (mosaic)``
    target — not the single-field ``<T>``, whose footprint differs. The owner
    has three of these (``M 3_MOSAIC_SUB``, ``M 44_MOSAIC_SUB``,
    ``NGC 6960_MOSAIC_SUB``), each shown beside its own twin."""
    subs = data_root / "dump" / "M 44_mosaic_sub"
    frames = [subs / f"Light_{i:03d}.fit" for i in range(8)]

    lib = Library.open_or_create(data_root / "library")
    try:
        _make_target(lib, "M 44 (mosaic)", *M31, source_paths=frames)
        _make_target(lib, "M 44_mosaic_sub", M31[0] + 0.001, M31[1],
                     source_paths=frames)
    finally:
        lib.close()

    assert client.get("/api/targets/merge-suggestions").json() == []


def test_a_real_third_folder_survives_when_a_duplicate_is_dropped(
    client, data_root: Path,
):
    """Dropping the duplicate must not take the whole group with it when a
    genuine second folder is also there: the remaining two are still a real
    merge, and the headline integration now sums only unique data."""
    subs = data_root / "dump" / "M 101_sub"
    sub_frames = [subs / f"Light_{i:03d}.fit" for i in range(10)]
    night2 = data_root / "dump" / "M 101 night 2"

    lib = Library.open_or_create(data_root / "library")
    try:
        _make_target(lib, "M 101", *M31, source_paths=sub_frames)
        _make_target(lib, "M 101_sub", M31[0] + 0.001, M31[1],
                     source_paths=sub_frames)
        _make_target(lib, "M 101 night 2", M31[0] + 0.002, M31[1],
                     source_paths=[night2 / f"Light_{i:03d}.fit" for i in range(5)])
    finally:
        lib.close()

    body = client.get("/api/targets/merge-suggestions").json()
    assert len(body) == 1
    assert {t["safe"] for t in body[0]["targets"]} == {"M_101", "M_101_night_2"}


# --- and never offer a merge the rest of the app already refuses -------------


def test_a_mosaic_is_not_offered_beside_the_single_field_of_the_same_object(
    client, data_root: Path,
):
    """``_apply_seestar_convention`` keeps ``<T> (mosaic)`` and ``<T>`` as two
    targets precisely because their canvases differ — "never co-stacked or
    auto-merged". They point at the same place, so position clustering fused them
    anyway and the nudge offered exactly that merge."""
    lib = Library.open_or_create(data_root / "library")
    try:
        _make_target(lib, "M 44", *M31,
                     source_paths=[data_root / "dump" / "M 44_sub" / "a.fit"])
        _make_target(lib, "M 44 (mosaic)", M31[0] + 0.001, M31[1],
                     source_paths=[data_root / "dump" / "M 44_mosaic_sub" / "b.fit"])
    finally:
        lib.close()

    assert client.get("/api/targets/merge-suggestions").json() == []


def test_two_mosaics_of_the_same_object_are_still_offered(client, data_root: Path):
    """Splitting the populations must not make mosaics unmergeable: two mosaic
    folders of one object share a canvas and are a real merge."""
    lib = Library.open_or_create(data_root / "library")
    try:
        _make_target(lib, "M 44 (mosaic)", *M31,
                     source_paths=[data_root / "dump" / "M 44_mosaic_sub" / "a.fit"])
        _make_target(lib, "M 44 night 2 (mosaic)", M31[0] + 0.001, M31[1],
                     source_paths=[data_root / "dump" / "M 44b_mosaic_sub" / "b.fit"])
    finally:
        lib.close()

    body = client.get("/api/targets/merge-suggestions").json()
    assert len(body) == 1
    assert len(body[0]["targets"]) == 2


def test_a_junk_on_device_output_is_not_offered_as_a_merge_partner(
    client, data_root: Path,
):
    """The Seestar's own stacked output sits at the same coordinates as the subs
    it came from, so it clustered with them — and the app offered to *combine* a
    target the cleanup card was simultaneously offering to *delete*."""
    incoming = data_root / "dump"
    (incoming / "M 31_sub").mkdir(parents=True)
    output = incoming / "M 31"
    output.mkdir()

    lib = Library.open_or_create(data_root / "library")
    try:
        _make_target(lib, "M 31", *M31, source_paths=[output / "Stacked.fit"])
        _make_target(lib, "M 31 night 2", M31[0] + 0.001, M31[1],
                     source_paths=[incoming / "M 31 night 2" / "Light_001.fit"])
    finally:
        lib.close()

    assert client.get("/api/targets/merge-suggestions").json() == []


def test_the_owners_m3_card_produces_no_suggestion_at_all(client, data_root: Path):
    """End to end on the shape from the owner's screenshot. Their M 3 card listed
    five targets and headlined "64 h total" over ~31 h of real data. Every one of
    the five is either a duplicate of another, the on-device output, or a mosaic
    that must not be fused with the single field — so the honest answer is no
    merge nudge, and three cleanup nudges instead."""
    incoming = data_root / "dump"
    (incoming / "M 3_sub").mkdir(parents=True)
    (incoming / "M 3_mosaic_sub").mkdir()
    (incoming / "M 3_mosaic").mkdir()
    subs = [incoming / "M 3_sub" / f"Light_{i:03d}.fit" for i in range(20)]
    mosaic_subs = [incoming / "M 3_mosaic_sub" / f"Light_{i:03d}.fit" for i in range(9)]

    lib = Library.open_or_create(data_root / "library")
    try:
        _make_target(lib, "M 3", *M31,
                     source_paths=[*subs, incoming / "M 3" / "Stacked.fit"])
        _make_target(lib, "M 3_sub", M31[0] + 0.001, M31[1], source_paths=subs)
        _make_target(lib, "M 3 (mosaic)", M31[0] + 0.002, M31[1],
                     source_paths=mosaic_subs)
        _make_target(lib, "M 3_mosaic_sub", M31[0] + 0.001, M31[1] + 0.001,
                     source_paths=mosaic_subs)
        _make_target(lib, "M 3_mosaic", M31[0], M31[1] + 0.002,
                     source_paths=[incoming / "M 3_mosaic" / "Stacked.fit"])
    finally:
        lib.close()

    assert client.get("/api/targets/merge-suggestions").json() == []
    # The three leftovers are all reachable by the cleanup nudge instead. (Keyed
    # by display name: "M 3 (mosaic)" and "M 3_mosaic" both want the safe name
    # "M_3_mosaic", so the library suffixes the second one.)
    cleanup = {s["name"]: s["reason"]
               for s in client.get("/api/targets/cleanup-suggestions").json()}
    assert cleanup == {
        "M 3_sub": "duplicate_sub",
        "M 3_mosaic_sub": "duplicate_sub",
        "M 3_mosaic": "on_device_output",
    }
