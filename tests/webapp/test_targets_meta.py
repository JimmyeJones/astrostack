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
