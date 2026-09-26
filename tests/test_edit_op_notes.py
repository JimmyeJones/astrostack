"""A recipe may carry the same op twice — so its outcome notes must too.

``EditContext.op_notes`` is how an op hands the caller a small fact about what it
really did. Its sibling channels (``fitted``, ``field_deltas``) have been keyed
by the recipe op's **uid** from the start, precisely because a recipe is a list
and the editor's Add menu has no duplicate guard — but ``op_notes`` was keyed by
the op **id**, so a second instance silently overwrote the first's note.

The one that costs something is ``tone.color_calibrate``'s ``proxy_fallback``:
the editor captions it *"the saved picture's colour will differ a little from
this preview"* (``colorCalProxyFallbackCaption``). With two colour-cal ops and
the **first** the one that fell back on the decimated proxy, the whole advisory
vanished — a preview-vs-export parity warning going silent, which is the class
AGENTS.md §1 re-opened priority 1 over.
"""

from __future__ import annotations

import numpy as np

from seestack.edit.opnotes import COLOR_CAL_OP, merge_color_cal
from seestack.edit.pipeline import apply_recipe
from seestack.edit.recipe import OpInstance, Recipe
from seestack.edit.registry import EditContext


def _starfield(seed: int = 7) -> np.ndarray:
    """A small RGB frame with enough stars for a gray-star solve to run."""
    rng = np.random.default_rng(seed)
    h = w = 160
    rgb = rng.normal(0.02, 0.0015, size=(h, w, 3)).astype(np.float32)
    yy, xx = np.mgrid[0:h, 0:w]
    for _ in range(90):
        cy, cx = rng.uniform(6, h - 6), rng.uniform(6, w - 6)
        amp = rng.uniform(0.25, 0.8)
        star = amp * np.exp(-((yy - cy) ** 2 + (xx - cx) ** 2) / (2 * 1.4**2))
        rgb += star[..., None].astype(np.float32)
    rgb[..., 0] *= 1.35
    rgb[..., 2] *= 0.70
    return rgb


# --------------------------------------------------------------------------
# The context: one note per instance
# --------------------------------------------------------------------------


def test_two_instances_of_one_op_each_keep_their_own_note() -> None:
    """Two colour-cal ops in one recipe leave two notes, in render order.

    Fails before the fix: both wrote ``op_notes["tone.color_calibrate"]``, so the
    second overwrote the first and the caller saw one note for a two-step chain.
    """
    rec = Recipe(ops=[
        OpInstance(id=COLOR_CAL_OP, params={"mode": "gray_star"}, uid="first"),
        OpInstance(id=COLOR_CAL_OP, params={"mode": "gray_star"}, uid="second"),
    ])
    ctx = EditContext()
    apply_recipe(_starfield(), rec, ctx, auto_stretch=False)

    notes = ctx.notes_for(COLOR_CAL_OP)
    assert len(notes) == 2, "each instance must keep its own note"
    assert all(n.get("mode_used") for n in notes)
    # Keyed to the instance, exactly as ``fitted`` already is.
    assert set(ctx.op_notes) == {f"first:{COLOR_CAL_OP}", f"second:{COLOR_CAL_OP}"}


def test_one_instance_reads_back_exactly_as_before() -> None:
    """The single-op recipe every surface actually renders is unchanged."""
    rec = Recipe(ops=[OpInstance(id=COLOR_CAL_OP, params={"mode": "gray_star"},
                                 uid="only")])
    ctx = EditContext()
    apply_recipe(_starfield(), rec, ctx, auto_stretch=False)

    notes = ctx.notes_for(COLOR_CAL_OP)
    assert len(notes) == 1
    assert merge_color_cal(notes) == notes[0]


def test_a_direct_caller_with_no_uid_still_gets_its_note() -> None:
    """An engine caller applying the op by hand sets no ``op_uid``; the note
    lands under the bare op id and reads back the same way — the same degrade
    ``EditContext.fit`` already has."""
    from seestack.edit.registry import get_op

    spec = get_op(COLOR_CAL_OP)
    assert spec is not None
    ctx = EditContext()
    spec.apply(_starfield(), {"mode": "gray_star"}, ctx)
    assert list(ctx.op_notes) == [COLOR_CAL_OP]
    assert len(ctx.notes_for(COLOR_CAL_OP)) == 1


def test_notes_for_ignores_other_ops() -> None:
    ctx = EditContext()
    ctx.op_uid = "a"
    ctx.record_note("tone.other", {"mode_used": "x"})
    ctx.op_uid = "b"
    ctx.record_note(COLOR_CAL_OP, {"mode_used": "gray_star"})
    assert ctx.notes_for(COLOR_CAL_OP) == [{"mode_used": "gray_star"}]


# --------------------------------------------------------------------------
# The merge: which question each field answers
# --------------------------------------------------------------------------


def test_the_parity_warning_is_any_instance_not_the_last() -> None:
    """The preview's colour is not the export's if **any** step diverged.

    This is the defect in one line: with the fallback on the *first* op, taking
    the last note's flag drops the advisory entirely.
    """
    merged = merge_color_cal([
        {"mode_used": "background_neutral", "n_stars_used": 0, "notes": "",
         "proxy_fallback": True},
        {"mode_used": "gray_star", "n_stars_used": 42, "notes": "",
         "proxy_fallback": False},
    ])
    assert merged is not None
    assert merged["proxy_fallback"] is True
    # …while the balance the picture ended up with is the last one's.
    assert merged["mode_used"] == "gray_star"
    assert merged["n_stars_used"] == 42


def test_the_balance_reported_is_the_one_the_picture_carries() -> None:
    merged = merge_color_cal([
        {"mode_used": "gray_star", "n_stars_used": 42, "notes": "a",
         "proxy_fallback": False},
        {"mode_used": "background_neutral", "n_stars_used": 0, "notes": "b",
         "proxy_fallback": False},
    ])
    assert merged is not None
    assert merged["mode_used"] == "background_neutral"
    assert merged["notes"] == "b"
    assert merged["proxy_fallback"] is False


def test_merge_is_the_identity_on_a_single_note() -> None:
    note = {"mode_used": "gray_star", "n_stars_used": 7, "notes": "",
            "proxy_fallback": True}
    assert merge_color_cal([note]) == note


def test_nothing_to_report_reads_as_none() -> None:
    assert merge_color_cal([]) is None
    assert merge_color_cal([{"mode_used": "", "proxy_fallback": True}]) is None
    assert merge_color_cal([None, "not a note"]) is None


def test_a_note_without_a_mode_never_becomes_the_answer() -> None:
    """A half-written note can't mask a real one — but its parity flag still
    counts, because it is still a step that ran."""
    merged = merge_color_cal([
        {"mode_used": "gray_star", "n_stars_used": 5, "notes": "",
         "proxy_fallback": False},
        {"mode_used": "", "proxy_fallback": True},
    ])
    assert merged is not None
    assert merged["mode_used"] == "gray_star"
    assert merged["proxy_fallback"] is True
