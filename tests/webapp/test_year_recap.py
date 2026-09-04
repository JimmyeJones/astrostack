"""API tests for ``GET /api/recap/year/{year}`` — "Your year under the stars".

The endpoint is a year-shaped slice of the same night fold the Dashboard
heatmap uses, so these pin the two things only the API layer can get wrong: that
the year boundary is honoured against real project data, and that the response
stays honest (and linkable) on the edges — a year with nothing in it, a bad year
in the path, and a first-light target that no longer exists in the registry.
"""

from __future__ import annotations

from datetime import datetime, timezone


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


def _library(built_library):
    from seestack.io.library import Library

    return Library.open_or_create(built_library / "library")


def test_year_recap_counts_only_that_years_nights(client, built_library):
    from datetime import date

    lib = _library(built_library)
    try:
        # M 42 in 2024, NGC 7000 in 2025 — two different years, one library.
        _set_night(lib, "M_42", date(2024, 11, 3), 22, 60.0)       # 3 × 60 s
        _set_night(lib, "NGC_7000", date(2025, 2, 14), 21, 30.0)   # 3 × 30 s
    finally:
        lib.close()

    r = client.get("/api/recap/year/2024")
    assert r.status_code == 200
    data = r.json()
    assert data["year"] == 2024
    assert data["has_anything"] is True
    assert data["n_nights"] == 1
    assert data["n_frames"] == 3
    assert data["total_exposure_s"] == 180.0
    assert data["target_names"] == ["M_42"]
    assert data["years_with_data"] == [2024, 2025]
    assert "2024" in data["headline"]
    assert data["empty_message"] == ""

    other = client.get("/api/recap/year/2025").json()
    assert other["n_nights"] == 1
    assert other["total_exposure_s"] == 90.0
    assert other["target_names"] == ["NGC_7000"]


def test_year_recap_first_lights_link_to_their_targets(client, built_library):
    from datetime import date

    lib = _library(built_library)
    try:
        _set_night(lib, "M_42", date(2025, 1, 5), 22, 60.0)
        _set_night(lib, "NGC_7000", date(2025, 3, 9), 21, 60.0)
    finally:
        lib.close()

    data = client.get("/api/recap/year/2025").json()
    # Both targets are new this year, in the order they were first shot, each
    # carrying the safe name the page links with.
    assert [f["name"] for f in data["first_lights"]] == ["M_42", "NGC_7000"]
    assert [f["safe"] for f in data["first_lights"]] == ["M_42", "NGC_7000"]
    assert data["first_light_line"] == "First light: M_42 and NGC_7000"

    # A target first shot in an earlier year is not a first light in a later one.
    later = client.get("/api/recap/year/2026").json()
    assert later["first_lights"] == []


def test_year_recap_names_the_longest_and_sharpest_nights(client, built_library):
    from datetime import date

    lib = _library(built_library)
    try:
        _set_night(lib, "M_42", date(2025, 1, 5), 22, 30.0)       # 90 s
        _set_night(lib, "NGC_7000", date(2025, 3, 9), 21, 600.0)  # 1800 s
    finally:
        lib.close()

    data = client.get("/api/recap/year/2025").json()
    assert data["longest_night"]["date"] == "2025-03-09"
    assert data["longest_night"]["exposure_s"] == 1800.0
    # Nothing in the fixture carries enough measured star sizes to name a
    # sharpest night, and the endpoint says so rather than inventing one.
    assert data["sharpest_night"] is None


def test_empty_year_offers_the_years_that_do_have_data(client, built_library):
    from datetime import date

    lib = _library(built_library)
    try:
        _set_night(lib, "M_42", date(2024, 11, 3), 22, 60.0)
    finally:
        lib.close()

    data = client.get("/api/recap/year/2026").json()
    assert data["has_anything"] is False
    assert data["n_nights"] == 0
    assert data["stats"] == []
    assert data["headline"] == ""
    assert data["years_with_data"] == [2024]
    assert "2024" in data["empty_message"]


def test_year_recap_on_an_empty_library_is_kind_not_an_error(client, data_root):
    data = client.get("/api/recap/year/2026").json()
    assert data["has_anything"] is False
    assert data["years_with_data"] == []
    assert "No nights recorded in 2026 yet" in data["empty_message"]


def test_year_out_of_range_is_rejected(client, built_library):
    assert client.get("/api/recap/year/1234").status_code == 422
    assert client.get("/api/recap/year/99999").status_code == 422
    assert client.get("/api/recap/year/not-a-year").status_code == 422


def test_year_recap_counts_accepted_frames_only(client, built_library):
    # The year rides the same fold as the heatmap, which counts kept subs — so a
    # clouded-out, fully-rejected night must not inflate the year's hours.
    from datetime import date

    lib = _library(built_library)
    try:
        _set_night(lib, "M_42", date(2025, 1, 5), 22, 60.0)
        _set_night(lib, "NGC_7000", date(2025, 3, 9), 21, 60.0)
        proj = lib.open_target("NGC_7000")
        try:
            for f in proj.iter_frames():
                proj.update_frame(f.id, accept=0)
        finally:
            proj.close()
    finally:
        lib.close()

    data = client.get("/api/recap/year/2025").json()
    assert data["n_nights"] == 1
    assert data["total_exposure_s"] == 180.0
    assert data["target_names"] == ["M_42"]


def test_year_recap_and_activity_calendar_agree_about_a_night(client, built_library):
    """One fold, one set of numbers — the year page and the heatmap cannot
    describe the same night differently."""
    from datetime import date

    now_year = datetime.now(timezone.utc).year
    lib = _library(built_library)
    try:
        _set_night(lib, "M_42", date(now_year, 1, 20), 22, 45.0)
        # Park the other target well outside the year under test so the year's
        # totals are exactly the one night the heatmap is being compared on.
        _set_night(lib, "NGC_7000", date(now_year - 3, 6, 1), 21, 45.0)
    finally:
        lib.close()

    cal = client.get("/api/activity-calendar?months=24").json()
    year = client.get(f"/api/recap/year/{now_year}").json()
    cal_nights = {n["date"]: n for n in cal["nights"]}
    assert cal_nights[f"{now_year}-01-20"]["exposure_s"] == year["total_exposure_s"]
    assert cal_nights[f"{now_year}-01-20"]["n_frames"] == year["n_frames"]
    assert year["longest_night"] is None  # one night in the year — nothing to rank
