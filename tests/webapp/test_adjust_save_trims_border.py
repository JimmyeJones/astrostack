"""History's "Adjust → Save" keeps an unedited mosaic's border trimmed (owner ⭐
2026-10-28, the last open piece of slice (1)).

v0.504.2 cut a fresh stack's stored preview to the rectangle the editor's Auto
would trim, but saving a new stretch from History's Adjust panel re-rendered the
whole canvas and cleared the recorded crop — so the colour-confetti fringe came
straight back onto the thumbnail, the share JPEG and the wallpaper. The slider
save now renders the same rectangle (``render_stack_png(crop=)``, cut after the
stretch and before any North-up turn) and records it, with ``auto_crop_border``
on; a single field, the setting off, or a display-space export keep the whole
canvas as before.
"""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
from PIL import Image

from .test_unedited_preview_trim import (
    _add_mosaic_run,
    _rect,
    _row,
    _safe,
    _size,
    _speckle,
)


def _save(client, safe: str, run_id: int, **body):  # noqa: ANN003, ANN202
    payload = {"stretch": 0.5, "black": 0.35, **body}
    return client.post(f"/api/targets/{safe}/stack-runs/{run_id}/preview",
                       json=payload)


def _whole_render(fits_path: str) -> bytes:
    from seestack.render.thumbnail import render_stack_png

    return render_stack_png(fits_path, stretch=0.5, black=0.35)


def test_a_slider_save_on_an_unedited_mosaic_keeps_autos_rectangle(
        client, solved_library):
    """The saved bytes are the slider render cut to Auto's rectangle — a crop of
    the whole-canvas render, so the tone is the one the sliders chose — and the
    crop is recorded, so every surface that lines up with the preview follows."""
    from seestack.edit.ops.geometry import crop_bounds
    from seestack.previewcrop import PreviewCrop, parse_preview_crop

    safe = _safe(client)
    run_id, preview_path = _add_mosaic_run(solved_library, safe)
    fits_path = _row(solved_library, safe, run_id).fits_path
    whole = _whole_render(fits_path)
    assert _speckle(whole) > 1000               # the slider render carries the band

    r = _save(client, safe, run_id)
    assert r.status_code == 200, r.text
    assert r.json()["border_trimmed"] is True

    rect = _rect(fits_path)
    pw, ph = _size(whole)
    cx0, cx1, cy0, cy1 = crop_bounds(ph, pw, dict(zip(("x0", "y0", "x1", "y1"),
                                                      rect, strict=True)))
    saved = Path(preview_path).read_bytes()
    assert _size(saved) == (cx1 - cx0, cy1 - cy0)
    with Image.open(io.BytesIO(whole)) as im:
        want = np.asarray(im.convert("RGB"))[cy0:cy1, cx0:cx1]
    with Image.open(io.BytesIO(saved)) as im:
        np.testing.assert_array_equal(np.asarray(im.convert("RGB")), want)
    assert _speckle(saved) < 0.01 * _speckle(whole)

    row = _row(solved_library, safe, run_id)
    crop = parse_preview_crop(row.preview_crop_json)
    assert isinstance(crop, PreviewCrop)
    assert crop.as_tuple() == tuple(rect)
    assert row.preview_stretch == 0.5 and row.preview_black == 0.35


def test_the_share_jpeg_after_a_slider_save_is_trimmed_and_full_size(
        client, solved_library):
    """The native share render replays the recorded trim on the saved curve, so
    the JPEG is the Full-res PNG's picture rather than the ragged canvas."""
    safe = _safe(client)
    run_id, _ = _add_mosaic_run(solved_library, safe)
    assert _save(client, safe, run_id).status_code == 200
    fullres = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/full-res-png")
    jpeg = client.get(f"/api/targets/{safe}/stack-runs/{run_id}/jpeg")
    assert fullres.status_code == 200 and jpeg.status_code == 200
    assert _size(jpeg.content) == _size(fullres.content)
    assert max(_size(jpeg.content)) > 1024
    assert _size(jpeg.content) != (2400, 1800)


def test_a_north_up_slider_save_trims_before_it_turns(client, solved_library,
                                                      monkeypatch):
    """The crop is a fraction of the canvas grid, so it is cut first and the turn
    applied to the cut picture — the order every consumer composes them in."""
    from seestack.render import thumbnail

    turned = []

    def fake_turn(disp, fits_path):  # noqa: ANN001, ANN202
        turned.append(disp.shape[:2])
        return np.ascontiguousarray(np.rot90(disp))

    monkeypatch.setattr(thumbnail, "_apply_north_up", fake_turn)
    monkeypatch.setattr(thumbnail, "applied_north_up_deg", lambda p: 90.0)
    safe = _safe(client)
    run_id, preview_path = _add_mosaic_run(solved_library, safe)
    r = _save(client, safe, run_id, north_up=True)
    assert r.status_code == 200, r.text
    assert r.json()["border_trimmed"] is True
    (th, tw), = turned
    assert (tw, th) != (1024, 768)               # the turn saw the cut picture
    assert _size(Path(preview_path).read_bytes()) == (th, tw)
    row = _row(solved_library, safe, run_id)
    assert row.preview_crop_json is not None
    assert row.preview_north_up_deg == 90.0


def test_switched_off_a_slider_save_keeps_the_whole_canvas(client, solved_library):
    safe = _safe(client)
    run_id, preview_path = _add_mosaic_run(solved_library, safe)
    assert client.put("/api/settings",
                      json={"auto_crop_border": False}).status_code == 200
    r = _save(client, safe, run_id)
    assert r.status_code == 200
    assert r.json()["border_trimmed"] is False
    assert _size(Path(preview_path).read_bytes()) == (1024, 768)
    assert _row(solved_library, safe, run_id).preview_crop_json is None


def test_a_single_field_slider_save_keeps_the_whole_canvas(client, solved_library):
    safe = _safe(client)
    run_id, preview_path = _add_mosaic_run(solved_library, safe, is_mosaic=False)
    r = _save(client, safe, run_id)
    assert r.status_code == 200
    assert r.json()["border_trimmed"] is False
    assert _size(Path(preview_path).read_bytes()) == (1024, 768)
    assert _row(solved_library, safe, run_id).preview_crop_json is None


def test_render_stack_png_without_a_crop_is_unchanged(client, solved_library):
    """``crop=None`` (every other caller, and the live Adjust render) is the
    whole-canvas render it has always been."""
    from seestack.render.thumbnail import render_stack_png

    safe = _safe(client)
    run_id, _ = _add_mosaic_run(solved_library, safe)
    fits_path = _row(solved_library, safe, run_id).fits_path
    assert render_stack_png(fits_path, crop=None) == render_stack_png(fits_path)
