"""The import stuck behind the one serial worker (`webapp/jobqueue.py`).

The failure this reports is silent by construction — a frame that was never
imported has no row anywhere to be missing from — so these tests are written
against the *shape* the observer measured on the owner's box (an import queued
for days behind a long `reprocess_all`), not against a convenient fixture.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from webapp.jobqueue import IMPORT_WAIT_MIN_HOURS, import_waiting

NOW = datetime(2026, 9, 14, 3, 0, tzinfo=timezone.utc)


def _stamp(hours_ago: float) -> str:
    return (NOW - timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _job(**kw) -> dict:
    job = {
        "id": "j1", "kind": "pipeline", "target": None, "state": "queued",
        "created_utc": _stamp(0), "started_utc": None,
    }
    job.update(kw)
    return job


def test_a_healthy_queue_says_nothing():
    # The ordinary answer, on every install, almost every minute.
    assert import_waiting([], NOW) is None
    assert import_waiting([_job(state="running", started_utc=_stamp(0.2))], NOW) is None


def test_an_import_queued_a_few_minutes_is_just_the_worker_being_busy():
    # Serialising is the design, not the bug: a short wait must not raise a note.
    assert import_waiting([_job(created_utc=_stamp(0.25))], NOW) is None


def test_an_import_queued_for_days_names_the_job_holding_the_worker():
    # The observer's own shape: an import queued three days, a reprocess_all that
    # has held the single worker since before it.
    jobs = [
        _job(id="imp", created_utc=_stamp(70)),
        _job(id="rep", kind="reprocess_all", state="running",
             created_utc=_stamp(96), started_utc=_stamp(96)),
    ]
    w = import_waiting(jobs, NOW)
    assert w is not None
    assert w.job_id == "imp"
    assert w.waiting_hours == 70.0
    assert w.n_waiting == 1
    assert w.holder_id == "rep"
    assert w.holder_kind == "reprocess_all"
    assert w.holder_hours == 96.0


def test_nothing_running_is_still_reported_because_that_is_the_worse_case():
    # A queue that is not busy but not moving means the worker is gone — the note
    # must still fire, with no holder to point at.
    w = import_waiting([_job(created_utc=_stamp(9))], NOW)
    assert w is not None
    assert w.holder_id is None and w.holder_kind is None and w.holder_hours is None


def test_a_long_running_stack_alone_is_not_a_stuck_import():
    # A stack somebody started can legitimately run for hours. With no import
    # queued behind it there is nothing to say.
    jobs = [{"id": "s", "kind": "stack", "state": "running", "target": "M 42",
             "created_utc": _stamp(8), "started_utc": _stamp(8)}]
    assert import_waiting(jobs, NOW) is None


def test_only_the_import_kind_counts():
    # An editor export or a stack waiting its turn is ordinary serialisation and
    # the person who pressed the button is watching it.
    jobs = [_job(kind="editor_export", created_utc=_stamp(50)),
            _job(kind="stack", created_utc=_stamp(50))]
    assert import_waiting(jobs, NOW) is None


def test_the_longest_waiting_import_is_the_one_reported_and_all_are_counted():
    jobs = [_job(id="new", created_utc=_stamp(3)),
            _job(id="old", created_utc=_stamp(30))]
    w = import_waiting(jobs, NOW)
    assert w is not None
    assert w.job_id == "old" and w.n_waiting == 2


def test_an_unparseable_or_future_stamp_never_manufactures_a_warning():
    # One bad row must not invent a stall. A stamp in the future (a clock skewed
    # ahead on the source share) is not evidence of a wait either.
    assert import_waiting([_job(created_utc="not a date")], NOW) is None
    assert import_waiting([_job(created_utc=None)], NOW) is None
    assert import_waiting([_job(created_utc=_stamp(-40))], NOW) is None


def test_the_threshold_is_the_named_constant_not_a_magic_number():
    just_under = import_waiting([_job(created_utc=_stamp(IMPORT_WAIT_MIN_HOURS - 0.1))], NOW)
    just_over = import_waiting([_job(created_utc=_stamp(IMPORT_WAIT_MIN_HOURS + 0.1))], NOW)
    assert just_under is None and just_over is not None
    # And a caller may tighten it without editing the module.
    assert import_waiting([_job(created_utc=_stamp(0.5))], NOW, min_hours=0.25) is not None


def test_a_holder_with_a_target_carries_it_so_the_sentence_can_name_it():
    jobs = [_job(id="imp", created_utc=_stamp(5)),
            _job(id="stk", kind="stack", state="running", target="NGC 6888",
                 created_utc=_stamp(6), started_utc=_stamp(6))]
    w = import_waiting(jobs, NOW)
    assert w is not None and w.holder_target == "NGC 6888"


def test_a_holder_that_never_recorded_a_start_is_still_named():
    # started_utc is written when the worker claims the job; a row read back from
    # an older DB may not have one. The holder is still the answer to "what is
    # running", just without a duration.
    jobs = [_job(id="imp", created_utc=_stamp(5)),
            _job(id="rep", kind="reprocess_all", state="running",
                 created_utc=_stamp(6), started_utc=None)]
    w = import_waiting(jobs, NOW)
    assert w is not None and w.holder_kind == "reprocess_all" and w.holder_hours is None


# --------------------------------------------------------------------------- #
# JobManager.active + the endpoint
# --------------------------------------------------------------------------- #

def test_active_returns_live_jobs_only_and_needs_no_db_read(tmp_path):
    from webapp.jobs import Job, JobManager

    jm = JobManager(tmp_path / "jobs.sqlite")
    # Persisted history the in-memory map has never seen: `active()` must not
    # pick it up (that is `list()`'s job), so the endpoint stays a cheap poll.
    old = Job(kind="pipeline", state="queued")
    old.created_utc = old.finished_utc = "0001"
    jm._persist(old)

    running = Job(kind="reprocess_all", state="running")
    queued = Job(kind="pipeline", state="queued")
    done = Job(kind="stack", state="done")
    for j in (running, queued, done):
        jm._jobs[j.id] = j

    ids = {j.id for j in jm.active()}
    assert ids == {running.id, queued.id}
    assert old.id not in ids


def test_queue_health_endpoint_is_silent_on_a_healthy_queue(client):
    r = client.get("/api/jobs/queue-health")
    assert r.status_code == 200
    assert r.json() == {"waiting": None}


def test_queue_health_endpoint_reports_a_stalled_import(client):
    # The literal path must also win against `/{job_id}` — a 404 here would mean
    # the route order regressed and the note could never fire.
    from datetime import datetime, timedelta, timezone

    from webapp.jobs import Job

    jm = client.app.state.job_manager
    old = (datetime.now(timezone.utc) - timedelta(hours=70)).strftime("%Y-%m-%dT%H:%M:%SZ")
    held = (datetime.now(timezone.utc) - timedelta(hours=96)).strftime("%Y-%m-%dT%H:%M:%SZ")

    imp = Job(kind="pipeline", state="queued")
    imp.created_utc = old
    rep = Job(kind="reprocess_all", state="running")
    rep.created_utc = rep.started_utc = held
    jm._jobs[imp.id] = imp
    jm._jobs[rep.id] = rep

    body = client.get("/api/jobs/queue-health").json()
    assert body["waiting"] is not None
    assert body["waiting"]["job_id"] == imp.id
    assert body["waiting"]["holder_kind"] == "reprocess_all"
    assert body["waiting"]["waiting_hours"] >= 69.9
