"""Direct pixel-transform tests for editor ops that had none.

seestack/bg/per_frame.py, final_gradient.py, and coverage_leveling.py each
have their own dedicated test files already covering the underlying math.
What's untested is the thin seestack/edit/ops wrapper around them: does it
actually forward recipe params through to the underlying function, and does
its own wrapper-only logic (the ctx.coverage-is-None early return, NaN
handling) behave correctly? seestack/edit/ops/stars.py has no underlying
module test at all — its erosion-based reduction is only exercised here.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("astropy")
pytest.importorskip("photutils")
pytest.importorskip("scipy")

from seestack.edit.registry import EditContext, get_op


def _flat_field_with_star(h=40, w=40, sky=0.2, peak=0.9, cx=20, cy=20):
    rgb = np.full((h, w, 3), sky, dtype=np.float32)
    rgb[cy - 1:cy + 2, cx - 1:cx + 2, :] = peak
    return rgb


# ---- stars.reduce ---------------------------------------------------------

def test_stars_reduce_shrinks_peak_leaves_background():
    rgb = _flat_field_with_star()
    op = get_op("stars.reduce")
    out = op.apply(rgb, {"amount": 0.8, "size": 2}, EditContext())

    assert out[20, 20, 0] < rgb[20, 20, 0], "star core should be pulled down"
    # Far from the star, the flat background must be untouched.
    assert np.allclose(out[2:6, 2:6, :], rgb[2:6, 2:6, :])


def test_stars_reduce_amount_zero_is_noop():
    rgb = _flat_field_with_star()
    op = get_op("stars.reduce")
    out = op.apply(rgb, {"amount": 0.0, "size": 2}, EditContext())
    assert np.array_equal(out, rgb)


def test_stars_reduce_larger_amount_reduces_more():
    rgb = _flat_field_with_star()
    op = get_op("stars.reduce")
    mild = op.apply(rgb, {"amount": 0.2, "size": 2}, EditContext())
    strong = op.apply(rgb, {"amount": 1.0, "size": 2}, EditContext())
    assert strong[20, 20, 0] < mild[20, 20, 0]


def test_stars_reduce_preserves_nan_gaps():
    rgb = _flat_field_with_star()
    rgb[:5, :, :] = np.nan  # e.g. an uncovered mosaic border
    op = get_op("stars.reduce")
    out = op.apply(rgb, {"amount": 0.8, "size": 2}, EditContext())
    assert np.all(np.isnan(out[:5, :, :]))


# ---- background.subtract ---------------------------------------------------

def _gradient_field(h=200, w=280, seed=7):
    rng = np.random.default_rng(seed)
    yy, xx = np.indices((h, w), dtype=np.float32)
    grad = (xx / w) * 200 + 1000
    noise = rng.normal(0, 8, size=(h, w)).astype(np.float32)
    return np.repeat((grad + noise)[..., None], 3, axis=-1)


def test_background_subtract_flattens_gradient():
    rgb = _gradient_field()
    op = get_op("background.subtract")
    out = op.apply(rgb, {"box_size": 32, "mode": "per_channel"}, EditContext())
    # Flattening should shrink the corner-to-corner spread a lot.
    assert (out[:, -1, 0].mean() - out[:, 0, 0].mean()) < (rgb[:, -1, 0].mean() - rgb[:, 0, 0].mean()) * 0.3


def test_background_subtract_forwards_box_size_param():
    rgb = _gradient_field()
    op = get_op("background.subtract")
    small_box = op.apply(rgb, {"box_size": 32}, EditContext())
    large_box = op.apply(rgb, {"box_size": 256}, EditContext())
    # Different box sizes fit a different background model — results diverge.
    assert not np.allclose(small_box, large_box, atol=1e-3)


# ---- background.final_gradient --------------------------------------------

def _gradient_with_bright_object(h=200, w=280, seed=3):
    rgb = _gradient_field(h, w, seed)
    rgb[h // 2 - 10:h // 2 + 10, w // 2 - 10:w // 2 + 10, :] += 4000.0
    return rgb


def test_final_gradient_flattens_sky_and_keeps_object_bright():
    rgb = _gradient_with_bright_object()
    op = get_op("background.final_gradient")
    out = op.apply(rgb, {"mode": "luminance", "box_size": 64}, EditContext())
    # The fitted background model should collapse the whole-frame median
    # close to zero even though the input had a ~200 ADU gradient baseline.
    assert abs(float(np.median(out[..., 0]))) < 60
    # The masked object should still stand out above the flattened sky.
    obj = out[90:110, 130:150, 0].mean()
    sky = out[5:15, 5:15, 0].mean()
    assert obj - sky > 2000.0


# ---- background.level_coverage ---------------------------------------------

def test_level_coverage_is_noop_without_coverage_in_context():
    rgb = _gradient_field()
    op = get_op("background.level_coverage")
    out = op.apply(rgb, {}, EditContext(coverage=None))
    assert np.array_equal(out, rgb)


def test_level_coverage_uses_context_coverage_to_flatten_panel_offsets():
    h, w = 120, 240
    rng = np.random.default_rng(1)
    rgb = rng.normal(0.0, 5.0, size=(h, w, 3)).astype(np.float32)
    coverage = np.zeros((h, w), dtype=np.int32)
    coverage[:, w // 2:] = 3
    rgb[:, w // 2:, :] += 200.0  # right half panel sits 200 ADU brighter

    op = get_op("background.level_coverage")
    out = op.apply(rgb, {}, EditContext(coverage=coverage))

    before_gap = abs(rgb[:, w // 2:, 0].mean() - rgb[:, :w // 2, 0].mean())
    after_gap = abs(out[:, w // 2:, 0].mean() - out[:, :w // 2, 0].mean())
    assert after_gap < before_gap * 0.3


def test_level_coverage_skips_on_shape_mismatch_instead_of_crashing():
    # A geometry op (crop/resize) earlier in the recipe can change the frame shape
    # so it no longer matches the native-geometry coverage map. The op must skip
    # (return the input unchanged) rather than raise and blank the render.
    rgb = _gradient_field()  # e.g. 120x240
    coverage = np.ones((rgb.shape[0] + 7, rgb.shape[1] - 5), dtype=np.int32)
    op = get_op("background.level_coverage")
    out = op.apply(rgb, {}, EditContext(coverage=coverage))
    assert np.array_equal(out, rgb)


# ---- geometry.resize degenerate-shape guard -------------------------------

def test_resize_never_collapses_an_axis_to_zero():
    # A heavy downscale of a thin frame (a sliver crop on the proxy, or a small
    # proxy) used to drive round(dim*scale) to 0, yielding an empty image that
    # then crashed the PNG/export render ("cannot write empty image"). Every axis
    # must stay >= 1 px regardless of how extreme the downscale is.
    op = get_op("geometry.resize")
    for shape, scale in [((2, 50, 3), 0.1), ((8, 8, 3), 0.1), ((3, 3, 3), 0.1)]:
        out = np.asarray(op.apply(np.ones(shape, np.float32), {"scale": scale},
                                  EditContext()))
        assert out.ndim == 3 and 0 not in out.shape, (shape, scale, out.shape)


def test_crop_then_resize_stays_renderable():
    # The end-to-end path that produced the empty image: stretch → thin crop
    # (survives the crop's >=2px guard) → downscale. The pipeline output must be a
    # non-empty display-space image that PIL can encode to a PNG.
    import io

    from PIL import Image

    from seestack.edit.pipeline import apply_recipe
    from seestack.edit.recipe import OpInstance, Recipe, validate_ops

    rng = np.random.default_rng(3)
    img = (rng.random((200, 200, 3)) * 0.4).astype(np.float32)
    ops = validate_ops([
        OpInstance(id="tone.stretch", params={"mode": "stf"}),
        OpInstance(id="geometry.crop", params={"x0": 0.0, "y0": 0.5, "x1": 1.0, "y1": 0.51}),
        OpInstance(id="geometry.resize", params={"scale": 0.1}),
    ])
    out = np.asarray(apply_recipe(img.copy(), Recipe(ops=ops), EditContext()))
    assert 0 not in out.shape
    u8 = (np.clip(np.nan_to_num(out), 0.0, 1.0) * 255).astype(np.uint8)
    Image.fromarray(u8, mode="RGB").save(io.BytesIO(), format="PNG")  # must not raise


# ---- geometry.resize: a shrink averages, it does not point-sample ----------

def _resize(img, scale):
    return np.asarray(get_op("geometry.resize").apply(img, {"scale": scale}, EditContext()))


def test_resize_shrink_averages_the_sky_noise_away():
    # A bare order-1 zoom lands each output pixel on ~one input pixel, so a
    # 0.25x "Resize" came out exactly as grainy as full size (std 0.67 sigma).
    # A real downscale averages what it drops: sigma/4 in theory.
    rng = np.random.default_rng(1)
    img = (0.1 + 0.01 * rng.standard_normal((400, 600, 3))).astype(np.float32)
    out = _resize(img, 0.25)
    assert out.shape == (100, 150, 3)
    assert float(np.std(out[..., 0])) < 0.35 * 0.01
    assert abs(float(np.mean(out)) - 0.1) < 1e-3  # level preserved


def test_resize_shrink_keeps_every_star_at_its_brightness():
    # Point-sampling let a star's brightness swing with its sub-pixel phase:
    # measured +-41 % (coefficient of variation) at 0.25x, some nearly gone.
    rng = np.random.default_rng(2)
    h, w = 480, 640
    yy, xx = np.mgrid[0:h, 0:w]
    sig = 2.5 / 2.355
    field = np.zeros((h, w), np.float32)
    centres = [(y + rng.random() * 4, x + rng.random() * 4)
               for y in range(20, h - 20, 40) for x in range(20, w - 20, 40)]
    for cy, cx in centres:
        sl = (slice(int(cy) - 6, int(cy) + 7), slice(int(cx) - 6, int(cx) + 7))
        field[sl] += np.exp(-((yy[sl] - cy) ** 2 + (xx[sl] - cx) ** 2) / (2 * sig * sig))
    out = _resize(np.stack([field] * 3, axis=-1), 0.25)[..., 0]
    flux = np.array([out[int(round(cy / 4)) - 2:int(round(cy / 4)) + 3,
                         int(round(cx / 4)) - 2:int(round(cx / 4)) + 3].sum()
                     for cy, cx in centres])
    assert flux.std() / flux.mean() < 0.1
    assert flux.min() > 0.75 * flux.mean()


def test_resize_shrink_keeps_coverage_and_does_not_darken_a_mosaic_edge():
    # NaN = no coverage: the anti-alias blur must neither eat into covered sky
    # next to a gap (zeros bleeding in would darken it) nor fill the gap.
    from scipy.ndimage import zoom

    img = np.full((200, 300, 3), 0.2, dtype=np.float32)
    img[:, :130] = np.nan          # an uncovered mosaic border
    img[150:, 200:, 1] = np.nan    # and a gap in one channel only
    out = _resize(img, 0.5)
    bare = zoom(img, (0.5, 0.5, 1.0), order=1)
    # The covered area (finite in every channel) is the area it always was.
    assert np.array_equal(np.isnan(out).any(axis=2), np.isnan(bare).any(axis=2))
    # Channel 0 has only the border gap; channel 1's extra gap stays in channel 1.
    assert np.array_equal(np.isnan(out[..., 1]), np.isnan(bare[..., 1]))
    assert np.isnan(out[..., 0]).sum() < np.isnan(out[..., 1]).sum()
    assert np.allclose(out[np.isfinite(out)], 0.2, atol=1e-5)


def test_resize_enlarge_is_unchanged():
    from scipy.ndimage import zoom

    rng = np.random.default_rng(3)
    img = rng.random((40, 60, 3)).astype(np.float32)
    img[:5, :5] = np.nan
    out = _resize(img, 1.5)
    assert np.array_equal(out, zoom(img, (60 / 40, 90 / 60, 1.0), order=1).astype(np.float32),
                          equal_nan=True)
