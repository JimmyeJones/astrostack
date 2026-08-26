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
    # …and how big a mosaic: M42 (85' x 60') is a 2x2, which is the number the
    # beginner actually sets in the Seestar app.
    assert info["mosaic"] is not None
    assert info["mosaic"]["cols"] == 2
    assert info["mosaic"]["rows"] == 2
    assert info["mosaic"]["panels"] == 4
    assert "2×2 mosaic (4 panels)" in info["mosaic"]["text"]
    # M42 is a curated popular target, so it carries a beginner blurb too.
    assert info["blurb"]
    assert "nebula" in info["blurb"].lower()
    # ...and a "how hard for a Seestar?" verdict — Orion is the easy one.
    assert info["difficulty"] is not None
    assert info["difficulty"]["level"] == "easy"
    assert info["difficulty"]["label"] == "Easy"
    assert info["difficulty"]["text"]


def test_identify_carries_the_background_mode_advice_for_a_big_nebula(
    client, solved_library,
):
    # M42 is the archetype the per-frame flatten's own docstring names: an
    # extended emission nebula, where the default per-channel sky fit bends into
    # the nebulosity differently in each channel. The Stack form's nudge reads
    # this field, so the endpoint must carry both the mode and the reason.
    r = client.get("/api/targets/M_42/identify")
    assert r.status_code == 200
    hint = r.json()["background_mode_hint"]
    assert hint is not None
    assert hint["mode"] == "luminance"
    assert "cyan cores" in hint["text"]


def test_identify_leaves_a_galaxy_on_the_default_background_mode(
    client, solved_library,
):
    # A galaxy is extended, but its channels share one shape — per-channel mode
    # handles it correctly, so the field must stay null and no nudge is shown.
    client.post("/api/targets", json={"name": "M 31"})
    targets = client.get("/api/targets").json()
    safe = next(t["safe_name"] for t in targets if t["name"] == "M 31")
    info = client.get(f"/api/targets/{safe}/identify").json()
    assert info is not None and info["type"] == "galaxy"
    assert info["background_mode_hint"] is None


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


def test_identify_plans_no_mosaic_for_a_target_that_fits(client, solved_library):
    # A compact target needs no mosaic, so the field stays null and the card
    # says nothing about panels (never a one-panel "mosaic").
    client.post("/api/targets", json={"name": "M 13"})
    targets = client.get("/api/targets").json()
    safe = next(t["safe_name"] for t in targets if t["name"] == "M 13")
    info = client.get(f"/api/targets/{safe}/identify").json()
    assert info is not None and info["framing"]["level"] == "fits"
    assert info["mosaic"] is None
