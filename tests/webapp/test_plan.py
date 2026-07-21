"""Tests for the 'Tonight' night-planner endpoint (``/api/plan/tonight``)."""

from __future__ import annotations

from datetime import date as _date
from datetime import datetime, timedelta, timezone
from pathlib import Path

from webapp.routers.plan import _parse_angle, _site_from_header

# A fixed winter evening in the northern hemisphere → a real dark window.
JAN_EVENING = "2026-01-15T20:00:00+00:00"


def test_parse_angle_handles_float_and_sexagesimal():
    assert _parse_angle(51.5) == 51.5
    assert _parse_angle("51.5") == 51.5
    assert abs(_parse_angle("51:30:00") - 51.5) < 1e-6
    assert abs(_parse_angle("-0:07:48") - (-0.13)) < 1e-3
    assert _parse_angle(None) is None
    assert _parse_angle("") is None
    assert _parse_angle("not-an-angle") is None


def test_site_from_header():
    assert _site_from_header({"SITELAT": 51.5, "SITELONG": -0.13}) == (51.5, -0.13)
    assert _site_from_header({"SITELAT": 51.5}) is None          # no longitude
    assert _site_from_header({"SITELAT": 999, "SITELONG": 0}) is None  # out of range


def test_tonight_without_location_prompts_for_one(client, solved_library):
    # Synth frames carry no SITELAT and no site is configured → the planner
    # can't run and asks the user to set a location, rather than 500-ing.
    r = client.get("/api/plan/tonight", params={"when": JAN_EVENING})
    assert r.status_code == 200
    body = r.json()
    assert body["location_source"] == "none"
    assert body["observer"] is None
    assert body["dark_window"] is None
    assert body["targets"] == []


def test_tonight_with_settings_location(client, solved_library):
    client.put("/api/settings", json={"site_lat": 51.5, "site_lon": -0.13})
    r = client.get("/api/plan/tonight", params={"when": JAN_EVENING})
    assert r.status_code == 200
    body = r.json()
    assert body["location_source"] == "settings"
    assert body["observer"]["lat_deg"] == 51.5
    assert body["dark_window"] is not None
    assert body["dark_window"]["sun_alt_threshold_deg"] == -18.0
    assert 0.0 <= body["moon_illumination"] <= 1.0
    # 2026-01-15 is a waning crescent (days before the ~01-18 new Moon).
    assert body["moon_waxing"] is False
    # The plan carries a moon-window cue alongside the dark window (concrete
    # rise/set time or an all-night flag); shape-checked here, values pinned in
    # the engine tests.
    mw = body["moon_window"]
    assert mw is not None
    assert set(mw) == {"rise_utc", "set_utc", "up_all_night", "down_all_night"}
    assert not (mw["up_all_night"] and mw["down_all_night"])

    targets = body["targets"]
    assert targets, "expected a ranked target list"
    # Scores are sorted best-first.
    scores = [t["score"] for t in targets]
    assert scores == sorted(scores, reverse=True)
    # The library target M_42 (ra 83.6 / dec −5.4) is present, deduped from the
    # catalog's M42, and flagged as already targeted with its capture stats.
    already = [t for t in targets if t["already_targeted"]]
    assert any(t["target_safe"] == "M_42" for t in already)
    m42 = next(t for t in already if t["target_safe"] == "M_42")
    assert m42["frames_accepted"] >= 1
    # No *catalog* duplicate is emitted near a library target's position (the
    # fixture's two library targets happen to share M42's coords, so both of
    # those legitimately show — dedup only suppresses the bundled-catalog copy).
    near_m42 = [t for t in targets if abs(t["ra_deg"] - 83.6) < 1.0
                and abs(t["dec_deg"] - (-5.4)) < 1.0]
    assert near_m42 and all(t["already_targeted"] for t in near_m42)
    # The catalog fills in "not yet targeted" candidates too.
    assert any(not t["already_targeted"] for t in targets)
    # A sized catalog candidate carries its "will it fit?" framing hint so the
    # planner can nudge toward mosaic mode pre-capture.
    by_id = {t["id"]: t for t in targets}
    if "M31" in by_id:  # Andromeda is up from London in January
        m31 = by_id["M31"]
        assert m31["size_arcmin"] == 178.0
        assert m31["framing"]["level"] == "mosaic"
        assert "mosaic" in m31["framing"]["text"]


def test_tonight_min_alt_override_changes_usable_window(client, solved_library):
    client.put("/api/settings", json={"site_lat": 51.5, "site_lon": -0.13})
    low = client.get("/api/plan/tonight", params={"when": JAN_EVENING, "min_alt": 10}).json()
    high = client.get("/api/plan/tonight", params={"when": JAN_EVENING, "min_alt": 60}).json()
    assert low["min_altitude_deg"] == 10
    assert high["min_altitude_deg"] == 60
    # A stricter altitude floor can only shrink each target's usable window.
    low_by_id = {t["id"]: t["minutes_above_min_alt"] for t in low["targets"]}
    for t in high["targets"]:
        if t["id"] in low_by_id:
            assert t["minutes_above_min_alt"] <= low_by_id[t["id"]] + 1e-6


def test_tonight_horizon_mask_trims_usable_windows(client, solved_library):
    # A horizon/tree wall raised above the min-altitude floor (but reachable) can
    # only shrink each target's usable window vs. the same plan with no mask, and
    # the response advertises that the mask is active.
    client.put("/api/settings", json={"site_lat": 51.5, "site_lon": -0.13})
    flat = client.get("/api/plan/tonight",
                      params={"when": JAN_EVENING, "min_alt": 20}).json()
    assert flat["horizon_active"] is False

    # A 45° wall across the whole sky. The settings save round-trips the profile.
    saved = client.put("/api/settings",
                       json={"horizon_profile": [[0, 45], [180, 45]]}).json()
    assert saved["horizon_profile"] == [[0.0, 45.0], [180.0, 45.0]]

    walled = client.get("/api/plan/tonight",
                        params={"when": JAN_EVENING, "min_alt": 20}).json()
    assert walled["horizon_active"] is True
    flat_by_id = {t["id"]: t["minutes_above_min_alt"] for t in flat["targets"]}
    for t in walled["targets"]:
        if t["id"] in flat_by_id:
            assert t["minutes_above_min_alt"] <= flat_by_id[t["id"]] + 1e-6
    # At least one target actually lost usable time to the wall (it isn't a no-op).
    assert any(t["minutes_above_min_alt"] < flat_by_id.get(t["id"], 0.0) - 1e-6
               for t in walled["targets"])


def test_settings_sanitises_a_malformed_horizon_profile(client):
    # Garbage points are dropped, azimuth wraps, altitude clamps — the save never
    # 422s and stores a clean, ordered profile.
    body = client.put("/api/settings", json={"horizon_profile": [
        [370, 15], ["bad", "pair"], [90], [45, 200], [180, -3],
    ]}).json()
    assert body["horizon_profile"] == [[10.0, 15.0], [45.0, 90.0], [180.0, 0.0]]
    # An empty profile is valid and inert (the default).
    cleared = client.put("/api/settings", json={"horizon_profile": []}).json()
    assert cleared["horizon_profile"] == []


def test_tonight_rejects_bad_when(client, solved_library):
    client.put("/api/settings", json={"site_lat": 51.5, "site_lon": -0.13})
    r = client.get("/api/plan/tonight", params={"when": "not-a-timestamp"})
    assert r.status_code == 422


def test_reference_for_date_lands_on_local_noon():
    # Local solar noon in UTC is 12:00 − lon/15 h: Greenwich noons at 12:00 UTC,
    # 15°E an hour earlier, 30°W two hours later — always on the chosen date.
    from webapp.routers.plan import _reference_for_date

    d = _date(2026, 7, 15)
    assert _reference_for_date(d, 0.0) == datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)
    assert _reference_for_date(d, 15.0) == datetime(2026, 7, 15, 11, 0, tzinfo=timezone.utc)
    assert _reference_for_date(d, -30.0) == datetime(2026, 7, 15, 14, 0, tzinfo=timezone.utc)


def test_tonight_plans_a_chosen_future_date(client, solved_library):
    # A calendar-date pick a few weeks out plans that night's dark window — the
    # same offline computation, just aimed at a different night. The Moon has moved
    # meaningfully by then, so the plan is genuinely date-specific, not "tonight".
    client.put("/api/settings", json={"site_lat": 51.5, "site_lon": -0.13})
    today = datetime.now(timezone.utc)
    future = (today + timedelta(days=20)).date().isoformat()
    r = client.get("/api/plan/tonight", params={"date": future, "min_alt": 20})
    assert r.status_code == 200
    body = r.json()
    assert body["location_source"] == "settings"
    assert body["dark_window"] is not None
    # generated_utc sits on (or adjacent to, across the noon boundary) the picked date.
    gen = datetime.fromisoformat(body["generated_utc"]).date()
    assert abs((gen - datetime.fromisoformat(future + "T00:00:00").date()).days) <= 1
    assert body["targets"], "expected a ranked target list for the chosen night"


def test_tonight_date_differs_from_today(client, solved_library):
    # Planning a night ~2 weeks out gives a different Moon than tonight (the Moon
    # cycles in ~29.5 days), proving the date actually drove the ephemeris.
    client.put("/api/settings", json={"site_lat": 51.5, "site_lon": -0.13})
    tonight = client.get("/api/plan/tonight").json()
    future = (datetime.now(timezone.utc) + timedelta(days=14)).date().isoformat()
    later = client.get("/api/plan/tonight", params={"date": future}).json()
    assert tonight["moon_illumination"] != later["moon_illumination"]


def test_tonight_rejects_a_far_future_date(client, solved_library):
    client.put("/api/settings", json={"site_lat": 51.5, "site_lon": -0.13})
    far = (datetime.now(timezone.utc) + timedelta(days=120)).date().isoformat()
    r = client.get("/api/plan/tonight", params={"date": far})
    assert r.status_code == 422


def test_tonight_accepts_the_pickers_farthest_date_across_the_tz_boundary(client, solved_library):
    # The date picker offers up to `local_today + 60`; for a viewer east of UTC in
    # their local morning that is `UTC_today + 61`. The backend must accept it (one
    # day of slack on the upper bound, mirroring the min) — before the fix the
    # farthest date the app's own picker allowed 422'd for eastern-hemisphere users.
    client.put("/api/settings", json={"site_lat": 51.5, "site_lon": -0.13})
    from webapp.routers.plan import _MAX_LOOKAHEAD_DAYS
    edge = (datetime.now(timezone.utc) + timedelta(days=_MAX_LOOKAHEAD_DAYS + 1)).date().isoformat()
    r = client.get("/api/plan/tonight", params={"date": edge})
    assert r.status_code == 200, r.text
    # One day past the picker's own max is still rejected (the cap still bites).
    beyond = (datetime.now(timezone.utc) + timedelta(days=_MAX_LOOKAHEAD_DAYS + 2)).date().isoformat()
    assert client.get("/api/plan/tonight", params={"date": beyond}).status_code == 422


def test_tonight_rejects_a_past_date(client, solved_library):
    client.put("/api/settings", json={"site_lat": 51.5, "site_lon": -0.13})
    past = (datetime.now(timezone.utc) - timedelta(days=10)).date().isoformat()
    r = client.get("/api/plan/tonight", params={"date": past})
    assert r.status_code == 422


def test_tonight_rejects_a_malformed_date(client, solved_library):
    client.put("/api/settings", json={"site_lat": 51.5, "site_lon": -0.13})
    r = client.get("/api/plan/tonight", params={"date": "2026-13-40"})
    assert r.status_code == 422


def test_next_session_returns_upcoming_windows_for_a_library_target(client, solved_library):
    # The forward-looking companion to /tonight: for a well-placed library target
    # it returns the next few nights it's shootable, so the Target page can say
    # "…and here's your next good window".
    client.put("/api/settings", json={"site_lat": 51.5, "site_lon": -0.13})
    r = client.get("/api/plan/next-session/M_42", params={"when": JAN_EVENING})
    assert r.status_code == 200
    body = r.json()
    assert body["location_source"] == "settings"
    assert body["target_has_position"] is True
    assert body["nights_scanned"] >= 1
    wins = body["windows"]
    assert wins, "Orion is well up on January nights from London"
    prev = None
    for w in wins:
        assert w["dark_start_utc"] < w["dark_end_utc"]
        assert w["usable_start_utc"] is not None
        assert w["max_altitude_deg"] > 30.0
        assert w["minutes_above_min_alt"] >= 45.0
        assert 0.0 <= w["moon_illumination"] <= 1.0
        # Chronological (soonest window first).
        if prev is not None:
            assert w["dark_start_utc"] > prev
        prev = w["dark_start_utc"]


def test_next_session_without_location_self_hides(client, solved_library):
    # No configured site and the synth frames carry no SITELAT → no windows to
    # compute, but a clean 200 with an empty list so the card just self-hides.
    r = client.get("/api/plan/next-session/M_42", params={"when": JAN_EVENING})
    assert r.status_code == 200
    body = r.json()
    assert body["location_source"] == "none"
    assert body["observer"] is None
    assert body["windows"] == []


def test_next_session_unknown_target_404s(client, solved_library):
    client.put("/api/settings", json={"site_lat": 51.5, "site_lon": -0.13})
    r = client.get("/api/plan/next-session/NOPE_404", params={"when": JAN_EVENING})
    assert r.status_code == 404


def test_next_session_never_rising_target_has_no_windows(client, solved_library):
    # A high altitude floor Orion can't clear from London → no usable window, so
    # the list is empty (the card self-hides) rather than 500-ing.
    client.put("/api/settings", json={"site_lat": 51.5, "site_lon": -0.13})
    r = client.get("/api/plan/next-session/M_42",
                   params={"when": JAN_EVENING, "min_alt": 80})
    assert r.status_code == 200
    body = r.json()
    assert body["min_altitude_deg"] == 80
    assert body["windows"] == []


def test_tonight_detects_site_from_fits_header(tmp_path: Path, monkeypatch):
    """With no configured site, the planner sniffs SITELAT/SITELONG from a frame."""
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from fastapi.testclient import TestClient
    from synth import write_seestar_fits

    from seestack.io.library import Library
    from seestack.io.scanner import scan_and_organize
    from webapp.main import create_app

    data_root = tmp_path / "data"
    incoming = data_root / "incoming" / "M_13"
    incoming.mkdir(parents=True)
    for i in range(2):
        write_seestar_fits(
            incoming / f"frame_{i:03d}.fit", add_wcs=True,
            ra_center_deg=250.4, dec_center_deg=36.5,
            site_lat=48.0, site_lon=11.0, seed=200 + i,
        )
    lib = Library.open_or_create(data_root / "library")
    try:
        scan_and_organize(lib, data_root / "incoming", copy_to_cache=False)
    finally:
        lib.close()

    monkeypatch.setenv("ASTROSTACK_DATA", str(data_root))
    app = create_app()
    with TestClient(app) as c:
        c.put("/api/settings", json={"watcher_enabled": False})
        body = c.get("/api/plan/tonight", params={"when": JAN_EVENING}).json()
    assert body["location_source"] == "fits"
    assert abs(body["observer"]["lat_deg"] - 48.0) < 1e-6
    assert abs(body["observer"]["lon_deg"] - 11.0) < 1e-6
