"""Gallery endpoint: every stack run across targets, with its settings."""

from __future__ import annotations

import json

from seestack.io.library import Library
from seestack.io.project import StackRunRow


def _register_run(data_root, safe: str, options: dict,
                  total_exposure_s: float | None = None) -> int:
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
                total_exposure_s=total_exposure_s,
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
    run_id = _register_run(solved_library, safe, opts, total_exposure_s=3600.0)

    r = client.get("/api/gallery")
    assert r.status_code == 200
    items = r.json()["items"]
    mine = next(it for it in items if it["run_id"] == run_id)
    assert mine["safe"] == safe
    assert mine["n_frames_used"] == 7
    assert mine["canvas_w"] == 480 and mine["canvas_h"] == 320
    assert mine["total_exposure_s"] == 3600.0
    assert mine["preview_url"].endswith(f"/stack-runs/{run_id}/preview")
    # The full stacking settings round-trip through options_json.
    assert mine["options"]["sigma_clip"] is True
    assert mine["options"]["sigma_kappa"] == 2.5
    # A plain stack run can pre-fill the Stack form ("Reuse settings").
    assert mine["reusable"] is True


def test_gallery_reusable_flag_excludes_combine_and_editor(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    stack_id = _register_run(solved_library, safe, {"sigma_clip": True})
    combine_id = _register_run(solved_library, safe, {"channel_combine": {"mode": "RGB"}})
    editor_id = _register_run(solved_library, safe, {"editor_recipe": {"ops": []}})

    items = {it["run_id"]: it for it in client.get("/api/gallery").json()["items"]}
    assert items[stack_id]["reusable"] is True
    assert items[combine_id]["reusable"] is False
    assert items[editor_id]["reusable"] is False


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
