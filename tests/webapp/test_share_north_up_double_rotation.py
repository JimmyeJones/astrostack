"""Sharing a picture whose stored preview was already saved North-up.

History's "Adjust → North up → Save" overwrites a run's stored preview with a
*rotated* render and records the angle (``stack_runs.preview_north_up_deg``).
Every surface that re-orients those stored bytes derives its geometry from the
master FITS, so unless it is told what the bytes already carry it applies the
whole turn a second time — the share came out 180° from the picture on screen.
The wallpaper's crop centre had the same blind spot in a different place: it maps
the target's RA/Dec onto a *uniform downscale* of the master, which a rotated
stored preview no longer is.

These drive the real endpoints, and the double-rotation ones are written against
the filed repro (a portrait master with a 90°-off canvas WCS, so a wrong turn is
visible in the dimensions alone).
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("astropy")
pytest.importorskip("PIL")

from astropy.io import fits  # noqa: E402
from PIL import Image  # noqa: E402

from seestack.io.library import Library  # noqa: E402
from seestack.io.project import StackRunRow  # noqa: E402

FULL_W, FULL_H = 120, 200


def _add_run(data_root, safe: str, *, rot_deg: float | None = 90.0) -> tuple[str, str]:
    """A run whose master is a tall 120×200 cube with a bright off-centre blob and
    (optionally) a ``rot_deg``-rotated canvas WCS **centred on the target's own
    catalog position at the blob**, so the wallpaper's crop has a real, off-centre
    point to find rather than one clamped to the frame. Returns
    ``(run_id, fits_path)``."""
    lib = Library.open_or_create(data_root / "library")
    try:
        entry = lib.find_target(safe)
        tdir = lib.target_dir(entry)
        yy, xx = np.mgrid[0:FULL_H, 0:FULL_W]
        blob = np.exp(-(((xx - 29) ** 2 + (yy - 39) ** 2) / 40.0)).astype(np.float32)
        sky = np.full((FULL_H, FULL_W), 0.02, dtype=np.float32)
        cube = np.stack([sky + blob, sky + 0.6 * blob, sky + 0.3 * blob]).astype(np.float32)
        hdr = fits.Header()
        if rot_deg is not None:
            th = np.radians(rot_deg)
            cdelt = 0.001
            hdr["CTYPE1"], hdr["CTYPE2"] = "RA---TAN", "DEC--TAN"
            # Reference pixel *on the blob* (1-based) at the target's own
            # RA/Dec, so `wallpaper_target_pixel` lands there.
            hdr["CRPIX1"], hdr["CRPIX2"] = 30.0, 40.0
            hdr["CRVAL1"] = float(entry.ra_deg)
            hdr["CRVAL2"] = float(entry.dec_deg)
            hdr["CD1_1"] = -cdelt * np.cos(th)
            hdr["CD1_2"] = cdelt * np.sin(th)
            hdr["CD2_1"] = cdelt * np.sin(th)
            hdr["CD2_2"] = cdelt * np.cos(th)
        fits_path = tdir / "master.fits"
        fits.PrimaryHDU(data=cube, header=hdr).writeto(fits_path, overwrite=True)
        preview_path = tdir / "master_preview.png"
        preview_path.write_bytes(b"\x89PNG\r\n\x1a\n")   # overwritten by the save below
        proj = lib.open_target(safe)
        try:
            run_id = proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc="2026-05-01T00:00:00Z",
                output_basename="master", fits_path=str(fits_path), tiff_path=None,
                preview_path=str(preview_path), n_frames_used=3,
                canvas_h=FULL_H, canvas_w=FULL_W, coverage_min=1, coverage_max=3,
                options_json="{}",
            ))
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
        return str(run_id), str(fits_path)
    finally:
        lib.close()


def _save_preview(client, safe: str, run_id: str, *, north_up: bool) -> None:
    r = client.post(f"/api/targets/{safe}/stack-runs/{run_id}/preview",
                    json={"stretch": 0.5, "black": 0.35, "north_up": north_up})
    assert r.status_code == 200, r.text


def _run(data_root, safe: str, run_id: str):
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            return next(r for r in proj.iter_stack_runs() if r.id == int(run_id))
        finally:
            proj.close()
    finally:
        lib.close()


def _size(data: bytes) -> tuple[int, int]:
    with Image.open(BytesIO(data)) as im:
        return im.size


# ---- the share JPEG ----------------------------------------------------------

def test_a_north_up_share_of_an_already_north_up_preview_is_not_turned_twice(
        client, solved_library):
    """The filed repro, end to end: with the picture already saved North-up, a
    North-up share must be the *same* picture, not one turned another 90°."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id, _fits = _add_run(solved_library, safe)

    # Baseline: saved un-rotated, a North-up share turns it once (portrait → landscape).
    _save_preview(client, safe, run_id, north_up=False)
    assert _size(Path(_run(solved_library, safe, run_id).preview_path).read_bytes()) \
        == (FULL_W, FULL_H)
    once = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/jpeg?north_up=true")
    assert once.status_code == 200
    assert _size(once.content) == (FULL_H, FULL_W)

    # Now save it North-up: the stored preview is itself landscape…
    _save_preview(client, safe, run_id, north_up=True)
    stored = Path(_run(solved_library, safe, run_id).preview_path).read_bytes()
    assert _size(stored) == (FULL_H, FULL_W)

    # …and a North-up share must stay landscape. Before the fix it came back
    # portrait — turned a second time, i.e. 180° from the picture on screen.
    again = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/jpeg?north_up=true")
    assert again.status_code == 200
    assert _size(again.content) == (FULL_H, FULL_W)

    # Exactly the stored picture, transcoded — the remaining rotation is zero, so
    # the bytes are never resampled again either.
    from seestack.stack.output import png_bytes_to_jpeg
    assert again.content == png_bytes_to_jpeg(stored)


def test_an_unrotated_run_shares_exactly_what_it_always_did(client, solved_library):
    """The no-regression half: with nothing baked in, the North-up share is the
    full turn applied to the stored preview, byte-for-byte as before."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id, fits_path = _add_run(solved_library, safe)
    _save_preview(client, safe, run_id, north_up=False)
    stored = Path(_run(solved_library, safe, run_id).preview_path).read_bytes()

    from seestack.render.thumbnail import orient_preview_north_up
    from seestack.stack.output import png_bytes_to_jpeg
    expected = png_bytes_to_jpeg(orient_preview_north_up(stored, fits_path))
    got = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/jpeg?north_up=true")
    assert got.status_code == 200
    assert got.content == expected
    # …and the plain share is untouched by any of this.
    plain = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/jpeg")
    assert plain.content == png_bytes_to_jpeg(stored)


def test_a_run_with_no_wcs_keeps_whatever_the_save_left(client, solved_library):
    """No usable WCS → nothing can be recomputed, so the bytes are served as
    stored rather than 'un-rotated' on a guess."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id, _fits = _add_run(solved_library, safe, rot_deg=None)
    _save_preview(client, safe, run_id, north_up=True)
    stored = Path(_run(solved_library, safe, run_id).preview_path).read_bytes()

    from seestack.stack.output import png_bytes_to_jpeg
    got = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/jpeg?north_up=true")
    assert got.status_code == 200
    assert got.content == png_bytes_to_jpeg(stored)


# ---- the baked scale bar + North/East rose -----------------------------------

def test_the_sky_marks_follow_a_preview_a_past_save_rotated(client, solved_library):
    """Same root class, found by the sweep: the rose is drawn at the rotation the
    *pixels* carry, and the bar's length is measured against the un-rotated width.
    Both were read off "what this request turned", which is zero for a picture the
    save had already turned."""
    from webapp.routers.stack import _sky_marks_for_run, _unrotated_preview_width

    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id, fits_path = _add_run(solved_library, safe)
    _save_preview(client, safe, run_id, north_up=True)
    run = _run(solved_library, safe, run_id)
    stored = Path(run.preview_path).read_bytes()
    baked = run.preview_north_up_deg
    assert baked and abs(baked) > 45.0        # the fixture really did turn it

    # The bar is a fraction of the picture's width *before* the turn — the stored
    # PNG's own width is the rotated one, and using it draws the bar too short.
    assert _size(stored) == (FULL_H, FULL_W)
    assert _unrotated_preview_width(stored, fits_path, baked) == FULL_W
    assert _unrotated_preview_width(stored, fits_path, 0.0) == FULL_H  # the old answer

    # And the rose: the marks at the baked angle are a different picture from the
    # marks at 0°, so serving the stale angle really was visible.
    marks_now = _sky_marks_for_run(fits_path, FULL_W, baked)
    marks_stale = _sky_marks_for_run(fits_path, FULL_W, 0.0)
    assert marks_now.directions != marks_stale.directions

    from seestack.stack.output import png_bytes_to_jpeg
    got = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/jpeg?scale=true")
    assert got.status_code == 200
    assert got.content == png_bytes_to_jpeg(stored, sky_marks=marks_now)
    assert got.content != png_bytes_to_jpeg(stored, sky_marks=marks_stale)


# ---- the wallpaper -----------------------------------------------------------

def test_a_north_up_wallpaper_of_an_already_north_up_preview_is_not_turned_twice(
        client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id, _fits = _add_run(solved_library, safe)
    _save_preview(client, safe, run_id, north_up=True)
    stored = Path(_run(solved_library, safe, run_id).preview_path).read_bytes()

    plain = client.get(
        f"/api/targets/{safe}/stack-runs/{run_id}/wallpaper?aspect=phone")
    turned = client.get(
        f"/api/targets/{safe}/stack-runs/{run_id}/wallpaper?aspect=phone&north_up=true")
    assert plain.status_code == turned.status_code == 200
    # Nothing left to turn, so asking for North-up changes nothing at all.
    assert turned.content == plain.content

    from seestack.wallpaper import (
        WALLPAPER_PRESETS,
        png_size,
        render_wallpaper_jpeg,
        rotate_point_north_up,
        wallpaper_target_pixel,
    )
    assert png_size(stored) == (FULL_H, FULL_W)
    # …and the crop is centred on where the object actually is in those rotated
    # pixels: measured on the un-rotated grid, then turned by the baked angle.
    run = _run(solved_library, safe, run_id)
    lib = Library.open_or_create(solved_library / "library")
    try:
        entry = lib.find_target(safe)
        ra, dec = entry.ra_deg, entry.dec_deg
    finally:
        lib.close()
    flat = wallpaper_target_pixel(run.fits_path, ra, dec, FULL_W, FULL_H)
    assert flat is not None
    expected_px = rotate_point_north_up(
        flat[0], flat[1], FULL_W, FULL_H, run.preview_north_up_deg)
    assert plain.content == render_wallpaper_jpeg(
        stored, WALLPAPER_PRESETS["phone"], expected_px)
    # The old code measured against the rotated size and never turned the point —
    # a visibly different crop.
    stale = wallpaper_target_pixel(run.fits_path, ra, dec, FULL_H, FULL_W)
    assert plain.content != render_wallpaper_jpeg(
        stored, WALLPAPER_PRESETS["phone"], stale)


def test_an_unrotated_wallpaper_is_exactly_what_it_always_was(client, solved_library):
    """No-regression: with nothing baked in, both the crop centre and the
    North-up turn are what they were before."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id, fits_path = _add_run(solved_library, safe)
    _save_preview(client, safe, run_id, north_up=False)
    stored = Path(_run(solved_library, safe, run_id).preview_path).read_bytes()

    from seestack.render.orient import NORTH_UP_MIN_DEG
    from seestack.render.thumbnail import orient_preview_north_up, stack_north_up_deg
    from seestack.wallpaper import (
        WALLPAPER_PRESETS,
        png_size,
        render_wallpaper_jpeg,
        rotate_point_north_up,
        wallpaper_target_pixel,
    )
    lib = Library.open_or_create(solved_library / "library")
    try:
        entry = lib.find_target(safe)
        ra, dec = entry.ra_deg, entry.dec_deg
    finally:
        lib.close()
    size = png_size(stored)
    target_px = wallpaper_target_pixel(fits_path, ra, dec, size[0], size[1])

    plain = client.get(
        f"/api/targets/{safe}/stack-runs/{run_id}/wallpaper?aspect=phone")
    assert plain.content == render_wallpaper_jpeg(
        stored, WALLPAPER_PRESETS["phone"], target_px)

    angle = stack_north_up_deg(fits_path)
    assert angle is not None and abs(angle) >= NORTH_UP_MIN_DEG
    turned_px = rotate_point_north_up(target_px[0], target_px[1], size[0], size[1], angle)
    turned = client.get(
        f"/api/targets/{safe}/stack-runs/{run_id}/wallpaper?aspect=phone&north_up=true")
    assert turned.content == render_wallpaper_jpeg(
        orient_preview_north_up(stored, fits_path),
        WALLPAPER_PRESETS["phone"], turned_px)


# ---- the other way the recorded angle can go stale ---------------------------

def test_the_auto_edit_clears_a_rotation_it_just_rendered_away(client, solved_library):
    """Found by the same sweep: "Process target"'s auto-edit rewrites the stored
    preview from the master's own (un-rotated) grid, so a North-up rotation an
    earlier save baked in is gone — but the recorded angle survived it. A stale
    angle is worse than none: every surface that lines up with the stored preview
    then corrects for a turn that is no longer there."""
    from webapp.pipeline import _auto_edit_process_run

    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id, _fits = _add_run(solved_library, safe)
    _save_preview(client, safe, run_id, north_up=True)
    before = _run(solved_library, safe, run_id)
    assert before.preview_north_up_deg          # the save really did record one
    assert _size(Path(before.preview_path).read_bytes()) == (FULL_H, FULL_W)

    lib = Library.open_or_create(solved_library / "library")
    try:
        assert _auto_edit_process_run(lib, safe, int(run_id)) is not None
    finally:
        lib.close()

    after = _run(solved_library, safe, run_id)
    # The rewritten preview is back on the master's grid…
    assert _size(Path(after.preview_path).read_bytes()) == (FULL_W, FULL_H)
    # …and the record says so.
    assert after.preview_north_up_deg == 0.0
