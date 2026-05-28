"""WCS serialization round-trip and footprint computation."""

import numpy as np
import pytest

pytest.importorskip("astropy")

from astropy.wcs import WCS  # noqa: E402

from seestack.io.wcs_io import (  # noqa: E402
    footprint_radec_deg,
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
