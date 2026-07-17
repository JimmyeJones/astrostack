"""GET /api/targets/{safe}/identify — the offline "What am I looking at?" card."""

from __future__ import annotations


def test_identify_known_target_by_name(client, solved_library):
    # The synthetic library has an "M_42" folder — it must resolve to the Orion
    # Nebula with friendly type + constellation.
    targets = client.get("/api/targets").json()
    m42 = next(t for t in targets if t["safe_name"] == "M_42")
    r = client.get(f"/api/targets/{m42['safe_name']}/identify")
    assert r.status_code == 200
    info = r.json()
    assert info is not None
    assert info["id"] == "M42"
    assert info["name"] == "Orion Nebula"
    assert info["type"] == "nebula"
    assert info["constellation"] == "Orion"
    assert info["matched_by"] == "name"
    # M42 (~85') is bigger than the single Seestar frame → a mosaic framing hint.
    assert info["size_arcmin"] == 85.0
    assert info["framing"] is not None
    assert info["framing"]["level"] == "mosaic"
    assert "mosaic" in info["framing"]["text"]
    # M42 is a curated popular target, so it carries a beginner blurb too.
    assert info["blurb"]
    assert "nebula" in info["blurb"].lower()


def test_identify_returns_null_for_an_unmatched_target(client, solved_library):
    # A freshly created target with a non-catalog name and no solve → no card.
    client.post("/api/targets", json={"name": "backyard test field"})
    targets = client.get("/api/targets").json()
    safe = next(t["safe_name"] for t in targets if t["name"] == "backyard test field")
    r = client.get(f"/api/targets/{safe}/identify")
    assert r.status_code == 200
    assert r.json() is None


def test_identify_unknown_target_404(client):
    r = client.get("/api/targets/does_not_exist/identify")
    assert r.status_code == 404
