"""A full container temp dir is a *setup* problem, not a sub that "couldn't be located".

Every plate solve copies its sub into a scratch dir under ``tempfile.gettempdir()``
(``ASTAPSolver._solve_once``) — in the container that is its own writable layer,
a different filesystem from the mounted library. When it was full, every solve
failed before ASTAP ran with a raw ``OSError: [Errno 28] …`` cut at 120 chars,
nothing was logged (the DB writes all succeeded), and the reject summary blamed
the subs ("check your subs aren't trailed or fogged"). Scout 2026-11-11, sweep (3).
"""

from __future__ import annotations

import errno
import logging
import os

import pytest

import seestack.solve.astap as astap_mod
from seestack.solve.astap import (
    SOLVE_SETUP_SCRATCH_FULL,
    ASTAPScratchError,
    ASTAPSolver,
    classify_solve_setup_error,
)
from seestack.solve.runner import apply_solve_result_to_db, solve_one

pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX stub binary")


def _stub_astap(tmp_path):
    """A startable ASTAP that never solves — it must not even be reached."""
    p = tmp_path / "astap_stub" / "astap"
    p.parent.mkdir()
    p.write_text("#!/bin/sh\necho ran >> \"$(dirname \"$0\")/ran.log\"\nexit 1\n")
    p.chmod(0o755)
    return p


def _frame(tmp_path, name="Light_M 42_10.0s_0001.fit"):
    d = tmp_path / "incoming"
    d.mkdir(exist_ok=True)
    f = d / name
    f.write_bytes(b"the owner's only copy" * 64)
    return f


def _copy_raises_enospc(monkeypatch):
    """What ``shutil.copy2`` does on a full disk: ``_fastcopy_sendfile`` raises
    ENOSPC labelled with the *source* name."""
    calls = []

    def full(src, dst, *a, **kw):
        calls.append(dst)
        err = OSError(errno.ENOSPC, os.strerror(errno.ENOSPC))
        err.filename, err.filename2 = str(src), str(dst)
        raise err

    monkeypatch.setattr(astap_mod.shutil, "copy2", full)
    return calls


def test_a_full_temp_dir_is_a_canonical_setup_reason(tmp_path, monkeypatch):
    """FAIL-BEFORE: ``OSError: [Errno 28] No space left on device: '…'``, which no
    classifier matched."""
    stub = _stub_astap(tmp_path)
    frame = _frame(tmp_path)
    _copy_raises_enospc(monkeypatch)

    res = solve_one(1, str(frame), astap_path=str(stub), timeout_s=5.0)

    assert res.solved is False
    assert classify_solve_setup_error(res.error) == SOLVE_SETUP_SCRATCH_FULL
    # ASTAP was never started, and the source is untouched.
    assert not (stub.parent / "ran.log").exists()
    assert sorted(p.name for p in frame.parent.iterdir()) == [frame.name]


def test_a_missing_temp_dir_is_the_same_setup_reason(tmp_path, monkeypatch):
    """No patched copy: the scratch dir itself can't be created."""
    stub = _stub_astap(tmp_path)
    frame = _frame(tmp_path)
    monkeypatch.setattr(astap_mod.tempfile, "tempdir", str(tmp_path / "no-such-tmp"))

    res = solve_one(1, str(frame), astap_path=str(stub), timeout_s=5.0)

    assert classify_solve_setup_error(res.error) == SOLVE_SETUP_SCRATCH_FULL
    assert not (stub.parent / "ran.log").exists()


def test_the_ladder_stops_on_the_first_rung(tmp_path, monkeypatch):
    stub = _stub_astap(tmp_path)
    frame = _frame(tmp_path)
    calls = _copy_raises_enospc(monkeypatch)
    solver = ASTAPSolver(astap_path=stub, timeout_s=5.0)

    with pytest.raises(ASTAPScratchError) as ei:
        solver.solve(frame)

    assert len(calls) == 1
    # Names the temp dir (what to clear), not the sub.
    assert SOLVE_SETUP_SCRATCH_FULL in str(ei.value)
    assert frame.name not in str(ei.value)


def test_an_unreadable_source_stays_that_subs_own_failure(tmp_path, monkeypatch):
    """A permission error on the *source* is one sub's problem, not the temp dir's
    — it must never raise the "free space" banner."""
    stub = _stub_astap(tmp_path)
    frame = _frame(tmp_path)

    def denied(src, dst, *a, **kw):
        raise PermissionError(errno.EACCES, os.strerror(errno.EACCES), str(src))

    monkeypatch.setattr(astap_mod.shutil, "copy2", denied)
    res = solve_one(1, str(frame), astap_path=str(stub), timeout_s=5.0)

    assert res.solved is False
    assert classify_solve_setup_error(res.error) is None


def test_the_stored_reason_is_canonical_and_survives_truncation(tmp_path, monkeypatch):
    from tests.test_stack_pipeline import _build_project

    stub = _stub_astap(tmp_path)
    proj = _build_project(tmp_path, n=2)
    try:
        _copy_raises_enospc(monkeypatch)
        for row in proj.iter_frames():
            res = solve_one(row.id, row.cached_path, astap_path=str(stub), timeout_s=5.0)
            apply_solve_result_to_db(proj, res)
        reasons = {r.reject_reason for r in proj.iter_frames()}
    finally:
        proj.close()
    assert reasons == {f"solve_failed:{SOLVE_SETUP_SCRATCH_FULL}"}


def test_the_scan_logs_the_temp_dir_once_and_counts_it(tmp_path, monkeypatch, caplog):
    """FAIL-BEFORE: the pass ended ``solve_ok: 0`` with no log line at all, so
    ``/api/logs`` (and the observer) never saw why."""
    from seestack.io.scanner import run_qc_and_solve
    from tests.test_stack_pipeline import _build_project

    stub = _stub_astap(tmp_path)
    proj = _build_project(tmp_path, n=3)
    try:
        for row in proj.iter_frames():
            proj.update_frame(row.id, wcs_json=None, ra_center_deg=None, dec_center_deg=None)
        _copy_raises_enospc(monkeypatch)
        with caplog.at_level(logging.WARNING, logger="seestack.io.scanner"):
            summary = run_qc_and_solve(proj, run_qc=False, run_solve=True, serial=True,
                                       astap_path=str(stub))
    finally:
        proj.close()

    assert summary["solve_total"] == 3
    assert summary["solve_ok"] == 0
    assert summary["solve_scratch_full"] == 3
    warnings = [r.getMessage() for r in caplog.records if "temp dir" in r.getMessage()]
    assert len(warnings) == 1
    assert "3 sub(s)" in warnings[0]
    assert os.path.basename(astap_mod.tempfile.gettempdir()) in warnings[0]


def test_the_reject_summary_does_not_blame_the_subs():
    """FAIL-BEFORE: ``dominant:solve_failed`` — "check your subs aren't trailed or
    fogged" — for subs the solver never looked at."""
    from webapp.rejection_summary import bucket_for, summarize_rejections

    reason = f"solve_failed:{SOLVE_SETUP_SCRATCH_FULL}"
    assert bucket_for(reason) == "unsolved"
    out = summarize_rejections({reason: 12}, n_accepted=0)
    assert out["verdict"]["key"] != "dominant:solve_failed"
    assert "trailed" not in out["verdict"]["text"]
    # An ordinary per-frame failure keeps its bucket.
    assert bucket_for("solve_failed:no catalog match") == "solve_failed"
