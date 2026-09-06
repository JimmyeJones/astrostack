"""Adaptive Auto — the per-library taste profile (seestack/edit/auto_prefs.py)
and its effect on the one-click Auto recipe."""

from __future__ import annotations

import json

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
    # global says brighter; the galaxy override says darker for that param only.
    # Two taps, because a type-scoped tap starts from the taste *in force* (+1
    # here) and moves one step: +1 → 0 → −1.
    prof = auto_prefs.record_feedback(None, "too_dark")               # global +1
    for _ in range(2):
        prof = auto_prefs.record_feedback(prof, "too_bright", object_type="galaxy")
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


# --- recency decay (slice (b)'s remaining half) -----------------------------
# "Recent feedback weighs more" — a bias fades one step per DECAY_DAYS without
# reinforcement, so a taste the owner moved on from returns to Auto's measured
# default on its own. Every test drives the clock explicitly (`now=`), so none of
# them are wall-clock flaky.

_DAY = 86400.0
_T0 = 1_700_000_000.0  # an arbitrary fixed epoch


def test_an_unreinforced_bias_fades_one_step_per_decay_period():
    prof = None
    for _ in range(3):
        prof = auto_prefs.record_feedback(prof, "too_dark", now=_T0)
    assert auto_prefs.effective_biases(prof, now=_T0) == {"brightness": 3}
    # Just short of one period: nothing has moved yet.
    almost = _T0 + auto_prefs.DECAY_DAYS * _DAY - _DAY
    assert auto_prefs.effective_biases(prof, now=almost) == {"brightness": 3}
    for periods, expected in ((1, 2), (2, 1), (3, 0), (9, 0)):
        at = _T0 + periods * auto_prefs.DECAY_DAYS * _DAY
        got = auto_prefs.effective_biases(prof, now=at)
        assert got.get("brightness", 0) == expected, (periods, got)
    # Fully faded reads as neutral — Auto is back to its data-driven values.
    far = _T0 + 3 * auto_prefs.DECAY_DAYS * _DAY
    assert auto_prefs.is_neutral(prof, now=far)
    assert auto_prefs.apply_profile(prof, now=far, **_BASE)["target_bg"] == pytest.approx(
        _BASE["target_bg"])


def test_a_negative_bias_fades_toward_neutral_not_through_it():
    prof = None
    for _ in range(2):
        prof = auto_prefs.record_feedback(prof, "too_bright", now=_T0)
    assert auto_prefs.effective_biases(prof, now=_T0) == {"brightness": -2}
    one = _T0 + auto_prefs.DECAY_DAYS * _DAY
    assert auto_prefs.effective_biases(prof, now=one) == {"brightness": -1}
    # Never crosses zero into the opposite taste, however long it is left.
    for periods in (2, 3, 40):
        at = _T0 + periods * auto_prefs.DECAY_DAYS * _DAY
        assert auto_prefs.effective_biases(prof, now=at) == {}


def test_a_profile_written_before_decay_shipped_never_fades():
    """§9 upgrade-safety: an old stored profile carries no stamps, so it behaves
    byte-for-byte as it does today no matter how much later it is read."""
    old = {"version": 1, "biases": {"brightness": 3, "sharpen": -2}, "counts": {}}
    for years in (0, 1, 10):
        at = _T0 + years * 365 * _DAY
        assert auto_prefs.effective_biases(old, now=at) == {
            "brightness": 3, "sharpen": -2}
        assert auto_prefs.steps_faded(old, now=at) == 0
        assert auto_prefs.fade_note(old, now=at) is None


def test_new_feedback_builds_on_the_faded_value_and_restarts_the_fade():
    """A tap means "a bit more than it is *now*", not "a bit more than the
    saturated value I stopped meaning two years ago"."""
    prof = None
    for _ in range(3):
        prof = auto_prefs.record_feedback(prof, "too_dark", now=_T0)
    late = _T0 + 2 * auto_prefs.DECAY_DAYS * _DAY   # faded 3 → 1
    prof = auto_prefs.record_feedback(prof, "too_dark", now=late)
    assert auto_prefs.effective_biases(prof, now=late) == {"brightness": 2}
    # ...and the clock restarted from the new tap, not from the original one.
    assert auto_prefs.effective_biases(
        prof, now=late + auto_prefs.DECAY_DAYS * _DAY) == {"brightness": 1}


def test_the_opposite_cue_still_walks_a_faded_bias_all_the_way_back():
    prof = auto_prefs.record_feedback(None, "too_dark", now=_T0)
    late = _T0 + 5 * auto_prefs.DECAY_DAYS * _DAY
    prof = auto_prefs.record_feedback(prof, "too_bright", now=late)
    # The +1 had already faded to 0, so one "too bright" leaves a real −1 rather
    # than silently netting out against a stale accumulator.
    assert auto_prefs.effective_biases(prof, now=late) == {"brightness": -1}


def test_a_faded_per_type_override_falls_back_to_the_global_taste():
    prof = auto_prefs.record_feedback(None, "too_dark", now=_T0)          # global +1
    for _ in range(2):                                                    # override −1
        prof = auto_prefs.record_feedback(prof, "too_bright", now=_T0,
                                          object_type="galaxy")
    assert auto_prefs.effective_biases(prof, "galaxy", now=_T0) == {"brightness": -1}
    late = _T0 + 2 * auto_prefs.DECAY_DAYS * _DAY
    # Both have faded away by now, so neither taste applies...
    assert auto_prefs.effective_biases(prof, "galaxy", now=late) == {}
    # ...and the note no longer claims a galaxy-scoped taste that isn't in force.
    assert auto_prefs.describe_profile(prof, "galaxy", now=late) is None


def test_the_fade_is_never_silent():
    prof = None
    for _ in range(3):
        prof = auto_prefs.record_feedback(prof, "too_dark", now=_T0)
    assert auto_prefs.steps_faded(prof, now=_T0) == 0
    assert auto_prefs.fade_note(prof, now=_T0) is None      # nothing has moved yet

    part = _T0 + auto_prefs.DECAY_DAYS * _DAY
    assert auto_prefs.steps_faded(prof, now=part) == 1
    note = auto_prefs.fade_note(prof, now=part)
    assert note is not None and "fading" in note
    # The "why Auto shifted" note is still there, just weaker.
    assert auto_prefs.describe_profile(prof, now=part) is not None

    gone = _T0 + 3 * auto_prefs.DECAY_DAYS * _DAY
    assert auto_prefs.steps_faded(prof, now=gone) == 3
    gone_note = auto_prefs.fade_note(prof, now=gone)
    # The vanished "why" note is explained rather than just disappearing.
    assert auto_prefs.describe_profile(prof, now=gone) is None
    assert gone_note is not None and "measured default" in gone_note


def test_a_clock_that_jumps_backwards_does_not_age_a_bias_backwards():
    """A stamp in the future (NAS/host clock skew, a restored backup) reads as
    'just now' — it must never resurrect or invert a bias."""
    prof = auto_prefs.record_feedback(None, "too_dark", now=_T0)
    earlier = _T0 - 400 * _DAY
    assert auto_prefs.effective_biases(prof, now=earlier) == {"brightness": 1}
    assert auto_prefs.fade_note(prof, now=earlier) is None


def test_a_garbled_stamp_degrades_to_no_decay_rather_than_raising():
    """§9 loader tolerance: the stamps map is as untrusted as the rest of the
    store, and an unusable stamp must fall back to today's no-fade behaviour."""
    for bad in (None, "yesterday", -1, 0, float("nan"), float("inf"), True, {}):
        prof = {"version": 1, "biases": {"brightness": 2},
                "stamps": {"brightness": bad}}
        assert auto_prefs.effective_biases(prof, now=_T0) == {"brightness": 2}
    # A stamp for a parameter that carries no bias is simply dropped.
    prof = {"version": 1, "biases": {}, "stamps": {"brightness": _T0}}
    assert auto_prefs.effective_biases(prof, now=_T0) == {}
    # ...and so is a stamp naming a parameter this version doesn't know.
    prof = {"version": 1, "biases": {"brightness": 1}, "stamps": {"nope": _T0}}
    assert auto_prefs.effective_biases(prof, now=_T0) == {"brightness": 1}


def test_a_recorded_profile_stays_json_safe():
    """The webapp persists this dict with json.dumps — a stamp must not smuggle
    in anything that isn't."""
    prof = auto_prefs.record_feedback(None, "too_dark", now=_T0)
    prof = auto_prefs.record_feedback(prof, "too_soft", now=_T0,
                                      object_type="nebula")
    round_tripped = json.loads(json.dumps(prof))
    assert auto_prefs.effective_biases(round_tripped, "nebula", now=_T0) == {
        "brightness": 1, "sharpen": 1}


def test_a_faded_override_unmasking_a_bigger_global_bias_still_counts_as_a_fade():
    """The one case where a parameter's *applied* magnitude goes up as it fades:
    a per-type override that stops winning hands the parameter back to a stronger
    global bias. That must not net out against the fade and silence the note."""
    prof = None
    for _ in range(3):
        prof = auto_prefs.record_feedback(prof, "too_dark", now=_T0)      # global +3
    for _ in range(4):                                                    # override −1
        # Four taps: a type-scoped tap starts from the +3 in force and walks it
        # down one step at a time (+3 → +2 → +1 → 0 → −1).
        prof = auto_prefs.record_feedback(prof, "too_bright", now=_T0,
                                          object_type="galaxy")
    assert auto_prefs.effective_biases(prof, "galaxy", now=_T0) == {"brightness": -1}

    late = _T0 + auto_prefs.DECAY_DAYS * _DAY
    # The override has faded away; the global (also one step down) now applies.
    assert auto_prefs.effective_biases(prof, "galaxy", now=late) == {"brightness": 2}
    assert auto_prefs.steps_faded(prof, "galaxy", now=late) >= 0
    assert auto_prefs.fade_note(prof, "galaxy", now=late) is not None


def test_the_first_type_scoped_tap_moves_one_step_not_across_the_global_bias():
    """A tap is one gentle step, whichever bucket it lands in.

    Regression: a per-type bucket overrides the global one *per parameter*, and a
    fresh override used to start at neutral — so the first type-scoped tap
    replaced the global value with ±1 instead of moving it. With a global "+2
    brighter" (what the owner gets from two taps on a picture the classifier
    can't place), one "too bright" on a galaxy landed at −1: a three-step,
    0.06-in-``target_bg`` jump *past* neutral in the direction they didn't ask
    for, and the +1 they were asking for was unreachable — tapping back returned
    to +2, so the taste oscillated between two wrong values forever."""
    prof = None
    for _ in range(2):
        prof = auto_prefs.record_feedback(prof, "too_dark", now=_T0)  # global +2
    assert auto_prefs.effective_biases(prof, "galaxy", now=_T0) == {"brightness": 2}

    # One tap on a galaxy → one step down, not a jump to the other side of neutral.
    prof = auto_prefs.record_feedback(prof, "too_bright", now=_T0, object_type="galaxy")
    assert auto_prefs.effective_biases(prof, "galaxy", now=_T0) == {"brightness": 1}
    # …and only for galaxies: every other kind of target keeps the global taste.
    assert auto_prefs.effective_biases(prof, "nebula", now=_T0) == {"brightness": 2}
    assert auto_prefs.effective_biases(prof, None, now=_T0) == {"brightness": 2}


def test_a_type_scoped_taste_walks_one_step_per_tap_in_both_directions():
    """Every reachable value between the bounds, and no jumps — the property the
    bug above broke. Includes neutral: "no shift for galaxies" while the global
    stays "+2 brighter" is a real setting, so a per-type 0 has to stick rather
    than hand the parameter straight back to the global taste."""
    prof = None
    for _ in range(2):
        prof = auto_prefs.record_feedback(prof, "too_dark", now=_T0)  # global +2

    seen = []
    for _ in range(5):
        prof = auto_prefs.record_feedback(prof, "too_bright", now=_T0,
                                          object_type="galaxy")
        seen.append(auto_prefs.effective_biases(prof, "galaxy", now=_T0)
                    .get("brightness", 0))
    # +2 → +1 → 0 → −1 → −2 → −3 (the floor), one step at a time.
    assert seen == [1, 0, -1, -2, -3]

    seen = []
    for _ in range(7):
        prof = auto_prefs.record_feedback(prof, "too_dark", now=_T0,
                                          object_type="galaxy")
        seen.append(auto_prefs.effective_biases(prof, "galaxy", now=_T0)
                    .get("brightness", 0))
    assert seen == [-2, -1, 0, 1, 2, 3, 3]
    # The global taste is untouched throughout — this was all galaxy-scoped.
    assert auto_prefs.effective_biases(prof, None, now=_T0) == {"brightness": 2}


def test_a_type_scoped_neutral_survives_a_json_round_trip():
    """The sticky 0 is stored, so "no shift for galaxies" survives the webapp's
    JSON persistence rather than reverting to the global taste on the next read."""
    prof = None
    for _ in range(2):
        prof = auto_prefs.record_feedback(prof, "too_dark", now=_T0)  # global +2
    for _ in range(2):
        prof = auto_prefs.record_feedback(prof, "too_bright", now=_T0,
                                          object_type="galaxy")       # galaxy 0
    round_tripped = json.loads(json.dumps(prof))
    assert auto_prefs.effective_biases(round_tripped, "galaxy", now=_T0) == {}
    assert auto_prefs.is_neutral(round_tripped, "galaxy", now=_T0)
    assert auto_prefs.effective_biases(round_tripped, "nebula", now=_T0) == {"brightness": 2}
    # Auto really does run its measured default on a galaxy, and the shifted
    # value on anything else.
    gal = auto_prefs.apply_profile(round_tripped, object_type="galaxy",
                                   now=_T0, **_BASE)
    neb = auto_prefs.apply_profile(round_tripped, object_type="nebula",
                                   now=_T0, **_BASE)
    assert gal["target_bg"] == pytest.approx(_BASE["target_bg"])
    assert neb["target_bg"] > _BASE["target_bg"]
    # And a neutral galaxy override doesn't invent a "for your galaxies" note.
    assert auto_prefs.describe_profile(round_tripped, "galaxy", now=_T0) is None
