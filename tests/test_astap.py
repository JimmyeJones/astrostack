"""ASTAP wrapper — discovery and ini parsing (no real solve)."""

import subprocess

import pytest

from seestack.solve.astap import (
    ASTAPError,
    ASTAPSolver,
    _parse_astap_ini,
    find_astap,
    find_star_db_dir,
)


def test_find_astap_with_explicit_missing(tmp_path):
    bogus = tmp_path / "does_not_exist.exe"
    assert find_astap(bogus) is None


def test_find_astap_with_explicit_existing(tmp_path):
    fake = tmp_path / "astap.exe"
    fake.write_bytes(b"")
    assert find_astap(fake) == fake


def test_solver_raises_when_missing(tmp_path, monkeypatch):
    # No astap on PATH and not at the explicit path.
    monkeypatch.setenv("PATH", str(tmp_path))
    with pytest.raises(ASTAPError):
        ASTAPSolver(astap_path=tmp_path / "nope.exe")


def test_parse_ini(tmp_path):
    ini = tmp_path / "frame.ini"
    ini.write_text(
        "PLTSOLVD=T\n"
        "CRVAL1=83.6331\n"
        "CRVAL2=-5.3911\n"
        "CDELT1=-0.0007\n"
        "CDELT2=0.0007\n"
        "CROTA2=12.5\n"
    )
    ra, dec, pix, rot = _parse_astap_ini(ini)
    assert ra == pytest.approx(83.6331)
    assert dec == pytest.approx(-5.3911)
    # 0.0007 deg/px = 2.52 arcsec/px
    assert pix == pytest.approx(0.0007 * 3600.0)
    assert rot == pytest.approx(12.5)


def test_parse_ini_missing_file(tmp_path):
    with pytest.raises(ASTAPError):
        _parse_astap_ini(tmp_path / "missing.ini")


def test_find_star_db_dir_beside_binary(tmp_path):
    # .290 files sitting next to the astap binary are found automatically.
    (tmp_path / "astap").write_bytes(b"")
    (tmp_path / "d05_0101.290").write_bytes(b"x")
    assert find_star_db_dir(tmp_path / "astap") == tmp_path


def test_find_star_db_dir_1476_format(tmp_path):
    # The D-series databases (d05/d50) use .1476 files, not .290.
    (tmp_path / "astap").write_bytes(b"")
    (tmp_path / "d05_0101.1476").write_bytes(b"x")
    assert find_star_db_dir(tmp_path / "astap") == tmp_path


def test_find_star_db_dir_none_when_absent(tmp_path):
    (tmp_path / "astap").write_bytes(b"")
    # A stray non-database file must not count as a star database.
    (tmp_path / "readme.txt").write_bytes(b"x")
    assert find_star_db_dir(tmp_path / "astap") is None


def test_find_star_db_dir_env_override(tmp_path, monkeypatch):
    bindir = tmp_path / "bin"
    dbdir = tmp_path / "data"
    bindir.mkdir()
    dbdir.mkdir()
    (bindir / "astap").write_bytes(b"")
    (dbdir / "h17_0101.290").write_bytes(b"x")
    monkeypatch.setenv("SEESTACK_ASTAP_DATA", str(dbdir))
    assert find_star_db_dir(bindir / "astap") == dbdir


def test_solver_passes_db_dir(tmp_path, monkeypatch):
    # The -d flag is added to the ASTAP command when a star DB is present.
    (tmp_path / "astap").write_bytes(b"")
    (tmp_path / "d05_0101.290").write_bytes(b"x")
    frame = tmp_path / "frame.fits"
    frame.write_bytes(b"")

    solver = ASTAPSolver(astap_path=tmp_path / "astap")
    assert solver.db_dir == tmp_path

    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd

        class _P:
            returncode = 1
            stdout = ""
            stderr = "no solution"
        return _P()

    monkeypatch.setattr("seestack.solve.astap.subprocess.run", fake_run)
    solver.solve(frame)
    assert "-d" in captured["cmd"]
    assert str(tmp_path) in captured["cmd"]


def _make_solver(tmp_path):
    (tmp_path / "astap").write_bytes(b"")
    (tmp_path / "d05_0101.290").write_bytes(b"x")
    return ASTAPSolver(astap_path=tmp_path / "astap")


def test_adaptive_ladder_escalates_downsample(tmp_path, monkeypatch):
    # ASTAP "fails" until the frame is downsampled (binned) to suppress noise,
    # then solves. solve() should walk the ladder and return the solved result.
    frame = tmp_path / "frame.fits"
    frame.write_bytes(b"")
    solver = _make_solver(tmp_path)
    wcs = frame.with_suffix(".wcs")
    ini = frame.with_suffix(".ini")

    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)

        class _P:
            stdout = ""
            stderr = ""
            returncode = 1
        # Only "solve" (write sidecars, rc 0) once ASTAP is told to downsample.
        if "-z" in cmd:
            wcs.write_text("CRVAL1=10\n")
            ini.write_text("CRVAL1=10\nCRVAL2=20\nCDELT2=0.0007\nCROTA2=0\n")
            _P.returncode = 0
        else:
            wcs.unlink(missing_ok=True)
            _P.returncode = 1
            _P.stderr = "no solution found"
        return _P()

    monkeypatch.setattr("seestack.solve.astap.subprocess.run", fake_run)
    result = solver.solve(frame)
    assert result.solved
    # First attempt had no -z (default); a later one added it.
    assert "-z" not in calls[0]
    assert any("-z" in c for c in calls)


def test_adaptive_ladder_stops_on_fatal_error(tmp_path, monkeypatch):
    # A "no star database" failure is unrecoverable — don't burn the whole ladder.
    frame = tmp_path / "frame.fits"
    frame.write_bytes(b"")
    solver = _make_solver(tmp_path)
    n = {"calls": 0}

    def fake_run(cmd, **kwargs):
        n["calls"] += 1

        class _P:
            returncode = 1
            stdout = ""
            stderr = "Error: no star database found"
        return _P()

    monkeypatch.setattr("seestack.solve.astap.subprocess.run", fake_run)
    result = solver.solve(frame)
    assert not result.solved
    assert n["calls"] == 1  # stopped after the first (fatal) attempt


def test_adaptive_ladder_survives_a_timeout_on_the_first_rung(tmp_path, monkeypatch):
    # A timeout on the slow full-res first rung must NOT abort the ladder: the
    # faster downsampled rungs run on fewer pixels and can still solve the frame.
    frame = tmp_path / "frame.fits"
    frame.write_bytes(b"")
    solver = _make_solver(tmp_path)
    wcs = frame.with_suffix(".wcs")
    ini = frame.with_suffix(".ini")

    def fake_run(cmd, **kwargs):
        # First rung (no -z) runs long and times out; a downsampled rung solves.
        if "-z" not in cmd:
            raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout", 60))
        wcs.write_text("CRVAL1=10\n")
        ini.write_text("CRVAL1=10\nCRVAL2=20\nCDELT2=0.0007\nCROTA2=0\n")

        class _P:
            stdout = ""
            stderr = ""
            returncode = 0
        return _P()

    monkeypatch.setattr("seestack.solve.astap.subprocess.run", fake_run)
    result = solver.solve(frame)
    assert result.solved  # rescued by a later rung instead of giving up on the timeout


def test_adaptive_ladder_raises_only_after_every_rung_times_out(tmp_path, monkeypatch):
    # If *every* rung times out the failure is surfaced — but only after the whole
    # ladder has been tried, not on the first timeout.
    frame = tmp_path / "frame.fits"
    frame.write_bytes(b"")
    solver = _make_solver(tmp_path)
    n = {"calls": 0}

    def fake_run(cmd, **kwargs):
        n["calls"] += 1
        raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout", 60))

    monkeypatch.setattr("seestack.solve.astap.subprocess.run", fake_run)
    with pytest.raises(ASTAPError):
        solver.solve(frame)
    assert n["calls"] == len(ASTAPSolver._SOLVE_LADDER)  # tried every rung first


def test_solve_once_emits_z_and_s_flags(tmp_path, monkeypatch):
    frame = tmp_path / "frame.fits"
    frame.write_bytes(b"")
    solver = _make_solver(tmp_path)
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd

        class _P:
            returncode = 1
            stdout = ""
            stderr = "no solution"
        return _P()

    monkeypatch.setattr("seestack.solve.astap.subprocess.run", fake_run)
    solver._solve_once(frame, downsample=4, max_stars=200)
    cmd = captured["cmd"]
    assert "-z" in cmd and "4" in cmd
    assert "-s" in cmd and "200" in cmd


def _capture_cmd(monkeypatch):
    captured: dict = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd

        class _P:
            returncode = 1
            stdout = ""
            stderr = "no solution"
        return _P()

    monkeypatch.setattr("seestack.solve.astap.subprocess.run", fake_run)
    return captured


def test_solver_adds_position_hint(tmp_path, monkeypatch):
    solver = _make_solver(tmp_path)
    frame = tmp_path / "frame.fits"
    frame.write_bytes(b"")
    captured = _capture_cmd(monkeypatch)
    solver.solve(frame, ra_hint_deg=83.6, dec_hint_deg=-5.4, radius_deg=10.0)
    cmd = captured["cmd"]
    assert "-ra" in cmd and "-spd" in cmd
    assert abs(float(cmd[cmd.index("-ra") + 1]) - 83.6 / 15.0) < 1e-3   # degrees → hours
    assert abs(float(cmd[cmd.index("-spd") + 1]) - (-5.4 + 90.0)) < 1e-3  # dec → south-polar-dist
    assert float(cmd[cmd.index("-r") + 1]) == 10.0


def test_solver_omits_hint_when_absent(tmp_path, monkeypatch):
    solver = _make_solver(tmp_path)
    frame = tmp_path / "frame.fits"
    frame.write_bytes(b"")
    captured = _capture_cmd(monkeypatch)
    solver.solve(frame)
    assert "-ra" not in captured["cmd"] and "-spd" not in captured["cmd"]
