"""ASTAP wrapper — discovery and ini parsing (no real solve)."""

import pytest

from seestack.solve.astap import ASTAPError, ASTAPSolver, _parse_astap_ini, find_astap


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
