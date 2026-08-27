"""A preview saved *North-up* has to be followed by everything that places it.

History's "Adjust" can overwrite a run's stored preview with a North-up-rotated
render. The Sky map reads those same bytes — and used to describe them with the
**un-rotated** canvas: an un-rotated coverage mask keying the transparency, and a
tile WCS built from the un-rotated (and, on a 90° save, differently-shaped) grid.
So an irregular mosaic showed its footprint in the wrong place, on a tile placed
at the wrong orientation. These tests pin the rotation being recorded and both
halves following it.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits

from seestack.io.library import Library
from seestack.io.project import StackRunRow

pytest.importorskip("PIL")

#: The canvas tilt that makes the North-up correction an exact 90° step, so the
#: rotation is lossless (``np.rot90``) and the footprint comparison below can be
#: exact rather than fuzzy — and the canvas is non-square, so the save swaps the
#: picture's width and height, which is the shape the placement bug is worst on.
_TILT_DEG = 90.0
_H, _W = 30, 40


def _make_lopsided_mosaic_run(data_root, safe: str) -> tuple[str, Path]:
    """Register a run whose FITS has an L-shaped covered footprint and a tilted
    celestial WCS — a mosaic that both *has* a footprint to misplace and *needs*
    a North-up correction."""
    lib = Library.open_or_create(data_root / "library")
    try:
        tdir = lib.target_dir(lib.find_target(safe))
        cube = np.full((3, _H, _W), np.nan, dtype=np.float32)
        cube[:, :20, :24] = 0.8               # the L: a tall-left block…
        cube[:, 20:, :12] = 0.8               # …with a narrower foot

        th = np.radians(_TILT_DEG)
        cdelt = 0.001
        hdr = fits.Header()
        hdr["CTYPE1"] = "RA---TAN"
        hdr["CTYPE2"] = "DEC--TAN"
        hdr["CRPIX1"] = (_W - 1) / 2 + 1
        hdr["CRPIX2"] = (_H - 1) / 2 + 1
        hdr["CRVAL1"] = 150.0
        hdr["CRVAL2"] = 20.0
        hdr["CD1_1"] = -cdelt * np.cos(th)
        hdr["CD1_2"] = cdelt * np.sin(th)
        hdr["CD2_1"] = cdelt * np.sin(th)
        hdr["CD2_2"] = cdelt * np.cos(th)

        fits_path = tdir / "mosaic.fits"
        fits.PrimaryHDU(data=cube, header=hdr).writeto(fits_path, overwrite=True)
        preview_path = tdir / "mosaic_preview.png"
        preview_path.write_bytes(b"\x89PNG\r\n\x1a\n")   # overwritten by the save

        proj = lib.open_target(safe)
        try:
            run_id = proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc="2026-05-01T00:00:00Z",
                output_basename="mosaic", fits_path=str(fits_path), tiff_path=None,
                preview_path=str(preview_path), n_frames_used=3,
                canvas_h=_H, canvas_w=_W, coverage_min=0, coverage_max=3,
                options_json="{}",
            ))
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
        return str(run_id), preview_path
    finally:
        lib.close()


def _recorded_north_up(data_root, safe: str, run_id: str) -> float | None:
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            run = next(r for r in proj.iter_stack_runs() if r.id == int(run_id))
            return run.preview_north_up_deg
        finally:
            proj.close()
    finally:
        lib.close()


def _fits_path_of(data_root, safe: str, run_id: str) -> str:
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            return next(
                r for r in proj.iter_stack_runs() if r.id == int(run_id)).fits_path
        finally:
            proj.close()
    finally:
        lib.close()


def _save_preview(client, safe: str, run_id: str, *, north_up: bool):
    return client.post(
        f"/api/targets/{safe}/stack-runs/{run_id}/preview",
        json={"stretch": 0.5, "black": 0.0, "north_up": north_up},
    )


def test_north_up_save_records_the_rotation_it_applied(client, solved_library):
    """The angle is written on the run — and *cleared* when the picture is saved
    again without the toggle, so nothing is left following a ghost rotation."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id, _ = _make_lopsided_mosaic_run(solved_library, safe)

    assert _recorded_north_up(solved_library, safe, run_id) is None

    r = _save_preview(client, safe, run_id, north_up=True)
    assert r.status_code == 200
    assert r.json()["north_up_deg"] == pytest.approx(90.0, abs=1e-6)
    assert _recorded_north_up(solved_library, safe, run_id) == pytest.approx(
        90.0, abs=1e-6)

    assert _save_preview(client, safe, run_id, north_up=False).status_code == 200
    assert _recorded_north_up(solved_library, safe, run_id) == 0.0


def test_sky_overlay_alpha_follows_a_north_up_saved_picture(client, solved_library):
    """The transparent footprint must land where the *visible* picture has data.

    The bug: the coverage mask comes off the un-rotated FITS, so on a North-up
    save it was stretched onto a rotated picture — half the pixels' alpha from
    the wrong place. The correction here is an exact 90° step, so ground truth is
    plain ``np.rot90`` (numpy, not our rotation helpers)."""
    from PIL import Image

    from seestack.render.thumbnail import stack_coverage_mask

    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id, preview_path = _make_lopsided_mosaic_run(solved_library, safe)
    fits_path = _fits_path_of(solved_library, safe, run_id)

    # The picture *before* the North-up save, to prove the save turned it.
    assert _save_preview(client, safe, run_id, north_up=False).status_code == 200
    plain_rgb = np.asarray(Image.open(preview_path).convert("RGB"))

    r = _save_preview(client, safe, run_id, north_up=True)
    assert r.json()["north_up_deg"] == pytest.approx(90.0, abs=1e-6)  # → k = 1
    assert np.array_equal(np.asarray(Image.open(preview_path).convert("RGB")),
                          np.rot90(plain_rgb, k=1))

    resp = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/sky-overlay")
    assert resp.status_code == 200
    im = Image.open(BytesIO(resp.content))
    assert im.mode == "RGBA"
    assert im.size == (_H, _W)            # the 90° save swapped width and height
    alpha = np.asarray(im)[:, :, 3]

    mask = stack_coverage_mask(fits_path)
    expected = np.rot90(mask, k=1)        # the footprint the picture now has
    assert expected.any() and not expected.all()   # genuinely irregular
    assert np.array_equal(alpha == 255, expected)
    assert np.array_equal(alpha == 0, ~expected)

    # …and the un-rotated mask (what the endpoint used to composite) really does
    # disagree with it, so this isn't a vacuous assertion.
    stale = np.asarray(
        Image.fromarray(mask.astype(np.uint8) * 255, mode="L").resize(
            im.size, Image.NEAREST)) > 127
    assert (stale != expected).mean() > 0.2


def test_sky_overlay_is_unchanged_for_an_ordinary_run(client, solved_library):
    """No North-up save → the overlay keys its alpha off the plain, un-rotated
    coverage mask exactly as it always did."""
    from PIL import Image

    from seestack.render.thumbnail import stack_coverage_mask

    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id, _ = _make_lopsided_mosaic_run(solved_library, safe)
    assert _save_preview(client, safe, run_id, north_up=False).status_code == 200

    before = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/sky-overlay")
    assert before.status_code == 200
    im = Image.open(BytesIO(before.content))
    assert im.size == (_W, _H)
    mask = stack_coverage_mask(_fits_path_of(solved_library, safe, run_id))
    assert np.array_equal(np.asarray(im)[:, :, 3] == 255, mask)


def test_sky_places_a_north_up_tile_on_the_grid_it_actually_has(client, solved_library):
    """The map's tile WCS has to describe the rotated preview, not the canvas the
    pixels no longer sit on — otherwise the picture is confidently misplaced."""
    from astropy.io import fits as _fits

    from seestack.io.wcs_io import celestial_wcs_from_fits, wcs_from_text

    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id, preview_path = _make_lopsided_mosaic_run(solved_library, safe)
    assert _save_preview(client, safe, run_id, north_up=True).status_code == 200

    images = client.get("/api/sky").json()["images"]
    img = next(i for i in images if i["run_id"] == int(run_id))
    d = img["wcs"]
    assert d is not None
    from PIL import Image
    assert (d["NAXIS1"], d["NAXIS2"]) == Image.open(preview_path).size

    hdr = _fits.Header()
    for k, v in d.items():
        hdr[k] = v
    tile_wcs = wcs_from_text(str(hdr))

    # The canvas centre's sky position must land on the rotated picture's centre.
    canvas_wcs, cw, ch = celestial_wcs_from_fits(
        _fits_path_of(solved_library, safe, run_id))
    ra, dec = (float(v) for v in canvas_wcs.all_pix2world((cw - 1) / 2,
                                                          (ch - 1) / 2, 0))
    x, y = (float(v) for v in tile_wcs.all_world2pix(ra, dec, 0))
    assert abs(x - (d["NAXIS1"] - 1) / 2) < 1.0
    assert abs(y - (d["NAXIS2"] - 1) / 2) < 1.0

    # A 90° save swaps the picture's axes, so the tile's on-sky box must swap too
    # — the old code reported the un-rotated canvas's box here.
    assert img["width_deg"] == pytest.approx(_H * 0.001, rel=1e-6)
    assert img["height_deg"] == pytest.approx(_W * 0.001, rel=1e-6)
