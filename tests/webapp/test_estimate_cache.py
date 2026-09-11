"""The Stack form's canvas is held between requests — and revalidated on every one.

``/stack-estimate`` carries nine query params and only ``mosaic_canvas`` can
move the canvas the other eight are priced off, so nudging κ or the drizzle
scale used to re-read one WCS per sub (~1 s on the owner's 5,477-sub mosaic) to
refresh a sentence. :mod:`webapp.estimate_cache` keeps the basis.

The two things worth pinning are therefore opposites: that a repeat really is a
*hit* (or the module buys nothing), and that a changed frame set really is a
*miss* (or it serves a canvas built from where the subs used to be — a stale
sizing after a scan, which is its own bug). The endpoint tests below assert the
second through the HTTP layer, on the answer a user would see, not just on the
counters.
"""

from __future__ import annotations

import pytest

from webapp import estimate_cache


@pytest.fixture(autouse=True)
def _fresh_cache():
    """Each test starts from zeroed counters — the cache is process-global."""
    estimate_cache.clear()
    yield
    estimate_cache.clear()


def _safe(client) -> str:
    return client.get("/api/targets").json()[0]["safe_name"]


def test_the_rejection_knobs_no_longer_rebuild_the_canvas(client, solved_library):
    """κ, the min/max count and Auto all change the response and none of them
    is allowed to cost a canvas computation."""
    safe = _safe(client)
    base = client.get(f"/api/targets/{safe}/stack-estimate")
    assert base.status_code == 200
    assert estimate_cache.stats()["misses"] == 1

    for params in (
        {"sigma_kappa": 2.0},
        {"sigma_kappa": 5.0},
        {"sigma_clip": "false"},
        {"min_max_reject": "true", "min_max_reject_count": 3},
        {"auto_reject": "true"},
        {"drizzle": "true", "drizzle_scale": 2.0},
    ):
        r = client.get(f"/api/targets/{safe}/stack-estimate", params=params)
        assert r.status_code == 200, params
    stats = estimate_cache.stats()
    assert stats["misses"] == 1, "only the first request may build a canvas"
    assert stats["hits"] == 6


def test_the_canvas_mode_is_its_own_entry(client, solved_library):
    """``mosaic_canvas`` is the one option the canvas depends on, so it keys
    the cache rather than sharing an entry."""
    safe = _safe(client)
    client.get(f"/api/targets/{safe}/stack-estimate")
    client.get(f"/api/targets/{safe}/stack-estimate",
               params={"mosaic_canvas": "reference"})
    assert estimate_cache.stats()["misses"] == 2
    # …and each mode is then served from its own held basis.
    client.get(f"/api/targets/{safe}/stack-estimate")
    client.get(f"/api/targets/{safe}/stack-estimate",
               params={"mosaic_canvas": "reference"})
    assert estimate_cache.stats() == {"hits": 2, "misses": 2, "entries": 2}


def test_a_changed_frame_set_is_answered_freshly(client, solved_library):
    """The fail-before test: with the fingerprint check removed this serves the
    three-frame canvas for a target that now has four frames.

    A new sub landing in ``incoming/`` between two page loads is the ordinary
    case, not an exotic one — the owner shoots while the app is open.
    """
    from seestack.io.library import Library
    from seestack.io.project import FrameRow

    safe = _safe(client)
    before = client.get(f"/api/targets/{safe}/stack-estimate").json()
    assert before["n_frames"] == 3

    # A fourth sub, solved and pointing somewhere else entirely, so it both
    # changes the count and grows the union canvas.
    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target(safe)
        try:
            existing = next(iter(proj.iter_frames()))
            proj.add_frame(FrameRow(
                source_path="late_arrival.fit", cached_path="late_arrival.fit",
                width_px=existing.width_px, height_px=existing.height_px,
                bayer_pattern="RGGB", wcs_json=existing.wcs_json,
                ra_center_deg=(existing.ra_center_deg or 0.0) + 0.2,
                dec_center_deg=existing.dec_center_deg,
                pixscale_arcsec=existing.pixscale_arcsec,
            ))
        finally:
            proj.close()
    finally:
        lib.close()

    after = client.get(f"/api/targets/{safe}/stack-estimate").json()
    assert after["n_frames"] == 4, "the new sub must reach the sizing"
    assert estimate_cache.stats()["misses"] == 2


def test_a_resolve_that_moves_a_frame_is_answered_freshly(client, solved_library):
    """The sharper half of the same claim: the frame *count* is unchanged, so
    only a fingerprint over the WCS itself can catch this."""
    from seestack.io.library import Library

    safe = _safe(client)
    before = client.get(f"/api/targets/{safe}/stack-estimate").json()

    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target(safe)
        try:
            rows = list(proj.iter_frames())
            # Re-point one sub a long way off: same row count, same lengths, a
            # union canvas that must grow.
            moved = (rows[0].wcs_json or "").replace("83.6", "84.9")
            assert moved != rows[0].wcs_json
            proj.update_frame(rows[0].id, wcs_json=moved,
                              ra_center_deg=(rows[0].ra_center_deg or 0.0) + 1.3)
        finally:
            proj.close()
    finally:
        lib.close()

    after = client.get(f"/api/targets/{safe}/stack-estimate").json()
    assert estimate_cache.stats()["misses"] == 2
    assert (after["canvas_w"], after["canvas_h"]) != (before["canvas_w"],
                                                      before["canvas_h"])


def test_the_target_page_question_shares_the_held_canvas(client, solved_library):
    """``/rejection-outlook`` asks the same canvas a different question, and it
    runs on every Target-page load — so it must ride on the Stack form's basis
    rather than rebuild one."""
    safe = _safe(client)
    assert client.get(f"/api/targets/{safe}/stack-estimate").status_code == 200
    r = client.get(f"/api/targets/{safe}/rejection-outlook")
    assert r.status_code == 200
    assert estimate_cache.stats() == {"hits": 1, "misses": 1, "entries": 1}


def test_nothing_solved_yet_is_not_cached(client, built_library):
    """A target with no WCS raises rather than sizing, and a failure must not be
    remembered — the very next request after a solve has to answer."""
    safe = _safe(client)
    assert client.get(f"/api/targets/{safe}/stack-estimate").status_code == 422
    assert estimate_cache.stats() == {"hits": 0, "misses": 0, "entries": 0}
    # And the sibling endpoint's "no opinion" answer, same path.
    r = client.get(f"/api/targets/{safe}/rejection-outlook")
    assert r.status_code == 200 and r.json()["reaches"] is None
    assert estimate_cache.stats()["entries"] == 0


def test_the_cache_is_bounded(client, solved_library, monkeypatch):
    """It holds a working set, not a library. Oldest-used goes first."""
    monkeypatch.setattr(estimate_cache, "MAX_ENTRIES", 2)
    safe = _safe(client)
    for mode in ("auto", "reference", "union"):
        client.get(f"/api/targets/{safe}/stack-estimate",
                   params={"mosaic_canvas": mode})
    assert estimate_cache.stats()["entries"] == 2
    # "auto" was the least recently used, so it is the one that had to be
    # rebuilt; "union" is still held.
    client.get(f"/api/targets/{safe}/stack-estimate",
               params={"mosaic_canvas": "union"})
    assert estimate_cache.stats()["hits"] == 1
    client.get(f"/api/targets/{safe}/stack-estimate",
               params={"mosaic_canvas": "auto"})
    assert estimate_cache.stats() == {"hits": 1, "misses": 4, "entries": 2}


def test_two_targets_do_not_share_an_entry(client, solved_library, monkeypatch):
    """Keyed on the project, so moving between targets is two entries and never
    one target's canvas served for another.

    Budget pinned for the same reason as the comparison test below: it is read
    from *available* memory and drifts by kilobytes between two calls."""
    monkeypatch.setenv("ASTROSTACK_MAX_STACK_GB", "1.0")
    targets = [t["safe_name"] for t in client.get("/api/targets").json()]
    assert len(targets) >= 2
    seen = []
    for safe in targets[:2]:
        seen.append(client.get(f"/api/targets/{safe}/stack-estimate").json())
    assert estimate_cache.stats() == {"hits": 0, "misses": 2, "entries": 2}
    for safe, expected in zip(targets[:2], seen, strict=True):
        assert client.get(f"/api/targets/{safe}/stack-estimate").json() == expected
    assert estimate_cache.stats()["hits"] == 2


def test_a_held_basis_gives_the_same_answer_as_a_cold_one(
        client, solved_library, monkeypatch):
    """The whole response, byte for byte, warm against cold — the property that
    makes this a pure optimisation rather than a second sizing rule.

    The budget is pinned because it is otherwise read from the box's *available*
    memory, which moves by a few kilobytes between two calls — a difference with
    nothing to do with the cache (``tests/test_estimate_basis.py`` pins it for
    the same reason)."""
    monkeypatch.setenv("ASTROSTACK_MAX_STACK_GB", "1.0")
    safe = _safe(client)
    params = {"drizzle": "true", "drizzle_scale": 1.5, "auto_reject": "true",
              "sigma_kappa": 2.5, "min_max_reject_count": 2}
    cold = client.get(f"/api/targets/{safe}/stack-estimate", params=params).json()
    warm = client.get(f"/api/targets/{safe}/stack-estimate", params=params).json()
    estimate_cache.clear()
    cold_again = client.get(f"/api/targets/{safe}/stack-estimate",
                            params=params).json()
    assert warm == cold == cold_again
