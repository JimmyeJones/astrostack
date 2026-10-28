"""A Settings "ASTAP path" that is set but wrong must not read as "ASTAP isn't
installed" (Scout 2026-10-28, sweep (3)).

The value the field holds is cleaned of what a paste adds (whitespace, one pair
of quotes) — a field holding one space *looks* blank and means blank — a folder
is searched for the program inside it, and a path that still leads nowhere is
named, with the built-in ASTAP offered by path, in the solve reason and the
``/api/system`` hint. It never silently falls back to the bundled binary.

The bundled install is a real working stub on ``SEESTACK_ASTAP_PATH`` (the
Docker image's layout, database beside it), run through the real ``find_astap``
/ ``solve_one`` — no mocks.
"""

from __future__ import annotations

import os

import pytest

from seestack.solve.astap import (
    SOLVE_SETUP_ASTAP_MISSING,
    astap_path_problem,
    classify_solve_setup_error,
    find_astap,
    find_star_db_dir,
)
from seestack.solve.runner import solve_one

pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX exec semantics")

# A NAS host-side path the container can't see (shape only, not anyone's).
_HOST_PATH = "/nonexistent-host-pool/apps/astap/astap"


@pytest.fixture()
def bundled(tmp_path, monkeypatch):
    d = tmp_path / "opt_astap"
    d.mkdir()
    exe = d / "astap"
    exe.write_text("#!/bin/sh\necho 'ASTAP version 2024.x stub'\nexit 0\n")
    exe.chmod(0o755)
    (d / "d05_0101.1476").write_bytes(b"db")
    monkeypatch.setenv("SEESTACK_ASTAP_PATH", str(exe))
    monkeypatch.delenv("SEESTACK_ASTAP_DATA", raising=False)
    return exe


def _frame(tmp_path):
    f = tmp_path / "incoming" / "Light_M42_10.0s_0001.fit"
    f.parent.mkdir()
    f.write_bytes(b"the owner's only copy")
    return f


def test_whitespace_and_quotes_around_a_good_path_are_cleaned(bundled):
    assert find_astap(" ") == bundled             # looks blank, means blank
    assert find_astap(f"{bundled} ") == bundled
    assert find_astap(f'"{bundled}"') == bundled
    assert find_astap(f"  '{bundled}'\n") == bundled
    for value in (" ", f"{bundled} ", f'"{bundled}"'):
        assert astap_path_problem(value) is None


def test_the_install_folder_finds_the_program_and_its_database(bundled):
    got = find_astap(str(bundled.parent))
    assert got == bundled
    assert find_star_db_dir(got) == bundled.parent
    assert astap_path_problem(str(bundled.parent)) is None


@pytest.mark.parametrize("value, says", [
    (_HOST_PATH, "doesn't exist"),
    ("{dir}/astap_cli", "doesn't exist"),
    ("{empty}", "is a folder with no ASTAP program"),
])
def test_a_path_that_leads_nowhere_is_named_and_the_built_in_is_offered(
        bundled, tmp_path, value, says):
    empty = tmp_path / "empty_dir"
    empty.mkdir()
    value = value.format(dir=bundled.parent, empty=empty)
    assert find_astap(value) is None              # no silent fallback
    problem = astap_path_problem(value)
    assert problem is not None
    assert value in problem and says in problem
    assert f"built-in ASTAP ({bundled})" in problem

    frame = _frame(tmp_path)
    before = frame.read_bytes()
    res = solve_one(1, str(frame), astap_path=value, timeout_s=5.0)
    assert res.solved is False
    assert classify_solve_setup_error(res.error) == SOLVE_SETUP_ASTAP_MISSING
    assert value in (res.error or "")
    assert "Install ASTAP" not in (res.error or "")
    assert frame.read_bytes() == before
    assert sorted(p.name for p in frame.parent.iterdir()) == [frame.name]


def test_without_a_built_in_the_problem_says_point_it_at_the_program(
        tmp_path, monkeypatch):
    monkeypatch.delenv("SEESTACK_ASTAP_PATH", raising=False)
    monkeypatch.setenv("PATH", str(tmp_path))     # no astap on PATH either
    problem = astap_path_problem(_HOST_PATH)
    assert problem is not None and "point it at the ASTAP program" in problem
    # Unset is not a path problem — the old install message still applies.
    assert astap_path_problem(None) is None and astap_path_problem("") is None


def test_system_reports_each_value_by_what_is_wrong(client, bundled, tmp_path):
    def astap_for(value):
        assert client.put("/api/settings", json={"astap_path": value}).status_code == 200
        return client.get("/api/system").json()["astap"]

    for ok in (" ", f'"{bundled}"', str(bundled.parent)):
        a = astap_for(ok)
        assert a["found"] is True and a["runs"] is True, ok
        assert a["star_db_found"] is True, ok
        assert not a.get("hint"), ok

    a = astap_for(_HOST_PATH)
    assert a["found"] is False
    assert _HOST_PATH in a["hint"] and "clear it" in a["hint"]
