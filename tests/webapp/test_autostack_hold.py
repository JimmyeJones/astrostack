"""GET /api/targets/{safe}/autostack-hold — "why did my picture stop updating?".

The walk-away readability preflight (v0.270.1) holds a target back rather than
publishing a picture made thin by subs it can't read, and explains itself on the
Jobs page. This endpoint puts the same recorded fact on the Target page, which is
where a beginner actually looks when their picture goes stale.
"""

from __future__ import annotations

from webapp.jobs import Job


def _finished_scan(client, result: dict, *, when: str = "2026-08-26T02:00:00Z") -> Job:
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


def test_hold_is_reported_with_the_scans_own_numbers(client, solved_library):
    _finished_scan(client, {
        "scanned": 0,
        "auto_stack_held_unreadable": [
            {"target": "M_42", "offered": 787, "readable": 271, "unreadable": 516,
             "prior_best": 787, "reason": "that would be a thinner stack…"},
        ],
    })
    b = client.get("/api/targets/M_42/autostack-hold").json()
    assert b["offered"] == 787
    assert b["readable"] == 271
    assert b["unreadable"] == 516
    assert b["reason"].startswith("that would be")
    assert b["when_utc"] == "2026-08-26T02:00:00Z"
    # …and only for the target that was actually held.
    assert client.get("/api/targets/NGC_7000/autostack-hold").json() is None


def test_hold_clears_itself_once_a_later_scan_stacks_the_target(client, solved_library):
    """No dismissal, no stored state: the note reads the *newest* finished scan,
    so a hold the next scan resolved simply stops being reported."""
    _finished_scan(client, {
        "auto_stack_held_unreadable": [
            {"target": "M_42", "offered": 10, "readable": 4, "unreadable": 6},
        ],
    }, when="2026-08-26T02:00:00Z")
    assert client.get("/api/targets/M_42/autostack-hold").json() is not None

    _finished_scan(client, {"auto_stacked": ["M_42"]}, when="2026-08-26T03:00:00Z")
    assert client.get("/api/targets/M_42/autostack-hold").json() is None


def test_hold_ignores_unfinished_and_non_scan_jobs(client, solved_library):
    """A still-running scan has no verdict yet, and another job kind's result is
    none of this endpoint's business — neither may mask or fake a hold."""
    _finished_scan(client, {
        "auto_stack_held_unreadable": [
            {"target": "M_42", "offered": 10, "readable": 4, "unreadable": 6},
        ],
    }, when="2026-08-26T02:00:00Z")
    jm = client.app.state.job_manager
    running = Job(kind="pipeline")
    running.state = "running"
    running.created_utc = "2026-08-26T04:00:00Z"
    jm._jobs[running.id] = running
    jm._persist(running)
    other = Job(kind="process_target", target="M_42")
    other.state = "done"
    other.created_utc = "2026-08-26T05:00:00Z"
    other.finished_utc = "2026-08-26T05:00:00Z"
    other.result = {"stacked": True}
    jm._jobs[other.id] = other
    jm._persist(other)

    b = client.get("/api/targets/M_42/autostack-hold").json()
    assert b is not None and b["unreadable"] == 6


def test_hold_is_silent_with_no_scans_and_404s_for_an_unknown_target(
    client, solved_library,
):
    assert client.get("/api/targets/M_42/autostack-hold").json() is None
    assert client.get("/api/targets/nope/autostack-hold").status_code == 404


def test_hold_tolerates_a_malformed_entry(client, solved_library):
    """Job results are free-form JSON written by an older build; a junk entry
    must render nothing rather than 500 the Target page."""
    _finished_scan(client, {"auto_stack_held_unreadable": [None, "junk", {}]})
    assert client.get("/api/targets/M_42/autostack-hold").json() is None
