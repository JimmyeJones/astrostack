"""Walk-away cost: a sub ASTAP cannot place is not re-solved on every import.

Full audit 2026-11-26 (``backend.md`` §5): ``build_solve_arglist`` re-offers every
``solve_failed:`` sub with no attempt count, so 8 unsolvable subs cost 3 ASTAP
runs each on *every* later scan — at ~1 % unsolvable on a library of tens of
thousands of subs, hours of solver time per new night, holding the single
worker. Retries can succeed (#965), so the walk-away pipeline backs off instead
of giving up; every user-started solve still retries everything.
"""

from __future__ import annotations

import pytest

import seestack.solve.runner as runner
from seestack.io.project import FrameRow, Project
from seestack.io.scanner import run_qc_and_solve
from seestack.solve.astap import SOLVE_SETUP_NO_DATABASE
from seestack.solve.runner import (
    SOLVE_BACKOFF_BASE_S,
    SOLVE_BACKOFF_MAX_S,
    SOLVE_FREE_ATTEMPTS,
    SolveResult,
    solve_backoff_s,
)
from tests.synth import make_synth_wcs_text

DAY = 24 * 3600.0


def _project(tmp_path, n: int = 3) -> Project:
    """``n`` QC'd, accepted, unsolved subs on disk."""
    proj = Project.create(tmp_path / "p", name="backoff")
    raws = tmp_path / "incoming"
    raws.mkdir()
    for i in range(n):
        f = raws / f"Light_M 42_10.0s_{i:04d}.fit"
        f.write_bytes(b"x" * 64)
        proj.add_frame(FrameRow(source_path=str(f), star_count=50,
                                width_px=480, height_px=320,
                                bayer_pattern="RGGB"))
    return proj


class _Solver:
    """Stands in for ``solve_one``: records who it was asked to solve."""

    def __init__(self, *, error: str = "No solution found", solves: set[int] = frozenset()):
        self.error = error
        self.solves = set(solves)
        self.calls: list[int] = []

    def __call__(self, frame_id, fits_path, *a, **kw):
        self.calls.append(frame_id)
        if frame_id in self.solves:
            return SolveResult(frame_id, fits_path, True, make_synth_wcs_text(),
                               83.6, -5.4, 5.0, 0.0, None)
        return SolveResult(frame_id, fits_path, False, None, None, None, None, None,
                           self.error)


@pytest.fixture
def clock(monkeypatch):
    import seestack.io.scanner as scanner

    class _Clock:
        t = 1_800_000_000.0

        def time(self):
            return self.t

    c = _Clock()
    monkeypatch.setattr(scanner.time, "time", c.time)
    return c


def _walk_away(proj, solver, monkeypatch, **kw):
    monkeypatch.setattr(runner, "solve_one", solver)
    solver.calls.clear()
    return run_qc_and_solve(proj, run_qc=False, run_solve=True, serial=True,
                            retry_unsolved_with_sibling_hint=False,
                            solve_backoff=kw.pop("solve_backoff", True), **kw)


def test_the_backoff_schedule():
    assert [solve_backoff_s(n) for n in range(SOLVE_FREE_ATTEMPTS)] == [0.0] * SOLVE_FREE_ATTEMPTS
    assert solve_backoff_s(SOLVE_FREE_ATTEMPTS) == SOLVE_BACKOFF_BASE_S
    assert solve_backoff_s(SOLVE_FREE_ATTEMPTS + 1) == 2 * SOLVE_BACKOFF_BASE_S
    assert solve_backoff_s(SOLVE_FREE_ATTEMPTS + 50) == SOLVE_BACKOFF_MAX_S


def test_an_unsolvable_sub_is_not_re_solved_on_every_import(tmp_path, monkeypatch, clock):
    """FAIL-BEFORE: every import re-ran the solver on all three subs."""
    proj = _project(tmp_path)
    try:
        solver = _Solver()
        ids = sorted(f.id for f in proj.iter_frames())
        # The free retries: each import tries them all, as before.
        for _ in range(SOLVE_FREE_ATTEMPTS):
            _walk_away(proj, solver, monkeypatch)
            assert sorted(solver.calls) == ids
            clock.t += 3600
        # Then they wait: an import an hour later runs ASTAP on none of them.
        summary = _walk_away(proj, solver, monkeypatch)
        assert solver.calls == []
        assert summary["solve_total"] == 0
        assert summary["solve_backoff_waiting"] == len(ids)
        # A day after the last failure they are tried once more…
        clock.t += DAY
        _walk_away(proj, solver, monkeypatch)
        assert sorted(solver.calls) == ids
        # …and the next wait is twice as long.
        clock.t += DAY + 60
        _walk_away(proj, solver, monkeypatch)
        assert solver.calls == []
        clock.t += DAY
        _walk_away(proj, solver, monkeypatch)
        assert sorted(solver.calls) == ids
    finally:
        proj.close()


def test_a_new_sub_is_still_solved_at_once(tmp_path, monkeypatch, clock):
    proj = _project(tmp_path, n=2)
    try:
        solver = _Solver()
        for _ in range(SOLVE_FREE_ATTEMPTS):
            _walk_away(proj, solver, monkeypatch)
        f = tmp_path / "incoming" / "Light_M 42_10.0s_0099.fit"
        f.write_bytes(b"x" * 64)
        new_id = proj.add_frame(FrameRow(source_path=str(f), star_count=50))
        _walk_away(proj, solver, monkeypatch)
        assert solver.calls == [new_id]
    finally:
        proj.close()


def test_a_user_started_solve_retries_every_sub(tmp_path, monkeypatch, clock):
    """"Locate my subs" / Process / re-process pass no back-off, and do not count."""
    proj = _project(tmp_path)
    try:
        solver = _Solver()
        for _ in range(SOLVE_FREE_ATTEMPTS):
            _walk_away(proj, solver, monkeypatch)
        _walk_away(proj, solver, monkeypatch, solve_backoff=False)
        assert len(solver.calls) == 3
        assert {a for a, _t in proj.solve_attempts().values()} == {SOLVE_FREE_ATTEMPTS}
    finally:
        proj.close()


def test_changing_the_solver_starts_every_count_again(tmp_path, monkeypatch, clock):
    """A new star database, ASTAP, field of view or timeout can change the answer."""
    proj = _project(tmp_path)
    try:
        solver = _Solver()
        for _ in range(SOLVE_FREE_ATTEMPTS):
            _walk_away(proj, solver, monkeypatch)
        _walk_away(proj, solver, monkeypatch)
        assert solver.calls == []
        _walk_away(proj, solver, monkeypatch, astap_timeout_s=240.0)
        assert len(solver.calls) == 3
    finally:
        proj.close()


def test_a_setup_failure_never_counts(tmp_path, monkeypatch, clock):
    """No star database says nothing about the sub: installing it must not then
    find every sub waiting out a back-off."""
    proj = _project(tmp_path)
    try:
        solver = _Solver(error=f"ASTAP: {SOLVE_SETUP_NO_DATABASE} found")
        for _ in range(SOLVE_FREE_ATTEMPTS + 2):
            _walk_away(proj, solver, monkeypatch)
            assert len(solver.calls) == 3
        assert proj.solve_attempts() == {}
    finally:
        proj.close()


def test_a_sub_that_solves_forgets_its_failures(tmp_path, monkeypatch, clock):
    proj = _project(tmp_path)
    try:
        ids = sorted(f.id for f in proj.iter_frames())
        _walk_away(proj, _Solver(), monkeypatch)
        _walk_away(proj, _Solver(solves={ids[0]}), monkeypatch)
        counts = proj.solve_attempts()
        assert ids[0] not in counts
        assert counts[ids[1]][0] == 2
        assert proj.get_frame(ids[0]).wcs_json
    finally:
        proj.close()


def test_an_old_project_gains_the_table_on_open(tmp_path):
    """Upgrade-safe: the count lives in an aux table created on every open, so a
    project written before it existed opens and counts, and no SCHEMA_VERSION bump
    makes a rolled-back build refuse it."""
    proj = _project(tmp_path, n=1)
    proj._conn.execute("DROP TABLE solve_attempts")
    proj.close()
    proj = Project.open(tmp_path / "p")
    try:
        assert proj.solve_attempts() == {}
        fid = next(proj.iter_frames()).id
        proj.note_solve_failures([fid], 5.0)
        proj.note_solve_failures([fid], 9.0)
        assert proj.solve_attempts() == {fid: (2, 9.0)}
    finally:
        proj.close()
