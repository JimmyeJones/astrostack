"""The star-matched count reaches the job result the walk-away user actually reads.

``StackResult.n_star_matched`` says how much of a picture's depth came from subs
placed by their star patterns rather than located in the sky. That only means
something if it leaves the engine: the Jobs summary is where a finished stack lands,
and `Jobs.tsx::starMatchedNote` turns this number into the one sentence that says
so. The sibling of ``test_auto_stack_saved_masters``' calibration-warning
forwarding, and written the same way — ``run_stack`` is stubbed, because what is
under test is the wiring, not the stacker.
"""

from types import SimpleNamespace

import pytest

pytest.importorskip("astropy")

from seestack.io.library import Library  # noqa: E402
from webapp import pipeline  # noqa: E402
from webapp.config import Settings  # noqa: E402
from webapp.jobs import Job  # noqa: E402


class _FakeJM:
    """The tiny slice of JobManager ``_stack_target`` touches."""

    def set_progress(self, *a, **k) -> None:  # noqa: ANN002, ANN003
        pass

    def append_log(self, *a, **k) -> None:  # noqa: ANN002, ANN003
        pass


def _stack_returning(monkeypatch, **fields):
    def fake_run_stack(proj, opts, *, progress=None, cancel=None,
                       memory_budget_gb=None, app_version=None):  # noqa: ANN001
        return SimpleNamespace(
            output_dir="/tmp/x", run_id=1, n_frames_used=9, canvas_shape=(1, 1, 3),
            cancelled=False, errors=[], excluded_frames=[],
            calibration_warnings=[], **fields,
        )

    monkeypatch.setattr("seestack.stack.stacker.run_stack", fake_run_stack)


def _run(data_root):
    lib = Library.open_or_create(data_root / "library")
    try:
        safe = lib.list_targets()[0].safe_name
        return pipeline._stack_target(
            Settings(data_root=str(data_root)), jm=_FakeJM(),
            job=Job(kind="pipeline"), lib=lib, safe=safe,
        )
    finally:
        lib.close()


def test_the_count_rides_the_job_result(solved_library, monkeypatch):
    _stack_returning(monkeypatch, n_star_matched=6)
    assert _run(solved_library)["n_star_matched"] == 6


def test_a_run_with_the_option_off_reports_zero(solved_library, monkeypatch):
    """The default, and so every ordinary run: the note self-omits on 0."""
    _stack_returning(monkeypatch, n_star_matched=0)
    assert _run(solved_library)["n_star_matched"] == 0


def test_a_result_from_before_the_field_existed_degrades_to_zero(
        solved_library, monkeypatch):
    """Upgrade-safety, the same shape the calibration-warning forwarding needs: a
    result object with no such attribute must read as "nothing to say" rather than
    raise mid-job."""
    _stack_returning(monkeypatch)
    assert _run(solved_library)["n_star_matched"] == 0
