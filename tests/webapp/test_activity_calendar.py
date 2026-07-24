"""API tests for the ``/api/activity-calendar`` imaging-calendar heatmap."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


def _set_night(lib, safe: str, day, hour_start: int, exposure_s: float) -> None:
    """Stamp all of a target's frames onto one observing night (same UTC date,
    evening hours), each with the given exposure."""
    proj = lib.open_target(safe)
    try:
        for i, f in enumerate(proj.iter_frames()):
            ts = datetime(day.year, day.month, day.day, hour_start, i * 5,
                          tzinfo=timezone.utc)
            proj.update_frame(
                f.id,
                timestamp_utc=ts.isoformat().replace("+00:00", "Z"),
                exposure_s=exposure_s,
            )
    finally:
        proj.close()


def test_activity_calendar_buckets_two_nights(client, built_library):
    from seestack.io.library import Library

    now = datetime.now(timezone.utc)
    day_a = (now - timedelta(days=9)).date()
    day_b = (now - timedelta(days=6)).date()

    lib = Library.open_or_create(built_library / "library")
    try:
        _set_night(lib, "M_42", day_a, 22, 60.0)       # 3 subs × 60 s = 180 s
        _set_night(lib, "NGC_7000", day_b, 21, 30.0)   # 3 subs × 30 s = 90 s
    finally:
        lib.close()

    r = client.get("/api/activity-calendar")
    assert r.status_code == 200
    data = r.json()
    assert data["n_nights"] == 2
    assert data["total_exposure_s"] == 270.0
    nights = {n["date"]: n for n in data["nights"]}
    assert nights[day_a.isoformat()]["exposure_s"] == 180.0
    assert nights[day_a.isoformat()]["n_frames"] == 3
    assert nights[day_a.isoformat()]["targets"] == ["M_42"]
    assert nights[day_b.isoformat()]["targets"] == ["NGC_7000"]
    # Nights are date-ascending and the window ends today.
    assert [n["date"] for n in data["nights"]] == sorted(n["date"] for n in data["nights"])
    assert data["end_date"] == now.date().isoformat()


def test_activity_calendar_empty_library_is_valid(client, data_root):
    # data_root has an incoming/ but no scanned library yet.
    r = client.get("/api/activity-calendar")
    assert r.status_code == 200
    data = r.json()
    assert data["n_nights"] == 0
    assert data["nights"] == []
    assert data["total_exposure_s"] == 0.0
    assert data["best_streak_nights"] == 0


def test_activity_calendar_months_is_clamped(client, built_library):
    r = client.get("/api/activity-calendar?months=999")
    assert r.status_code == 200
    assert r.json()["months"] == 24
    r = client.get("/api/activity-calendar?months=0")
    assert r.status_code == 200
    assert r.json()["months"] == 1


def test_activity_calendar_ignores_a_frame_with_no_timestamp(client, built_library):
    # Frames ingested by the scanner may carry no capture timestamp; those must be
    # skipped, leaving a valid empty-ish payload rather than a 500.
    r = client.get("/api/activity-calendar")
    assert r.status_code == 200
    # No timestamps were set here, so no nights are reported.
    assert r.json()["n_nights"] == 0


def _night_of_the_session(client, built_library):
    """Stamp M_42's frames onto a 03:00-UTC session ~30 days ago and return the
    single observing-night date the calendar reports for it."""
    from seestack.io.library import Library

    day = (datetime.now(timezone.utc) - timedelta(days=30)).date()
    lib = Library.open_or_create(built_library / "library")
    try:
        _set_night(lib, "M_42", day, 3, 60.0)  # 03:00 UTC — near the UTC midnight edge
    finally:
        lib.close()
    r = client.get("/api/activity-calendar")
    assert r.status_code == 200
    nights = [n for n in r.json()["nights"] if n["n_frames"] == 3]
    assert len(nights) == 1
    return day, nights[0]["date"]


def test_calendar_falls_back_to_sitelong_when_no_configured_lon(
        client, built_library, monkeypatch):
    # No site_lon in Settings, but a frame's header says we're far east (+150°,
    # ~+10 h). A 03:00-UTC session then belongs to *that* calendar day's night,
    # not the previous UTC night the bare UTC fallback would assign.
    import webapp.routers.stats as stats
    monkeypatch.setattr(stats, "detect_site_from_library",
                        lambda lib, **k: (20.0, 150.0))
    day, night = _night_of_the_session(client, built_library)
    assert night == day.isoformat()


def test_calendar_uses_utc_when_no_location_anywhere(
        client, built_library, monkeypatch):
    # No configured lon and no header site → UTC noon-to-noon: the same 03:00-UTC
    # session buckets onto the *previous* calendar day.
    import webapp.routers.stats as stats
    monkeypatch.setattr(stats, "detect_site_from_library", lambda lib, **k: None)
    day, night = _night_of_the_session(client, built_library)
    assert night == (day - timedelta(days=1)).isoformat()


def test_configured_site_lon_wins_and_skips_header_probe(
        client, built_library, monkeypatch):
    # An explicit Settings longitude must win over any header, and the FITS probe
    # must not run at all when a location is already configured.
    import webapp.routers.stats as stats

    def _boom(lib, **k):
        raise AssertionError("header probe must not run when site_lon is configured")

    monkeypatch.setattr(stats, "detect_site_from_library", _boom)
    client.put("/api/settings", json={"site_lon": 150.0})
    day, night = _night_of_the_session(client, built_library)
    assert night == day.isoformat()  # +150° → same-day night, same as the fallback
