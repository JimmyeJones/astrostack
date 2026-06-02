"""GET /api/stats dashboard aggregates."""

from __future__ import annotations

import json

from seestack.io.library import Library
from seestack.io.project import StackRunRow


def test_stats_empty(client):
    r = client.get("/api/stats")
    assert r.status_code == 200
    b = r.json()
    assert b["n_targets"] == 0
    assert b["n_stack_runs"] == 0
    assert b["recent_stacks"] == []
    assert b["acceptance_rate"] is None


def test_stats_rolls_up_library(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target(safe)
        try:
            proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc="2026-05-02T00:00:00Z",
                output_basename="master", fits_path=None, tiff_path=None,
                preview_path=None, n_frames_used=3,
                canvas_h=320, canvas_w=480, coverage_min=1, coverage_max=3,
                options_json=json.dumps({}),
            ))
        finally:
            proj.close()
    finally:
        lib.close()

    b = client.get("/api/stats").json()
    assert b["n_targets"] == 2
    assert b["n_frames"] > 0
    assert b["n_stack_runs"] == 1
    assert b["n_targets_with_stacks"] == 1
    assert 0.0 <= b["acceptance_rate"] <= 1.0
    assert len(b["recent_stacks"]) == 1
    assert b["recent_stacks"][0]["safe"] == safe
    assert "integration_hours" in b
