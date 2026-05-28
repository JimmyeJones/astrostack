"""Solve runner — works without a real ASTAP install via mock."""

from unittest.mock import patch

import pytest

pytest.importorskip("astropy")

from seestack.io.project import FrameRow, Project  # noqa: E402
from seestack.solve.astap import ASTAPResult, ASTAPSolver  # noqa: E402
from seestack.solve.runner import (  # noqa: E402
    SolveResult,
    apply_solve_result_to_db,
    build_solve_arglist,
    solve_one,
)


def test_build_solve_arglist_skips_solved(tmp_path):
    proj = Project.create(tmp_path / "p", name="t")
    try:
        # Create a fake file so the path-exists check passes.
        f1 = tmp_path / "a.fit"
        f1.write_bytes(b"")
        f2 = tmp_path / "b.fit"
        f2.write_bytes(b"")
        id1 = proj.add_frame(FrameRow(source_path=str(f1)))
        id2 = proj.add_frame(FrameRow(source_path=str(f2)))
        # Mark id1 as already solved.
        proj.update_frame(id1, wcs_json="dummy")

        args = build_solve_arglist(proj)
        ids = [a[0] for a in args]
        assert id1 not in ids
        assert id2 in ids
    finally:
        proj.close()


def test_solve_one_handles_missing_astap(tmp_path):
    """If ASTAP isn't installed, solve_one returns a clean error result."""
    fits = tmp_path / "x.fit"
    fits.write_bytes(b"")
    # find_astap looks at PATH and standard install locations. With a bogus
    # explicit path we force "not found".
    with patch("seestack.solve.runner.ASTAPSolver", side_effect=__import__(
            "seestack.solve.astap", fromlist=["ASTAPError"]).ASTAPError("astap missing")):
        result = solve_one(1, str(fits), astap_path=str(tmp_path / "nope.exe"))
    assert isinstance(result, SolveResult)
    assert result.solved is False
    assert result.error is not None
    assert "astap" in result.error.lower()


def test_solve_one_with_mock_solver(tmp_path):
    """End-to-end with a mocked ASTAPSolver that returns a successful result."""
    fits = tmp_path / "x.fit"
    fits.write_bytes(b"")
    sidecar = tmp_path / "x.wcs"
    sidecar.write_bytes(b"")  # presence is enough for the wrapper

    fake_result = ASTAPResult(
        fits_path=fits,
        wcs_sidecar_path=sidecar,
        ra_center_deg=83.63,
        dec_center_deg=-5.39,
        pixscale_arcsec=2.5,
        rotation_deg=12.0,
        solved=True,
        log_tail="",
    )

    class FakeSolver:
        def __init__(self, *a, **kw):
            pass

        def solve(self, _path):
            return fake_result

    with patch("seestack.solve.runner.ASTAPSolver", FakeSolver), \
         patch("seestack.io.wcs_io.wcs_text_from_sidecar", return_value="CRVAL1=1.0"):
        result = solve_one(7, str(fits))

    assert result.solved is True
    assert result.frame_id == 7
    assert result.ra_center_deg == 83.63
    assert result.wcs_text == "CRVAL1=1.0"
    assert result.error is None


def test_apply_solve_result_writes_db(tmp_path):
    proj = Project.create(tmp_path / "p", name="t")
    try:
        fid = proj.add_frame(FrameRow(source_path="x.fit"))
        result = SolveResult(
            frame_id=fid, fits_path="x.fit", solved=True,
            wcs_text="CRVAL1=1.0", ra_center_deg=83.63, dec_center_deg=-5.39,
            pixscale_arcsec=2.5, rotation_deg=12.0, error=None,
        )
        apply_solve_result_to_db(proj, result)
        f = proj.get_frame(fid)
        assert f is not None
        assert f.wcs_json == "CRVAL1=1.0"
        assert f.ra_center_deg == 83.63
        assert f.pixscale_arcsec == 2.5
    finally:
        proj.close()


def test_apply_solve_result_failure_doesnt_clobber_accept(tmp_path):
    proj = Project.create(tmp_path / "p", name="t")
    try:
        fid = proj.add_frame(FrameRow(source_path="x.fit"))
        result = SolveResult(
            frame_id=fid, fits_path="x.fit", solved=False,
            wcs_text=None, ra_center_deg=None, dec_center_deg=None,
            pixscale_arcsec=None, rotation_deg=None,
            error="match failed",
        )
        apply_solve_result_to_db(proj, result)
        f = proj.get_frame(fid)
        assert f is not None
        # We don't auto-reject — solve failure is often transient.
        assert f.accept is True
        assert f.reject_reason and "solve_failed" in f.reject_reason
    finally:
        proj.close()
