"""Adaptive Auto — the feedback chips that cannot move the picture in front of you.

``auto_prefs`` stores a bounded per-parameter bias and ``auto_recipe`` applies it on
top of what it measured from the image, re-clamped to that parameter's
``_PARAM_RANGE``. When the measured value already sits at the end of that range the
clamp swallows the shift, so the bias moves and **the recipe does not** — on a deep
clean stack (the owner's own shape) ``denoise_strength`` is exactly 0.0 and no
"Over-smoothed" tap has anything to ease back, and on a very noisy one the denoise is
pinned at ``_AUTO_DENOISE_MAX`` and "Too noisy" has nothing to add. The editor
answered every one of those taps with *"Thanks — Auto will lean that way for you"*.

``presets.inert_auto_cues`` reports the whole set *before* any chip is tapped, which
is both the honest answer and the cheap one: the exact predicate (rebuild the recipe
either side of the tap) costs a measured 639 ms a build, and the knobs it needs are
measured once per Auto click anyway.

The load-bearing test here is :func:`test_inert_cues_agree_with_the_recipe_itself` —
it asks ``auto_recipe`` directly, so the report cannot drift from the thing it
reports on.
"""
from __future__ import annotations

import numpy as np
import pytest

from seestack.edit import auto_prefs, presets


def _scene(sigma: float, *, h: int = 220, w: int = 260, seed: int = 5) -> np.ndarray:
    """A small OSC-ish stack: faint diffuse glow, a scatter of stars, a green cast
    and the given background noise. ``sigma`` is the only knob that matters here —
    it is what drives the denoise/sharpen crossfade and the saturation term."""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:h, 0:w]
    base = 0.02 + 0.03 * np.exp(
        -(((yy - h / 2) / (h / 5.0)) ** 2 + ((xx - w / 2) / (w / 5.0)) ** 2))
    rgb = np.repeat(base[..., None], 3, axis=-1).astype(np.float32)
    rgb[..., 1] *= 1.08
    for _ in range(50):
        y, x = int(rng.integers(5, h - 5)), int(rng.integers(5, w - 5))
        rgb[y - 1:y + 2, x - 1:x + 2, :] += 0.35
    rgb += rng.normal(0.0, sigma, rgb.shape).astype(np.float32)
    return rgb.astype(np.float32)


def _ops(recipe) -> list[tuple[str, bool, dict]]:
    """A recipe as something comparable. ``Recipe.to_dict()`` cannot be compared —
    it mints a fresh ``uid`` per op and stamps ``updated_utc`` — and it fails in the
    direction that hides this bug: every build reads as different, so every tap looks
    like it moved something."""
    return [(op.id, op.enabled, dict(op.params)) for op in recipe.ops]


# --- the extraction is behaviour-preserving ----------------------------------

def test_measured_knobs_are_the_numbers_the_recipe_is_built_from():
    """``measured_auto_knobs`` is not a second opinion about the picture: with a
    neutral profile its values are exactly what the recipe's own ops carry."""
    rgb = _scene(0.0004)
    knobs = presets.measured_auto_knobs(rgb)
    ops = dict((op.id, op.params) for op in presets.auto_recipe(rgb).ops)
    assert ops["tone.stretch"]["target_bg"] == knobs["target_bg"]
    assert ops["tone.saturation"]["amount"] == round(knobs["saturation"], 3)
    assert ops["tone.scnr"]["amount"] == round(knobs["scnr_amount"], 3)
    assert ops["detail.sharpen"]["amount"] == knobs["sharpen_amount"]
    # A clean stack carries no denoise op at all, which is the whole mechanism.
    assert knobs["denoise_strength"] == 0.0
    assert "detail.denoise" not in ops
    # Highlight protection starts off, so the stretch holds nothing back. (The op
    # carries the param at its own 0.0 default once ``validate_ops`` has filled it
    # in; what the recipe *emits* is nothing — see ``auto_op_params``.)
    assert knobs["highlight_protect"] == 0.0
    assert ops["tone.stretch"].get("highlights", 0.0) == 0.0
    assert "highlights" not in presets.auto_op_params(
        presets.auto_knob_values(knobs))["tone.stretch"]


def test_an_unmeasurable_image_still_yields_the_neutral_fallbacks():
    """The old "treated as clean" behaviour: no image ⇒ full sharpen, no denoise."""
    knobs = presets.measured_auto_knobs(None)
    assert knobs == {"target_bg": 0.20, "saturation": 1.2, "denoise_strength": 0.0,
                     "chroma_strength": 0.0, "sharpen_amount": 0.5,
                     "scnr_amount": 0.7, "highlight_protect": 0.0}
    # And the recipe built from them is the same one as always.
    ids = [op.id for op in presets.auto_recipe(None).ops]
    assert ids == ["background.final_gradient", "tone.color_calibrate",
                   "tone.stretch", "tone.scnr", "tone.saturation", "tone.curves",
                   "detail.sharpen"]


def test_auto_op_params_applies_the_post_profile_denoise_cap():
    """``_AUTO_DENOISE_MAX`` is applied *after* the taste profile, so a learned
    "too noisy" bias cannot push the one-click result back to a waxy sky — and that
    cap is the third way a tap can be swallowed, on top of ``_PARAM_RANGE``."""
    knobs = dict(presets.measured_auto_knobs(None), denoise_strength=0.95)
    values = presets.auto_knob_values(knobs)
    assert values["denoise_strength"] == pytest.approx(presets._AUTO_DENOISE_MAX)


# --- the report agrees with the recipe ---------------------------------------

@pytest.mark.parametrize("sigma", [0.0004, 0.004, 0.02, 0.05])
def test_inert_cues_agree_with_the_recipe_itself(sigma):
    """**The guard that cannot drift.** For every one of the twelve cues, on four
    pictures and from four different stored tastes: a cue is reported inert exactly
    when ``auto_recipe`` — asked directly, before and after the tap — builds the
    byte-identical op list.

    This is deliberately end-to-end rather than a check of the helper against
    itself: three of the last five editor bugs in this area were a second copy of
    some arithmetic drifting from the first, and the only way to pin this report is
    against the recipe it is a report about.
    """
    rgb = _scene(sigma)
    knobs = presets.measured_auto_knobs(rgb)
    object_type = presets.classify_target(rgb).get("cls")

    starts = [auto_prefs.empty_profile()]
    for cue, reps in [("too_dark", 3), ("too_noisy", 2), ("core_clipped", 1)]:
        prof = auto_prefs.empty_profile()
        for _ in range(reps):
            prof = auto_prefs.record_feedback(prof, cue, object_type=object_type)
        starts.append(prof)

    for prof in starts:
        reported = set(presets.inert_auto_cues(knobs, prof, object_type))
        before = _ops(presets.auto_recipe(rgb, prefs=prof))
        for cue in auto_prefs.known_cues():
            tapped = auto_prefs.record_feedback(prof, cue, object_type=object_type)
            after = _ops(presets.auto_recipe(rgb, prefs=tapped))
            assert (after == before) is (cue in reported), (
                f"sigma={sigma} cue={cue}: recipe "
                f"{'unchanged' if after == before else 'changed'} but "
                f"{'reported inert' if cue in reported else 'reported live'}")


def test_a_clean_deep_stack_cannot_be_asked_for_less_smoothing():
    """The measured case from the lead: ``noise_fraction`` 0 ⇒ no denoise to ease
    back, so every "Over-smoothed" tap is inert — five of five, not just the fourth.
    "Too dark" on the same picture is live, so this is not a report that everything
    is dead."""
    rgb = _scene(0.0004)
    knobs = presets.measured_auto_knobs(rgb)
    assert knobs["denoise_strength"] == 0.0
    prof = auto_prefs.empty_profile()
    for _ in range(5):
        assert "over_smoothed" in presets.inert_auto_cues(knobs, prof)
        prof = auto_prefs.record_feedback(prof, "over_smoothed")
    assert "too_dark" not in presets.inert_auto_cues(
        knobs, auto_prefs.empty_profile())


def test_a_very_noisy_stack_cannot_be_asked_for_more_smoothing_or_less_sharpening():
    """The mirror image: the denoise is pinned at its cap and the sharpen is at its
    floor, so "Too noisy" and "Over-sharpened" are both dead from the first tap."""
    rgb = _scene(0.05)
    knobs = presets.measured_auto_knobs(rgb)
    assert knobs["denoise_strength"] >= presets._AUTO_DENOISE_MAX
    assert knobs["sharpen_amount"] == 0.0
    inert = presets.inert_auto_cues(knobs, auto_prefs.empty_profile())
    assert {"too_noisy", "over_sharpened"} <= set(inert)


def test_the_one_sided_highlight_knob_is_inert_until_it_is_held_back():
    """"Core looks flat" walks highlight protection back toward off, and off is
    where it starts — so it is dead on any picture Auto is not already holding
    back, from the very first tap, and alive again the moment it is."""
    knobs = presets.measured_auto_knobs(None)
    assert "core_flat" in presets.inert_auto_cues(knobs, auto_prefs.empty_profile())
    held = auto_prefs.record_feedback(auto_prefs.empty_profile(), "core_clipped")
    assert "core_flat" not in presets.inert_auto_cues(knobs, held)


def test_a_saturated_taste_is_reported_inert_in_both_mechanisms():
    """The store-side limit ``_feedback_limit_note`` already covers after the fact:
    the fourth identical tap stores nothing new. It is in this report too, so the
    row can dim the chip before the owner reaches for it a fourth time."""
    knobs = presets.measured_auto_knobs(None)
    prof = auto_prefs.empty_profile()
    for _ in range(auto_prefs.MAX_STEPS):
        assert "too_green" not in presets.inert_auto_cues(knobs, prof)
        prof = auto_prefs.record_feedback(prof, "too_green")
    assert "too_green" in presets.inert_auto_cues(knobs, prof)


def test_every_inert_cue_has_a_sentence_to_show():
    """A chip the row dims has to be able to say why — a cue added to ``_CUE_STEP``
    without a phrase would otherwise dim silently. (``_UNCHANGED_PHRASE`` is pinned
    against ``_CUE_STEP`` from both sides by
    ``tests/test_auto_feedback_cues_mirror.py``; this is the hint wording on top of
    it.)"""
    for cue in auto_prefs.known_cues():
        hint = auto_prefs.limit_hint(cue)
        assert hint and hint.endswith(
            "Tapping still teaches Auto for your other pictures.")
    assert auto_prefs.limit_hint("make_it_pop") is None


def test_an_inert_tap_is_still_recorded():
    """The taste is library-wide, so a tap this picture cannot show is still a real
    preference — the hint says so, and the store had better agree with the hint."""
    knobs = presets.measured_auto_knobs(_scene(0.0004))
    assert "over_smoothed" in presets.inert_auto_cues(
        knobs, auto_prefs.empty_profile())
    prof = auto_prefs.record_feedback(auto_prefs.empty_profile(), "over_smoothed")
    assert prof["biases"]["denoise"] == -1
