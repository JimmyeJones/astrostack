"""GET /api/targets/{safe}/session-recap — the "Last session" summary card."""

from __future__ import annotations


def test_session_recap_for_a_built_target(client, built_library):
    targets = client.get("/api/targets").json()
    m42 = next(t for t in targets if t["safe_name"] == "M_42")
    r = client.get(f"/api/targets/{m42['safe_name']}/session-recap")
    assert r.status_code == 200
    recap = r.json()
    assert recap is not None
    # The synthetic library ingests 3 frames per target, all accepted.
    assert recap["n_frames"] == 3
    assert recap["n_kept"] == 3
    assert recap["n_set_aside"] == 0
    assert recap["reject_buckets"] == {}
    assert recap["kept_exposure_s"] > 0
    assert recap["total_kept_exposure_s"] == recap["kept_exposure_s"]
    assert recap["start_utc"] is not None and recap["end_utc"] is not None
    # A single-session synthetic target has no prior night to compare against.
    assert recap["quality_drift"] is None


def test_session_recap_surfaces_a_quality_drift_nudge(client, built_library):
    """A soft second night on top of a sharp first surfaces the FWHM drift note
    through the endpoint (serialised nested object, not just the engine dataclass)."""
    import datetime as dt

    from seestack.io.library import Library
    from seestack.io.project import FrameRow

    targets = client.get("/api/targets").json()
    m42 = next(t for t in targets if t["safe_name"] == "M_42")
    lib = Library.open_or_create(built_library / "library")
    try:
        proj = lib.open_target(m42["safe_name"])
        try:
            # A sharp prior night, then a soft newest night — enough measured subs
            # each, and both after the synthetic 2024 frames so soft is the newest.
            # tz-aware to match the ingested frames' stored UTC timestamps.
            sharp = dt.datetime(2025, 1, 1, 22, 0, 0, tzinfo=dt.timezone.utc)
            soft = dt.datetime(2025, 1, 8, 22, 0, 0, tzinfo=dt.timezone.utc)
            for i in range(6):
                proj.add_frame(FrameRow(source_path=f"/x/sharp{i}.fit",
                                        timestamp_utc=(sharp + dt.timedelta(seconds=30 * i)).isoformat(),
                                        exposure_s=10.0, fwhm_px=3.2))
            for i in range(6):
                proj.add_frame(FrameRow(source_path=f"/x/soft{i}.fit",
                                        timestamp_utc=(soft + dt.timedelta(seconds=30 * i)).isoformat(),
                                        exposure_s=10.0, fwhm_px=5.4))
        finally:
            proj.close()
    finally:
        lib.close()

    r = client.get(f"/api/targets/{m42['safe_name']}/session-recap")
    assert r.status_code == 200
    drift = r.json()["quality_drift"]
    assert drift is not None
    assert drift["kind"] == "fwhm"
    assert drift["latest_fwhm_px"] == 5.4
    assert drift["baseline_fwhm_px"] == 3.2


def test_session_recap_null_for_an_empty_target(client):
    # A freshly created target has no frames → nothing datable → null card.
    client.post("/api/targets", json={"name": "empty field"})
    targets = client.get("/api/targets").json()
    safe = next(t["safe_name"] for t in targets if t["name"] == "empty field")
    r = client.get(f"/api/targets/{safe}/session-recap")
    assert r.status_code == 200
    assert r.json() is None


def test_session_recap_unknown_target_404(client):
    r = client.get("/api/targets/does_not_exist/session-recap")
    assert r.status_code == 404
