"""GET/PUT /api/targets/{safe}/integration-goal — the user-set integration goal
that drives the "Is it enough yet?" readiness card. Stored in the existing
project-meta kv table (no schema migration)."""

from __future__ import annotations


def test_goal_defaults_to_null(client, built_library):
    targets = client.get("/api/targets").json()
    safe = next(t["safe_name"] for t in targets if t["safe_name"] == "M_42")
    r = client.get(f"/api/targets/{safe}/integration-goal")
    assert r.status_code == 200
    assert r.json() == {"goal_s": None}


def test_set_and_read_back_a_goal(client, built_library):
    targets = client.get("/api/targets").json()
    safe = next(t["safe_name"] for t in targets if t["safe_name"] == "M_42")

    put = client.put(f"/api/targets/{safe}/integration-goal", json={"goal_s": 6 * 3600})
    assert put.status_code == 200
    assert put.json()["goal_s"] == 6 * 3600

    got = client.get(f"/api/targets/{safe}/integration-goal")
    assert got.status_code == 200
    assert got.json()["goal_s"] == 6 * 3600


def test_clearing_a_goal_reverts_to_default(client, built_library):
    targets = client.get("/api/targets").json()
    safe = next(t["safe_name"] for t in targets if t["safe_name"] == "M_42")

    client.put(f"/api/targets/{safe}/integration-goal", json={"goal_s": 4 * 3600})
    cleared = client.put(f"/api/targets/{safe}/integration-goal", json={"goal_s": None})
    assert cleared.status_code == 200
    assert cleared.json()["goal_s"] is None
    assert client.get(f"/api/targets/{safe}/integration-goal").json()["goal_s"] is None


def test_goal_is_clamped_to_sane_bounds(client, built_library):
    targets = client.get("/api/targets").json()
    safe = next(t["safe_name"] for t in targets if t["safe_name"] == "M_42")

    # Absurdly large → clamped down to the 1000 h ceiling, not stored raw.
    huge = client.put(f"/api/targets/{safe}/integration-goal",
                      json={"goal_s": 10_000 * 3600})
    assert huge.status_code == 200
    assert huge.json()["goal_s"] == 1000.0 * 3600.0

    # Tiny positive → clamped up to the 60 s floor.
    tiny = client.put(f"/api/targets/{safe}/integration-goal", json={"goal_s": 1})
    assert tiny.status_code == 200
    assert tiny.json()["goal_s"] == 60.0


def test_non_positive_goal_is_rejected(client, built_library):
    targets = client.get("/api/targets").json()
    safe = next(t["safe_name"] for t in targets if t["safe_name"] == "M_42")
    for bad in (0, -5):
        r = client.put(f"/api/targets/{safe}/integration-goal", json={"goal_s": bad})
        assert r.status_code == 422


def test_unknown_target_404(client):
    assert client.get("/api/targets/does_not_exist/integration-goal").status_code == 404
    assert client.put("/api/targets/does_not_exist/integration-goal",
                      json={"goal_s": 3600}).status_code == 404
