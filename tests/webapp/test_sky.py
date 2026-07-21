"""Sky viewer endpoint: bright-star catalog + placed stacked images."""

from __future__ import annotations

import pytest

from seestack.io.library import Library
from seestack.io.project import StackRunRow


def _add_stack_run_with_preview(data_root, safe: str) -> None:
    """Give one target a plate-scale + a stack run with a real preview file."""
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            # Ensure at least one frame carries a pixel scale so the sky router
            # can size the image on the sphere.
            first = next(proj.iter_frames())
            proj.update_frame(first.id, pixscale_arcsec=2.5, rotation_deg=12.0)

            # A real (small) PNG so the router can read its dimensions for WCS.
            from PIL import Image
            preview = lib.target_dir(lib.find_target(safe)) / "master_preview.png"
            Image.new("RGB", (960, 540)).save(preview)
            proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc="2026-05-01T00:00:00Z",
                output_basename="master", fits_path=None, tiff_path=None,
                preview_path=str(preview), n_frames_used=3,
                canvas_h=1080, canvas_w=1920, coverage_min=1, coverage_max=3,
                options_json="{}",
            ))
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
    finally:
        lib.close()


def test_sky_skips_run_whose_preview_file_is_missing(client, solved_library):
    """A run whose preview PNG was deleted on disk (but whose DB row survives)
    must not be placed on the sky — its tile's image would 404. Mirrors the
    ``Path(...).exists()`` guard gallery.py / stats.py already apply."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _add_stack_run_with_preview(solved_library, safe)
    # It's placed while the preview exists.
    assert len(client.get("/api/sky").json()["images"]) == 1

    # Delete the preview file (leave the DB row) → the run is skipped, not shown
    # with a broken preview_url.
    from pathlib import Path
    preview = Path(_preview_path_for(solved_library, safe))
    preview.unlink()
    assert len(client.get("/api/sky").json()["images"]) == 0


def _preview_path_for(data_root, safe: str) -> str:
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            run = next(r for r in proj.iter_stack_runs() if r.preview_path)
            return run.preview_path
        finally:
            proj.close()
    finally:
        lib.close()


def _add_run_with_master_wcs(data_root, safe: str, *, cd, crval=(83.6, -5.4),
                             full_w=1920, full_h=1080, preview_w=960, preview_h=540):
    """A stack run whose master FITS carries a real (rotated) canvas WCS + a
    downscaled preview PNG, so the sky router places it from the *stored* geometry.
    Returns the master FITS path."""
    import numpy as np
    from astropy.io import fits
    from PIL import Image

    from seestack.io.library import Library

    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            first = next(proj.iter_frames())
            proj.update_frame(first.id, pixscale_arcsec=2.5, rotation_deg=12.0)
            tdir = lib.target_dir(lib.find_target(safe))
            preview = tdir / "master_preview.png"
            Image.new("RGB", (preview_w, preview_h)).save(preview)
            master = tdir / "master.fits"
            hdr = fits.Header()
            hdr["CTYPE1"] = "RA---TAN"
            hdr["CTYPE2"] = "DEC--TAN"
            hdr["CRPIX1"] = full_w / 2 + 0.5
            hdr["CRPIX2"] = full_h / 2 + 0.5
            hdr["CRVAL1"] = crval[0]
            hdr["CRVAL2"] = crval[1]
            hdr["CD1_1"], hdr["CD1_2"] = cd[0]
            hdr["CD2_1"], hdr["CD2_2"] = cd[1]
            fits.PrimaryHDU(
                data=np.zeros((3, full_h, full_w), dtype=np.float32), header=hdr,
            ).writeto(master, overwrite=True)
            proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc="2026-05-01T00:00:00Z",
                output_basename="master", fits_path=str(master), tiff_path=None,
                preview_path=str(preview), n_frames_used=3,
                canvas_h=full_h, canvas_w=full_w, coverage_min=1, coverage_max=3,
                options_json="{}",
            ))
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
    finally:
        lib.close()
    return master


def test_sky_places_image_from_the_stored_canvas_wcs(client, solved_library):
    """When the run's master FITS carries a canvas WCS, the overlay is placed from
    *that* stored geometry (rescaled to the preview grid) — not extrapolated from
    frame 0. A 37° canvas rotation is faithfully reproduced, which the frame-0 TAN
    fallback (rotation 12°) would get wrong. This is the owner-reported sky-map
    placement fix."""
    import math

    safe = client.get("/api/targets").json()[0]["safe_name"]
    scale = 2.5 / 3600.0
    theta = math.radians(37.0)
    c, s = math.cos(theta), math.sin(theta)
    cd = [(-scale * c, scale * s), (scale * s, scale * c)]
    _add_run_with_master_wcs(solved_library, safe, cd=cd, crval=(83.6, -5.4))

    wcs = client.get("/api/sky").json()["images"][0]["wcs"]
    assert wcs is not None
    # Uniform ½ downscale (1920→960): CD columns double, orientation preserved.
    assert wcs["CD1_1"] == pytest.approx(-scale * c * 2, rel=1e-6)
    assert wcs["CD1_2"] == pytest.approx(scale * s * 2, rel=1e-6)
    assert wcs["CRVAL1"] == pytest.approx(83.6, abs=1e-9)
    assert wcs["CRVAL2"] == pytest.approx(-5.4, abs=1e-9)
    # The stored 37° rotation ≠ the frame-0 fallback's 12°, so this proves the
    # placement came from the canvas WCS, not `_tan_wcs`.
    assert abs(wcs["CD1_2"]) > 1e-4


def test_sky_falls_back_to_tan_wcs_without_a_master_fits(client, solved_library):
    """A run with no master FITS (older/edited run) still gets a placement via the
    single-frame TAN extrapolation — the fix never regresses those runs."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _add_stack_run_with_preview(solved_library, safe)  # fits_path=None
    wcs = client.get("/api/sky").json()["images"][0]["wcs"]
    assert wcs is not None
    # `_tan_wcs` centres CRVAL on the target and uses the frame-0 rotation (12°).
    assert wcs["CRPIX1"] == pytest.approx(960 / 2 + 0.5, abs=1e-9)


def test_sky_returns_stars(client):
    r = client.get("/api/sky")
    assert r.status_code == 200
    data = r.json()
    assert len(data["stars"]) > 20
    sirius = next(s for s in data["stars"] if s["name"] == "Sirius")
    assert sirius["ra_deg"] > 100 and sirius["mag"] < 0  # brightest star
    # No stacked images yet.
    assert data["images"] == []


def test_sky_places_stacked_image(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _add_stack_run_with_preview(solved_library, safe)

    data = client.get("/api/sky").json()
    assert len(data["images"]) == 1
    img = data["images"][0]
    assert img["safe"] == safe
    # 1920 px * 2.5"/px / 3600 = 1.333 deg wide; 1080 → 0.75 deg tall.
    assert abs(img["width_deg"] - 1.3333) < 1e-2
    assert abs(img["height_deg"] - 0.75) < 1e-2
    assert img["rotation_deg"] == 12.0
    # The overlay is the transparent (RGBA) sky-overlay render, so an irregular
    # mosaic shows its true footprint instead of an opaque black rectangle.
    assert img["preview_url"].endswith(f"/stack-runs/{img['run_id']}/sky-overlay")
    assert img["ra_deg"] is not None and img["dec_deg"] is not None

    # WCS for the preview PNG (960×540 here) so Aladin can place it.
    wcs = img["wcs"]
    assert wcs is not None
    assert wcs["CTYPE1"] == "RA---TAN" and wcs["CTYPE2"] == "DEC--TAN"
    assert wcs["NAXIS1"] == 960 and wcs["NAXIS2"] == 540
    assert abs(wcs["CRVAL1"] - img["ra_deg"]) < 1e-9
    assert abs(wcs["CRPIX1"] - (960 / 2 + 0.5)) < 1e-9
    # Scale = width_deg / preview_w ; |CD| diagonal ≈ that scale.
    scale = img["width_deg"] / 960
    assert abs((wcs["CD1_1"] ** 2 + wcs["CD1_2"] ** 2) ** 0.5 - scale) < 1e-9
