"""PATCH /api/targets/{safe}: editable notes + tags, surfaced in target output."""

from __future__ import annotations


def test_patch_notes_and_tags(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]

    r = client.patch(f"/api/targets/{safe}", json={"notes": "hi", "tags": ["nebula", "rgb"]})
    assert r.status_code == 200
    body = r.json()
    assert body["notes"] == "hi"
    assert body["tags"] == ["nebula", "rgb"]

    # Surfaced in the list + detail views.
    listed = next(t for t in client.get("/api/targets").json() if t["safe_name"] == safe)
    assert listed["tags"] == ["nebula", "rgb"]
    detail = client.get(f"/api/targets/{safe}").json()
    assert detail["notes"] == "hi"

    # Partial patch leaves notes intact.
    r2 = client.patch(f"/api/targets/{safe}", json={"tags": ["mono"]})
    assert r2.json()["notes"] == "hi"
    assert r2.json()["tags"] == ["mono"]


def test_patch_unknown_target_404(client):
    r = client.patch("/api/targets/does_not_exist", json={"notes": "x"})
    assert r.status_code == 404


def test_patch_renames_the_display_name_without_moving_the_target(client, solved_library):
    """The one-click "use this name?" the identity card offers. The label
    changes; the safe name — which every path, link and stored run resolves
    through — must not."""
    r = client.patch("/api/targets/M_42", json={"name": "Orion Nebula"})
    assert r.status_code == 200
    assert r.json()["name"] == "Orion Nebula"
    assert r.json()["safe_name"] == "M_42"

    # Still reachable at the same URL, and the new name is what the app shows.
    detail = client.get("/api/targets/M_42")
    assert detail.status_code == 200
    assert detail.json()["name"] == "Orion Nebula"
    listed = next(t for t in client.get("/api/targets").json()
                  if t["safe_name"] == "M_42")
    assert listed["name"] == "Orion Nebula"

    # An older client that patches notes without a name leaves it alone.
    r2 = client.patch("/api/targets/M_42", json={"notes": "clear night"})
    assert r2.json()["name"] == "Orion Nebula"
    assert r2.json()["notes"] == "clear night"


def test_patch_refuses_a_blank_name_or_one_another_target_owns(client, solved_library):
    assert client.patch("/api/targets/M_42", json={"name": "   "}).status_code == 400
    # NGC_7000 is the other target in the fixture library.
    assert client.patch("/api/targets/M_42",
                        json={"name": "NGC_7000"}).status_code == 400
    # Nothing changed on either target.
    assert client.get("/api/targets/M_42").json()["name"] == "M_42"
    assert client.get("/api/targets/NGC_7000").json()["name"] == "NGC_7000"
