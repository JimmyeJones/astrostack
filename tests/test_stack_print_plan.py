"""The Stack form's print line — say the paper size *before* the run fixes it.

``printexport`` already tells a finished picture what it prints at, and what it
would take to reach one size up. That is the right sentence in the wrong tense:
the lever it names (Drizzle) is a knob on a form the user has already left. These
tests pin the pre-run half — :func:`seestack.stack.stacker._print_plan` — and the
three promises it makes: the paper size is the one ``print_options`` would give
the canvas the run really writes; the drizzle scale offered genuinely *reaches*
the next size; and it stays silent rather than arguing with the memory guard.
"""

import pytest

pytest.importorskip("astropy")

from seestack.io.project import FrameRow, Project
from seestack.printexport import (
    DRIZZLE_MAX_USEFUL_SCALE,
    PAPER_SIZES,
    print_options,
)
from seestack.stack.stacker import (
    StackOptions,
    _estimate_peak_bytes,
    _print_plan,
    estimate_stack,
)
from tests.synth import make_synth_wcs_text

HUGE_BUDGET = 10**12  # nothing here is memory-bound unless a test says so


def _plan(w, h, *, drizzle=False, scale=1.0, budget=HUGE_BUDGET):
    """The plan for a canvas whose *output* is w×h at the given drizzle scale."""
    canvas_h = int(round(h / scale)) if drizzle else h
    canvas_w = int(round(w / scale)) if drizzle else w
    return _print_plan(w, h, (canvas_h, canvas_w), drizzle=drizzle,
                       drizzle_scale=scale, drizzle_reject=False,
                       rejection_map=False, budget=budget)


def test_names_the_same_paper_print_options_would():
    """The pre-run sentence and the finished picture's own answer must agree —
    two voices on one canvas is exactly the drift this reuses ``print_options``
    to avoid."""
    for w, h in [(1200, 800), (2400, 1600), (4000, 3000), (6000, 4000)]:
        plan = _plan(w, h)
        best = print_options(w, h)[0]
        assert plan.name == best.name
        assert plan.dpi == best.dpi
        assert best.name in plan.text


def test_too_small_says_pixels_not_subs():
    """The one claim that must never appear: more subs do not enlarge a canvas."""
    plan = _plan(300, 200)
    assert plan.name is None and plan.dpi is None
    assert "won't have enough pixels" in plan.text
    assert "Drizzle" in plan.text
    # More subs are named only to be ruled *out* — never as the way there.
    assert "not more subs" in plan.text
    assert "another night" not in plan.text.lower()


def test_offered_drizzle_scale_really_reaches_that_paper():
    """The nudge is verified, not extrapolated: re-sizing the canvas by the
    offered scale must actually qualify for the paper it names."""
    checked = 0
    for w, h in [(1200, 800), (1600, 1200), (1800, 1200), (2400, 1600)]:
        plan = _plan(w, h)
        if plan.bigger_name is None:
            continue
        checked += 1
        s = plan.bigger_drizzle_scale
        assert s is not None and 1.0 < s <= DRIZZLE_MAX_USEFUL_SCALE
        _, (out_h, out_w) = _estimate_peak_bytes(
            (h, w), drizzle=True, drizzle_scale=s)
        assert any(o.name == plan.bigger_name
                   for o in print_options(out_w, out_h))
        # …and it points *up*: the paper offered is bigger than what it prints now.
        longest = {p.name: p.long_in for p in PAPER_SIZES}
        if plan.name is not None:
            assert longest[plan.bigger_name] > longest[plan.name]
    assert checked >= 2, "fixture no longer exercises the nudge"


def test_scale_multiplies_the_scale_already_set():
    """With drizzle already on, the offer is an *absolute* scale to move to —
    ``current × gap`` — not the gap on its own."""
    off = _plan(1800, 1200, drizzle=False)
    on = _plan(1800, 1200, drizzle=True, scale=1.5)
    assert off.bigger_name is not None and off.bigger_name == on.bigger_name
    assert on.bigger_drizzle_scale > off.bigger_drizzle_scale
    assert "Turning Drizzle on at" in off.bigger_text
    assert "Raising Drizzle to" in on.bigger_text


def test_silent_when_the_gap_needs_more_than_super_resolution_pays_for():
    """Past ``DRIZZLE_MAX_USEFUL_SCALE`` the honest lever is a mosaic, not a
    bigger number in a box — so say nothing rather than set a silly goal."""
    plan = _plan(1800, 1200, drizzle=True, scale=DRIZZLE_MAX_USEFUL_SCALE)
    assert plan.bigger_name is None
    assert plan.bigger_drizzle_scale is None and plan.bigger_text is None
    # The "what it prints today" half still stands.
    assert plan.name is not None and plan.text


def test_silent_at_the_largest_paper():
    plan = _plan(9000, 6000)
    assert plan.name == PAPER_SIZES[-1].name
    assert plan.bigger_name is None and plan.bigger_text is None


def test_defers_to_the_memory_verdict():
    """The nudge must never offer a canvas the memory guard would refuse — the
    over-budget alert owns that case, and two answers is worse than one."""
    generous = _plan(1800, 1200)
    assert generous.bigger_name is not None
    peak, _ = _estimate_peak_bytes(
        (1200, 1800), drizzle=True,
        drizzle_scale=generous.bigger_drizzle_scale)
    tight = _plan(1800, 1200, budget=int(peak) - 1)
    assert tight.bigger_name is None
    assert tight.bigger_drizzle_scale is None and tight.bigger_text is None
    # …and only the *nudge* is withheld; the plain fact is still told.
    assert tight.name == generous.name and tight.text == generous.text


def _single_field_project(tmp_path, *, width, height) -> Project:
    proj = Project.create(tmp_path / "p", name="t")
    wcs_text = make_synth_wcs_text(
        width=width, height=height, ra_center_deg=100.0, dec_center_deg=20.0,
        pixscale_arcsec=5.0,
    )
    for i in range(4):
        proj.add_frame(FrameRow(
            source_path=f"f{i}.fit", cached_path=f"f{i}.fit",
            width_px=width, height_px=height, bayer_pattern="RGGB",
            wcs_json=wcs_text, ra_center_deg=100.0, dec_center_deg=20.0,
            pixscale_arcsec=5.0,
        ))
    return proj


def test_estimate_stack_carries_the_plan(tmp_path):
    """End to end: the plan rides on ``StackEstimate`` and describes the canvas
    that estimate reports, not some other one."""
    proj = _single_field_project(tmp_path, width=1800, height=1200)
    try:
        est = estimate_stack(proj, StackOptions(drizzle=False),
                             memory_budget_gb=8.0)
        assert est.print_plan is not None
        best = print_options(est.output_w, est.output_h)[0]
        assert est.print_plan.name == best.name
        assert est.print_plan.bigger_name is not None
    finally:
        proj.close()


def test_estimate_plan_is_silent_on_a_canvas_the_budget_refuses(tmp_path):
    """The over-budget case: the estimate already refuses the run, so the print
    nudge must not be offering a *bigger* one alongside it."""
    proj = _single_field_project(tmp_path, width=1800, height=1200)
    try:
        est = estimate_stack(proj, StackOptions(drizzle=True, drizzle_scale=2.0),
                             memory_budget_gb=20e-3)
        assert est.would_exceed is True
        assert est.print_plan is not None
        assert est.print_plan.bigger_name is None
    finally:
        proj.close()
