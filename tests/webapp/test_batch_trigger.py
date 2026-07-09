"""The watcher's enqueue callback (`_on_batch_ready`) must not enqueue a second
pipeline while one is already active — even when the running pipeline has been
pushed out of the recent-jobs window by many newer jobs."""

from __future__ import annotations

from types import SimpleNamespace

from webapp import main as webapp_main
from webapp.jobs import Job, JobManager


def _fake_app(jm: JobManager):
    store = SimpleNamespace(get=lambda: SimpleNamespace())
    return SimpleNamespace(state=SimpleNamespace(job_manager=jm, settings_store=store))


def _finished_pipeline(jm: JobManager, state: str) -> Job:
    """Persist a terminal pipeline job in the given state and return it."""
    job = Job(kind="pipeline", state=state)
    job.created_utc = job.finished_utc = "0001"
    jm._persist(job)
    return job


def test_on_batch_ready_defers_when_running_pipeline_is_past_the_recent_window(
    tmp_path, monkeypatch
):
    """Regression: a long-running pipeline (old created_utc) must still block a
    duplicate trigger after many newer jobs have been recorded.

    The old guard scanned ``jm.list(limit=20)`` — which merges live + DB jobs,
    sorts by ``created_utc`` and truncates — so a running pipeline that started
    before 20 newer jobs were created was truncated out of the result, the guard
    saw no active pipeline, and it enqueued a *second* pipeline (a redundant
    full re-scan/QC/solve/stack pass). ``active_of_kind`` scans the full
    in-memory job map, so it can't be truncated away.
    """
    jm = JobManager(tmp_path / "jobs.sqlite")

    # A pipeline that has been running since before everything else.
    running = Job(kind="pipeline", state="running")
    running.created_utc = running.started_utc = "0000"
    jm._jobs[running.id] = running  # active jobs live in the in-memory map
    jm._persist(running)

    # 20 newer jobs finish after it starts (queued editor/stack/reprocess work,
    # then done) — enough to push the running pipeline past a limit=20 window.
    for i in range(1, 21):
        j = Job(kind="editor_png", state="done")
        j.created_utc = j.finished_utc = f"{i:04d}"
        jm._persist(j)

    # Sanity: the old approach would have truncated the running pipeline out.
    recent = jm.list(limit=20)
    assert running.id not in {j.id for j in recent}
    # …but the unbounded active lookup still finds it.
    assert jm.active_of_kind("pipeline") is not None

    submitted: list[int] = []
    monkeypatch.setattr(
        webapp_main.pipeline, "submit_pipeline",
        lambda *a, **k: submitted.append(1),
    )

    accepted = webapp_main._on_batch_ready(_fake_app(jm))

    assert accepted is False        # deferred, not consumed
    assert submitted == []          # no duplicate pipeline enqueued


def test_on_batch_ready_enqueues_when_no_pipeline_is_active(tmp_path, monkeypatch):
    """With no active pipeline the callback enqueues one and reports acceptance."""
    jm = JobManager(tmp_path / "jobs.sqlite")
    # A finished pipeline in history must not count as active.
    old = Job(kind="pipeline", state="done")
    old.created_utc = old.finished_utc = "0000"
    jm._persist(old)

    submitted: list[int] = []

    def _submit(*a, **k):
        submitted.append(1)
        return Job(kind="pipeline", state="queued")

    monkeypatch.setattr(webapp_main.pipeline, "submit_pipeline", _submit)

    accepted = webapp_main._on_batch_ready(_fake_app(jm))

    assert accepted is True
    assert submitted == [1]


# ---- stranded-batch recovery (a pipeline that failed before importing) -------


def test_on_batch_ready_records_the_pipeline_it_enqueued(tmp_path, monkeypatch):
    """The callback stamps the enqueued pipeline's id so a failure can be retried."""
    jm = JobManager(tmp_path / "jobs.sqlite")
    enqueued = Job(kind="pipeline", state="queued")
    monkeypatch.setattr(
        webapp_main.pipeline, "submit_pipeline", lambda *a, **k: enqueued
    )
    app = _fake_app(jm)
    assert webapp_main._on_batch_ready(app) is True
    assert app.state.watcher_pipeline_id == enqueued.id
    assert app.state.watcher_pipeline_is_recovery is False


def test_on_batch_ready_flags_a_recovery_enqueue(tmp_path, monkeypatch):
    """When the enqueue is itself a re-offer, the new pipeline is marked a retry."""
    jm = JobManager(tmp_path / "jobs.sqlite")
    enqueued = Job(kind="pipeline", state="queued")
    monkeypatch.setattr(
        webapp_main.pipeline, "submit_pipeline", lambda *a, **k: enqueued
    )
    app = _fake_app(jm)
    app.state.watcher_recovery_next = True  # set by a prior stranded check
    assert webapp_main._on_batch_ready(app) is True
    assert app.state.watcher_pipeline_is_recovery is True
    assert app.state.watcher_recovery_next is False  # consumed


def test_stranded_check_true_after_pipeline_errors(tmp_path):
    """A watcher pipeline that ends in ``error`` (before importing) needs a retry."""
    jm = JobManager(tmp_path / "jobs.sqlite")
    failed = _finished_pipeline(jm, "error")
    app = _fake_app(jm)
    app.state.watcher_pipeline_id = failed.id
    assert webapp_main._stranded_batch_needs_retry(app) is True
    # It armed the recovery flag so the re-offer is marked as a retry.
    assert app.state.watcher_recovery_next is True


def test_stranded_check_false_when_pipeline_succeeded_or_was_cancelled(tmp_path):
    """A ``done`` or user-``cancelled`` pipeline must not be re-offered."""
    jm = JobManager(tmp_path / "jobs.sqlite")
    for state in ("done", "cancelled", "interrupted"):
        job = _finished_pipeline(jm, state)
        app = _fake_app(jm)
        app.state.watcher_pipeline_id = job.id
        assert webapp_main._stranded_batch_needs_retry(app) is False


def test_stranded_check_false_while_a_pipeline_is_still_active(tmp_path):
    """Don't decide anything while a pipeline is running — let it finish first."""
    jm = JobManager(tmp_path / "jobs.sqlite")
    running = Job(kind="pipeline", state="running")
    jm._jobs[running.id] = running
    jm._persist(running)
    app = _fake_app(jm)
    app.state.watcher_pipeline_id = running.id
    assert webapp_main._stranded_batch_needs_retry(app) is False


def test_stranded_recovery_is_bounded_to_a_single_retry(tmp_path):
    """A pipeline enqueued *as* a recovery that also fails is not retried again."""
    jm = JobManager(tmp_path / "jobs.sqlite")
    failed_retry = _finished_pipeline(jm, "error")
    app = _fake_app(jm)
    app.state.watcher_pipeline_id = failed_retry.id
    app.state.watcher_pipeline_is_recovery = True  # this failure was itself a retry
    assert webapp_main._stranded_batch_needs_retry(app) is False


def test_stranded_check_false_with_no_tracked_pipeline(tmp_path):
    """No pipeline has been enqueued yet → nothing to recover."""
    jm = JobManager(tmp_path / "jobs.sqlite")
    assert webapp_main._stranded_batch_needs_retry(_fake_app(jm)) is False
