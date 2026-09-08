"""The picture you actually *share* comes off the master, not the 1024 px preview.

Every export the app hands over used to start from ``run.preview_path`` — the
stored preview, capped at ``PREVIEW_MAX_WIDTH`` — so the JPEG a beginner posts,
sends to family or prints was 1024 px however big the stack was. These pin that
the share JPEG (and its keepsake / scale-&-compass variants) is re-rendered from
the run's own master at share resolution, and that every case where that render
could show a *different* picture still falls back to the stored bytes.
"""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

import numpy as np
from astropy.io import fits
from astropy.wcs import WCS
from PIL import Image

from seestack.io.library import Library
from seestack.io.project import StackRunRow

_seq = 0


def _register(data_root, safe: str, *, canvas=(1600, 1600), preview_long: int = 400,
              display_space: bool = False, rotation_deg: float = 0.0,
              recipe: str | None = None) -> int:
    """A run as a real stack leaves one: a full-resolution master, and a stored
    preview that is the *capped* render of it."""
    global _seq
    _seq += 1
    tag = f"share_{_seq}"
    from seestack.render.thumbnail import render_preview_png_full_res

    w, h = canvas
    lib = Library.open_or_create(data_root / "library")
    try:
        tdir = Path(lib.target_dir(lib.find_target(safe)))
        ramp = np.tile(np.linspace(0.02, 0.9, w, dtype=np.float32), (h, 1))
        cube = np.stack([ramp, ramp, ramp], axis=0)
        wcs = WCS(naxis=2)
        wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
        wcs.wcs.crpix = [w / 2 + 0.5, h / 2 + 0.5]
        wcs.wcs.crval = [150.0, 20.0]
        th = np.radians(rotation_deg)
        ct, st = float(np.cos(th)), float(np.sin(th))
        s = 0.001
        wcs.wcs.cd = [[-s * ct, s * st], [s * st, s * ct]]
        fits_path = tdir / f"{tag}_master.fits"
        fits.PrimaryHDU(data=cube, header=wcs.to_header()).writeto(
            fits_path, overwrite=True)
        preview_path = tdir / f"{tag}_master_preview.png"
        preview_path.write_bytes(
            render_preview_png_full_res(fits_path, max_long_edge=preview_long))

        opts = {"output_name": tag}
        if display_space:
            opts["preview_display_space"] = True
        proj = lib.open_target(safe)
        try:
            run_id = proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc="2026-05-01T00:00:00Z",
                output_basename=f"{tag}_master", fits_path=str(fits_path),
                tiff_path=None, preview_path=str(preview_path), n_frames_used=5,
                canvas_h=h, canvas_w=w, coverage_min=1, coverage_max=5,
                options_json=json.dumps(opts),
            ))
            if recipe is not None:
                from webapp.routers.editor import RECIPE_META_PREFIX
                proj.set_meta(f"{RECIPE_META_PREFIX}{run_id}", recipe)
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
        return run_id
    finally:
        lib.close()


def _img(content: bytes) -> Image.Image:
    return Image.open(BytesIO(content))


def _safe(client) -> str:
    return client.get("/api/targets").json()[0]["safe_name"]


def test_share_jpeg_comes_off_the_master_not_the_capped_preview(
        client, solved_library):
    safe = _safe(client)
    run_id = _register(solved_library, safe, canvas=(1600, 1600), preview_long=400)
    r = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/jpeg")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg"
    assert _img(r.content).size == (1600, 1600)          # was the 400 px preview


def test_share_jpeg_is_capped_so_a_share_stays_a_quick_render(
        client, solved_library, monkeypatch):
    """A huge mosaic doesn't turn one tap into a full-canvas render: the share
    render is bounded by `SHARE_JPEG_MAX_LONG_EDGE`."""
    from webapp.routers import stack as stack_router

    monkeypatch.setattr(stack_router, "SHARE_JPEG_MAX_LONG_EDGE", 700)
    safe = _safe(client)
    run_id = _register(solved_library, safe, canvas=(1600, 1600), preview_long=400)
    r = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/jpeg")
    assert max(_img(r.content).size) == 700


def test_share_jpeg_is_the_same_picture_only_bigger(client, solved_library):
    """Bigger, not different. Compared against the display-space twin, which
    declines the native render and so serves the old preview-sourced bytes."""
    safe = _safe(client)
    native = _register(solved_library, safe, canvas=(1600, 1600))
    stored = _register(solved_library, safe, canvas=(1600, 1600), display_space=True)

    a = _img(client.get(f"/api/targets/{safe}/stack-runs/{native}/jpeg").content)
    b = _img(client.get(f"/api/targets/{safe}/stack-runs/{stored}/jpeg").content)
    assert a.size == (1600, 1600) and b.size == (400, 400)
    small_a = np.asarray(a.convert("L").resize((32, 32), Image.BOX), dtype=float)
    small_b = np.asarray(b.convert("L").resize((32, 32), Image.BOX), dtype=float)
    assert np.abs(small_a - small_b).max() < 12.0


def test_share_jpeg_measures_the_scale_bar_against_the_picture_it_draws_on(
        client, solved_library, monkeypatch):
    """The bar's length is `fraction × the width it is handed`, so handing the
    marks the stored preview's width while drawing on the master would print a
    bar a quarter the length it claims."""
    from webapp.routers import stack as stack_router

    seen: list[int] = []
    real = stack_router._sky_marks_for_run

    def spy(fits_path, preview_width, *a, **k):  # noqa: ANN001, ANN202
        seen.append(preview_width)
        return real(fits_path, preview_width, *a, **k)

    monkeypatch.setattr(stack_router, "_sky_marks_for_run", spy)
    safe = _safe(client)
    run_id = _register(solved_library, safe, canvas=(1600, 1600), preview_long=400)
    r = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/jpeg?scale=true")
    assert r.status_code == 200
    assert seen == [1600]
    assert _img(r.content).size == (1600, 1600)


def test_keepsake_frames_the_full_resolution_picture(client, solved_library):
    """The framed variant — the one meant for a 6×4 print — mats the big picture,
    and its matte scales with it rather than staying a 1024 px card."""
    safe = _safe(client)
    run_id = _register(solved_library, safe, canvas=(1600, 1600), preview_long=400)
    r = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/jpeg?keepsake=true")
    assert r.status_code == 200
    w, h = _img(r.content).size
    assert w > 1600 and h > 1600                        # picture + a matte around it


def test_share_jpeg_falls_back_for_a_processed_run_with_no_saved_recipe(
        client, solved_library):
    """A display-space preview is a baked edit, and only the saved recipe can
    reproduce it. Without one, rendering the (linear) master would hand over the
    *un-edited* picture — so the stored bytes stay, exactly as before."""
    safe = _safe(client)
    run_id = _register(solved_library, safe, canvas=(1600, 1600), preview_long=400,
                       display_space=True)
    assert _img(client.get(
        f"/api/targets/{safe}/stack-runs/{run_id}/jpeg").content).size == (400, 400)


def _stretch_recipe() -> str:
    from seestack.edit.recipe import OpInstance, Recipe

    return Recipe(ops=[OpInstance(
        id="tone.stretch", params={"mode": "stf", "target_bg": 0.5},
        enabled=True)]).to_json()


def test_share_jpeg_of_a_processed_run_is_rendered_through_its_saved_recipe(
        client, solved_library):
    """His main path. "Process target" / "Reprocess everything" leave a
    display-space preview, so every share of one used to be a re-encode of the
    1024 px preview — soft on the phone he reads this app on. With the recipe
    saved, the share is the same edit rendered off the master at share size."""
    safe = _safe(client)
    run_id = _register(solved_library, safe, canvas=(1600, 1600), preview_long=400,
                       display_space=True, recipe=_stretch_recipe())
    got = _img(client.get(f"/api/targets/{safe}/stack-runs/{run_id}/jpeg").content)
    assert got.size == (1600, 1600)      # the canvas, not the 400 px preview


def test_the_share_source_is_rendered_once_and_then_reused(
        client, solved_library, monkeypatch):
    """Every one of the nine things a run can be handed out as used to re-read the
    master — 104 MB off the NAS per tap on his mosaic. One render now serves them
    all, and the second request serves the cache."""
    from webapp import pipeline

    safe = _safe(client)
    run_id = _register(solved_library, safe, canvas=(1600, 1600), preview_long=400,
                       display_space=True, recipe=_stretch_recipe())
    calls = 0
    real = pipeline.render_run_full_res_png

    def counted(*a, **kw):
        nonlocal calls
        calls += 1
        return real(*a, **kw)

    monkeypatch.setattr(pipeline, "render_run_full_res_png", counted)
    base = f"/api/targets/{safe}/stack-runs/{run_id}"
    assert client.get(f"{base}/jpeg").status_code == 200
    assert client.get(f"{base}/jpeg?keepsake=true").status_code == 200
    assert client.get(f"{base}/wallpaper?aspect=phone").status_code == 200
    assert calls == 1


def test_the_share_cache_is_rebuilt_when_the_saved_recipe_changes(
        client, solved_library, monkeypatch):
    """A re-edit must not be served yesterday's picture: the recipe is in the
    cache's signature, as the preview's and the master's file stamps are."""
    import json

    from webapp import pipeline
    from webapp.routers.editor import RECIPE_META_PREFIX

    safe = _safe(client)
    run_id = _register(solved_library, safe, canvas=(1600, 1600), preview_long=400,
                       display_space=True, recipe=_stretch_recipe())
    base = f"/api/targets/{safe}/stack-runs/{run_id}"
    first = client.get(f"{base}/jpeg").content

    changed = json.loads(_stretch_recipe())
    changed["ops"][0]["params"]["target_bg"] = 0.15
    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target(safe)
        try:
            proj.set_meta(f"{RECIPE_META_PREFIX}{run_id}", json.dumps(changed))
        finally:
            proj.close()
    finally:
        lib.close()

    calls = 0
    real = pipeline.render_run_full_res_png

    def counted(*a, **kw):
        nonlocal calls
        calls += 1
        return real(*a, **kw)

    monkeypatch.setattr(pipeline, "render_run_full_res_png", counted)
    second = client.get(f"{base}/jpeg").content
    assert calls == 1                    # rebuilt, not served from the stale cache
    assert second != first               # and it is the new edit


def test_the_share_cache_is_rebuilt_when_the_preview_is_rewritten(
        client, solved_library, monkeypatch):
    """History's "Adjust → Save" rewrites the stored preview; the cache is keyed on
    that file's stamp, so the next share is the picture he just saved."""
    from webapp import pipeline

    safe = _safe(client)
    run_id = _register(solved_library, safe, canvas=(1600, 1600), preview_long=400,
                       display_space=True, recipe=_stretch_recipe())
    base = f"/api/targets/{safe}/stack-runs/{run_id}"
    assert client.get(f"{base}/jpeg").status_code == 200

    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target(safe)
        try:
            run = next(r for r in proj.iter_stack_runs() if r.id == run_id)
        finally:
            proj.close()
    finally:
        lib.close()
    preview = Path(run.preview_path)
    preview.write_bytes(preview.read_bytes())          # same bytes, new mtime/size stamp
    import os
    os.utime(preview, (0, 0))

    calls = 0
    real = pipeline.render_run_full_res_png

    def counted(*a, **kw):
        nonlocal calls
        calls += 1
        return real(*a, **kw)

    monkeypatch.setattr(pipeline, "render_run_full_res_png", counted)
    assert client.get(f"{base}/jpeg").status_code == 200
    assert calls == 1                                   # rebuilt rather than reused


def test_the_share_cache_lands_beside_the_run_and_is_a_registered_artefact(
        client, solved_library):
    """Tens of megabytes per run, so it must be deletable with the run: it is
    written next to the master under a registered suffix, which is what the
    delete/prune paths resolve."""
    from seestack.stack.output import RUN_ARTEFACT_SUFFIXES

    safe = _safe(client)
    run_id = _register(solved_library, safe, canvas=(1600, 1600), preview_long=400,
                       display_space=True, recipe=_stretch_recipe())
    assert client.get(f"/api/targets/{safe}/stack-runs/{run_id}/jpeg").status_code == 200

    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target(safe)
        try:
            run = next(r for r in proj.iter_stack_runs() if r.id == run_id)
        finally:
            proj.close()
    finally:
        lib.close()
    master = Path(run.fits_path)
    stem = master.name[: -len(master.suffix)]
    cache = master.with_name(f"{stem}{RUN_ARTEFACT_SUFFIXES['share_png']}")
    sig = master.with_name(f"{stem}{RUN_ARTEFACT_SUFFIXES['share_sig']}")
    assert cache.exists() and sig.exists()
    # No half-written temporary left behind.
    assert not list(master.parent.glob("*_share.png*.tmp"))

    # …and deleting the run takes both with it, rather than leaving the largest
    # orphan the output tree can hold.
    assert client.delete(f"/api/targets/{safe}/stack-runs/{run_id}").status_code == 200
    assert not cache.exists() and not sig.exists()


def test_share_jpeg_falls_back_when_the_master_is_gone(client, solved_library):
    safe = _safe(client)
    run_id = _register(solved_library, safe, canvas=(1600, 1600), preview_long=400)
    lib = Library.open_or_create(solved_library / "library")
    try:
        proj = lib.open_target(safe)
        try:
            run = next(r for r in proj.iter_stack_runs() if r.id == run_id)
        finally:
            proj.close()
    finally:
        lib.close()
    Path(run.fits_path).unlink()
    assert _img(client.get(
        f"/api/targets/{safe}/stack-runs/{run_id}/jpeg").content).size == (400, 400)


def test_share_jpeg_north_up_still_turns_the_bigger_picture(client, solved_library):
    safe = _safe(client)
    run_id = _register(solved_library, safe, canvas=(1600, 1600), preview_long=400,
                       rotation_deg=30.0)
    plain = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/jpeg")
    north = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/jpeg?north_up=true")
    assert plain.status_code == 200 and north.status_code == 200
    assert plain.content != north.content
    assert _img(plain.content).size == (1600, 1600)
    # A bicubic expand-rotate grows the canvas and exposes black corners.
    assert max(_img(north.content).size) > 1600
    north_arr = np.asarray(_img(north.content).convert("L"))
    plain_arr = np.asarray(_img(plain.content).convert("L"))
    assert (north_arr < 8).mean() > (plain_arr < 8).mean() + 0.01
