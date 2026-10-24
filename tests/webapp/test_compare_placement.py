"""Compare's Split and Blink on a grown mosaic: ``GET …/compare-placement``.

Split lays run A's preview over run B's and Blink swaps them in one frame. Both
drew the two "contain" in one 640×420 box, so on a mosaic that grew between the
runs the same star sat ~94 px apart (Scout 2026-10-24). The endpoint now says
where A's displayed preview sits on B's by both masters' WCS; these tests hold
it to a **star**: one sky position, rendered into both previews by the real
renderer, must land on one frame pixel (± 1) once A goes through the matrix and
B through its offset — including when B is shown through the North-up view.
"""

from __future__ import annotations

import io
import math

import numpy as np
from astropy.io import fits
from astropy.wcs import WCS
from PIL import Image

from seestack.io.library import Library
from seestack.io.project import StackRunRow

# One shared tangent plane: a master whose pixel (0, 0) sits at plane (ox, oy)
# shows the sky at plane (x + ox, y + oy) at pixel (x, y).
_STAR_PLANE = (900.0, 420.0)
_SCALE = 3.0e-4                     # deg / px


def _plane_wcs() -> WCS:
    """The shared plane itself: an un-turned master with offset (0, 0)."""
    hd = fits.Header()
    hd["CTYPE1"], hd["CTYPE2"] = "RA---TAN", "DEC--TAN"
    hd["CRVAL1"], hd["CRVAL2"] = 83.8, 22.0
    hd["CRPIX1"], hd["CRPIX2"] = 1001.0, 501.0
    hd["CD1_1"], hd["CD2_2"] = -_SCALE, _SCALE
    hd["CD1_2"], hd["CD2_1"] = 0.0, 0.0
    return WCS(hd)


def _add_run(root, safe: str, name: str, *, w: int, h: int,
             offset: tuple[float, float] | None, rot_deg: float = 0.0,
             star: tuple[float, float] = _STAR_PLANE,
             crop: tuple[float, float, float, float] | None = None,
             bake_north_up: bool = False) -> int:
    """A master with one star at plane ``star`` and a WCS on the shared plane
    (``offset`` ``None`` → no WCS at all), its preview rendered by the real
    renderer, registered as a stack run.

    ``crop`` stores the preview as the one-click auto-edit's border trim does — a
    downscale of that fraction of the canvas, recorded in ``preview_crop_json`` —
    and ``bake_north_up`` as History's "North up → Save" does: turned bytes, the
    angle recorded on the run."""
    from seestack.render.thumbnail import render_stack_png

    lib = Library.open_or_create(root / "library")
    try:
        tdir = lib.target_dir(lib.find_target(safe))
        ox, oy = offset if offset is not None else (0.0, 0.0)
        hdu = fits.PrimaryHDU()
        hd = hdu.header
        if offset is not None:
            hd["CTYPE1"], hd["CTYPE2"] = "RA---TAN", "DEC--TAN"
            hd["CRVAL1"], hd["CRVAL2"] = 83.8, 22.0
            # Plane point (1000, 500) is the tangent point, 1-based CRPIX.
            hd["CRPIX1"], hd["CRPIX2"] = 1000.0 - ox + 1, 500.0 - oy + 1
            c, s = math.cos(math.radians(rot_deg)), math.sin(math.radians(rot_deg))
            hd["CD1_1"], hd["CD1_2"] = -_SCALE * c, _SCALE * s
            hd["CD2_1"], hd["CD2_2"] = _SCALE * s, _SCALE * c
            # Draw the star where *this* WCS puts the shared sky point, so a
            # turned framing still shows the same star.
            ra, dec = _plane_wcs().all_pix2world([star[0]], [star[1]], 0)
            px, py = WCS(hd).all_world2pix(ra, dec, 0)
            sx, sy = float(px[0]), float(py[0])
        else:
            sx, sy = star[0] - ox, star[1] - oy
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        chan = (0.05 + 0.9 * np.exp(-((xx - sx) ** 2 + (yy - sy) ** 2) / (2 * 4.0 ** 2))
                ).astype(np.float32)
        hdu.data = np.stack([chan, chan, chan])
        fp = tdir / f"{name}.fits"
        hdu.writeto(fp, overwrite=True)
        pp = tdir / f"{name}_preview.png"
        crop_json = None
        north_up_deg = None
        if crop is not None:
            from seestack.previewcrop import PreviewCrop, crop_pixel_box
            from seestack.render.thumbnail import preview_grid_size

            pc = PreviewCrop(*crop)
            full = Image.open(io.BytesIO(render_stack_png(fp, max_width=w)))
            box = crop_pixel_box(pc, w, h)
            cut = full.crop(box)
            cut = cut.resize(preview_grid_size(cut.width, cut.height), Image.BOX)
            buf = io.BytesIO()
            cut.save(buf, format="PNG")
            pp.write_bytes(buf.getvalue())
            crop_json = pc.to_json()
        elif bake_north_up:
            from seestack.render.thumbnail import orient_preview_north_up, stack_north_up_deg

            pp.write_bytes(orient_preview_north_up(render_stack_png(fp), fp))
            north_up_deg = stack_north_up_deg(fp)
        else:
            pp.write_bytes(render_stack_png(fp))
        proj = lib.open_target(safe)
        try:
            run_id = proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc=f"2026-05-{10 + len(name):02d}T00:00:00Z",
                output_basename=name, fits_path=str(fp), tiff_path=None,
                preview_path=str(pp), n_frames_used=50, canvas_h=h, canvas_w=w,
                coverage_min=1, coverage_max=3, options_json="{}",
            ))
            if north_up_deg is not None:
                proj.set_stack_preview_north_up(run_id, north_up_deg)
            if crop_json is not None:
                proj.set_stack_preview_crop(run_id, crop_json)
            return run_id
        finally:
            proj.close()
    finally:
        lib.close()


def _safe(client) -> str:
    return client.get("/api/targets").json()[0]["safe_name"]


def _star(png: bytes) -> tuple[float, float]:
    """The star's centroid in continuous picture coordinates (pixel i spans
    [i, i + 1), so its centre is i + 0.5)."""
    arr = np.asarray(Image.open(io.BytesIO(png)).convert("L"), dtype=float)
    y, x = np.unravel_index(np.argmax(arr), arr.shape)
    r = 6
    ys, xs = slice(max(0, y - r), y + r + 1), slice(max(0, x - r), x + r + 1)
    patch = arr[ys, xs] - np.median(arr)
    patch[patch < 0.3 * patch.max()] = 0
    gy, gx = np.mgrid[ys, xs]
    tot = patch.sum()
    return float((gx * patch).sum() / tot + 0.5), float((gy * patch).sum() / tot + 0.5)


def _preview(client, safe: str, run_id: int, north_up: bool = False) -> bytes:
    q = "?north_up=true" if north_up else ""
    r = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/preview{q}")
    assert r.status_code == 200
    return r.content


def _where_a_lands(body, a_xy):
    a, b, c, d, e, f = body["a"]["matrix"]
    u, v = a_xy
    return a * u + c * v + e, b * u + d * v + f


def test_one_star_lands_on_one_frame_pixel_across_a_grown_mosaic(client, solved_library):
    # The Scout's shape: a first-ever stack with two panels set aside, then the
    # grown one — different canvases, both wider than the preview's 1024 px, so
    # each preview is shrunk by its own factor.
    safe = _safe(client)
    first = _add_run(solved_library, safe, "first", w=1300, h=500, offset=(300.0, 200.0))
    now = _add_run(solved_library, safe, "now", w=2000, h=1300, offset=(0.0, 0.0))

    body = client.get(f"/api/targets/{safe}/compare-placement?a={first}&b={now}").json()
    assert body["placeable"] is True
    sa = _star(_preview(client, safe, first))
    sb = _star(_preview(client, safe, now))
    fx, fy = _where_a_lands(body, sa)
    assert abs(fx - (sb[0] + body["b"]["x"])) <= 1.0
    assert abs(fy - (sb[1] + body["b"]["y"])) <= 1.0
    # Drawn at one scale: A's 1300 canvas px are the same sky width as 1300 of
    # B's, which B's preview shows at 1024/2000.
    assert abs(body["a"]["matrix"][0] - (1300 / 1024) * (1024 / 2000)) < 0.01
    # The frame holds both pictures without clipping either.
    assert body["frame_w"] >= body["b"]["width"] and body["frame_h"] >= body["b"]["height"]


def test_the_other_way_round_the_frame_grows_to_hold_the_wider_picture(client, solved_library):
    safe = _safe(client)
    first = _add_run(solved_library, safe, "first", w=1300, h=500, offset=(300.0, 200.0))
    now = _add_run(solved_library, safe, "now", w=2000, h=1300, offset=(0.0, 0.0))

    body = client.get(f"/api/targets/{safe}/compare-placement?a={now}&b={first}").json()
    assert body["placeable"] is True
    sa = _star(_preview(client, safe, now))
    sb = _star(_preview(client, safe, first))
    fx, fy = _where_a_lands(body, sa)
    assert abs(fx - (sb[0] + body["b"]["x"])) <= 1.0
    assert abs(fy - (sb[1] + body["b"]["y"])) <= 1.0
    # B (the smaller one) is moved into the frame, not A cut off at its edge.
    assert body["b"]["x"] > 0 and body["b"]["y"] > 0
    assert body["frame_w"] > body["b"]["width"]


def test_the_north_up_view_is_the_picture_the_placement_describes(client, solved_library):
    # B is framed 30° off North and is being *shown* turned; the placement has to
    # describe those turned bytes, not the stored ones.
    safe = _safe(client)
    first = _add_run(solved_library, safe, "first", w=1300, h=500, offset=(300.0, 200.0))
    now = _add_run(solved_library, safe, "now", w=2000, h=1300, offset=(0.0, 0.0),
                   rot_deg=30.0)

    body = client.get(f"/api/targets/{safe}/compare-placement"
                      f"?a={first}&b={now}&north_up_b=true").json()
    assert body["placeable"] is True
    turned = _preview(client, safe, now, north_up=True)
    assert Image.open(io.BytesIO(turned)).size != Image.open(
        io.BytesIO(_preview(client, safe, now))).size      # it really was turned
    assert Image.open(io.BytesIO(turned)).size == (body["b"]["width"], body["b"]["height"])
    sa = _star(_preview(client, safe, first))
    sb = _star(turned)
    fx, fy = _where_a_lands(body, sa)
    assert abs(fx - (sb[0] + body["b"]["x"])) <= 1.0
    assert abs(fy - (sb[1] + body["b"]["y"])) <= 1.0


def test_a_trimmed_or_saved_north_up_preview_is_placed_by_what_it_shows(
        client, solved_library):
    # The one-click "Process target" ends with a border trim, and History can save
    # a preview turned North-up: either way the stored bytes are no longer a plain
    # downscale of the canvas, and the placement has to follow them.
    safe = _safe(client)
    first = _add_run(solved_library, safe, "first", w=1300, h=500, offset=(300.0, 200.0))
    trimmed = _add_run(solved_library, safe, "trimmed", w=2000, h=1300, offset=(0.0, 0.0),
                       crop=(0.1, 0.05, 0.9, 0.95))
    saved = _add_run(solved_library, safe, "saved", w=2000, h=1300, offset=(0.0, 0.0),
                     rot_deg=30.0, bake_north_up=True)

    sa = _star(_preview(client, safe, first))
    for b, north_up in ((trimmed, False), (saved, False), (saved, True)):
        body = client.get(f"/api/targets/{safe}/compare-placement"
                          f"?a={first}&b={b}&north_up_b={str(north_up).lower()}").json()
        assert body["placeable"] is True
        shown = _preview(client, safe, b, north_up=north_up)
        assert Image.open(io.BytesIO(shown)).size == (body["b"]["width"], body["b"]["height"])
        sb = _star(shown)
        fx, fy = _where_a_lands(body, sa)
        assert abs(fx - (sb[0] + body["b"]["x"])) <= 1.0, (b, north_up)
        assert abs(fy - (sb[1] + body["b"]["y"])) <= 1.0, (b, north_up)


def test_same_canvas_is_the_identity(client, solved_library):
    safe = _safe(client)
    one = _add_run(solved_library, safe, "one", w=900, h=600, offset=(0.0, 0.0))
    two = _add_run(solved_library, safe, "two", w=900, h=600, offset=(0.0, 0.0))

    body = client.get(f"/api/targets/{safe}/compare-placement?a={one}&b={two}").json()
    assert body["placeable"] is True
    assert np.allclose(body["a"]["matrix"], [1, 0, 0, 1, 0, 0], atol=1e-3)
    assert (body["frame_w"], body["frame_h"]) == (900, 600)


def test_no_wcs_or_no_shared_sky_is_unplaceable_not_an_error(client, solved_library):
    safe = _safe(client)
    solved = _add_run(solved_library, safe, "solved", w=900, h=600, offset=(0.0, 0.0))
    bare = _add_run(solved_library, safe, "bare", w=1200, h=600, offset=None)
    far = _add_run(solved_library, safe, "far", w=900, h=600, offset=(20000.0, 0.0),
                   star=(20400.0, 300.0))

    for a, b in ((solved, bare), (bare, solved), (solved, far)):
        r = client.get(f"/api/targets/{safe}/compare-placement?a={a}&b={b}")
        assert r.status_code == 200
        assert r.json() == {"placeable": False}


def test_an_unknown_run_is_a_404(client, solved_library):
    safe = _safe(client)
    one = _add_run(solved_library, safe, "one", w=900, h=600, offset=(0.0, 0.0))
    r = client.get(f"/api/targets/{safe}/compare-placement?a={one}&b=99999")
    assert r.status_code == 404
