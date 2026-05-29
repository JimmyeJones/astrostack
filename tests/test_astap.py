"""ASTAP wrapper — discovery and ini parsing (no real solve)."""

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


def test_find_star_db_dir_none_when_absent(tmp_path):
    (tmp_path / "astap").write_bytes(b"")
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
