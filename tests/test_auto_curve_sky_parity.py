"""Auto's contrast curve must not move the sky — measured through *real*
``autostretch`` output, not a synthesised approximation of it.

This is the regression test the 2026-09-02 external audit's A1 finding says was
missing. The pre-existing guard (``test_sky_dominated_frame_does_not_lift_the_sky``
in ``tests/test_edit_curve.py``) builds its fixture as ``clip(sky + normal)`` — a
smooth distribution with **no hard-clip spike** — so it could never exhibit the
bug it was written to catch:

``tone.stretch`` (mode ``stf``) clips its shadows at ``median − 2σ``, landing 1–2 %
of an ordinary Seestar stack on **exactly 0.0**. That spike was always the tallest
bin of ``_sky_mode``'s histogram, so the sky read as ~0.0008, the "the median *is*
the sky, so decline" gate never fired, and Auto lifted the median — which is the
sky — halfway toward ``CURVE_TARGET_BG``. Measured +19 % here, +36 % through the
full Auto recipe in the audit. The other branch was wrong too: once the gate *did*
fire, the fixed fallback S-curve mapped 0.25→0.20 and **darkened** the same sky.

Everything below therefore starts from a linear stack and runs the real stretch.
"""

from __future__ import annotations

import numpy as np
import pytest

from seestack.edit.curve import _sky_mode, fallback_tone_curve, suggest_tone_curve
from seestack.edit.ops.tone import _curves
from seestack.render.thumbnail import autostretch

# A generous corner of every scene below is pure background: no object, no star.
_SKY_PATCH = (slice(0, 60), slice(0, 60))


def _linear_stack(*, sky=0.02, noise=0.001, obj=0.05, stars=400, h=600, w=800, seed=7):
    """A linear (pre-stretch) OSC stack: a faint noisy sky, an extended object, and
    a Pareto-brightness starfield — the shape a Seestar sub-stack has when it
    reaches the editor.

    The starfield is deliberately dense enough that the frame's 99.5th percentile
    lands on *stars* (~3.5× the sky), which is what the real dynamic range of a
    stack looks like and what ``autostretch`` normalises against. A star-poor
    fixture normalises against the sky itself and produces an unrealistically wide
    display-space background — the kind of detail that makes a synthetic test agree
    with a bug instead of the world."""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:h, 0:w]
    img = sky + rng.normal(0.0, noise, (h, w))
    img += obj * np.exp(-(((xx - w / 2) / 160.0) ** 2 + ((yy - h / 2) / 120.0) ** 2))
    for _ in range(stars):
        cy, cx = int(rng.integers(2, h - 2)), int(rng.integers(2, w - 2))
        img[cy - 1:cy + 2, cx - 1:cx + 2] += 0.02 * (float(rng.pareto(1.2)) + 1.0)
    return np.clip(np.repeat(img[..., None], 3, axis=2), 0.0, None).astype("float32")


def _stretched(**kw):
    """The image exactly as it enters ``tone.curves`` in the Auto recipe: the real
    per-channel STF stretch, shadow clip and all."""
    return autostretch(_linear_stack(**kw), target_bg=0.18)


def _sky_level(img):
    patch = img[_SKY_PATCH + (1,)]
    return float(np.median(patch[np.isfinite(patch)]))


def _auto(img):
    """Apply the Curves op the way Auto does: auto=True on an untouched identity."""
    return _curves(img, {"points": [[0.0, 0.0], [1.0, 1.0]], "auto": True}, None)


def test_the_fixture_really_does_carry_a_hard_clip_spike():
    """Guard the guard: if the stretch ever stops clipping to a floor spike, the
    tests below would pass for the wrong reason. Assert the bug's precondition — and
    note *where* it appears. The clip bites when the frame's median is the sky
    (``shadows = median − 2σ`` then lands inside the background), i.e. on exactly
    the sky-dominated deep-sky frames the owner mostly shoots; a frame with a big
    bright object has its median dragged clear and barely clips at all."""
    img = _stretched(obj=0.0)
    finite = img[np.isfinite(img)]
    floor = float(finite.min())
    assert float((finite == floor).mean()) > 0.005, \
        "the STF shadow clip must pile ≥0.5% of a sky-dominated frame on the floor"
    assert float(np.percentile(finite, 0.5)) == pytest.approx(floor, abs=1e-6)


def test_sky_mode_reads_the_sky_not_the_clip_spike():
    """A1's mechanism, at the smallest unit: the mode must land on the stretched sky
    (the stretch's own target), not on the clipped floor — which is where it landed
    before, reading 0.0008 for a 0.18 sky."""
    img = _stretched(obj=0.0)
    finite = img[np.isfinite(img)]
    assert _sky_mode(finite) == pytest.approx(_sky_level(img), abs=0.02)


@pytest.mark.parametrize("target_bg", [0.15, 0.18, 0.22, 0.25])
@pytest.mark.parametrize("obj", [0.0, 0.05, 0.5], ids=["bare-sky", "faint-obj", "bright-obj"])
def test_auto_curve_does_not_move_the_sky_at_any_stretch_target(target_bg, obj):
    """The contract, end to end, across the stretch targets Auto actually uses and
    the three scene shapes that pick different branches of the curve: whatever
    branch it takes, the sky comes out where the stretch put it."""
    img = autostretch(_linear_stack(obj=obj), target_bg=target_bg)
    before = _sky_level(img)
    after = _sky_level(_auto(img))
    assert abs(after - before) / before < 0.02, (
        f"Auto moved the sky {before:.4f} → {after:.4f} "
        f"({100 * (after - before) / before:+.1f}%) at target_bg={target_bg}, obj={obj}")


@pytest.mark.parametrize("n_subs", [4, 40, 400])
def test_the_sky_stays_put_at_every_stack_depth(n_subs):
    """The audit measured the identical bad control point at every depth from 4 to
    1,000 subs — deeper stacking made the sky cleaner but not safer. Model depth as
    the shrinking read noise of an N-sub average, on the sky-dominated shape where
    the clip spike is largest."""
    img = autostretch(_linear_stack(obj=0.0, noise=0.002 * 4 / np.sqrt(n_subs)),
                      target_bg=0.18)
    before = _sky_level(img)
    after = _sky_level(_auto(img))
    assert abs(after - before) / before < 0.02


def test_sky_dominated_stack_declines_rather_than_lifting_the_median():
    """With the sky read correctly, a frame that is all sky and stars has nothing
    above the background's noise to lift, so the suggestion declines — which is the
    whole point of that gate. Before the fix it compared a 0.18 median against a
    0.0008 "sky" and never fired."""
    assert suggest_tone_curve(_stretched(obj=0.0)) is None


def test_the_fallback_pins_the_sky_instead_of_darkening_it():
    """The other half of A1: the frame above lands on the fallback, and the fixed
    S-curve's 0.25→0.20 knee darkened exactly the tones a stretched sky occupies."""
    from seestack.edit.ops.tone import _AUTO_CONTRAST_FALLBACK

    img = _stretched(obj=0.0)
    before = _sky_level(img)

    old = _sky_level(_curves(img, {"points": _AUTO_CONTRAST_FALLBACK}, None))
    assert (before - old) / before > 0.10, "the old fixed fallback must darken the sky"

    pts = fallback_tone_curve(img)
    assert pts[1][0] == pts[1][1], "the anchor sits on the identity"
    assert pts[1][0] >= before - 0.02, "and at or above the sky, so the sky can't ride it"
    new = _sky_level(_curves(img, {"points": pts}, None))
    assert abs(new - before) / before < 0.02


def test_the_fallback_still_shapes_the_tones_above_the_sky():
    """Anchoring the sky must not turn the fallback into a silent no-op: tones
    between the sky and white still get the gentle shoulder lift."""
    img = _stretched(obj=0.0)
    pts = fallback_tone_curve(img)
    out = _curves(img, {"points": pts}, None)
    above = np.isfinite(img[..., 1]) & (img[..., 1] > pts[1][0] + 0.1)
    assert above.sum() > 100
    assert float(out[..., 1][above].mean()) > float(img[..., 1][above].mean()) + 1e-3


def test_the_fallback_is_the_identity_when_there_is_no_room_above_the_sky():
    """A bright image whose sky already sits at/above the shoulder knee gets the
    identity — never a curve that shoves the background around."""
    rng = np.random.default_rng(11)
    bright = np.clip(0.8 + rng.normal(0.0, 0.01, (200, 200, 3)), 0.0, 1.0).astype("float32")
    assert fallback_tone_curve(bright) == [[0.0, 0.0], [1.0, 1.0]]
    assert np.allclose(_auto(bright), bright, atol=1e-4)


def test_an_object_dominated_frame_still_gets_its_midtone_lift():
    """The fix must not cost the case the curve exists for: when a bright object
    fills much of the frame there is real structure above the sky's noise, so the
    lift still happens — and the sky anchor still sits on the identity."""
    img = _stretched(obj=0.5)
    pts = suggest_tone_curve(img)
    assert pts is not None
    assert pts[1][0] == pts[1][1]                       # sky anchor on identity
    mid = next(p for p in pts if p[1] > p[0])
    assert mid[0] > pts[1][0]                           # the lift is above the sky
    before = _sky_level(img)
    after = _sky_level(_auto(img))
    assert abs(after - before) / max(before, 1e-6) < 0.05


def test_a_mosaic_gap_does_not_reintroduce_the_spike():
    """NaN is "no coverage" and must stay excluded from the sky measurement — a
    mosaic's uncovered border must not become the floor spike by another route."""
    img = _stretched()
    img[:80, :, :] = np.nan
    before = float(np.nanmedian(img[100:160, :60, 1]))
    out = _auto(img)
    assert np.array_equal(np.isnan(out), np.isnan(img))
    after = float(np.nanmedian(out[100:160, :60, 1]))
    assert abs(after - before) / before < 0.02
