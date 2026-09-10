"""GET /api/targets/{safe}/autostack-thin-hold — "why isn't my mosaic stacking?".

The minimum-frames floor (v0.183.0) holds a target back rather than publishing
single-frame colour speckle, and since the floor learned to judge a *pixel* it
also holds a **mosaic** whose panels are one sub deep — a target whose subs are
every one of them located, and whose count is well past the floor. The Target
page's own note can only see the "not located yet" half, so without this endpoint
that hold is invisible and the app reads as idle.
"""

from __future__ import annotations

from webapp.jobs import Job


def _finished_scan(client, result: dict, *, when: str = "2026-09-10T02:00:00Z") -> Job:
    """Persist a finished ``pipeline`` job carrying ``result``, newest last."""
    jm = client.app.state.job_manager
    job = Job(kind="pipeline")
    job.state = "done"
    job.created_utc = when
    job.finished_utc = when
    job.result = result
    jm._jobs[job.id] = job
    jm._persist(job)
    return job


def test_a_mosaic_hold_is_reported_with_the_scans_own_numbers(client, solved_library):
    _finished_scan(client, {
        "scanned": 0,
        "auto_stack_held_thin": [
            {"target": "M_42", "frames": 9, "min": 3, "panel_depth": 1, "panels": 9},
        ],
    })
    b = client.get("/api/targets/M_42/autostack-thin-hold").json()
    assert b["frames"] == 9
    assert b["min_frames"] == 3
    assert b["panel_depth"] == 1
    assert b["panels"] == 9
    assert b["when_utc"] == "2026-09-10T02:00:00Z"
    # …and only for the target that was actually held.
    assert client.get("/api/targets/NGC_7000/autostack-thin-hold").json() is None


def test_a_plain_thin_hold_reports_no_panels(client, solved_library):
    """A single field held on its count is still reported — with the mosaic
    fields at 0, which is what a reader must key off to choose its words."""
    _finished_scan(client, {
        "auto_stack_held_thin": [{"target": "M_42", "frames": 2, "min": 3}],
    })
    b = client.get("/api/targets/M_42/autostack-thin-hold").json()
    assert b["frames"] == 2 and b["min_frames"] == 3
    assert b["panel_depth"] == 0 and b["panels"] == 0


def test_the_hold_clears_itself_once_a_later_scan_stacks_the_target(
    client, solved_library,
):
    """No dismissal, no stored state: it reads the *newest* finished scan only."""
    _finished_scan(client, {
        "auto_stack_held_thin": [
            {"target": "M_42", "frames": 9, "min": 3, "panel_depth": 1, "panels": 9},
        ],
    }, when="2026-09-10T02:00:00Z")
    assert client.get("/api/targets/M_42/autostack-thin-hold").json() is not None

    _finished_scan(client, {"auto_stacked": ["M_42"]}, when="2026-09-10T03:00:00Z")
    assert client.get("/api/targets/M_42/autostack-thin-hold").json() is None


def test_the_hold_is_silent_with_no_scans_and_404s_for_an_unknown_target(
    client, solved_library,
):
    assert client.get("/api/targets/M_42/autostack-thin-hold").json() is None
    assert client.get("/api/targets/nope/autostack-thin-hold").status_code == 404


def test_the_hold_tolerates_a_malformed_entry(client, solved_library):
    """Job results are free-form JSON written by an older build; a junk entry
    must render nothing rather than 500 the Target page."""
    _finished_scan(client, {"auto_stack_held_thin": [None, "junk", {}]})
    assert client.get("/api/targets/M_42/autostack-thin-hold").json() is None
