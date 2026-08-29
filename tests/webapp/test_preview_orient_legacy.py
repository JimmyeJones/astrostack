"""A preview saved North-up *before* the angle column existed is still followed.

``stack_runs.preview_north_up_deg`` records what History's "Adjust → North up →
Save" baked into the stored preview. The column arrived in v0.288 and is written
only by that save — so on an install upgraded onto this build, a run somebody
saved North-up earlier carries a rotation with a ``NULL`` angle, and every reader
used to treat that as "not rotated": the Sky map placed the tile on the
un-rotated canvas, its alpha came off an un-rotated mask, and History drew its
object pins and scale bar on a picture that had been turned under them.

The rotation is recoverable rather than guessable — the save is the only thing
that rotates a stored preview, and its angle is a deterministic function of the
run's own WCS — so :mod:`webapp.preview_orient` *checks* the stored PNG's
dimensions instead of assuming. These tests pin both halves: the legacy run is
healed, and an ordinary run is untouched.
"""

from __future__ import annotations

from io import BytesIO

import numpy as np
import pytest
from PIL import Image

from seestack.io.library import Library
from webapp.preview_orient import baked_north_up_deg, recovered_north_up_deg

from .test_sky_north_up import (
    _H,
    _make_lopsided_mosaic_run,
    _save_preview,
)


def _run_row(data_root, safe: str, run_id: str):  # noqa: ANN202
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            return next(r for r in proj.iter_stack_runs() if r.id == int(run_id))
        finally:
            proj.close()
    finally:
        lib.close()


def _forget_the_angle(data_root, safe: str, run_id: str) -> None:
    """Put the run back in the state a pre-v0.288 install left it in: rotated
    pixels on disk, no recorded angle."""
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            assert proj.set_stack_preview_north_up(int(run_id), None)
        finally:
            proj.close()
    finally:
        lib.close()


def _legacy_north_up_run(client, solved_library, safe: str) -> str:
    """A run whose stored preview really is rotated 90°, with a NULL angle."""
    run_id, _preview = _make_lopsided_mosaic_run(solved_library, safe)
    r = _save_preview(client, safe, run_id, north_up=True)
    assert r.status_code == 200
    assert r.json()["north_up_deg"] == pytest.approx(90.0, abs=1e-6)
    _forget_the_angle(solved_library, safe, run_id)
    return run_id


def test_a_rotation_nobody_recorded_is_recovered_from_the_stored_pixels(
        client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _legacy_north_up_run(client, solved_library, safe)

    run = _run_row(solved_library, safe, run_id)
    assert run.preview_north_up_deg is None          # the pre-column state
    assert baked_north_up_deg(run) == pytest.approx(90.0, abs=1e-6)


def test_an_ordinary_run_is_untouched_and_costs_no_guess(client, solved_library):
    """The no-regression half. A preview nobody ever saved North-up sits on the
    plain canvas grid, so the check answers 0.0 without inventing anything."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id, _preview = _make_lopsided_mosaic_run(solved_library, safe)
    assert _save_preview(client, safe, run_id, north_up=False).status_code == 200
    _forget_the_angle(solved_library, safe, run_id)

    run = _run_row(solved_library, safe, run_id)
    assert recovered_north_up_deg(run) == 0.0
    assert baked_north_up_deg(run) == 0.0


def test_a_recorded_angle_always_wins_including_an_explicit_zero(
        client, solved_library):
    """An explicit 0.0 is a *statement* that the bytes are on the canvas grid —
    the one-click auto-edit writes it after rewriting a preview an older save had
    turned. It must never be second-guessed by the recovery."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _legacy_north_up_run(client, solved_library, safe)
    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target(safe)
        try:
            assert proj.set_stack_preview_north_up(int(run_id), 0.0)
        finally:
            proj.close()
    finally:
        lib.close()

    run = _run_row(solved_library, safe, run_id)
    assert recovered_north_up_deg(run) == pytest.approx(90.0, abs=1e-6)  # it could
    assert baked_north_up_deg(run) == 0.0                                # it doesn't


def test_a_cropped_preview_makes_no_claim(client, solved_library):
    """An auto-edit border trim leaves the preview on neither grid, so the
    arithmetic can't speak and we stay with today's answer."""
    from seestack.previewcrop import make_crop, preview_crop_json

    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _legacy_north_up_run(client, solved_library, safe)
    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target(safe)
        try:
            assert proj.set_stack_preview_crop(
                int(run_id), preview_crop_json(make_crop(0.05, 0.05, 0.95, 0.95)))
        finally:
            proj.close()
    finally:
        lib.close()

    assert recovered_north_up_deg(_run_row(solved_library, safe, run_id)) == 0.0


def test_the_sky_overlay_alpha_follows_a_legacy_north_up_save(client, solved_library):
    """End to end: the transparent footprint lands where the *visible* picture
    has data, even though nothing recorded the turn. Fails before the recovery —
    the mask came off the un-rotated FITS and was stretched onto rotated pixels."""
    from seestack.render.thumbnail import stack_coverage_mask

    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _legacy_north_up_run(client, solved_library, safe)
    fits_path = _run_row(solved_library, safe, run_id).fits_path

    resp = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/sky-overlay")
    assert resp.status_code == 200
    im = Image.open(BytesIO(resp.content))
    assert im.mode == "RGBA"
    assert im.size[0] == _H                 # the 90° save swapped width and height
    alpha = np.asarray(im)[:, :, 3]

    expected = np.rot90(stack_coverage_mask(fits_path), k=1)
    assert expected.any() and not expected.all()      # genuinely irregular
    assert np.array_equal(alpha == 255, expected)


def test_history_stops_drawing_pins_on_a_picture_an_old_save_turned(
        client, solved_library):
    """The run listing reports the recovered angle, which is what suppresses
    History's object pins and scale bar on a rotated stored preview."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _legacy_north_up_run(client, solved_library, safe)

    runs = client.get(f"/api/targets/{safe}/stack-runs").json()
    row = next(r for r in runs if r["id"] == int(run_id))
    assert row["preview_north_up_deg"] == pytest.approx(90.0, abs=1e-6)


def test_the_listing_still_says_nothing_for_an_ordinary_run(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id, _preview = _make_lopsided_mosaic_run(solved_library, safe)
    assert _save_preview(client, safe, run_id, north_up=False).status_code == 200
    _forget_the_angle(solved_library, safe, run_id)

    runs = client.get(f"/api/targets/{safe}/stack-runs").json()
    row = next(r for r in runs if r["id"] == int(run_id))
    assert row["preview_north_up_deg"] is None


def test_the_sky_map_places_a_legacy_north_up_run_on_its_rotated_grid(
        client, solved_library):
    """The Sky map's tile WCS has to describe the pixels the preview actually
    has. A 90° save swaps the grid, so the recovered angle changes the tile's
    reported size — which the un-recovered path got backwards."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    _legacy_north_up_run(client, solved_library, safe)

    img = client.get("/api/sky").json()["images"][0]
    assert img["wcs"] is not None
    # The canvas is 40 wide × 30 tall, so un-rotated it covers more sky across
    # than up. The 90° save swapped the picture's axes, and the tile's reported
    # extent has to swap with them — it didn't before the recovery.
    assert img["height_deg"] > img["width_deg"]
