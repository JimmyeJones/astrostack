"""The stack-then-solve bootstrap's rescue must reach the user.

``run_qc_and_solve`` already reports ``bootstrap_engaged`` /
``bootstrap_solved`` / ``bootstrap_propagated`` when the opt-in bootstrap lifts
un-located subs into the stack (v0.210.0) — and the single-target jobs
(``qc_solve`` / ``process_target``) return that summary verbatim. The
whole-library **scan** discarded it, though, which is exactly the walk-away path
where the rescue happens unattended: the beginner who turned the setting on saw a
suddenly-thicker stack with nothing saying why. The scan now rolls the per-target
counts up into ``summary["bootstrap_rescued"]``.
"""

from __future__ import annotations

from seestack.io.library import Library
from webapp import pipeline
from webapp.config import Settings
from webapp.jobs import Job


class _FakeJM:
    def maybe_flush(self, job) -> None:  # noqa: ANN001
        pass


def _settings(root):
    return Settings(
        data_root=str(root), auto_ingest=False, auto_qc=True,
        auto_solve=True, auto_stack=False, astap_bootstrap_solve=True,
    )


def test_scan_reports_the_bootstrap_rescue_per_target(solved_library, monkeypatch):
    seen: list[object] = []

    def fake_qc(proj, **kwargs):  # noqa: ANN001
        seen.append(proj)
        base = {"qc_done": 0, "qc_total": 0, "solve_done": 0, "solve_total": 0}
        # Only the first target's subs needed rescuing.
        if len(seen) == 1:
            base |= {"bootstrap_engaged": True, "bootstrap_solved": True,
                     "bootstrap_propagated": 12}
        return base

    monkeypatch.setattr("webapp.pipeline.run_qc_and_solve", fake_qc)

    lib = Library.open_or_create(solved_library / "library")
    try:
        summary = pipeline._pipeline_body(
            _settings(solved_library), _FakeJM(), Job(kind="pipeline"), root=None)
    finally:
        lib.close()

    rescued = summary.get("bootstrap_rescued")
    assert rescued == {"M_42": 12}, summary


def test_scan_omits_the_key_when_the_bootstrap_never_engaged(solved_library, monkeypatch):
    """A run where every sub plate-solved on its own says nothing — the summary
    key is absent rather than a misleading zero."""
    def fake_qc(proj, **kwargs):  # noqa: ANN001
        return {"qc_done": 3, "qc_total": 3, "solve_done": 3, "solve_total": 3}

    monkeypatch.setattr("webapp.pipeline.run_qc_and_solve", fake_qc)

    lib = Library.open_or_create(solved_library / "library")
    try:
        summary = pipeline._pipeline_body(
            _settings(solved_library), _FakeJM(), Job(kind="pipeline"), root=None)
    finally:
        lib.close()

    assert "bootstrap_rescued" not in summary


def test_scan_ignores_an_engaged_bootstrap_that_rescued_nothing(
        solved_library, monkeypatch):
    """The bootstrap can engage, fail to solve the deep image, and propagate
    nothing. That is not a rescue — don't claim one."""
    def fake_qc(proj, **kwargs):  # noqa: ANN001
        return {"qc_done": 0, "qc_total": 0, "solve_done": 0, "solve_total": 0,
                "bootstrap_engaged": True, "bootstrap_solved": False,
                "bootstrap_propagated": 0}

    monkeypatch.setattr("webapp.pipeline.run_qc_and_solve", fake_qc)

    lib = Library.open_or_create(solved_library / "library")
    try:
        summary = pipeline._pipeline_body(
            _settings(solved_library), _FakeJM(), Job(kind="pipeline"), root=None)
    finally:
        lib.close()

    assert "bootstrap_rescued" not in summary
