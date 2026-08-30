"""'Make it your wallpaper' export endpoint — crop the finished preview to a
phone/desktop/square aspect, centred on the plate-solved target."""

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

_run_seq = 0


def _register_run(data_root, safe: str, *, preview: Image.Image,
                  with_wcs: bool = False, target_ra_dec=None,
                  rotation_deg: float = 0.0) -> int:
    """Register a run with a real preview PNG (and optionally a WCS master +
    target position) so the wallpaper endpoint has something to crop.

    ``rotation_deg`` rotates the WCS's CD matrix so the master is *not* North-up,
    which is what the ``north_up`` wallpaper option corrects."""
    global _run_seq
    _run_seq += 1
    tag = f"wp_{_run_seq}"
    lib = Library.open_or_create(data_root / "library")
    try:
        tdir = Path(lib.target_dir(lib.find_target(safe)))
        w, h = preview.size
        cube = np.zeros((3, h, w), dtype=np.float32)
        hdr = None
        if with_wcs:
            wcs = WCS(naxis=2)
            wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
            wcs.wcs.crpix = [w / 2 + 0.5, h / 2 + 0.5]
            wcs.wcs.crval = [150.0, 20.0]
            theta = np.radians(rotation_deg)
            ct, st = float(np.cos(theta)), float(np.sin(theta))
            s = 0.001
            # RA-flipped (CDELT1<0) TAN with an in-plane field rotation.
            wcs.wcs.cd = [[-s * ct, s * st], [s * st, s * ct]]
            hdr = wcs.to_header()
        fits_path = tdir / f"{tag}_master.fits"
        fits.PrimaryHDU(data=cube, header=hdr).writeto(fits_path, overwrite=True)
        preview_path = tdir / f"{tag}_master_preview.png"
        preview.save(preview_path)

        proj = lib.open_target(safe)
        try:
            run_id = proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc="2026-05-01T00:00:00Z",
                output_basename=f"{tag}_master", fits_path=str(fits_path), tiff_path=None,
                preview_path=str(preview_path), n_frames_used=5,
                canvas_h=h, canvas_w=w, coverage_min=1, coverage_max=5,
                options_json=json.dumps({"output_name": "wp"}),
            ))
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
        return run_id
    finally:
        lib.close()


def _register_native_run(data_root, safe: str, *, canvas=(1200, 900),
                         preview_long: int = 400, rotation_deg: float = 0.0,
                         display_space: bool = False) -> int:
    """Register a run the way a real stack leaves one: a full-resolution master
    FITS, and a stored preview that is the *capped* render of it.

    The wallpaper's whole question is which of those two it crops, so the fixture
    has to keep them at different sizes (as production does — the preview is capped
    at ``PREVIEW_MAX_WIDTH``) and make the preview a faithful downscale of the
    master rather than an unrelated picture.
    """
    global _run_seq
    _run_seq += 1
    tag = f"wpn_{_run_seq}"
    from seestack.render.thumbnail import render_preview_png_full_res

    w, h = canvas
    lib = Library.open_or_create(data_root / "library")
    try:
        tdir = Path(lib.target_dir(lib.find_target(safe)))
        # A left→right ramp: a rotation visibly reshuffles it, and its histogram is
        # scale-free, so the 400 px and full-res renders get the same autostretch.
        ramp = np.tile(np.linspace(0.02, 0.9, w, dtype=np.float32), (h, 1))
        cube = np.stack([ramp, ramp, ramp], axis=0)
        wcs = WCS(naxis=2)
        wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
        wcs.wcs.crpix = [w / 2 + 0.5, h / 2 + 0.5]
        wcs.wcs.crval = [150.0, 20.0]
        theta = np.radians(rotation_deg)
        ct, st = float(np.cos(theta)), float(np.sin(theta))
        s = 0.001
        wcs.wcs.cd = [[-s * ct, s * st], [s * st, s * ct]]
        fits_path = tdir / f"{tag}_master.fits"
        fits.PrimaryHDU(data=cube, header=wcs.to_header()).writeto(
            fits_path, overwrite=True)
        preview_path = tdir / f"{tag}_master_preview.png"
        preview_path.write_bytes(
            render_preview_png_full_res(fits_path, max_long_edge=preview_long))

        opts = {"output_name": "wp"}
        if display_space:
            opts["preview_display_space"] = True
        proj = lib.open_target(safe)
        try:
            run_id = proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc="2026-05-01T00:00:00Z",
                output_basename=f"{tag}_master", fits_path=str(fits_path),
                tiff_path=None, preview_path=str(preview_path), n_frames_used=5,
                canvas_h=h, canvas_w=w, coverage_min=1, coverage_max=5,
                options_json=json.dumps(opts),
            ))
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
        return run_id
    finally:
        lib.close()


def _set_target_position(data_root, safe: str, ra: float, dec: float) -> None:
    """Force the target's stored RA/Dec (used to steer the wallpaper crop)."""
    lib = Library.open_or_create(data_root / "library")
    try:
        lib._upsert_target(name=safe, safe_name=safe, ra_deg=ra, dec_deg=dec)
    finally:
        lib.close()


def _open(content: bytes) -> Image.Image:
    return Image.open(BytesIO(content))


def test_wallpaper_phone_desktop_square_aspects(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _register_run(solved_library, safe,
                           preview=Image.new("RGB", (400, 300), (30, 60, 120)))

    for aspect, ratio in (("phone", 1170 / 2532), ("desktop", 1920 / 1080),
                          ("square", 1.0)):
        r = client.get(
            f"/api/targets/{safe}/stack-runs/{run_id}/wallpaper?aspect={aspect}")
        assert r.status_code == 200, (aspect, r.status_code)
        assert r.headers["content-type"] == "image/jpeg"
        img = _open(r.content)
        assert abs(img.width / img.height - ratio) < 0.03, aspect
        # Never upsampled past the 400×300 source.
        assert img.width <= 400 and img.height <= 300


def test_wallpaper_unknown_aspect_is_400(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _register_run(solved_library, safe,
                           preview=Image.new("RGB", (200, 200), (0, 0, 0)))
    r = client.get(
        f"/api/targets/{safe}/stack-runs/{run_id}/wallpaper?aspect=banner")
    assert r.status_code == 400


def test_wallpaper_missing_run_is_404(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    r = client.get(f"/api/targets/{safe}/stack-runs/999999/wallpaper?aspect=phone")
    assert r.status_code == 404


def test_wallpaper_default_aspect_is_phone(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _register_run(solved_library, safe,
                           preview=Image.new("RGB", (400, 300), (30, 60, 120)))
    r = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/wallpaper")
    assert r.status_code == 200
    img = _open(r.content)
    assert abs(img.width / img.height - 1170 / 2532) < 0.03


def test_wallpaper_is_built_from_the_full_resolution_picture(client, solved_library):
    """The regression: the stored preview is capped at 1024 px, so cropping *it* to
    a phone shape handed back a wallpaper a fraction of the screen it is for. The
    run's own master carries the pixels — the wallpaper now comes off that."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _register_native_run(solved_library, safe, canvas=(1200, 900),
                                  preview_long=400)
    r = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/wallpaper?aspect=phone")
    assert r.status_code == 200
    img = _open(r.content)
    # Full-height crop of the 900 px master, not of its 300 px-tall preview.
    assert img.height == 900
    assert abs(img.width / img.height - 1170 / 2532) < 0.03


def test_wallpaper_native_source_is_the_same_picture_as_the_preview(
        client, solved_library):
    """Bigger, but not *different*: the native render must be the picture the user
    already sees. Compared against the same run's preview-sourced wallpaper (the
    display-space twin, which declines the native path) column by column."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    native = _register_native_run(solved_library, safe, canvas=(1200, 900))
    stored = _register_native_run(solved_library, safe, canvas=(1200, 900),
                                  display_space=True)

    a = _open(client.get(
        f"/api/targets/{safe}/stack-runs/{native}/wallpaper?aspect=square").content)
    b = _open(client.get(
        f"/api/targets/{safe}/stack-runs/{stored}/wallpaper?aspect=square").content)
    assert a.height > b.height                          # the point of the change
    # Same ramp, same crop: resample both to one small grid and compare.
    small_a = np.asarray(a.convert("L").resize((32, 32), Image.BOX), dtype=float)
    small_b = np.asarray(b.convert("L").resize((32, 32), Image.BOX), dtype=float)
    assert abs(small_a.mean() - small_b.mean()) < 4.0
    assert np.abs(small_a - small_b).max() < 12.0


def test_wallpaper_falls_back_to_the_preview_for_a_processed_run(
        client, solved_library):
    """A "Process target" run's preview is a display-space auto-edit only its saved
    recipe can reproduce, so the native render is declined and the endpoint behaves
    exactly as it did before."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _register_native_run(solved_library, safe, canvas=(1200, 900),
                                  preview_long=400, display_space=True)
    img = _open(client.get(
        f"/api/targets/{safe}/stack-runs/{run_id}/wallpaper?aspect=phone").content)
    assert img.height == 300                            # the stored preview's height


def test_wallpaper_falls_back_when_the_master_is_gone(client, solved_library):
    """A run whose FITS has been cleaned up still gets its (smaller) wallpaper off
    the stored preview rather than a 404."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _register_native_run(solved_library, safe, canvas=(1200, 900))
    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target(safe)
        try:
            run = next(r for r in proj.iter_stack_runs() if r.id == run_id)
        finally:
            proj.close()
    finally:
        lib.close()
    Path(run.fits_path).unlink()
    img = _open(client.get(
        f"/api/targets/{safe}/stack-runs/{run_id}/wallpaper?aspect=phone").content)
    assert img.height == 300


def test_wallpaper_north_up_on_the_native_source(client, solved_library):
    """North-up still turns the picture — and still at native resolution — when the
    bigger source is in play."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _register_native_run(solved_library, safe, canvas=(900, 900),
                                  rotation_deg=30.0)
    plain = client.get(
        f"/api/targets/{safe}/stack-runs/{run_id}/wallpaper?aspect=square")
    north = client.get(
        f"/api/targets/{safe}/stack-runs/{run_id}/wallpaper?aspect=square&north_up=true")
    assert plain.status_code == 200 and north.status_code == 200
    assert plain.content != north.content
    # Both still come off the master (the 400 px preview could not reach either).
    assert _open(plain.content).height == 900
    assert _open(north.content).height > 900            # grown by the expand-rotate
    north_arr = np.asarray(_open(north.content).convert("L"))
    plain_arr = np.asarray(_open(plain.content).convert("L"))
    assert (north_arr < 8).mean() > (plain_arr < 8).mean() + 0.01


def _wallpaper_mean(client, safe, run_id) -> float:
    r = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/wallpaper?aspect=phone")
    assert r.status_code == 200
    return float(np.asarray(_open(r.content)).mean())


def test_wallpaper_north_up_rotates_a_tilted_run(client, solved_library):
    """A run whose WCS carries a real field rotation: the North-up wallpaper is a
    rotated crop (different pixels + a tell-tale black corner from the expand
    rotate), while the plain wallpaper is not."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    # A left→right brightness ramp so a rotation visibly reshuffles the pixels.
    w, h = 400, 300
    ramp = np.tile(np.linspace(20, 235, w, dtype=np.uint8), (h, 1))
    grad = Image.fromarray(np.stack([ramp, ramp, ramp], axis=-1), "RGB")
    run_id = _register_run(solved_library, safe, preview=grad, with_wcs=True,
                           rotation_deg=30.0)

    plain = client.get(
        f"/api/targets/{safe}/stack-runs/{run_id}/wallpaper?aspect=square")
    north = client.get(
        f"/api/targets/{safe}/stack-runs/{run_id}/wallpaper?aspect=square&north_up=true")
    assert plain.status_code == 200 and north.status_code == 200
    assert plain.content != north.content                     # rotation changed it
    # The bicubic expand-rotate fills exposed corners with black, so the North-up
    # crop has some near-black pixels the plain (gap-free) ramp crop never has.
    north_arr = np.asarray(_open(north.content).convert("L"))
    plain_arr = np.asarray(_open(plain.content).convert("L"))
    assert (north_arr < 8).mean() > (plain_arr < 8).mean() + 0.01


def test_wallpaper_north_up_no_op_without_field_rotation(client, solved_library):
    """A run already North-up (no field rotation) → the ``north_up`` request is a
    no-op: byte-for-byte the same wallpaper as the plain one."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _register_run(solved_library, safe,
                           preview=Image.new("RGB", (400, 300), (30, 60, 120)),
                           with_wcs=True, rotation_deg=0.0)
    plain = client.get(
        f"/api/targets/{safe}/stack-runs/{run_id}/wallpaper?aspect=phone")
    north = client.get(
        f"/api/targets/{safe}/stack-runs/{run_id}/wallpaper?aspect=phone&north_up=true")
    assert plain.status_code == 200 and north.status_code == 200
    assert plain.content == north.content


def test_wallpaper_centres_on_the_target_via_wcs(client, solved_library):
    """A horizontal brightness ramp preview + two opposite target offsets → the
    two target-centred phone crops sit on opposite sides of the ramp (one dark,
    one bright) and both differ from the plain centred crop — proving the endpoint
    actually places the crop on the target's WCS pixel, whichever RA-sign the
    projection uses."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    w, h = 400, 300
    ramp = np.tile(np.linspace(0, 255, w, dtype=np.uint8), (h, 1))
    grad = Image.fromarray(np.stack([ramp, ramp, ramp], axis=-1), "RGB")

    wcs_run = _register_run(solved_library, safe, preview=grad, with_wcs=True)
    centre_run = _register_run(solved_library, safe, preview=grad, with_wcs=False)

    # Repoint the shared target ±0.18° in RA from the canvas-centre CRVAL between
    # calls: one offset lands near the left edge, the other near the right (which
    # is which depends on the CD sign — the test stays agnostic to that).
    _set_target_position(solved_library, safe, 150.18, 20.0)
    mean_a = _wallpaper_mean(client, safe, wcs_run)
    _set_target_position(solved_library, safe, 149.82, 20.0)
    mean_b = _wallpaper_mean(client, safe, wcs_run)
    mean_centre = _wallpaper_mean(client, safe, centre_run)

    # Opposite offsets land on opposite ends of the ramp.
    assert abs(mean_a - mean_b) > 40
    # One clearly darker than centre, the other clearly brighter.
    lo, hi = sorted((mean_a, mean_b))
    assert lo < mean_centre - 15
    assert hi > mean_centre + 15
