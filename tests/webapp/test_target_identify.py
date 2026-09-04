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


def test_identify_carries_the_light_travel_line(client, solved_library):
    # "How far did you see?" — the one line on the card that is pure wonder
    # rather than advice. M42 is ~1,344 ly, so the light left before the
    # telescope existed; the endpoint carries the whole ready-to-render
    # sentence, so no client has to re-derive the wording.
    info = client.get("/api/targets/M_42/identify").json()
    lt = info["light_travel"]
    assert lt is not None
    assert lt["distance_ly"] == 1344
    assert lt["years"] == "1,340 years"
    assert lt["text"] == (
        "The light in this picture left about 1,340 years ago — "
        "before the telescope was invented."
    )


def test_identify_light_travel_reaches_a_megalight_year_galaxy(client, solved_library):
    client.post("/api/targets", json={"name": "M 31"})
    targets = client.get("/api/targets").json()
    safe = next(t["safe_name"] for t in targets if t["name"] == "M 31")
    lt = client.get(f"/api/targets/{safe}/identify").json()["light_travel"]
    assert lt is not None
    assert "2.5 million years ago" in lt["text"]
    assert "before our species existed" in lt["text"]

def test_identify_plans_no_mosaic_for_a_target_that_fits(client, solved_library):
    # A compact target needs no mosaic, so the field stays null and the card
    # says nothing about panels (never a one-panel "mosaic").
    client.post("/api/targets", json={"name": "M 13"})
    targets = client.get("/api/targets").json()
    safe = next(t["safe_name"] for t in targets if t["name"] == "M 13")
    info = client.get(f"/api/targets/{safe}/identify").json()
    assert info is not None and info["framing"]["level"] == "fits"
    assert info["mosaic"] is None


def _set_pixel_scale(data_root, arcsec_per_px: float, w: int, h: int) -> None:
    """Give every frame in the library a solved plate scale and shape.

    The `solved_library` fixture injects a WCS but no `pixscale_arcsec`, which is
    exactly the "nothing to derive from" case the framing advice falls back on —
    so a test that wants the derived answer has to write one.
    """
    from seestack.io.library import Library

    lib = Library.open_or_create(data_root / "library")
    try:
        for entry in lib.list_targets():
            proj = lib.open_target(entry.safe_name)
            try:
                for f in proj.iter_frames():
                    proj.update_frame(f.id, pixscale_arcsec=arcsec_per_px,
                                      width_px=w, height_px=h)
            finally:
                proj.close()
    finally:
        lib.close()


def test_the_framing_verdict_is_measured_from_the_owners_own_frames(
        client, solved_library):
    """M 42 is a 4-panel mosaic through an S50's field and needs none through a
    wider one — and the card must read the field off the owner's own frames.

    The module shipped with the S50's 77' x 44' hard-coded eight days before the
    owner confirmed an S30 (AGENTS.md §1 "Owner facts"), whose short edge alone
    (~72') is wider than the S50's long one. The fixture's frames are 480x320
    rather than a Seestar's 16:9, so this writes a plate scale that gives them
    that ~72' short edge rather than pretending they are Seestar frames — the
    field is what the verdict reads, and a fixture claiming a sensor it does not
    have is how this bug got shipped in the first place.
    """
    _set_pixel_scale(solved_library, 71.8 * 60.0 / 320.0, 480, 320)  # 107.7' x 71.8'

    info = client.get("/api/targets/M_42/identify").json()
    assert info is not None and info["id"] == "M42"
    # 85' clears the ~72' short edge but fits the ~108' long one — "tight", with
    # no mosaic to plan. Through the S50 field this reads "mosaic" + 2x2/4 panels.
    assert info["framing"]["level"] == "tight"
    assert info["mosaic"] is None


def test_a_library_with_no_solved_plate_scale_keeps_the_previous_answer(
        client, solved_library):
    """The fallback is unchanged behaviour, not a second guess: an install whose
    frames carry no measured scale gets exactly the verdict it got before."""
    info = client.get("/api/targets/M_42/identify").json()
    assert info["framing"]["level"] == "mosaic"
    assert info["mosaic"]["panels"] == 4


def test_the_planner_badges_the_same_field_as_the_target_card(
        client, solved_library):
    """Two screens, one telescope. The Tonight planner's "Needs mosaic" badge and
    the Target page's framing line are the same claim about the same object, so
    they have to be computed against the same field — they were separately
    hard-coded against the S50's before."""
    _set_pixel_scale(solved_library, 71.8 * 60.0 / 320.0, 480, 320)  # 107.7' x 71.8'
    client.put("/api/settings", json={"site_lat": 51.5, "site_lon": -0.13})

    plan = client.get("/api/plan/tonight",
                      params={"when": "2026-01-15T21:00:00Z"}).json()
    rows = [t for t in plan.get("targets", []) if t.get("framing")]
    assert rows, "the planner returned no framed rows to check"
    checked = 0
    for row in rows:
        size = row.get("size_arcmin")
        if size is None:
            continue
        # Nothing under the ~72' short edge may be badged as needing a mosaic;
        # against the S50's 43' several of these were.
        if size <= 71.0:
            assert row["framing"]["level"] == "fits", row["name"]
            assert row.get("mosaic") is None, row["name"]
            checked += 1
    assert checked, "no row small enough to pin the widened field"

    # …and the Target card agrees about M 42 in the same breath.
    info = client.get("/api/targets/M_42/identify").json()
    assert info["framing"]["level"] == "tight"
