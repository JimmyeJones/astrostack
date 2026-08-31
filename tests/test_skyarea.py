"""How much sky the owner's pictures cover — and why two pictures of one patch
are not two patches.

``stack_sky_area_deg2`` measures one master off its own WCS, exactly. The
library-wide total used to be the *sum* of those, which double-counts every
patch the owner photographed twice — an ordinary shape on a real install (a
mosaic re-framed over an earlier single field, or the two folder spellings of
one object), and one that told them they had seen sky they had not.
``sky_area_union_deg2`` counts a shared patch once, without moving any single
picture's own number.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from astropy.io import fits

from seestack.skyarea import (
    _sky_cell_keys,
    sky_area_union_deg2,
    stack_sky_area_deg2,
)

pytest.importorskip("PIL")

_H, _W = 200, 300
_SCALE_DEG = 0.002                      # 7.2 arcsec/px — a 0.4° × 0.6° canvas
_AREA_DEG2 = _H * _W * _SCALE_DEG * _SCALE_DEG
_DEC = 20.0


def _master(tmp_path, name: str, *, ra_deg: float = 150.0,
            dec_deg: float = _DEC) -> str:
    """A finished-stack master FITS with a real TAN WCS and a fully covered
    canvas (no frame-count sibling, so the well-covered mask falls back to the
    has-data footprint — every pixel counts)."""
    hdr = fits.Header()
    hdr["CTYPE1"] = "RA---TAN"
    hdr["CTYPE2"] = "DEC--TAN"
    hdr["CRPIX1"] = (_W - 1) / 2 + 1
    hdr["CRPIX2"] = (_H - 1) / 2 + 1
    hdr["CRVAL1"] = ra_deg
    hdr["CRVAL2"] = dec_deg
    hdr["CD1_1"] = -_SCALE_DEG
    hdr["CD1_2"] = 0.0
    hdr["CD2_1"] = 0.0
    hdr["CD2_2"] = _SCALE_DEG
    cube = np.full((3, _H, _W), 0.3, dtype=np.float32)
    path = tmp_path / f"{name}.fits"
    fits.PrimaryHDU(data=cube, header=hdr).writeto(path, overwrite=True)
    return str(path)


def test_one_picture_is_exactly_its_own_wcs_area(tmp_path):
    """The union of one picture is that picture — the single-master
    measurement is untouched by the deduplication that surrounds it."""
    path = _master(tmp_path, "a")
    assert stack_sky_area_deg2(path) == pytest.approx(_AREA_DEG2, rel=1e-9)

    cov = sky_area_union_deg2([path])
    assert cov.n_pictures == 1
    assert cov.union_deg2 == pytest.approx(_AREA_DEG2, rel=1e-9)
    assert cov.summed_deg2 == pytest.approx(_AREA_DEG2, rel=1e-9)


def test_two_pictures_of_different_patches_still_add_up(tmp_path):
    """Nothing is deduplicated that shouldn't be: two targets pointed 5° apart
    are two patches of sky and the owner has genuinely seen both."""
    paths = [_master(tmp_path, "a"), _master(tmp_path, "b", ra_deg=155.0)]
    cov = sky_area_union_deg2(paths)
    assert cov.n_pictures == 2
    assert cov.union_deg2 == pytest.approx(2 * _AREA_DEG2, rel=1e-9)
    assert cov.summed_deg2 == pytest.approx(2 * _AREA_DEG2, rel=1e-9)


def test_two_pictures_of_the_same_patch_are_counted_once(tmp_path):
    """The bug: the owner's library holds several pairs aimed at exactly the
    same sky (a mosaic and the single field it grew from, and both folder
    spellings of one object), and every one of them was counted twice."""
    paths = [_master(tmp_path, "a"), _master(tmp_path, "b")]
    cov = sky_area_union_deg2(paths)
    assert cov.n_pictures == 2                      # still two pictures…
    assert cov.union_deg2 == pytest.approx(_AREA_DEG2, rel=1e-9)   # …one patch
    # The old naive total is still reported, so a caller can say what moved.
    assert cov.summed_deg2 == pytest.approx(2 * _AREA_DEG2, rel=1e-9)


def test_half_overlapping_pictures_count_the_shared_half_once(tmp_path):
    """The realistic case, and the one a set-based fix has to get roughly
    right rather than exactly: a re-framed second session sharing half its
    field with the first is 1.5 patches, not 2."""
    # Half the canvas width, in RA degrees at this declination.
    half_ra = 0.5 * _W * _SCALE_DEG / math.cos(math.radians(_DEC))
    paths = [_master(tmp_path, "a"),
             _master(tmp_path, "b", ra_deg=150.0 + half_ra)]
    cov = sky_area_union_deg2(paths)
    assert cov.summed_deg2 == pytest.approx(2 * _AREA_DEG2, rel=1e-9)
    # Well clear of both wrong answers (2.0× summed, 1.0× fully deduplicated),
    # with room for the grid's boundary rounding.
    assert 1.35 * _AREA_DEG2 < cov.union_deg2 < 1.65 * _AREA_DEG2


def test_an_unsolved_picture_contributes_nothing_rather_than_a_guess(tmp_path):
    """No WCS ⇒ no honest area, exactly as for a single master."""
    hdr = fits.Header()
    path = tmp_path / "nowcs.fits"
    fits.PrimaryHDU(data=np.full((3, _H, _W), 0.3, dtype=np.float32),
                    header=hdr).writeto(path, overwrite=True)
    cov = sky_area_union_deg2([str(path)])
    assert cov.n_pictures == 0
    assert cov.union_deg2 == 0.0
    assert cov.summed_deg2 == 0.0


def test_no_pictures_at_all_is_zero_not_an_error(tmp_path):
    cov = sky_area_union_deg2([])
    assert (cov.union_deg2, cov.summed_deg2, cov.n_pictures) == (0.0, 0.0, 0)


# ---- the sky grid the deduplication is bucketed into ---------------------

def test_the_sky_grid_agrees_with_itself_and_wraps_in_ra():
    """A cell is only an identity for "this patch is already counted", so the
    two properties that matter are that one position always lands in one cell,
    and that the RA seam is not a discontinuity."""
    ra = np.array([10.0, 10.0, 360.0, 0.0])
    dec = np.array([20.0, 20.0, 20.0, 20.0])
    keys = _sky_cell_keys(ra, dec, 0.05)
    assert keys[0] == keys[1]        # the same position, twice
    assert keys[2] == keys[3]        # RA 360° is RA 0°, not a different sky


def test_the_sky_grid_separates_patches_a_degree_apart_and_the_two_poles():
    keys = _sky_cell_keys(np.array([10.0, 11.0]), np.array([20.0, 20.0]), 0.05)
    assert keys[0] != keys[1]
    poles = _sky_cell_keys(np.array([10.0, 10.0]), np.array([89.9, -89.9]), 0.05)
    assert poles[0] != poles[1]
