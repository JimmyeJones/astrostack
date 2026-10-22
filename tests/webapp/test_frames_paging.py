"""`GET /api/targets/<t>/frames` pages in SQLite, not in Python.

The frames table fetches the whole target 2,000 rows at a time until it gets a
short page (`api.listFrames`), so what one visit costs is *per request* × the
number of pages. The endpoint used to answer each one by reading every row of
the target, building a `FrameRow` for each, sorting in Python and discarding all
but the window. On the owner's deepest target — 35,894 subs — that is eighteen
full reads per visit: measured at **9.09 s / 163.6 MB peak** against
**2.42 s / 83.5 MB** once SQLite does the sort and the slice.

The ordering is unchanged and pinned against the Python sort in
`tests/test_project_frames_page.py`. What is pinned *here* is the property that
lives at the endpoint: a page costs a page's worth of rows.
"""

from __future__ import annotations


def _built(client, request_row_count):
    rows = client.get("/api/targets/M_42/frames").json()
    assert len(rows) == 3
    return rows


def test_a_page_request_builds_only_that_pages_rows(client, built_library):
    # The regression this guards is invisible from the outside: re-introduce a
    # whole-table read and every response stays byte-identical while the cost
    # goes back to O(target). Counting the rows the endpoint turns into objects
    # is the only way to see it, and it is the thing the change is for.
    from framerows import frame_rows_built_by

    from webapp.routers import frames as frames_router

    all_rows = client.get("/api/targets/M_42/frames").json()
    assert len(all_rows) == 3, "fixture must have more frames than the page asks for"

    # Attributed to the endpoint's own stack, not to the process — see
    # `tests/framerows.py` for the leaked `job-worker` this used to count. It
    # matters doubly here, where the expected count is one rather than zero: a
    # stray row would read as the page's own.
    with frame_rows_built_by(frames_router.list_frames) as built:
        page = client.get(
            "/api/targets/M_42/frames",
            params={"sort": "fwhm_px", "order": "desc", "limit": 1},
        ).json()
    assert len(page) == 1
    assert built() == 1, f"built {built()} frame rows to serve a 1-row page"


def test_paging_through_a_target_visits_every_frame_exactly_once(client, built_library):
    # What `api.listFrames` actually does: fixed-size pages until a short one.
    # A sort whose values tie (here: every frame shares an exposure) is where an
    # unstable order would repeat a row in one page and drop it from another.
    seen: list[int] = []
    page_size = 2
    for offset in range(0, 10, page_size):
        page = client.get(
            "/api/targets/M_42/frames",
            params={"sort": "exposure_s", "limit": page_size, "offset": offset},
        ).json()
        seen += [f["id"] for f in page]
        if len(page) < page_size:
            break
    whole = [f["id"] for f in client.get(
        "/api/targets/M_42/frames", params={"sort": "exposure_s"}).json()]
    assert seen == whole
    assert sorted(seen) == sorted(whole) and len(set(seen)) == len(seen)


def test_an_unknown_sort_still_falls_back_to_id_rather_than_erroring(
        client, built_library):
    # The engine raises on a column it doesn't know; the endpoint's allow-list
    # is what keeps that from ever reaching a user as a 500.
    rows = client.get(
        "/api/targets/M_42/frames",
        params={"sort": "id; DROP TABLE frames", "order": "asc"},
    ).json()
    ids = [f["id"] for f in rows]
    assert ids == sorted(ids)
    assert len(client.get("/api/targets/M_42/frames").json()) == 3


def test_a_frame_row_carries_its_plate_scale(client, built_library):
    # The Target page's mixed-pointing guard scales its link from the subs' own
    # solved field (scale × size), so the row has to carry the scale. Additive:
    # an unsolved sub sends null.
    from seestack.io.library import Library

    rows = client.get("/api/targets/M_42/frames").json()
    assert all(r["pixscale_arcsec"] is None for r in rows)
    lib = Library.open_or_create(built_library / "library")
    try:
        proj = lib.open_target("M_42")
        try:
            proj.update_frame(rows[0]["id"], pixscale_arcsec=3.99)
        finally:
            proj.close()
    finally:
        lib.close()
    rows = client.get("/api/targets/M_42/frames").json()
    assert rows[0]["pixscale_arcsec"] == 3.99
