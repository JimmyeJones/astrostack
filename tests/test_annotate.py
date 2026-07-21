"""Tests for :mod:`seestack.annotate` — the "what's in this picture?" projector."""

from __future__ import annotations

import numpy as np
from astropy.wcs import WCS

from seestack.annotate import FieldObject, objects_in_field
from seestack.nightplan import CatalogObject, load_catalog


def _tan_wcs(width: int, height: int, ra: float, dec: float, arcsec_per_px: float = 1.0) -> WCS:
    """A trivial TAN WCS centred on the frame at (``ra``, ``dec``)."""
    w = WCS(naxis=2)
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    w.wcs.crpix = [width / 2 + 0.5, height / 2 + 0.5]  # 1-based FITS centre
    w.wcs.crval = [ra, dec]
    w.wcs.cdelt = [-arcsec_per_px / 3600.0, arcsec_per_px / 3600.0]
    return w


def _obj(cid: str, ra: float, dec: float, *, name: str = "", type: str = "galaxy") -> CatalogObject:
    return CatalogObject(id=cid, name=name, ra_deg=ra, dec_deg=dec, type=type, con="")


def _sky_at(wcs: WCS, x: float, y: float) -> tuple[float, float]:
    """World (ra, dec) degrees at 0-based pixel (x, y)."""
    sky = wcs.pixel_to_world(x, y)
    return float(sky.ra.deg), float(sky.dec.deg)


def test_object_at_field_centre_lands_at_the_centre_pixel():
    W, H = 200, 100
    wcs = _tan_wcs(W, H, 10.0, 20.0)
    cx, cy = W / 2 - 0.5, H / 2 - 0.5  # 0-based frame centre → crpix - 1
    ra, dec = _sky_at(wcs, cx, cy)
    cat = [_obj("M99", ra, dec, name="Centre")]

    found = objects_in_field(wcs, W, H, catalog=cat)

    assert len(found) == 1
    assert isinstance(found[0], FieldObject)
    assert found[0].catalog_id == "M99"
    assert found[0].name == "Centre"
    np.testing.assert_allclose(found[0].x_px, cx, atol=1e-3)
    np.testing.assert_allclose(found[0].y_px, cy, atol=1e-3)


def test_object_just_outside_the_frame_is_excluded_but_a_margin_keeps_it():
    W, H = 200, 100
    wcs = _tan_wcs(W, H, 10.0, 20.0)
    # A world position that maps ~6 px past the right edge.
    ra, dec = _sky_at(wcs, W - 1 + 6.0, H / 2 - 0.5)
    cat = [_obj("NGC 1", ra, dec)]

    assert objects_in_field(wcs, W, H) == []  # bundled catalog: this synthetic id isn't there
    assert objects_in_field(wcs, W, H, catalog=cat) == []  # just outside → dropped
    kept = objects_in_field(wcs, W, H, catalog=cat, margin=10.0)
    assert [o.catalog_id for o in kept] == ["NGC 1"]


def test_object_behind_the_projection_is_dropped():
    W, H = 100, 100
    wcs = _tan_wcs(W, H, 10.0, 20.0)
    # Diametrically opposite point on the sky → behind the TAN projection.
    cat = [
        _obj("HERE", *_sky_at(wcs, 50, 50)),
        _obj("BEHIND", 190.0, -20.0),
    ]
    found = objects_in_field(wcs, W, H, catalog=cat)
    assert [o.catalog_id for o in found] == ["HERE"]


def test_ra_seam_is_handled_by_the_projection_not_naive_ra_math():
    # Field centred right on RA≈0; an interior pixel on the low-RA side wraps to
    # ~359.9°. Naive |ra_obj - ra_centre| math would call it ~360° away and drop
    # it; the projection correctly sees it a fraction of a degree inside the frame.
    W, H = 100, 100
    wcs = _tan_wcs(W, H, 0.05, 5.0, arcsec_per_px=10.0)
    ra, dec = _sky_at(wcs, 80.0, 50.0)  # right of centre → RA wraps below 360
    assert ra > 180.0  # genuinely across the 0/360 seam
    cat = [_obj("SEAM", ra, dec, name="Across the seam")]
    found = objects_in_field(wcs, W, H, catalog=cat)
    assert [o.catalog_id for o in found] == ["SEAM"]
    np.testing.assert_allclose(found[0].x_px, 80.0, atol=1e-3)


def test_none_wcs_and_empty_frame_return_empty():
    wcs = _tan_wcs(100, 100, 10.0, 20.0)
    assert objects_in_field(None, 100, 100) == []
    assert objects_in_field(wcs, 0, 100) == []
    assert objects_in_field(wcs, 100, 0) == []


def test_runs_against_the_real_bundled_catalog_around_m31():
    # M31 is at ~10.68, +41.27; a wide field there should pick up M31 (and its
    # companions M32/M110 sit within ~1°, so a wide-enough field catches them).
    W, H = 4000, 3000
    wcs = _tan_wcs(W, H, 10.68, 41.27, arcsec_per_px=3.0)  # ~3.3° × 2.5° field
    found = objects_in_field(wcs, W, H)
    ids = {o.catalog_id for o in found}
    assert "M31" in ids
    # Every returned object really does have its centre inside the frame.
    for o in found:
        assert -0.5 <= o.x_px <= W - 0.5
        assert -0.5 <= o.y_px <= H - 0.5
    # Sanity: the bundled catalog is non-trivial and the projector ran.
    assert len(load_catalog()) > 100
