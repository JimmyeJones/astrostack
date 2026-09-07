"""`/api/wishlist` — the objects the owner said they want to shoot.

Read-only and offline apart from one tiny registry table: the catalog ships with
the app, the capture match reads the target registry, and "is it up tonight?" is
the planner's own dark-window scoring. No ASTAP and no network.

Lyra is the fixture sky for the tonight half, for the same reason
``test_life_list_nearly_there`` uses it: from 51°N in July the Ring Nebula is
unambiguously overhead, so the assertion can't flip with the calendar.
"""

from __future__ import annotations

from seestack.io.library import Library
from seestack.io.project import FrameRow, StackRunRow

LONDON = {"site_lat": 51.5, "site_lon": -0.13}
SUMMER_NIGHT = "2026-07-15T23:00:00Z"
WINTER_EVENING = "2026-01-15T20:00:00Z"

M31 = (10.6847, 41.2687)
M57 = (283.396, 33.029)


def _register(data_root, name: str, ra: float, dec: float, *,
              n_frames: int = 6, preview: str | None = None) -> str:
    """One solved target in the registry, as a real ingest (and stack) leaves it."""
    lib = Library.open_or_create(data_root / "library")
    try:
        entry, proj = lib.create_target(name, ra_deg=ra, dec_deg=dec)
        try:
            proj.add_frames([
                FrameRow(source_path=f"{entry.safe_name}-{i}.fit")
                for i in range(n_frames)
            ])
            if preview is not None:
                proj.add_stack_run(StackRunRow(
                    id=None, timestamp_utc="2026-05-02T00:00:00Z",
                    output_basename="master", fits_path=None, tiff_path=None,
                    preview_path=preview, n_frames_used=n_frames,
                    canvas_h=320, canvas_w=480,
                    coverage_min=1, coverage_max=n_frames, options_json="{}",
                ))
        finally:
            proj.close()
        lib.refresh_target_stats(entry.safe_name)
        return entry.safe_name
    finally:
        lib.close()


# ---- the list itself ---------------------------------------------------


def test_a_fresh_install_has_an_empty_wishlist(client, data_root):
    """Nothing new appears until the owner asks for it — every surface that
    draws the list self-hides on this, which is the whole upgrade story."""
    body = client.get("/api/wishlist").json()
    assert body["items"] == []
    assert body["counts"] == {"saved": 0, "captured": 0}


def test_starring_an_object_saves_it_and_returns_the_new_list(client, data_root):
    body = client.post("/api/wishlist/M31").json()
    assert [i["catalog_id"] for i in body["items"]] == ["M31"]
    assert body["items"][0]["name"] == "Andromeda Galaxy"
    assert body["items"][0]["con"] == "And"
    assert body["items"][0]["captured"] is False
    assert body["counts"]["saved"] == 1
    # The toggle's answer *is* the refreshed state — no follow-up fetch needed.
    assert client.get("/api/wishlist").json() == body


def test_unstarring_removes_it_and_is_safe_to_repeat(client, data_root):
    client.post("/api/wishlist/M31")
    body = client.delete("/api/wishlist/M31").json()
    assert body["items"] == []
    # Two tabs can both untick it; the second must not be an error.
    assert client.delete("/api/wishlist/M31").status_code == 200


def test_starring_twice_keeps_one_row_in_its_original_place(client, data_root):
    client.post("/api/wishlist/M31")
    client.post("/api/wishlist/M42")
    body = client.post("/api/wishlist/M31").json()
    assert [i["catalog_id"] for i in body["items"]] == ["M31", "M42"]


def test_an_object_the_catalog_does_not_know_is_refused(client, data_root):
    """The client never supplies coordinates — only ids the app can actually
    render are storable, so the wishlist can't become a way to push arbitrary
    sky positions into the planner."""
    assert client.post("/api/wishlist/NOT-A-REAL-OBJECT").status_code == 404
    assert client.get("/api/wishlist").json()["items"] == []


def test_a_wishlisted_object_you_have_shot_reads_as_captured(client, data_root):
    _register(data_root, "M 31", *M31, preview="/tmp/does-not-exist.jpg")
    body = client.post("/api/wishlist/M31").json()
    item = body["items"][0]
    assert item["captured"] is True
    assert item["safe_name"] == "M_31"
    assert item["target_name"] == "M 31"
    assert body["counts"] == {"saved": 1, "captured": 1}
    # The registry's preview path doesn't exist, so no thumbnail URL is offered
    # rather than one that 404s.
    assert item["thumbnail_url"] is None


def test_a_stacked_capture_offers_its_picture(client, data_root, tmp_path):
    preview = tmp_path / "preview.jpg"
    preview.write_bytes(b"not-really-a-jpeg")
    _register(data_root, "M 31", *M31, preview=str(preview))
    item = client.post("/api/wishlist/M31").json()["items"][0]
    assert item["thumbnail_url"] == "/api/targets/M_31/thumbnail"


def test_the_life_list_is_untouched_by_the_wishlist(client, data_root):
    """The wishlist sits beside the life list; it doesn't shadow or change it."""
    client.post("/api/wishlist/M31")
    body = client.get("/api/life-list").json()
    assert body["counts"]["messier_total"] == 110


# ---- "up tonight" ------------------------------------------------------


def test_tonight_is_empty_with_nothing_saved(client, data_root):
    client.put("/api/settings", json=LONDON)
    body = client.get("/api/wishlist/tonight", params={"when": SUMMER_NIGHT}).json()
    assert body["saved"] == 0
    assert body["up"] == []


def test_tonight_names_a_saved_object_that_is_well_placed(client, data_root):
    client.post("/api/wishlist/M57")
    client.put("/api/settings", json=LONDON)

    body = client.get("/api/wishlist/tonight", params={"when": SUMMER_NIGHT}).json()
    assert body["saved"] == 1
    assert body["location_source"] == "settings"
    assert [u["catalog_id"] for u in body["up"]] == ["M57"]
    up = body["up"][0]
    assert up["name"] == "Ring Nebula"
    assert up["max_altitude_deg"] > 60          # Lyra is overhead from 51°N
    assert up["minutes_above_min_alt"] > 45
    assert up["usable_start_utc"] and up["usable_end_utc"]
    assert up["captured"] is False


def test_tonight_says_nothing_when_the_saved_object_is_not_up(client, data_root):
    """The card must not claim an altitude the object doesn't have — it goes
    quiet instead, and ``saved`` tells the UI the list itself isn't empty."""
    client.post("/api/wishlist/M57")
    client.put("/api/settings", json=LONDON)

    body = client.get("/api/wishlist/tonight", params={"when": WINTER_EVENING}).json()
    assert body["saved"] == 1
    assert body["up"] == []


def test_tonight_without_a_location_explains_itself(client, data_root):
    client.post("/api/wishlist/M57")
    body = client.get("/api/wishlist/tonight", params={"when": SUMMER_NIGHT}).json()
    assert body["saved"] == 1
    assert body["up"] == []
    assert body["location_source"] == "none"


def test_tonight_ranks_only_what_you_saved(client, data_root):
    """The point of the feature: M31 is up on the same July night from London,
    but it is not on the list, so it is not in the answer."""
    client.post("/api/wishlist/M57")
    client.put("/api/settings", json=LONDON)
    ids = [u["catalog_id"] for u in
           client.get("/api/wishlist/tonight",
                      params={"when": SUMMER_NIGHT}).json()["up"]]
    assert ids == ["M57"]


def test_a_bad_when_is_rejected_rather_than_silently_ignored(client, data_root):
    r = client.get("/api/wishlist/tonight", params={"when": "not-a-time"})
    assert r.status_code == 422
