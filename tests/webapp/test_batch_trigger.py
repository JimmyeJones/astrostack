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
    monkeypatch.setattr(
        webapp_main.pipeline, "submit_pipeline",
        lambda *a, **k: submitted.append(1),
    )

    accepted = webapp_main._on_batch_ready(_fake_app(jm))

    assert accepted is True
    assert submitted == [1]
