"""WCS serialization round-trip and footprint computation."""

import numpy as np
import pytest

pytest.importorskip("astropy")

from astropy.wcs import WCS  # noqa: E402

from seestack.io.wcs_io import (  # noqa: E402
    _extent_from_scale_matrix,
    canvas_extent_from_fits,
    footprint_radec_deg,
    wcs_center_deg_from_text,
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


def test_wcs_center_deg_from_text_reads_the_reference_point():
    """The CRVAL centre is recovered from a WCS text blob — the same coordinates
    ASTAP's ``.ini`` reports — so a solved frame whose ``.ini`` didn't parse can
    still have its centre backfilled from the ``.wcs`` sidecar."""
    w = _make_simple_wcs(ra_deg=200.7, dec_deg=-33.2)
    centre = wcs_center_deg_from_text(wcs_to_text(w))
    assert centre is not None
    ra, dec = centre
    assert ra == pytest.approx(200.7, abs=1e-6)
    assert dec == pytest.approx(-33.2, abs=1e-6)


def test_wcs_center_deg_from_text_handles_no_wcs():
    """Empty/garbage input yields None rather than raising or inventing a centre."""
    assert wcs_center_deg_from_text(None) is None
    assert wcs_center_deg_from_text("") is None


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


def test_wcs_text_is_usable_separates_a_real_solution_from_a_readable_blob():
    """``wcs_text_is_usable`` is the "is this actually a solution?" test that
    truthiness and ``wcs_from_text() is not None`` both fail to be.

    An empty or truncated ASTAP ``.wcs`` sidecar reads back as a bare ``"END"``
    header: a truthy string that parses to a non-None, celestial-less WCS. Every
    caller that trusts a stored solution (persisting it, propagating it, counting
    it as located) needs to tell that apart from a real solve.
    """
    from seestack.io.wcs_io import wcs_text_is_usable

    w = WCS(naxis=2)
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    w.wcs.crval = [83.6, -5.4]
    w.wcs.crpix = [240.5, 160.5]
    w.wcs.cdelt = [-5.0 / 3600.0, 5.0 / 3600.0]
    assert wcs_text_is_usable(wcs_to_text(w)) is True

    for blob in (None, "", "END", "SIMPLE  =                    T\nEND",
                 "BITPIX  =                  -32\nNAXIS   =                    2\nEND"):
        # Truthy for most of these, and wcs_from_text returns an object for the
        # readable ones — but none of them locates the frame on the sky.
        assert wcs_text_is_usable(blob) is False


# ---- North-up-saved previews (Sky-map placement) -------------------------

def _north_up_master(tmp_path, *, rot_deg, full_w=200, full_h=140):
    """A stack master whose canvas is tilted by ``rot_deg`` — the shape History's
    "Adjust" North-up save exists for."""
    import math

    scale = 2.0 / 3600.0
    th = math.radians(rot_deg)
    c, s = math.cos(th), math.sin(th)
    cd = [[-scale * c, scale * s], [scale * s, scale * c]]
    path = tmp_path / f"master_{rot_deg}.fits"
    _write_master_fits(path, full_w=full_w, full_h=full_h, cd=cd)
    return path


@pytest.mark.parametrize("rot_deg", [12.0, 33.0, 88.0, -60.0])
def test_north_up_preview_wcs_places_the_rotated_pixels(tmp_path, rot_deg):
    """A preview saved North-up is no longer a plain downscale of the canvas, so
    its WCS must describe the *rotated* grid — otherwise the Sky map places the
    picture at the wrong orientation (and, on a 90° save, the wrong aspect).

    Ground truth is the rotation itself: rotate a marker pixel exactly the way
    the preview render does, then ask the derived WCS where that marker's sky
    position lands. It must be the marker's new pixel.
    """
    from astropy.io import fits as _fits

    from seestack.io.wcs_io import celestial_wcs_from_fits
    from seestack.render.orient import rotate_image_north_up
    from seestack.render.thumbnail import applied_north_up_deg

    fits_path = _north_up_master(tmp_path, rot_deg=rot_deg)
    full_wcs, full_w, full_h = celestial_wcs_from_fits(fits_path)
    applied = applied_north_up_deg(fits_path)
    assert applied != 0.0                      # a real tilt to correct

    blank = np.zeros((full_h, full_w, 3), np.float32)
    rotated = rotate_image_north_up(blank, applied)
    new_h, new_w = rotated.shape[:2]

    d = wcs_dict_rescaled_to_preview(fits_path, new_w, new_h, north_up_deg=applied)
    assert d is not None
    assert (d["NAXIS1"], d["NAXIS2"]) == (new_w, new_h)
    hdr = _fits.Header()
    for k, v in d.items():
        hdr[k] = v
    rot_wcs = wcs_from_text(str(hdr))

    # The same WCS built the way the map used to build it: from the un-rotated
    # canvas. It is the "before" of this regression.
    plain = wcs_dict_rescaled_to_preview(fits_path, new_w, new_h)
    plain_hdr = _fits.Header()
    for k, v in plain.items():
        plain_hdr[k] = v
    plain_wcs = wcs_from_text(str(plain_hdr))

    worst_plain = 0.0
    for px, py in [(30, 20), (150, 100), (full_w // 2, full_h // 2), (5, 130)]:
        marker = np.zeros((full_h, full_w, 3), np.float32)
        marker[py, px] = 1.0
        out = rotate_image_north_up(marker, applied)
        ys, xs = np.nonzero(out[:, :, 0] > 0.4)
        assert len(xs) >= 1
        ox, oy = float(xs.mean()), float(ys.mean())

        ra, dec = (float(v) for v in full_wcs.all_pix2world(px, py, 0))
        gx, gy = (float(v) for v in rot_wcs.all_world2pix(ra, dec, 0))
        assert abs(gx - ox) < 1.0 and abs(gy - oy) < 1.0

        bx, by = (float(v) for v in plain_wcs.all_world2pix(ra, dec, 0))
        worst_plain = max(worst_plain, float(np.hypot(bx - ox, by - oy)))
    # …and the un-rotated WCS really is visibly wrong (this is the bug).
    assert worst_plain > 5.0


def test_north_up_zero_leaves_the_preview_wcs_exactly_as_before(tmp_path):
    """The default is the existing behaviour, key for key — an ordinary run (and
    every run stacked before this column existed) is untouched."""
    fits_path = _north_up_master(tmp_path, rot_deg=33.0)
    assert (wcs_dict_rescaled_to_preview(fits_path, 100, 70, north_up_deg=0.0)
            == wcs_dict_rescaled_to_preview(fits_path, 100, 70))
    assert (canvas_extent_from_fits(fits_path, north_up_deg=0.0)
            == canvas_extent_from_fits(fits_path))


def test_north_up_extent_is_the_rotated_bounding_box_at_one_orientation(tmp_path):
    """The 3D sky viewer sizes and orients its tile from the extent, so that has
    to follow the rotation too: the box grows to the rotated bounding box, and
    every North-up picture ends up at the *same* position angle whatever its
    canvas started at — which is what "North is up" means."""
    from seestack.render.thumbnail import applied_north_up_deg

    angles = []
    for rot_deg in (12.0, 33.0, -60.0):
        fits_path = _north_up_master(tmp_path, rot_deg=rot_deg)
        applied = applied_north_up_deg(fits_path)
        plain = canvas_extent_from_fits(fits_path)
        rotated = canvas_extent_from_fits(fits_path, north_up_deg=applied)
        assert plain is not None and rotated is not None
        # Rotating with `expand` can only grow the canvas.
        assert rotated[0] >= plain[0] - 1e-9
        assert rotated[1] >= plain[1] - 1e-9
        angles.append(rotated[2])
    for a in angles[1:]:
        assert abs(((a - angles[0]) + 180.0) % 360.0 - 180.0) < 0.5


def test_north_up_preview_wcs_still_returns_none_without_a_master(tmp_path):
    assert wcs_dict_rescaled_to_preview(
        tmp_path / "nope.fits", 100, 100, north_up_deg=90.0) is None
    assert canvas_extent_from_fits(tmp_path / "nope.fits", north_up_deg=90.0) is None


# --- footprint_radec_deg's vectorised path ---------------------------------
#
# The four corners go through one ``all_pix2world`` call instead of four
# ``pixel_to_world`` calls (each of which builds a whole SkyCoord), because
# ``compute_mosaic_canvas`` calls this once per *sub* — 5,477 of them on the
# owner's largest target. These pin that the shortcut is exact, and that it is
# only taken for the equatorial WCSs it is valid for.


def test_the_vectorised_footprint_is_identical_to_the_per_corner_transform():
    """The fast path must agree with ``pixel_to_world`` to the last bit — it is
    the same transform, with the SkyCoord wrapping left off."""
    from seestack.io.wcs_io import _is_plain_radec

    w = _make_simple_wcs(ra_deg=205.5, dec_deg=28.4, pix_scale_arcsec=2.9,
                         width=1080, height=1920)
    assert _is_plain_radec(w)                       # the fast path is in play
    got = footprint_radec_deg(w, 1080, 1920)
    expect = [
        (float(s.ra.deg), float(s.dec.deg))
        for s in (w.pixel_to_world(x, y)
                  for x, y in [(0, 0), (1079, 0), (1079, 1919), (0, 1919)])
    ]
    assert got == expect


def test_a_non_equatorial_wcs_is_not_read_as_ra_dec():
    """``all_pix2world`` hands back longitude/latitude in the same two slots, so
    a galactic WCS must keep the original path — which has always declined it
    (``SkyCoord.ra`` does not exist there) rather than mislabelling the axes."""
    from astropy.wcs import WCS

    from seestack.io.wcs_io import _is_plain_radec

    g = WCS(naxis=2)
    g.wcs.ctype = ["GLON-TAN", "GLAT-TAN"]
    g.wcs.crval = [120.0, 30.0]
    g.wcs.crpix = [50.0, 50.0]
    g.wcs.cdelt = [-1e-3, 1e-3]
    assert not _is_plain_radec(g)
    assert footprint_radec_deg(g, 100, 100) is None


def test_the_footprint_of_a_frame_across_ra_zero_still_wraps_the_short_way():
    """A frame straddling the seam has corners on both sides — the transform
    reports them as it always did, and the callers unwrap."""
    w = _make_simple_wcs(ra_deg=0.0, dec_deg=10.0, pix_scale_arcsec=5.0,
                         width=400, height=400)
    corners = footprint_radec_deg(w, 400, 400)
    assert corners is not None and len(corners) == 4
    assert any(ra > 359.0 for ra, _ in corners)
    assert any(ra < 1.0 for ra, _ in corners)


def test_a_frame_with_no_recorded_size_still_answers_none():
    """``mosaic`` guards this, the desktop footprint view does not — and the
    vectorised path must not turn "no dimensions" into a raised TypeError."""
    w = _make_simple_wcs()
    assert footprint_radec_deg(w, None, None) is None
    assert footprint_radec_deg(w, 100, None) is None


# --- the plain-TAN fast path in `wcs_from_text` -----------------------------


def _header_text(**cards) -> str:
    """FITS header text with the cards in the order given (as ASTAP writes)."""
    from astropy.io.fits import Header

    header = Header()
    for keyword, value in cards.items():
        header[keyword.replace("__", "-")] = value
    return str(header)


def _astropy_wcs_from_text(text: str):
    """What ``wcs_from_text`` used to do, verbatim — the reference to match."""
    import warnings

    from astropy.io.fits import Header
    from astropy.wcs import WCS as AstropyWCS
    from astropy.wcs import FITSFixedWarning

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", FITSFixedWarning)
        return AstropyWCS(Header.fromstring(text))


_OURS_CDELT = wcs_to_text(_make_simple_wcs())


def _rotated_cd_text() -> str:
    w = _make_simple_wcs()
    w.wcs.cd = np.array([[-7.5e-4, 3.1e-5], [3.1e-5, 7.5e-4]])
    return wcs_to_text(w)


def _astap_sidecar_text() -> str:
    """An ASTAP-shaped solution: CD *and* the legacy CDELT/CROTA pair beside it."""
    return _header_text(
        SIMPLE=True, BITPIX=8, NAXIS=0,
        CTYPE1="RA---TAN", CTYPE2="DEC--TAN", CUNIT1="deg", CUNIT2="deg",
        CRPIX1=540.5, CRPIX2=960.5, CRVAL1=83.822, CRVAL2=-5.391,
        CDELT1=-7.5e-4, CDELT2=7.5e-4, CROTA1=0.0, CROTA2=2.36,
        CD1_1=-7.4936e-4, CD1_2=3.09e-5, CD2_1=3.09e-5, CD2_2=7.4936e-4,
    )


_FAST_PATH_CORPUS = {
    "our own CDELT serialisation": _OURS_CDELT,
    "our own CD serialisation": _rotated_cd_text(),
    "an ASTAP sidecar (CD beside CDELT+CROTA)": _astap_sidecar_text(),
    "the legacy CDELT+CROTA2 convention": _header_text(
        CTYPE1="RA---TAN", CTYPE2="DEC--TAN",
        CRPIX1=540.5, CRPIX2=960.5, CRVAL1=83.822, CRVAL2=-5.391,
        CDELT1=-7.5e-4, CDELT2=7.5e-4, CROTA2=30.0),
    "a half-written CD matrix": _header_text(
        CTYPE1="RA---TAN", CTYPE2="DEC--TAN",
        CRPIX1=540.5, CRPIX2=960.5, CRVAL1=83.822, CRVAL2=-5.391,
        CD1_1=-7.5e-4, CD2_2=7.5e-4),
    "a half-written PC matrix": _header_text(
        CTYPE1="RA---TAN", CTYPE2="DEC--TAN",
        CRPIX1=540.5, CRPIX2=960.5, CRVAL1=83.822, CRVAL2=-5.391,
        CDELT1=-7.5e-4, CDELT2=7.5e-4, PC1_1=0.9, PC2_2=0.9),
    "a frame carrying its own dimensions": _header_text(
        SIMPLE=True, BITPIX=8, NAXIS=2, NAXIS1=1080, NAXIS2=1920,
        CTYPE1="RA---TAN", CTYPE2="DEC--TAN",
        CRPIX1=540.5, CRPIX2=960.5, CRVAL1=83.822, CRVAL2=-5.391,
        CD1_1=-7.5e-4, CD1_2=0.0, CD2_1=0.0, CD2_2=7.5e-4),
    "a frame stamped with its capture time and frame": _header_text(
        CTYPE1="RA---TAN", CTYPE2="DEC--TAN",
        CRPIX1=540.5, CRPIX2=960.5, CRVAL1=83.822, CRVAL2=-5.391,
        CD1_1=-7.5e-4, CD1_2=0.0, CD2_1=0.0, CD2_2=7.5e-4,
        RADESYS="ICRS", EQUINOX=2000.0,
        DATE__OBS="2024-11-15T21:03:11", MJD__OBS=60629.877),
    "a frame near the RA=0 seam": wcs_to_text(_make_simple_wcs(ra_deg=0.05)),
    "a frame near the pole": wcs_to_text(_make_simple_wcs(dec_deg=89.4)),
}


@pytest.mark.parametrize("label", sorted(_FAST_PATH_CORPUS))
def test_the_fast_wcs_path_is_indistinguishable_from_astropys_own_read(label):
    """The fast path is only allowed to exist because it is not an
    approximation: for every header shape this app stores, it must produce a WCS
    that re-serialises byte-for-byte like astropy's, records the same pixel
    shape, and transforms a grid of pixels to bit-identical RA/Dec.

    Byte-identical ``to_header`` is the bar rather than "close enough on a pixel
    grid" because ``solve.bootstrap.propagate_wcs`` reads a solution back,
    shifts it and re-serialises it into the project DB — a dropped keyword would
    become stored data, not just a transient object.
    """
    from seestack.io.wcs_io import _wcs_from_plain_tan_text

    text = _FAST_PATH_CORPUS[label]
    fast = _wcs_from_plain_tan_text(text)
    assert fast is not None, "this header shape should take the fast path"
    reference = _astropy_wcs_from_text(text)

    assert str(fast.to_header(relax=True)) == str(reference.to_header(relax=True))
    assert fast.pixel_shape == reference.pixel_shape

    xs, ys = np.meshgrid(np.linspace(0, 1079, 21), np.linspace(0, 1919, 21))
    fast_ra, fast_dec = fast.all_pix2world(xs.ravel(), ys.ravel(), 0)
    ref_ra, ref_dec = reference.all_pix2world(xs.ravel(), ys.ravel(), 0)
    assert np.array_equal(fast_ra, ref_ra)
    assert np.array_equal(fast_dec, ref_dec)

    # And through the public entry point, which is what every caller uses.
    assert str(wcs_from_text(text).to_header(relax=True)) == \
        str(reference.to_header(relax=True))


_FAST_PATH_DECLINES = {
    "SIP distortion": _header_text(
        CTYPE1="RA---TAN-SIP", CTYPE2="DEC--TAN-SIP",
        CRPIX1=1.0, CRPIX2=1.0, CRVAL1=1.0, CRVAL2=1.0,
        CD1_1=-1e-4, CD1_2=0.0, CD2_1=0.0, CD2_2=1e-4,
        A_ORDER=2, A_0_0=0.0, A_0_1=0.0, A_0_2=1e-6,
        A_1_0=0.0, A_1_1=2e-6, A_2_0=3e-6,
        B_ORDER=2, B_0_0=0.0, B_0_1=0.0, B_0_2=4e-6,
        B_1_0=0.0, B_1_1=5e-6, B_2_0=6e-6),
    "PV distortion": _header_text(
        CTYPE1="RA---TAN", CTYPE2="DEC--TAN",
        CRPIX1=1.0, CRPIX2=1.0, CRVAL1=1.0, CRVAL2=1.0,
        CD1_1=-1e-4, CD1_2=0.0, CD2_1=0.0, CD2_2=1e-4, PV1_1=0.5),
    "a galactic projection": _header_text(
        CTYPE1="GLON-TAN", CTYPE2="GLAT-TAN",
        CRPIX1=1.0, CRPIX2=1.0, CRVAL1=1.0, CRVAL2=1.0,
        CDELT1=-1e-4, CDELT2=1e-4),
    "a non-TAN projection": _header_text(
        CTYPE1="RA---SIN", CTYPE2="DEC--SIN",
        CRPIX1=1.0, CRPIX2=1.0, CRVAL1=1.0, CRVAL2=1.0,
        CDELT1=-1e-4, CDELT2=1e-4),
    "a third axis": _header_text(
        WCSAXES=3, CTYPE1="RA---TAN", CTYPE2="DEC--TAN", CTYPE3="WAVE",
        CRPIX1=1.0, CRPIX2=1.0, CRVAL1=1.0, CRVAL2=1.0,
        CDELT1=-1e-4, CDELT2=1e-4),
    "axes in arcsec rather than degrees": _header_text(
        CTYPE1="RA---TAN", CTYPE2="DEC--TAN", CUNIT1="arcsec", CUNIT2="arcsec",
        CRPIX1=1.0, CRPIX2=1.0, CRVAL1=1.0, CRVAL2=1.0,
        CDELT1=-0.36, CDELT2=0.36),
    "no reference point at all": _header_text(
        CTYPE1="RA---TAN", CTYPE2="DEC--TAN", CDELT1=-1e-4, CDELT2=1e-4),
    "a length that is not a whole number of cards": "CTYPE1  = 'RA---TAN'",
    "an empty sidecar": "END" + " " * 77,
}


@pytest.mark.parametrize("label", sorted(_FAST_PATH_DECLINES))
def test_a_header_the_fast_path_does_not_fully_understand_goes_to_astropy(label):
    """The fast path's safety is that it declines rather than guesses: anything
    it cannot reproduce keyword-for-keyword falls through to astropy's own
    permissive read, which is what these headers got before it existed —
    including the ones astropy itself refuses, which must still come back as
    ``None`` rather than as a silently-simplified solution."""
    from seestack.io.wcs_io import _wcs_from_plain_tan_text

    text = _FAST_PATH_DECLINES[label]
    assert _wcs_from_plain_tan_text(text) is None

    try:
        reference = _astropy_wcs_from_text(text)
    except Exception:  # noqa: BLE001 — astropy rejects it; so must we
        assert wcs_from_text(text) is None
        return
    result = wcs_from_text(text)
    assert result is not None
    assert str(result.to_header(relax=True)) == str(reference.to_header(relax=True))


def test_a_duplicated_wcs_keyword_is_left_to_astropy():
    """Our card scan keeps the *last* value it sees and astropy keeps the first,
    so a header that says CRVAL1 twice must not take the fast path — otherwise
    the two reads would place the same frame in two different places."""
    from seestack.io.wcs_io import _wcs_from_plain_tan_text

    text = wcs_to_text(_make_simple_wcs())
    doubled = text[:-2880] + "CRVAL1  = 111.0".ljust(80) + text[-2880:]
    assert _wcs_from_plain_tan_text(doubled) is None


def test_a_blob_with_no_wcs_keys_still_reads_as_an_unsolved_frame():
    """``wcs_text_is_usable`` leans on a bare "END" sidecar coming back as a
    *non-None* WCS with no celestial axes — the fast path must not turn it into
    ``None`` and silently reclassify the frame."""
    from seestack.io.wcs_io import wcs_text_is_usable

    blob = "END" + " " * 2877
    wcs = wcs_from_text(blob)
    assert wcs is not None
    assert not wcs.has_celestial
    assert not wcs_text_is_usable(blob)
