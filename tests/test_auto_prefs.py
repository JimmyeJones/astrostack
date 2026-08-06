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
               denoise_strength=0.0, scnr_amount=0.7, highlight_protect=0.0)
    for prof in (None, auto_prefs.empty_profile(), {}, {"biases": {}}):
        assert auto_prefs.apply_profile(prof, **base) == pytest.approx(base)
    # A caller that omits the newest parameter gets it back at its own default,
    # so an older call site keeps working and still reads as "off".
    older_call = dict(base)
    older_call.pop("highlight_protect")
    assert auto_prefs.apply_profile(None, **older_call)["highlight_protect"] == 0.0
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


# --- per-object-type taste (slice b) ----------------------------------------

_BASE = dict(target_bg=0.2, saturation=1.2, sharpen_amount=0.5,
             denoise_strength=0.0, scnr_amount=0.7)


def test_type_feedback_records_into_that_types_bucket_not_global():
    prof = auto_prefs.record_feedback(None, "too_dark", object_type="galaxy")
    # global set stays neutral; the bias lives in the galaxy bucket
    assert "brightness" not in prof["biases"]
    assert prof["by_type"]["galaxy"]["biases"]["brightness"] == 1
    # applied for a galaxy → brighter; for a cluster (no bucket) → unchanged
    gal = auto_prefs.apply_profile(prof, object_type="galaxy", **_BASE)
    clu = auto_prefs.apply_profile(prof, object_type="cluster", **_BASE)
    assert gal["target_bg"] > 0.2
    assert clu["target_bg"] == pytest.approx(0.2)
    # and an unclassified image gets the (empty) global taste → unchanged
    assert auto_prefs.apply_profile(prof, object_type=None, **_BASE)["target_bg"] \
        == pytest.approx(0.2)


def test_type_override_takes_precedence_over_global_per_param():
    # global says brighter; the galaxy override says darker for that param only
    prof = auto_prefs.record_feedback(None, "too_dark")               # global +1
    prof = auto_prefs.record_feedback(prof, "too_bright", object_type="galaxy")  # galaxy -1
    eff_gal = auto_prefs.effective_biases(prof, "galaxy")
    eff_neb = auto_prefs.effective_biases(prof, "nebula")
    assert eff_gal["brightness"] == -1   # galaxy override wins
    assert eff_neb["brightness"] == 1     # nebula falls back to global


def test_global_taste_still_applies_to_every_type():
    prof = auto_prefs.record_feedback(None, "too_soft")  # global sharpen +1
    for otype in ("galaxy", "nebula", "cluster", None):
        out = auto_prefs.apply_profile(prof, object_type=otype, **_BASE)
        assert out["sharpen_amount"] > 0.5


def test_type_bucket_walks_back_to_neutral_and_is_dropped():
    prof = auto_prefs.record_feedback(None, "too_green", object_type="nebula")
    assert prof["by_type"]["nebula"]["biases"]["green"] == 1
    # nebula's green bias exists; SCNR is stronger for a nebula
    assert auto_prefs.apply_profile(prof, object_type="nebula", **_BASE)["scnr_amount"] > 0.7
    # opposite feedback nets a bucket's bias out; the bias key is dropped and the
    # type reads neutral again (its counts persist, mirroring the global set).
    prof2 = auto_prefs.record_feedback(None, "too_dark", object_type="cluster")
    prof2 = auto_prefs.record_feedback(prof2, "too_bright", object_type="cluster")
    assert auto_prefs.effective_biases(prof2, "cluster") == {}
    assert auto_prefs.is_neutral(prof2, object_type="cluster")


def test_describe_profile_names_the_archetype_for_a_type_bias():
    prof = auto_prefs.record_feedback(None, "too_dark", object_type="galaxy")
    note = auto_prefs.describe_profile(prof, object_type="galaxy")
    assert note is not None and "for your galaxies" in note and "brighter" in note
    # a type with no override + no global bias is neutral (no note)
    assert auto_prefs.describe_profile(prof, object_type="cluster") is None
    # a global-only bias reads "for you" (not scoped to a type)
    g = auto_prefs.record_feedback(None, "too_dark")
    assert "for you," in (auto_prefs.describe_profile(g, object_type="galaxy") or "")


def test_old_flat_profile_upgrades_and_still_applies_globally():
    """A profile stored before per-type buckets existed (no by_type key) keeps
    behaving exactly as its global biases dictate."""
    old = {"version": 1, "biases": {"brightness": 2}, "counts": {"too_dark": 2}}
    assert auto_prefs.effective_biases(old, "galaxy") == {"brightness": 2}
    out = auto_prefs.apply_profile(old, object_type="galaxy", **_BASE)
    assert out["target_bg"] > 0.2


def test_coerce_drops_unknown_types_and_garbage_buckets():
    garbage = {"biases": {}, "by_type": {"quasar": {"biases": {"brightness": 1}},
                                         "galaxy": "nope",
                                         "nebula": {"biases": {"bogus": 9}}}}
    prof = auto_prefs.record_feedback(garbage, "")  # coerce via no-op cue
    assert "quasar" not in prof["by_type"]      # unknown type dropped
    assert "galaxy" not in prof["by_type"]       # non-dict bucket dropped
    assert "nebula" not in prof["by_type"]       # only a bogus param → empty → dropped


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


# --- the "Core blown out" cue ------------------------------------------------
#
# The one-sided knob: highlight protection starts *off* (0 = the historical
# stretch), so "core blown out" turns it up and "core looks flat" walks it back
# toward off. There is nothing below off to ask for, which is why the bias has
# its own floor at 0 rather than the symmetric -MAX_STEPS.

def test_core_clipped_turns_highlight_protection_up():
    prof = auto_prefs.record_feedback(None, "core_clipped")
    out = auto_prefs.apply_profile(prof, **_BASE)
    assert out["highlight_protect"] > 0.0
    # ...and nothing else moved.
    neutral = auto_prefs.apply_profile(None, **_BASE)
    for key in ("target_bg", "saturation", "sharpen_amount", "denoise_strength",
                "scnr_amount"):
        assert out[key] == pytest.approx(neutral[key])


def test_core_clipped_saturates_and_stays_in_range():
    prof = None
    for _ in range(8):
        prof = auto_prefs.record_feedback(prof, "core_clipped")
    assert prof["biases"]["highlights"] == auto_prefs.MAX_STEPS
    assert 0.0 <= auto_prefs.apply_profile(prof, **_BASE)["highlight_protect"] <= 1.0


def test_core_flat_walks_back_one_tap_at_a_time_and_stops_at_off():
    """One 'looks flat' must undo exactly one 'blown out' — if the bias could go
    negative (where the range clamp swallows it) the walk-back would silently
    need three taps to show any effect."""
    prof = auto_prefs.record_feedback(None, "core_clipped")
    prof = auto_prefs.record_feedback(prof, "core_clipped")
    two_up = auto_prefs.apply_profile(prof, **_BASE)["highlight_protect"]
    prof = auto_prefs.record_feedback(prof, "core_flat")
    one_up = auto_prefs.apply_profile(prof, **_BASE)["highlight_protect"]
    assert 0.0 < one_up < two_up
    # Back to neutral, and further taps can't push it below off.
    for _ in range(4):
        prof = auto_prefs.record_feedback(prof, "core_flat")
    assert "highlights" not in prof["biases"]
    assert auto_prefs.apply_profile(prof, **_BASE)["highlight_protect"] == 0.0
    assert auto_prefs.is_neutral(prof)


def test_a_garbled_store_cannot_inject_a_negative_highlight_bias():
    """§9 loader tolerance: an out-of-range value from an older/edited store is
    clamped into the parameter's own step range, not merely to ±MAX_STEPS."""
    assert auto_prefs.effective_biases({"biases": {"highlights": -3}}) == {}
    assert auto_prefs.effective_biases(
        {"biases": {"highlights": 99}}) == {"highlights": auto_prefs.MAX_STEPS}


def test_core_cue_is_recorded_per_object_type_like_the_others():
    prof = auto_prefs.record_feedback(None, "core_clipped", object_type="galaxy")
    assert auto_prefs.apply_profile(
        prof, object_type="galaxy", **_BASE)["highlight_protect"] > 0.0
    assert auto_prefs.apply_profile(
        prof, object_type="cluster", **_BASE)["highlight_protect"] == 0.0


def test_describe_profile_explains_the_held_back_core():
    prof = auto_prefs.record_feedback(None, "core_clipped")
    note = auto_prefs.describe_profile(prof)
    assert note is not None and "bright cores" in note


def test_auto_recipe_carries_the_highlight_bias_into_the_stretch():
    rgb = _clean_img()
    base = next(o for o in auto_recipe(rgb).ops if o.id == "tone.stretch")
    assert base.params.get("highlights", 0.0) == 0.0     # off by default
    prof = auto_prefs.record_feedback(None, "core_clipped")
    prof = auto_prefs.record_feedback(prof, "core_clipped")
    biased = next(o for o in auto_recipe(rgb, prefs=prof).ops
                  if o.id == "tone.stretch")
    assert biased.params["highlights"] > 0.0
    # The stretch's own measured value is untouched by this cue.
    assert biased.params["target_bg"] == pytest.approx(base.params["target_bg"])
