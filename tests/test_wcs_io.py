"""WCS serialization round-trip and footprint computation."""

import numpy as np
import pytest

pytest.importorskip("astropy")

from astropy.wcs import WCS  # noqa: E402

from seestack.io.wcs_io import (  # noqa: E402
    _extent_from_scale_matrix,
    canvas_extent_from_fits,
    center_from_wcs_text,
    footprint_radec_deg,
    wcs_dict_rescaled_to_preview,
    wcs_from_text,
    wcs_text_from_sidecar,
    wcs_to_text,
)


def _make_simple_wcs(ra_deg: float = 83.6, dec_deg: float = -5.4,
                     pix_scale_arcsec: float = 2.5,
                     width: int = 480, height: int = 320) -> WCS:
    """Build a TAN-projected WCS centered on (ra, dec)."""
    w = WCS(naxis=2)
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    w.wcs.crval = [ra_deg, dec_deg]
    w.wcs.crpix = [width / 2 + 0.5, height / 2 + 0.5]
    w.wcs.cdelt = np.array([-pix_scale_arcsec / 3600.0, pix_scale_arcsec / 3600.0])
    return w


def test_wcs_roundtrip():
    w = _make_simple_wcs()
    text = wcs_to_text(w)
    assert "CTYPE1" in text
    w2 = wcs_from_text(text)
    assert w2 is not None
    np.testing.assert_allclose(w2.wcs.crval, w.wcs.crval, rtol=1e-9)
    np.testing.assert_allclose(w2.wcs.crpix, w.wcs.crpix, rtol=1e-9)


def test_wcs_from_text_handles_empty():
    """Empty / None inputs short-circuit to None without going through astropy."""
    assert wcs_from_text(None) is None
    assert wcs_from_text("") is None
    # Note: astropy's WCS is very permissive about malformed headers (it just
    # fills in defaults) so we don't try to test rejection of garbage strings —
    # the contract is "no exception, returns *something or None*".


def test_center_from_wcs_text_recovers_crval():
    """The field centre is recoverable from the stored WCS blob alone."""
    w = _make_simple_wcs(ra_deg=210.802, dec_deg=54.349)
    ra, dec = center_from_wcs_text(wcs_to_text(w))
    assert ra == pytest.approx(210.802, abs=1e-6)
    assert dec == pytest.approx(54.349, abs=1e-6)


def test_center_from_wcs_text_wraps_ra():
    """A near-0h RA CRVAL comes back inside [0, 360)."""
    w = _make_simple_wcs(ra_deg=0.5, dec_deg=-10.0)
    ra, dec = center_from_wcs_text(wcs_to_text(w))
    assert 0.0 <= ra < 360.0
    assert ra == pytest.approx(0.5, abs=1e-6)


def test_center_from_wcs_text_handles_empty():
    assert center_from_wcs_text(None) == (None, None)
    assert center_from_wcs_text("") == (None, None)


def test_footprint_radec_deg_orientation():
    w = _make_simple_wcs(ra_deg=100.0, dec_deg=20.0, pix_scale_arcsec=2.5,
                         width=200, height=100)
    corners = footprint_radec_deg(w, 200, 100)
    assert corners is not None
    assert len(corners) == 4
    # All four corners should be within ~0.1 degree of the center for a small frame.
    for ra, dec in corners:
        assert abs(ra - 100.0) < 0.5
        assert abs(dec - 20.0) < 0.5


def test_footprint_radec_deg_handles_none():
    assert footprint_radec_deg(None, 100, 100) is None


def test_wcs_text_from_sidecar(tmp_path):
    """ASTAP writes a tiny FITS-header file; astropy can read it back."""
    w = _make_simple_wcs()
    # Write a header-only FITS-like file (just the header bytes, padded).
    header = w.to_header(relax=True)
    raw = header.tostring(padding=True).encode("ascii")
    p = tmp_path / "frame.wcs"
    p.write_bytes(raw)
    text = wcs_text_from_sidecar(p)
    assert text is not None
    assert "CRVAL1" in text


def test_wcs_text_from_sidecar_missing(tmp_path):
    assert wcs_text_from_sidecar(tmp_path / "nope.wcs") is None


# ---- wcs_dict_rescaled_to_preview ---------------------------------------

def _write_master_fits(path, *, full_w, full_h, cd, crval=(180.0, 45.0)):
    """Write a (3, H, W) stack-master-like FITS cube with a rotated CD-matrix WCS.

    Mirrors :func:`seestack.stack.output._write_fits` shape (channels-first cube)
    so ``celestial_wcs_from_fits`` reads a 2-D celestial WCS out of it.
    """
    from astropy.io import fits

    hdr = fits.Header()
    hdr["CTYPE1"] = "RA---TAN"
    hdr["CTYPE2"] = "DEC--TAN"
    hdr["CRPIX1"] = full_w / 2 + 0.5
    hdr["CRPIX2"] = full_h / 2 + 0.5
    hdr["CRVAL1"] = crval[0]
    hdr["CRVAL2"] = crval[1]
    hdr["CD1_1"] = cd[0][0]
    hdr["CD1_2"] = cd[0][1]
    hdr["CD2_1"] = cd[1][0]
    hdr["CD2_2"] = cd[1][1]
    cube = np.zeros((3, full_h, full_w), dtype=np.float32)
    fits.PrimaryHDU(data=cube, header=hdr).writeto(path, overwrite=True)


def test_rescaled_preview_wcs_places_pixels_like_the_full_res_canvas(tmp_path):
    """The rescaled preview WCS maps every preview pixel to the *same* sky position
    the full-res canvas WCS gives — including a real rotation the naive frame-0 TAN
    extrapolation would get wrong. This is the whole point of the fix: consume the
    stored canvas geometry verbatim instead of re-deriving scale + rotation-sign."""
    full_w, full_h = 1920, 1080
    scale = 2.5 / 3600.0
    theta = np.radians(37.0)  # a non-trivial, non-square-symmetric rotation
    c, s = np.cos(theta), np.sin(theta)
    cd = [[-scale * c, scale * s], [scale * s, scale * c]]
    fits_path = tmp_path / "master.fits"
    _write_master_fits(fits_path, full_w=full_w, full_h=full_h, cd=cd)

    pw, ph = 960, 540  # uniform ½ downscale
    d = wcs_dict_rescaled_to_preview(fits_path, pw, ph)
    assert d is not None
    assert d["NAXIS1"] == pw and d["NAXIS2"] == ph
    assert d["CTYPE1"] == "RA---TAN" and d["CTYPE2"] == "DEC--TAN"

    # Reconstruct WCS objects for both grids and compare sky positions. A preview
    # pixel centre i_p (1-based) samples full pixel (i_p-0.5)*s_full+0.5.
    from astropy.io import fits as _fits

    from seestack.io.wcs_io import celestial_wcs_from_fits
    full_wcs, _, _ = celestial_wcs_from_fits(fits_path)
    prev_hdr = _fits.Header()
    for k, v in d.items():
        prev_hdr[k] = v
    prev_wcs = wcs_from_text(str(prev_hdr))

    s_x, s_y = full_w / pw, full_h / ph
    for xp, yp in [(1, 1), (480, 270), (960, 540), (1, 540)]:
        xf = (xp - 0.5) * s_x + 0.5
        yf = (yp - 0.5) * s_y + 0.5
        sky_full = full_wcs.pixel_to_world(xf - 1, yf - 1)  # 0-based
        sky_prev = prev_wcs.pixel_to_world(xp - 1, yp - 1)
        assert abs(sky_full.ra.deg - sky_prev.ra.deg) * 3600 < 1e-3
        assert abs(sky_full.dec.deg - sky_prev.dec.deg) * 3600 < 1e-3

    # Determinant (pixel area on sky) scales by (s_x·s_y); orientation preserved.
    det_full = cd[0][0] * cd[1][1] - cd[0][1] * cd[1][0]
    det_prev = d["CD1_1"] * d["CD2_2"] - d["CD1_2"] * d["CD2_1"]
    assert det_prev == pytest.approx(det_full * s_x * s_y, rel=1e-9)


def test_rescaled_preview_wcs_returns_none_without_a_master(tmp_path):
    """Missing FITS / bad dims fall back to None so the caller uses `_tan_wcs`."""
    assert wcs_dict_rescaled_to_preview(tmp_path / "nope.fits", 100, 100) is None
    fits_path = tmp_path / "m.fits"
    _write_master_fits(fits_path, full_w=64, full_h=64,
                       cd=[[-1e-3, 0.0], [0.0, 1e-3]])
    assert wcs_dict_rescaled_to_preview(fits_path, 0, 100) is None
    assert wcs_dict_rescaled_to_preview(fits_path, 100, -1) is None


@pytest.mark.parametrize("crota2", [0.0, 12.0, 37.0, -25.0, 90.0])
def test_extent_from_scale_matrix_recovers_crota2(crota2):
    """Size + rotation are read back exactly from a standard CROTA2-built WCS.

    A single-frame canvas's stored WCS *is* the reference frame's solved WCS, so
    the recovered rotation must equal the frame's ``CROTA2`` (== its stored
    ``rotation_deg``) for the built-in 3D viewer to be unchanged there. Pins the
    ``atan2(-CD2_1, CD2_2)`` convention against astropy's own CROTA2→CD."""
    scale = 2.5 / 3600.0
    w = WCS(naxis=2)
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    w.wcs.crval = [83.6, -5.4]
    w.wcs.crpix = [960.5, 540.5]
    w.wcs.cdelt = np.array([-scale, scale])  # RA-flipped (CDELT1 < 0)
    w.wcs.crota = [0.0, crota2]
    width_deg, height_deg, rotation_deg = _extent_from_scale_matrix(
        w.pixel_scale_matrix, 1920, 1080)
    assert width_deg == pytest.approx(1920 * scale, rel=1e-9)
    assert height_deg == pytest.approx(1080 * scale, rel=1e-9)
    assert rotation_deg == pytest.approx(crota2, abs=1e-6)


def test_canvas_extent_from_fits_reads_the_stored_geometry(tmp_path):
    """The FITS wrapper returns the canvas size + rotation from a stored WCS, and
    falls back to None (caller uses the frame-0 extrapolation) when absent."""
    import math

    scale = 3.0 / 3600.0
    theta = math.radians(30.0)
    c, s = math.cos(theta), math.sin(theta)
    # Standard FITS CROTA2→CD for CDELT1 = -scale, CDELT2 = +scale, θ = 30°.
    cd = [[-scale * c, -scale * s], [-scale * s, scale * c]]
    fits_path = tmp_path / "m.fits"
    _write_master_fits(fits_path, full_w=1000, full_h=800, cd=cd)

    extent = canvas_extent_from_fits(fits_path)
    assert extent is not None
    width_deg, height_deg, rotation_deg = extent
    assert width_deg == pytest.approx(1000 * scale, rel=1e-6)
    assert height_deg == pytest.approx(800 * scale, rel=1e-6)
    assert rotation_deg == pytest.approx(30.0, abs=1e-4)

    # Missing / headerless master → None (frame-0 fallback).
    assert canvas_extent_from_fits(tmp_path / "nope.fits") is None
