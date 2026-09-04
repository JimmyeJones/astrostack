"""`GET …/stack-runs/{id}/annotations` — catalog objects inside a stack's field."""

from __future__ import annotations

import numpy as np
import pytest
from astropy.io import fits

from seestack.io.library import Library
from seestack.io.project import StackRunRow


def _add_run(data_root, safe: str, *, ra: float, dec: float, w: int, h: int,
             arcsec_per_px: float, with_wcs: bool = True,
             dec_sign: float = 1.0) -> int:
    """Register a stack run backed by a real 3-channel master FITS.

    When ``with_wcs`` the FITS header carries a TAN WCS centred on (ra, dec) —
    exactly as the stacker merges the canvas WCS into ``master.fits`` — so the
    endpoint reads the field geometry from the file, as in production.

    ``dec_sign`` picks which way up the field sits on screen, because the two
    cases answer the orientation questions differently and both are real: the
    default (+1, Dec increasing with row) draws North at the *bottom* of an image
    whose first row is the top one, so a North-up view is a 180° turn; ``-1``
    (North up, East left) is the orientation an already-oriented picture has, and
    needs no turn at all.
    """
    lib = Library.open_or_create(data_root / "library")
    try:
        tdir = lib.target_dir(lib.find_target(safe))
        fits_path = tdir / f"annot_{ra}_{w}x{h}_{dec_sign}.fits"
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
            hdr["CD2_2"] = dec_sign * arcsec_per_px / 3600.0
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
    # The scale bar is derived from the run's own WCS (3″/px × 4000 px = 3.33°
    # wide) and reported for the frontend overlay.
    sb = body["scale_bar"]
    assert sb is not None
    assert set(sb) == {"arcsec", "label", "fraction", "frame_arcmin", "moon_comparison"}
    assert 0 < sb["fraction"] <= 0.25
    assert sb["label"].endswith(("″", "′", "°"))
    assert abs(sb["frame_arcmin"] - (3.0 * w / 60.0)) < 1e-3


def test_annotations_report_where_north_and_east_point(client, solved_library):
    """The in-app overlay draws the same rose the shared JPEG bakes (v0.284.0),
    so the two can't disagree — which means the endpoint has to hand the frontend
    the *engine's* numbers rather than let it re-derive an orientation from a
    CD-matrix sign (the convention hazard the sky-atlas overlay is still gated
    on)."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    w, h = 4000, 3000
    run_id = _add_run(solved_library, safe, ra=10.68, dec=41.27, w=w, h=h,
                      arcsec_per_px=3.0)

    body = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/annotations").json()
    d = body["directions"]
    assert d is not None
    assert set(d) == {"north_deg", "east_deg"}
    # Ground truth: the *same* helper the baked share picture uses, read off the
    # same header — so this pins parity, not a re-derivation of the geometry.
    from seestack.io.wcs_io import celestial_wcs_from_fits
    from seestack.skymarks import sky_directions
    wcs, gw, gh = celestial_wcs_from_fits(_run_fits(solved_library, safe, run_id))
    expected = sky_directions(wcs, gw, gh)
    assert expected is not None
    assert abs(d["north_deg"] - expected.north_deg) < 1e-6
    assert abs(d["east_deg"] - expected.east_deg) < 1e-6
    # …and the two arms are genuinely different directions, so a rose drawn from
    # them can't collapse into one line.
    assert 30 < abs(((d["north_deg"] - d["east_deg"]) + 180) % 360 - 180) < 150


def _run_fits(data_root, safe: str, run_id: int) -> str:
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            run = next(r for r in proj.iter_stack_runs() if r.id == run_id)
            return run.fits_path
        finally:
            proj.close()
    finally:
        lib.close()


def test_annotations_empty_when_run_has_no_wcs(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _add_run(solved_library, safe, ra=10.68, dec=41.27, w=512, h=512,
                      arcsec_per_px=3.0, with_wcs=False)

    r = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/annotations")
    assert r.status_code == 200  # never 404s where the run exists
    body = r.json()
    assert body["objects"] == []
    # No WCS → no scale bar and no rose (the overlay simply doesn't offer them,
    # rather than drawing a made-up direction).
    assert body["scale_bar"] is None
    assert body["directions"] is None
    # …and no orientation to offer either, so no "North up" view toggle.
    assert body["north_up_deg"] is None


def _set_crop(data_root, safe: str, run_id: int, crop) -> None:
    """Record on the run what the one-click "Process target" auto-edit would have:
    its stored preview shows only ``crop`` of the stack canvas."""
    from seestack.previewcrop import preview_crop_json

    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            proj.set_stack_preview_crop(run_id, preview_crop_json(crop))
        finally:
            proj.close()
    finally:
        lib.close()


def test_annotations_offer_no_preview_bar_on_an_uncropped_run(client, solved_library):
    """The second bar exists only for the pictures that need it: an ordinary run's
    stored preview *is* the canvas, so `scale_bar` already describes it and the
    payload gains nothing."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _add_run(solved_library, safe, ra=10.68, dec=41.27, w=1000, h=800,
                      arcsec_per_px=3.0)

    body = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/annotations").json()
    assert body["scale_bar"] is not None
    assert body["preview_scale_bar"] is None


def test_annotations_size_a_cropped_preview_against_what_it_shows(
    client, solved_library,
):
    """A picture the auto-edit trimmed is *narrower* than the canvas, and the one
    sentence a beginner reads and shares off it — "the whole frame is about N full
    Moons wide" — is a claim about that picture. Sized on the canvas it overstates
    the field by the reciprocal of the crop (here 1/0.7 ≈ 1.43×).

    The drawn bar was already re-based client-side; the sentence was not, so the
    endpoint now hands back a second bar measured on the visible rectangle.
    """
    from seestack.io.wcs_io import arcsec_per_px, celestial_wcs_from_fits
    from seestack.previewcrop import PreviewCrop
    from seestack.scalebar import scale_bar_for

    safe = client.get("/api/targets").json()[0]["safe_name"]
    w, h = 1000, 800
    run_id = _add_run(solved_library, safe, ra=10.68, dec=41.27, w=w, h=h,
                      arcsec_per_px=3.0)
    # A 70 %-wide border trim, the shape `auto_crop_border` produces on a mosaic.
    _set_crop(solved_library, safe, run_id, PreviewCrop(0.15, 0.15, 0.85, 0.85))

    body = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/annotations").json()
    canvas = body["scale_bar"]
    shown = body["preview_scale_bar"]
    assert shown is not None
    # Ground truth: the *same* pure helper, on the same visible pixel box the
    # shared JPEG's baked marks use — parity, not a re-derivation.
    wcs, gw, gh = celestial_wcs_from_fits(_run_fits(solved_library, safe, run_id))
    expected = scale_bar_for(arcsec_per_px(wcs), round(0.7 * gw), round(0.7 * gh))
    assert expected is not None
    assert shown == expected.to_dict()
    # The claim really did shrink to the picture: ~70 % of the canvas's field, and
    # a strictly smaller Moon count than the canvas would have quoted.
    assert abs(shown["frame_arcmin"] - 0.7 * canvas["frame_arcmin"]) < 0.05
    assert shown["moon_comparison"] != canvas["moon_comparison"]
    # …and `fraction` is already a fraction of *this* picture's width, so nothing
    # downstream has to rescale it.
    assert abs(shown["fraction"] * shown["frame_arcmin"] * 60.0 - shown["arcsec"]) < 1.0


def test_annotations_offer_no_preview_bar_without_a_wcs_to_measure_it(
    client, solved_library,
):
    """A cropped run with no celestial solution has nothing to measure either
    bar from — the overlay omits both rather than inventing a field width."""
    from seestack.previewcrop import PreviewCrop

    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _add_run(solved_library, safe, ra=10.68, dec=41.27, w=512, h=512,
                      arcsec_per_px=3.0, with_wcs=False)
    _set_crop(solved_library, safe, run_id, PreviewCrop(0.1, 0.1, 0.9, 0.9))

    body = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/annotations").json()
    assert body["scale_bar"] is None
    assert body["preview_scale_bar"] is None


def test_annotations_say_how_far_north_up_would_turn_this_picture(
    client, solved_library,
):
    """The "North up" *view* toggle needs one number: would turning this picture
    actually change it? Pinned against `applied_north_up_deg` itself — the helper
    that owns the threshold-and-snap rules and that the renderer uses — so this
    asserts parity rather than re-deriving an angle from a CD matrix."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _add_run(solved_library, safe, ra=10.68, dec=41.27, w=800, h=600,
                      arcsec_per_px=3.0)

    body = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/annotations").json()
    from seestack.render.thumbnail import applied_north_up_deg
    expected = applied_north_up_deg(_run_fits(solved_library, safe, run_id))
    assert expected  # the fixture really is turned, or the test proves nothing
    assert body["north_up_deg"] is not None
    assert abs(body["north_up_deg"] - expected) < 1e-6


def test_annotations_offer_no_turn_on_an_already_north_up_picture(
    client, solved_library,
):
    """A control that visibly does nothing is worse than no control: a field that
    already sits North-up on screen gets its stored bytes handed back untouched by
    `?north_up=true` — so the endpoint reports null and the surface shows no
    toggle."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _add_run(solved_library, safe, ra=10.68, dec=41.27, w=800, h=600,
                      arcsec_per_px=3.0, dec_sign=-1.0)

    body = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/annotations").json()
    assert body["north_up_deg"] is None


def _bake_north_up(data_root, safe: str, run_id: int, deg: float) -> None:
    """Record on the run what a past "Adjust → North up → Save" would have: its
    stored preview bytes already carry ``deg`` of turn."""
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            proj.set_stack_preview_north_up(run_id, deg)
        finally:
            proj.close()
    finally:
        lib.close()


def test_annotations_offer_no_turn_on_a_picture_a_past_save_already_turned(
    client, solved_library,
):
    """The field this endpoint reports is "how far would `?north_up=true` turn
    this picture?", not "how far is this run's data from North up?" — and on a run
    whose stored preview a past "Adjust → North up → Save" already turned, those
    two answers differ.

    The renderer passes the baked angle as ``already_deg`` and applies only the
    remainder, so asking for North up hands back exactly the bytes already on
    screen — while the master FITS is still just as far from North as it ever was.
    Reporting the data's angle here put a view toggle on a picture it could not
    move.
    """
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _add_run(solved_library, safe, ra=10.68, dec=41.27, w=800, h=600,
                      arcsec_per_px=3.0)

    # Before the save is recorded the turn is real and is offered.
    from seestack.render.thumbnail import applied_north_up_deg
    turn = applied_north_up_deg(_run_fits(solved_library, safe, run_id))
    assert turn  # the fixture really is turned, or the test proves nothing
    before = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/annotations").json()
    assert before["north_up_deg"] is not None

    # …and once those very degrees are baked into the stored bytes, it is not.
    _bake_north_up(solved_library, safe, run_id, turn)
    after = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/annotations").json()
    assert after["north_up_deg"] is None
    # The rest of the payload is unchanged — this is a question about the stored
    # preview, not about the field, whose objects and rose are measured on the
    # un-rotated FITS grid either way.
    assert after["objects"] == before["objects"]
    assert after["directions"] == before["directions"]


# ---- the pins on a preview a past save turned --------------------------------

def test_no_preview_objects_on_a_run_nothing_turned(client, solved_library):
    """The extra list exists only for the geometry the browser can't reconstruct.
    An ordinary run's stored preview is the un-turned canvas, so the payload must
    be byte-for-byte what it was: three nulls, and the client keeps composing the
    crop itself."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _add_run(solved_library, safe, ra=10.68, dec=41.27, w=1000, h=800,
                      arcsec_per_px=3.0)

    body = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/annotations").json()
    assert body["objects"], "the fixture must actually contain objects"
    assert body["preview_objects"] is None
    assert body["preview_width"] is None
    assert body["preview_height"] is None


def test_a_saved_north_up_preview_gets_its_pins_placed_on_its_own_grid(
    client, solved_library,
):
    """The point of the whole thing: a picture the owner saved North-up used to
    lose "What's in it?" entirely — the app telling them it can't place labels on
    a picture its own Adjust panel made. The pins now come back, on the grid those
    stored bytes are actually on.

    Checked against ground truth, not against a second copy of the formula: plant
    each object's un-turned pixel in a marker image, put it through
    ``rotate_image_north_up`` — the function the saved preview itself went
    through — and the served coordinate has to be where the marker landed."""
    import numpy as np

    from seestack.render.orient import rotate_image_north_up

    safe = client.get("/api/targets").json()[0]["safe_name"]
    w, h = 1000, 800
    run_id = _add_run(solved_library, safe, ra=10.68, dec=41.27, w=w, h=h,
                      arcsec_per_px=3.0)
    _bake_north_up(solved_library, safe, run_id, 34.0)

    body = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/annotations").json()
    flat = {o["catalog_id"]: o for o in body["objects"]}
    turned = body["preview_objects"]
    assert turned, "a turned preview must still name what is in it"
    assert {o["catalog_id"] for o in turned} == set(flat)
    # Same fields on both lists, so one frontend type renders either.
    assert set(turned[0]) == set(body["objects"][0])

    for o in turned:
        src = flat[o["catalog_id"]]
        marker = np.zeros((h, w, 3), dtype=np.float32)
        marker[int(round(src["y_px"])), int(round(src["x_px"]))] = 1.0
        rot = rotate_image_north_up(marker, 34.0)
        assert (body["preview_height"], body["preview_width"]) == rot.shape[:2]
        plane = rot[..., 0]
        hit = plane > plane.max() * 0.3
        ys, xs = np.nonzero(hit)
        wts = plane[hit]
        assert abs(o["x_px"] - (xs * wts).sum() / wts.sum()) < 1.0
        assert abs(o["y_px"] - (ys * wts).sum() / wts.sum()) < 1.0


def test_a_turned_and_cropped_preview_composes_both_in_the_right_order(
    client, solved_library,
):
    """The pixels were cropped and *then* turned, so the pins are too: shifted
    into the kept rectangle first, and the turn applied to that rectangle rather
    than to the canvas behind it. A square turn makes the expected grid exact."""
    from seestack.previewcrop import PreviewCrop

    safe = client.get("/api/targets").json()[0]["safe_name"]
    w, h = 1000, 800
    run_id = _add_run(solved_library, safe, ra=10.68, dec=41.27, w=w, h=h,
                      arcsec_per_px=3.0)
    _set_crop(solved_library, safe, run_id, PreviewCrop(x0=0.2, y0=0.1, x1=0.8, y1=0.9))
    _bake_north_up(solved_library, safe, run_id, 90.0)

    body = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/annotations").json()
    # Crop keeps x 200…800, y 80…720 → a 600×640 picture, turned 90° → 640×600.
    assert (body["preview_width"], body["preview_height"]) == (640, 600)
    flat = {o["catalog_id"]: o for o in body["objects"]}
    assert body["preview_objects"]
    for o in body["preview_objects"]:
        src = flat[o["catalog_id"]]
        cx, cy = src["x_px"] - 200, src["y_px"] - 80
        # np.rot90 CCW once: (x, y) → (y, W−1−x) on the cropped 600×640 grid.
        assert o["x_px"] == pytest.approx(cy, abs=1e-6)
        assert o["y_px"] == pytest.approx(600 - 1 - cx, abs=1e-6)
        assert 0 <= o["x_px"] <= 640 and 0 <= o["y_px"] <= 600


def test_an_unreconcilable_preview_geometry_still_refuses(client, solved_library):
    """A preview that isn't a crop of the canvas at all can't be answered for,
    turned or not — the same stand-down the shared JPEG's labels and the scale
    bar make. Silence, never a guess."""
    from seestack.previewcrop import UNKNOWN

    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _add_run(solved_library, safe, ra=10.68, dec=41.27, w=1000, h=800,
                      arcsec_per_px=3.0)
    _set_crop(solved_library, safe, run_id, UNKNOWN)
    _bake_north_up(solved_library, safe, run_id, 34.0)

    body = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/annotations").json()
    assert body["preview_objects"] is None
    assert body["preview_width"] is None


def test_a_turned_run_with_no_wcs_answers_nothing_rather_than_erroring(
    client, solved_library,
):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _add_run(solved_library, safe, ra=10.68, dec=41.27, w=1000, h=800,
                      arcsec_per_px=3.0, with_wcs=False)
    _bake_north_up(solved_library, safe, run_id, 34.0)

    body = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/annotations").json()
    assert body["objects"] == []
    assert body["preview_objects"] is None


def test_annotations_404_for_unknown_run(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    r = client.get(f"/api/targets/{safe}/stack-runs/999999/annotations")
    assert r.status_code == 404
