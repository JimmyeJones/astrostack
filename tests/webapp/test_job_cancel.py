"""JobManager cancel semantics: a finished result must survive a late cancel."""

import time

import numpy as np

from webapp.jobs import JobManager


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
