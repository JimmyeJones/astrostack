"""JobManager: serialization, progress, cancel, persistence, restart recovery."""

from __future__ import annotations

import threading
import time

from webapp.jobs import Job, JobManager


def _wait(predicate, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(0.02)
    return False


def test_evict_old_prunes_jobs_db(tmp_path):
    import sqlite3

    jm = JobManager(tmp_path / "jobs.sqlite", max_history=3)  # disk keep = max(30, 50) = 50
    for i in range(70):
        job = Job(kind="t", state="done")
        job.created_utc = f"{i:04d}"
        job.finished_utc = f"{i:04d}"
        jm._persist(job)
    jm._evict_old()
    with sqlite3.connect(jm.db_path) as conn:
        n = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    assert n == 50  # pruned to the on-disk cap, not unbounded


def test_clear_history_removes_finished_only(tmp_path):
    import sqlite3

    jm = JobManager(tmp_path / "jobs.sqlite")
    for i in range(5):
        job = Job(kind="t", state="done")
        job.created_utc = job.finished_utc = f"{i:04d}"
        jm._persist(job)
    running = Job(kind="t", state="running")
    jm._persist(running)

    removed = jm.clear_history()
    assert removed == 5
    with sqlite3.connect(jm.db_path) as conn:
        states = [r[0] for r in conn.execute("SELECT state FROM jobs")]
    assert states == ["running"]  # only the in-flight job survives


def test_runs_and_records_result(tmp_path):
    jm = JobManager(tmp_path / "jobs.sqlite")
    jm.start()
    try:
        def body(job: Job):
            job.set_progress("work", 1, 1)
            return {"answer": 42}

        job = jm.submit("test", body)
        assert _wait(lambda: jm.get(job.id).state == "done")
        assert jm.get(job.id).result == {"answer": 42}
    finally:
        jm.stop()


def test_jobs_serialize_one_at_a_time(tmp_path):
    jm = JobManager(tmp_path / "jobs.sqlite")
    jm.start()
    try:
        active = 0
        max_active = 0
        lock = threading.Lock()

        def body(job: Job):
            nonlocal active, max_active
            with lock:
                active += 1
                max_active = max(max_active, active)
            time.sleep(0.1)
            with lock:
                active -= 1

        jobs = [jm.submit("test", body) for _ in range(4)]
        assert _wait(lambda: all(jm.get(j.id).state == "done" for j in jobs), timeout=10)
        assert max_active == 1, "jobs must not run concurrently"
    finally:
        jm.stop()


def test_cancel_queued_job(tmp_path):
    jm = JobManager(tmp_path / "jobs.sqlite")
    jm.start()
    try:
        release = threading.Event()

        def slow(job: Job):
            release.wait(2.0)

        running = jm.submit("test", slow)
        queued = jm.submit("test", slow)
        assert _wait(lambda: jm.get(running.id).state == "running")
        # Cancel the one still queued.
        assert jm.cancel(queued.id) is True
        assert jm.get(queued.id).state == "cancelled"
        release.set()
    finally:
        jm.stop()


def test_error_is_captured(tmp_path):
    jm = JobManager(tmp_path / "jobs.sqlite")
    jm.start()
    try:
        def boom(job: Job):
            raise ValueError("nope")

        job = jm.submit("test", boom)
        assert _wait(lambda: jm.get(job.id).state == "error")
        assert "nope" in jm.get(job.id).error
    finally:
        jm.stop()


def test_restart_marks_interrupted(tmp_path):
    db = tmp_path / "jobs.sqlite"
    jm = JobManager(db)
    jm.start()
    release = threading.Event()

    def slow(job: Job):
        release.wait(10.0)

    job = jm.submit("test", slow)
    try:
        assert _wait(lambda: jm.get(job.id).state == "running")
        # Simulate a crash: open a fresh manager over the same DB while the job
        # is still "running" in the DB (the worker hasn't finished).
        jm2 = JobManager(db)
        recovered = jm2.get(job.id)
        assert recovered is not None
        assert recovered.state == "interrupted"
    finally:
        release.set()
        jm.stop()
