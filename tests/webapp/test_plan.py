"""Tests for the 'Tonight' night-planner endpoint (``/api/plan/tonight``)."""

from __future__ import annotations

from datetime import date as _date
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from webapp.site_location import parse_angle as _parse_angle
from webapp.site_location import site_from_header as _site_from_header

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
        # …and how big a mosaic, serialized through asdict as a nested dict.
        assert m31["mosaic"]["cols"] == 3
        assert m31["mosaic"]["rows"] == 2
        assert m31["mosaic"]["panels"] == 6
        assert "3×2 mosaic (6 panels)" in m31["mosaic"]["text"]
        # ...and its "how hard for a Seestar?" verdict, so the planner shows
        # difficulty while choosing (serialized through asdict → nested dict).
        assert m31["difficulty"]["level"] == "easy"
        assert m31["difficulty"]["label"] == "Easy"
        assert m31["difficulty"]["text"]


def test_tonight_already_targeted_rows_carry_object_type(client, solved_library):
    # Regression: 'already targeted' rows used to emit type="" / con="", so every
    # owned target bucketed as "Other" (flat 4 h goal) and contradicted the
    # Dashboard "Target progress" card. The already-targeted M_42 must now carry
    # its catalog classification, resolved via the same identify_object path.
    client.put("/api/settings", json={"site_lat": 51.5, "site_lon": -0.13})
    body = client.get("/api/plan/tonight", params={"when": JAN_EVENING}).json()
    m42 = next(t for t in body["targets"]
               if t["already_targeted"] and t["target_safe"] == "M_42")
    assert m42["type"] == "nebula"
    assert m42["con"] == "Ori"
    # ...and it agrees with what /api/library-progress reports for the same target.
    prog = client.get("/api/library-progress").json()
    m42_prog = next((r for r in prog if r["safe"] == "M_42"), None)
    if m42_prog is not None:
        assert m42_prog["object_type"] == m42["type"]


def test_tonight_already_targeted_rows_carry_a_user_set_goal(client, solved_library):
    """A goal the owner set has to reach the planner, or the two screens disagree
    about the same target: Tonight would say "Plenty — try something new" from the
    per-type default while the Target page correctly says "keep going"."""
    client.put("/api/settings", json={"site_lat": 51.5, "site_lon": -0.13})

    # No goal set → the field is present and null, so the per-type default applies
    # exactly as before.
    body = client.get("/api/plan/tonight", params={"when": JAN_EVENING}).json()
    m42 = next(t for t in body["targets"]
               if t["already_targeted"] and t["target_safe"] == "M_42")
    assert m42["goal_s"] is None

    put = client.put("/api/targets/M_42/integration-goal", json={"goal_s": 12 * 3600.0})
    assert put.status_code == 200
    body = client.get("/api/plan/tonight", params={"when": JAN_EVENING}).json()
    m42 = next(t for t in body["targets"]
               if t["already_targeted"] and t["target_safe"] == "M_42")
    assert m42["goal_s"] == 12 * 3600.0
    # ...and it is the same number /api/library-progress reports for that target.
    prog = client.get("/api/library-progress").json()
    m42_prog = next((r for r in prog if r["safe"] == "M_42"), None)
    if m42_prog is not None:
        assert m42_prog["goal_s"] == m42["goal_s"]

    # A catalog row the user has never shot carries no goal at all.
    catalog_row = next(t for t in body["targets"] if not t["already_targeted"])
    assert catalog_row["goal_s"] is None


def test_tonight_survives_an_unreadable_project_when_reading_goals(
    client, solved_library, monkeypatch
):
    """A project that won't open must cost that row its goal, not the whole plan."""
    from seestack.io.library import Library

    def _boom(self, safe):  # noqa: ANN001
        raise OSError("project is toast")

    monkeypatch.setattr(Library, "open_target", _boom)
    client.put("/api/settings", json={"site_lat": 51.5, "site_lon": -0.13})
    r = client.get("/api/plan/tonight", params={"when": JAN_EVENING})
    assert r.status_code == 200
    m42 = next(t for t in r.json()["targets"]
               if t["already_targeted"] and t["target_safe"] == "M_42")
    assert m42["goal_s"] is None
    # The pace read shares that same failed open, so it degrades the same way.
    assert m42["recent_pace_s"] is None


def _seed_nights(data_root, safe: str, nights: list[int], *, subs: int = 40) -> None:
    """Give one target ``len(nights)`` capture nights of ``subs`` × 30 s subs, a
    week apart, so it has a measurable recent pace. Mirrors the helper in
    ``test_library_progress.py`` — the two surfaces must agree on the number."""
    from seestack.io.library import Library
    from seestack.io.project import FrameRow

    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            for day in nights:
                base = datetime(2026, 7, day, 22, 0, 0)
                for i in range(subs):
                    ts = base + timedelta(seconds=30 * i)
                    proj.add_frame(FrameRow(
                        source_path=f"/seed/{safe}-{day}-{i}.fit",
                        timestamp_utc=ts.isoformat(),
                        exposure_s=30.0,
                        accept=True,
                    ))
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
    finally:
        lib.close()


def test_tonight_already_targeted_rows_carry_a_recent_pace(client, solved_library):
    """The planner row is where the user picks tonight's target, so it has to be
    able to say "~1 more clear night finishes this" — which needs the target's own
    recent pace, the same figure the Dashboard overview reports."""
    _seed_nights(solved_library, "M_42", [1, 8])
    client.put("/api/settings", json={"site_lat": 51.5, "site_lon": -0.13})

    body = client.get("/api/plan/tonight", params={"when": JAN_EVENING}).json()
    by_safe = {t["target_safe"]: t for t in body["targets"] if t["already_targeted"]}
    # 40 subs × 30 s = 1200 s a night, twice → median 1200 s.
    assert by_safe["M_42"]["recent_pace_s"] == 1200.0
    # ...and it is the same number /api/library-progress reports for that target,
    # so the planner and the Dashboard can never quote different ETAs.
    prog = {r["safe"]: r for r in client.get("/api/library-progress").json()}
    assert prog["M_42"]["recent_pace_s"] == by_safe["M_42"]["recent_pace_s"]

    # A target with a single ingest night has no pace — one session is not a
    # pace, so the row says nothing about nights rather than guessing.
    assert by_safe["NGC_7000"]["recent_pace_s"] is None
    # A catalog row the user has never shot carries none at all.
    catalog_row = next(t for t in body["targets"] if not t["already_targeted"])
    assert catalog_row["recent_pace_s"] is None


def test_tonight_reuses_the_cached_per_target_annotation(
    client, solved_library, monkeypatch
):
    """The pace read scans every dated frame of every target, so the planner must
    not redo it on every render — but it must never serve a stale answer either."""
    import seestack.session_recap as session_recap

    calls: list[int] = []
    real = session_recap.recent_night_pace_s

    def _counted(proj, **kw):  # noqa: ANN001
        calls.append(1)
        return real(proj, **kw)

    monkeypatch.setattr(session_recap, "recent_night_pace_s", _counted)
    client.put("/api/settings", json={"site_lat": 51.5, "site_lon": -0.13})

    client.get("/api/plan/tonight", params={"when": JAN_EVENING})
    after_first = len(calls)
    assert after_first > 0
    # Second render of the same unchanged library: served from the cache.
    client.get("/api/plan/tonight", params={"when": JAN_EVENING})
    assert len(calls) == after_first

    # Setting a goal doesn't move the registry signature (it writes project
    # meta), so the cache is dropped explicitly — the user must not have to wait
    # out a TTL to see the goal they just set.
    client.put("/api/targets/M_42/integration-goal", json={"goal_s": 9 * 3600.0})
    body = client.get("/api/plan/tonight", params={"when": JAN_EVENING}).json()
    assert len(calls) > after_first
    m42 = next(t for t in body["targets"]
               if t["already_targeted"] and t["target_safe"] == "M_42")
    assert m42["goal_s"] == 9 * 3600.0

    # New subs *do* move the signature, so they invalidate it on their own.
    before_seed = len(calls)
    _seed_nights(solved_library, "M_42", [1, 8])
    body = client.get("/api/plan/tonight", params={"when": JAN_EVENING}).json()
    assert len(calls) > before_seed
    m42 = next(t for t in body["targets"]
               if t["already_targeted"] and t["target_safe"] == "M_42")
    assert m42["recent_pace_s"] == 1200.0


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


def test_next_session_defaults_to_three_windows(client, solved_library):
    # The default is unchanged by the `want` parameter: every existing caller
    # (and the .ics download) still gets the same three-window answer.
    client.put("/api/settings", json={"site_lat": 51.5, "site_lon": -0.13})
    r = client.get("/api/plan/next-session/M_42", params={"when": JAN_EVENING})
    assert r.status_code == 200
    assert len(r.json()["windows"]) == 3


def test_next_session_want_returns_more_windows_for_a_longer_goal(client, solved_library):
    # A goal that needs 5 more clear nights used to get *no* finish date at all,
    # because the endpoint only ever returned three windows to count against.
    # Asking for more is a bigger slice of the same 14-night scan.
    client.put("/api/settings", json={"site_lat": 51.5, "site_lon": -0.13})
    r = client.get("/api/plan/next-session/M_42",
                   params={"when": JAN_EVENING, "want": 5})
    assert r.status_code == 200
    body = r.json()
    wins = body["windows"]
    assert len(wins) == 5
    # Still the same scan, still chronological, and the first three are exactly
    # the ones the default request returns.
    assert body["nights_scanned"] == 14
    assert [w["dark_start_utc"] for w in wins] == sorted(w["dark_start_utc"] for w in wins)
    default = client.get("/api/plan/next-session/M_42",
                         params={"when": JAN_EVENING}).json()["windows"]
    assert [w["dark_start_utc"] for w in wins[:3]] == [w["dark_start_utc"] for w in default]


def test_next_session_want_is_bounded(client, solved_library):
    # Bounded on both ends so one request can't be turned into a long grind, and
    # so "0 windows" can't be asked for. Out-of-range is a 422, not a silent clamp.
    client.put("/api/settings", json={"site_lat": 51.5, "site_lon": -0.13})
    for bad in (0, -1, 9, 1000):
        r = client.get("/api/plan/next-session/M_42",
                       params={"when": JAN_EVENING, "want": bad})
        assert r.status_code == 422, bad
    r = client.get("/api/plan/next-session/M_42",
                   params={"when": JAN_EVENING, "want": 8})
    assert r.status_code == 200
    assert len(r.json()["windows"]) <= 8


def test_next_session_want_does_not_widen_the_scan_horizon(client, solved_library):
    # The 14-night scan stays the real limit: `want` slices what that scan found,
    # it never looks further ahead. Every window returned for the widest ask is
    # still inside the fortnight.
    client.put("/api/settings", json={"site_lat": 51.5, "site_lon": -0.13})
    r = client.get("/api/plan/next-session/M_42",
                   params={"when": JAN_EVENING, "want": 8})
    body = r.json()
    start = datetime.fromisoformat(JAN_EVENING)
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    horizon = start + timedelta(days=body["nights_scanned"] + 1)
    for w in body["windows"]:
        assert datetime.fromisoformat(w["dark_start_utc"]) < horizon


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


def test_next_session_ics_downloads_a_calendar_for_a_placed_target(client, solved_library):
    # One-tap "Add to calendar": the same upcoming windows, served as an .ics the
    # user's phone/desktop calendar imports.
    client.put("/api/settings", json={"site_lat": 51.5, "site_lon": -0.13})
    r = client.get("/api/plan/next-session/M_42/calendar.ics",
                   params={"when": JAN_EVENING})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/calendar")
    assert "attachment" in r.headers.get("content-disposition", "")
    assert "M_42-next-session.ics" in r.headers.get("content-disposition", "")
    body = r.text
    assert body.startswith("BEGIN:VCALENDAR")
    assert "END:VCALENDAR" in body
    assert "BEGIN:VEVENT" in body
    assert "SUMMARY:Image " in body
    assert "DTSTART:" in body and "DTEND:" in body
    # A plain-language, jargon-free description a beginner can act on.
    assert "Bring the Seestar out" in body


def test_next_session_ics_unknown_target_404s(client, solved_library):
    client.put("/api/settings", json={"site_lat": 51.5, "site_lon": -0.13})
    r = client.get("/api/plan/next-session/NOPE_404/calendar.ics",
                   params={"when": JAN_EVENING})
    assert r.status_code == 404


def test_next_session_ics_without_location_404s(client, solved_library):
    # No site → nothing to add; 404 rather than a blank file (the card hides it).
    r = client.get("/api/plan/next-session/M_42/calendar.ics",
                   params={"when": JAN_EVENING})
    assert r.status_code == 404


def test_next_session_ics_no_window_404s(client, solved_library):
    # An altitude floor Orion can't clear → no window, so the download 404s
    # instead of handing back an event-less calendar.
    client.put("/api/settings", json={"site_lat": 51.5, "site_lon": -0.13})
    r = client.get("/api/plan/next-session/M_42/calendar.ics",
                   params={"when": JAN_EVENING, "min_alt": 80})
    assert r.status_code == 404


def test_best_months_returns_a_seasonal_strip_for_a_library_target(client, solved_library):
    # The plan-ahead companion to /next-session: twelve months of observability
    # for this target, so the Target page can say "a winter target — best Nov–Feb".
    client.put("/api/settings", json={"site_lat": 51.5, "site_lon": -0.13})
    r = client.get("/api/plan/best-months/M_42", params={"when": JAN_EVENING})
    assert r.status_code == 200
    body = r.json()
    assert body["location_source"] == "settings"
    assert body["target_has_position"] is True
    assert body["year"] == 2026
    months = body["months"]
    assert [m["month"] for m in months] == list(range(1, 13))
    by_month = {m["month"]: m for m in months}
    # Orion (M42) from London: usable in deep winter, not in high summer.
    assert max(by_month[m]["usable_dark_minutes"] for m in (12, 1, 2)) > 60.0
    assert max(by_month[m]["usable_dark_minutes"] for m in (5, 6, 7)) == 0.0


def test_best_months_without_location_self_hides(client, solved_library):
    # No configured site and no SITELAT in the synth frames → empty strip (the UI
    # self-hides) with a clean 200, not a 500.
    r = client.get("/api/plan/best-months/M_42", params={"when": JAN_EVENING})
    assert r.status_code == 200
    body = r.json()
    assert body["location_source"] == "none"
    assert body["observer"] is None
    assert body["months"] == []


def test_best_months_unknown_target_404s(client, solved_library):
    client.put("/api/settings", json={"site_lat": 51.5, "site_lon": -0.13})
    r = client.get("/api/plan/best-months/NOPE_404", params={"when": JAN_EVENING})
    assert r.status_code == 404


def test_best_months_rejects_bad_when(client, solved_library):
    client.put("/api/settings", json={"site_lat": 51.5, "site_lon": -0.13})
    r = client.get("/api/plan/best-months/M_42", params={"when": "not-a-date"})
    assert r.status_code == 422


def test_moon_returns_an_interference_readout_for_a_library_target(client, solved_library):
    # "Is the Moon going to wash this out tonight?" — one honest verdict + sentence
    # for this target, so the Target page can warn before a clear night is wasted.
    client.put("/api/settings", json={"site_lat": 51.5, "site_lon": -0.13})
    r = client.get("/api/plan/moon/M_42", params={"when": JAN_EVENING})
    assert r.status_code == 200
    body = r.json()
    assert body["location_source"] == "settings"
    assert body["target_has_position"] is True
    moon = body["moon"]
    assert moon is not None
    assert 0.0 <= moon["illumination"] <= 1.0
    assert isinstance(moon["waxing"], bool)
    assert moon["phase_name"]
    assert moon["level"] in ("good", "ok", "poor")
    assert moon["text"]
    assert -90.0 <= moon["moon_altitude_deg"] <= 90.0
    assert 0.0 <= moon["separation_deg"] <= 180.0


def test_moon_without_location_self_hides(client, solved_library):
    # No configured site and no SITELAT in the synth frames → null readout (the
    # card self-hides) with a clean 200, not a 500.
    r = client.get("/api/plan/moon/M_42", params={"when": JAN_EVENING})
    assert r.status_code == 200
    body = r.json()
    assert body["location_source"] == "none"
    assert body["moon"] is None


def test_moon_unknown_target_404s(client, solved_library):
    client.put("/api/settings", json={"site_lat": 51.5, "site_lon": -0.13})
    r = client.get("/api/plan/moon/NOPE_404", params={"when": JAN_EVENING})
    assert r.status_code == 404


def test_moon_rejects_bad_when(client, solved_library):
    client.put("/api/settings", json={"site_lat": 51.5, "site_lon": -0.13})
    r = client.get("/api/plan/moon/M_42", params={"when": "not-a-date"})
    assert r.status_code == 422


def test_suggest_without_location_self_hides(client, solved_library):
    # No configured site and the synth frames carry no SITELAT → nothing to
    # suggest, but a clean 200 with an empty list so the card just self-hides.
    r = client.get("/api/plan/suggest", params={"when": JAN_EVENING})
    assert r.status_code == 200
    body = r.json()
    assert body["location_source"] == "none"
    assert body["observer"] is None
    assert body["suggestions"] == []


def test_suggest_returns_new_showpieces(client, solved_library):
    # "Try something new tonight": with a site set, a few famous, well-placed
    # showpieces the user hasn't captured, each with a plain-language blurb.
    client.put("/api/settings", json={"site_lat": 51.5, "site_lon": -0.13})
    r = client.get("/api/plan/suggest", params={"when": JAN_EVENING})
    assert r.status_code == 200
    body = r.json()
    assert body["location_source"] == "settings"
    sugg = body["suggestions"]
    assert sugg, "expected some new showpieces up on a January night from London"
    assert len(sugg) <= 3
    scores = [s["score"] for s in sugg]
    assert scores == sorted(scores, reverse=True)  # best-first
    for s in sugg:
        assert s["blurb"]                      # tells the beginner what it is
        assert s["max_altitude_deg"] > 30.0    # genuinely up
        assert s["minutes_above_min_alt"] >= 45.0
        # The library's M_42 (Orion) is "already have it" — never suggested.
        assert not (abs(s["ra_deg"] - 83.6) < 1.0 and abs(s["dec_deg"] + 5.4) < 1.0)


def test_suggest_ics_downloads_a_calendar_for_a_showpiece(client, solved_library):
    # One-tap "Add to calendar" for a *suggested* (not-yet-captured) target.
    client.put("/api/settings", json={"site_lat": 51.5, "site_lon": -0.13})
    r = client.get("/api/plan/suggest/M81/calendar.ics", params={"when": JAN_EVENING})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/calendar")
    assert "attachment" in r.headers.get("content-disposition", "")
    assert "M81-next-session.ics" in r.headers.get("content-disposition", "")
    body = r.text
    assert body.startswith("BEGIN:VCALENDAR")
    assert "BEGIN:VEVENT" in body
    assert "SUMMARY:Image Bode's Galaxy" in body
    assert "Bring the Seestar out" in body


def test_suggest_ics_non_showpiece_id_404s(client, solved_library):
    # M1 is a real catalog object but NOT on the showpiece whitelist — the .ics is
    # only meant to back the suggestion card, so it 404s rather than calendaring
    # an arbitrary catalog row.
    client.put("/api/settings", json={"site_lat": 51.5, "site_lon": -0.13})
    assert client.get("/api/plan/suggest/M1/calendar.ics",
                      params={"when": JAN_EVENING}).status_code == 404
    assert client.get("/api/plan/suggest/NOPE_404/calendar.ics",
                      params={"when": JAN_EVENING}).status_code == 404


def test_suggest_ics_without_location_404s(client, solved_library):
    # No site → nothing to add; 404 rather than a blank file (the card hides it).
    r = client.get("/api/plan/suggest/M81/calendar.ics", params={"when": JAN_EVENING})
    assert r.status_code == 404


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


# ---- "Best use of your scope right now" (/api/plan/best-tonight) -------------

# Around M 42's transit from London — the one library target these fixtures have.
JAN_MIDNIGHT = "2026-01-16T00:00:00+00:00"


def test_best_tonight_ranks_the_users_own_targets(client, solved_library):
    client.put("/api/settings", json={"site_lat": 51.5, "site_lon": -0.13})
    body = client.get("/api/plan/best-tonight",
                      params={"when": JAN_MIDNIGHT, "min_alt": 20}).json()
    assert body["location_source"] == "settings"
    assert body["observer"]["lat_deg"] == 51.5
    assert body["dark_now"] is True
    assert body["dark_minutes_left"] > 0
    pick = next(p for p in body["picks"] if p["safe"] == "M_42")
    # It only ever ranks the user's *own* targets — never the bundled catalog.
    owned = {t["safe_name"] for t in client.get("/api/targets").json()}
    assert {p["safe"] for p in body["picks"]} <= owned
    assert pick["altitude_now_deg"] is not None
    assert 0.0 < pick["noise_gain"] <= 1.0
    assert "M_42" in pick["reason"]
    assert "up right now" in pick["reason"]


def test_best_tonight_without_location_still_answers_the_depth_half(client, solved_library):
    """No site configured and no SITELAT in the synth headers: rather than 500 or
    go blank, it ranks on "would more subs help?" and says the placement is
    unknown."""
    body = client.get("/api/plan/best-tonight", params={"when": JAN_MIDNIGHT}).json()
    assert body["location_source"] == "none"
    assert body["observer"] is None
    assert body["dark_now"] is False
    assert body["picks"], "the depth-only half is still worth answering"
    assert all(p["altitude_now_deg"] is None for p in body["picks"])
    # Said once on the answer, not repeated inside every pick's own sentence.
    assert "Set your location in Settings" in body["note"]
    assert all("Set your location" not in p["reason"] for p in body["picks"])


def test_best_tonight_honours_the_limit_and_rejects_a_bad_when(client, solved_library):
    client.put("/api/settings", json={"site_lat": 51.5, "site_lon": -0.13})
    body = client.get("/api/plan/best-tonight",
                      params={"when": JAN_MIDNIGHT, "min_alt": 20, "limit": 1}).json()
    assert len(body["picks"]) <= 1
    assert client.get("/api/plan/best-tonight",
                      params={"when": "not-a-time"}).status_code == 422


def test_best_tonight_goes_quiet_when_nothing_is_up(client, solved_library):
    """A floor nothing clears leaves an empty list, so the card can just hide
    itself instead of recommending something that isn't there."""
    client.put("/api/settings", json={"site_lat": 51.5, "site_lon": -0.13})
    body = client.get("/api/plan/best-tonight",
                      params={"when": JAN_MIDNIGHT, "min_alt": 80}).json()
    assert body["picks"] == []


# --- "Nudge it this way, before you start" ---------------------------------- #
#
# The framing verdict on a finished picture already says *which way* to move the
# scope next time — but on the card you read the morning after. The planner is
# the screen you read while pointing, so the nudge is repeated there.

def _add_stack_run(data_root, safe: str, *, ra: float, dec: float,
                   w: int = 4000, h: int = 3000, arcsec_per_px: float = 3.0,
                   when: str = "2026-05-01T00:00:00Z") -> int:
    """Register a stack run whose master FITS carries a TAN WCS centred on
    (ra, dec) — the geometry the framing verdict reads, as in production."""
    import numpy as np
    from astropy.io import fits

    from seestack.io.library import Library
    from seestack.io.project import StackRunRow

    lib = Library.open_or_create(data_root / "library")
    try:
        tdir = Path(lib.target_dir(lib.find_target(safe)))
        fits_path = tdir / f"plan_framing_{ra}_{dec}_{when[:10]}.fits"
        hdu = fits.PrimaryHDU(data=np.zeros((3, h, w), dtype=np.float32))
        hdr = hdu.header
        hdr["CTYPE1"] = "RA---TAN"
        hdr["CTYPE2"] = "DEC--TAN"
        hdr["CRPIX1"] = w / 2 + 0.5
        hdr["CRPIX2"] = h / 2 + 0.5
        hdr["CRVAL1"] = ra
        hdr["CRVAL2"] = dec
        hdr["CD1_1"] = -arcsec_per_px / 3600.0
        hdr["CD1_2"] = 0.0
        hdr["CD2_1"] = 0.0
        hdr["CD2_2"] = arcsec_per_px / 3600.0
        hdu.writeto(fits_path, overwrite=True)
        # A real stack always writes a preview beside its master, and the library
        # registry records the newest one — which is what tells the cached
        # planner roll-up that a *new* picture has landed. Registering a run
        # without one would be a fixture that never happens in production.
        preview_path = fits_path.with_name(f"{fits_path.stem}_preview.png")
        preview_path.write_bytes(b"\x89PNG\r\n\x1a\n")

        proj = lib.open_target(safe)
        try:
            run_id = proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc=when,
                output_basename=f"master_{when[:10]}", fits_path=str(fits_path),
                tiff_path=None, preview_path=str(preview_path), n_frames_used=3,
                canvas_h=h, canvas_w=w, coverage_min=1, coverage_max=3,
                options_json="{}",
            ))
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
        return run_id
    finally:
        lib.close()


def _tonight_rows(client) -> dict:
    body = client.get("/api/plan/tonight", params={"when": JAN_EVENING}).json()
    return {t["target_safe"]: t for t in body["targets"] if t["already_targeted"]}


def test_tonight_row_says_which_way_to_nudge_after_a_badly_framed_picture(
    client, solved_library
):
    """M 42's last picture was pointed 1° north of it, so half the nebula ran off
    the bottom. The planner row now says to move south *before* the next session,
    in the same words the finished picture's card uses."""
    client.put("/api/settings", json={"site_lat": 51.5, "site_lon": -0.13})
    run_id = _add_stack_run(solved_library, "M_42", ra=83.822, dec=-5.391 + 1.0)

    row = _tonight_rows(client)["M_42"]
    nudge = row["recentre_nudge"]
    assert nudge is not None
    assert nudge["direction"] == "south"
    assert nudge["degrees"] == pytest.approx(1.0, abs=0.05)
    assert nudge["short"] == "1.0° south"
    assert "nudge your Seestar about 1.0° south" in nudge["text"]

    # …and it is *the same* advice the picture's own card gives, so the two
    # screens can never disagree about which way to move the scope.
    card = client.get(f"/api/targets/M_42/stack-runs/{run_id}/framing").json()
    assert card["nudge"] == nudge


def test_tonight_row_stays_silent_when_the_last_picture_was_well_framed(
    client, solved_library
):
    """A centred picture needs no advice, and a target with no picture at all has
    nothing to go on — both say nothing rather than inventing a direction."""
    client.put("/api/settings", json={"site_lat": 51.5, "site_lon": -0.13})
    _add_stack_run(solved_library, "M_42", ra=83.822, dec=-5.391)

    rows = _tonight_rows(client)
    assert rows["M_42"]["recentre_nudge"] is None
    assert rows["NGC_7000"]["recentre_nudge"] is None       # never stacked
    catalog_row = next(
        t for t in client.get("/api/plan/tonight",
                              params={"when": JAN_EVENING}).json()["targets"]
        if not t["already_targeted"])
    assert catalog_row["recentre_nudge"] is None


def test_tonight_row_follows_the_newest_picture_not_an_old_one(
    client, solved_library
):
    """A verdict from three sessions ago must never contradict a re-pointed one:
    once the scope has been moved and a well-framed picture stacked, the row goes
    quiet even though the badly-framed run is still in the history."""
    client.put("/api/settings", json={"site_lat": 51.5, "site_lon": -0.13})
    _add_stack_run(solved_library, "M_42", ra=83.822, dec=-5.391 + 1.0,
                   when="2026-05-01T00:00:00Z")
    assert _tonight_rows(client)["M_42"]["recentre_nudge"] is not None

    _add_stack_run(solved_library, "M_42", ra=83.822, dec=-5.391,
                   when="2026-06-01T00:00:00Z")
    assert _tonight_rows(client)["M_42"]["recentre_nudge"] is None


def test_tonight_row_follows_a_new_picture_even_within_one_second(
    client, solved_library
):
    """…and it must not depend on the clock. The planner row is cached behind the
    library registry's signature, and ``last_activity_utc`` is written at
    one-second granularity — so a re-stack that adds no accepted frames and lands
    inside the same second as the previous registry write moves nothing the
    signature used to look at. The row then went on quoting the *older* picture
    for a whole 60 s TTL: telling someone to nudge a scope they had already
    moved. Reproduced by pinning the stamp back to what it was."""
    from seestack.io.library import Library

    client.put("/api/settings", json={"site_lat": 51.5, "site_lon": -0.13})
    _add_stack_run(solved_library, "M_42", ra=83.822, dec=-5.391 + 1.0,
                   when="2026-05-01T00:00:00Z")
    assert _tonight_rows(client)["M_42"]["recentre_nudge"] is not None

    lib = Library.open_or_create(solved_library / "library")
    try:
        stamp = lib.find_target("M_42").last_activity_utc
    finally:
        lib.close()
    _add_stack_run(solved_library, "M_42", ra=83.822, dec=-5.391,
                   when="2026-06-01T00:00:00Z")
    lib = Library.open_or_create(solved_library / "library")
    try:
        lib._conn.execute(
            "UPDATE targets SET last_activity_utc = ? WHERE safe_name = ?",
            (stamp, "M_42"))
        lib._conn.commit()
    finally:
        lib.close()

    assert _tonight_rows(client)["M_42"]["recentre_nudge"] is None
