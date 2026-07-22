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
