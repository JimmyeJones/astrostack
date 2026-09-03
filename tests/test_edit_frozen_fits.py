"""Frozen fits: rendering one *region* of a picture the way the whole picture renders.

Four editor ops don't merely transform pixels — they first measure the **whole
image** and derive a number from it: the stretch takes each channel's robust
median and σ, auto-contrast reads the sky mode, colour calibration solves a white
balance from the star field, "Neutralize background" takes the sky's per-channel
medians. Hand any of them a 512×512 window and it fits *the window*, so the
window comes back stretched and colour-balanced differently from the picture it
was cut out of. That is why a render of a region cannot simply re-run the recipe
at ``proxy_scale = 1``.

``EditContext.fit`` is the channel that fixes it: a whole-image render records
what each op fitted, and a second render over a window is handed those values
instead of measuring its own. These tests pin both halves — that freezing changes
*nothing* when the array is the same one the fit was measured on, and that it is
what makes a crop agree with the frame — plus the control that says the fixture
can exhibit the problem at all: **unfrozen, the same crop visibly disagrees.**
"""

from __future__ import annotations

import numpy as np
import pytest

from seestack.edit.pipeline import apply_recipe
from seestack.edit.recipe import OpInstance, Recipe
from seestack.edit.registry import EditContext, get_op
from seestack.render.thumbnail import (
    asinh_stretch, autostretch, measure_stretch_stats,
)

_STAR_SIGMA_PX = 1.27
# The OSC sensor's own cast, and the sky's own (warm) colour — the two must
# differ, or a star-solved white balance and a starless one give the same answer
# and a fixture like that cannot show a divergence at all.
_SENSOR_CAST = (0.80, 1.0, 1.25)
_SKY_TINT = (1.18, 1.0, 0.88)

# The crop this file freezes onto. Deliberately placed **on the bright object**,
# not on empty sky: a window of representative sky would fit nearly the same
# numbers as the whole frame, and the test would pass without the freeze doing
# any work. A beginner zooms in on the interesting part, which is exactly the
# part whose own statistics are least like the picture's.
_CROP = (slice(60, 316), slice(120, 376))


def _synth_frame(h: int = 700, w: int = 1000, seed: int = 5) -> np.ndarray:
    """A linear OSC frame: tinted noisy sky, neutral stars, one bright galaxy."""
    rng = np.random.default_rng(seed)
    grey = rng.normal(0.0, 0.0015, size=(h, w)).astype(np.float32)

    rad = 6
    yy, xx = np.mgrid[-rad:rad + 1, -rad:rad + 1]
    kern = np.exp(-(xx ** 2 + yy ** 2) / (2 * _STAR_SIGMA_PX ** 2)).astype(np.float32)
    stars = np.zeros((h, w), dtype=np.float32)
    n_stars = 260
    ys = rng.integers(rad + 2, h - rad - 2, n_stars)
    xs = rng.integers(rad + 2, w - rad - 2, n_stars)
    amps = 10 ** rng.uniform(-1.4, -0.2, n_stars).astype(np.float32)
    for y, x, a in zip(ys, xs, amps, strict=True):
        stars[y - rad:y + rad + 1, x - rad:x + rad + 1] += a * kern

    # One bright, broad object sitting inside _CROP, so that window's median,
    # sky mode and star population are all unlike the frame's.
    oy, ox = np.mgrid[0:h, 0:w]
    obj = 0.10 * np.exp(-(((oy - 190) / 70.0) ** 2 + ((ox - 250) / 90.0) ** 2))

    rgb = np.empty((h, w, 3), dtype=np.float32)
    for c in range(3):
        rgb[..., c] = (0.05 * _SKY_TINT[c] + grey + stars + obj) * _SENSOR_CAST[c]
    return np.ascontiguousarray(rgb, dtype=np.float32)


def _recipe() -> Recipe:
    """Every op that fits from the whole image, plus two purely per-pixel ones.

    Kept to pointwise ops downstream on purpose: a spatial op (sharpen, denoise)
    reaches across the crop boundary, so its disagreement at a crop edge is a
    property of the crop, not of the fit — a separate question, and not this
    file's. With only pointwise ops left, frozen crop parity is *exact*, which is
    a far sharper assertion than "close enough".
    """
    return Recipe(ops=[
        OpInstance(id="tone.color_calibrate", params={"mode": "gray_star"}, uid="cc"),
        OpInstance(id="tone.stretch", params={"mode": "stf", "target_bg": 0.20}, uid="st"),
        OpInstance(id="tone.curves",
                   params={"points": [[0.0, 0.0], [1.0, 1.0]], "auto": True}, uid="cv"),
        OpInstance(id="tone.neutralize_background", params={"strength": 1.0}, uid="nb"),
        OpInstance(id="tone.saturation", params={"amount": 1.2}, uid="sa"),
        OpInstance(id="tone.levels", params={"black": 0.0, "white": 1.0, "gamma": 1.1},
                   uid="lv"),
    ])


def _render(rgb, recipe, *, frozen=None):
    ctx = EditContext(frozen_fits=frozen)
    out = apply_recipe(rgb.copy(), recipe, ctx)
    return out, ctx


# --- the channel itself ------------------------------------------------------

def test_fit_measures_and_records_when_nothing_is_frozen():
    ctx = EditContext(op_uid="a")
    assert ctx.fit("k", lambda: 7) == 7
    assert ctx.fitted == {"a:k": 7}


def test_fit_returns_the_frozen_value_without_measuring():
    calls = []

    def _compute():
        calls.append(1)
        return 7

    ctx = EditContext(op_uid="a", frozen_fits={"a:k": 99})
    assert ctx.fit("k", _compute) == 99
    assert calls == []            # the whole point: never measure the window
    assert ctx.fitted == {"a:k": 99}   # and it round-trips onward unchanged


def test_a_frozen_none_stays_none_rather_than_re_measuring():
    """``None`` is a real fitted value — "this image is too degenerate to anchor".
    If absence and ``None`` were the same thing, a window would quietly re-measure
    exactly where the frame gave up, which is the divergence this exists to stop."""
    calls = []
    ctx = EditContext(op_uid="a", frozen_fits={"a:k": None})
    assert ctx.fit("k", lambda: calls.append(1) or 7) is None
    assert calls == []


def test_fits_are_keyed_by_op_instance_not_op_id():
    """A recipe may carry the same op twice with different params — two stretches,
    two background passes. Keyed by id they would overwrite each other and the
    second would render with the first's numbers."""
    ctx = EditContext()
    ctx.op_uid = "first"
    ctx.fit("stretch_stats", lambda: "A")
    ctx.op_uid = "second"
    ctx.fit("stretch_stats", lambda: "B")
    assert ctx.fitted == {"first:stretch_stats": "A", "second:stretch_stats": "B"}


def test_the_pipeline_sets_and_clears_the_op_uid():
    rgb = _synth_frame(h=120, w=160)
    _out, ctx = _render(rgb, _recipe())
    assert ctx.op_uid is None                      # cleared after the last op
    assert {k.split(":")[0] for k in ctx.fitted} == {"cc", "st", "cv", "nb"}


# --- no behaviour change on the ordinary path --------------------------------

@pytest.mark.parametrize("target_bg", [0.14, 0.20, 0.25])
@pytest.mark.parametrize("protect", [0.0, 0.5])
def test_pinning_stf_to_its_own_measurement_is_the_unpinned_stretch(target_bg, protect):
    """``autostretch(x, stats=measure_stretch_stats(x))`` is byte-for-byte
    ``autostretch(x)`` — the same guarantee the asinh side already carries, so the
    two measurement sites cannot drift apart unnoticed."""
    rgb = _synth_frame(h=200, w=260)
    a = autostretch(rgb, target_bg=target_bg, highlight_protect=protect)
    b = autostretch(rgb, target_bg=target_bg, highlight_protect=protect,
                    stats=measure_stretch_stats(rgb))
    assert np.array_equal(a, b)


def test_measure_stretch_stats_serves_both_curves():
    """One measurement, either curve: the STF and asinh stretches normalise
    identically and anchor on the same robust per-channel (median, σ)."""
    rgb = _synth_frame(h=200, w=260)
    stats = measure_stretch_stats(rgb)
    assert np.array_equal(asinh_stretch(rgb),
                          asinh_stretch(rgb, stats=stats))
    assert np.array_equal(autostretch(rgb),
                          autostretch(rgb, stats=stats))


def test_a_recipe_render_is_unchanged_by_the_channel_existing():
    """The whole point of the defaults: with no frozen fits, every op measures for
    itself exactly as before. Pinned against a hand-run of the same ops."""
    rgb = _synth_frame(h=220, w=300)
    out, _ctx = _render(rgb, _recipe())

    ctx = EditContext()
    manual = rgb.copy()
    for op in _recipe().ops:
        ctx.op_uid = None                 # no uid keying — the direct-call path
        manual = get_op(op.id).apply(manual, op.params, ctx)
        if op.id == "tone.stretch":
            ctx.stage = "nonlinear"
    assert np.array_equal(np.nan_to_num(out), np.nan_to_num(manual))


def test_freezing_a_renders_own_fits_back_onto_it_changes_nothing():
    """The round trip that makes the channel safe to build on: what a render
    records, fed straight back to a render of the *same* array, reproduces it."""
    rgb = _synth_frame(h=260, w=340)
    first, ctx = _render(rgb, _recipe())
    second, _ = _render(rgb, _recipe(), frozen=ctx.fitted)
    assert np.array_equal(np.nan_to_num(first), np.nan_to_num(second))


# --- the reason it exists: a window renders like the picture ------------------

def _crop_of(img):
    return img[_CROP[0], _CROP[1]]


def test_an_unfrozen_crop_disagrees_with_the_picture_it_came_from():
    """The control, without which everything below could pass on a fixture that
    cannot exhibit the problem. Re-running the recipe over a window — the shape a
    "check it at full size" loupe would take if it just set ``proxy_scale = 1`` —
    produces a visibly different picture from the same pixels in the full render.
    """
    rgb = _synth_frame()
    full, _ = _render(rgb, _recipe())
    loose, _ = _render(rgb[_CROP[0], _CROP[1]], _recipe())

    diff = np.abs(np.nan_to_num(_crop_of(full)) - np.nan_to_num(loose))
    # Not a rounding difference: **0.40 mean, 0.57 max** on this fixture — most of
    # a tone, over most of the window. Frozen, the same comparison is exactly 0.0.
    assert diff.mean() > 0.02, f"crop is already faithful ({diff.mean():.4f}) — fixture is too kind"
    assert diff.max() > 0.05


def test_a_frozen_crop_reproduces_the_full_render_exactly():
    """Fit on the whole image, freeze onto a crop of it: the window's pixels are
    the picture's pixels. This is the property a full-resolution loupe rests on."""
    rgb = _synth_frame()
    full, ctx = _render(rgb, _recipe())
    windowed, _ = _render(rgb[_CROP[0], _CROP[1]], _recipe(), frozen=ctx.fitted)

    assert windowed.shape[:2] == (_CROP[0].stop - _CROP[0].start,
                                  _CROP[1].stop - _CROP[1].start)
    # Every op left in the recipe is pointwise once its fit is frozen, so this is
    # exact rather than approximate — a much sharper statement than a tolerance.
    assert np.array_equal(np.nan_to_num(_crop_of(full)), np.nan_to_num(windowed))


@pytest.mark.parametrize("crop", [
    (slice(0, 200), slice(0, 200)),          # a corner of plain sky
    (slice(150, 250), slice(200, 300)),      # the object's core
    (slice(400, 700), slice(600, 1000)),     # the far side of the frame
])
def test_frozen_parity_holds_wherever_the_window_is_taken(crop):
    rgb = _synth_frame()
    full, ctx = _render(rgb, _recipe())
    windowed, _ = _render(rgb[crop[0], crop[1]], _recipe(), frozen=ctx.fitted)
    assert np.array_equal(np.nan_to_num(full[crop[0], crop[1]]),
                          np.nan_to_num(windowed))


def test_a_frozen_white_balance_is_re_applied_without_re_solving():
    """Colour calibration's fit is a solve over the star field, and by far the
    op's dominant cost. A frozen one must be *applied*, not re-derived — both
    because a window holds different stars and because re-solving would make a
    loupe as slow as a second full render."""
    rgb = _synth_frame()
    _full, ctx = _render(rgb, _recipe())
    solved = ctx.fitted["cc:white_balance"]
    assert solved.mode_used == "gray_star", "fixture must actually reach a star solve"

    spec = get_op("tone.color_calibrate")
    window = rgb[_CROP[0], _CROP[1]]
    frozen_ctx = EditContext(op_uid="cc", frozen_fits={"cc:white_balance": solved})
    out = spec.apply(window.copy(), {"mode": "gray_star"}, frozen_ctx)

    for c in range(3):
        np.testing.assert_allclose(out[..., c], window[..., c] * solved.scale_rgb[c],
                                   rtol=1e-6)
    # …and the note the editor captions from carries the frozen solve's facts,
    # not a fresh window-sized one.
    assert frozen_ctx.op_notes["tone.color_calibrate"]["mode_used"] == "gray_star"
    assert frozen_ctx.op_notes["tone.color_calibrate"]["n_stars_used"] == solved.n_stars_used
