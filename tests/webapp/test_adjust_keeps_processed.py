"""Rotating a *finished* picture from Adjust must not throw the picture away.

History offers "Adjust" on any run with a FITS, and its own hint ("Stretch /
black point, from the full-range FITS") reads like a view control. On an
in-place "Process target" Auto edit it is not: ``save_stack_preview``
re-renders the preview from the **linear** master, so saving replaces the
tone-mapped picture — the one on the Target hero, in the Gallery, on the Library
tile, possibly pinned as the target's cover — with a plain stretch, silently. A
user who opened the panel only to tick **North up** paid that price too, which is
the reachable, innocent path: rotation is the one thing you genuinely want from
that panel on an already-finished picture.

So the save grew a second path, ``keep_processed``: re-bake the run's own stored
recipe (optionally rotated) instead of the sliders. The suggestion endpoint says
when the panel should offer it. The plain slider save is untouched — the tests
below pin both halves, because the fix is "give them the other option", not
"change what Save does".
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits
from astropy.wcs import WCS

from seestack.io.library import Library
from seestack.io.project import StackRunRow
from seestack.previewcrop import PreviewCrop, parse_preview_crop

pytest.importorskip("PIL")

_H = _W = 96


#: An off-centre covered block, used by the ``trimmable=True`` fixture so Auto's
#: border trim really fires (and is asymmetric, so a wrong offset can't hide
#: behind a right scale).
_COV_X0, _COV_X1 = 18, 86
_COV_Y0, _COV_Y1 = 10, 62


def _register_run(data_root, safe: str, *, rot_deg: float = 0.0,
                  name: str = "master", trimmable: bool = False) -> tuple[int, Path]:
    """Register a run with a real (optionally rotated) WCS and a placeholder
    preview PNG. With ``trimmable``, the canvas gets a wide ragged NaN border and
    a coverage sibling, so the Auto recipe ends in a real ``geometry.crop``.
    Returns ``(run_id, preview_path)``."""
    from PIL import Image

    lib = Library.open_or_create(data_root / "library")
    try:
        tdir = Path(lib.target_dir(lib.find_target(safe)))
        yy, xx = np.mgrid[0:_H, 0:_W]
        blob = np.exp(-(((xx - 48) ** 2 + (yy - 40) ** 2) / 150.0)).astype(np.float32)
        rng = np.random.default_rng(11)
        sky = rng.normal(0.02, 0.003, size=(_H, _W)).astype(np.float32)
        cube = np.stack([blob + sky, 0.6 * blob + sky, 0.3 * blob + sky]).astype(np.float32)
        if trimmable:
            covered = np.zeros((_H, _W), dtype=bool)
            covered[_COV_Y0:_COV_Y1, _COV_X0:_COV_X1] = True
            cube[:, ~covered] = np.nan

        wcs = WCS(naxis=2)
        wcs.wcs.crpix = [(_W - 1) / 2 + 1, (_H - 1) / 2 + 1]
        wcs.wcs.crval = [150.0, 20.0]
        wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
        th = np.radians(rot_deg)
        cd = 0.001
        wcs.wcs.cd = np.array([[-cd * np.cos(th), cd * np.sin(th)],
                               [cd * np.sin(th), cd * np.cos(th)]])
        fits_path = tdir / f"{name}.fits"
        fits.PrimaryHDU(data=cube, header=wcs.to_header()).writeto(
            fits_path, overwrite=True)
        if trimmable:
            cov = np.zeros((_H, _W), dtype=np.float32)
            cov[_COV_Y0:_COV_Y1, _COV_X0:_COV_X1] = 5.0
            fits.PrimaryHDU(data=cov).writeto(
                fits_path.with_name(f"{name}_coverage.fits"), overwrite=True)

        preview = tdir / f"{name}_preview.png"
        Image.new("RGB", (_W, _H), (10, 20, 30)).save(preview)

        proj = lib.open_target(safe)
        try:
            run_id = proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc="2026-05-01T00:00:00Z",
                output_basename=name, fits_path=str(fits_path), tiff_path=None,
                preview_path=str(preview), n_frames_used=5,
                canvas_h=_H, canvas_w=_W, coverage_min=0 if trimmable else 1,
                coverage_max=5,
                options_json=json.dumps({"output_name": "m42"}),
                is_mosaic=trimmable,
            ))
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
        return int(run_id), preview
    finally:
        lib.close()


def _auto_edit(data_root, safe: str, run_id: int) -> int | None:
    from webapp.pipeline import _auto_edit_process_run

    lib = Library.open_or_create(data_root / "library")
    try:
        return _auto_edit_process_run(lib, safe, run_id, auto_crop=True)
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


def _meta(data_root, safe: str, key: str) -> str | None:
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            return proj.get_meta(key)
        finally:
            proj.close()
    finally:
        lib.close()


def _set_meta(data_root, safe: str, key: str, value: str) -> None:
    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            proj.set_meta(key, value)
        finally:
            proj.close()
    finally:
        lib.close()


def _size(path: Path) -> tuple[int, int]:
    from PIL import Image

    with Image.open(path) as im:
        return im.size


def _mean_level(path: Path) -> float:
    from PIL import Image

    with Image.open(path) as im:
        return float(np.asarray(im.convert("RGB"), dtype=np.float32).mean())


# ---- what the panel is told ---------------------------------------------

def test_the_suggestion_endpoint_flags_a_processed_picture(client, solved_library):
    """The panel can only warn before the fact if it knows — and it can only
    offer the rescue if the recipe that made the picture is still there."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id, _preview = _register_run(solved_library, safe)

    plain = client.get(
        f"/api/targets/{safe}/stack-runs/{run_id}/render-suggestion").json()
    assert plain["processed_preview"] is False
    assert plain["can_keep_processed"] is False

    assert _auto_edit(solved_library, safe, run_id) is not None
    after = client.get(
        f"/api/targets/{safe}/stack-runs/{run_id}/render-suggestion").json()
    assert after["processed_preview"] is True
    assert after["can_keep_processed"] is True


def test_a_processed_run_whose_recipe_is_gone_is_warned_but_not_offered(
        client, solved_library):
    """Without the recipe there is nothing to re-bake, so the panel must warn
    and *not* promise a rescue it can't perform."""
    from webapp.routers.editor import RECIPE_META_PREFIX

    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id, _preview = _register_run(solved_library, safe)
    assert _auto_edit(solved_library, safe, run_id) is not None
    _set_meta(solved_library, safe, f"{RECIPE_META_PREFIX}{run_id}", "")

    body = client.get(
        f"/api/targets/{safe}/stack-runs/{run_id}/render-suggestion").json()
    assert body["processed_preview"] is True
    assert body["can_keep_processed"] is False


# ---- the save that keeps the picture ------------------------------------

def test_a_plain_slider_save_still_replaces_the_processed_picture(
        client, solved_library):
    """Unchanged behaviour, pinned on purpose: the fix adds an option, it does
    not quietly redefine Save. The markers are still cleared with the bytes."""
    from webapp.routers.editor import AUTO_EDIT_BAKED_LOOK_PREFIX

    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id, preview = _register_run(solved_library, safe)
    assert _auto_edit(solved_library, safe, run_id) is not None
    baked = preview.read_bytes()

    r = client.post(f"/api/targets/{safe}/stack-runs/{run_id}/preview",
                    json={"stretch": 0.5, "black": 0.35, "north_up": False})
    assert r.status_code == 200
    assert r.json().get("kept_processed") is not True
    assert preview.read_bytes() != baked
    row = _run_row(solved_library, safe, run_id)
    assert json.loads(row.options_json).get("preview_display_space") is False
    assert _meta(solved_library, safe,
                 f"{AUTO_EDIT_BAKED_LOOK_PREFIX}{run_id}") is None


def test_keep_processed_re_bakes_the_picture_instead_of_a_flat_stretch(
        client, solved_library):
    """The heart of it: saving with ``keep_processed`` reproduces the processed
    picture rather than overwriting it with a stretch of the linear master."""
    from webapp.routers.editor import AUTO_EDIT_BAKED_LOOK_PREFIX

    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id, preview = _register_run(solved_library, safe)
    assert _auto_edit(solved_library, safe, run_id) is not None
    baked = preview.read_bytes()

    r = client.post(f"/api/targets/{safe}/stack-runs/{run_id}/preview",
                    json={"keep_processed": True, "north_up": False})
    assert r.status_code == 200
    body = r.json()
    assert body["kept_processed"] is True
    assert body["stretch"] is None and body["black"] is None
    assert body["north_up_deg"] == 0.0
    # Same recipe, same proxy, same code path ⇒ the same picture, byte for byte.
    assert preview.read_bytes() == baked

    row = _run_row(solved_library, safe, run_id)
    # Still a processed picture, and still stamped as one — everything that
    # reads these markers (the reveal, the stretch suggestion, "finish them
    # all") must see no change at all.
    assert json.loads(row.options_json).get("preview_display_space") is True
    assert _meta(solved_library, safe,
                 f"{AUTO_EDIT_BAKED_LOOK_PREFIX}{run_id}") is not None
    # …and the bytes are not an asinh render, so nothing may match against one.
    assert row.preview_stretch is None and row.preview_black is None


def test_keep_processed_rotates_the_processed_picture_north_up(
        client, solved_library):
    """The whole reason the option exists: North up on a finished picture now
    turns *that* picture, and records the angle so the Sky map follows it."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id, preview = _register_run(solved_library, safe, rot_deg=30.0)
    assert _auto_edit(solved_library, safe, run_id) is not None
    baked_level = _mean_level(preview)
    baked_size = _size(preview)

    r = client.post(f"/api/targets/{safe}/stack-runs/{run_id}/preview",
                    json={"keep_processed": True, "north_up": True})
    assert r.status_code == 200
    assert abs(r.json()["north_up_deg"]) > 5.0
    row = _run_row(solved_library, safe, run_id)
    assert abs(row.preview_north_up_deg or 0.0) > 5.0
    # A 30° expand-rotate grows the canvas…
    turned = _size(preview)
    assert turned[0] > baked_size[0] and turned[1] > baked_size[1]
    # …and the pixels are still the *processed* ones: an expand-rotate only adds
    # black corners, so the mean can fall but the picture can't become the much
    # dimmer flat stretch of a linear master.
    assert _mean_level(preview) > 0.5 * baked_level
    # Still marked processed, so the rotation didn't cost the marker either.
    assert json.loads(row.options_json).get("preview_display_space") is True


def test_keep_processed_records_the_recipes_border_trim(client, solved_library):
    """The re-bake writes the same geometry the original bake did — a stale or
    missing crop would have every consumer that lines up with these bytes (the
    Sky-map footprint, the scale bar) correcting for the wrong rectangle."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id, _preview = _register_run(solved_library, safe, trimmable=True)
    assert _auto_edit(solved_library, safe, run_id) is not None
    baked_crop = _run_row(solved_library, safe, run_id).preview_crop_json
    # The fixture exists to make this a real rectangle — without one the
    # comparison below would be None == None and prove nothing.
    assert isinstance(parse_preview_crop(baked_crop), PreviewCrop)

    r = client.post(f"/api/targets/{safe}/stack-runs/{run_id}/preview",
                    json={"keep_processed": True, "north_up": False})
    assert r.status_code == 200
    assert _run_row(solved_library, safe, run_id).preview_crop_json == baked_crop


def test_keep_processed_on_an_ordinary_run_is_refused_not_guessed(
        client, solved_library):
    """A linear run has no processed picture to keep. Doing it anyway would turn
    a saved editor recipe into the run's thumbnail and mark it display-space —
    a *different* feature, down a path nothing offers. Refuse instead."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id, preview = _register_run(solved_library, safe)
    before = preview.read_bytes()

    r = client.post(f"/api/targets/{safe}/stack-runs/{run_id}/preview",
                    json={"keep_processed": True, "north_up": False})
    assert r.status_code == 400
    assert preview.read_bytes() == before


def test_keep_processed_without_a_recipe_is_refused_not_guessed(
        client, solved_library):
    """Processed, but the recipe is gone ⇒ nothing to bake. Say so rather than
    silently falling back to the stretch save the user was avoiding."""
    from webapp.routers.editor import RECIPE_META_PREFIX

    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id, preview = _register_run(solved_library, safe)
    assert _auto_edit(solved_library, safe, run_id) is not None
    _set_meta(solved_library, safe, f"{RECIPE_META_PREFIX}{run_id}", "")
    before = preview.read_bytes()

    r = client.post(f"/api/targets/{safe}/stack-runs/{run_id}/preview",
                    json={"keep_processed": True, "north_up": False})
    assert r.status_code == 400
    assert preview.read_bytes() == before


def test_keep_processed_re_bakes_a_drifted_run_back_into_agreement(
        client, solved_library):
    """A run whose recipe was re-saved in the editor shows an older look than it
    stores. Re-baking is exactly the cure: the bytes and the stamp come from one
    recipe again, so the surfaces that stood down (the reveal) can reopen."""
    from webapp.routers.editor import AUTO_EDIT_BAKED_LOOK_PREFIX
    from webapp.routers.stack import _baked_look_disagrees, _recipe_look

    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id, _preview = _register_run(solved_library, safe)
    assert _auto_edit(solved_library, safe, run_id) is not None

    # Drift the stamp, the way a "tweak and Save" in the editor does.
    _set_meta(solved_library, safe, f"{AUTO_EDIT_BAKED_LOOK_PREFIX}{run_id}",
              json.dumps([["tone.stretch", [["amount", 0.123]]]]))
    from webapp.routers.editor import RECIPE_META_PREFIX
    recipe_json = _meta(solved_library, safe, f"{RECIPE_META_PREFIX}{run_id}")
    assert _baked_look_disagrees(
        _meta(solved_library, safe, f"{AUTO_EDIT_BAKED_LOOK_PREFIX}{run_id}"),
        _recipe_look(recipe_json)) is True

    r = client.post(f"/api/targets/{safe}/stack-runs/{run_id}/preview",
                    json={"keep_processed": True, "north_up": False})
    assert r.status_code == 200
    stamp = _meta(solved_library, safe, f"{AUTO_EDIT_BAKED_LOOK_PREFIX}{run_id}")
    # Present *and* agreeing — a cleared stamp reads as "can't tell", which is
    # not the same statement and would pass a weaker assertion.
    assert stamp
    assert _baked_look_disagrees(stamp, _recipe_look(recipe_json)) is False


def test_an_ordinary_run_ignores_nothing_and_saves_as_before(client, solved_library):
    """Upgrade safety, stated as a test: a client that never sends the new flag
    gets exactly the old endpoint, on a run that was never processed."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id, preview = _register_run(solved_library, safe)
    before = preview.read_bytes()

    r = client.post(f"/api/targets/{safe}/stack-runs/{run_id}/preview",
                    json={"stretch": 0.6, "black": 0.2, "north_up": False})
    assert r.status_code == 200
    assert r.json()["stretch"] == pytest.approx(0.6)
    assert preview.read_bytes() != before
    row = _run_row(solved_library, safe, run_id)
    assert row.preview_stretch == pytest.approx(0.6)
