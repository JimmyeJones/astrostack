"""The read-only ``/api/targets/merge-suggestions`` endpoint that powers the
"these look like the same object — combine them?" Library nudge."""

from __future__ import annotations

from pathlib import Path

from seestack.io.library import Library

# M 31 (Andromeda) and, far away, M 42 (Orion). M 32 sits ~0.4° from M 31 —
# close on the sky but a genuinely different target that must NOT be fused.
M31 = (10.685, 41.269)
M32 = (10.674, 40.865)
M42 = (83.82, -5.39)


def _make_target(lib: Library, name: str, ra: float, dec: float) -> None:
    _entry, proj = lib.create_target(name, ra_deg=ra, dec_deg=dec)
    proj.close()


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


# --- the owner's real library shape (2026-08-31 screenshot) ------------------
# Every near-identical pair there is the SAME physical files counted twice: the
# convention now maps "<T>_sub/" to target "<T>", so a re-scan registers those
# subs under "<T>" while the old "<T>_sub"-named target lingers holding the very
# same frames. Position-only clustering had no idea, so the nudge offered to
# "combine" a target with its own duplicate, called it separate nights, and
# summed the integration twice ("64 h total" for ~31 h of real data).


def _target_with_frames(
    lib: Library,
    name: str,
    ra: float,
    dec: float,
    paths: list[Path],
    exposure_s: float = 10.0,
) -> str:
    from seestack.io.project import FrameRow

    entry, proj = lib.create_target(name, ra_deg=ra, dec_deg=dec)
    try:
        for sp in paths:
            proj.add_frame(FrameRow(source_path=str(sp), exposure_s=exposure_s))
    finally:
        proj.close()
    lib.refresh_target_stats(entry.safe_name)
    return entry.safe_name


def test_a_target_is_never_offered_a_merge_with_its_own_duplicate(client, data_root: Path):
    """The owner's ``M 13`` / ``M 13_SUB`` pair: one folder of subs, registered
    twice. Combining them moves nothing (``merge_projects`` dedupes on the
    canonical realpath), so the nudge promised a deeper picture it could not
    deliver — and its headline doubled the integration on the way. The right
    nudge for these is the cleanup card, which already detects them."""
    dump = data_root / "dump"
    subs_dir = dump / "M 13_sub"
    subs_dir.mkdir(parents=True)
    subs = [subs_dir / f"Light_{i:03d}.fit" for i in range(8)]
    # The base "<T>" target owns those same subs plus the on-device output
    # frames an old scan folded in — exactly the owner's 3628-vs-3619 signature.
    output_dir = dump / "M 13"
    output_dir.mkdir()

    lib = Library.open_or_create(data_root / "library")
    try:
        _target_with_frames(lib, "M 13", *M31, subs + [output_dir / "Stacked.fit"])
        _target_with_frames(lib, "M 13_SUB", M31[0] + 0.01, M31[1], subs)
    finally:
        lib.close()

    assert client.get("/api/targets/merge-suggestions").json() == []
    # ...and the pair is not simply invisible: cleanup owns it.
    cleanup = {c["safe"]: c["reason"] for c in client.get(
        "/api/targets/cleanup-suggestions").json()}
    assert cleanup.get("M_13_SUB") == "duplicate_sub"


def test_a_genuinely_different_second_folder_is_still_offered(client, data_root: Path):
    """The one pair in the owner's library with genuinely different counts
    (``NGC 6888`` 4815 subs beside ``NGC 6888_SUB`` 3110) is a real two-folder
    case, and combining it really does deepen the picture. Only a *confirmed*
    duplicate — one whose base owns every single frame — may be dropped."""
    dump = data_root / "dump"
    shared = dump / "NGC 6888_sub"
    shared.mkdir(parents=True)
    base_frames = [shared / f"Light_{i:03d}.fit" for i in range(8)]
    other = dump / "NGC 6888_sub_night2"
    other.mkdir()
    # The "_sub"-named target holds a frame the base does NOT own.
    extra = [shared / f"Light_{i:03d}.fit" for i in range(4)] + [other / "Light_099.fit"]

    lib = Library.open_or_create(data_root / "library")
    try:
        _target_with_frames(lib, "NGC 6888", *M31, base_frames)
        _target_with_frames(lib, "NGC 6888_SUB", M31[0] + 0.01, M31[1], extra)
    finally:
        lib.close()

    body = client.get("/api/targets/merge-suggestions").json()
    assert len(body) == 1
    assert {t["safe"] for t in body[0]["targets"]} == {"NGC_6888", "NGC_6888_SUB"}


def test_a_mosaic_is_never_offered_a_merge_with_its_own_single_field(client, data_root: Path):
    """``_apply_seestar_convention`` creates ``"<T> (mosaic)"`` as a target
    *deliberately* kept distinct from ``<T>`` "so their differing footprints are
    never co-stacked or auto-merged". They share a sky position by definition, so
    position-only clustering paired them every time and the nudge offered exactly
    the merge the scanner had gone out of its way to prevent."""
    dump = data_root / "dump"
    (dump / "M 3_sub").mkdir(parents=True)
    (dump / "M 3_mosaic_sub").mkdir()
    field = [dump / "M 3_sub" / f"Light_{i:03d}.fit" for i in range(8)]
    panels = [dump / "M 3_mosaic_sub" / f"Light_{i:03d}.fit" for i in range(6)]

    lib = Library.open_or_create(data_root / "library")
    try:
        _target_with_frames(lib, "M 3", *M31, field)
        _target_with_frames(lib, "M 3 (mosaic)", M31[0] + 0.01, M31[1], panels)
    finally:
        lib.close()

    assert client.get("/api/targets/merge-suggestions").json() == []


def test_two_mosaic_folders_of_one_object_still_cluster(client, data_root: Path):
    """The mosaic rule drops a mosaic only when its OWN single field is present —
    two same-object folders that are both mosaics are still a real merge."""
    dump = data_root / "dump"
    (dump / "a_mosaic_sub").mkdir(parents=True)
    (dump / "b_mosaic_sub").mkdir()

    lib = Library.open_or_create(data_root / "library")
    try:
        _target_with_frames(
            lib, "M 3 (mosaic)", *M31,
            [dump / "a_mosaic_sub" / f"L_{i}.fit" for i in range(4)])
        _target_with_frames(
            lib, "M 3 north (mosaic)", M31[0] + 0.01, M31[1],
            [dump / "b_mosaic_sub" / f"L_{i}.fit" for i in range(4)])
    finally:
        lib.close()

    body = client.get("/api/targets/merge-suggestions").json()
    assert len(body) == 1
    assert {t["safe"] for t in body[0]["targets"]} == {"M_3_mosaic", "M_3_north_mosaic"}


def test_the_owners_m3_card_disappears_entirely(client, data_root: Path):
    """End-to-end on the owner's worst card: five members, "64 h total", ~31 h of
    real data. Its single field, its mosaic, both of their ``_sub`` duplicates and
    the mosaic's on-device output — after this fix the merge nudge is silent and
    every leftover is offered to cleanup instead."""
    dump = data_root / "dump"
    for d in ("M 3_sub", "M 3_mosaic_sub", "M 3_mosaic"):
        (dump / d).mkdir(parents=True)
    field = [dump / "M 3_sub" / f"Light_{i:03d}.fit" for i in range(8)]
    panels = [dump / "M 3_mosaic_sub" / f"Light_{i:03d}.fit" for i in range(6)]
    # A mosaic's on-device output is one image PER PANEL — the owner's real
    # M 44_MOSAIC holds 11 and NGC 6960_MOSAIC 7, both far past the ≤2 gate that
    # used to decide whether such a target was even examined.
    mosaic_out = [dump / "M 3_mosaic" / f"panel_{i:02d}.fit" for i in range(11)]

    lib = Library.open_or_create(data_root / "library")
    try:
        _target_with_frames(lib, "M 3", *M31, field)
        _target_with_frames(lib, "M 3_SUB", M31[0] + 0.005, M31[1], field)
        _target_with_frames(lib, "M 3 (mosaic)", M31[0] + 0.01, M31[1], panels)
        _target_with_frames(lib, "M 3_MOSAIC_SUB", M31[0] + 0.015, M31[1], panels)
        _target_with_frames(lib, "M 3_MOSAIC", M31[0] + 0.02, M31[1], mosaic_out)
    finally:
        lib.close()

    assert client.get("/api/targets/merge-suggestions").json() == []
    cleanup = {c["safe"]: c["reason"] for c in client.get(
        "/api/targets/cleanup-suggestions").json()}
    assert cleanup == {
        "M_3_SUB": "duplicate_sub",
        "M_3_MOSAIC_SUB": "duplicate_sub",
        "M_3_MOSAIC": "on_device_output",
    }
