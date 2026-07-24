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
