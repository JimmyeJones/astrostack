"""GET /api/targets/{safe}/live-session — "Tonight, live"."""

from __future__ import annotations

import datetime as dt


def _stamp(data_root, safe: str, per_frame: dict[int, dict]) -> None:
    """Stamp fields onto specific frames (by 0-based ordinal) of a target."""
    from seestack.io.library import Library

    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            ids = [f.id for f in proj.iter_frames()]
            for ordinal, fields in per_frame.items():
                proj.update_frame(ids[ordinal], **fields)
        finally:
            proj.close()
    finally:
        lib.close()


def _shoot_recently(data_root, safe: str, *, minutes_ago: int = 5) -> None:
    """Re-stamp the fixture's three subs as if they landed minutes ago, so the
    session reads as one in progress."""
    now = dt.datetime.now(dt.timezone.utc)
    _stamp(data_root, safe, {
        i: {"timestamp_utc": (now - dt.timedelta(minutes=minutes_ago + 2 - i)).isoformat()}
        for i in range(3)
    })


def test_live_session_for_a_built_target(client, built_library):
    r = client.get("/api/targets/M_42/live-session")
    assert r.status_code == 200
    live = r.json()
    assert live is not None
    # The synthetic library ingests 3 frames per target, all accepted.
    assert live["n_frames"] == 3
    assert live["n_kept"] == 3
    assert live["n_set_aside"] == 0
    assert live["kept_exposure_s"] > 0
    assert live["reject_buckets"] == {}
    assert live["start_utc"] is not None and live["latest_utc"] is not None
    # Three subs is below the grading floor — "unknown" is not "bad".
    assert live["conditions"]["verdict"] == "unknown"
    assert live["conditions"]["n_recent"] == 3


def test_a_night_in_progress_reads_as_active(client, built_library, data_root):
    """The whole reason the endpoint exists: subs landing now → `active`, so the
    page can say "tonight, live" instead of falling back to the recap."""
    _shoot_recently(data_root, "M_42", minutes_ago=3)
    live = client.get("/api/targets/M_42/live-session").json()
    assert live["active"] is True
    assert live["minutes_since_latest"] < 10.0


def test_the_fixture_night_from_2024_is_not_active(client, built_library):
    """A finished night is still summarised — with `active` false — rather than
    vanishing, so the page has something honest to show."""
    live = client.get("/api/targets/M_42/live-session").json()
    assert live["active"] is False
    assert live["minutes_since_latest"] > 60.0


def test_conditions_and_buckets_survive_serialisation(
    client, built_library, data_root
):
    """The nested conditions object (and its plain reject buckets) must reach the
    page, not just the engine dataclass."""
    from seestack.io.library import Library
    from seestack.io.project import FrameRow

    now = dt.datetime.now(dt.timezone.utc)
    lib = Library.open_or_create(built_library / "library")
    try:
        proj = lib.open_target("M_42")
        try:
            for i in range(12):
                proj.add_frame(FrameRow(
                    source_path=f"/x/keep{i}.fit",
                    timestamp_utc=(now - dt.timedelta(minutes=40 - i)).isoformat(),
                    exposure_s=10.0, fwhm_px=3.0))
            for i in range(8):
                proj.add_frame(FrameRow(
                    source_path=f"/x/cloud{i}.fit",
                    timestamp_utc=(now - dt.timedelta(minutes=20 - i)).isoformat(),
                    exposure_s=10.0, accept=False, reject_reason="auto:grade:sky"))
        finally:
            proj.close()
    finally:
        lib.close()

    live = client.get("/api/targets/M_42/live-session").json()
    assert live["active"] is True
    c = live["conditions"]
    assert c["n_recent"] == 20
    assert c["n_recent_kept"] == 12
    assert c["verdict"] == "mixed"
    assert c["median_fwhm_px"] == 3.0
    assert c["recent_buckets"] == {"cloudy": 8}
    assert live["reject_buckets"] == {"cloudy": 8}
    assert live["newest_kept_frame_id"] is not None


def test_the_goal_travels_with_the_live_session(client, built_library, data_root):
    """"Have I got enough to go inside?" needs the goal beside the integration —
    and it must be the *same* goal every other screen reads."""
    _shoot_recently(data_root, "M_42")
    client.put("/api/targets/M_42/integration-goal", json={"goal_s": 3600.0})
    live = client.get("/api/targets/M_42/live-session").json()
    assert live["goal_exposure_s"] == 3600.0
    assert live["goal_exposure_s"] == client.get(
        "/api/targets/M_42/integration-goal").json()["goal_s"]


def test_no_goal_set_says_nothing_rather_than_inventing_one(client, built_library):
    live = client.get("/api/targets/M_42/live-session").json()
    assert live["goal_exposure_s"] is None


def test_live_session_null_for_an_empty_target(client):
    client.post("/api/targets", json={"name": "empty field"})
    targets = client.get("/api/targets").json()
    safe = next(t["safe_name"] for t in targets if t["name"] == "empty field")
    r = client.get(f"/api/targets/{safe}/live-session")
    assert r.status_code == 200
    assert r.json() is None


def test_live_session_unknown_target_404(client):
    assert client.get("/api/targets/does_not_exist/live-session").status_code == 404


def test_a_stalled_night_reaches_the_page_as_quiet(client, built_library):
    """The walk-away failure: subs arrive steadily, then stop mid-session. The
    verdict — and the cadence behind it — has to survive serialisation, or the
    Target page's note has nothing to say."""
    from seestack.io.library import Library
    from seestack.io.project import FrameRow

    now = dt.datetime.now(dt.timezone.utc)
    lib = Library.open_or_create(built_library / "library")
    try:
        proj = lib.open_target("M_42")
        try:
            # 30 subs a minute apart, the newest 90 minutes ago.
            for i in range(30):
                proj.add_frame(FrameRow(
                    source_path=f"/x/stall{i}.fit",
                    timestamp_utc=(now - dt.timedelta(minutes=119 - i)).isoformat(),
                    exposure_s=10.0))
        finally:
            proj.close()
    finally:
        lib.close()

    live = client.get("/api/targets/M_42/live-session").json()
    assert live["active"] is False
    assert live["quiet"] is True
    assert live["typical_gap_minutes"] == 1.0
    assert live["quiet_after_minutes"] == 45.0


def test_a_night_that_merely_ended_is_not_reported_as_quiet(client, built_library):
    """The fixture's 2024 night is long over — "capture may have stopped" would
    be nonsense about it, so the endpoint must not say it."""
    live = client.get("/api/targets/M_42/live-session").json()
    assert live["active"] is False
    assert live["quiet"] is False
