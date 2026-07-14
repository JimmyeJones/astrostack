"""One target that fails to *open* must not sink the whole unattended batch.

Regression: the auto-stack loop (`_pipeline_body`) and the reprocess-all loop
(`submit_reprocess_all`) each isolate a ``_stack_target`` failure so "one bad
target shouldn't sink the batch" — but their per-target *pre-stack* helpers
(frame-count / mixed-pointing check / mark-attempt for auto-stack; stale-version
lookup / refresh / options lookup / open for reprocess-all) all open the
target's project DB and were left **outside** that ``try/except``. A target
still registered in ``library.sqlite`` but whose ``project.sqlite`` is gone or
corrupt (deleted on the NAS directly, a partial delete, a restored-from-backup
mismatch) therefore raised ``FileNotFoundError`` out of the whole pass — the job
went red and **every other target was silently skipped**, exactly the failure
the sibling QC/solve loop already isolates (see test_pipeline_qc_isolation).
Both loops must now record the broken target and carry on.
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


def _break_first_target(data_root) -> str:
    """Delete M_42's project.sqlite so its next open raises — leaving the target
    registered in the library. Returns its safe name."""
    lib = Library.open_or_create(data_root / "library")
    try:
        broken = lib.list_targets()[0]  # M_42 sorts before NGC_7000
        db = lib.target_dir(broken) / "project.sqlite"
        assert db.exists()
        db.unlink()
        return broken.safe_name
    finally:
        lib.close()


def _fake_stack_recorder():
    stacked: list[str] = []

    def fake_stack_target(settings, jm, job, lib, safe, **kwargs):  # noqa: ANN001
        stacked.append(safe)
        return {"run_id": None, "cancelled": False}

    return fake_stack_target, stacked


def test_auto_stack_isolates_a_target_that_fails_to_open(solved_library, monkeypatch):
    broken = _break_first_target(solved_library)
    fake_stack_target, stacked = _fake_stack_recorder()
    monkeypatch.setattr("webapp.pipeline._stack_target", fake_stack_target)

    settings = Settings(
        data_root=str(solved_library), auto_ingest=False, auto_qc=False,
        auto_solve=False, auto_stack=True,
    )

    # Before the fix this raised FileNotFoundError out of the whole pass; after it
    # returns a normal summary with the broken target recorded.
    summary = pipeline._pipeline_body(settings, _FakeJM(), Job(kind="pipeline"), root=None)

    # The broken target is recorded as a stack error, not raised.
    assert broken in summary.get("stack_errors", {}), summary
    assert "cancelled" not in summary
    # The crux: the healthy target still auto-stacked instead of being skipped
    # because a sibling target's open blew up the pass.
    assert stacked == ["NGC_7000"], stacked


def test_reprocess_all_isolates_a_target_that_fails_to_open(solved_library, monkeypatch):
    broken = _break_first_target(solved_library)
    fake_stack_target, stacked = _fake_stack_recorder()
    monkeypatch.setattr("webapp.pipeline._stack_target", fake_stack_target)

    settings = Settings(data_root=str(solved_library))
    job = Job(kind="reprocess_all")
    captured: dict = {}

    class _CaptureJM(_FakeJM):
        def submit(self, kind, fn, target=None):  # noqa: ANN001
            captured["fn"] = fn
            return job

    pipeline.submit_reprocess_all(settings, _CaptureJM())
    # Before the fix captured["fn"](job) raised FileNotFoundError; after the fix
    # it completes with the broken target recorded in "failed".
    result = captured["fn"](job)

    assert result["stacked"] == 1, result
    assert stacked == ["NGC_7000"], stacked
    failed_targets = {f["target"] for f in result.get("failed", [])}
    assert broken in failed_targets, result
    assert result["cancelled"] is False


def test_reprocess_all_progress_advances_over_a_broken_target(solved_library, monkeypatch):
    """The progress counter must still advance past a broken target (the fix routes
    the per-target progress update through ``finally``)."""
    _break_first_target(solved_library)
    fake_stack_target, _ = _fake_stack_recorder()
    monkeypatch.setattr("webapp.pipeline._stack_target", fake_stack_target)

    progress: list[tuple[int, int]] = []
    real_set = Job.set_progress

    def spy_set_progress(self, phase, done, total, detail=""):  # noqa: ANN001
        if phase == "reprocess":
            progress.append((done, total))
        return real_set(self, phase, done, total, detail)

    monkeypatch.setattr(Job, "set_progress", spy_set_progress)

    settings = Settings(data_root=str(solved_library))
    job = Job(kind="reprocess_all")
    captured: dict = {}

    class _CaptureJM(_FakeJM):
        def submit(self, kind, fn, target=None):  # noqa: ANN001
            captured["fn"] = fn
            return job

    pipeline.submit_reprocess_all(settings, _CaptureJM())
    captured["fn"](job)

    # Both targets (the broken one and the healthy one) advanced the counter to 2/2.
    assert (2, 2) in progress, progress
