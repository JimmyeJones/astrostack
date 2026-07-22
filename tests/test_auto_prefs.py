"""Adaptive Auto — the per-library taste profile (seestack/edit/auto_prefs.py)
and its effect on the one-click Auto recipe."""

from __future__ import annotations

import numpy as np
import pytest

from seestack.edit import auto_prefs
from seestack.edit.presets import auto_recipe


# --- the profile accumulator -------------------------------------------------

def test_empty_and_none_profile_leave_params_unchanged():
    base = dict(target_bg=0.2, saturation=1.2, sharpen_amount=0.5,
               denoise_strength=0.0, scnr_amount=0.7)
    for prof in (None, auto_prefs.empty_profile(), {}, {"biases": {}}):
        assert auto_prefs.apply_profile(prof, **base) == pytest.approx(base)
    assert auto_prefs.is_neutral(None)
    assert auto_prefs.describe_profile(None) is None


def test_feedback_biases_the_matching_parameter():
    prof = auto_prefs.record_feedback(None, "too_dark")
    assert prof["biases"]["brightness"] == 1
    out = auto_prefs.apply_profile(prof, target_bg=0.2, saturation=1.2,
                                   sharpen_amount=0.5, denoise_strength=0.0,
                                   scnr_amount=0.7)
    assert out["target_bg"] > 0.2  # brighter
    # only the targeted param moved
    assert out["saturation"] == 1.2 and out["sharpen_amount"] == 0.5


def test_repeated_feedback_saturates_never_runs_away():
    prof = None
    for _ in range(20):
        prof = auto_prefs.record_feedback(prof, "too_soft")
    assert prof["biases"]["sharpen"] == auto_prefs.MAX_STEPS  # clamped
    out = auto_prefs.apply_profile(prof, target_bg=0.2, saturation=1.2,
                                   sharpen_amount=0.5, denoise_strength=0.0,
                                   scnr_amount=0.7)
    # bounded shift: MAX_STEPS * per-step, and inside the safe range
    assert out["sharpen_amount"] == pytest.approx(0.8)
    assert 0.0 <= out["sharpen_amount"] <= 1.0


def test_opposite_feedback_walks_the_bias_back():
    prof = auto_prefs.record_feedback(None, "too_dark")
    prof = auto_prefs.record_feedback(prof, "too_dark")
    assert prof["biases"]["brightness"] == 2
    prof = auto_prefs.record_feedback(prof, "too_bright")
    assert prof["biases"]["brightness"] == 1
    prof = auto_prefs.record_feedback(prof, "too_bright")
    # netted back to neutral — the key is dropped, profile is neutral again
    assert "brightness" not in prof["biases"]
    assert auto_prefs.is_neutral(prof)


def test_apply_profile_clamps_to_the_safe_range():
    prof = None
    for _ in range(auto_prefs.MAX_STEPS):
        prof = auto_prefs.record_feedback(prof, "too_bright")
    # brightness min bias = -MAX_STEPS*0.02 = -0.06; from a 0.11 base that would be
    # 0.05 but the safe floor is 0.10, so it clamps.
    out = auto_prefs.apply_profile(prof, target_bg=0.11, saturation=1.2,
                                   sharpen_amount=0.5, denoise_strength=0.0,
                                   scnr_amount=0.7)
    assert out["target_bg"] == pytest.approx(0.10)


def test_unknown_cue_is_ignored():
    prof = auto_prefs.record_feedback(None, "make_it_pop")
    assert auto_prefs.is_neutral(prof)


def test_coerce_tolerates_garbage_upgrade_safe():
    # An older/garbled store must degrade to neutral, never raise.
    garbage = {"version": 99, "biases": {"brightness": "lots", "bogus": 5,
                                         "sharpen": 999}, "counts": "nope"}
    out = auto_prefs.apply_profile(garbage, target_bg=0.2, saturation=1.2,
                                   sharpen_amount=0.5, denoise_strength=0.0,
                                   scnr_amount=0.7)
    # bogus param dropped; sharpen clamped to MAX_STEPS (not 999)
    assert out["sharpen_amount"] == pytest.approx(0.8)
    assert out["target_bg"] == 0.2  # non-numeric brightness ignored


def test_describe_profile_is_plain_language():
    prof = auto_prefs.record_feedback(None, "too_dark")
    prof = auto_prefs.record_feedback(prof, "over_sharpened")
    note = auto_prefs.describe_profile(prof)
    assert note is not None
    assert "brighter" in note and "softer" in note
    assert note.endswith("based on your recent feedback.")


# --- integration with auto_recipe -------------------------------------------

def _clean_img():
    img = np.full((80, 100, 3), 0.05, np.float32)
    img[30:50, 40:60] += 0.5
    return img


def _shape(recipe):
    # OpInstance uids are randomised per build, so compare the meaningful content
    # (op id + params), not the transient uid.
    return [(o.id, o.params) for o in recipe.ops]


def test_auto_recipe_default_is_byte_for_byte_without_prefs():
    """The whole upgrade-safety guarantee: prefs=None (or an empty/neutral
    profile) yields exactly the recipe Auto emitted before Adaptive Auto."""
    rgb = _clean_img()
    baseline = _shape(auto_recipe(rgb))
    assert _shape(auto_recipe(rgb, prefs=None)) == baseline
    assert _shape(auto_recipe(rgb, prefs=auto_prefs.empty_profile())) == baseline
    assert _shape(auto_recipe(rgb, prefs={})) == baseline


def test_auto_recipe_applies_a_brightness_bias():
    rgb = _clean_img()
    base_bg = next(o for o in auto_recipe(rgb).ops
                   if o.id == "tone.stretch").params["target_bg"]
    prof = auto_prefs.record_feedback(None, "too_dark")
    prof = auto_prefs.record_feedback(prof, "too_dark")
    biased_bg = next(o for o in auto_recipe(rgb, prefs=prof).ops
                     if o.id == "tone.stretch").params["target_bg"]
    assert biased_bg > base_bg


def test_auto_recipe_bias_can_add_denoise_to_a_clean_stack():
    """A clean stack gets no denoise op by default; a 'too noisy' bias adds one."""
    rgb = _clean_img()
    assert "detail.denoise" not in [o.id for o in auto_recipe(rgb).ops]
    prof = auto_prefs.record_feedback(None, "too_noisy")
    ids = [o.id for o in auto_recipe(rgb, prefs=prof).ops]
    assert "detail.denoise" in ids
    # still ordered correctly (linear denoise before the stretch)
    assert ids.index("detail.denoise") < ids.index("tone.stretch")
