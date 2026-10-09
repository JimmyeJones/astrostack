"""The Adaptive-Auto feedback vocabulary must be the same on both screens — and
every parameter it reaches must be reachable in *both* directions.

The cue string a chip sends is the wire contract between two tables that were
mirrored by comment only:

* ``AUTO_FEEDBACK_CHIPS`` (``frontend/src/components/editor/AutoFeedback.tsx``)
  — the chips the editor's "How did Auto do? Tap what you'd change:" row draws;
* ``seestack.edit.auto_prefs._CUE_STEP`` — the table that turns one tap into a
  bounded bias on one Auto parameter.

A chip the engine does not know 422s at the user; a cue with no chip is a taste
they can never express. Both are now pinned against a **shared table** driven
from each side, the idiom ``tests/test_auto_summary_mirror.py`` established.

The second half is the one that found a real defect. ``green`` was the only one
of the six biased parameters a cue could move in a single direction: three "too
green" taps saturated Auto's SCNR amount at 1.0 (full green-cast removal) and
nothing short of ``DELETE /api/editor/auto-preferences`` — which throws away
*every* learned taste — could walk it back, while ``_BIAS_PHRASE`` already held
the sentence for the negative green bias ("with a lighter green-cast removal")
that no cue could produce. ``too_magenta`` closes it, and
:func:`test_every_biased_parameter_is_reachable_in_both_directions` is what
stops the next cue being added one-way.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from seestack.edit.auto_prefs import (
    _BIAS_PHRASE,
    _CUE_STEP,
    _PARAM_STEP,
    _UNCHANGED_PHRASE,
    apply_profile,
    known_cues,
    record_feedback,
    unchanged_note,
)

_FE = Path(__file__).resolve().parents[1] / "frontend" / "src" / "components" / "editor"
CUE_CASES_JSON = _FE / "autoFeedbackCues.cases.json"


def _cases() -> list[dict]:
    """The shared table, or a loud failure — a table that can't be found
    enforces nothing, and a relocated one is itself the drift this guards."""
    assert CUE_CASES_JSON.exists(), (
        f"The shared feedback-cue table is missing at {CUE_CASES_JSON}. It is "
        "driven from both sides — this file and "
        "frontend/src/components/editor/AutoFeedback.test.tsx — so if it moved, "
        "both have to follow."
    )
    cases = json.loads(CUE_CASES_JSON.read_text(encoding="utf-8"))["cases"]
    assert cases, "The shared feedback-cue table is empty, so it pins nothing."
    return cases


def test_the_engine_knows_exactly_the_cues_in_the_shared_table() -> None:
    """As a **set**, deliberately. The table's order is the order the chips
    render in — which the frontend half of this guard pins — while ``_CUE_STEP``
    is grouped by the parameter each cue moves, so the two sequences legitimately
    differ. What has to match exactly is *which* cues exist."""
    assert set(known_cues()) == {c["cue"] for c in _cases()}, (
        "`_CUE_STEP` and the shared table disagree about which cues exist. A "
        "chip the engine doesn't know 422s at the user; a cue with no chip is a "
        "taste they can't express."
    )
    assert len(known_cues()) == len(_cases()), "a cue is listed twice"


@pytest.mark.parametrize("case", _cases(), ids=lambda c: c["cue"])
def test_each_cue_moves_the_parameter_and_direction_the_table_says(case) -> None:
    assert _CUE_STEP[case["cue"]] == (case["param"], case["step"]), (
        f"`{case['cue']}` moves {_CUE_STEP[case['cue']]}, but the shared table "
        f"the editor's chip row is also driven against says "
        f"({case['param']!r}, {case['step']})."
    )


def test_every_biased_parameter_is_reachable_in_both_directions() -> None:
    """The guard this file exists for. Every knob a cue can move must have a cue
    that moves it *back*, or a tap is one-way and only a whole-profile Reset
    undoes it — which is what shipped for ``green``."""
    for param in sorted(_PARAM_STEP):
        directions = {step for p, step in _CUE_STEP.values() if p == param}
        assert {+1, -1} <= directions, (
            f"`{param}` can only be nudged {sorted(directions)}. A one-way knob "
            "means a tap the owner cannot walk back without discarding every "
            "other taste they have taught Auto (or waiting out "
            "`DECAY_DAYS` a step at a time). Add the opposite cue."
        )


def test_every_bias_phrase_is_produced_by_some_cue() -> None:
    """The read side and the write side of one store, the other way round: a
    phrase for a direction no cue can reach is a sentence the app can never
    say. That is how the missing ``green`` walk-back announced itself."""
    reachable = {(param, step > 0) for param, step in _CUE_STEP.values()}
    assert set(_BIAS_PHRASE) <= reachable, (
        f"`_BIAS_PHRASE` describes {sorted(set(_BIAS_PHRASE) - reachable)}, "
        "which no cue can produce."
    )


def test_the_green_pair_walks_a_saturated_bias_all_the_way_back() -> None:
    """End to end, on the symptom: saturate the green removal with taps and bring
    it back with the opposite cue, without touching the rest of the profile."""
    base = dict(target_bg=0.2, saturation=1.2, sharpen_amount=0.5,
                denoise_strength=0.1, scnr_amount=0.7)
    prof = None
    # An unrelated taste that must survive the walk-back untouched.
    prof = record_feedback(prof, "too_dark")
    for _ in range(3):
        prof = record_feedback(prof, "too_green")
    assert apply_profile(prof, **base)["scnr_amount"] == pytest.approx(1.0)
    for _ in range(3):
        prof = record_feedback(prof, "too_magenta")
    back = apply_profile(prof, **base)
    assert back["scnr_amount"] == pytest.approx(0.7), (
        "three 'too magenta' taps must undo three 'too green' ones"
    )
    assert back["target_bg"] == pytest.approx(0.22), (
        "walking the green bias back must not disturb the brightness taste"
    )


def test_the_green_walk_back_saturates_rather_than_running_away() -> None:
    """Symmetric like the other two-sided knobs: ±MAX_STEPS, and the SCNR op is
    still emitted at the floor (``auto_recipe`` drops it below 0.05)."""
    base = dict(target_bg=0.2, saturation=1.2, sharpen_amount=0.5,
                denoise_strength=0.1, scnr_amount=0.7)
    prof = None
    for _ in range(10):
        prof = record_feedback(prof, "too_magenta")
    amount = apply_profile(prof, **base)["scnr_amount"]
    assert amount == pytest.approx(0.4), "±3 steps of 0.10 from Auto's own 0.7"
    assert amount >= 0.05, "a saturated walk-back must not switch the op off"


def test_every_cue_can_say_that_it_changed_nothing() -> None:
    """Third table, same rule as the first two. A tap can land somewhere it has
    no room to move — the taste already at ``MAX_STEPS``, or at the
    ``_PARAM_MIN_STEP`` floor that makes ``highlights`` one-sided — and the
    editor then says so instead of "Thanks — Auto will lean that way for you". A
    cue with no phrase would fall back to that claim on exactly the taps where it
    is untrue, which is the defect the sentence exists for; so the table is
    pinned against ``_CUE_STEP`` from both sides."""
    assert set(_UNCHANGED_PHRASE) == set(_CUE_STEP), (
        "`_UNCHANGED_PHRASE` and `_CUE_STEP` disagree about which cues exist: "
        f"no phrase for {sorted(set(_CUE_STEP) - set(_UNCHANGED_PHRASE))}, "
        f"a phrase for {sorted(set(_UNCHANGED_PHRASE) - set(_CUE_STEP))} that "
        "no chip can send."
    )
    for cue in sorted(_CUE_STEP):
        note = unchanged_note(cue)
        assert note and note.endswith("."), f"{cue} has no finished sentence"
        assert "this picture" in note, (
            f"{cue}'s line must say the *picture* did not change — the stored "
            "taste may well have, and claiming otherwise is the opposite lie."
        )
    assert unchanged_note("make_it_pop") is None, "an unknown cue says nothing"
