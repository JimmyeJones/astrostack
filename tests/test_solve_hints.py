"""Plate-solve hints: parse target RA/Dec from FITS headers and feed ASTAP."""

from __future__ import annotations

import pytest

pytest.importorskip("astropy")

from seestack.io.fits_loader import _coord_to_deg, _target_dec_deg, _target_ra_deg


def test_coord_parsing_decimal_and_sexagesimal():
    # Decimal values are degrees.
    assert _coord_to_deg(83.6, is_ra=True) == pytest.approx(83.6)
    assert _coord_to_deg(-5.4, is_ra=False) == pytest.approx(-5.4)
    assert _coord_to_deg("83.6", is_ra=True) == pytest.approx(83.6)
    # Sexagesimal RA is hours → ×15; Dec is degrees.
    assert _coord_to_deg("05 35 17.0", is_ra=True) == pytest.approx(5.58806 * 15, abs=1e-2)
    assert _coord_to_deg("-05 23 00", is_ra=False) == pytest.approx(-5.3833, abs=1e-3)
    # Out-of-range rejected.
    assert _coord_to_deg(999.0, is_ra=True) is None
    assert _coord_to_deg(120.0, is_ra=False) is None


def test_target_keyword_lookup():
    from astropy.io.fits import Header

    assert _target_ra_deg(Header({"RA": 83.6})) == pytest.approx(83.6)
    assert _target_dec_deg(Header({"DEC": -5.4})) == pytest.approx(-5.4)
    # OBJCTRA sexagesimal hours.
    assert _target_ra_deg(Header({"OBJCTRA": "05 35 17"})) == pytest.approx(83.82, abs=0.1)
    assert _target_ra_deg(Header({"FOO": 1})) is None


def _write_fits_with_coords(path, ra=None, dec=None):
    import numpy as np
    from astropy.io import fits

    h = fits.Header()
    h["BAYERPAT"] = "RGGB"
    if ra is not None:
        h["RA"] = ra
    if dec is not None:
        h["DEC"] = dec
    fits.writeto(path, np.zeros((20, 20), dtype="uint16"), h, overwrite=True)
    return path


def test_ingest_stores_target_hint(tmp_path):
    from seestack.core.cache import CacheManager
    from seestack.io.ingest import ingest_files
    from seestack.io.project import Project

    src = tmp_path / "raws"
    src.mkdir()
    _write_fits_with_coords(src / "a.fit", ra=83.6, dec=-5.4)
    _write_fits_with_coords(src / "b.fit")  # no coords

    proj = Project.create(tmp_path / "p", name="t")
    cache = CacheManager(proj.project_dir)
    try:
        list(ingest_files(proj, cache, [src / "a.fit", src / "b.fit"]))
        frames = {f.source_path.split("/")[-1]: f for f in proj.iter_frames()}
        assert frames["a.fit"].ra_hint_deg == pytest.approx(83.6)
        assert frames["a.fit"].dec_hint_deg == pytest.approx(-5.4)
        assert frames["b.fit"].ra_hint_deg is None
    finally:
        proj.close()


def test_build_solve_arglist_threads_hint(tmp_path):
    from seestack.io.project import FrameRow, Project
    from seestack.solve.runner import build_solve_arglist

    proj = Project.create(tmp_path / "p", name="t")
    fits_path = tmp_path / "f.fit"
    fits_path.write_bytes(b"x")
    try:
        proj.add_frame(FrameRow(source_path=str(fits_path), cached_path=str(fits_path),
                                ra_hint_deg=83.6, dec_hint_deg=-5.4))
        args = build_solve_arglist(proj, use_hint=True)
        assert len(args) == 1
        # tuple: (fid, path, astap_path, fov, timeout, ra_hint, dec_hint, radius)
        assert args[0][5] == pytest.approx(83.6) and args[0][6] == pytest.approx(-5.4)
        # use_hint=False suppresses the hint.
        args_off = build_solve_arglist(proj, use_hint=False)
        assert args_off[0][5] is None and args_off[0][6] is None
    finally:
        proj.close()


def test_fallback_solve_hint_medians_solved_centres():
    from types import SimpleNamespace

    from seestack.solve.runner import fallback_solve_hint

    # No solved frames → no hint.
    assert fallback_solve_hint([]) is None
    assert fallback_solve_hint([SimpleNamespace(ra_center_deg=None, dec_center_deg=None)]) is None

    # One solved frame → its own centre.
    one = [SimpleNamespace(ra_center_deg=83.6, dec_center_deg=-5.4)]
    ra, dec = fallback_solve_hint(one)
    assert ra == pytest.approx(83.6) and dec == pytest.approx(-5.4)

    # Several → robust median of the centres.
    many = [SimpleNamespace(ra_center_deg=r, dec_center_deg=d)
            for r, d in [(83.0, -5.0), (83.6, -5.4), (84.2, -5.8)]]
    ra, dec = fallback_solve_hint(many)
    assert ra == pytest.approx(83.6) and dec == pytest.approx(-5.4)


def test_fallback_solve_hint_wraps_ra_at_zero():
    from types import SimpleNamespace

    from seestack.solve.runner import fallback_solve_hint

    # Frames straddling RA=0h (359.9° and 0.1°) must median near 0°, not ~180°.
    frames = [SimpleNamespace(ra_center_deg=r, dec_center_deg=45.0)
              for r in (359.8, 359.9, 0.1, 0.2)]
    ra, dec = fallback_solve_hint(frames)
    assert (ra < 1.0 or ra > 359.0)
    assert dec == pytest.approx(45.0)


def test_build_solve_arglist_offers_sibling_centre_when_header_hint_absent(tmp_path):
    from seestack.io.project import FrameRow, Project
    from seestack.solve.runner import SIBLING_HINT_RADIUS_DEG, build_solve_arglist

    proj = Project.create(tmp_path / "p", name="t")
    a = tmp_path / "a.fit"; a.write_bytes(b"x")
    b = tmp_path / "b.fit"; b.write_bytes(b"x")
    c = tmp_path / "c.fit"; c.write_bytes(b"x")
    try:
        # A solved sibling fixes the pointing at (200, 12).
        proj.add_frame(FrameRow(source_path=str(a), cached_path=str(a),
                                wcs_json="{\"solved\": true}",
                                ra_center_deg=200.0, dec_center_deg=12.0))
        # An unsolved frame with NO header hint → should borrow the sibling centre.
        proj.add_frame(FrameRow(source_path=str(b), cached_path=str(b)))
        # An unsolved frame WITH its own header hint → left untouched.
        proj.add_frame(FrameRow(source_path=str(c), cached_path=str(c),
                                ra_hint_deg=50.0, dec_hint_deg=-1.0))

        args = {tp[1].split("/")[-1]: tp for tp in build_solve_arglist(proj, use_hint=True)}
        # tuple: (fid, path, astap_path, fov, timeout, ra_hint, dec_hint, radius)
        assert args["b.fit"][5] == pytest.approx(200.0)
        assert args["b.fit"][6] == pytest.approx(12.0)
        assert args["b.fit"][7] == pytest.approx(SIBLING_HINT_RADIUS_DEG)
        # The header-hinted frame keeps its own hint and the blind radius (30°).
        assert args["c.fit"][5] == pytest.approx(50.0)
        assert args["c.fit"][6] == pytest.approx(-1.0)
        assert args["c.fit"][7] == pytest.approx(30.0)
        # The already-solved sibling is not re-offered.
        assert "a.fit" not in args

        # use_hint=False → no sibling borrowing (fully blind solve).
        off = {tp[1].split("/")[-1]: tp for tp in build_solve_arglist(proj, use_hint=False)}
        assert off["b.fit"][5] is None and off["b.fit"][6] is None
        assert off["b.fit"][7] == pytest.approx(30.0)
    finally:
        proj.close()


def test_build_solve_arglist_no_sibling_leaves_hintless_frame_blind(tmp_path):
    from seestack.io.project import FrameRow, Project
    from seestack.solve.runner import build_solve_arglist

    proj = Project.create(tmp_path / "p", name="t")
    b = tmp_path / "b.fit"; b.write_bytes(b"x")
    try:
        # No solved frame on the target → nothing to borrow; frame stays blind.
        proj.add_frame(FrameRow(source_path=str(b), cached_path=str(b)))
        (tp,) = build_solve_arglist(proj, use_hint=True)
        assert tp[5] is None and tp[6] is None
        assert tp[7] == pytest.approx(30.0)
    finally:
        proj.close()


def test_solve_one_passes_hint_to_solver(tmp_path, monkeypatch):
    from seestack.solve import runner

    seen: dict = {}

    class FakeSolver:
        def __init__(self, *a, **kw):
            pass

        def solve(self, _path, *, ra_hint_deg=None, dec_hint_deg=None, radius_deg=None):
            seen.update(ra=ra_hint_deg, dec=dec_hint_deg, radius=radius_deg)

            class _R:
                solved = False
                wcs_sidecar_path = None
                ra_center_deg = dec_center_deg = pixscale_arcsec = rotation_deg = None
                log_tail = ""
            return _R()

    monkeypatch.setattr(runner, "ASTAPSolver", FakeSolver)
    runner.solve_one(1, str(tmp_path / "x.fit"),
                     ra_hint_deg=83.6, dec_hint_deg=-5.4, search_radius_deg=12.0)
    assert seen == {"ra": 83.6, "dec": -5.4, "radius": 12.0}
