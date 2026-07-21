"""`GET …/stack-runs/{id}/annotations` — catalog objects inside a stack's field."""

from __future__ import annotations

import numpy as np
from astropy.io import fits

from seestack.io.library import Library
from seestack.io.project import StackRunRow


def _add_run(data_root, safe: str, *, ra: float, dec: float, w: int, h: int,
             arcsec_per_px: float, with_wcs: bool = True) -> int:
    """Register a stack run backed by a real 3-channel master FITS.

    When ``with_wcs`` the FITS header carries a TAN WCS centred on (ra, dec) —
    exactly as the stacker merges the canvas WCS into ``master.fits`` — so the
    endpoint reads the field geometry from the file, as in production."""
    lib = Library.open_or_create(data_root / "library")
    try:
        tdir = lib.target_dir(lib.find_target(safe))
        fits_path = tdir / f"annot_{ra}_{w}x{h}.fits"
        cube = np.zeros((3, h, w), dtype=np.float32)  # (C, H, W)
        hdu = fits.PrimaryHDU(data=cube)
        if with_wcs:
            hdr = hdu.header
            hdr["CTYPE1"] = "RA---TAN"
            hdr["CTYPE2"] = "DEC--TAN"
            hdr["CRPIX1"] = w / 2 + 0.5
            hdr["CRPIX2"] = h / 2 + 0.5
            hdr["CRVAL1"] = ra
            hdr["CRVAL2"] = dec
            hdr["CD1_1"] = -arcsec_per_px / 3600.0
            hdr["CD1_2"] = 0.0
            hdr["CD2_1"] = 0.0
            hdr["CD2_2"] = arcsec_per_px / 3600.0
        hdu.writeto(fits_path, overwrite=True)

        proj = lib.open_target(safe)
        try:
            run_id = proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc="2026-05-01T00:00:00Z",
                output_basename="master", fits_path=str(fits_path), tiff_path=None,
                preview_path=None, n_frames_used=3,
                canvas_h=h, canvas_w=w, coverage_min=1, coverage_max=3,
                options_json="{}",
            ))
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
        return run_id
    finally:
        lib.close()


def test_annotations_lists_catalog_objects_in_the_field(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    # A wide field on M31 (~3.3° × 2.5°) — the bundled catalog has M31 here.
    w, h = 4000, 3000
    run_id = _add_run(solved_library, safe, ra=10.68, dec=41.27, w=w, h=h,
                      arcsec_per_px=3.0)

    r = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/annotations")
    assert r.status_code == 200
    body = r.json()
    assert body["width"] == w and body["height"] == h
    ids = {o["catalog_id"] for o in body["objects"]}
    assert "M31" in ids
    for o in body["objects"]:
        assert -0.5 <= o["x_px"] <= w - 0.5
        assert -0.5 <= o["y_px"] <= h - 0.5
        assert {"catalog_id", "name", "type", "ra_deg", "dec_deg", "x_px", "y_px"} <= o.keys()


def test_annotations_empty_when_run_has_no_wcs(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _add_run(solved_library, safe, ra=10.68, dec=41.27, w=512, h=512,
                      arcsec_per_px=3.0, with_wcs=False)

    r = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/annotations")
    assert r.status_code == 200  # never 404s where the run exists
    body = r.json()
    assert body["objects"] == []


def test_annotations_404_for_unknown_run(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    r = client.get(f"/api/targets/{safe}/stack-runs/999999/annotations")
    assert r.status_code == 404
