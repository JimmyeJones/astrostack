"""An ASTAP that is there but can't be started reaches the user as a setup
problem: the Target page's banner (``reject-summary.solve_setup_problem``) and
the ``/api/system`` hint both name it, instead of every sub reading as an
ordinary "plate-solve failed"."""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX exec semantics")


def _stub(tmp_path):
    p = tmp_path / "astap_noexec" / "astap"
    p.parent.mkdir()
    p.write_text("#!/bin/sh\nexit 0\n")
    p.chmod(0o644)
    return p


def test_reject_summary_names_an_unstartable_astap(client, built_library, data_root, tmp_path):
    from seestack.io.library import Library
    from seestack.solve.runner import apply_solve_result_to_db, solve_one

    stub = _stub(tmp_path)
    frames = client.get("/api/targets/M_42/frames").json()
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target("M_42")
        try:
            for f in frames[:3]:
                row = proj.get_frame(f["id"])
                path = row.cached_path or row.source_path
                res = solve_one(f["id"], str(path), astap_path=str(stub), timeout_s=5.0)
                apply_solve_result_to_db(proj, res)
            reasons = {proj.get_frame(f["id"]).reject_reason for f in frames[:3]}
        finally:
            proj.close()
    finally:
        lib.close()

    # One canonical, tally-able reason — not three raw exception strings.
    assert reasons == {"solve_failed:astap cannot run"}
    body = client.get("/api/targets/M_42/frames/reject-summary").json()
    assert body["solve_setup_problem"] == {"kind": "astap", "frames": 3, "cannot_run": True}


def test_system_hint_names_an_unstartable_astap(client, tmp_path):
    stub = _stub(tmp_path)
    assert client.put("/api/settings", json={"astap_path": str(stub)}).status_code == 200
    astap = client.get("/api/system").json()["astap"]
    assert astap["found"] is True
    assert astap["runs"] is False
    assert "can't be started" in astap["hint"]
