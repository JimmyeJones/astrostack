"""A recipe that already rotates must not be turned North-up a second time.

The editor's Rotate op turns the picture counter-clockwise — the same sense as
the North-up turn (``orient.rotate_image_north_up``). Someone who straightened a
processed picture by hand in the editor and saved it has *already* applied part
(or all) of the master's North-up correction. Both places that turn a recipe
render North-up — the Full-res PNG download (``render_run_recipe_fullres_png``)
and History's "Adjust → keep processed → North up" save — used to apply the
master's **whole** angle on top, so the picture came out turned by the recipe's
angle twice: North off by that much, and the canvas grown with black corners.
They now apply only the remainder (``geometry.recipe_rotation_deg``).
"""

from __future__ import annotations

import io
import json

import numpy as np
import pytest

from seestack.edit.ops.geometry import recipe_rotation_deg
from seestack.edit.recipe import OpInstance, Recipe

from .test_adjust_keeps_processed import (
    _auto_edit,
    _register_run,
    _run_row,
    _set_meta,
    _size,
)
from .test_pictures_archive import _turned_master

pytest.importorskip("PIL")


def _png_size(data: bytes) -> tuple[int, int]:
    from PIL import Image

    with Image.open(io.BytesIO(data)) as im:
        return im.size


def test_recipe_rotation_deg_sums_only_enabled_real_turns():
    rec = Recipe(ops=[
        OpInstance(id="stretch.stf", params={}),
        OpInstance(id="geometry.rotate", params={"angle": 30.0}),
        OpInstance(id="geometry.rotate", params={"angle": -12.5}),
        OpInstance(id="geometry.rotate", params={"angle": 90.0}, enabled=False),
        OpInstance(id="geometry.rotate", params={"angle": 1e-4}),
        OpInstance(id="geometry.crop", params={}),
    ])
    assert recipe_rotation_deg(rec) == pytest.approx(17.5)
    assert recipe_rotation_deg(Recipe(ops=[])) == 0.0


def _recipe(rotate: float) -> dict:
    ops = [OpInstance(id="stretch.stf", params={})]
    if rotate:
        ops.append(OpInstance(id="geometry.rotate",
                              params={"angle": rotate, "expand": True}))
    return json.loads(Recipe(ops=ops).to_json())


def test_full_res_north_up_of_a_recipe_that_already_turned_north_up_is_a_no_op(tmp_path):
    """The recipe turns the picture by exactly the master's North-up angle, so
    asking for North up must change nothing. Before: a second 140° expand-turn
    grew a 499×487 picture to 697×695 and left North pointing 140° away."""
    from seestack.render.thumbnail import stack_north_up_deg
    from webapp.pipeline import render_run_recipe_fullres_png

    fits_path = tmp_path / "m.fits"
    _turned_master(fits_path, w=400, h=300, rot_deg=40.0)
    angle = stack_north_up_deg(fits_path)
    assert angle is not None and abs(angle) > 10

    straightened = _recipe(angle)
    plain = render_run_recipe_fullres_png(str(fits_path), straightened, north_up=False)
    north = render_run_recipe_fullres_png(str(fits_path), straightened, north_up=True)
    assert _png_size(north) == _png_size(plain)
    assert north == plain


def _bearing_of_brightest(data: bytes) -> float:
    """Direction (deg, CCW from the +x axis, y up) from the picture's centre to
    its brightest pixel. Every turn here is about the centre, so a marked pixel's
    bearing is the picture's orientation, whatever the expands did to the size."""
    from PIL import Image

    with Image.open(io.BytesIO(data)) as im:
        a = np.asarray(im.convert("L"), dtype=np.float32)
    y, x = np.unravel_index(int(np.argmax(a)), a.shape)
    cy, cx = (a.shape[0] - 1) / 2, (a.shape[1] - 1) / 2
    return float(np.degrees(np.arctan2(cy - y, x - cx)))


def test_full_res_north_up_applies_only_the_rest_of_the_turn(tmp_path):
    """A recipe that turned part of the way: North up must land the picture at
    the master's whole North-up orientation — where a recipe with no rotate
    lands it — not at that plus the recipe's own turn. Measured by where a
    single bright star ends up relative to the centre."""
    from astropy.io import fits

    from seestack.render.thumbnail import stack_north_up_deg
    from webapp.pipeline import render_run_recipe_fullres_png

    fits_path = tmp_path / "m.fits"
    _turned_master(fits_path, w=400, h=300, rot_deg=40.0)
    with fits.open(fits_path, mode="update") as hdul:
        cube = np.full_like(hdul[0].data, 20.0)
        cube[:, 60:64, 300:304] = 5000.0  # one star, well off-centre
        hdul[0].data = cube
    angle = stack_north_up_deg(fits_path)

    whole = _bearing_of_brightest(render_run_recipe_fullres_png(
        str(fits_path), _recipe(0.0), north_up=True))
    part = _bearing_of_brightest(render_run_recipe_fullres_png(
        str(fits_path), _recipe(angle / 3), north_up=True))
    diff = (part - whole + 180.0) % 360.0 - 180.0
    assert abs(diff) < 3.0


def test_full_res_north_up_without_a_rotate_is_unchanged(tmp_path):
    """No rotate in the recipe: the master's whole turn, exactly as before."""
    from seestack.render.orient import rotate_image_north_up
    from seestack.render.thumbnail import stack_north_up_deg
    from webapp.pipeline import render_run_recipe_fullres_png

    fits_path = tmp_path / "m.fits"
    _turned_master(fits_path, w=400, h=300, rot_deg=40.0)
    angle = stack_north_up_deg(fits_path)
    plain = _png_size(render_run_recipe_fullres_png(
        str(fits_path), _recipe(0.0), north_up=False))
    turned = rotate_image_north_up(np.zeros((plain[1], plain[0], 3), np.float32), angle)
    assert _png_size(render_run_recipe_fullres_png(
        str(fits_path), _recipe(0.0), north_up=True)) == (turned.shape[1], turned.shape[0])


def test_keep_processed_north_up_save_does_not_turn_a_straightened_recipe_again(
        client, solved_library):
    """History's "Adjust → keep processed → North up" re-bakes the saved recipe
    and turns the bytes North-up. With a recipe that already turned the picture
    North-up the stored preview must come out the size of the un-turned bake,
    and still record the run's whole turn (that is where the bytes now sit), so
    the share/wallpaper paths add nothing more."""
    from seestack.render.thumbnail import stack_north_up_deg
    from webapp.routers.editor import RECIPE_META_PREFIX

    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id, preview = _register_run(solved_library, safe, rot_deg=30.0)
    assert _auto_edit(solved_library, safe, run_id) is not None
    row = _run_row(solved_library, safe, run_id)
    angle = stack_north_up_deg(row.fits_path)
    assert angle is not None and abs(angle) > 5

    from seestack.io.library import Library

    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target(safe)
        try:
            recipe = json.loads(proj.get_meta(f"{RECIPE_META_PREFIX}{run_id}"))
        finally:
            proj.close()
    finally:
        lib.close()
    recipe["ops"].append(json.loads(Recipe(ops=[OpInstance(
        id="geometry.rotate", params={"angle": angle, "expand": True})]).to_json())["ops"][0])
    _set_meta(solved_library, safe, f"{RECIPE_META_PREFIX}{run_id}", json.dumps(recipe))

    base = f"/api/targets/{safe}/stack-runs/{run_id}/preview"
    r = client.post(base, json={"keep_processed": True, "north_up": False})
    assert r.status_code == 200
    straightened = _size(preview)

    r = client.post(base, json={"keep_processed": True, "north_up": True})
    assert r.status_code == 200
    assert _size(preview) == straightened
    assert abs(r.json()["north_up_deg"]) > 5.0
