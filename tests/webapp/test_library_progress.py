"""GET /api/library-progress — the Dashboard "Target progress" overview card.

Read-only per-target integration inputs (total exposure, catalog object type,
any user-set goal, and the target's recent per-night pace); the readiness
verdict and the "N more clear nights" estimate are computed client-side.
"""

from __future__ import annotations


def test_progress_empty_for_a_library_with_no_light(client):
    # No targets scanned yet → nothing to report → empty list (never 500s).
    r = client.get("/api/library-progress")
    assert r.status_code == 200
    assert r.json() == []


def test_progress_lists_targets_with_integration_and_object_type(client, built_library):
    """Both built targets have collected some light, so each appears with a
    positive integration total, a resolved offline object type, and no goal."""
    body = client.get("/api/library-progress").json()
    by_safe = {row["safe"]: row for row in body}
    assert {"M_42", "NGC_7000"} <= set(by_safe)

    for safe in ("M_42", "NGC_7000"):
        row = by_safe[safe]
        assert row["total_exposure_s"] > 0
        # M 42 / NGC 7000 are both nebulae in the bundled catalog — the type is
        # resolved offline from the target name, no project open needed.
        assert row["object_type"] == "nebula"
        assert row["goal_s"] is None


def test_progress_surfaces_a_user_set_goal(client, built_library):
    """A goal set on one target is reflected in the overview so it stays in sync
    with the Target page's readiness card (which honours the same override)."""
    put = client.put("/api/targets/M_42/integration-goal", json={"goal_s": 6 * 3600.0})
    assert put.status_code == 200

    body = client.get("/api/library-progress").json()
    by_safe = {row["safe"]: row for row in body}
    assert by_safe["M_42"]["goal_s"] == 6 * 3600.0
    # An untouched target keeps the per-type default (no stored goal).
    assert by_safe["NGC_7000"]["goal_s"] is None


def _seed_nights(data_root, safe: str, nights: list[int], *, subs: int = 40) -> None:
    """Give one target ``len(nights)`` capture nights of ``subs`` × 30 s subs, a
    week apart, so it has a measurable recent pace."""
    from datetime import datetime, timedelta

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


def test_progress_reports_a_recent_pace_for_a_target_with_several_nights(
    client, built_library
):
    """Two productive nights → the overview carries the median kept integration
    per night, which is what turns "how far to go?" into "N more clear nights"."""
    _seed_nights(built_library, "M_42", [1, 8])

    body = client.get("/api/library-progress").json()
    by_safe = {row["safe"]: row for row in body}
    # 40 subs × 30 s = 1200 s per night, both nights the same → median 1200 s.
    assert by_safe["M_42"]["recent_pace_s"] == 1200.0
    # The untouched target has a single ingest night, which is not a pace.
    assert by_safe["NGC_7000"]["recent_pace_s"] is None


def test_progress_pace_is_absent_for_a_single_night_target(client, built_library):
    """One session is not a pace — the field is present but null, so the card
    simply says nothing about nights rather than guessing."""
    body = client.get("/api/library-progress").json()
    for row in body:
        assert "recent_pace_s" in row
        assert row["recent_pace_s"] is None


def _seed_split_nights(data_root, safe: str, nights: list[int], *, subs: int = 20) -> None:
    """Give one target ``len(nights)`` capture nights that were each shot in *two
    goes* — 21:00, then 05:00 the next morning — which is one observing night but
    two 6 h-gap capture sessions."""
    from datetime import datetime, timedelta

    from seestack.io.library import Library
    from seestack.io.project import FrameRow

    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            for day in nights:
                evening = datetime(2026, 7, day, 21, 0, 0)
                for half, base in ((0, evening), (1, evening + timedelta(hours=8))):
                    for i in range(subs):
                        ts = base + timedelta(seconds=30 * i)
                        proj.add_frame(FrameRow(
                            source_path=f"/seed/{safe}-{day}-{half}-{i}.fit",
                            timestamp_utc=ts.isoformat(),
                            exposure_s=30.0,
                            accept=True,
                        ))
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
    finally:
        lib.close()


def test_progress_pace_counts_a_split_night_once(client, built_library):
    """A night shot in two goes is one clear night's worth of light, not two
    half-nights. Counting the halves separately halved the pace, and the pace is
    the divisor behind "about N more clear nights" — so the card told a beginner
    they needed twice as many clear nights as they really did."""
    # Pin the observing-night bucketing so the assertion doesn't depend on
    # whatever longitude the fixture's headers happen to carry.
    assert client.put("/api/settings", json={"site_lon": 0.0}).status_code == 200
    _seed_split_nights(built_library, "M_42", [1, 8, 15])

    body = client.get("/api/library-progress").json()
    by_safe = {row["safe"]: row for row in body}
    # 2 × 20 subs × 30 s = 1200 s per night; each half alone is only 600 s.
    assert by_safe["M_42"]["recent_pace_s"] == 1200.0


def test_progress_pace_agrees_with_the_targets_nights_card(client, built_library):
    """The two surfaces quote the same ETA for the same picture: the Dashboard
    divides by this server-side pace, the Target page derives its own from the
    rows of ``/api/targets/{safe}/nights``. Both must see the same nights."""
    from statistics import median

    assert client.put("/api/settings", json={"site_lon": 0.0}).status_code == 200
    _seed_split_nights(built_library, "M_42", [1, 8, 15])

    nights = client.get("/api/targets/M_42/nights").json()
    # One row per observing night, each spanning both of its halves (plus the
    # fixture library's own small ingest night).
    assert [n["night_date"] for n in nights][:3] == [
        "2026-07-15", "2026-07-08", "2026-07-01",
    ]
    # The same window + productivity filter ``clearNights.ts`` applies to these
    # rows client-side (PACE_LOOKBACK_NIGHTS = 5, MIN_PRODUCTIVE_NIGHT_S = 120).
    client_side = [n["kept_exposure_s"] for n in nights[:5]
                   if n["kept_exposure_s"] >= 120.0]
    server_pace = {r["safe"]: r["recent_pace_s"]
                   for r in client.get("/api/library-progress").json()}["M_42"]
    assert server_pace == median(client_side)
