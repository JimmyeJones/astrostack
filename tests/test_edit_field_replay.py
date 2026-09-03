"""Replayed fields: rendering one *window* of a picture the way the picture renders.

The second half of what a full-resolution loupe needs. ``EditContext.fit``
(v0.328.2) carries a *scalar* an op measured from the whole image — a stretch's
median and σ, a white balance, a sky mode. The three ``background.*`` ops cannot
use it, because what they fit is a **spatial model**: a mesh over the whole
canvas, a per-coverage-level offset. Handed a 512×512 window they fit *the
window*, so the window comes back with a different sky subtracted from the one
the picture got — and Auto always contains ``background.final_gradient``, so
without this a loupe would be honest only for a recipe that has none.

All three ops are purely additive (see ``ops/background.py``), so the thing worth
carrying is the field itself, measured as ``after − before``. A field is not a
number, so it remembers the grid it was measured on — ``(source_origin,
proxy_scale)`` — and is resampled onto whatever grid replays it. The two grids
that matter are the same picture cropped (a crop of the proxy) and the same
picture at full resolution (the loupe), and the proxy is a plain strided
decimation, so proxy pixel ``(i, j)`` *is* full pixel ``(i·step, j·step)`` and
the mapping needs no guessing.

These pin: that nothing moves on the ordinary path; that a crop rendered with the
replayed field reproduces the picture's own pixels; the **control** that says the
fixture can exhibit the problem at all (unfrozen, the same crop visibly
disagrees); that a full-resolution window agrees with the preview it was opened
from, at the pixels the two actually share; and that an uncovered region stays
uncovered instead of bleeding through the interpolation.
"""

from __future__ import annotations

import numpy as np
import pytest

from seestack.edit.pipeline import apply_recipe
from seestack.edit.recipe import OpInstance, Recipe
from seestack.edit.registry import EditContext, FieldDelta, get_op

# The crop these tests freeze onto. On the bright object on purpose: a window of
# representative sky would have nearly the picture's own gradient in it and the
# test would pass without the replay doing any work.
_CROP = (slice(60, 316), slice(120, 376))


def _synth_frame(h: int = 700, w: int = 1000, seed: int = 11) -> np.ndarray:
    """A linear OSC frame with a strong, *asymmetric* light-pollution gradient.

    The gradient is what the background ops are for, and it has to vary across
    the frame — a flat offset would be fitted identically on any window, and none
    of this would be needed.
    """
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:h, 0:w]
    ny, nx = yy / max(h - 1, 1), xx / max(w - 1, 1)
    # A tilted, curved sky: brighter towards one corner, per channel differently
    # (light pollution is not grey).
    grad = 0.02 + 0.05 * nx + 0.03 * ny + 0.02 * (nx - 0.5) ** 2

    rad = 6
    ky, kx = np.mgrid[-rad:rad + 1, -rad:rad + 1]
    kern = np.exp(-(kx ** 2 + ky ** 2) / (2 * 1.27 ** 2)).astype(np.float32)
    stars = np.zeros((h, w), dtype=np.float32)
    ys = rng.integers(rad + 2, h - rad - 2, 240)
    xs = rng.integers(rad + 2, w - rad - 2, 240)
    amps = 10 ** rng.uniform(-1.4, -0.3, 240).astype(np.float32)
    for y, x, a in zip(ys, xs, amps, strict=True):
        stars[y - rad:y + rad + 1, x - rad:x + rad + 1] += a * kern

    obj = 0.08 * np.exp(-(((yy - 190) / 70.0) ** 2 + ((xx - 250) / 90.0) ** 2))
    noise = rng.normal(0.0, 0.0012, size=(h, w)).astype(np.float32)

    tint = (1.15, 1.0, 0.85)
    rgb = np.empty((h, w, 3), dtype=np.float32)
    for c in range(3):
        rgb[..., c] = grad * tint[c] + noise + stars + obj
    return np.ascontiguousarray(rgb, dtype=np.float32)


def _recipe() -> Recipe:
    """A gradient pass, then pointwise tone ops whose fits are frozen too.

    Both channels have to be in play together: a window's *tone* is frozen by
    ``fit`` and its *sky* by the field replay, and a loupe that got one without
    the other would still be a different picture. Downstream ops are kept
    pointwise so the comparison below is a statement about the field, not about a
    spatial op reaching across a crop edge.
    """
    return Recipe(ops=[
        OpInstance(id="background.final_gradient",
                   params={"mode": "per_channel", "box_size": 128}, uid="bg"),
        OpInstance(id="tone.stretch", params={"mode": "stf", "target_bg": 0.20}, uid="st"),
        OpInstance(id="tone.levels", params={"black": 0.0, "white": 1.0, "gamma": 1.1},
                   uid="lv"),
    ])


def _render(rgb, recipe, *, frozen=None, deltas=None, capture=False,
            origin=(0.0, 0.0), scale=1.0):
    ctx = EditContext(frozen_fits=frozen, frozen_deltas=deltas,
                      capture_fields=capture, source_origin=origin,
                      proxy_scale=scale)
    out = apply_recipe(rgb.copy(), recipe, ctx)
    return out, ctx


def _num(a):
    return np.nan_to_num(a)


# --- nothing moves on the ordinary path --------------------------------------

def test_a_render_is_byte_for_byte_unchanged_by_the_channel_existing():
    """With no capture and no frozen deltas, every additive op runs exactly as it
    always did — pinned against a hand-run of the same ops."""
    rgb = _synth_frame(h=220, w=300)
    out, ctx = _render(rgb, _recipe())
    assert ctx.field_deltas == {}      # capture is off by default

    manual = rgb.copy()
    hand = EditContext()
    for op in _recipe().ops:
        manual = get_op(op.id).apply(manual, op.params, hand)
        if op.id == "tone.stretch":
            hand.stage = "nonlinear"
    assert np.array_equal(_num(out), _num(manual))


def test_capturing_a_field_does_not_change_the_render_it_was_captured_from():
    rgb = _synth_frame(h=220, w=300)
    plain, _ = _render(rgb, _recipe())
    captured, ctx = _render(rgb, _recipe(), capture=True)
    assert np.array_equal(_num(plain), _num(captured))
    assert set(ctx.field_deltas) == {"bg"}
    assert ctx.field_deltas["bg"].delta.shape == rgb.shape


def test_only_the_additive_ops_declare_themselves_so():
    """The flag is a claim about engine code (see ``ops/background.py``); a new op
    must not acquire it by accident."""
    from seestack.edit.registry import all_specs

    additive = {s.id for s in all_specs() if s.additive_field}
    assert additive == {"background.subtract", "background.final_gradient",
                        "background.level_coverage"}


def test_a_field_is_keyed_by_op_instance_so_two_passes_dont_overwrite():
    """A recipe may legitimately carry two background passes; keyed by op id the
    second would be replayed with the first's field."""
    rgb = _synth_frame(h=200, w=260)
    twice = Recipe(ops=[
        OpInstance(id="background.final_gradient", params={"box_size": 128}, uid="one"),
        OpInstance(id="background.subtract", params={"box_size": 96}, uid="two"),
    ])
    _out, ctx = _render(rgb, twice, capture=True)
    assert set(ctx.field_deltas) == {"one", "two"}
    a, b = ctx.field_deltas["one"].delta, ctx.field_deltas["two"].delta
    assert not np.allclose(_num(a), _num(b))


# --- the reason it exists: a window renders like the picture ------------------

def test_an_unreplayed_crop_disagrees_with_the_picture_it_came_from():
    """The control. Re-running the recipe over a window — the shape the loupe
    would take if it just set ``proxy_scale = 1`` — fits the *window's* sky, so
    the same pixels come out different. Without this assertion every test below
    could pass on a fixture too flat to show the problem."""
    rgb = _synth_frame()
    full, ctx = _render(rgb, _recipe(), capture=True)
    loose, _ = _render(rgb[_CROP[0], _CROP[1]], _recipe(), frozen=ctx.fitted)

    diff = np.abs(_num(full[_CROP[0], _CROP[1]]) - _num(loose))
    # Measured: 0.207 mean, 0.520 max of a 0–1 tone. A fifth of the range, over
    # the whole window — not a subtlety.
    assert diff.mean() > 0.02, (
        f"crop is already faithful ({diff.mean():.4f}) — the fixture's gradient is too kind")
    assert diff.max() > 0.1


def test_a_replayed_crop_reproduces_the_full_render():
    """Fit on the whole image, replay onto a crop of it: the window's pixels are
    the picture's pixels. This is the property a full-size loupe rests on."""
    rgb = _synth_frame()
    full, ctx = _render(rgb, _recipe(), capture=True)
    window, _ = _render(rgb[_CROP[0], _CROP[1]], _recipe(),
                        frozen=ctx.fitted, deltas=ctx.field_deltas,
                        origin=(float(_CROP[0].start), float(_CROP[1].start)))

    assert window.shape[:2] == (_CROP[0].stop - _CROP[0].start,
                                _CROP[1].stop - _CROP[1].start)
    # Measured: **exactly 0.0** on this fixture, against a control of 0.207 mean
    # / 0.520 max. The tolerance is there because the field travels as
    # `after − before` in float32 and `a + (b − a)` is only guaranteed to round
    # back to `b` when the two are within a factor of two — true of a sky
    # correction and its sky, but not something to assert of arbitrary data.
    np.testing.assert_allclose(_num(full[_CROP[0], _CROP[1]]), _num(window), atol=2e-5)


@pytest.mark.parametrize("crop", [
    (slice(0, 200), slice(0, 200)),          # a corner of plain sky
    (slice(150, 250), slice(200, 300)),      # the object's core
    (slice(400, 700), slice(600, 1000)),     # the far side of the frame
])
def test_replayed_parity_holds_wherever_the_window_is_taken(crop):
    rgb = _synth_frame()
    full, ctx = _render(rgb, _recipe(), capture=True)
    window, _ = _render(rgb[crop[0], crop[1]], _recipe(),
                        frozen=ctx.fitted, deltas=ctx.field_deltas,
                        origin=(float(crop[0].start), float(crop[1].start)))
    np.testing.assert_allclose(_num(full[crop[0], crop[1]]), _num(window), atol=2e-5)


def test_a_full_res_window_agrees_with_the_preview_it_was_opened_from():
    """The loupe's actual geometry, and the sharpest thing this file says.

    The preview is a strided proxy of the picture; the loupe is a small window of
    the picture at full resolution. Proxy pixel ``(i, j)`` *is* full pixel
    ``(i·step, j·step)``, so every proxy pixel inside the window has a full-res
    pixel holding the very same data — and with the sky field replayed and the
    tone fits frozen, the loupe must reproduce the preview at exactly those
    pixels. Anything else means the beginner is tuning against one picture and
    judging another.
    """
    step = 2
    full_rgb = _synth_frame()
    proxy = np.ascontiguousarray(full_rgb[::step, ::step])

    preview, ctx = _render(proxy, _recipe(), capture=True, scale=float(step))

    y0, x0, side = 200, 300, 256          # a full-res window on the object's edge
    window_rgb = full_rgb[y0:y0 + side, x0:x0 + side]
    loupe, _ = _render(window_rgb, _recipe(), frozen=ctx.fitted,
                       deltas=ctx.field_deltas, origin=(float(y0), float(x0)))

    # The preview pixels the window covers, and the loupe pixels that are the
    # very same source samples.
    pi0, pj0 = -(-y0 // step), -(-x0 // step)     # first proxy index inside
    pi1, pj1 = (y0 + side - 1) // step + 1, (x0 + side - 1) // step + 1
    from_preview = preview[pi0:pi1, pj0:pj1]
    from_loupe = loupe[pi0 * step - y0::step, pj0 * step - x0::step][
        :pi1 - pi0, :pj1 - pj0]

    assert from_preview.shape == from_loupe.shape
    np.testing.assert_allclose(_num(from_preview), _num(from_loupe), atol=2e-5)


def test_without_the_replay_the_same_full_res_window_does_not_agree():
    """The control for the test above: re-fitting on the window (frozen tone, but
    the sky refitted) leaves a visible disagreement with the preview."""
    step = 2
    full_rgb = _synth_frame()
    proxy = np.ascontiguousarray(full_rgb[::step, ::step])
    preview, ctx = _render(proxy, _recipe(), capture=True, scale=float(step))

    y0, x0, side = 200, 300, 256
    loose, _ = _render(full_rgb[y0:y0 + side, x0:x0 + side], _recipe(),
                       frozen=ctx.fitted)

    pi0, pj0 = -(-y0 // step), -(-x0 // step)
    pi1, pj1 = (y0 + side - 1) // step + 1, (x0 + side - 1) // step + 1
    a = _num(preview[pi0:pi1, pj0:pj1])
    b = _num(loose[pi0 * step - y0::step, pj0 * step - x0::step][:pi1 - pi0, :pj1 - pj0])
    # Measured: 0.040 mean, 0.140 max, against 0.0 with the field replayed.
    assert np.abs(a - b).mean() > 0.02


# --- coverage holes must not bleed through the interpolation ------------------

def test_an_uncovered_region_stays_uncovered_and_does_not_spread():
    """A field is ``NaN`` exactly where the picture is, and bilinear interpolation
    spreads a ``NaN`` into its neighbours — which would turn covered pixels at a
    mosaic's edge into holes. The fill happens before interpolation; the filled
    values only ever land on pixels that are ``NaN`` in the picture anyway."""
    rgb = _synth_frame(h=400, w=520)
    rgb[:80, :] = np.nan                     # an uncovered strip, mosaic-shaped

    full, ctx = _render(rgb, _recipe(), capture=True)
    crop = (slice(40, 240), slice(100, 340))  # straddles the edge of the hole
    window, _ = _render(rgb[crop[0], crop[1]], _recipe(),
                        frozen=ctx.fitted, deltas=ctx.field_deltas,
                        origin=(float(crop[0].start), float(crop[1].start)))

    covered = np.isfinite(full[crop[0], crop[1]])
    assert np.array_equal(np.isfinite(window), covered), "coverage changed shape"
    assert covered.any() and not covered.all(), "fixture must straddle the edge"
    np.testing.assert_allclose(_num(full[crop[0], crop[1]]), _num(window), atol=2e-5)


def test_a_wholly_uncovered_field_replays_as_no_correction():
    """Degenerate, but reachable: a field with nothing finite in it must correct
    nothing rather than propagate NaN into the window."""
    ctx = EditContext()
    fd = FieldDelta(delta=np.full((8, 8, 3), np.nan, dtype=np.float32))
    replayed = ctx.replay_field(fd, (4, 4, 3))
    assert replayed.shape == (4, 4, 3)
    assert np.all(replayed == 0.0)


def test_replaying_onto_the_same_grid_returns_the_field_itself():
    """The identity case the crop tests rest on: coincident grids mean every
    lookup lands on an exact sample, so no interpolation error enters at all."""
    rng = np.random.default_rng(3)
    fd = FieldDelta(delta=rng.normal(size=(9, 11, 3)).astype(np.float32))
    got = EditContext().replay_field(fd, (9, 11, 3))
    assert np.array_equal(got, fd.delta)
