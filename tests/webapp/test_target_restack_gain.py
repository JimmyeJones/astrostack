"""`GET /api/targets/{safe}/restack-gain` — "this picture was made by an older
AstroStack", said as a gain rather than a version number.

The engine half is unit-tested in ``tests/test_restackgain.py``; these pin the
endpoint's own contract — genuine runs only, the datable-subs gate measured off
the *target's* real frames, and silence when there is nothing honest to offer.
The fixture library is the good case for the gate by construction: its subs carry
a real ``DATE-OBS`` (2024-09-12), which is the owner's own situation.
"""

from __future__ import annotations

import json

from seestack.io.library import Library
from seestack.io.project import StackRunRow


def _register_run(data_root, safe: str, *, ts: str, start: str | None = None,
                  hours: list[str] | None = None, n_frames: int = 40,
                  options: dict | None = None) -> int:
    """Add a stack run. ``options=None`` writes a genuine ``StackOptions``
    payload; pass a bare dict for a non-genuine (editor-export/combine) run."""
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            run_id = proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc=ts,
                output_basename="master", fits_path=None, tiff_path=None,
                preview_path=None, n_frames_used=n_frames,
                canvas_h=320, canvas_w=480, coverage_min=1, coverage_max=n_frames,
                options_json=json.dumps(
                    options if options is not None else {"output_name": "m42"}),
                capture_start_utc=start, capture_end_utc=start,
                capture_hours_json=json.dumps(hours) if hours else None,
            ))
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
        return run_id
    finally:
        lib.close()


def test_an_undated_picture_is_offered_a_restack_that_would_date_it(
    client, built_library,
):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _register_run(built_library, safe, ts="2026-08-30T14:32:05Z")

    body = client.get(f"/api/targets/{safe}/restack-gain").json()
    assert body is not None
    assert body["run_id"] == run_id
    assert body["missing_capture_window"] is True
    assert body["missing_night_count"] is False
    # What it combined then, and what a re-stack would combine now — the cost
    # half, so "stack 5,000 subs again" is never a blind click.
    assert body["n_frames_used"] == 40
    assert body["n_frames_ready"] == 3       # the fixture's three accepted subs


def test_a_picture_that_already_records_its_nights_says_nothing(
    client, built_library,
):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _register_run(built_library, safe, ts="2026-08-30T14:32:05Z",
                  start="2024-09-12T03:14:55Z", hours=["2024-09-12T03:00:00Z"])
    assert client.get(f"/api/targets/{safe}/restack-gain").json() is None


def test_an_editor_export_is_not_the_picture_this_is_about(client, built_library):
    """An export inherits its source run's window, so it can neither gain nor
    lose one — the offer must be about the newest *genuine* stack."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _register_run(built_library, safe, ts="2026-08-30T14:32:05Z",
                  start="2024-09-12T03:14:55Z", hours=["2024-09-12T03:00:00Z"])
    _register_run(built_library, safe, ts="2026-08-31T09:00:00Z",
                  options={"edit_export": True})
    assert client.get(f"/api/targets/{safe}/restack-gain").json() is None


def test_undatable_subs_leave_the_offer_silent(client, built_library):
    """A window can be missing because the subs carry no capture time at all,
    and a re-stack would not fix that — so the note must not promise it."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _register_run(built_library, safe, ts="2026-08-30T14:32:05Z")
    lib = Library.open_or_create(built_library / "library")
    try:
        proj = lib.open_target(safe)
        try:
            for f in proj.iter_frames():
                proj.update_frame(f.id, timestamp_utc=None)
        finally:
            proj.close()
    finally:
        lib.close()
    assert client.get(f"/api/targets/{safe}/restack-gain").json() is None


def test_a_target_with_no_stack_yet_says_nothing(client, built_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    assert client.get(f"/api/targets/{safe}/restack-gain").json() is None


def test_restack_gain_unknown_target_404(client):
    assert client.get("/api/targets/does_not_exist/restack-gain").status_code == 404
