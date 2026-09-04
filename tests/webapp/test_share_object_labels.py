""""Save it with the names on it" — the object labels baked into the shared JPEG.

The Target page names the catalog objects in a solved field on screen, but the
overlay is drawn in the browser: share the picture and the answer is gone. The
share JPEG grew a ``label_objects`` flag that bakes the same pins and names into
the pixels, from the same offline catalog and the same solved WCS.

What has to hold, in order:

* it actually **draws** the names, and the plain download is untouched;
* it **refuses rather than guesses** on a picture whose geometry can't be
  reconciled with the grid the pins were measured on, because a mis-plotted name
  is worse than none and there is no toggle server-side to fall back to;
* it **composes** with both geometries that *are* reconcilable: an auto-edit
  border trim, where each pin shifts into the kept rectangle, and a North-up
  turn, where every pin follows the pixels through the renderer's own transform
  (a turned share used to carry no names at all);
* the labelled file is saved under its own name, so it can't overwrite a
  sibling variant in the downloads folder.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits

from seestack.io.library import Library
from seestack.io.project import StackRunRow
from seestack.previewcrop import UNKNOWN, PreviewCrop

pytest.importorskip("PIL")

#: A wide field centred on the Orion sword, so the bundled catalog really does
#: put several named objects inside it (M42, M43, NGC 1977 …). Big enough on the
#: sky, tiny in pixels, so the render is instant.
_H, _W = 180, 240
_CDELT = 0.02          # deg/px → a ~4.8° × 3.6° field
_RA, _DEC = 83.8, -5.4


def _make_orion_run(data_root, safe: str,
                    field_rotation_deg: float = 0.0) -> tuple[int, Path, Path]:
    """Register a run whose solved field contains several catalog objects.

    ``field_rotation_deg`` tilts the CD matrix, which is what makes a run's
    ``?north_up=true`` share actually *turn* — a mount that happened to sit
    square gives nothing to correct, so a turn test on the default field would
    pass while measuring a no-op.
    """
    import math

    lib = Library.open_or_create(data_root / "library")
    try:
        tdir = lib.target_dir(lib.find_target(safe))
        rng = np.random.default_rng(11)
        cube = rng.normal(0.25, 0.02, size=(3, _H, _W)).astype(np.float32)

        theta = math.radians(field_rotation_deg)
        cos_t, sin_t = math.cos(theta), math.sin(theta)
        hdr = fits.Header()
        hdr["CTYPE1"] = "RA---TAN"
        hdr["CTYPE2"] = "DEC--TAN"
        hdr["CRPIX1"] = (_W - 1) / 2 + 1
        hdr["CRPIX2"] = (_H - 1) / 2 + 1
        hdr["CRVAL1"] = _RA
        hdr["CRVAL2"] = _DEC
        hdr["CD1_1"] = -_CDELT * cos_t
        hdr["CD1_2"] = _CDELT * sin_t
        hdr["CD2_1"] = _CDELT * sin_t
        hdr["CD2_2"] = _CDELT * cos_t
        fits_path = tdir / "orion.fits"
        fits.PrimaryHDU(data=cube, header=hdr).writeto(fits_path, overwrite=True)

        preview_path = tdir / "orion_preview.png"
        from seestack.stack.output import _write_preview_png
        _write_preview_png(preview_path, np.moveaxis(cube, 0, -1))

        proj = lib.open_target(safe)
        try:
            run_id = proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc="2026-05-01T00:00:00Z",
                output_basename="orion", fits_path=str(fits_path), tiff_path=None,
                preview_path=str(preview_path), n_frames_used=9,
                canvas_h=_H, canvas_w=_W, coverage_min=9, coverage_max=9,
                options_json="{}",
            ))
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
        return int(run_id), fits_path, preview_path
    finally:
        lib.close()


def _safe(client) -> str:
    return client.get("/api/targets").json()[0]["safe_name"]


def _jpeg(client, safe: str, run_id: int, query: str = ""):
    r = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/jpeg{query}")
    assert r.status_code == 200, r.text
    return r


def _pixels(data: bytes) -> np.ndarray:
    from io import BytesIO

    from PIL import Image

    with Image.open(BytesIO(data)) as img:
        return np.asarray(img.convert("RGB"), dtype=np.int16)


# ---- it draws them ------------------------------------------------------

def test_the_field_really_does_contain_catalog_objects(client, solved_library):
    """Guard for everything below: if this scene had no named object in it, a
    "labelled == plain" assertion would pass for the wrong reason."""
    from webapp.routers.stack import _object_labels_for_run

    safe = _safe(client)
    _run_id, fits_path, _preview = _make_orion_run(solved_library, safe)
    labels = _object_labels_for_run(str(fits_path), (), None)
    assert len(labels.labels) >= 2, labels
    # And they are ordered most-notable-first, so the drawing hands out its
    # limited room to the objects the picture is actually about.
    notability = [lab.notability for lab in labels.labels]
    assert notability == sorted(notability)


def test_the_labelled_share_differs_from_the_plain_one(client, solved_library):
    safe = _safe(client)
    run_id, _fits_path, _preview = _make_orion_run(solved_library, safe)
    plain = _jpeg(client, safe, run_id).content
    labelled = _jpeg(client, safe, run_id, "?label_objects=true").content
    assert plain != labelled
    a, b = _pixels(plain), _pixels(labelled)
    assert a.shape == b.shape, "labels are marks on the picture, not a frame round it"
    assert np.abs(a - b).sum() > 0


def test_the_plain_download_is_byte_for_byte_unchanged(client, solved_library):
    """The flag is opt-in: every existing surface embeds the bare URL and must
    get exactly the bytes it got before."""
    safe = _safe(client)
    run_id, _fits_path, _preview = _make_orion_run(solved_library, safe)
    assert (_jpeg(client, safe, run_id).content
            == _jpeg(client, safe, run_id, "?label_objects=false").content)


def test_the_labelled_file_is_saved_under_its_own_name(client, solved_library):
    """So it can't silently overwrite the plain (or scale, or keepsake) variant
    in the downloads folder — the same reason those have their own suffixes."""
    safe = _safe(client)
    run_id, _fits_path, _preview = _make_orion_run(solved_library, safe)
    r = _jpeg(client, safe, run_id, "?label_objects=true")
    assert "orion_labelled.jpg" in r.headers["content-disposition"]


def test_labels_compose_with_the_keepsake_matte(client, solved_library):
    """The keepsake mats the picture on a dark card. Labels are drawn on the
    picture *first*, so a framed keepsake carries them too rather than one
    overlay cancelling the other."""
    safe = _safe(client)
    run_id, _fits_path, _preview = _make_orion_run(solved_library, safe)
    keepsake = _jpeg(client, safe, run_id, "?keepsake=true").content
    both = _jpeg(client, safe, run_id, "?keepsake=true&label_objects=true").content
    assert keepsake != both
    # The keepsake wins the *filename* (it is the more specific variant), so the
    # two can't be told apart by name — which is exactly why the bytes must differ.
    assert _pixels(keepsake).shape == _pixels(both).shape


# ---- it refuses rather than guesses --------------------------------------

def test_a_turned_picture_keeps_its_names_and_moves_them_with_the_pixels(
        client, solved_library):
    """The pins are measured on the un-rotated FITS grid, and a rotate-with-expand
    moves every pixel *and* grows the canvas — so a North-up share used to carry
    no names at all, which made the two most-wanted marks on a shared file
    (North-up framing and object names) mutually exclusive. The anchors now
    follow the turn through the renderer's own transform, so the names travel
    with it.

    Verified against ground truth rather than against a second copy of the
    formula: each object's un-turned pixel is planted in a marker image, that
    image is put through ``rotate_image_north_up`` — the function the picture
    itself goes through — and the label has to land where the marker did. The
    tolerance is a pixel because a marker can only be planted on a whole pixel
    while a catalog object sits between them; the sub-pixel exactness of the
    transform is pinned in ``tests/test_object_labels.py``, on positions chosen
    to be integers. A wrong sign or a dropped axis misses by tens of pixels.
    """
    import numpy as np

    from seestack.render.orient import rotate_image_north_up
    from webapp.routers.stack import _object_labels_for_run

    safe = _safe(client)
    _run_id, fits_path, _preview = _make_orion_run(solved_library, safe)
    flat = _object_labels_for_run(str(fits_path), (), None)
    assert flat                                                   # the control
    turned = _object_labels_for_run(str(fits_path), (31.5,), None)
    assert {lab.text for lab in turned.labels} == {lab.text for lab in flat.labels}

    by_text = {lab.text: lab for lab in turned.labels}
    for lab in flat.labels:
        marker = np.zeros((_H, _W, 3), dtype=np.float32)
        marker[int(round(lab.y * _H)), int(round(lab.x * _W))] = 1.0
        rot = rotate_image_north_up(marker, 31.5)
        plane = rot[..., 0]
        hit = plane > plane.max() * 0.3
        ys, xs = np.nonzero(hit)
        wts = plane[hit]
        gx = (xs * wts).sum() / wts.sum()
        gy = (ys * wts).sum() / wts.sum()
        moved = by_text[lab.text]
        assert moved.x * rot.shape[1] == pytest.approx(gx, abs=1.0)
        assert moved.y * rot.shape[0] == pytest.approx(gy, abs=1.0)


def test_the_north_up_share_actually_carries_the_names(client, solved_library):
    """End-to-end, through the endpoint, on a field whose mount really was
    turned: asking for both at once has to produce a turned picture with names
    on it, not a turned picture with the names quietly dropped."""
    safe = _safe(client)
    run_id, _fits_path, _preview = _make_orion_run(
        solved_library, safe, field_rotation_deg=28.0)
    plain = _jpeg(client, safe, run_id).content
    turned = _jpeg(client, safe, run_id, "?north_up=true").content
    # The control: this field really does get turned, so the assertion below is
    # about a rotated picture rather than an accidental no-op.
    assert _pixels(turned).shape != _pixels(plain).shape
    both = _jpeg(client, safe, run_id,
                 "?north_up=true&label_objects=true").content
    assert turned != both, "the names have to reach a North-up share"
    a, b = _pixels(turned), _pixels(both)
    assert a.shape == b.shape, "labels are marks on the picture, not a frame"
    assert np.abs(a - b).sum() > 0


def test_a_preview_a_past_save_turned_still_carries_its_names(
        client, solved_library):
    """The other way a picture arrives turned: History's "Adjust → North up →
    Save" overwrites the stored preview with a rotated render and records the
    angle. Nothing in *this* request turns anything, so the share has to seed
    the pins with what the bytes already carry — the same blind spot the scale
    bar and the rose had before v0.309.0."""
    from seestack.io.library import Library as _Library
    from webapp.routers.stack import _object_labels_for_run

    safe = _safe(client)
    run_id, fits_path, _preview = _make_orion_run(
        solved_library, safe, field_rotation_deg=28.0)
    saved = client.post(f"/api/targets/{safe}/stack-runs/{run_id}/preview",
                        json={"stretch": 0.5, "black": 0.35, "north_up": True})
    assert saved.status_code == 200, saved.text

    lib = _Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target(safe)
        try:
            run = next(r for r in proj.iter_stack_runs() if r.id == run_id)
        finally:
            proj.close()
    finally:
        lib.close()
    baked = run.preview_north_up_deg
    assert baked, "the fixture's save really did bake a turn in"

    # The pins have to be placed on the turned grid the stored bytes are on…
    turned = _object_labels_for_run(str(fits_path), (baked,), None)
    assert turned
    flat = _object_labels_for_run(str(fits_path), (), None)
    assert {lab.text for lab in turned.labels} == {lab.text for lab in flat.labels}
    assert [(lab.x, lab.y) for lab in turned.labels] != [
        (lab.x, lab.y) for lab in flat.labels]

    # …and the endpoint has to use them, with no `north_up` asked for at all.
    plain = _jpeg(client, safe, run_id).content
    labelled = _jpeg(client, safe, run_id, "?label_objects=true").content
    assert plain != labelled
    assert _pixels(plain).shape == _pixels(labelled).shape


def test_an_unreconcilable_preview_geometry_draws_nothing(client, solved_library):
    """A preview whose geometry can't be matched to the canvas refuses, exactly
    as the scale bar does."""
    from webapp.routers.stack import _object_labels_for_run

    safe = _safe(client)
    _run_id, fits_path, _preview = _make_orion_run(solved_library, safe)
    assert not _object_labels_for_run(str(fits_path), (), UNKNOWN)


def test_a_run_with_no_fits_has_no_labels_and_no_error(client, solved_library):
    from webapp.routers.stack import _object_labels_for_run

    assert not _object_labels_for_run(None, (), None)
    assert not _object_labels_for_run("/nowhere/at/all.fits", (), None)


# ---- the geometry that *is* reconcilable ---------------------------------

def test_a_cropped_preview_shifts_its_pins_into_the_trim(client, solved_library):
    """An auto-edit border trim is the one geometry that composes: the picture
    shows a rectangle of the canvas, so each pin is re-based onto it and an
    object the trim cut away drops out instead of landing on the wrong pixel."""
    from webapp.routers.stack import _object_labels_for_run

    safe = _safe(client)
    _run_id, fits_path, _preview = _make_orion_run(solved_library, safe)
    full = _object_labels_for_run(str(fits_path), (), None)
    # Keep the middle half of the canvas.
    crop = PreviewCrop(x0=0.25, y0=0.25, x1=0.75, y1=0.75)
    trimmed = _object_labels_for_run(str(fits_path), (), crop)

    kept = {lab.text for lab in trimmed.labels}
    assert kept, "the middle of an Orion field should still hold a named object"
    assert kept <= {lab.text for lab in full.labels}
    by_text = {lab.text: lab for lab in full.labels}
    for lab in trimmed.labels:
        before = by_text[lab.text]
        # Re-based onto the visible rectangle: a fraction measured on the canvas
        # maps to (f - 0.25) / 0.5 on a picture showing its middle half.
        assert lab.x == pytest.approx((before.x - 0.25) / 0.5, abs=1e-6)
        assert lab.y == pytest.approx((before.y - 0.25) / 0.5, abs=1e-6)
        assert 0.0 <= lab.x <= 1.0 and 0.0 <= lab.y <= 1.0


def test_the_shared_keepsake_carries_the_marks_and_the_names_together(
        client, solved_library):
    """The share meant for other people. A scale bar, a compass and the names of
    what's in the field are what make a picture read as a real astrophoto to
    someone who wasn't there — and all three compose in one request, each a
    clean no-op on a run that can't supply it."""
    safe = _safe(client)
    run_id, _fits_path, _preview = _make_orion_run(solved_library, safe)
    plain_keepsake = _jpeg(client, safe, run_id, "?keepsake=true").content
    everything = _jpeg(
        client, safe, run_id,
        "?keepsake=true&scale=true&label_objects=true").content
    marks_only = _jpeg(client, safe, run_id, "?keepsake=true&scale=true").content
    assert len({plain_keepsake, marks_only, everything}) == 3, (
        "each overlay has to actually add something of its own")
    assert _pixels(everything).shape == _pixels(marks_only).shape


def test_a_name_is_never_left_buried_under_the_sky_marks(client, solved_library):
    """The marks are drawn *after* the names, so a collision is silent: the bar
    or the rose simply covers a name nobody can then read. The drawing is handed
    the boxes the marks will occupy (`skymarks.mark_zones`) so it routes the chip
    elsewhere — or drops it — instead."""
    import numpy as np
    from PIL import Image

    from seestack.objectlabels import ObjectLabel, ObjectLabels, draw_object_labels
    from seestack.skymarks import SkyDirections, SkyMarks, mark_zones

    img = Image.new("RGB", (600, 450), (8, 8, 8))
    marks = SkyMarks(bar_px=140.0, bar_label="15'",
                     directions=SkyDirections(north_deg=104.0, east_deg=194.0))
    zones = mark_zones(600, 450, marks)
    # Two objects planted exactly under the two marks.
    labels = ObjectLabels((
        ObjectLabel("Under the bar", 0.10, 0.05, 0.95),
        ObjectLabel("Under the rose", 0.90, 0.05, 0.96),
    ))
    out = draw_object_labels(img, labels, avoid=zones)
    diff = np.abs(np.asarray(out, dtype=np.int16)
                  - np.asarray(img, dtype=np.int16)).sum(axis=2)
    ys, xs = np.nonzero(diff)
    for x0, y0, x1, y1 in zones:
        inside = (xs >= x0) & (xs <= x1) & (ys >= y0) & (ys <= y1)
        # Only a dot may remain inside a zone — it never moves, by design — so
        # what's left there must be far too small to be a name.
        assert int(inside.sum()) < 200, (x0, y0, x1, y1, int(inside.sum()))
