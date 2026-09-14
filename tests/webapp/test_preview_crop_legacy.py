"""A preview that is a *crop* of its canvas, saved before the crop column existed.

``stack_runs.preview_crop_json`` records what a run's stored preview PNG shows of
its stack canvas — the border trim the one-click "Process target" auto-edit bakes
in. NULL is contractually "a plain full-canvas downscale", and every surface that
lines up with those bytes (the Sky map's tile placement and footprint mask,
History's object pins and scale bar, the rejection overlay, the wallpaper crop)
believes it.

The column is written by ``webapp.pipeline._preview_crop_json_for_recipe``, which
postdates a great many runs. Observer issue #877 (2026-09-14) measured the
consequence on the owner's own library: NULL on **all 614** runs, while 42 of the
stored PNGs reconcile to a saved crop rectangle to within a pixel. Those 42 are
placed as if they showed the whole canvas, off by the trim's offset and scale.

The fix is the same shape as the sibling North-up recovery in
:mod:`webapp.preview_orient` (see ``test_preview_orient_legacy.py``): *check* the
stored bytes instead of assuming. A plain downscale keeps the canvas's shape, so
a preview whose aspect ratio is not the canvas's is provably not one, and earns
:data:`~seestack.previewcrop.UNKNOWN` — "decline to place geometry" — which every
consumer already honours. Never a fabricated rectangle: a PNG header can disprove
the contract and cannot say which part of the canvas survived.

These tests pin all of it: the legacy cropped run is caught, and the three ways an
ordinary run could be wrongly accused are not.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from seestack.io.library import Library
from seestack.previewcrop import UNKNOWN as CROP_UNKNOWN
from seestack.previewcrop import PreviewCrop, make_crop, preview_crop_json
from webapp.preview_orient import recovered_preview_crop

from .test_preview_orient_legacy import _run_row
from .test_sky_north_up import _make_lopsided_mosaic_run, _save_preview

# The fixture canvas (``_make_lopsided_mosaic_run``) is 40 × 30, so a plain
# downscale sits on that grid at that shape. A band of it does not.
_CANVAS_AR = 40 / 30


def _rewrite_preview(run, size: tuple[int, int]) -> None:
    """Put ``size`` pixels where the run's preview PNG is, leaving every column on
    the run row alone — exactly the state a pre-column render left behind: bytes
    that are not a plain downscale, and nothing recorded that says so."""
    path = Path(run.preview_path)
    with Image.open(path) as im:
        im.load()
        im.resize(size, Image.NEAREST).save(path)


def _set_crop(data_root, safe: str, run_id: str, crop_json: str | None) -> None:
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            assert proj.set_stack_preview_crop(int(run_id), crop_json)
        finally:
            proj.close()
    finally:
        lib.close()


def _legacy_cropped_run(client, solved_library, safe: str):  # noqa: ANN202
    """A run whose stored preview really is a band of its canvas, with a NULL
    ``preview_crop_json`` — the pre-column state the observer measured."""
    run_id, _preview = _make_lopsided_mosaic_run(solved_library, safe)
    assert _save_preview(client, safe, run_id, north_up=False).status_code == 200
    run = _run_row(solved_library, safe, run_id)
    assert run.preview_crop_json is None          # the pre-column state
    _rewrite_preview(run, (36, 12))               # a 3.0 band of a 1.33 canvas
    return run_id


def test_a_crop_nobody_recorded_is_caught_from_the_stored_pixels(
        client, solved_library):
    """The core regression. Before the recovery this answered ``None`` — "a plain
    full-canvas downscale" — about a picture that is a band of its canvas."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _legacy_cropped_run(client, solved_library, safe)

    run = _run_row(solved_library, safe, run_id)
    assert run.preview_crop_json is None
    assert recovered_preview_crop(run) == CROP_UNKNOWN


def test_an_ordinary_downscale_is_untouched(client, solved_library):
    """The no-regression half, and the one that matters most: a false ``UNKNOWN``
    silently withdraws a working overlay from every ordinary run."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id, _preview = _make_lopsided_mosaic_run(solved_library, safe)
    assert _save_preview(client, safe, run_id, north_up=False).status_code == 200

    run = _run_row(solved_library, safe, run_id)
    assert recovered_preview_crop(run) is None


def test_a_preview_rendered_at_another_width_is_not_accused(
        client, solved_library):
    """Shape, not size. A preview written at some other width — an older build's
    preview cap, say — is still a faithful downscale, and the arithmetic cannot
    say otherwise. Accusing it would strip the overlay from a whole library."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id, _preview = _make_lopsided_mosaic_run(solved_library, safe)
    assert _save_preview(client, safe, run_id, north_up=False).status_code == 200
    run = _run_row(solved_library, safe, run_id)
    _rewrite_preview(run, (80, 60))               # 2× the grid, the same shape

    run = _run_row(solved_library, safe, run_id)
    assert (80 / 60) == pytest.approx(_CANVAS_AR)
    assert recovered_preview_crop(run) is None


def test_a_legacy_north_up_save_is_not_mistaken_for_a_crop(client, solved_library):
    """The other way a stored preview legitimately leaves the canvas grid. A 90°
    save *swaps* the shape, which is exactly what a crop looks like to a header —
    so the check has to ask what turn the bytes carry before accusing them."""
    from webapp.preview_orient import baked_north_up_deg

    from .test_preview_orient_legacy import _legacy_north_up_run

    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _legacy_north_up_run(client, solved_library, safe)

    run = _run_row(solved_library, safe, run_id)
    assert baked_north_up_deg(run) == pytest.approx(90.0, abs=1e-6)
    assert run.preview_crop_json is None
    # 30 × 40 against a 40 × 30 canvas: a different shape, and an innocent one.
    assert recovered_preview_crop(run) is None


def test_a_recorded_crop_always_wins(client, solved_library):
    """A written column is a statement about the bytes and is never second-guessed."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _legacy_cropped_run(client, solved_library, safe)
    assert recovered_preview_crop(
        _run_row(solved_library, safe, run_id)) == CROP_UNKNOWN   # it would

    _set_crop(solved_library, safe, run_id,
              preview_crop_json(make_crop(0.05, 0.3, 0.95, 0.7)))
    crop = recovered_preview_crop(_run_row(solved_library, safe, run_id))
    assert isinstance(crop, PreviewCrop)                          # it doesn't
    assert crop.as_tuple() == pytest.approx((0.05, 0.3, 0.95, 0.7))


def test_this_column_has_no_positive_full_canvas_state_so_the_check_always_runs(
        client, solved_library):
    """The asymmetry against the North-up angle, pinned because the whole recovery
    rests on it. ``preview_crop_json`` stores NULL for a *full-canvas* crop as
    well as for no crop, so — unlike an explicit ``0.0`` angle — the column can
    never say "I checked, and it is the whole canvas". A NULL is therefore always
    an open question, and reading the bytes is the only way to answer it."""
    assert preview_crop_json(None) is None
    assert preview_crop_json(make_crop(0.0, 0.0, 1.0, 1.0)) is None

    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _legacy_cropped_run(client, solved_library, safe)
    _set_crop(solved_library, safe, run_id,
              preview_crop_json(make_crop(0.0, 0.0, 1.0, 1.0)))

    run = _run_row(solved_library, safe, run_id)
    assert run.preview_crop_json is None
    assert recovered_preview_crop(run) == CROP_UNKNOWN


def test_history_stops_drawing_pins_on_a_picture_it_cannot_place(
        client, solved_library):
    """End to end. The run listing's ``preview_geometry_unknown`` is what
    suppresses History's object pins and scale bar; before the recovery it was
    ``False`` on exactly the runs that needed it."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _legacy_cropped_run(client, solved_library, safe)

    runs = client.get(f"/api/targets/{safe}/stack-runs").json()
    row = next(r for r in runs if r["id"] == int(run_id))
    assert row["preview_geometry_unknown"] is True


def test_the_listing_still_says_nothing_for_an_ordinary_run(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id, _preview = _make_lopsided_mosaic_run(solved_library, safe)
    assert _save_preview(client, safe, run_id, north_up=False).status_code == 200

    runs = client.get(f"/api/targets/{safe}/stack-runs").json()
    row = next(r for r in runs if r["id"] == int(run_id))
    assert row["preview_geometry_unknown"] is False


def test_the_sky_overlay_declines_rather_than_punching_the_wrong_pixels(
        client, solved_library):
    """The footprint mask comes off the un-cropped FITS. Stretched onto a band of
    that canvas it makes a confidently-wrong picture of where the data is, so the
    endpoint serves the opaque preview instead."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _legacy_cropped_run(client, solved_library, safe)

    resp = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/sky-overlay")
    assert resp.status_code == 200
    with Image.open(Path(_run_row(solved_library, safe, run_id).preview_path)) as im:
        assert im.size == (36, 12)
    # The stored preview served straight back, not an RGBA mask composed onto it.
    assert resp.content == Path(
        _run_row(solved_library, safe, run_id).preview_path).read_bytes()
