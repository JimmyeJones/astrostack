"""A frame id or page window past SQLite's 64-bit integer is "no such row", not a 500.

Every other int query param in the routers is clamped, and every run-id route looks
its run up in Python, so the Scout's 2026-11-11 crawl of all 169 GET routes with
hostile numbers found exactly these four 500s: `sqlite3` raises ``OverflowError``
binding an int it cannot store, and nothing between the route and the cursor
caught it. No screen sends such a number; the point is that the frames routes
answer it the way they answer any other id that names nothing.
"""

from __future__ import annotations

import pytest

TOO_BIG = 2 ** 63  # one past SQLite's INTEGER range
HUGE = 10 ** 20


@pytest.mark.parametrize("frame_id", [TOO_BIG, HUGE, -(2 ** 63) - 1])
def test_a_frame_id_sqlite_cannot_store_is_404(client, built_library, frame_id):
    r = client.get(f"/api/targets/M_42/frames/{frame_id}")
    assert r.status_code == 404, r.text
    r = client.get(f"/api/targets/M_42/frames/{frame_id}/preview")
    assert r.status_code == 404, r.text
    r = client.patch(f"/api/targets/M_42/frames/{frame_id}", json={"accept": False})
    assert r.status_code == 404, r.text


def test_a_page_window_past_sqlite_range_is_clamped(client, built_library):
    every = client.get("/api/targets/M_42/frames").json()
    assert len(every) == 3

    r = client.get("/api/targets/M_42/frames", params={"offset": HUGE})
    assert r.status_code == 200, r.text
    assert r.json() == []

    r = client.get("/api/targets/M_42/frames", params={"limit": HUGE})
    assert r.status_code == 200, r.text
    assert [f["id"] for f in r.json()] == [f["id"] for f in every]


def test_project_get_frame_out_of_range_is_none(built_library):
    from seestack.io.library import Library

    lib = Library.open_or_create(built_library / "library")
    try:
        proj = lib.open_target("M_42")
        try:
            assert proj.get_frame(TOO_BIG) is None
            assert proj.get_frame(-(2 ** 63) - 1) is None
            assert list(proj.iter_frames_page(offset=TOO_BIG)) == []
            assert len(list(proj.iter_frames_page(limit=TOO_BIG))) == 3
        finally:
            proj.close()
    finally:
        lib.close()
