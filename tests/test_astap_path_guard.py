"""A typed ASTAP path may only name an ASTAP program — never "any executable".

Audit 2026-11-26: ``astap_path`` is a setting anyone who can reach the app can
change (auth is off by default) and the solver executes it. ``find_astap``
accepted any path that existed, so a request could name a shell or a script and
the next solve ran it as the container's user — which is root, with the owner's
only copy of his raw subs mounted read-write.
"""
from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from seestack.solve.astap import astap_path_problem, find_astap, is_astap_program_name
from seestack.solve.runner import solve_one
from tests.synth import write_seestar_fits


def _script(path: Path, marker: Path) -> Path:
    path.write_text(f"#!/bin/sh\necho ran > '{marker}'\nexit 0\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


@pytest.mark.parametrize("name", ["astap", "astap_cli", "ASTAP.EXE", "astap_cli.exe"])
def test_astap_names_are_accepted(tmp_path, name):
    exe = tmp_path / name
    exe.write_text("")
    assert is_astap_program_name(exe)
    assert find_astap(str(exe)) == exe


@pytest.mark.parametrize("name", ["sh", "evil.sh", "astap.sh", "not-astap", "python3"])
def test_any_other_existing_file_is_refused(tmp_path, name):
    exe = _script(tmp_path / name, tmp_path / "marker")
    assert find_astap(str(exe)) is None
    assert "isn't an ASTAP program" in (astap_path_problem(str(exe)) or "")


def test_a_real_shell_is_refused():
    assert find_astap("/bin/sh") is None


def test_a_refused_path_is_never_executed(tmp_path):
    marker = tmp_path / "marker"
    evil = _script(tmp_path / "evil.sh", marker)
    frame = write_seestar_fits(tmp_path / "f.fit", width=64, height=48)
    res = solve_one(1, str(frame), astap_path=str(evil), timeout_s=5.0)
    assert not res.solved
    assert not marker.exists(), "the refused program was executed"


def test_a_folder_is_still_searched_for_astap_only(tmp_path):
    _script(tmp_path / "evil.sh", tmp_path / "marker")
    assert find_astap(str(tmp_path)) is None
    (tmp_path / "astap_cli").write_text("")
    assert find_astap(str(tmp_path)) == tmp_path / "astap_cli"
    assert os.path.basename(str(find_astap(str(tmp_path)))) == "astap_cli"
