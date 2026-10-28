"""The desktop Library dialog's per-target log line reports real solves."""

import pytest

pytest.importorskip("PySide6")

from seestack.gui.library_dialog import _target_summary_line  # noqa: E402


def test_a_field_where_nothing_located_does_not_claim_a_perfect_solve():
    # Every solve was *attempted* (the progress counter is full) and none
    # came back with a WCS — the line must say 0, not 40/40.
    summary = {"qc_done": 40, "qc_total": 40,
               "solve_done": 40, "solve_total": 40, "solve_ok": 0}
    line = _target_summary_line("M 42", summary, run_solve=True)
    assert line == "  ✓ M 42: QC 40/40, solved 0/40"


def test_partial_solve_reports_the_frames_actually_located():
    summary = {"qc_done": 40, "qc_total": 40,
               "solve_done": 40, "solve_total": 40, "solve_ok": 31}
    assert _target_summary_line("M 42", summary, True).endswith(", solved 31/40")


def test_solve_clause_is_omitted_without_an_honest_count_or_when_not_solving():
    no_ok = {"qc_done": 5, "qc_total": 5, "solve_done": 5, "solve_total": 5}
    assert _target_summary_line("M 42", no_ok, True) == "  ✓ M 42: QC 5/5"
    with_ok = dict(no_ok, solve_ok=5)
    assert _target_summary_line("M 42", with_ok, False) == "  ✓ M 42: QC 5/5"
