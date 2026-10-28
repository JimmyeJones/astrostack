"""An ASTAP that is present but cannot be started is a *setup* problem.

A binary that lost its execute bit (or sits on a ``noexec`` mount), or one built
for another CPU, fails every frame identically. It used to escape the solve
ladder as a raw ``PermissionError`` / ``OSError`` string that no classifier
matched, so every sub read as an ordinary per-frame "plate-solve failed" and the
Target page never named the one-time fix. These run real stub files through the
real ``solve_one`` — no ``subprocess`` mock — so the OS itself refuses them.
"""

from __future__ import annotations

import os
import stat

import pytest

from seestack.solve.astap import (
    SOLVE_SETUP_ASTAP_CANNOT_RUN,
    ASTAPCannotRunError,
    ASTAPSolver,
    classify_solve_setup_error,
)
from seestack.solve.runner import solve_one

pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX exec semantics")


def _no_exec_bit(tmp_path):
    p = tmp_path / "astap_noexec" / "astap"
    p.parent.mkdir()
    p.write_text("#!/bin/sh\nexit 0\n")
    p.chmod(0o644)
    return p


def _wrong_format(tmp_path):
    # Executable, but not a binary this kernel can load and no ``#!`` line.
    p = tmp_path / "astap_garbage" / "astap"
    p.parent.mkdir()
    p.write_bytes(b"\x7fELF\x02\x01\x01garbage-not-a-real-binary" + b"\x00" * 64)
    p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return p


def _frame(tmp_path):
    f = tmp_path / "incoming" / "Light_M42_10.0s_0001.fit"
    f.parent.mkdir()
    f.write_bytes(b"the owner's only copy")
    return f


@pytest.mark.parametrize("make_stub", [_no_exec_bit, _wrong_format])
def test_solve_one_reports_an_unstartable_astap_as_a_setup_problem(tmp_path, make_stub):
    stub = make_stub(tmp_path)
    frame = _frame(tmp_path)
    before = frame.read_bytes()

    res = solve_one(1, str(frame), astap_path=str(stub), timeout_s=5.0)

    assert res.solved is False
    assert classify_solve_setup_error(res.error) == SOLVE_SETUP_ASTAP_CANNOT_RUN
    # Never touches the source sub.
    assert frame.read_bytes() == before
    assert sorted(p.name for p in frame.parent.iterdir()) == [frame.name]


def test_the_ladder_stops_on_the_first_unstartable_rung(tmp_path, monkeypatch):
    stub = _no_exec_bit(tmp_path)
    frame = _frame(tmp_path)
    solver = ASTAPSolver(astap_path=stub, timeout_s=5.0)
    calls = []
    real = solver._run_astap

    def counting(*a, **kw):
        calls.append(1)
        return real(*a, **kw)

    monkeypatch.setattr(solver, "_run_astap", counting)
    with pytest.raises(ASTAPCannotRunError):
        solver.solve(frame)
    assert len(calls) == 1


def test_a_transient_oserror_stays_an_ordinary_rung_failure(tmp_path, monkeypatch):
    # Out of memory / too many processes may clear on the next rung; it is not
    # "this binary can never run here".
    import errno

    frame = _frame(tmp_path)
    stub = tmp_path / "astap"
    stub.write_text("")
    solver = ASTAPSolver(astap_path=stub, timeout_s=5.0)

    def boom(cmd, **kw):
        raise OSError(errno.ENOMEM, "Cannot allocate memory")

    monkeypatch.setattr("seestack.solve.astap.subprocess.run", boom)
    res = solve_one(1, str(frame), astap_path=str(stub), timeout_s=5.0)
    assert res.solved is False
    assert classify_solve_setup_error(res.error) is None


def test_classifier_keeps_astap_missing_first():
    assert classify_solve_setup_error("astap not found") != SOLVE_SETUP_ASTAP_CANNOT_RUN
    assert classify_solve_setup_error("astap cannot run: x") == SOLVE_SETUP_ASTAP_CANNOT_RUN
    assert classify_solve_setup_error("Permission denied") is None
