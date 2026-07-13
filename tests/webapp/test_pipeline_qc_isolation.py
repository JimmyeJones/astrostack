"""One target's QC/solve failure must not sink the whole unattended pipeline.

Regression: the auto ingest→QC→auto-stack pipeline's per-target QC/solve loop
(`_pipeline_body`) wrapped each target only in ``try/finally: proj.close()`` —
with **no ``except``** — while every sibling per-target loop (auto-stack,
reprocess-all, editor-batch) deliberately isolates a per-item failure so "one
target shouldn't sink the batch". So a single target raising in
``run_qc_and_solve`` (a process-pool spin-up error, a ``build_*_arglist`` raise,
a DB hiccup) propagated out of the loop: the whole job was marked ``error`` and
the auto-stack pass never ran — silently skipping unattended stacking for
*every* target even though the frames were already scanned and persisted. The
loop must now isolate a per-target failure, record it in ``summary["qc_errors"]``,
and carry on (and a cancel must still classify as a cancel, not an error).
"""

from __future__ import annotations

from seestack.io.library import Library
from webapp import pipeline
from webapp.config import Settings
from webapp.jobs import Job


class _FakeJM:
    def maybe_flush(self, job) -> None:  # noqa: ANN001
        pass


def test_qc_target_failure_isolated_and_autostack_still_runs(solved_library, monkeypatch):
    # Fully-unattended config: QC on, auto-stack on (the "just works" path).
    settings = Settings(
        data_root=str(solved_library), auto_ingest=False, auto_qc=True,
        auto_solve=False, auto_stack=True,
    )

    qc_calls: list[str] = []

    def fake_qc(proj, **kwargs):  # noqa: ANN001
        qc_calls.append("call")
        # The first target blows up the way a process-pool spin-up / arglist build
        # can; the second must still be processed.
        if len(qc_calls) == 1:
            raise RuntimeError("simulated process-pool spin-up failure")
        return {"qc_done": 0, "qc_total": 0, "solve_done": 0, "solve_total": 0}

    monkeypatch.setattr("webapp.pipeline.run_qc_and_solve", fake_qc)

    stacked: list[str] = []

    def fake_stack_target(settings, jm, job, lib, safe, *, auto_bind_calibration=False):  # noqa: ANN001
        stacked.append(safe)
        return {"run_id": None}

    monkeypatch.setattr("webapp.pipeline._stack_target", fake_stack_target)

    lib = Library.open_or_create(solved_library / "library")
    try:
        # Before the fix this raised (propagating the target's RuntimeError); after
        # the fix it returns a normal summary.
        summary = pipeline._pipeline_body(settings, _FakeJM(), Job(kind="pipeline"), root=None)
    finally:
        lib.close()

    # Both targets were attempted — the first failure did not abort the loop.
    assert len(qc_calls) == 2
    # The failure is recorded, not raised, and the job is not misclassified as
    # cancelled.
    assert len(summary.get("qc_errors", {})) == 1
    assert "cancelled" not in summary
    # The crux: the auto-stack pass still ran for *all* healthy targets instead of
    # being skipped because the job errored out.
    assert "auto_stacked" in summary
    assert set(stacked) == {"M_42", "NGC_7000"}


def test_qc_cancel_during_target_is_classified_cancelled(solved_library, monkeypatch):
    # A cancel that surfaces as a raise (rather than run_qc_and_solve's graceful
    # early return) must still be classified as a cancel, not an error, by the new
    # except's cancel re-check.
    settings = Settings(
        data_root=str(solved_library), auto_ingest=False, auto_qc=True,
        auto_solve=False, auto_stack=False,
    )

    def fake_qc(proj, *, should_stop=None, **kwargs):  # noqa: ANN001
        # Behave like a mid-run cancellation that propagates as an exception.
        raise RuntimeError("interrupted")

    monkeypatch.setattr("webapp.pipeline.run_qc_and_solve", fake_qc)

    lib = Library.open_or_create(solved_library / "library")
    try:
        job = Job(kind="pipeline")
        job._cancel.set()  # the user cancelled — the raise coincides with a cancel
        summary = pipeline._pipeline_body(settings, _FakeJM(), job, root=None)
    finally:
        lib.close()

    assert summary.get("cancelled") is True
    # A cancel is not recorded as a per-target error.
    assert "qc_errors" not in summary
