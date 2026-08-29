"""A preview the auto-edit *cropped* has to be followed by everything that places it.

The one-click "Process target" job re-renders a run's stored preview through the
Auto recipe, and Auto ends with a ``geometry.crop`` that trims a mosaic's ragged
border (``auto_crop_border``, on by default). The stored picture is then a crop of
the canvas — but nothing recorded that, so every consumer that treats the preview
as a uniform downscale of the master FITS placed its geometry on the *full*
canvas: the Sky-map coverage overlay punched its transparency through the wrong
pixels, the shared picture's scale bar was sized for a wider field than the one on
screen, and the wallpaper crop re-centred on the wrong spot.

This is the crop analogue of the North-up family (v0.288.1 → v0.290.1) and the fix
is the same shape: the writer records what it did
(``stack_runs.preview_crop_json``), and each consumer composes it.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits

from seestack.io.library import Library
from seestack.io.project import StackRunRow
from seestack.previewcrop import UNKNOWN, PreviewCrop, parse_preview_crop

pytest.importorskip("PIL")

#: A canvas big enough that the border trim is many pixels wide, small enough to
#: stack/render instantly. The covered region is an off-centre block, so the trim
#: is asymmetric — a symmetric one would hide an offset bug behind a scale bug.
_H, _W = 60, 80
_COV_X0, _COV_X1 = 16, 72       # covered columns
_COV_Y0, _COV_Y1 = 8, 52        # covered rows


def _make_trimmable_mosaic_run(data_root, safe: str) -> tuple[int, Path, Path]:
    """Register a mosaic run whose coverage map has a wide ragged border, so the
    Auto recipe really does emit a ``geometry.crop``. Returns
    ``(run_id, fits_path, preview_path)``."""
    lib = Library.open_or_create(data_root / "library")
    try:
        tdir = lib.target_dir(lib.find_target(safe))
        rng = np.random.default_rng(7)
        cube = np.full((3, _H, _W), np.nan, dtype=np.float32)
        block = rng.normal(0.25, 0.02, size=(3, _COV_Y1 - _COV_Y0,
                                             _COV_X1 - _COV_X0))
        cube[:, _COV_Y0:_COV_Y1, _COV_X0:_COV_X1] = block.astype(np.float32)

        cdelt = 0.001
        hdr = fits.Header()
        hdr["CTYPE1"] = "RA---TAN"
        hdr["CTYPE2"] = "DEC--TAN"
        hdr["CRPIX1"] = (_W - 1) / 2 + 1
        hdr["CRPIX2"] = (_H - 1) / 2 + 1
        hdr["CRVAL1"] = 150.0
        hdr["CRVAL2"] = 20.0
        hdr["CD1_1"] = -cdelt
        hdr["CD1_2"] = 0.0
        hdr["CD2_1"] = 0.0
        hdr["CD2_2"] = cdelt

        fits_path = tdir / "mosaic.fits"
        fits.PrimaryHDU(data=cube, header=hdr).writeto(fits_path, overwrite=True)
        # The sibling coverage map the trim rectangle is measured from.
        cov = np.zeros((_H, _W), dtype=np.float32)
        cov[_COV_Y0:_COV_Y1, _COV_X0:_COV_X1] = 3.0
        fits.PrimaryHDU(data=cov).writeto(
            fits_path.with_name("mosaic_coverage.fits"), overwrite=True)

        preview_path = tdir / "mosaic_preview.png"
        from seestack.stack.output import _write_preview_png
        _write_preview_png(preview_path, np.moveaxis(cube, 0, -1))

        proj = lib.open_target(safe)
        try:
            run_id = proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc="2026-05-01T00:00:00Z",
                output_basename="mosaic", fits_path=str(fits_path), tiff_path=None,
                preview_path=str(preview_path), n_frames_used=3,
                canvas_h=_H, canvas_w=_W, coverage_min=0, coverage_max=3,
                options_json="{}", is_mosaic=True,
            ))
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
        return int(run_id), fits_path, preview_path
    finally:
        lib.close()


def _run_row(data_root, safe: str, run_id: int):
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            return next(r for r in proj.iter_stack_runs() if r.id == run_id)
        finally:
            proj.close()
    finally:
        lib.close()


def _auto_edit(data_root, safe: str, run_id: int, *, auto_crop: bool = True):
    from webapp.pipeline import _auto_edit_process_run

    lib = Library.open_or_create(data_root / "library")
    try:
        return _auto_edit_process_run(lib, safe, run_id, auto_crop=auto_crop)
    finally:
        lib.close()


def _set_crop(data_root, safe: str, run_id: int, value: str | None) -> None:
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            assert proj.set_stack_preview_crop(run_id, value) is True
        finally:
            proj.close()
    finally:
        lib.close()


# ---- the writer's half --------------------------------------------------

def test_auto_edit_records_the_border_trim_it_baked_in(client, solved_library):
    """The crop the render applied is written on the run — and the stored bytes
    really are smaller than the canvas, so the record isn't describing nothing."""
    from PIL import Image

    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id, _fits_path, preview_path = _make_trimmable_mosaic_run(
        solved_library, safe)
    assert _run_row(solved_library, safe, run_id).preview_crop_json is None

    before = Image.open(preview_path).size
    assert _auto_edit(solved_library, safe, run_id) is not None

    crop = parse_preview_crop(
        _run_row(solved_library, safe, run_id).preview_crop_json)
    assert isinstance(crop, PreviewCrop), "the auto-edit's border trim went unrecorded"
    # The recorded rectangle matches the covered block the trim kept…
    assert crop.x0 == pytest.approx(_COV_X0 / _W, abs=0.03)
    assert crop.x1 == pytest.approx(_COV_X1 / _W, abs=0.03)
    assert crop.y0 == pytest.approx(_COV_Y0 / _H, abs=0.03)
    assert crop.y1 == pytest.approx(_COV_Y1 / _H, abs=0.03)
    # …and it is genuinely off-centre, so composing it can't be confused with a
    # pure rescale.
    assert abs(crop.x0 - (1.0 - crop.x1)) > 0.05
    # The stored picture really did shrink.
    after = Image.open(preview_path).size
    assert after[0] < before[0] and after[1] < before[1]


def test_an_uncropped_auto_edit_records_no_crop(client, solved_library):
    """With the owner's "let Auto trim the border" preference off, the render
    still covers the whole canvas — the column stays NULL, which is what every
    consumer has always assumed."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id, _fits_path, _preview = _make_trimmable_mosaic_run(solved_library, safe)

    assert _auto_edit(solved_library, safe, run_id, auto_crop=False) is not None
    assert _run_row(solved_library, safe, run_id).preview_crop_json is None


def test_re_rendering_without_a_trim_clears_a_recorded_crop(client, solved_library):
    """Always written, never left alone: a stale rectangle would have every
    consumer correcting for a trim that is no longer in the bytes."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id, _fits_path, _preview = _make_trimmable_mosaic_run(solved_library, safe)

    assert _auto_edit(solved_library, safe, run_id) is not None
    assert _run_row(solved_library, safe, run_id).preview_crop_json is not None
    assert _auto_edit(solved_library, safe, run_id, auto_crop=False) is not None
    assert _run_row(solved_library, safe, run_id).preview_crop_json is None


def test_saving_the_preview_from_adjust_clears_a_recorded_crop(client, solved_library):
    """History's "Adjust → Save" re-renders straight off the master FITS, so the
    new bytes cover the whole canvas again."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id, _fits_path, _preview = _make_trimmable_mosaic_run(solved_library, safe)
    assert _auto_edit(solved_library, safe, run_id) is not None
    assert _run_row(solved_library, safe, run_id).preview_crop_json is not None

    r = client.post(f"/api/targets/{safe}/stack-runs/{run_id}/preview",
                    json={"stretch": 0.5, "black": 0.0, "north_up": False})
    assert r.status_code == 200
    assert _run_row(solved_library, safe, run_id).preview_crop_json is None


def test_the_run_listing_reports_the_baked_crop(client, solved_library):
    """History draws object pins and a scale bar on the *stored preview* bytes,
    with coordinates measured on the un-cropped FITS grid — so it needs to know
    the picture it is drawing on was trimmed. The run row carries it."""
    from seestack.previewcrop import preview_crop_json

    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id, _fits_path, _preview = _make_trimmable_mosaic_run(solved_library, safe)

    def row():
        return next(r for r in client.get(f"/api/targets/{safe}/stack-runs").json()
                    if r["id"] == run_id)

    # Never processed → absent, which reads the same as "the whole canvas".
    assert row()["preview_crop"] is None
    assert row()["preview_geometry_unknown"] is False

    assert _auto_edit(solved_library, safe, run_id) is not None
    crop = parse_preview_crop(
        _run_row(solved_library, safe, run_id).preview_crop_json)
    assert isinstance(crop, PreviewCrop)
    assert row()["preview_crop"] == {
        "x0": crop.x0, "y0": crop.y0, "x1": crop.x1, "y1": crop.y1}
    assert row()["preview_geometry_unknown"] is False

    _set_crop(solved_library, safe, run_id, preview_crop_json(UNKNOWN))
    assert row()["preview_crop"] is None
    assert row()["preview_geometry_unknown"] is True


# ---- the Sky-map coverage overlay --------------------------------------

def test_sky_overlay_alpha_follows_a_cropped_picture(client, solved_library):
    """The transparent footprint must land where the *visible* picture has data.

    The bug: the coverage mask comes off the un-cropped FITS, so it was stretched
    across a cropped picture — the mosaic's ragged edge drawn over the middle of
    the image."""
    from PIL import Image

    from seestack.previewcrop import crop_pixel_box
    from seestack.render.thumbnail import stack_coverage_mask

    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id, fits_path, preview_path = _make_trimmable_mosaic_run(
        solved_library, safe)
    assert _auto_edit(solved_library, safe, run_id) is not None
    crop = parse_preview_crop(
        _run_row(solved_library, safe, run_id).preview_crop_json)
    assert isinstance(crop, PreviewCrop)

    resp = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/sky-overlay")
    assert resp.status_code == 200
    im = Image.open(BytesIO(resp.content))
    assert im.mode == "RGBA"
    assert im.size == Image.open(preview_path).size
    alpha = np.asarray(im)[:, :, 3]

    mask = stack_coverage_mask(fits_path)
    x0, y0, x1, y1 = crop_pixel_box(crop, mask.shape[1], mask.shape[0])
    expected = np.asarray(
        Image.fromarray((mask[y0:y1, x0:x1].astype(np.uint8) * 255), mode="L")
        .resize(im.size, Image.NEAREST)) > 127
    assert np.array_equal(alpha > 127, expected)

    # …and the *un-cropped* mask (what the endpoint used to composite) really
    # does disagree, so this isn't a vacuous assertion.
    stale = np.asarray(
        Image.fromarray(mask.astype(np.uint8) * 255, mode="L").resize(
            im.size, Image.NEAREST)) > 127
    assert (stale != expected).mean() > 0.1


def test_sky_overlay_is_unchanged_for_an_ordinary_run(client, solved_library):
    """No recorded crop → the alpha comes off the plain, un-cropped coverage mask
    exactly as it always did."""
    from PIL import Image

    from seestack.render.thumbnail import stack_coverage_mask

    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id, fits_path, _preview = _make_trimmable_mosaic_run(solved_library, safe)

    resp = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/sky-overlay")
    assert resp.status_code == 200
    im = Image.open(BytesIO(resp.content))
    assert im.size == (_W, _H)
    assert np.array_equal(np.asarray(im)[:, :, 3] == 255,
                          stack_coverage_mask(fits_path))


def test_sky_overlay_declines_transparency_on_unreconcilable_geometry(
        client, solved_library):
    """When the stored preview's geometry can't be reduced to a crop of the
    canvas there is no honest way to line the mask up — serve the opaque picture
    rather than punch holes through the wrong pixels."""
    from PIL import Image

    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id, _fits_path, preview_path = _make_trimmable_mosaic_run(
        solved_library, safe)
    from seestack.previewcrop import preview_crop_json
    _set_crop(solved_library, safe, run_id, preview_crop_json(UNKNOWN))

    resp = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/sky-overlay")
    assert resp.status_code == 200
    assert resp.content == preview_path.read_bytes()
    assert Image.open(BytesIO(resp.content)).mode == "RGB"


# ---- the Sky map's tile placement --------------------------------------

def test_sky_places_a_cropped_tile_on_the_grid_it_actually_has(client, solved_library):
    """The tile's WCS has to describe the *cropped* picture. Built from the whole
    canvas it maps the full footprint onto the trimmed pixels — the picture is
    drawn stretched and shifted by the trim's offset."""
    from astropy.io import fits as _fits
    from PIL import Image

    from seestack.io.wcs_io import celestial_wcs_from_fits, wcs_from_text
    from seestack.previewcrop import crop_pixel_box

    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id, fits_path, preview_path = _make_trimmable_mosaic_run(
        solved_library, safe)
    assert _auto_edit(solved_library, safe, run_id) is not None
    crop = parse_preview_crop(
        _run_row(solved_library, safe, run_id).preview_crop_json)
    assert isinstance(crop, PreviewCrop)

    img = next(i for i in client.get("/api/sky").json()["images"]
               if i["run_id"] == run_id)
    d = img["wcs"]
    assert d is not None
    assert (d["NAXIS1"], d["NAXIS2"]) == Image.open(preview_path).size

    hdr = _fits.Header()
    for k, v in d.items():
        hdr[k] = v
    tile_wcs = wcs_from_text(str(hdr))

    canvas_wcs, cw, ch = celestial_wcs_from_fits(fits_path)
    x0, y0, x1, y1 = crop_pixel_box(crop, cw, ch)
    # The *cropped* rectangle's centre must land on the tile's centre…
    ra, dec = (float(v) for v in canvas_wcs.all_pix2world(
        (x0 + x1 - 1) / 2.0, (y0 + y1 - 1) / 2.0, 0))
    x, y = (float(v) for v in tile_wcs.all_world2pix(ra, dec, 0))
    assert abs(x - (d["NAXIS1"] - 1) / 2) < 1.0
    assert abs(y - (d["NAXIS2"] - 1) / 2) < 1.0
    # …and the tile is reported at the trimmed size, not the canvas's.
    assert img["width_deg"] == pytest.approx((x1 - x0) * 0.001, rel=1e-6)
    assert img["height_deg"] == pytest.approx((y1 - y0) * 0.001, rel=1e-6)
    # …centred on the picture, not on the target it was trimmed away from.
    assert img["ra_deg"] == pytest.approx(ra, abs=1e-6)
    assert img["dec_deg"] == pytest.approx(dec, abs=1e-6)

    # The un-cropped canvas centre really is somewhere else, so this isn't vacuous.
    c_ra, c_dec = (float(v) for v in canvas_wcs.all_pix2world(
        (cw - 1) / 2.0, (ch - 1) / 2.0, 0))
    assert abs(c_ra - ra) > 1e-4 or abs(c_dec - dec) > 1e-4


def test_sky_tile_is_unchanged_for_an_ordinary_run(client, solved_library):
    """No recorded crop → the tile is sized, centred and placed off the full
    canvas exactly as it always was."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id, _fits_path, _preview = _make_trimmable_mosaic_run(solved_library, safe)

    target = next(t for t in client.get("/api/targets").json()
                  if t["safe_name"] == safe)
    img = next(i for i in client.get("/api/sky").json()["images"]
               if i["run_id"] == run_id)
    assert img["width_deg"] == pytest.approx(_W * 0.001, rel=1e-6)
    assert img["height_deg"] == pytest.approx(_H * 0.001, rel=1e-6)
    assert img["ra_deg"] == pytest.approx(target["ra_deg"], abs=1e-9)
    assert img["dec_deg"] == pytest.approx(target["dec_deg"], abs=1e-9)
    assert img["wcs"] is not None


def test_sky_declines_to_place_unreconcilable_geometry(client, solved_library):
    """A preview whose geometry can't be reduced to a crop of the canvas gets no
    tile WCS at all — a confidently-misplaced picture is worse than none."""
    from seestack.previewcrop import preview_crop_json

    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id, _fits_path, _preview = _make_trimmable_mosaic_run(solved_library, safe)
    _set_crop(solved_library, safe, run_id, preview_crop_json(UNKNOWN))

    img = next(i for i in client.get("/api/sky").json()["images"]
               if i["run_id"] == run_id)
    assert img["wcs"] is None
    # …but the picture still appears on the map, at the canvas footprint.
    assert img["width_deg"] == pytest.approx(_W * 0.001, rel=1e-6)


# ---- the shared picture's scale bar ------------------------------------

def _label_arcsec(label: str) -> float:
    """The angular length a baked scale-bar label claims, in arcsec (the ASCII
    form :attr:`ScaleBar.ascii_label` draws: ``30"`` / ``1'`` / ``2°``)."""
    unit = label[-1]
    value = float(label[:-1])
    return value * {'"': 1.0, "'": 60.0, "°": 3600.0}[unit]


def _implied_arcsec(marks, picture_width_px: int, picture_arcsec: float) -> float:
    """How long the drawn bar actually is on the sky, from the picture it's on."""
    return marks.bar_px / picture_width_px * picture_arcsec

def test_the_shared_scale_bar_is_sized_for_the_visible_picture(client, solved_library):
    """The bar's length is a fraction of the picture's own width. Measured against
    the *canvas* it comes out too short on a cropped picture — the same on-sky
    length covers a larger share of what's left — so a beginner reads the wrong
    size off their shared image."""
    from webapp.routers.stack import _sky_marks_for_run

    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id, fits_path, _preview = _make_trimmable_mosaic_run(solved_library, safe)
    assert _auto_edit(solved_library, safe, run_id) is not None
    crop = parse_preview_crop(
        _run_row(solved_library, safe, run_id).preview_crop_json)
    assert isinstance(crop, PreviewCrop)

    width = 400
    canvas_arcsec = _W * 3.6                       # CD = 0.001 deg/px
    full = _sky_marks_for_run(str(fits_path), width)
    cropped = _sky_marks_for_run(str(fits_path), width, 0.0, crop)
    assert full.bar_px and cropped.bar_px

    # The honest check: how long the drawn bar *is* on the sky must equal what it
    # is labelled. Un-cropped, the picture spans the whole canvas…
    assert _implied_arcsec(full, width, canvas_arcsec) == pytest.approx(
        _label_arcsec(full.bar_label), rel=0.02)
    # …cropped, it spans only the trimmed field.
    visible_arcsec = canvas_arcsec * crop.w_frac
    assert _implied_arcsec(cropped, width, visible_arcsec) == pytest.approx(
        _label_arcsec(cropped.bar_label), rel=0.02)
    assert cropped.bar_px < width          # and still fits on the picture

    # The pre-fix drawing — the canvas-sized bar laid on the cropped picture —
    # really did claim a length it didn't have, so this isn't vacuous.
    assert _implied_arcsec(full, width, visible_arcsec) != pytest.approx(
        _label_arcsec(full.bar_label), rel=0.05)

    # An unreconcilable preview draws no bar rather than a wrong one.
    assert _sky_marks_for_run(str(fits_path), width, 0.0, UNKNOWN).bar_px is None


def test_the_shared_scale_bar_is_unchanged_without_a_crop(client, solved_library):
    """The default call — every run that isn't cropped — is bit-for-bit as before."""
    from webapp.routers.stack import _sky_marks_for_run

    safe = client.get("/api/targets").json()[0]["safe_name"]
    _run_id, fits_path, _preview = _make_trimmable_mosaic_run(solved_library, safe)
    assert (_sky_marks_for_run(str(fits_path), 400, 0.0, None).bar_px
            == _sky_marks_for_run(str(fits_path), 400).bar_px)


# ---- the wallpaper crop ------------------------------------------------

def test_wallpaper_centres_on_the_target_through_the_crop(client, solved_library):
    """`wallpaper_target_pixel` maps the target's sky position onto a *uniform
    downscale* of the master; on a cropped preview it has to shift into the
    cropped rectangle first, or the wallpaper re-centres on the wrong spot."""
    from seestack.io.wcs_io import celestial_wcs_from_fits
    from seestack.previewcrop import crop_pixel_box
    from seestack.wallpaper import wallpaper_target_pixel

    safe = client.get("/api/targets").json()[0]["safe_name"]
    _run_id, fits_path, _preview = _make_trimmable_mosaic_run(solved_library, safe)
    wcs, full_w, full_h = celestial_wcs_from_fits(fits_path)

    # A sky position deliberately off the canvas centre, inside the covered block.
    ra, dec = (float(v) for v in wcs.all_pix2world(_COV_X0 + 8, _COV_Y0 + 6, 0))
    crop = PreviewCrop(_COV_X0 / _W, _COV_Y0 / _H, _COV_X1 / _W, _COV_Y1 / _H)
    x0, y0, x1, y1 = crop_pixel_box(crop, full_w, full_h)
    prev_w, prev_h = (x1 - x0) * 2, (y1 - y0) * 2   # the cropped picture, 2× up

    px = wallpaper_target_pixel(fits_path, ra, dec, prev_w, prev_h, crop)
    assert px is not None
    assert px[0] == pytest.approx((_COV_X0 + 8 - x0 + 0.5) * 2 - 0.5, abs=0.6)
    assert px[1] == pytest.approx((_COV_Y0 + 6 - y0 + 0.5) * 2 - 0.5, abs=0.6)

    # Without the crop the same call lands somewhere else entirely — the bug.
    stale = wallpaper_target_pixel(fits_path, ra, dec, prev_w, prev_h)
    assert abs(stale[0] - px[0]) > 5 or abs(stale[1] - px[1]) > 5

    # Unreconcilable geometry declines (the caller then centres on the image).
    assert wallpaper_target_pixel(fits_path, ra, dec, prev_w, prev_h, UNKNOWN) is None
    # …and the default is bit-for-bit the old behaviour.
    assert wallpaper_target_pixel(fits_path, ra, dec, prev_w, prev_h, None) == stale


def test_wallpaper_endpoint_serves_a_cropped_preview(client, solved_library):
    """End-to-end: the wallpaper still renders (and at the asked-for aspect) for a
    run whose preview the auto-edit trimmed."""
    from PIL import Image

    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id, _fits_path, _preview = _make_trimmable_mosaic_run(solved_library, safe)
    assert _auto_edit(solved_library, safe, run_id) is not None

    r = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/wallpaper",
                   params={"aspect": "phone"})
    assert r.status_code == 200
    im = Image.open(BytesIO(r.content))
    assert im.size[0] > 0 and im.size[1] > 0
