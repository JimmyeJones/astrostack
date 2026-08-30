"""`GET …/stack-runs/{id}/full-res-png` — download the finished picture at full
output resolution (the direct answer to the "my downloaded picture is low-res"
owner report)."""

from __future__ import annotations

import io

import numpy as np
from astropy.io import fits
from PIL import Image

from seestack.io.library import Library
from seestack.io.project import StackRunRow


def _add_run(data_root, safe: str, *, w: int, h: int, with_fits: bool = True) -> int:
    lib = Library.open_or_create(data_root / "library")
    try:
        tdir = lib.target_dir(lib.find_target(safe))
        fits_path = None
        if with_fits:
            fits_path = tdir / f"master_{w}x{h}.fits"
            rng = np.random.default_rng(1)
            cube = (rng.random((3, h, w), dtype=np.float32) * 200.0)
            fits.PrimaryHDU(data=cube).writeto(fits_path, overwrite=True)
        proj = lib.open_target(safe)
        try:
            run_id = proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc="2026-05-01T00:00:00Z",
                output_basename="master", fits_path=str(fits_path) if fits_path else None,
                tiff_path=None, preview_path=None, n_frames_used=5,
                canvas_h=h, canvas_w=w, coverage_min=1, coverage_max=5,
                options_json="{}",
            ))
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
        return run_id
    finally:
        lib.close()


def test_full_res_png_serves_native_resolution(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    # Wider than the 1024 px preview cap so "full-res" is visibly different.
    w, h = 1600, 1200
    run_id = _add_run(solved_library, safe, w=w, h=h)

    r = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/full-res-png")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert "attachment" in r.headers.get("content-disposition", "")
    assert "master_fullres.png" in r.headers.get("content-disposition", "")
    with Image.open(io.BytesIO(r.content)) as im:
        assert im.size == (w, h)  # native output resolution, not the 1024 cap


def test_full_res_png_of_an_enormous_mosaic_is_capped_not_native(
    client, solved_library,
):
    """The download menus used to call this file "native size" — and History
    printed the canvas dimensions beside it — on every picture, including ones
    the render caps.

    This reads the **served bytes** at the production ceiling (not an injected
    one), so the claim the copy makes is pinned to what the endpoint actually
    hands over rather than to a string. A canvas past the cap comes back
    decimated; the FITS and TIFF beside it are what hold its native pixels, and
    `frontend/src/fullres.ts` now says so.
    """
    from webapp.routers.stack import _FULL_RES_PNG_MAX_LONG_EDGE as CAP

    safe = client.get("/api/targets").json()[0]["safe_name"]
    # Deliberately a *long thin* canvas: past the cap on its long edge (so the
    # decimation really fires) while staying cheap to render.
    w, h = CAP + 400, 100
    run_id = _add_run(solved_library, safe, w=w, h=h)

    r = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/full-res-png")
    assert r.status_code == 200
    with Image.open(io.BytesIO(r.content)) as im:
        assert im.size != (w, h)          # NOT native, whatever the menu says
        assert max(im.size) == CAP        # …capped exactly at the ceiling


def test_full_res_png_at_the_cap_exactly_is_still_native(client, solved_library):
    """The boundary the copy switches on: a canvas *at* the ceiling is served
    native, so the honest wording stays "native size" for it rather than warning
    about a cap that didn't bite."""
    from webapp.routers.stack import _FULL_RES_PNG_MAX_LONG_EDGE as CAP

    safe = client.get("/api/targets").json()[0]["safe_name"]
    w, h = CAP, 60
    run_id = _add_run(solved_library, safe, w=w, h=h)

    r = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/full-res-png")
    assert r.status_code == 200
    with Image.open(io.BytesIO(r.content)) as im:
        assert im.size == (w, h)


def test_full_res_png_404_when_run_has_no_fits(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _add_run(solved_library, safe, w=100, h=80, with_fits=False)
    r = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/full-res-png")
    assert r.status_code == 404


def test_full_res_png_404_for_unknown_run(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    r = client.get(f"/api/targets/{safe}/stack-runs/999999/full-res-png")
    assert r.status_code == 404


def test_full_res_png_of_a_process_target_run_serves_the_edited_recipe(
        client, solved_library):
    """A "Process target" auto-edit leaves the FITS linear and stores the finished
    look as the run's editor recipe (marked ``preview_display_space``). The full-res
    download must render *that recipe* — the picture the user clicked — not the plain
    STF of the un-edited linear master (the pre-fix behaviour served the wrong,
    darker/un-edited image)."""
    import json

    from seestack.edit.recipe import OpInstance, Recipe
    from seestack.render.thumbnail import render_preview_png_full_res
    from webapp.pipeline import render_run_recipe_fullres_png
    from webapp.routers.editor import RECIPE_META_PREFIX

    safe = client.get("/api/targets").json()[0]["safe_name"]
    w, h = 200, 160
    lib = Library.open_or_create(solved_library / "library")
    try:
        tdir = lib.target_dir(lib.find_target(safe))
        fits_path = tdir / "master_edit.fits"
        rng = np.random.default_rng(2)
        # A dim linear master, so the conservative export STF and the recipe's
        # strong stretch land visibly different pictures.
        cube = (rng.random((3, h, w), dtype=np.float32) * 0.02).astype("float32")
        fits.PrimaryHDU(data=cube).writeto(fits_path, overwrite=True)
        proj = lib.open_target(safe)
        recipe = Recipe(ops=[OpInstance(
            id="tone.stretch", params={"mode": "stf", "target_bg": 0.5},
            enabled=True)])
        try:
            run_id = proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc="2026-05-01T00:00:00Z",
                output_basename="master", fits_path=str(fits_path),
                tiff_path=None, preview_path=None, n_frames_used=5,
                canvas_h=h, canvas_w=w, coverage_min=1, coverage_max=5,
                options_json=json.dumps({"preview_display_space": True}),
            ))
            proj.set_meta(f"{RECIPE_META_PREFIX}{run_id}", recipe.to_json())
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
    finally:
        lib.close()

    r = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/full-res-png")
    assert r.status_code == 200
    got = np.asarray(Image.open(io.BytesIO(r.content)).convert("RGB"))

    want_png = render_run_recipe_fullres_png(
        str(fits_path), json.loads(recipe.to_json()))
    want = np.asarray(Image.open(io.BytesIO(want_png)).convert("RGB"))
    stf_png = render_preview_png_full_res(str(fits_path))
    stf = np.asarray(Image.open(io.BytesIO(stf_png)).convert("RGB"))

    assert got.shape == (h, w, 3)  # native resolution
    # The download IS the edited recipe render...
    assert np.array_equal(got, want)
    # ...and is visibly different from the un-edited STF the pre-fix path served.
    assert np.mean(np.abs(got.astype(int) - stf.astype(int))) > 5


def test_full_res_png_honours_a_saved_adjust_stretch(client, solved_library):
    """A run whose look the user tuned with History's "Adjust" sliders downloads
    at full resolution through the **same asinh curve** its saved preview uses —
    not the STF autostretch.

    Regression: ``set_stack_preview`` re-bakes the stored preview with
    ``render_stack_png(stretch, black)`` and records the two values on the run, so
    the thumbnail, share-JPEG and wallpaper all show the tuned look. The full-res
    download ignored those columns and re-ran ``_autostretch_for_export``, so the
    one export a user would frame or print was the only one that disagreed with
    what they saved.
    """
    from seestack.render.thumbnail import (
        render_preview_png_full_res,
        render_stack_png,
    )

    safe = client.get("/api/targets").json()[0]["safe_name"]
    w, h = 200, 160
    stretch, black = 0.7, 0.5

    lib = Library.open_or_create(solved_library / "library")
    try:
        tdir = lib.target_dir(lib.find_target(safe))
        fits_path = tdir / "master_adjusted.fits"
        # A dim linear master with a bright blob, so the conservative STF and the
        # user's dark-background asinh choice land visibly different pictures.
        rng = np.random.default_rng(3)
        cube = (rng.random((3, h, w), dtype=np.float32) * 0.004 + 0.02).astype("float32")
        cube[:, h // 2 - 8:h // 2 + 8, w // 2 - 8:w // 2 + 8] = 0.6
        fits.PrimaryHDU(data=cube).writeto(fits_path, overwrite=True)
        proj = lib.open_target(safe)
        try:
            run_id = proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc="2026-05-01T00:00:00Z",
                output_basename="master", fits_path=str(fits_path),
                tiff_path=None, preview_path=None, n_frames_used=5,
                canvas_h=h, canvas_w=w, coverage_min=1, coverage_max=5,
                options_json="{}",
            ))
            # What an Adjust + Save writes.
            proj.set_stack_preview_stretch(run_id, stretch, black)
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
    finally:
        lib.close()

    r = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/full-res-png")
    assert r.status_code == 200
    got = np.asarray(Image.open(io.BytesIO(r.content)).convert("RGB"))
    assert got.shape == (h, w, 3)  # still native resolution

    want_png = render_preview_png_full_res(
        str(fits_path), stretch=stretch, black=black)
    want = np.asarray(Image.open(io.BytesIO(want_png)).convert("RGB"))
    assert np.array_equal(got, want)

    # The saved look really is the asinh one, and really is different from the STF
    # the pre-fix path served (the whole point of the bug).
    stf = np.asarray(Image.open(io.BytesIO(
        render_preview_png_full_res(str(fits_path)))).convert("RGB"))
    assert np.mean(np.abs(got.astype(int) - stf.astype(int))) > 5
    # …and it matches the curve the stored 1024 px preview was baked with.
    preview = np.asarray(Image.open(io.BytesIO(render_stack_png(
        str(fits_path), stretch=stretch, black=black,
        max_width=8000))).convert("RGB"))
    assert np.array_equal(got, preview)


def test_full_res_png_of_an_unadjusted_run_is_unchanged(client, solved_library):
    """No saved Adjust (the columns are NULL) → the STF export is byte-for-byte
    what it always was. The stretch carry-through must be inert on every run the
    user never tuned."""
    from seestack.render.thumbnail import render_preview_png_full_res

    safe = client.get("/api/targets").json()[0]["safe_name"]
    w, h = 180, 140
    run_id = _add_run(solved_library, safe, w=w, h=h)

    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target(safe)
        try:
            run = next(r for r in proj.iter_stack_runs() if r.id == run_id)
            assert run.preview_stretch is None and run.preview_black is None
            fits_path = run.fits_path
        finally:
            proj.close()
    finally:
        lib.close()

    r = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/full-res-png")
    assert r.status_code == 200
    assert r.content == render_preview_png_full_res(fits_path)


def _add_north_up_saved_run(data_root, safe: str, *, w: int, h: int,
                            rot_deg: float = 30.0) -> int:
    """A run as History's "Adjust → North up → Save" leaves one: a canvas-grid
    master, a stored preview rendered *turned*, and the angle recorded on the row.
    """
    from astropy.wcs import WCS

    from seestack.render.thumbnail import (
        applied_north_up_deg,
        render_preview_png_full_res,
    )

    lib = Library.open_or_create(data_root / "library")
    try:
        tdir = lib.target_dir(lib.find_target(safe))
        rng = np.random.default_rng(3)
        cube = (rng.random((3, h, w), dtype=np.float32) * 200.0)
        wcs = WCS(naxis=2)
        wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
        wcs.wcs.crpix = [w / 2 + 0.5, h / 2 + 0.5]
        wcs.wcs.crval = [150.0, 20.0]
        th = np.radians(rot_deg)
        ct, st = float(np.cos(th)), float(np.sin(th))
        s = 0.001
        wcs.wcs.cd = [[-s * ct, s * st], [s * st, s * ct]]
        fits_path = tdir / f"turned_{w}x{h}.fits"
        fits.PrimaryHDU(data=cube, header=wcs.to_header()).writeto(
            fits_path, overwrite=True)
        preview_path = tdir / f"turned_{w}x{h}_preview.png"
        preview_path.write_bytes(render_preview_png_full_res(
            fits_path, max_long_edge=1024, north_up=True))

        proj = lib.open_target(safe)
        try:
            run_id = proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc="2026-05-01T00:00:00Z",
                output_basename="turned", fits_path=str(fits_path), tiff_path=None,
                preview_path=str(preview_path), n_frames_used=5,
                canvas_h=h, canvas_w=w, coverage_min=1, coverage_max=5,
                options_json="{}",
            ))
            # What the save records: the turn it just baked into those bytes.
            proj.set_stack_preview_north_up(run_id, applied_north_up_deg(fits_path))
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
        return run_id
    finally:
        lib.close()


def test_full_res_png_follows_a_preview_that_was_saved_north_up(
        client, solved_library):
    """The regression: this render starts from the *canvas-grid* FITS, while every
    other surface shows the stored preview — so on a run whose preview a past
    "Adjust → North up → Save" turned, the "Full-res PNG (native size)" download
    came back rotated away from the picture it claims to be (measured: a 1600×1200
    master saved North-up shows as 1024×948 on screen and downloaded as 1600×1200,
    i.e. a 30° different picture)."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _add_north_up_saved_run(solved_library, safe, w=1600, h=1200)

    shown = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/preview")
    assert shown.status_code == 200
    with Image.open(io.BytesIO(shown.content)) as im:
        shown_aspect = im.width / im.height

    r = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/full-res-png")
    assert r.status_code == 200
    with Image.open(io.BytesIO(r.content)) as im:
        got_w, got_h = im.size
    # Same picture, just bigger: the expand-rotate's aspect, not the canvas's.
    assert abs(got_w / got_h - shown_aspect) < 0.01
    assert abs(got_w / got_h - 1600 / 1200) > 0.1     # and *not* the canvas grid
    assert max(got_w, got_h) > 1600                   # grown by the rotation


def test_asking_for_north_up_on_an_already_turned_run_is_the_same_picture(
        client, solved_library):
    """`?north_up=true` and the bare URL both mean "the run's own full North-up
    correction" on such a run — one turn, not two."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id = _add_north_up_saved_run(solved_library, safe, w=1600, h=1200)

    plain = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/full-res-png")
    asked = client.get(
        f"/api/targets/{safe}/stack-runs/{run_id}/full-res-png?north_up=true")
    assert plain.status_code == 200 and asked.status_code == 200
    assert plain.content == asked.content


def test_full_res_png_of_an_unturned_run_is_untouched(client, solved_library):
    """The no-regression half: a run nothing ever turned still renders on the
    canvas grid, byte-for-byte as before."""
    from seestack.render.thumbnail import render_preview_png_full_res

    safe = client.get("/api/targets").json()[0]["safe_name"]
    w, h = 300, 220
    run_id = _add_run(solved_library, safe, w=w, h=h)
    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target(safe)
        try:
            fits_path = next(
                r for r in proj.iter_stack_runs() if r.id == run_id).fits_path
        finally:
            proj.close()
    finally:
        lib.close()

    r = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/full-res-png")
    assert r.content == render_preview_png_full_res(fits_path)
