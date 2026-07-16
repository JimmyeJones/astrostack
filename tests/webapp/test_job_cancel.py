"""JobManager cancel semantics: a finished result must survive a late cancel."""

import threading
import time

import numpy as np

import webapp.jobs as jobs_mod
from webapp.jobs import _TERMINAL, JobManager


def _wait_until(pred, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if pred():
            return True
        time.sleep(0.01)
    return False


def test_late_cancel_keeps_completed_result(tmp_path):
    """A non-cancel-aware job that runs to completion must be marked done and
    keep its result, even if cancel was requested before it returned.

    Regression: the worker used to mark any job with cancel_requested() as
    'cancelled' and throw away the returned value, so a stack that had already
    finished was discarded and the user had to redo it.
    """
    mgr = JobManager(tmp_path / "jobs.db")
    mgr.start()
    try:
        def fn(job):
            # Simulate the user pressing cancel just as the (non-cancel-aware)
            # work finishes: the flag is set, but the function still returns a
            # full result.
            job._cancel.set()
            return {"stack": "done", "frames": 42}

        job = mgr.submit("stack", fn)
        assert _wait_until(lambda: job.state in ("done", "cancelled", "error"))
        assert job.state == "done", job.state
        assert job.result == {"stack": "done", "frames": 42}
    finally:
        mgr.stop()


def test_cancel_without_result_marks_cancelled(tmp_path):
    """A cancel-aware job that aborts without producing a result stays
    'cancelled' (the honored-cancel path is unchanged)."""
    mgr = JobManager(tmp_path / "jobs.db")
    mgr.start()
    try:
        def fn(job):
            job._cancel.set()
            return None  # aborted early, nothing produced

        job = mgr.submit("stack", fn)
        assert _wait_until(lambda: job.state in ("done", "cancelled", "error"))
        assert job.state == "cancelled", job.state
    finally:
        mgr.stop()


def test_cancel_sentinel_result_marks_cancelled(tmp_path):
    """A cancel-aware stack that honors the cancel returns a *truthy* sentinel
    dict (`run_stack` -> StackResult(cancelled=True) -> `_stack_target` returns
    {"cancelled": True, "run_id": None, ...}) — with no finished run. The worker
    must mark that 'cancelled', not report an empty result as a done stack.

    Regression: `completed = result or job.result` is truthy for the sentinel, so
    the old `not completed` test alone misclassified a cancelled stack as 'done'
    with `run_id: None` and no openable output.
    """
    mgr = JobManager(tmp_path / "jobs.db")
    mgr.start()
    try:
        def fn(job):
            job._cancel.set()
            return {"cancelled": True, "run_id": None, "output_dir": "", "errors": []}

        job = mgr.submit("stack", fn)
        assert _wait_until(lambda: job.state in ("done", "cancelled", "error"))
        assert job.state == "cancelled", job.state
        # The sentinel result is preserved so the Jobs page can show cancel detail.
        assert job.result is not None and job.result.get("cancelled") is True
    finally:
        mgr.stop()


def test_cancel_cannot_race_worker_claim_into_a_cancelled_row(tmp_path, monkeypatch):
    """A cancel landing exactly as the worker claims a queued job must not leave the
    job marked 'cancelled' while its (non-cancel-aware) body still runs to completion.

    The race window is between the worker's 'cancelled while queued?' check and its
    flip to 'running'. We pause the worker inside that window — the claim computes
    ``started_utc`` (a ``_utc()`` call) there, under the job lock, while the state is
    still 'queued' — and fire ``cancel()`` from another thread:

    - Fixed: ``cancel()`` reads+transitions ``job.state`` under the same lock the
      worker holds during the claim, so it blocks; once the worker flips to
      'running' the cancel sees 'running' and only sets the ``_cancel`` event. A
      non-cancel-aware body runs to completion and the job ends 'done'.
    - Before the fix (claim not under the lock): ``cancel()`` reads 'queued', marks
      the job cancelled and persists a terminal row, and the worker runs the body
      anyway — the job is reported cancelled while a master/PNG was really produced.
    """
    mgr = JobManager(tmp_path / "jobs.db")

    armed = threading.Event()
    reached_claim = threading.Event()
    release_claim = threading.Event()
    real_utc = jobs_mod._utc

    def paused_utc():
        # Pause exactly once — on the worker's claim call inside the locked window.
        if armed.is_set():
            armed.clear()
            reached_claim.set()
            release_claim.wait(5.0)
        return real_utc()

    # The dataclass ``created_utc`` factory captured the original function at class
    # definition, so ``submit`` is unaffected; only the by-name ``_utc()`` calls
    # (the worker's claim, cancel's finished_utc) resolve to this patch.
    monkeypatch.setattr(jobs_mod, "_utc", paused_utc)

    ran = threading.Event()

    def body(job):
        ran.set()  # non-cancel-aware: ignore the cancel flag, run to completion
        return {"produced": True}

    mgr.start()
    try:
        armed.set()
        job = mgr.submit("build_master", body)
        assert reached_claim.wait(5.0), "worker never reached the claim window"
        assert job.state == "queued"

        cancel_done = threading.Event()

        def do_cancel():
            mgr.cancel(job.id)
            cancel_done.set()

        t = threading.Thread(target=do_cancel)
        t.start()
        try:
            # While the worker holds the claim lock, cancel() can't complete and the
            # job must never be observed 'cancelled'.
            assert not cancel_done.wait(0.5), "cancel() did not serialize with claim"
            assert job.state != "cancelled"

            # Let the worker finish claiming; cancel() now sees 'running'/'done'.
            release_claim.set()
            assert cancel_done.wait(5.0)
        finally:
            release_claim.set()
            t.join(5.0)

        assert _wait_until(lambda: job.state in _TERMINAL)
        assert ran.is_set(), "the non-cancel-aware body should have run to completion"
        assert job.state == "done", job.state
        assert job.result == {"produced": True}
    finally:
        release_claim.set()
        mgr.stop()


def test_non_serializable_result_does_not_kill_worker(tmp_path):
    """A job whose result isn't JSON-serialisable (e.g. a stray numpy scalar)
    must not kill the single worker thread — persistence is best-effort, and a
    dead worker would silently halt *all* subsequent job processing.

    Regression: json.dumps(job.result) used to run inside a try that only caught
    sqlite3.Error, so a TypeError propagated out of _persist in the worker's
    finally and killed the worker.
    """
    mgr = JobManager(tmp_path / "jobs.db")
    mgr.start()
    try:
        def bad(job):
            return {"val": np.int64(7)}  # not JSON-serialisable

        j1 = mgr.submit("stack", bad)
        assert _wait_until(lambda: j1.state in ("done", "cancelled", "error"))
        assert j1.state == "done", j1.state

        # The worker must still be alive: a later job runs to completion.
        j2 = mgr.submit("stack", lambda job: {"ok": True})
        assert _wait_until(lambda: j2.state in ("done", "cancelled", "error"))
        assert j2.state == "done", j2.state
        assert j2.result == {"ok": True}
    finally:
        mgr.stop()
