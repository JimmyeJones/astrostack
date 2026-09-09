"""The per-run share-ready zoom clip — info + the cached animation itself.

The engine half (the camera schedule) is pinned in ``tests/test_zoom_clip.py``.
These cover the webapp half: that the clip is framed on the *plate-solved* object
in the stored preview's own grid, that a run with no picture self-hides rather
than erroring, and that the cache is keyed to the preview so a re-edited picture
never serves yesterday's move.
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


def _blob_preview(w=400, h=300, blob_xy=(300, 90)) -> Image.Image:
    yy, xx = np.mgrid[0:h, 0:w]
    sky = np.full((h, w), 0.05, dtype=np.float32)
    sky += 0.9 * np.exp(-(((xx - blob_xy[0]) / 12) ** 2 + ((yy - blob_xy[1]) / 12) ** 2))
    u8 = (np.clip(sky, 0, 1) * 255).astype(np.uint8)
    return Image.fromarray(np.dstack([u8] * 3), mode="RGB")


def _register_run(data_root, safe: str, *, preview: Image.Image | None,
                  with_wcs: bool = False) -> tuple[int, Path | None]:
    """A run with a real preview PNG (and optionally a WCS master, so the clip can
    be framed on the catalogued target). Returns ``(run_id, preview_path)``."""
    global _seq
    _seq += 1
    tag = f"zc_{_seq}"
    lib = Library.open_or_create(data_root / "library")
    try:
        tdir = Path(lib.target_dir(lib.find_target(safe)))
        w, h = preview.size if preview is not None else (40, 30)
        hdr = None
        if with_wcs:
            wcs = WCS(naxis=2)
            wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
            wcs.wcs.crpix = [w / 2 + 0.5, h / 2 + 0.5]
            wcs.wcs.crval = [150.0, 20.0]
            s = 0.001
            wcs.wcs.cd = [[-s, 0.0], [0.0, s]]
            hdr = wcs.to_header()
        fits_path = tdir / f"{tag}_master.fits"
        fits.PrimaryHDU(data=np.zeros((3, h, w), dtype=np.float32),
                        header=hdr).writeto(fits_path, overwrite=True)
        preview_path = None
        if preview is not None:
            preview_path = tdir / f"{tag}_master_preview.png"
            preview.save(preview_path)
        proj = lib.open_target(safe)
        try:
            run_id = proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc="2026-05-01T00:00:00Z",
                output_basename=f"{tag}_master", fits_path=str(fits_path),
                tiff_path=None,
                preview_path=str(preview_path) if preview_path else None,
                n_frames_used=42, canvas_h=h, canvas_w=w, coverage_min=1,
                coverage_max=42, options_json=json.dumps({"output_name": "zc"}),
                total_exposure_s=1260.0,
            ))
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
        return (run_id, preview_path)
    finally:
        lib.close()


def _register_master_run(data_root, safe: str, *, canvas=(1600, 1200),
                         preview_long: int = 400, display_space: bool = False,
                         fine_detail: bool = False) -> tuple[int, Path]:
    """A run as a real stack leaves one: a full-resolution master plus a stored
    preview that is the *capped* render of it — the shape
    ``_register_run`` above deliberately doesn't have (its canvas is its preview,
    so the native re-render declines and the clip stays preview-sourced).

    ``fine_detail`` plants a pattern whose period survives at canvas resolution
    and is beyond the capped preview's Nyquist, so "is the clip really made of
    more detail?" is answerable from the frames.
    """
    global _seq
    _seq += 1
    tag = f"zcm_{_seq}"
    from seestack.render.thumbnail import render_preview_png_full_res

    w, h = canvas
    lib = Library.open_or_create(data_root / "library")
    try:
        tdir = Path(lib.target_dir(lib.find_target(safe)))
        yy, xx = np.mgrid[0:h, 0:w]
        plane = np.tile(np.linspace(0.05, 0.85, w, dtype=np.float32), (h, 1))
        if fine_detail:
            plane = plane + 0.12 * np.sin(2 * np.pi * xx / 8.0).astype(np.float32)
        plane += (0.6 * np.exp(-(((xx - w * 0.3) / (w * 0.03)) ** 2
                                 + ((yy - h * 0.5) / (h * 0.03)) ** 2))
                  ).astype(np.float32)
        cube = np.clip(np.stack([plane] * 3, axis=0), 0.0, 1.0)
        wcs = WCS(naxis=2)
        wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
        wcs.wcs.crpix = [w / 2 + 0.5, h / 2 + 0.5]
        wcs.wcs.crval = [150.0, 20.0]
        s = 0.001
        wcs.wcs.cd = [[-s, 0.0], [0.0, s]]
        fits_path = tdir / f"{tag}_master.fits"
        fits.PrimaryHDU(data=cube, header=wcs.to_header()).writeto(
            fits_path, overwrite=True)
        preview_path = tdir / f"{tag}_master_preview.png"
        preview_path.write_bytes(
            render_preview_png_full_res(fits_path, max_long_edge=preview_long))

        opts: dict = {"output_name": tag}
        if display_space:
            opts["preview_display_space"] = True
        proj = lib.open_target(safe)
        try:
            run_id = proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc="2026-05-01T00:00:00Z",
                output_basename=f"{tag}_master", fits_path=str(fits_path),
                tiff_path=None, preview_path=str(preview_path), n_frames_used=7,
                canvas_h=h, canvas_w=w, coverage_min=1, coverage_max=7,
                options_json=json.dumps(opts), total_exposure_s=1260.0,
            ))
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
        return (run_id, fits_path)
    finally:
        lib.close()


def _deepest(frames: list[Image.Image]) -> Image.Image:
    """The most zoomed-in frame of the loop — the push-in's last one."""
    return frames[(len(frames) + 2) // 2 - 1]


def _high_frequency_energy(img: Image.Image) -> float:
    """Mean absolute adjacent-pixel difference: how much detail a frame carries,
    blind to overall brightness."""
    a = np.asarray(img.convert("L"), dtype=np.float32)
    return float(np.abs(np.diff(a, axis=1)).mean() + np.abs(np.diff(a, axis=0)).mean())


def _set_target_position(data_root, safe: str, ra: float, dec: float) -> None:
    lib = Library.open_or_create(data_root / "library")
    try:
        lib._upsert_target(name=safe, safe_name=safe, ra_deg=ra, dec_deg=dec)
    finally:
        lib.close()


def _frames(content: bytes) -> list[Image.Image]:
    out = []
    with Image.open(BytesIO(content)) as clip:
        for i in range(getattr(clip, "n_frames", 1)):
            clip.seek(i)
            out.append(clip.convert("RGB").copy())
    return out


def test_info_offers_the_clip_and_says_how_it_will_be_framed(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id, _ = _register_run(solved_library, safe, preview=_blob_preview())

    body = client.get(
        f"/api/targets/{safe}/stack-runs/{run_id}/zoom-clip/info").json()
    assert body["available"] is True
    assert body["format"] in ("webp", "png")
    assert body["seconds"] > 0 and body["zoom"] > 1
    assert body["width"] and body["height"]
    # No target position on this library entry ⇒ the move aims at the picture's
    # own brightest part, and the UI is told so rather than implying a solve.
    assert body["centred_on_target"] is False


def test_info_self_hides_when_there_is_no_picture(client, solved_library):
    """A run with no stored preview has nothing to move a camera over. The card
    must disappear, not error at the user."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id, _ = _register_run(solved_library, safe, preview=None)

    r = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/zoom-clip/info")
    assert r.status_code == 200
    assert r.json() == {"available": False}
    # …and the download itself is an honest 404 rather than a broken file.
    assert client.get(
        f"/api/targets/{safe}/stack-runs/{run_id}/zoom-clip").status_code == 404


def test_unknown_run_is_404(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    assert client.get(
        f"/api/targets/{safe}/stack-runs/999999/zoom-clip/info").status_code == 404
    assert client.get(
        f"/api/targets/{safe}/stack-runs/999999/zoom-clip").status_code == 404


def test_the_clip_is_a_looping_animation_of_the_run(client, solved_library):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id, _ = _register_run(solved_library, safe, preview=_blob_preview())

    r = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/zoom-clip")
    assert r.status_code == 200
    assert r.headers["content-type"] in ("image/webp", "image/png")
    frames = _frames(r.content)
    assert len(frames) > 4
    # It comes back where it started, so it loops without a jump.
    assert np.array_equal(np.asarray(frames[0]), np.asarray(frames[-1])) is False
    first = np.asarray(frames[0], dtype=np.int16)
    last = np.asarray(frames[-1], dtype=np.int16)
    assert np.abs(first - last).mean() < np.abs(
        first - np.asarray(frames[len(frames) // 2], dtype=np.int16)).mean()


def test_the_move_is_centred_on_the_plate_solved_target(client, solved_library):
    """The point of solving for the object: a galaxy off to one side ends up in
    the middle of the deepest frame, not wherever the picture's centre happens to
    be. Fail-before-the-feature: there was no clip at all."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    # The blob sits left-of-centre in the preview; the WCS puts the catalogued
    # position on the same pixel (crval is at the canvas centre, CD is 0.001°/px
    # with RA flipped, so +0.1° in RA is 100 px to the *left*).
    run_id, _ = _register_run(
        solved_library, safe, preview=_blob_preview(blob_xy=(100, 150)),
        with_wcs=True)
    _set_target_position(solved_library, safe, 150.1, 20.0)

    info = client.get(
        f"/api/targets/{safe}/stack-runs/{run_id}/zoom-clip/info").json()
    assert info["centred_on_target"] is True

    frames = _frames(client.get(
        f"/api/targets/{safe}/stack-runs/{run_id}/zoom-clip").content)
    deepest = np.asarray(frames[(len(frames) + 2) // 2 - 1].convert("L"),
                         dtype=np.float32)
    ys, xs = np.where(deepest > 200)
    assert xs.size, "the object must be visible in the zoomed frame"
    h, w = deepest.shape
    assert abs(xs.mean() / w - 0.5) < 0.15
    assert abs(ys.mean() / h - 0.5) < 0.15


def test_the_clip_is_cached_and_rebuilt_when_the_picture_changes(
    client, solved_library,
):
    """Repeat downloads must be a file read, but a re-edited preview must never
    serve yesterday's move — so the cache is keyed to the preview's own bytes."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id, preview_path = _register_run(
        solved_library, safe, preview=_blob_preview(blob_xy=(300, 90)))

    first = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/zoom-clip")
    assert first.status_code == 200
    cached = list(preview_path.parent.glob("*_zoom.*"))
    assert {p.suffix for p in cached} >= {".sig"}
    again = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/zoom-clip")
    assert again.content == first.content

    # The user re-edits and saves: same path, different picture.
    _blob_preview(blob_xy=(80, 220)).save(preview_path)
    rebuilt = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/zoom-clip")
    assert rebuilt.status_code == 200
    assert rebuilt.content != first.content


def test_the_clip_is_sized_by_the_master_not_by_the_capped_preview(
    client, solved_library,
):
    """The clip asks for `CLIP_LONG_EDGE` and, made from the 1024 px stored
    preview, could never reach it: `zoom_clip_size` never upsamples, so the whole
    move was sized at ``preview / CLIP_ZOOM``. Fail-before: a 400 px preview of a
    1600 px canvas gave a 222 px clip."""
    from seestack.render.zoomclip import CLIP_LONG_EDGE

    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id, _ = _register_master_run(
        solved_library, safe, canvas=(1600, 1200), preview_long=400)

    frames = _frames(client.get(
        f"/api/targets/{safe}/stack-runs/{run_id}/zoom-clip").content)
    assert frames[0].size == (CLIP_LONG_EDGE, 480)


def test_the_clip_carries_detail_the_stored_preview_could_not_hold(
    client, solved_library,
):
    """Not just more pixels — more picture. The same scene is served twice: once
    where the native re-render is allowed, and once as a display-space run with no
    saved recipe, which declines it and so moves the camera over the capped
    preview exactly as before. Comparing the deepest frames at one size (upscaling
    invents nothing) shows the fine pattern only the master ever carried."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    native, _ = _register_master_run(
        solved_library, safe, canvas=(1600, 1200), preview_long=400,
        fine_detail=True)
    stored, _ = _register_master_run(
        solved_library, safe, canvas=(1600, 1200), preview_long=400,
        fine_detail=True, display_space=True)

    a = _deepest(_frames(client.get(
        f"/api/targets/{safe}/stack-runs/{native}/zoom-clip").content))
    b = _deepest(_frames(client.get(
        f"/api/targets/{safe}/stack-runs/{stored}/zoom-clip").content))
    assert a.size == (640, 480) and b.size == (222, 167)
    assert _high_frequency_energy(a) > 1.5 * _high_frequency_energy(
        b.resize(a.size, Image.LANCZOS))


def test_info_reports_the_size_the_download_actually_comes_out_at(
    client, solved_library,
):
    """The size axis of the download-copy sweep: `info` answers before anything is
    rendered, so its figure has to be read off the same source the download will
    use — on both paths."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    native, _ = _register_master_run(
        solved_library, safe, canvas=(1600, 1200), preview_long=400)
    stored, _ = _register_master_run(
        solved_library, safe, canvas=(1600, 1200), preview_long=400,
        display_space=True)

    for run_id in (native, stored):
        info = client.get(
            f"/api/targets/{safe}/stack-runs/{run_id}/zoom-clip/info").json()
        frames = _frames(client.get(
            f"/api/targets/{safe}/stack-runs/{run_id}/zoom-clip").content)
        assert (info["width"], info["height"]) == frames[0].size


def test_the_clip_is_rebuilt_when_the_master_it_is_now_made_from_changes(
    client, solved_library,
):
    """The cache used to be keyed on the preview alone, which was the whole source.
    It isn't any more — a re-stack that rewrites the master under an unchanged
    preview must not serve a move over pixels that are gone."""
    safe = client.get("/api/targets").json()[0]["safe_name"]
    run_id, fits_path = _register_master_run(
        solved_library, safe, canvas=(1600, 1200), preview_long=400)

    first = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/zoom-clip")
    assert first.status_code == 200
    again = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/zoom-clip")
    assert again.content == first.content          # cached, not re-rendered

    h, w = 1200, 1600
    yy, xx = np.mgrid[0:h, 0:w]
    flipped = np.clip(
        np.tile(np.linspace(0.85, 0.05, w, dtype=np.float32), (h, 1))
        + 0.6 * np.exp(-(((xx - w * 0.7) / (w * 0.03)) ** 2
                         + ((yy - h * 0.5) / (h * 0.03)) ** 2)), 0.0, 1.0)
    with fits.open(fits_path, mode="update") as hdul:
        hdul[0].data = np.stack([flipped] * 3, axis=0).astype(np.float32)
    rebuilt = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/zoom-clip")
    assert rebuilt.status_code == 200
    assert rebuilt.content != first.content


def test_a_zoom_clip_travels_with_its_run(tmp_path):
    """The cache lives in ``output/`` beside the picture it was made from, so a
    re-stack must archive it with the rest of the set rather than leaving a clip
    of a picture that no longer exists under that basename."""
    from seestack.stack.output import RUN_ARTEFACT_SUFFIXES, _archive_existing_outputs

    assert RUN_ARTEFACT_SUFFIXES["zoom_webp"] == "_zoom.webp"
    for suffix in ("_zoom.webp", "_zoom.png", "_zoom.sig"):
        assert suffix in RUN_ARTEFACT_SUFFIXES.values()
        (tmp_path / f"master{suffix}").write_bytes(b"x")
    _archive_existing_outputs(tmp_path, "master")
    assert not list(tmp_path.glob("master_zoom.*"))
    assert len(list(tmp_path.glob("master_*_zoom.*"))) == 3
