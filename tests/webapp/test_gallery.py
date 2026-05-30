"""Gallery endpoint: every stack run across targets, with its settings."""

from __future__ import annotations

import json

from seestack.io.library import Library
from seestack.io.project import StackRunRow


def _register_run(data_root, safe: str, options: dict) -> int:
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            run_id = proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc="2026-05-02T00:00:00Z",
                output_basename="master", fits_path=None, tiff_path=None,
                preview_path=None, n_frames_used=7,
                canvas_h=320, canvas_w=480, coverage_min=1, coverage_max=7,
                options_json=json.dumps(options),
            ))
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
        return run_id
    finally:
        lib.close()


def test_gallery_lists_runs_with_options(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    opts = {"sigma_clip": True, "sigma_kappa": 2.5, "drizzle": False, "output_name": "m42"}
    run_id = _register_run(solved_library, safe, opts)

    r = client.get("/api/gallery")
    assert r.status_code == 200
    items = r.json()["items"]
    mine = next(it for it in items if it["run_id"] == run_id)
    assert mine["safe"] == safe
    assert mine["n_frames_used"] == 7
    assert mine["canvas_w"] == 480 and mine["canvas_h"] == 320
    assert mine["preview_url"].endswith(f"/stack-runs/{run_id}/preview")
    # The full stacking settings round-trip through options_json.
    assert mine["options"]["sigma_clip"] is True
    assert mine["options"]["sigma_kappa"] == 2.5


def test_gallery_empty_when_no_runs(client):
    # Fresh data root with no stacks → empty list, still 200.
    r = client.get("/api/gallery")
    assert r.status_code == 200
    assert r.json()["items"] == []


def test_gallery_tolerates_bad_options_json(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target(safe)
        try:
            run_id = proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc="2026-05-03T00:00:00Z",
                output_basename="bad", fits_path=None, tiff_path=None,
                preview_path=None, n_frames_used=1,
                canvas_h=10, canvas_w=10, coverage_min=1, coverage_max=1,
                options_json="not json{",
            ))
        finally:
            proj.close()
    finally:
        lib.close()

    r = client.get("/api/gallery")
    assert r.status_code == 200
    mine = next(it for it in r.json()["items"] if it["run_id"] == run_id)
    assert mine["options"] == {}
