"""Auto-stack pipeline pass: fires for eligible targets, non-fatal, idempotent."""

from __future__ import annotations

from types import SimpleNamespace

from seestack.io.library import Library
from seestack.io.project import StackRunRow
from webapp import pipeline
from webapp.config import Settings
from webapp.jobs import Job


class _FakeJM:
    def maybe_flush(self, job) -> None:  # noqa: ANN001
        pass


def _settings(root) -> Settings:
    # Only auto_stack on, so the run goes straight to the auto-stack pass.
    return Settings(
        data_root=str(root), auto_ingest=False, auto_qc=False,
        auto_solve=False, auto_stack=True,
    )


def _patch_run_stack(monkeypatch):
    calls: list[str] = []

    def fake_run_stack(proj, opts, *, progress=None, cancel=None):  # noqa: ANN001
        calls.append(getattr(proj, "name", "?"))
        return SimpleNamespace(
            output_dir="/tmp/x", n_frames_used=3, canvas_shape=(1, 1, 3),
            cancelled=False, errors=[],
        )

    monkeypatch.setattr("seestack.stack.stacker.run_stack", fake_run_stack)
    return calls


def test_auto_stack_runs_for_solved_targets(solved_library, monkeypatch):
    calls = _patch_run_stack(monkeypatch)
    lib = Library.open_or_create(solved_library / "library")
    try:
        job = Job(kind="pipeline")
        summary = pipeline._pipeline_body(_settings(solved_library), _FakeJM(), job, root=None)
    finally:
        lib.close()
    # Every solved target with no prior stack should have been stacked.
    assert len(calls) >= 1
    assert summary["auto_stacked"]
    assert not summary.get("stack_errors")


def test_auto_stack_skips_already_stacked(solved_library, monkeypatch):
    calls = _patch_run_stack(monkeypatch)
    lib = Library.open_or_create(solved_library / "library")
    try:
        # Give every target a recent stack run covering all its solved frames.
        for entry in lib.list_targets():
            proj = lib.open_target(entry.safe_name)
            try:
                n = sum(1 for f in proj.iter_frames(accepted_only=True) if f.wcs_json)
                proj.add_stack_run(StackRunRow(
                    id=None, timestamp_utc="2026-05-01T00:00:00Z",
                    output_basename="master", fits_path=None, tiff_path=None,
                    preview_path=None, n_frames_used=n,
                    canvas_h=10, canvas_w=10, coverage_min=1, coverage_max=n,
                    options_json="{}",
                ))
            finally:
                proj.close()
        job = Job(kind="pipeline")
        summary = pipeline._pipeline_body(_settings(solved_library), _FakeJM(), job, root=None)
    finally:
        lib.close()
    assert calls == []                       # nothing new to stack
    assert summary["auto_stacked"] == []
    assert summary["auto_stack_skipped"]


def test_auto_stack_failure_is_non_fatal(solved_library, monkeypatch):
    def boom(proj, opts, *, progress=None, cancel=None):  # noqa: ANN001
        raise ValueError("No accepted frames are plate-solved yet")

    monkeypatch.setattr("seestack.stack.stacker.run_stack", boom)
    lib = Library.open_or_create(solved_library / "library")
    try:
        job = Job(kind="pipeline")
        # Must NOT raise — the pipeline records the error and carries on.
        summary = pipeline._pipeline_body(_settings(solved_library), _FakeJM(), job, root=None)
    finally:
        lib.close()
    assert summary["stack_errors"]
    assert summary["auto_stacked"] == []
