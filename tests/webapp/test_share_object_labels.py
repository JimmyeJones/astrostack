""""Save it with the names on it" — the object labels baked into the shared JPEG.

The Target page names the catalog objects in a solved field on screen, but the
overlay is drawn in the browser: share the picture and the answer is gone. The
share JPEG grew a ``label_objects`` flag that bakes the same pins and names into
the pixels, from the same offline catalog and the same solved WCS.

What has to hold, in order:

* it actually **draws** the names, and the plain download is untouched;
* it **refuses rather than guesses** on a picture whose geometry no longer
  matches the grid the pins were measured on — a turned one — because a
  mis-plotted name is worse than none, and there is no toggle server-side to
  fall back to;
* it **composes** the one geometry that *is* reconcilable: an auto-edit border
  trim, where each pin shifts into the kept rectangle;
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


def _make_orion_run(data_root, safe: str) -> tuple[int, Path, Path]:
    """Register a run whose solved field contains several catalog objects."""
    lib = Library.open_or_create(data_root / "library")
    try:
        tdir = lib.target_dir(lib.find_target(safe))
        rng = np.random.default_rng(11)
        cube = rng.normal(0.25, 0.02, size=(3, _H, _W)).astype(np.float32)

        hdr = fits.Header()
        hdr["CTYPE1"] = "RA---TAN"
        hdr["CTYPE2"] = "DEC--TAN"
        hdr["CRPIX1"] = (_W - 1) / 2 + 1
        hdr["CRPIX2"] = (_H - 1) / 2 + 1
        hdr["CRVAL1"] = _RA
        hdr["CRVAL2"] = _DEC
        hdr["CD1_1"] = -_CDELT
        hdr["CD1_2"] = 0.0
        hdr["CD2_1"] = 0.0
        hdr["CD2_2"] = _CDELT
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
    labels = _object_labels_for_run(str(fits_path), 0.0, None)
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

def test_a_turned_picture_is_shared_unlabelled_rather_than_mis_plotted(
        client, solved_library):
    """The pins are measured on the un-rotated FITS grid, and a rotate-with-expand
    moves every pixel *and* grows the canvas. Unlike the browser overlay there is
    no toggle to fall back to here, so a turned share must simply carry no names —
    never names in the wrong places."""
    from webapp.routers.stack import _object_labels_for_run

    safe = _safe(client)
    _run_id, fits_path, _preview = _make_orion_run(solved_library, safe)
    assert _object_labels_for_run(str(fits_path), 0.0, None)      # the control
    assert not _object_labels_for_run(str(fits_path), 31.5, None)


def test_an_unreconcilable_preview_geometry_draws_nothing(client, solved_library):
    """A preview whose geometry can't be matched to the canvas refuses, exactly
    as the scale bar does."""
    from webapp.routers.stack import _object_labels_for_run

    safe = _safe(client)
    _run_id, fits_path, _preview = _make_orion_run(solved_library, safe)
    assert not _object_labels_for_run(str(fits_path), 0.0, UNKNOWN)


def test_a_run_with_no_fits_has_no_labels_and_no_error(client, solved_library):
    from webapp.routers.stack import _object_labels_for_run

    assert not _object_labels_for_run(None, 0.0, None)
    assert not _object_labels_for_run("/nowhere/at/all.fits", 0.0, None)


# ---- the geometry that *is* reconcilable ---------------------------------

def test_a_cropped_preview_shifts_its_pins_into_the_trim(client, solved_library):
    """An auto-edit border trim is the one geometry that composes: the picture
    shows a rectangle of the canvas, so each pin is re-based onto it and an
    object the trim cut away drops out instead of landing on the wrong pixel."""
    from webapp.routers.stack import _object_labels_for_run

    safe = _safe(client)
    _run_id, fits_path, _preview = _make_orion_run(solved_library, safe)
    full = _object_labels_for_run(str(fits_path), 0.0, None)
    # Keep the middle half of the canvas.
    crop = PreviewCrop(x0=0.25, y0=0.25, x1=0.75, y1=0.75)
    trimmed = _object_labels_for_run(str(fits_path), 0.0, crop)

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
