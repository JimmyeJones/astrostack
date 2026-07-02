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


def _add_stack_run(root, safe, ts="2026-05-02T00:00:00Z", preview="master_preview.png"):
    lib = Library.open_or_create(root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc=ts, output_basename="master",
                fits_path=None, tiff_path=None, preview_path=preview,
                n_frames_used=3, canvas_h=320, canvas_w=480,
                coverage_min=1, coverage_max=3, options_json=json.dumps({}),
            ))
        finally:
            proj.close()
        # Bumps last_activity_utc + last_stack_preview → cache signature changes.
        lib.refresh_target_stats(safe)
    finally:
        lib.close()


def test_stats_caches_rollup_until_activity_changes(client, solved_library, monkeypatch):
    import webapp.routers.stats as stats_mod

    calls = {"n": 0}
    real = stats_mod._rollup_stacks

    def counting(lib, targets):
        calls["n"] += 1
        return real(lib, targets)

    monkeypatch.setattr(stats_mod, "_rollup_stacks", counting)

    # First hit does the expensive roll-up; a second hit with nothing changed
    # is served from cache (no extra project opens).
    assert client.get("/api/stats").json()["n_stack_runs"] == 0
    assert calls["n"] == 1
    assert client.get("/api/stats").json()["n_stack_runs"] == 0
    assert calls["n"] == 1

    # A completed stack bumps last_activity_utc, which changes the cache
    # signature — the next call re-rolls up and reflects the new run.
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _add_stack_run(solved_library, safe)
    body = client.get("/api/stats").json()
    assert calls["n"] == 2
    assert body["n_stack_runs"] == 1
