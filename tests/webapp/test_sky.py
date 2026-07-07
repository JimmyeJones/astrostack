"""Sky viewer endpoint: bright-star catalog + placed stacked images."""

from __future__ import annotations

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
    assert img["preview_url"].endswith(f"/stack-runs/{img['run_id']}/preview")
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
