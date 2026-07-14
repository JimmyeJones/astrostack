"""GET /api/targets/{safe}/stack-health — the "How's my stack?" card."""

from __future__ import annotations

import json
from pathlib import Path

from seestack.io.library import Library
from seestack.io.project import StackRunRow


def _add_run(data_root: Path, safe: str, **kw) -> int:
    """Insert a genuine stack run directly (avoids running a real stack)."""
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            base = dict(
                id=None, timestamp_utc="2026-07-14T00:00:00+00:00",
                output_basename="m42", fits_path="m42.fits", tiff_path=None,
                preview_path=None, n_frames_used=30, canvas_h=1080, canvas_w=1920,
                coverage_min=30, coverage_max=30,
                options_json=json.dumps({"sigma_clip": True}),  # a genuine run
                calstat="dark+flat", is_mosaic=False,
            )
            base.update(kw)
            return proj.add_stack_run(StackRunRow(**base))
        finally:
            proj.close()
    finally:
        lib.close()


def test_stack_health_null_without_a_stack(client, solved_library):
    # M_42 has frames but no stack run yet → nothing to grade.
    r = client.get("/api/targets/M_42/stack-health")
    assert r.status_code == 200
    assert r.json() is None


def test_stack_health_reports_notes_for_a_calibrated_stack(client, solved_library, data_root):
    rid = _add_run(data_root, "M_42")
    r = client.get("/api/targets/M_42/stack-health")
    assert r.status_code == 200
    body = r.json()
    assert body is not None
    assert body["run_id"] == rid
    assert body["notes"], "a calibrated stack should still get a positive note"
    assert all({"kind", "severity", "message"} <= set(n) for n in body["notes"])


def test_stack_health_uncalibrated_leads_with_calibration_action(
        client, solved_library, data_root):
    _add_run(data_root, "M_42", calstat=None, coverage_min=2, coverage_max=30)
    body = client.get("/api/targets/M_42/stack-health").json()
    kinds = [n["kind"] for n in body["notes"]]
    assert kinds[0] == "calibration"
    assert body["notes"][0]["action"] == "calibration"
    assert "coverage" in kinds  # ragged border also surfaced


def test_stack_health_grades_a_specific_run_by_id(client, solved_library, data_root):
    # The History card grades a *specific* run via ?run_id=, not just the newest.
    old = _add_run(data_root, "M_42", timestamp_utc="2026-07-13T00:00:00+00:00",
                   calstat=None)  # older, uncalibrated
    new = _add_run(data_root, "M_42", timestamp_utc="2026-07-14T00:00:00+00:00",
                   calstat="dark+flat")  # newer, calibrated
    # Default (no run_id) grades the newest genuine run.
    assert client.get("/api/targets/M_42/stack-health").json()["run_id"] == new
    # ?run_id= grades that specific run, and sees its own (uncalibrated) fields.
    body = client.get(f"/api/targets/M_42/stack-health?run_id={old}").json()
    assert body["run_id"] == old
    assert body["notes"][0]["kind"] == "calibration"


def test_stack_health_null_for_unknown_run_id(client, solved_library, data_root):
    _add_run(data_root, "M_42")
    r = client.get("/api/targets/M_42/stack-health?run_id=99999")
    assert r.status_code == 200
    assert r.json() is None


def test_stack_health_unknown_target_404(client):
    r = client.get("/api/targets/does_not_exist/stack-health")
    assert r.status_code == 404
