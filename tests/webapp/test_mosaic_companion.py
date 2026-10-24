"""A single field's Target page names the mosaic of the same object he already has.

The framing note and the coaching line both tell a single field of something
bigger than one frame to "shoot it in mosaic mode next session". The Seestar
writes those subs into ``<T>_mosaic_sub/``, which becomes its own
``"<T> (mosaic)"`` target — so for a heavy mosaic user the advice is usually
already taken, and the page never pointed at the picture it made.
``GET /api/targets/{safe}`` now serves ``mosaic_companion`` for that.
"""

from __future__ import annotations

from pathlib import Path

from seestack.io.library import Library
from seestack.io.project import FrameRow
from webapp.mosaic_companion import find_mosaic_companion


def _add_target(
    lib: Library, name: str, n: int, *, ra: float | None = None,
    dec: float | None = None, exposure_s: float = 10.0,
) -> str:
    entry, proj = lib.open_or_create_target(name)
    try:
        for i in range(n):
            proj.add_frame(FrameRow(
                source_path=f"/data/incoming/{entry.safe_name}/Light_{i:03d}.fit",
                exposure_s=exposure_s,
                ra_center_deg=ra, dec_center_deg=dec,
            ))
    finally:
        proj.close()
    lib.refresh_target_stats(entry.safe_name)
    return entry.safe_name


def _companion(client, safe: str):  # noqa: ANN001, ANN202
    r = client.get(f"/api/targets/{safe}")
    assert r.status_code == 200, r.text
    return r.json()["mosaic_companion"]


def test_names_the_conventions_mosaic_of_this_field(client, data_root: Path):
    lib = Library.open_or_create(data_root / "library")
    try:
        field = _add_target(lib, "M 42", 6)
        mosaic = _add_target(lib, "M 42 (mosaic)", 30)
    finally:
        lib.close()

    got = _companion(client, field)
    assert got == {
        "safe_name": mosaic, "name": "M 42 (mosaic)",
        "n_frames_accepted": 30, "total_exposure_s": 300.0,
    }
    # A mosaic is never told to shoot a mosaic, so it has no companion.
    assert _companion(client, mosaic) is None


def test_a_renamed_pair_is_matched_by_where_it_points(client, data_root: Path):
    lib = Library.open_or_create(data_root / "library")
    try:
        field = _add_target(lib, "Orion Nebula", 6, ra=83.82, dec=-5.39)
        _add_target(lib, "Too far (mosaic)", 50, ra=84.5, dec=-5.39)
        shallow = _add_target(lib, "Shallow (mosaic)", 10, ra=83.85, dec=-5.40)
        deep = _add_target(lib, "Deep (mosaic)", 40, ra=83.80, dec=-5.38)
    finally:
        lib.close()

    got = _companion(client, field)
    # The deepest of the two within the merge nudge's tolerance; the one 0.7°
    # away is a different pointing, however deep.
    assert got["safe_name"] == deep
    assert got["safe_name"] != shallow


def test_silent_without_a_mosaic_of_this_object(client, data_root: Path):
    lib = Library.open_or_create(data_root / "library")
    try:
        field = _add_target(lib, "M 42", 6, ra=83.82, dec=-5.39)
        # Another object's mosaic, and another single field of this one.
        _add_target(lib, "M 31 (mosaic)", 30, ra=10.68, dec=41.27)
        _add_target(lib, "M 42 night two", 6, ra=83.82, dec=-5.39)
        # The convention's name, but no accepted sub in it yet.
        _add_target(lib, "M 42 (mosaic)", 0)
    finally:
        lib.close()

    assert _companion(client, field) is None


def test_the_list_endpoint_does_not_carry_it(client, data_root: Path):
    lib = Library.open_or_create(data_root / "library")
    try:
        _add_target(lib, "M 42", 6)
        _add_target(lib, "M 42 (mosaic)", 30)
    finally:
        lib.close()

    rows = client.get("/api/targets").json()
    assert rows and all(r.get("mosaic_companion") is None for r in rows)


def test_name_match_beats_a_deeper_positional_one(data_root: Path):
    lib = Library.open_or_create(data_root / "library")
    try:
        _add_target(lib, "M 42", 6, ra=83.82, dec=-5.39)
        _add_target(lib, "M 42 (mosaic)", 10)
        _add_target(lib, "Big M42 (mosaic)", 90, ra=83.82, dec=-5.39)
        targets = lib.list_targets()
        field = lib.find_target("M 42")
        got = find_mosaic_companion(field, targets)
    finally:
        lib.close()

    assert got is not None and got.name == "M 42 (mosaic)"


def test_a_flagged_mixed_drop_is_never_the_companion(data_root: Path):
    lib = Library.open_or_create(data_root / "library")
    try:
        _add_target(lib, "M 42", 6)
        _add_target(lib, "M 42 (mosaic)", 30)
        lib.flag_legacy_mixed_drop("M 42 (mosaic)")
        targets = lib.list_targets()
        field = lib.find_target("M 42")
        got = find_mosaic_companion(field, targets)
    finally:
        lib.close()

    assert got is None
