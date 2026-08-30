"""``/api/sky/universe`` — the captured objects placed in depth by real distance."""

from __future__ import annotations

from seestack.io.library import Library
from seestack.io.project import FrameRow
from seestack.universemap import PROVENANCE


def test_universe_places_the_captured_targets_by_distance(client, built_library):
    r = client.get("/api/sky/universe")
    assert r.status_code == 200
    body = r.json()

    by_safe = {o["safe"]: o for o in body["objects"]}
    assert set(by_safe) == {"M_42", "NGC_7000"}
    # M42 (1,344 ly) really is nearer than the North America Nebula (2,200 ly),
    # so it sits further in — the one thing this map exists to show.
    assert by_safe["M_42"]["distance_ly"] < by_safe["NGC_7000"]["distance_ly"]
    assert by_safe["M_42"]["depth"] < by_safe["NGC_7000"]["depth"]
    assert all(0.0 < o["depth"] < 1.0 for o in body["objects"])
    # Nearest first.
    assert [o["safe"] for o in body["objects"]] == ["M_42", "NGC_7000"]

    m42 = by_safe["M_42"]
    assert m42["object_id"] == "M42"
    assert m42["distance_text"].endswith(" ly")
    assert m42["years_text"].endswith(" years")
    # Placed at the *object's* catalog position, so every picture of a target
    # lands where the object actually is.
    assert m42["ra_deg"] > 80 and m42["dec_deg"] < 0


def test_universe_says_what_the_object_actually_is(client, built_library):
    # Fail-before: the read-out was a distance and a light-travel time about an
    # object the reader may not recognise. The catalog's one-liner already
    # existed (the Target page's object card shows it); it just wasn't carried.
    body = client.get("/api/sky/universe").json()
    by_safe = {o["safe"]: o for o in body["objects"]}
    assert "blurb" in by_safe["M_42"]
    assert by_safe["M_42"]["blurb"].strip()          # M 42 is a curated entry
    assert all(isinstance(o["blurb"], str) for o in body["objects"])


def test_universe_carries_a_labelled_scale_and_its_provenance(client, built_library):
    body = client.get("/api/sky/universe").json()
    assert len(body["shells"]) >= 2
    depths = [s["depth"] for s in body["shells"]]
    assert depths == sorted(depths)
    assert all(s["label"].endswith(" ly") for s in body["shells"])
    assert body["near_ly"] < body["far_ly"]
    # The map must never read as "my telescope measured this".
    assert body["provenance"] == PROVENANCE


def test_universe_reports_an_unplaceable_target_instead_of_guessing(
    client, built_library,
):
    """A target the bundled catalog can't identify is named, not invented."""
    lib = Library.open_or_create(built_library / "library")
    try:
        entry, proj = lib.create_target("Backyard test frames")
        try:
            proj.add_frame(FrameRow(source_path="/incoming/backyard/frame_000.fit"))
        finally:
            proj.close()
        lib.refresh_target_stats(entry.safe_name)
    finally:
        lib.close()

    body = client.get("/api/sky/universe").json()
    assert "Backyard test frames" not in [o["name"] for o in body["objects"]]
    unplaced = {u["name"]: u for u in body["unplaced"]}
    assert "Backyard test frames" in unplaced
    assert unplaced["Backyard test frames"]["reason"]


def test_universe_ignores_registry_rows_with_no_frames(client, built_library):
    """A folder that never became a capture is neither placed nor apologised for."""
    lib = Library.open_or_create(built_library / "library")
    try:
        _entry, proj = lib.create_target("Empty folder")
        proj.close()
    finally:
        lib.close()

    body = client.get("/api/sky/universe").json()
    names = [o["name"] for o in body["objects"]] + [u["name"] for u in body["unplaced"]]
    assert "Empty folder" not in names


def test_universe_on_an_empty_library_is_an_honest_empty_map(client, data_root):
    body = client.get("/api/sky/universe").json()
    assert body["objects"] == [] and body["shells"] == []
    assert body["near_ly"] == 0.0 and body["far_ly"] == 0.0
    assert body["provenance"] == PROVENANCE
