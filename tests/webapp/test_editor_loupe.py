"""«Check it at full size»: one window of the picture rendered at 1:1.

The live preview is a ≤1500 px strided decimation of what may be a 150 MP mosaic,
and four editor controls carry an advisory about it — deconvolution understates,
sharpening understates, star reduction differs, hot-pixel removal is skipped.
Each is honest, and each leaves a beginner with a slider they cannot set by eye.
This endpoint is the answer instead of the apology: one modest full-resolution
window, through the same recipe.

What makes it honest rather than a second lie is the two channels underneath it.
The ops that measure the **whole image** get the fits the whole-image render made
(``EditContext.fit``, v0.328.2); the three ``background.*`` passes, which fit a
sky *model*, have the field they subtracted replayed onto the window rather than
re-fitted there (``replay_field``, v0.328.6). The decisive test here is therefore
not "does it return a PNG" but **does the window agree with the preview where the
two show the same source pixels** — with its control, that a window re-rendered
without those channels does not.
"""

from __future__ import annotations

import base64
import io
import json
from pathlib import Path

import numpy as np
from astropy.io import fits
from PIL import Image

from seestack.io.library import Library
from seestack.io.project import StackRunRow

# Big enough that the proxy is genuinely decimated (PROXY_MAX_PX is 1500, so this
# strides by 2) — the whole point of the feature is the gap between the two, and a
# fixture that fits in the proxy cannot exhibit it at all.
BIG_W, BIG_H = 1600, 900
STEP = 2


def _make_run(data_root: Path, safe: str, *, basename: str, w: int, h: int) -> int:
    """A stack run whose FITS carries an asymmetric sky gradient and stars.

    The gradient matters: it is what the background pass fits, and a flat sky
    would be fitted identically on any window, so the replay would have nothing to
    do and the parity test below would pass for the wrong reason.
    """
    rng = np.random.default_rng(7)
    yy, xx = np.mgrid[0:h, 0:w]
    ny, nx = yy / (h - 1), xx / (w - 1)
    sky = 0.02 + 0.05 * nx + 0.03 * ny + 0.02 * (nx - 0.5) ** 2

    stars = np.zeros((h, w), dtype=np.float32)
    ys = rng.integers(8, h - 8, 400)
    xs = rng.integers(8, w - 8, 400)
    stars[ys, xs] = 10 ** rng.uniform(-1.2, -0.2, 400)

    cube = np.empty((3, h, w), dtype=np.float32)
    for c, tint in enumerate((1.15, 1.0, 0.85)):
        cube[c] = (sky * tint + stars
                   + rng.normal(0.0, 0.0012, size=(h, w))).astype(np.float32)

    lib = Library.open_or_create(data_root / "library")
    try:
        proj = lib.open_target(safe)
        try:
            outdir = Path(proj.project_dir) / "output"
            outdir.mkdir(parents=True, exist_ok=True)
            fp = outdir / f"{basename}.fits"
            fits.writeto(fp, cube, overwrite=True)
            return proj.add_stack_run(StackRunRow(
                id=None, timestamp_utc="2026-05-02T00:00:00Z",
                output_basename=basename, fits_path=str(fp), tiff_path=None,
                preview_path=None, n_frames_used=12, canvas_h=h, canvas_w=w,
                coverage_min=12, coverage_max=12, options_json="{}",
            ))
        finally:
            proj.close()
    finally:
        lib.close()


def _enc(ops: list[dict]) -> str:
    return base64.urlsafe_b64encode(
        json.dumps({"version": 1, "ops": ops}).encode()).decode()


#: Background + tone only, on purpose. A *spatial* op (sharpen, denoise) reaches
#: across the window's edge and legitimately differs there — a separate question,
#: and the one the loupe exists to let a person judge by eye rather than by test.
FLAT_RECIPE = [
    {"uid": "bg", "id": "background.final_gradient", "enabled": True,
     "params": {"mode": "per_channel", "box_size": 128}},
    {"uid": "st", "id": "tone.stretch", "enabled": True,
     "params": {"mode": "stf", "target_bg": 0.2}},
    {"uid": "lv", "id": "tone.levels", "enabled": True,
     "params": {"black": 0.0, "white": 1.0, "gamma": 1.1}},
]


def _png(resp) -> np.ndarray:
    return np.asarray(Image.open(io.BytesIO(resp.content)).convert("RGB"),
                      dtype=np.int16)


def _big(client, built_library, basename="big"):
    return _make_run(built_library, "M_42", basename=basename, w=BIG_W, h=BIG_H)


# --- when it is offered at all ------------------------------------------------

def test_it_is_offered_where_the_preview_is_decimated(client, built_library):
    run_id = _big(client, built_library)
    r = client.get(f"/api/targets/M_42/stack-runs/{run_id}/editor/loupe-info",
                   params={"recipe": _enc(FLAT_RECIPE)})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["available"] is True
    assert body["reason"] is None
    assert body["proxy_scale"] == STEP
    assert (body["canvas_width"], body["canvas_height"]) == (BIG_W, BIG_H)


def test_it_is_not_offered_when_the_preview_already_shows_every_pixel(
        client, built_library):
    """A small stack's proxy *is* the picture, so there is nothing to check — and
    saying so is better than a control that returns the image you already see."""
    run_id = _make_run(built_library, "M_42", basename="small", w=200, h=140)
    r = client.get(f"/api/targets/M_42/stack-runs/{run_id}/editor/loupe-info",
                   params={"recipe": _enc(FLAT_RECIPE)})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["available"] is False
    assert "every pixel" in body["reason"]


def test_a_rotated_picture_is_declined_rather_than_guessed_at(client, built_library):
    """Where the user clicked is not answerable once the render isn't a crop of
    the canvas, so both the offer and the render refuse — in plain language."""
    run_id = _big(client, built_library, basename="rot")
    rotated = _enc([{"uid": "ro", "id": "geometry.rotate", "enabled": True,
                     "params": {"angle": 5.0}}, *FLAT_RECIPE])

    info = client.get(f"/api/targets/M_42/stack-runs/{run_id}/editor/loupe-info",
                      params={"recipe": rotated}).json()
    assert info["available"] is False
    assert "rotated" in info["reason"]

    r = client.get(f"/api/targets/M_42/stack-runs/{run_id}/editor/loupe",
                   params={"recipe": rotated})
    assert r.status_code == 409
    assert "rotated" in r.json()["detail"]


def test_a_crop_before_the_background_pass_is_declined(client, built_library):
    """The replayed sky field remembers where it was measured; a crop upstream of
    the pass moves that origin and the field would land in the wrong place. Auto
    puts its crop last, so this only fires on a hand-reordered recipe."""
    run_id = _big(client, built_library, basename="cropfirst")
    bad = _enc([{"uid": "cr", "id": "geometry.crop", "enabled": True,
                 "params": {"x0": 0.1, "y0": 0.1, "x1": 0.9, "y1": 0.9}},
                *FLAT_RECIPE])
    info = client.get(f"/api/targets/M_42/stack-runs/{run_id}/editor/loupe-info",
                      params={"recipe": bad}).json()
    assert info["available"] is False
    assert "background" in info["reason"]
    assert client.get(f"/api/targets/M_42/stack-runs/{run_id}/editor/loupe",
                      params={"recipe": bad}).status_code == 409


def test_a_crop_after_the_background_pass_is_fine(client, built_library):
    """…and the ordinary shape — Auto's own — is not refused."""
    run_id = _big(client, built_library, basename="cropafter")
    ok = _enc([*FLAT_RECIPE,
               {"uid": "cr", "id": "geometry.crop", "enabled": True,
                "params": {"x0": 0.1, "y0": 0.1, "x1": 0.9, "y1": 0.9}}])
    info = client.get(f"/api/targets/M_42/stack-runs/{run_id}/editor/loupe-info",
                      params={"recipe": ok}).json()
    assert info["available"] is True


# --- where it looks -----------------------------------------------------------

def _window(resp) -> dict:
    return json.loads(resp.headers["X-Loupe-Window"])


def test_it_returns_a_full_resolution_window_of_the_place_that_was_clicked(
        client, built_library):
    run_id = _big(client, built_library, basename="where")
    r = client.get(f"/api/targets/M_42/stack-runs/{run_id}/editor/loupe",
                   params={"recipe": _enc(FLAT_RECIPE), "fx": 0.25, "fy": 0.75,
                           "size": 256})
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "image/png"
    assert _png(r).shape == (256, 256, 3)

    win = _window(r)
    assert (win["width"], win["height"]) == (256, 256)
    # Centred on the click, to within the rounding of a half-pixel.
    assert abs(win["x"] + 128 - 0.25 * BIG_W) <= 1
    assert abs(win["y"] + 128 - 0.75 * BIG_H) <= 1
    assert win["canvas_width"] == BIG_W


def test_a_window_at_the_very_edge_stays_inside_the_canvas(client, built_library):
    run_id = _big(client, built_library, basename="edge")
    for fx, fy in ((0.0, 0.0), (1.0, 1.0), (-3.0, 9.0)):
        r = client.get(f"/api/targets/M_42/stack-runs/{run_id}/editor/loupe",
                       params={"recipe": _enc(FLAT_RECIPE), "fx": fx, "fy": fy,
                               "size": 256})
        assert r.status_code == 200, r.text
        win = _window(r)
        assert 0 <= win["x"] <= BIG_W - win["width"]
        assert 0 <= win["y"] <= BIG_H - win["height"]
        assert _png(r).shape == (256, 256, 3)


def test_the_click_is_read_through_the_recipes_own_crop(client, built_library):
    """The browser can only report a fraction of what it is *showing*, and a
    trailing crop means that is a fraction of the crop, not of the canvas. The
    centre of a cropped preview is the centre of the crop."""
    run_id = _big(client, built_library, basename="mapped")
    cropped = _enc([*FLAT_RECIPE,
                    {"uid": "cr", "id": "geometry.crop", "enabled": True,
                     "params": {"x0": 0.6, "y0": 0.0, "x1": 1.0, "y1": 0.4}}])
    r = client.get(f"/api/targets/M_42/stack-runs/{run_id}/editor/loupe",
                   params={"recipe": cropped, "fx": 0.5, "fy": 0.5, "size": 256})
    assert r.status_code == 200, r.text
    win = _window(r)
    # The crop's own centre is 0.8 across and 0.2 down the canvas — not 0.5/0.5.
    assert abs(win["x"] + 128 - 0.8 * BIG_W) <= 1
    assert abs(win["y"] + 128 - 0.2 * BIG_H) <= 1


def test_the_window_is_also_reported_where_the_preview_would_draw_it(
        client, built_library):
    """The marker's own coordinate system. ``x``/``y`` are full-canvas pixels,
    which is the right frame for "which part of my picture is this?" and the
    wrong one for a rectangle drawn on the preview — with no crop the two agree,
    which is exactly why the disagreement went unnoticed."""
    run_id = _big(client, built_library, basename="onpreview")
    r = client.get(f"/api/targets/M_42/stack-runs/{run_id}/editor/loupe",
                   params={"recipe": _enc(FLAT_RECIPE), "fx": 0.25, "fy": 0.75,
                           "size": 256})
    assert r.status_code == 200, r.text
    win = _window(r)
    assert win["preview_width"] == round(256 / BIG_W, 6)
    assert win["preview_height"] == round(256 / BIG_H, 6)
    # Centred on the click, in the preview's own fractions.
    assert abs(win["preview_x"] + win["preview_width"] / 2 - 0.25) < 0.002
    assert abs(win["preview_y"] + win["preview_height"] / 2 - 0.75) < 0.002


def test_the_preview_rectangle_is_measured_against_the_crop_not_the_canvas(
        client, built_library):
    """With a crop the two frames genuinely differ, and this is the pair of
    numbers that cannot be derived in the browser without a second copy of the
    mapping. A click at the centre of a preview cropped to the last 40 % of the
    width is 0.8 across the *canvas* and still 0.5 across the *preview*."""
    run_id = _big(client, built_library, basename="onpreviewcrop")
    cropped = _enc([*FLAT_RECIPE,
                    {"uid": "cr", "id": "geometry.crop", "enabled": True,
                     "params": {"x0": 0.6, "y0": 0.0, "x1": 1.0, "y1": 0.4}}])
    r = client.get(f"/api/targets/M_42/stack-runs/{run_id}/editor/loupe",
                   params={"recipe": cropped, "fx": 0.5, "fy": 0.5, "size": 256})
    assert r.status_code == 200, r.text
    win = _window(r)
    # Canvas-frame: 0.8 across. Preview-frame: still the middle.
    assert abs(win["x"] + 128 - 0.8 * BIG_W) <= 1
    assert abs(win["preview_x"] + win["preview_width"] / 2 - 0.5) < 0.005
    assert abs(win["preview_y"] + win["preview_height"] / 2 - 0.5) < 0.005
    # …and the window is a bigger share of a cropped preview than of the canvas.
    assert win["preview_width"] > win["width"] / BIG_W


def test_a_window_clamped_past_a_crops_edge_says_so_rather_than_sliding_inward(
        client, built_library):
    """The window is clamped inside the **canvas**, not inside the crop, so at the
    edge of a crop that touches the canvas edge it genuinely hangs over the side.
    Reporting a fraction outside 0..1 lets the caller draw it clipped, which is
    the truth; clamping here would draw it somewhere it is not."""
    run_id = _big(client, built_library, basename="onpreviewedge")
    # A crop flush against the right/bottom edge, narrower than the 256 px window.
    cropped = _enc([*FLAT_RECIPE,
                    {"uid": "cr", "id": "geometry.crop", "enabled": True,
                     "params": {"x0": 0.95, "y0": 0.95, "x1": 1.0, "y1": 1.0}}])
    r = client.get(f"/api/targets/M_42/stack-runs/{run_id}/editor/loupe",
                   params={"recipe": cropped, "fx": 1.0, "fy": 1.0, "size": 256})
    assert r.status_code == 200, r.text
    win = _window(r)
    assert win["preview_x"] < 0 and win["preview_width"] > 1
    # The canvas-frame answer is still correct and still inside the canvas.
    assert 0 <= win["x"] <= BIG_W - win["width"]


# --- the point of it: the window is the same picture --------------------------

def _overlap(preview: np.ndarray, loupe: np.ndarray, win: dict):
    """The preview pixels the window covers, beside the loupe pixels that are the
    very same source samples. The proxy is a strided decimation, so proxy pixel
    ``(i, j)`` *is* full pixel ``(i·step, j·step)`` — no interpolation involved on
    either side of this comparison."""
    y0, x0, h, w = win["y"], win["x"], win["height"], win["width"]
    i0, j0 = -(-y0 // STEP), -(-x0 // STEP)
    i1, j1 = (y0 + h - 1) // STEP + 1, (x0 + w - 1) // STEP + 1
    a = preview[i0:i1, j0:j1]
    b = loupe[i0 * STEP - y0::STEP, j0 * STEP - x0::STEP][:i1 - i0, :j1 - j0]
    assert a.shape == b.shape and a.size > 0
    return a, b


def test_the_window_is_the_same_picture_the_preview_is_showing(client, built_library):
    """The claim the whole three-slice project exists to make.

    A beginner tunes against the preview and judges at full size; if the two are
    different pictures, the loupe is worse than the advisories it replaces. With
    the whole-image fits frozen and the sky field replayed, the window reproduces
    the preview at every source pixel the two share — to within 8-bit rounding,
    which is all a PNG can carry.
    """
    run_id = _big(client, built_library, basename="parity")
    rec = _enc(FLAT_RECIPE)
    preview = _png(client.get(
        f"/api/targets/M_42/stack-runs/{run_id}/editor/preview", params={"recipe": rec}))
    r = client.get(f"/api/targets/M_42/stack-runs/{run_id}/editor/loupe",
                   params={"recipe": rec, "fx": 0.35, "fy": 0.6, "size": 256})
    assert r.status_code == 200, r.text

    a, b = _overlap(preview, _png(r), _window(r))
    # Measured: **0 of 255** — the shared samples come back byte-identical, against
    # 22.1 mean / 117 max for the naive window in the control below. The assertion
    # allows one level because a PNG is all the comparison can carry.
    assert np.abs(a - b).max() <= 1, f"max 8-bit difference {np.abs(a - b).max()}"


def test_without_the_frozen_channels_the_same_window_is_a_different_picture(
        client, built_library):
    """The control. Re-running the recipe over the window at ``proxy_scale = 1`` —
    the shape this feature would have taken without the two channels — fits the
    *window's* sky and stretch, and comes back visibly different. Without this
    assertion the test above could pass on a fixture too flat to show the problem.
    """
    from seestack.edit.pipeline import apply_recipe
    from seestack.edit.proxy import read_window_rgb
    from seestack.edit.recipe import recipe_from_dict
    from seestack.edit.registry import EditContext

    run_id = _big(client, built_library, basename="control")
    rec = _enc(FLAT_RECIPE)
    preview = _png(client.get(
        f"/api/targets/M_42/stack-runs/{run_id}/editor/preview", params={"recipe": rec}))
    r = client.get(f"/api/targets/M_42/stack-runs/{run_id}/editor/loupe",
                   params={"recipe": rec, "fx": 0.35, "fy": 0.6, "size": 256})
    win = _window(r)

    lib = Library.open_or_create(built_library / "library")
    try:
        proj = lib.open_target("M_42")
        try:
            fits_path = Path(proj.project_dir) / "output" / "control.fits"
        finally:
            proj.close()
    finally:
        lib.close()

    naive = apply_recipe(
        read_window_rgb(fits_path, win["y"], win["x"], win["height"], win["width"]),
        recipe_from_dict({"version": 1, "ops": FLAT_RECIPE}),
        EditContext(proxy_scale=1.0))
    naive8 = (np.clip(np.nan_to_num(naive), 0.0, 1.0) * 255).astype(np.int16)

    a, b = _overlap(preview, naive8, win)
    # Measured: 22.1 mean / 117 max of 255 — a different picture, not a rounding
    # difference, and exactly what a beginner would have been tuning against.
    assert np.abs(a - b).mean() > 3, (
        f"the naive window already matches ({np.abs(a - b).mean():.2f}/255) — "
        "the fixture's gradient is too kind to exhibit the problem")


# --- the window read ----------------------------------------------------------

def test_a_window_read_holds_exactly_the_canvas_pixels_it_covers(tmp_path):
    """``read_window_rgb`` exists so a 150 MP mosaic is never loaded to serve a few
    hundred pixels. It must still hold the same numbers a whole-file read would."""
    from seestack.edit.proxy import read_window_rgb, source_shape

    rng = np.random.default_rng(2)
    cube = rng.random((3, 60, 90)).astype(np.float32)
    fp = tmp_path / "canvas.fits"
    fits.writeto(fp, cube, overwrite=True)

    assert source_shape(fp) == (60, 90)
    got = read_window_rgb(fp, 12, 30, 20, 25)
    assert got.shape == (20, 25, 3)
    want = np.transpose(cube[:, 12:32, 30:55], (1, 2, 0))
    assert np.array_equal(got, want)


def test_a_mono_canvas_reads_as_three_equal_channels(tmp_path):
    """Matching ``_load_fits_rgb``: a 2-D stack is grey, not a crash."""
    from seestack.edit.proxy import read_window_rgb, source_shape

    plane = np.random.default_rng(4).random((40, 50)).astype(np.float32)
    fp = tmp_path / "mono.fits"
    fits.writeto(fp, plane, overwrite=True)

    assert source_shape(fp) == (40, 50)
    got = read_window_rgb(fp, 5, 6, 8, 9)
    assert got.shape == (8, 9, 3)
    for c in range(3):
        assert np.array_equal(got[..., c], plane[5:13, 6:15])
