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
