"""A cancelled pipeline / process / QC job must be *classified* cancelled.

Regression: the cancel-aware bodies broke out of their loops on
``job.cancel_requested()`` and then returned their **truthy** summary dict with
no top-level ``cancelled`` sentinel. ``JobManager._run`` only marks a job
``cancelled`` when the body returns falsy *or* returns ``{"cancelled": True}``,
so a truthy summary fell through to ``done`` — a cancelled scan/QC showed on the
Jobs/History page as if it completed successfully. Each cancel-driven break must
now surface ``summary["cancelled"] = True``.
"""

from __future__ import annotations

from types import SimpleNamespace

from seestack.io.library import Library
from webapp import pipeline
from webapp.config import Settings
from webapp.jobs import Job


class _FakeJM:
    def maybe_flush(self, job) -> None:  # noqa: ANN001
        pass


def test_pipeline_qc_phase_cancel_is_classified_cancelled(solved_library):
    # auto_qc on (no ingest/stack): a job cancelled before the QC/solve loop runs
    # breaks on the first cancel check. The returned summary must carry the
    # cancelled sentinel so the worker marks the job 'cancelled', not 'done'.
    settings = Settings(
        data_root=str(solved_library), auto_ingest=False, auto_qc=True,
        auto_solve=False, auto_stack=False,
    )
    lib = Library.open_or_create(solved_library / "library")
    try:
        job = Job(kind="pipeline")
        job._cancel.set()  # user cancels the scan up-front
        summary = pipeline._pipeline_body(settings, _FakeJM(), job, root=None)
    finally:
        lib.close()
    assert summary.get("cancelled") is True


def test_pipeline_auto_stack_cancel_is_classified_cancelled(solved_library):
    # auto_stack on: a job cancelled before the auto-stack loop runs breaks on the
    # first cancel check and must surface the cancelled sentinel.
    settings = Settings(
        data_root=str(solved_library), auto_ingest=False, auto_qc=False,
        auto_solve=False, auto_stack=True,
    )
    lib = Library.open_or_create(solved_library / "library")
    try:
        job = Job(kind="pipeline")
        job._cancel.set()
        summary = pipeline._pipeline_body(settings, _FakeJM(), job, root=None)
    finally:
        lib.close()
    assert summary.get("cancelled") is True
    assert summary["auto_stacked"] == []


def test_pipeline_mid_stack_cancel_is_classified_cancelled(solved_library, monkeypatch):
    # A user cancel *during* a target's stack: run_stack returns cancelled=True,
    # the loop breaks — the summary must still carry the top-level sentinel.
    settings = Settings(
        data_root=str(solved_library), auto_ingest=False, auto_qc=False,
        auto_solve=False, auto_stack=True,
    )

    def fake_run_stack(proj, opts, *, progress=None, cancel=None,
                       memory_budget_gb=None, app_version=None):  # noqa: ANN001
        return SimpleNamespace(
            output_dir="/tmp/x", run_id=None, n_frames_used=0,
            canvas_shape=(1, 1, 3), cancelled=True, errors=[], excluded_frames=[],
        )

    monkeypatch.setattr("seestack.stack.stacker.run_stack", fake_run_stack)
    lib = Library.open_or_create(solved_library / "library")
    try:
        summary = pipeline._pipeline_body(
            settings, _FakeJM(), Job(kind="pipeline"), root=None
        )
    finally:
        lib.close()
    assert summary.get("cancelled") is True
    assert summary["auto_stacked"] == []


def test_process_target_qc_phase_cancel_is_classified_cancelled(solved_library, monkeypatch):
    # submit_process_target cancelled during QC/solve (before the stack) must also
    # surface the sentinel — not just the stack-phase cancel.
    settings = Settings(data_root=str(solved_library), auto_grade_frames=False)

    def fake_qc(proj, **kwargs):  # noqa: ANN001
        # Honour the cancel the way run_qc_and_solve does (stop between frames).
        return {"qc_done": 0, "qc_total": 3, "solve_done": 0, "solve_total": 3}

    monkeypatch.setattr("webapp.pipeline.run_qc_and_solve", fake_qc)
    lib = Library.open_or_create(solved_library / "library")
    try:
        safe = lib.list_targets()[0].safe_name
    finally:
        lib.close()

    # Run the job body via a JobManager stub that invokes it inline with a
    # pre-cancelled job, so the body's post-QC cancel check fires.
    class _JM(_FakeJM):
        def submit(self, kind, fn, **kw):  # noqa: ANN001
            job = Job(kind=kind)
            job._cancel.set()
            return fn(job)

    summary = pipeline.submit_process_target(settings, _JM(), safe)
    assert summary.get("cancelled") is True
    assert summary.get("stack_skipped_reason") == "cancelled"


def test_editor_batch_cancel_is_classified_cancelled(solved_library):
    # A cancelled batch export must surface the sentinel too — a beginner who hits
    # Stop mid-batch shouldn't see a green "Done".
    settings = Settings(data_root=str(solved_library))

    class _JM(_FakeJM):
        def submit(self, kind, fn, **kw):  # noqa: ANN001
            job = Job(kind=kind)
            job._cancel.set()  # cancelled before the first item
            return fn(job)

    items = [{"safe": "M_42", "run_id": 1}]
    result = pipeline.submit_editor_batch(settings, _JM(), items, {"ops": []})
    assert result.get("cancelled") is True
    assert result["exported"] == []
