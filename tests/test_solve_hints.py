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
