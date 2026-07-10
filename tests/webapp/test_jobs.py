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


def test_list_never_truncates_active_jobs(tmp_path):
    """Regression: the currently-running job must stay visible in ``list`` even
    when more than ``limit`` newer jobs exist.

    A single serial worker holds many queued jobs plus one running one whose
    ``created_utc`` predates them. The old ``list`` merged live + history, sorted
    by ``created_utc DESC`` and truncated to ``limit`` — so the old running job
    fell off the end and ``GET /api/jobs`` couldn't show or cancel the job that
    was actually executing. Active jobs are now guaranteed present.
    """
    jm = JobManager(tmp_path / "jobs.sqlite")

    # A pipeline that started before everything else (oldest created_utc).
    running = Job(kind="pipeline", state="running")
    running.created_utc = running.started_utc = "0000"
    jm._jobs[running.id] = running  # active jobs live in the in-memory map
    jm._persist(running)

    # A queue of newer jobs, all created after it and well past a limit=5 window.
    for i in range(1, 21):
        q = Job(kind="editor_png", state="queued")
        q.created_utc = f"{i:04d}"
        jm._jobs[q.id] = q
        jm._persist(q)

    listed = jm.list(limit=5)
    ids = {j.id for j in listed}
    # The running job is present despite 20 newer jobs and a limit of 5.
    assert running.id in ids
    running_out = next(j for j in listed if j.id == running.id)
    assert running_out.state == "running"
    # All active jobs are surfaced (21 total: 1 running + 20 queued); history
    # only fills the *remaining* slots, so a large active queue is never hidden.
    assert len(listed) == 21
    assert all(j.state in ("running", "queued") for j in listed)


def test_list_history_still_bounded_by_limit(tmp_path):
    """With no active jobs, ``list`` still returns at most ``limit`` history rows
    (newest first) — the limit bounds history exactly as before."""
    jm = JobManager(tmp_path / "jobs.sqlite")
    for i in range(20):
        j = Job(kind="t", state="done")
        j.created_utc = j.finished_utc = f"{i:04d}"
        jm._persist(j)
    listed = jm.list(limit=5)
    assert len(listed) == 5
    # Newest five (created 0015..0019), most-recent first.
    assert [j.created_utc for j in listed] == ["0019", "0018", "0017", "0016", "0015"]


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
        # An unrecognised failure carries no canonical kind (frontend shows raw text).
        assert jm.get(job.id).error_kind is None
    finally:
        jm.stop()


def test_classify_job_error_maps_known_signatures():
    from webapp.jobs import classify_job_error

    # Type-based (reword-proof) for the OOM guard.
    assert classify_job_error(MemoryError("stack canvas needs ~7 GB")) == "memory_budget"
    # ...or by message when raised as a plain exception carrying "working memory".
    assert classify_job_error(
        RuntimeError("needs 7 GB of working memory")) == "memory_budget"
    assert classify_job_error(
        ValueError("no accepted, plate-solved frames to stack")) == "no_solved_frames"
    assert classify_job_error(
        ValueError("no frames could be aligned")) == "no_alignment"
    assert classify_job_error(
        ValueError("drizzle: no usable frames")) == "no_alignment"
    assert classify_job_error(
        ValueError("reference frame is missing WCS or dimensions")) == "no_reference_wcs"
    # A Build-master job pointed at an empty/wrong folder.
    assert classify_job_error(
        FileNotFoundError("No FITS files found in /mnt/darks")) == "no_fits_in_folder"
    # But an *internal* FileNotFoundError (missing target/run) is not dressed up
    # as a folder problem.
    assert classify_job_error(FileNotFoundError("no target 'M31'")) is None
    # Anything unrecognised stays None so the raw text is shown verbatim.
    assert classify_job_error(OSError("disk is full")) is None


def test_error_kind_persisted_and_reloaded(tmp_path):
    db = tmp_path / "jobs.sqlite"
    jm = JobManager(db)
    jm.start()
    try:
        def boom(job: Job):
            raise MemoryError("stack output canvas needs more working memory")

        job = jm.submit("stack", boom)
        assert _wait(lambda: jm.get(job.id).state == "error")
        assert jm.get(job.id).error_kind == "memory_budget"
    finally:
        jm.stop()
    # Survives a reload from disk (fresh manager over the same DB).
    reloaded = JobManager(db).get(job.id)
    assert reloaded.error_kind == "memory_budget"


def test_error_kind_column_added_to_pre_existing_db(tmp_path):
    """A jobs.sqlite created before the error_kind column must migrate in place
    (additive ALTER, never a reset) and keep serving its old history."""
    import sqlite3

    db = tmp_path / "jobs.sqlite"
    # Simulate the old schema: the jobs table without an error_kind column.
    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            CREATE TABLE jobs (
                id TEXT PRIMARY KEY, kind TEXT NOT NULL, target TEXT,
                state TEXT NOT NULL, phase TEXT, done INTEGER, total INTEGER,
                detail TEXT, created_utc TEXT, started_utc TEXT, finished_utc TEXT,
                error TEXT, result_json TEXT
            )
            """
        )
        conn.execute(
            "INSERT INTO jobs(id, kind, state, error) VALUES('old1','stack','error',?)",
            ("MemoryError: needs working memory",),
        )
    # Opening a JobManager runs the additive migration.
    jm = JobManager(db)
    with sqlite3.connect(db) as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(jobs)")}
    assert "error_kind" in cols
    old = jm.get("old1")
    assert old is not None
    assert old.error == "MemoryError: needs working memory"  # old row preserved
    assert old.error_kind is None  # not backfilled — the frontend still matches raw


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


def test_rest_endpoints_include_error_kind(client):
    """The REST job endpoints must expose the server-classified ``error_kind``.

    It's persisted and returned by ``Job.to_dict()`` and the SSE stream, but the
    ``JobOut`` response model has to declare the field or FastAPI silently strips
    it — leaving the Jobs page (which loads history over ``GET /api/jobs``, not
    SSE) to fall back to brittle string-matching of the raw error text.
    """
    jm: JobManager = client.app.state.job_manager

    def boom(job: Job):
        raise MemoryError("stack output canvas needs more working memory")

    job = jm.submit("stack", boom)
    assert _wait(lambda: jm.get(job.id).state == "error")
    assert jm.get(job.id).error_kind == "memory_budget"

    # GET /api/jobs/{id}
    one = client.get(f"/api/jobs/{job.id}").json()
    assert one["error_kind"] == "memory_budget"

    # GET /api/jobs (history list) — the path the Jobs page actually uses.
    listed = client.get("/api/jobs").json()
    row = next(r for r in listed if r["id"] == job.id)
    assert row["error_kind"] == "memory_budget"
