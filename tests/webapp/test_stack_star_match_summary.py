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


def test_the_forms_copy_does_not_tell_a_mosaic_user_the_pass_is_skipped():
    """The other half of "it leaves the engine": the sentence beside the switch.

    v0.484.0 taught this pass to place a **mosaic's** subs — one star anchor per
    solved panel, asserted by
    ``tests/test_stack_star_match_unsolved.py::test_a_mosaic_stack_takes_the_subs_the_solver_could_not_place``
    — and left the Stack form still ending *"Skipped on a mosaic, where the subs
    cover different parts of the sky."* The owner is a heavy mosaic user, so on the
    one surface where he learns what the switch does, the feature built for him said
    it was not for him. Nothing tested the copy, so nothing caught it.

    Worded as "the claim it must not make" rather than as a snapshot of the current
    sentence: this help text is rewritten regularly, and a test that pins the exact
    wording is one that gets updated without being read.
    """
    from webapp.schemas import stack_option_fields

    field = next(f for f in stack_option_fields()
                 if f.key == "star_match_unsolved")
    text = (field.help or "")
    lowered = text.lower()
    assert "mosaic" in lowered, text
    for claim in ("skipped on a mosaic", "not on a mosaic", "mosaics are skipped",
                  "single field only", "single-field only"):
        assert claim not in lowered, (claim, text)
    # And it still names the case that genuinely is out of reach, so "mosaics are
    # included" cannot be read as "every panel": a panel where *nothing* solved has
    # no anchor, deliberately (v0.484.0 — a centre-shift cap wide enough to admit a
    # whole panel step would also admit a wrong lock).
    assert "panel" in lowered, text
