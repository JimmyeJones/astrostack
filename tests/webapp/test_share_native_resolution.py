"""The picture you actually *share* comes off the master, not the 1024 px preview.

Every export the app hands over used to start from ``run.preview_path`` — the
stored preview, capped at ``PREVIEW_MAX_WIDTH`` — so the JPEG a beginner posts,
sends to family or prints was 1024 px however big the stack was. These pin that
the share JPEG (and its keepsake / scale-&-compass variants) is re-rendered from
the run's own master at share resolution, and that every case where that render
could show a *different* picture still falls back to the stored bytes.
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

_seq = 0


def _register(data_root, safe: str, *, canvas=(1600, 1600), preview_long: int = 400,
              display_space: bool = False, rotation_deg: float = 0.0) -> int:
    """A run as a real stack leaves one: a full-resolution master, and a stored
    preview that is the *capped* render of it."""
    global _seq
    _seq += 1
    tag = f"share_{_seq}"
    from seestack.render.thumbnail import render_preview_png_full_res

    w, h = canvas
    lib = Library.open_or_create(data_root / "library")
    try:
        tdir = Path(lib.target_dir(lib.find_target(safe)))
        ramp = np.tile(np.linspace(0.02, 0.9, w, dtype=np.float32), (h, 1))
        cube = np.stack([ramp, ramp, ramp], axis=0)
        wcs = WCS(naxis=2)
        wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
        wcs.wcs.crpix = [w / 2 + 0.5, h / 2 + 0.5]
        wcs.wcs.crval = [150.0, 20.0]
        th = np.radians(rotation_deg)
        ct, st = float(np.cos(th)), float(np.sin(th))
        s = 0.001
        wcs.wcs.cd = [[-s * ct, s * st], [s * st, s * ct]]
        fits_path = tdir / f"{tag}_master.fits"
        fits.PrimaryHDU(data=cube, header=wcs.to_header()).writeto(
            fits_path, overwrite=True)
        preview_path = tdir / f"{tag}_master_preview.png"
        preview_path.write_bytes(
            render_preview_png_full_res(fits_path, max_long_edge=preview_long))

        opts = {"output_name": tag}
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


def _img(content: bytes) -> Image.Image:
    return Image.open(BytesIO(content))


def _safe(client) -> str:
    return client.get("/api/targets").json()[0]["safe_name"]


def test_share_jpeg_comes_off_the_master_not_the_capped_preview(
        client, solved_library):
    safe = _safe(client)
    run_id = _register(solved_library, safe, canvas=(1600, 1600), preview_long=400)
    r = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/jpeg")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg"
    assert _img(r.content).size == (1600, 1600)          # was the 400 px preview


def test_share_jpeg_is_capped_so_a_share_stays_a_quick_render(
        client, solved_library, monkeypatch):
    """A huge mosaic doesn't turn one tap into a full-canvas render: the share
    render is bounded by `SHARE_JPEG_MAX_LONG_EDGE`."""
    from webapp.routers import stack as stack_router

    monkeypatch.setattr(stack_router, "SHARE_JPEG_MAX_LONG_EDGE", 700)
    safe = _safe(client)
    run_id = _register(solved_library, safe, canvas=(1600, 1600), preview_long=400)
    r = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/jpeg")
    assert max(_img(r.content).size) == 700


def test_share_jpeg_is_the_same_picture_only_bigger(client, solved_library):
    """Bigger, not different. Compared against the display-space twin, which
    declines the native render and so serves the old preview-sourced bytes."""
    safe = _safe(client)
    native = _register(solved_library, safe, canvas=(1600, 1600))
    stored = _register(solved_library, safe, canvas=(1600, 1600), display_space=True)

    a = _img(client.get(f"/api/targets/{safe}/stack-runs/{native}/jpeg").content)
    b = _img(client.get(f"/api/targets/{safe}/stack-runs/{stored}/jpeg").content)
    assert a.size == (1600, 1600) and b.size == (400, 400)
    small_a = np.asarray(a.convert("L").resize((32, 32), Image.BOX), dtype=float)
    small_b = np.asarray(b.convert("L").resize((32, 32), Image.BOX), dtype=float)
    assert np.abs(small_a - small_b).max() < 12.0


def test_share_jpeg_measures_the_scale_bar_against_the_picture_it_draws_on(
        client, solved_library, monkeypatch):
    """The bar's length is `fraction × the width it is handed`, so handing the
    marks the stored preview's width while drawing on the master would print a
    bar a quarter the length it claims."""
    from webapp.routers import stack as stack_router

    seen: list[int] = []
    real = stack_router._sky_marks_for_run

    def spy(fits_path, preview_width, *a, **k):  # noqa: ANN001, ANN202
        seen.append(preview_width)
        return real(fits_path, preview_width, *a, **k)

    monkeypatch.setattr(stack_router, "_sky_marks_for_run", spy)
    safe = _safe(client)
    run_id = _register(solved_library, safe, canvas=(1600, 1600), preview_long=400)
    r = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/jpeg?scale=true")
    assert r.status_code == 200
    assert seen == [1600]
    assert _img(r.content).size == (1600, 1600)


def test_keepsake_frames_the_full_resolution_picture(client, solved_library):
    """The framed variant — the one meant for a 6×4 print — mats the big picture,
    and its matte scales with it rather than staying a 1024 px card."""
    safe = _safe(client)
    run_id = _register(solved_library, safe, canvas=(1600, 1600), preview_long=400)
    r = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/jpeg?keepsake=true")
    assert r.status_code == 200
    w, h = _img(r.content).size
    assert w > 1600 and h > 1600                        # picture + a matte around it


def test_share_jpeg_falls_back_to_the_preview_for_a_processed_run(
        client, solved_library):
    safe = _safe(client)
    run_id = _register(solved_library, safe, canvas=(1600, 1600), preview_long=400,
                       display_space=True)
    assert _img(client.get(
        f"/api/targets/{safe}/stack-runs/{run_id}/jpeg").content).size == (400, 400)


def test_share_jpeg_falls_back_when_the_master_is_gone(client, solved_library):
    safe = _safe(client)
    run_id = _register(solved_library, safe, canvas=(1600, 1600), preview_long=400)
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
    assert _img(client.get(
        f"/api/targets/{safe}/stack-runs/{run_id}/jpeg").content).size == (400, 400)


def test_share_jpeg_north_up_still_turns_the_bigger_picture(client, solved_library):
    safe = _safe(client)
    run_id = _register(solved_library, safe, canvas=(1600, 1600), preview_long=400,
                       rotation_deg=30.0)
    plain = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/jpeg")
    north = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/jpeg?north_up=true")
    assert plain.status_code == 200 and north.status_code == 200
    assert plain.content != north.content
    assert _img(plain.content).size == (1600, 1600)
    # A bicubic expand-rotate grows the canvas and exposes black corners.
    assert max(_img(north.content).size) > 1600
    north_arr = np.asarray(_img(north.content).convert("L"))
    plain_arr = np.asarray(_img(plain.content).convert("L"))
    assert (north_arr < 8).mean() > (plain_arr < 8).mean() + 0.01
