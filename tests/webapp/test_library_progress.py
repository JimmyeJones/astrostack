"""GET /api/library-progress — the Dashboard "Target progress" overview card.

Read-only per-target integration inputs (total exposure, catalog object type,
any user-set goal); the readiness verdict itself is computed client-side.
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
