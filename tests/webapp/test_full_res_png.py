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
