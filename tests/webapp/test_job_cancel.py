"""JobManager cancel semantics: a finished result must survive a late cancel."""

import time

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
