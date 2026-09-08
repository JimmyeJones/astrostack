"""`GET /api/life-list/nearly-there` — "you're one away from finishing Lyra".

The life list says *how many* famous objects the owner has; this says what to
point at **next**, and whether it's up tonight. Read-only and offline: the
capture match reads the target registry and the observability comes from the
same bundled-catalog planner every other card uses.

Lyra is the fixture constellation because the bundled catalog holds exactly two
of its objects (M56 and the Ring Nebula, M57), so capturing one leaves a clean
"one missing" state that no other constellation can outrank.
"""

from __future__ import annotations

from seestack.io.library import Library
from seestack.io.project import FrameRow

# A northern site and a July night: Lyra is high overhead, so M57 is
# unambiguously well-placed. Fixed rather than "now" so the assertion can't
# flip with the calendar.
LONDON = {"site_lat": 51.5, "site_lon": -0.13}
SUMMER_NIGHT = "2026-07-15T23:00:00Z"
# The same site in mid-January, when Lyra is a pre-dawn object at best.
WINTER_EVENING = "2026-01-15T20:00:00Z"

M56 = (289.148, 30.183)
M57 = (283.396, 33.029)


def _register(data_root, name: str, ra: float, dec: float, *, n_frames: int = 6) -> str:
    lib = Library.open_or_create(data_root / "library")
    try:
        entry, proj = lib.create_target(name, ra_deg=ra, dec_deg=dec)
        try:
            proj.add_frames([
                FrameRow(source_path=f"{entry.safe_name}-{i}.fit")
                for i in range(n_frames)
            ])
        finally:
            proj.close()
        lib.refresh_target_stats(entry.safe_name)
        return entry.safe_name
    finally:
        lib.close()


def test_an_empty_library_is_close_to_nothing(client, data_root):
    """Nothing captured isn't 'nearly done' — the card self-hides rather than
    telling a fresh install it's one away from everything."""
    assert client.get("/api/life-list/nearly-there").json() is None


def test_one_capture_leaves_the_constellation_one_away(client, data_root):
    _register(data_root, "M 56", *M56)

    body = client.get("/api/life-list/nearly-there").json()
    assert body is not None
    assert body["con"] == "Lyr"
    assert body["constellation"] == "Lyra"          # the full name, for the copy
    assert body["captured"] == 1 and body["total"] == 2
    assert [m["catalog_id"] for m in body["missing"]] == ["M57"]
    assert body["missing"][0]["name"] == "Ring Nebula"
    # No location configured → no "and it's up tonight" half, and the UI is told
    # why rather than left to guess.
    assert body["tonight_catalog_id"] is None
    assert body["location_source"] == "none"
    assert body["missing"][0]["max_altitude_deg"] is None


def test_a_known_site_says_whether_the_missing_object_is_up(client, data_root):
    _register(data_root, "M 56", *M56)
    client.put("/api/settings", json=LONDON)

    body = client.get("/api/life-list/nearly-there",
                      params={"when": SUMMER_NIGHT}).json()
    assert body["location_source"] == "settings"
    assert body["tonight_catalog_id"] == "M57"
    missing = body["missing"][0]
    assert missing["max_altitude_deg"] > 60          # Lyra is overhead from 51°N
    assert missing["minutes_above_min_alt"] > 45
    assert missing["usable_start_utc"] and missing["usable_end_utc"]


def test_an_object_that_is_not_up_still_shows_the_constellation(client, data_root):
    """The 'you're close' half is worth saying even when tonight can't help —
    but we must not claim an altitude the object doesn't have."""
    _register(data_root, "M 56", *M56)
    client.put("/api/settings", json=LONDON)

    body = client.get("/api/life-list/nearly-there",
                      params={"when": WINTER_EVENING}).json()
    assert body["con"] == "Lyr"
    assert body["tonight_catalog_id"] is None
    assert body["missing"][0]["max_altitude_deg"] is None


def test_finishing_the_constellation_clears_the_nudge(client, data_root):
    _register(data_root, "M 56", *M56)
    assert client.get("/api/life-list/nearly-there").json()["con"] == "Lyr"

    _register(data_root, "M 57", *M57)
    assert client.get("/api/life-list/nearly-there").json() is None


def test_a_bad_when_is_rejected_rather_than_silently_ignored(client, data_root):
    _register(data_root, "M 56", *M56)
    r = client.get("/api/life-list/nearly-there", params={"when": "not-a-time"})
    assert r.status_code == 422


def test_the_plain_life_list_is_unchanged(client, data_root):
    """The new route sits beside `/api/life-list`, it doesn't shadow it."""
    body = client.get("/api/life-list").json()
    assert body["counts"]["messier_total"] == 110


# --- `GET /api/life-list/nearly-there/calendar.ics` ---------------------------
#
# The nudge knows what to point at and when it is up; without this it ended on a
# sentence the beginner had to remember. M57 is not a showpiece the suggestion
# card's `.ics` route would serve, which is the whole reason this route exists.


def test_the_tonight_pick_can_be_added_to_a_calendar(client, data_root):
    _register(data_root, "M 56", *M56)
    client.put("/api/settings", json=LONDON)

    r = client.get("/api/life-list/nearly-there/calendar.ics",
                   params={"when": SUMMER_NIGHT})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/calendar")
    assert "M57-next-session.ics" in r.headers["content-disposition"]
    body = r.text
    assert "BEGIN:VCALENDAR" in body and "BEGIN:VEVENT" in body
    # The event is about the object the card names, in plain language.
    assert "Ring Nebula" in body


def test_the_calendar_is_for_the_object_the_card_picked_not_an_id_we_were_given(
        client, data_root):
    """The route takes no id at all: it re-asks the same endpoint the card read,
    so the file cannot describe a different object or a different night — and
    there is no way to calendar an arbitrary catalog row through it."""
    _register(data_root, "M 56", *M56)
    client.put("/api/settings", json=LONDON)

    card = client.get("/api/life-list/nearly-there",
                      params={"when": SUMMER_NIGHT}).json()
    ics = client.get("/api/life-list/nearly-there/calendar.ics",
                     params={"when": SUMMER_NIGHT}).text
    assert card["tonight_catalog_id"] == "M57"
    assert f"UID:{card['tonight_catalog_id']}-" in ics
    # And there is no id-shaped variant of the route to reach instead — asked of
    # the app's own schema rather than of a URL, since an unknown path under a
    # built frontend is the SPA's index page, not a 404.
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/life-list/nearly-there/calendar.ics" in paths
    assert not [p for p in paths
                if p.startswith("/api/life-list/nearly-there/{")]


def test_the_missing_object_is_often_one_the_suggestion_route_will_not_serve(
        client, data_root):
    """Why this route exists at all, as a fact rather than a comment: a
    nearly-finished constellation's missing object comes from the *whole*
    bundled catalog, while `/api/plan/suggest/{id}/calendar.ics` is deliberately
    restricted to the showpiece whitelist. Reusing that route would have meant
    widening the guard that stops arbitrary catalog rows being calendared."""
    from seestack.nightplan import _SHOWPIECE_IDS, load_catalog

    catalog_ids = {obj.id for obj in load_catalog()}
    assert not catalog_ids <= set(_SHOWPIECE_IDS)


def test_nothing_up_tonight_is_a_404_not_a_blank_calendar(client, data_root):
    _register(data_root, "M 56", *M56)
    client.put("/api/settings", json=LONDON)

    r = client.get("/api/life-list/nearly-there/calendar.ics",
                   params={"when": WINTER_EVENING})
    assert r.status_code == 404


def test_no_location_and_no_nearly_finished_constellation_are_both_404s(
        client, data_root):
    # Nothing captured at all: no constellation is close.
    assert client.get("/api/life-list/nearly-there/calendar.ics").status_code == 404
    # Close, but no site to work out a window from.
    _register(data_root, "M 56", *M56)
    assert client.get("/api/life-list/nearly-there/calendar.ics").status_code == 404


def test_a_bad_when_is_rejected_by_the_calendar_route_too(client, data_root):
    _register(data_root, "M 56", *M56)
    client.put("/api/settings", json=LONDON)
    r = client.get("/api/life-list/nearly-there/calendar.ics",
                   params={"when": "not-a-time"})
    assert r.status_code == 422
