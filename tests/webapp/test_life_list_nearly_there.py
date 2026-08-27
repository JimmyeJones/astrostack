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
