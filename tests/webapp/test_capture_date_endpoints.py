"""A picture's date is when its subs were *shot*, not when the stack ran.

Regression cover for the wrong-fact bug on **shared output**: the ready-to-post
caption and the OS share sheet both said a picture was "shot on" / "captured" the
run's ``timestamp_utc`` — the moment it was processed. The fixture frames carry a
``DATE-OBS`` of 2024-09-12 and the stack runs *now*, which is the owner's own
situation (a Seestar back catalogue stacked on the day the app was installed), so
the old behaviour dated every picture to today.

These pin the server half end to end: the stacker measures the window off the
frames, and every endpoint that hands a picture to a caption reports it.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone

from seestack.io.library import Library
from seestack.io.project import StackRunRow

#: The observing night every fixture sub belongs to. Their ``DATE-OBS`` is
#: ``2024-09-12T03:14:55`` (see ``tests/synth.py``) — 3 a.m., i.e. the small
#: hours of the night that *started* on the 11th, which is the noon-to-noon
#: bucket the Nights card and the imaging calendar put it in too.
FIXTURE_NIGHT = "2024-09-11"


def _wait_job(client, job_id: str, timeout: float = 120.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"/api/jobs/{job_id}").json()
        if body["state"] in ("done", "error", "cancelled"):
            return body
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} did not finish in {timeout}s")


def test_a_stack_records_when_its_subs_were_shot(client, solved_library):
    r = client.post(
        "/api/targets/M_42/stack",
        json={"output_name": "capture_window", "sigma_clip": False,
              "background_flatten": False, "suppress_hot_pixels": False,
              "max_workers": 2},
    )
    assert r.status_code == 200
    body = _wait_job(client, r.json()["job_id"])
    assert body["state"] == "done", body

    run = client.get("/api/targets/M_42/stack-runs").json()[0]
    # The subs were shot in 2024; the stack ran just now. Before the fix the only
    # date the app had was the second one, and it published it as the first.
    assert run["capture_night_start"] == FIXTURE_NIGHT
    assert run["capture_night_end"] == FIXTURE_NIGHT
    today = datetime.now(timezone.utc).date().isoformat()
    assert run["timestamp_utc"][:10] == today
    assert run["capture_night_start"] != today


def _add_run(root, safe, **kw) -> int:
    lib = Library.open_or_create(root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            fields = dict(
                id=None, timestamp_utc="2026-08-30T12:00:00Z",
                output_basename="master", fits_path=None, tiff_path=None,
                preview_path=None, n_frames_used=3, canvas_h=320, canvas_w=480,
                coverage_min=1, coverage_max=3, options_json=json.dumps({}),
            )
            fields.update(kw)
            return proj.add_stack_run(StackRunRow(**fields))
        finally:
            proj.close()
    finally:
        lib.close()


def test_stack_runs_reports_a_multi_night_window(client, solved_library):
    _add_run(
        solved_library, "M_42",
        capture_start_utc="2024-11-15T22:01:00Z",
        capture_end_utc="2024-11-18T21:40:00Z",
    )
    run = next(r for r in client.get("/api/targets/M_42/stack-runs").json()
               if r["output_basename"] == "master")
    assert run["capture_night_start"] == "2024-11-15"
    assert run["capture_night_end"] == "2024-11-18"


def test_a_run_with_no_recorded_window_reports_none(client, solved_library):
    """Every run on the owner's install predates the column. It must report
    nothing at all rather than falling back to the stack stamp — a caller that
    sees None drops the clause, which is the honest outcome."""
    _add_run(solved_library, "M_42")
    run = next(r for r in client.get("/api/targets/M_42/stack-runs").json()
               if r["output_basename"] == "master")
    assert run["capture_night_start"] is None
    assert run["capture_night_end"] is None


def test_the_dashboard_strip_and_the_gallery_agree_with_history(
        client, solved_library):
    """Three surfaces show the same picture; they must date it identically."""
    _add_run(
        solved_library, "M_42",
        preview_path=None,
        capture_start_utc="2024-11-15T22:01:00Z",
        capture_end_utc="2024-11-15T23:59:00Z",
    )
    history = next(r for r in client.get("/api/targets/M_42/stack-runs").json()
                   if r["output_basename"] == "master")
    strip = next(s for s in client.get("/api/stats").json()["recent_stacks"]
                 if s["output_basename"] == "master")
    gallery = next(g for g in client.get("/api/gallery").json()["items"]
                   if g["output_basename"] == "master")
    for surface in (history, strip, gallery):
        assert surface["capture_night_start"] == "2024-11-15"
        assert surface["capture_night_end"] == "2024-11-15"


def test_the_observers_own_night_is_the_one_reported(client, solved_library):
    """A session that straddles UTC noon is one night to its observer. The
    endpoints bucket with the configured longitude, exactly as the Nights card
    and the imaging calendar do, so no two surfaces can name it differently."""
    _add_run(
        solved_library, "M_42",
        capture_start_utc="2024-11-15T10:00:00Z",
        capture_end_utc="2024-11-15T18:00:00Z",
    )
    assert client.put("/api/settings", json={"site_lon": 150.0}).status_code == 200
    run = next(r for r in client.get("/api/targets/M_42/stack-runs").json()
               if r["output_basename"] == "master")
    assert run["capture_night_start"] == "2024-11-15"
    assert run["capture_night_end"] == "2024-11-15"


# ---- how many nights ---------------------------------------------------


def test_a_real_stack_records_the_nights_its_subs_came_from(
        client, solved_library):
    """The fixture subs are all one night, and the endpoint says so — a count of
    1, not the silence a run with no recorded hours reports."""
    r = client.post(
        "/api/targets/M_42/stack",
        json={"output_name": "capture_nights", "sigma_clip": False,
              "background_flatten": False, "suppress_hot_pixels": False,
              "max_workers": 2},
    )
    assert r.status_code == 200
    assert _wait_job(client, r.json()["job_id"])["state"] == "done"

    run = next(r for r in client.get("/api/targets/M_42/stack-runs").json()
               if r["output_basename"] == "capture_nights")
    assert run["capture_nights"] == 1


def test_the_same_window_reports_the_nights_it_actually_holds(
        client, solved_library):
    """The point of the column: two runs with an identical 15→18 Nov window,
    one built from two nights and one from four."""
    _add_run(
        solved_library, "M_42", output_basename="sparse",
        capture_start_utc="2024-11-15T22:00:00Z",
        capture_end_utc="2024-11-18T22:00:00Z",
        capture_hours_json=json.dumps(
            ["2024-11-15T22:00:00Z", "2024-11-18T22:00:00Z"]),
    )
    _add_run(
        solved_library, "M_42", output_basename="dense",
        capture_start_utc="2024-11-15T22:00:00Z",
        capture_end_utc="2024-11-18T22:00:00Z",
        capture_hours_json=json.dumps([
            "2024-11-15T22:00:00Z", "2024-11-16T22:00:00Z",
            "2024-11-17T22:00:00Z", "2024-11-18T22:00:00Z"]),
    )
    runs = {r["output_basename"]: r
            for r in client.get("/api/targets/M_42/stack-runs").json()}
    assert runs["sparse"]["capture_night_start"] == "2024-11-15"
    assert runs["dense"]["capture_night_start"] == "2024-11-15"
    assert runs["sparse"]["capture_nights"] == 2
    assert runs["dense"]["capture_nights"] == 4


def test_a_run_with_no_recorded_hours_reports_no_count(client, solved_library):
    """Every run on the owner's install predates the column: it must say nothing
    rather than claim a picture came from zero nights."""
    _add_run(solved_library, "M_42",
             capture_start_utc="2024-11-15T22:01:00Z",
             capture_end_utc="2024-11-18T21:40:00Z")
    run = next(r for r in client.get("/api/targets/M_42/stack-runs").json()
               if r["output_basename"] == "master")
    assert run["capture_nights"] is None


def test_every_surface_counts_the_nights_the_same_way(client, solved_library):
    """History, the Dashboard strip and the Gallery all show one picture; a
    count that differed between them would be a visible contradiction."""
    _add_run(
        solved_library, "M_42",
        capture_start_utc="2024-11-15T22:00:00Z",
        capture_end_utc="2024-11-16T22:00:00Z",
        capture_hours_json=json.dumps(
            ["2024-11-15T22:00:00Z", "2024-11-16T22:00:00Z"]),
    )
    history = next(r for r in client.get("/api/targets/M_42/stack-runs").json()
                   if r["output_basename"] == "master")
    strip = next(s for s in client.get("/api/stats").json()["recent_stacks"]
                 if s["output_basename"] == "master")
    gallery = next(g for g in client.get("/api/gallery").json()["items"]
                   if g["output_basename"] == "master")
    for surface in (history, strip, gallery):
        assert surface["capture_nights"] == 2


def test_the_count_follows_the_observers_longitude(client, solved_library):
    """Bucketed through the same helper as the dates, so the count can never
    contradict the range beside it: one New Zealand evening straddling UTC noon
    is one night, and both facts say so together."""
    hours = json.dumps(["2024-11-15T10:00:00Z", "2024-11-15T18:00:00Z"])
    _add_run(
        solved_library, "M_42",
        capture_start_utc="2024-11-15T10:00:00Z",
        capture_end_utc="2024-11-15T18:00:00Z",
        capture_hours_json=hours,
    )
    assert client.put("/api/settings", json={"site_lon": 150.0}).status_code == 200
    run = next(r for r in client.get("/api/targets/M_42/stack-runs").json()
               if r["output_basename"] == "master")
    assert run["capture_night_start"] == run["capture_night_end"] == "2024-11-15"
    assert run["capture_nights"] == 1
