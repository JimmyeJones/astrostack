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


# --- slice (b): the shareable year — poster, caption, and the honest hero ----
#
# The year page told the story but had nothing a beginner could post. These pin
# the API half: the `.jpg` route actually resolving (it shares a path prefix
# with the JSON one, so a route-ordering slip would 422 it), the caption and
# hero riding along on the JSON, and the one thing that could quietly lie — a
# hero picture whose target was also imaged in another year.

def _register_preview(root, safe: str, image_bytes: bytes | None = None):
    """Register a stack run whose preview is a real readable PNG on disk, so the
    year poster has a hero backdrop to composite (mirrors the helper in
    ``tests/webapp/test_recap.py``)."""
    import io
    import json

    from PIL import Image

    from seestack.io.library import Library
    from seestack.io.project import StackRunRow

    lib = Library.open_or_create(root / "library")
    try:
        entry = lib.find_target(safe)
        preview_path = lib.target_dir(entry) / "master_preview.png"
        preview_path.parent.mkdir(parents=True, exist_ok=True)
        if image_bytes is None:
            buf = io.BytesIO()
            Image.new("RGB", (64, 32), (255, 255, 255)).save(buf, format="PNG")
            image_bytes = buf.getvalue()
        preview_path.write_bytes(image_bytes)
        proj = lib.open_target(safe)
        try:
            proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc="2026-05-02T00:00:00Z",
                output_basename="master", fits_path=None, tiff_path=None,
                preview_path=str(preview_path), n_frames_used=3,
                canvas_h=320, canvas_w=480, coverage_min=1, coverage_max=3,
                options_json=json.dumps({}),
            ))
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
    finally:
        lib.close()
    return preview_path


def test_year_poster_downloads_as_a_square_jpeg(client, built_library):
    """The `.jpg` route resolves — it shares its prefix with `/{year}`, whose
    int path param would 422 on "2024.jpg" if the ordering ever slipped."""
    import io
    from datetime import date

    from PIL import Image

    lib = _library(built_library)
    try:
        _set_night(lib, "M_42", date(2024, 11, 3), 22, 60.0)
    finally:
        lib.close()

    r = client.get("/api/recap/year/2024.jpg")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg"
    assert "my-2024-under-the-stars.jpg" in r.headers["content-disposition"]
    with Image.open(io.BytesIO(r.content)) as img:
        assert img.size[0] == img.size[1]


def test_year_poster_uses_that_years_own_best_picture(client, solved_library):
    """The backdrop is the year's hero, not the plain deep-space background."""
    import io
    from datetime import date

    from PIL import Image

    lib = _library(solved_library)
    try:
        _set_night(lib, "M_42", date(2024, 11, 3), 22, 60.0)
    finally:
        lib.close()
    _register_preview(solved_library, "M_42")

    r = client.get("/api/recap/year/2024.jpg")
    assert r.status_code == 200
    with Image.open(io.BytesIO(r.content)) as img:
        corner = img.convert("RGB").getpixel((2, img.size[1] - 2))
    # A white hero, veiled: lighter than the plain background, dark enough that
    # the poster text stays readable over it.
    assert all(60 < c < 210 for c in corner), corner


def test_year_poster_survives_an_unreadable_preview(client, solved_library):
    """A deleted or corrupt preview falls back to the plain backdrop, never a
    500 — previews are regenerated artifacts, not user data."""
    import io
    from datetime import date

    from PIL import Image

    lib = _library(solved_library)
    try:
        _set_night(lib, "M_42", date(2024, 11, 3), 22, 60.0)
    finally:
        lib.close()
    _register_preview(solved_library, "M_42", image_bytes=b"not really a png")

    r = client.get("/api/recap/year/2024.jpg")
    assert r.status_code == 200
    with Image.open(io.BytesIO(r.content)) as img:
        assert img.size[0] == img.size[1]


def test_year_poster_backdrop_is_the_cover_you_pinned(client, solved_library):
    """The year poster is the other surface that read ``last_stack_preview``
    directly, so it too could show a picture the owner deliberately demoted."""
    import io
    import json
    from datetime import date

    from PIL import Image

    from seestack.io.library import Library
    from seestack.io.project import StackRunRow

    def register(basename, rgb, timestamp):
        lib = Library.open_or_create(solved_library / "library")
        try:
            preview = lib.target_dir(lib.find_target("M_42")) / f"{basename}.png"
            preview.parent.mkdir(parents=True, exist_ok=True)
            buf = io.BytesIO()
            Image.new("RGB", (64, 32), rgb).save(buf, format="PNG")
            preview.write_bytes(buf.getvalue())
            proj = lib.open_target("M_42")
            try:
                run_id = proj.add_stack_run(StackRunRow(
                    id=None, timestamp_utc=timestamp,
                    output_basename=basename, fits_path=None, tiff_path=None,
                    preview_path=str(preview), n_frames_used=3,
                    canvas_h=320, canvas_w=480, coverage_min=1, coverage_max=3,
                    options_json=json.dumps({}),
                ))
            finally:
                proj.close()
            lib.refresh_target_stats("M_42")
            return run_id
        finally:
            lib.close()

    def corner():
        r = client.get("/api/recap/year/2024.jpg")
        assert r.status_code == 200
        with Image.open(io.BytesIO(r.content)) as img:
            return img.convert("RGB").getpixel((2, img.size[1] - 2))

    lib = _library(solved_library)
    try:
        _set_night(lib, "M_42", date(2024, 11, 3), 22, 60.0)
    finally:
        lib.close()
    favourite = register("favourite", (255, 255, 255), "2026-05-01T00:00:00Z")
    register("newer", (0, 0, 0), "2026-05-09T00:00:00Z")

    unpinned = corner()
    assert max(unpinned) < 60, unpinned

    lib = _library(solved_library)
    try:
        lib.set_target_cover("M_42", favourite)
    finally:
        lib.close()
    pinned = corner()
    assert all(60 < c < 210 for c in pinned), pinned


def test_year_poster_404s_for_a_year_with_no_nights(client, built_library):
    """A poster about a year of nothing is a wall of nothing — the page's empty
    state already says where the nights actually are."""
    from datetime import date

    lib = _library(built_library)
    try:
        _set_night(lib, "M_42", date(2024, 11, 3), 22, 60.0)
    finally:
        lib.close()

    assert client.get("/api/recap/year/2019.jpg").status_code == 404


def test_year_poster_rejects_a_year_out_of_range(client, built_library):
    assert client.get("/api/recap/year/1200.jpg").status_code == 422


def test_year_recap_carries_a_caption_to_post_beside_the_poster(client,
                                                                built_library):
    from datetime import date

    lib = _library(built_library)
    try:
        _set_night(lib, "M_42", date(2024, 11, 3), 22, 60.0)     # 3 × 60 s
        _set_night(lib, "NGC_7000", date(2025, 2, 14), 21, 30.0)  # a different year
    finally:
        lib.close()

    data = client.get("/api/recap/year/2024").json()
    assert data["caption"] == (
        "2024 under the stars · 1 night out · 3 min of light · 1 target · "
        "first light: M_42")


def test_an_empty_year_offers_no_caption(client, built_library):
    from datetime import date

    lib = _library(built_library)
    try:
        _set_night(lib, "M_42", date(2024, 11, 3), 22, 60.0)
    finally:
        lib.close()

    assert client.get("/api/recap/year/2019").json()["caption"] == ""


def test_year_hero_is_a_target_shot_that_year_and_links_to_it(client,
                                                              solved_library):
    from datetime import date

    lib = _library(solved_library)
    try:
        _set_night(lib, "M_42", date(2024, 11, 3), 22, 60.0)
        _set_night(lib, "NGC_7000", date(2025, 2, 14), 21, 30.0)
    finally:
        lib.close()
    # Both targets have a picture; only M 42 has a night in 2024.
    _register_preview(solved_library, "M_42")
    _register_preview(solved_library, "NGC_7000")

    hero = client.get("/api/recap/year/2024").json()["hero"]
    assert hero is not None
    assert hero["name"] == "M_42"
    assert hero["thumbnail_url"] == "/api/targets/M_42/thumbnail"
    # Shot in 2024 and no other year — nothing to caveat.
    assert hero["note"] == ""


def test_year_hero_says_so_when_its_picture_may_carry_another_years_light(
        client, solved_library):
    """The hero's preview is its *newest* stack. A target imaged across two
    years must not be presented as if the pixels were all this year's."""
    from datetime import date

    lib = _library(solved_library)
    try:
        _set_night(lib, "M_42", date(2024, 11, 3), 22, 60.0)
        _set_night(lib, "NGC_7000", date(2025, 2, 14), 21, 30.0)
        # …and M 42 was shot again the following June, so its newest stack can
        # no longer be honestly captioned as "your 2024".
        proj = lib.open_target("M_42")
        try:
            first = list(proj.iter_frames())[0]
            proj.update_frame(first.id, timestamp_utc="2025-06-01T22:00:00Z")
        finally:
            proj.close()
        lib.refresh_target_stats("M_42")
    finally:
        lib.close()
    _register_preview(solved_library, "M_42")

    data = client.get("/api/recap/year/2024").json()
    assert data["years_with_data"] == [2024, 2025]
    hero = data["hero"]
    assert hero["name"] == "M_42"
    assert "other years" in hero["note"]


def test_year_with_no_picture_yet_reports_no_hero(client, built_library):
    """A library that has captured but never stacked: the year still has its
    story, and the share card simply offers the poster without a backdrop."""
    from datetime import date

    lib = _library(built_library)
    try:
        _set_night(lib, "M_42", date(2024, 11, 3), 22, 60.0)
    finally:
        lib.close()

    data = client.get("/api/recap/year/2024").json()
    assert data["has_anything"] is True
    assert data["hero"] is None
