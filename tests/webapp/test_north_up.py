"""'North up' orientation on the History render — offered from the run's WCS.

Rotates the rendered stack so celestial North points up (like reference photos of
the object). Availability + angle come from the render-suggestion endpoint; the
render endpoint applies it when ``north_up=true``.
"""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

import numpy as np
from astropy.io import fits
from astropy.wcs import WCS
from PIL import Image

from seestack.io.library import Library
from seestack.io.project import StackRunRow


def _register_wcs_run(data_root, safe: str, *, rot_deg: float) -> int:
    """Register a run whose 3-channel master FITS carries a celestial WCS rotated
    by ``rot_deg`` (RA increasing left)."""
    lib = Library.open_or_create(data_root / "library")
    try:
        tdir = Path(lib.target_dir(lib.find_target(safe)))
        h = w = 80
        yy, xx = np.mgrid[0:h, 0:w]
        blob = np.exp(-(((xx - 40) ** 2 + (yy - 40) ** 2) / 80.0)).astype(np.float32)
        cube = np.stack([blob, 0.6 * blob, 0.3 * blob]).astype(np.float32)

        wcs = WCS(naxis=2)
        wcs.wcs.crpix = [(w - 1) / 2 + 1, (h - 1) / 2 + 1]
        wcs.wcs.crval = [150.0, 20.0]
        wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
        th = np.radians(rot_deg)
        cd = 0.001
        wcs.wcs.cd = np.array([[-cd * np.cos(th), cd * np.sin(th)],
                               [cd * np.sin(th), cd * np.cos(th)]])
        hdr = wcs.to_header()
        hdu = fits.PrimaryHDU(data=cube, header=hdr)
        fits_path = tdir / "master.fits"
        hdu.writeto(fits_path, overwrite=True)
        preview = tdir / "master_preview.png"
        Image.new("RGB", (w, h), (10, 20, 30)).save(preview)

        proj = lib.open_target(safe)
        try:
            run_id = proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc="2026-05-01T00:00:00Z",
                output_basename="master", fits_path=str(fits_path), tiff_path=None,
                preview_path=str(preview), n_frames_used=5,
                canvas_h=h, canvas_w=w, coverage_min=1, coverage_max=5,
                options_json=json.dumps({"output_name": "m42"}),
            ))
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
        return run_id
    finally:
        lib.close()


def _png_size(content: bytes) -> tuple[int, int]:
    with Image.open(BytesIO(content)) as im:
        return im.size  # (w, h)


def test_suggestion_reports_a_north_up_angle_for_a_rotated_run(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _register_wcs_run(solved_library, safe, rot_deg=30.0)

    body = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/render-suggestion").json()
    assert body.get("north_up_deg") is not None
    # A 30° tilt needs a real (non-trivial) correction, not a snap-to-zero.
    assert abs(body["north_up_deg"]) > 5.0


def test_render_north_up_reorients_the_image(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _register_wcs_run(solved_library, safe, rot_deg=30.0)

    plain = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/render?size=256")
    rotated = client.get(
        f"/api/targets/{safe}/stack-runs/{run_id}/render?size=256&north_up=true")
    assert plain.status_code == 200 and rotated.status_code == 200
    # A 30° expand-rotate grows the canvas, so the oriented image is larger.
    pw, ph = _png_size(plain.content)
    rw, rh = _png_size(rotated.content)
    assert rw > pw and rh > ph


def test_render_north_up_noop_without_wcs(client, solved_library, tmp_path):
    # A run whose master carries no WCS (older run) offers no angle and renders
    # unchanged with north_up on — never an error.
    safe = client.get("/api/targets").json()[0]["safe_name"]
    lib = Library.open_or_create(solved_library / "library")
    try:
        tdir = Path(lib.target_dir(lib.find_target(safe)))
        cube = np.ones((3, 40, 40), np.float32)
        fp = tdir / "nowcs.fits"
        fits.PrimaryHDU(data=cube).writeto(fp, overwrite=True)
        prev = tdir / "nowcs_preview.png"
        Image.new("RGB", (40, 40), (5, 5, 5)).save(prev)
        proj = lib.open_target(safe)
        try:
            run_id = proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc="2026-05-02T00:00:00Z",
                output_basename="nowcs", fits_path=str(fp), tiff_path=None,
                preview_path=str(prev), n_frames_used=5,
                canvas_h=40, canvas_w=40, coverage_min=1, coverage_max=5,
                options_json="{}"))
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
    finally:
        lib.close()

    body = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/render-suggestion").json()
    assert body.get("north_up_deg") is None
    plain = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/render?size=128")
    rotated = client.get(
        f"/api/targets/{safe}/stack-runs/{run_id}/render?size=128&north_up=true")
    assert _png_size(plain.content) == _png_size(rotated.content)
