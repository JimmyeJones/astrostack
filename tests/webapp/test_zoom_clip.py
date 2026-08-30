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
