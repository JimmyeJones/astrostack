"""The "an older version trimmed this picture too far" verdict.

Pure unit tests for :mod:`webapp.stale_crop` — the judgement itself, with no
stack, no coverage FITS and no HTTP, so the thresholds can be pinned at the
boundary rather than inferred from an endpoint's answer. The wiring (the per-run
endpoint and the library-wide scan) is tested against real runs in
``tests/webapp/test_editor.py`` and ``tests/webapp/test_overtrim.py``.
"""

from __future__ import annotations

import pytest

from webapp.stale_crop import (
    STALE_CROP_KEEP_RATIO,
    combined_crop_keep_fraction,
    crop_is_stale,
    crop_keep_fraction,
    enabled_crop_ops,
    stale_crop_verdict,
)


def _rect(x0, y0, x1, y1):
    return {"x0": x0, "y0": y0, "x1": x1, "y1": y1}


def _crop_ops(rect):
    """A one-crop recipe, the shape ``stale_crop_verdict`` now takes."""
    return [{"id": "geometry.crop", "enabled": True, "params": rect}]


# ---- crop_keep_fraction ----------------------------------------------------

def test_keep_fraction_is_the_rectangles_area():
    assert crop_keep_fraction(_rect(0.0, 0.0, 1.0, 1.0)) == pytest.approx(1.0)
    assert crop_keep_fraction(_rect(0.25, 0.25, 0.75, 0.75)) == pytest.approx(0.25)


def test_the_audit_s_own_recipe_measures_three_point_four_percent():
    """The rectangle v0.277.0 wrote onto the owner's 5089x2045 mosaic, verbatim
    from the 2026-09-10 audit. It is what "a sliver" means numerically, and it is
    the number the fixtures below are built around."""
    kept = crop_keep_fraction(_rect(0.6228, 0.0341, 0.6896, 0.5463))
    assert kept == pytest.approx(0.034, abs=0.001)


def test_empty_params_read_as_the_ops_own_full_frame_defaults():
    """``geometry.crop``'s params default to (0,0,1,1), so a crop op carrying no
    params crops nothing. Reading that as "keeps everything" — rather than as
    malformed — is what keeps it out of the note, which is right: it took nothing
    away."""
    assert crop_keep_fraction({}) == pytest.approx(1.0)
    assert crop_is_stale(crop_keep_fraction({}), 0.9) is False


@pytest.mark.parametrize("bad", [
    None, "not a dict", 42,
    {"x0": 0.5, "y0": 0.0, "x1": 0.5, "y1": 1.0},   # zero width
    {"x0": 0.9, "y0": 0.0, "x1": 0.1, "y1": 1.0},   # inverted
    {"x0": "a", "y0": 0.0, "x1": 1.0, "y1": 1.0},   # hand-edited junk
])
def test_a_degenerate_or_malformed_rectangle_has_no_keep_fraction(bad):
    """A recipe is a user-editable document that reaches this code by PUT, so the
    judgement must answer "I don't know" rather than a negative area."""
    assert crop_keep_fraction(bad) is None


# ---- enabled_crop_op -------------------------------------------------------

def test_it_finds_an_enabled_crop_and_ignores_a_disabled_one():
    params = _rect(0.1, 0.1, 0.2, 0.2)
    ops = [{"id": "tone.stretch", "enabled": True, "params": {}},
           {"id": "geometry.crop", "enabled": True, "params": params}]
    assert enabled_crop_ops(ops) == [params]
    off = [{"id": "geometry.crop", "enabled": False, "params": params}]
    assert enabled_crop_ops(off) == [], "a disabled crop is not what is on screen"
    assert enabled_crop_ops([]) == []
    assert enabled_crop_ops(None) == []


def test_it_reads_parsed_op_instances_too():
    """The router holds dicts; anything holding a parsed recipe holds
    ``OpInstance``. One helper serves both, so the two can never disagree."""
    from seestack.edit.recipe import OpInstance

    params = _rect(0.0, 0.0, 0.5, 0.5)
    ops = [OpInstance(id="geometry.crop", params=params, enabled=True)]
    assert enabled_crop_ops(ops) == [params]


def test_two_crops_multiply_the_way_the_editor_multiplies_them():
    """Each crop cuts what the last one left, so their shares compose — the same
    arithmetic ``mosaicTrim.cropCoverageFraction`` does. Reading only the first
    would understate the cut on exactly the recipes this note is about."""
    ops = [{"id": "geometry.crop", "enabled": True,
            "params": _rect(0.0, 0.0, 0.5, 0.5)},          # keeps 0.25
           {"id": "geometry.crop", "enabled": True,
            "params": _rect(0.0, 0.0, 0.5, 1.0)}]          # keeps 0.5 of that
    assert combined_crop_keep_fraction(ops) == pytest.approx(0.125)
    assert combined_crop_keep_fraction([]) is None


# ---- crop_is_stale ---------------------------------------------------------

def test_the_audit_s_case_is_stale():
    """3.4 % kept where the border rule keeps 92.4 % — the reproduced state of
    every mosaic the owner Auto-edited before D1 was fixed."""
    assert crop_is_stale(0.034, 0.924) is True


def test_a_crop_that_keeps_most_of_what_the_rule_keeps_is_not_stale():
    """The owner's own framing must not be nagged."""
    assert crop_is_stale(0.55, 0.95) is False


def test_someone_framing_on_the_middle_of_their_mosaic_is_not_accused():
    """Why the threshold is a quarter and not the backlog entry's suggested half
    (the editor's reasoning, shipped v0.416.0). Deliberately keeping 40 % of a
    well-covered mosaic is a decision, and a half would call it a defect."""
    kept, offered = 0.4 * 0.92, 0.92  # keeps 40 % of what the canvas offers
    assert crop_is_stale(kept, offered) is False
    assert kept < 0.5 * offered, "a half would have accused this framing choice"


def test_the_ratio_threshold_is_pinned_at_its_boundary():
    suggested = 0.9
    edge = STALE_CROP_KEEP_RATIO * suggested
    assert crop_is_stale(edge - 1e-6, suggested) is True
    # Exactly at the boundary is *not* stale (strictly less than).
    assert crop_is_stale(edge, suggested) is False


def test_it_measures_against_what_the_canvas_offers_never_the_whole_frame():
    """On a genuinely ragged mosaic that only offers 20 %, a crop keeping 10 %
    has kept half of what there was — a framing choice, not the D1 collapse."""
    assert crop_is_stale(0.10, 0.20) is False


def test_a_crop_larger_than_the_rule_wants_is_never_stale():
    """The rule wanting *less* than the saved crop is the ordinary state of a
    hand-cropped picture and of a canvas whose own covered rect is small. This
    note is only ever about a picture that lost too much."""
    assert crop_is_stale(0.10, 0.05) is False
    assert crop_is_stale(0.95, 0.95) is False


def test_an_unmeasurable_picture_is_never_accused():
    assert crop_is_stale(None, 0.9) is False
    assert crop_is_stale(0.03, None) is False


# ---- stale_crop_verdict ----------------------------------------------------

def test_no_proposed_trim_means_no_opinion():
    """Deliberately the same answer the shipped editor note gives
    (``overTrimmedVerdict`` returns null on a null suggestion): with no measured
    proposal there is nothing to weigh the crop against but the whole frame, and
    a legitimately tight hand-crop is a small share of that too. Missing this
    case in all three surfaces beats catching it in one."""
    v = stale_crop_verdict(_crop_ops(_rect(0.6228, 0.0341, 0.6896, 0.5463)), None)
    assert v["stale"] is False
    assert v["suggested_keep_fraction"] is None


def test_an_unmeasurable_run_is_also_silent():
    """A run with no coverage sibling cannot have its trim re-derived at all."""
    v = stale_crop_verdict(_crop_ops(_rect(0.6228, 0.0341, 0.6896, 0.5463)), None,
                           measurable=False)
    assert v["stale"] is False
    assert v["suggested_keep_fraction"] is None


def test_a_picture_with_no_crop_at_all_is_silent():
    v = stale_crop_verdict([], _rect(0.02, 0.02, 0.98, 0.98))
    assert v["stale"] is False
    assert v["stored_keep_fraction"] is None


def test_the_verdict_carries_the_replacement_crop():
    suggested = _rect(0.02, 0.02, 0.98, 0.98)
    v = stale_crop_verdict(_crop_ops(_rect(0.62, 0.03, 0.69, 0.55)), suggested)
    assert v["stale"] is True
    assert v["suggested_crop"] == suggested
    assert v["stored_keep_fraction"] == pytest.approx(0.0364, abs=1e-3)
    assert v["suggested_keep_fraction"] == pytest.approx(0.9216, abs=1e-3)


# ---- the two copies of one threshold ---------------------------------------

def test_the_threshold_has_not_drifted_from_the_editors_copy():
    """One rule, two implementations: this module decides the Target-page and
    Dashboard notes, and ``mosaicTrim.OVER_TRIM_KEEP_RATIO`` decides the editor's
    (v0.416.0). If they diverge, the Dashboard names pictures the editor is
    silent about — which is precisely the failure "one definition, two surfaces"
    exists to prevent, and it would be invisible until the owner clicked through.

    A grep rather than a shared constant because the two live in different
    languages; the repo already pins cross-language constants this way."""
    import re
    from pathlib import Path

    ts = Path(__file__).resolve().parents[1] / (
        "frontend/src/components/editor/mosaicTrim.ts")
    src = ts.read_text(encoding="utf-8")
    m = re.search(r"export const OVER_TRIM_KEEP_RATIO\s*=\s*([0-9.]+)", src)
    assert m, "OVER_TRIM_KEEP_RATIO is gone from mosaicTrim.ts — was it renamed?"
    assert float(m.group(1)) == STALE_CROP_KEEP_RATIO, (
        f"the editor uses {m.group(1)} but webapp/stale_crop.py uses "
        f"{STALE_CROP_KEEP_RATIO}; change them together or the surfaces disagree")
