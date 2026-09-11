"""Can this stack's outlier rejection actually drop a lone satellite trail?

``seestack.stackhealth`` answers that *after* a stack has run (its
``rejection_blind`` note). ``rejection_reach`` is the same answer computed
*before* it, so the Stack form can say so while the toggle that would fix it is
still on screen — and both read the same :func:`kappa_min_frames`, so the
warning and the note can never disagree.
"""

from __future__ import annotations

import pytest

from seestack.stack.stacker import (
    DRIZZLE_REJECT_MIN_FRAMES,
    MIN_MAX_MIN_FRAMES,
    StackOptions,
    combine_method,
    kappa_min_frames,
    rejection_reach,
)


# --- combine_method: the dispatcher's own gates, in one place ------------------

@pytest.mark.parametrize(("n", "expected"), [
    (1, "mean"), (2, "mean"), (3, "mean"), (4, "sigma-clip"), (50, "sigma-clip"),
])
def test_default_options_fall_through_to_a_plain_mean_below_four_frames(n, expected):
    """The default ``sigma_clip=True`` only dispatches from 4 frames; below that
    the stack combines as a plain average with no rejection pass at all."""
    assert combine_method(StackOptions(), n) == expected


@pytest.mark.parametrize(("n", "expected"), [
    (2, "mean"), (3, "min-max-reject"), (30, "min-max-reject"),
])
def test_min_max_needs_three_frames_and_then_takes_precedence(n, expected):
    opts = StackOptions(min_max_reject=True)
    assert combine_method(opts, n) == expected


def test_drizzle_wins_over_both_toggles():
    opts = StackOptions(drizzle=True, sigma_clip=True, min_max_reject=True)
    assert combine_method(opts, 200) == "drizzle"


# --- rejection_reach: the honest "will it remove anything?" --------------------

def test_sigma_clip_runs_but_cannot_clip_a_lone_outlier_below_kappa_min_frames():
    """The gap this whole helper exists for: at the default κ=3 sigma clipping
    dispatches from 4 frames but is blind to a single trail until 11, so on every
    small stack in between it runs, records ``REJMODE = sigma-clip``, and clips
    nothing."""
    need = kappa_min_frames(3.0)
    assert need == 11
    for n in range(4, need):
        reach = rejection_reach(StackOptions(), n)
        assert reach.method == "sigma-clip"
        assert reach.lone_outlier_min_frames == need
        assert reach.reaches is False, f"{n} frames wrongly reported as protected"
    at_threshold = rejection_reach(StackOptions(), need)
    assert at_threshold.reaches is True


def test_a_three_frame_default_stack_reports_no_rejection_at_all():
    """Not merely "blind" — no pass runs, so the combine is a plain average."""
    reach = rejection_reach(StackOptions(), 3)
    assert reach.method == "mean"
    assert reach.reaches is False
    assert reach.lone_outlier_min_frames is None


def test_min_max_reaches_a_lone_outlier_from_three_frames_up():
    for n in (3, 4, 10):
        reach = rejection_reach(StackOptions(sigma_clip=False, min_max_reject=True), n)
        assert reach.method == "min-max-reject"
        assert reach.reaches is True
        assert reach.lone_outlier_min_frames == MIN_MAX_MIN_FRAMES


def test_auto_reject_is_the_fix_and_reaches_at_every_count_from_three_up():
    """"Turn on Auto outlier removal" is only honest advice if it actually helps:
    auto picks min/max below the κ switch, so it reaches from 3 frames up — where
    the same stack with the plain default reaches nowhere below 11."""
    for n in range(3, 12):
        auto = rejection_reach(StackOptions(auto_reject=True), n)
        assert auto.reaches is True, f"auto failed to protect a {n}-frame stack"
        assert rejection_reach(StackOptions(), n).reaches is (n >= kappa_min_frames(3.0))


def test_two_frames_cannot_be_protected_by_any_setting():
    """Below min/max's 3-frame floor there is no method to offer, so the form must
    have nothing to click — every option resolves to a plain mean."""
    for opts in (StackOptions(), StackOptions(auto_reject=True),
                 StackOptions(min_max_reject=True)):
        reach = rejection_reach(opts, 2)
        assert reach.method == "mean"
        assert reach.reaches is False
        assert reach.lone_outlier_min_frames is None


def test_a_loosened_kappa_lowers_the_threshold_rather_than_moving_a_constant():
    """The reach is read off κ, not off a hard-coded frame count — a user who set
    κ=1.5 genuinely is protected sooner, and the helper says so."""
    loose = rejection_reach(StackOptions(sigma_kappa=1.5), 6)
    assert loose.lone_outlier_min_frames == kappa_min_frames(1.5)
    assert loose.reaches is True
    assert rejection_reach(StackOptions(sigma_kappa=3.0), 6).reaches is False


def test_drizzle_says_nothing_when_its_two_pass_rejection_was_never_asked_for():
    off = rejection_reach(StackOptions(drizzle=True), 200)
    assert off.method == "drizzle" and off.reaches is False
    assert off.lone_outlier_min_frames is None


def test_drizzle_reports_the_same_kappa_bound_as_sigma_clip_not_its_dispatch_gate():
    """The bug this replaces: the drizzle branch reported ``n >= 4`` — the count
    the two-pass rejection *dispatches* at — as if it were the count at which it
    can remove anything. It is the same κ·σ clip as sigma clipping, so it is
    blind to a lone trail until :func:`kappa_min_frames`, measured on a real
    drizzle stack in ``tests/test_drizzle_reject.py``."""
    need = kappa_min_frames(3.0)
    assert need == 11
    opts = StackOptions(drizzle=True, drizzle_reject=True)
    for n in range(DRIZZLE_REJECT_MIN_FRAMES, need):
        reach = rejection_reach(opts, n)
        assert reach.method == "drizzle"
        assert reach.lone_outlier_min_frames == need
        assert reach.reaches is False, f"{n} frames wrongly reported as protected"
    assert rejection_reach(opts, need).reaches is True
    # Below the dispatch gate the pass does not even run — still unreached, and
    # still reported with the honest bound rather than the gate.
    too_few = rejection_reach(opts, DRIZZLE_REJECT_MIN_FRAMES - 1)
    assert too_few.reaches is False and too_few.lone_outlier_min_frames == need


def test_a_drizzled_mosaic_is_judged_on_its_panel_depth_not_its_frame_count():
    """The owner's shape: four panels, 40 subs, ten on any one spot. Deep enough
    by frame count, ten short of what the clip needs on a pixel."""
    opts = StackOptions(drizzle=True, drizzle_reject=True)
    assert rejection_reach(opts, 40, depth=10).reaches is False
    assert rejection_reach(opts, 40, depth=11).reaches is True
    # …and a single field of the same 40 subs is unaffected.
    assert rejection_reach(opts, 40).reaches is True


def test_a_loosened_kappa_lowers_the_drizzle_threshold_too():
    """Read off κ on the drizzle path as well — ``clip_reference`` is handed
    ``options.sigma_kappa``, the very same number."""
    loose = rejection_reach(
        StackOptions(drizzle=True, drizzle_reject=True, sigma_kappa=1.5), 6)
    assert loose.lone_outlier_min_frames == kappa_min_frames(1.5)
    assert loose.reaches is True


def test_reach_agrees_with_the_note_stackhealth_writes_after_the_stack():
    """One definition, two surfaces. `stackhealth` fires its `rejection_blind`
    note exactly when the recorded mode is sigma-clip and the frame count is under
    `kappa_min_frames`; `rejection_reach` must call the same stack unprotected
    *before* it runs, or the form and the finished picture contradict each other."""
    from seestack.io.project import StackRunRow
    from seestack.stackhealth import stack_health

    for n in (5, 8, 10, 11, 20):
        reach = rejection_reach(StackOptions(), n)
        run = StackRunRow(
            id=1, timestamp_utc="2026-07-14T00:00:00+00:00", output_basename="m42",
            fits_path="m42.fits", tiff_path=None, preview_path=None,
            n_frames_used=n, canvas_h=1080, canvas_w=1920,
            coverage_min=n, coverage_max=n, coverage_thin_frac=0.0,
            options_json="{}", rejection_mode="sigma-clip",
            calstat="dark+flat", is_mosaic=False,
        )
        blind = any(note.kind == "rejection_blind" for note in stack_health(run, []))
        assert blind is (not reach.reaches), f"disagreed at {n} frames"


def test_reach_and_the_note_agree_on_a_drizzled_run_too():
    """The same contract on the path the owner actually stacks mosaics with: the
    outlook before the night and the note on the finished picture are one
    answer, or the app contradicts itself a night apart."""
    from seestack.io.project import StackRunRow
    from seestack.stackhealth import stack_health

    opts = StackOptions(drizzle=True, drizzle_reject=True)
    for n in (5, 8, 10, 11, 20):
        reach = rejection_reach(opts, n)
        run = StackRunRow(
            id=1, timestamp_utc="2026-07-14T00:00:00+00:00", output_basename="m42",
            fits_path="m42.fits", tiff_path=None, preview_path=None,
            n_frames_used=n, canvas_h=1080, canvas_w=1920,
            coverage_min=n, coverage_max=n, coverage_thin_frac=0.0,
            options_json='{"drizzle": true, "drizzle_reject": true}',
            rejection_mode="drizzle-reject",
            calstat="dark+flat", is_mosaic=False,
        )
        blind = any(note.kind == "rejection_blind" for note in stack_health(run, []))
        assert blind is (not reach.reaches), f"disagreed at {n} frames"


def test_reach_and_the_note_agree_on_a_min_max_run_too():
    """The third mode, and the one the contract used to miss. ``rejection_reach``
    has always sized min/max by the *pixel* depth (``reach_n = min(n, depth)``),
    while ``stackhealth`` excluded the mode outright — so a mosaic two subs deep
    was warned about on the Stack form and then praised on the finished picture.
    Walk the floor in both directions and require one answer."""
    from seestack.io.project import StackRunRow
    from seestack.stackhealth import stack_health

    opts = StackOptions(min_max_reject=True, sigma_clip=False)
    for depth in (1, 2, 3, 4, 8):
        reach = rejection_reach(opts, 20, depth=depth)
        run = StackRunRow(
            id=1, timestamp_utc="2026-09-11T00:00:00+00:00", output_basename="m42",
            fits_path="m42.fits", tiff_path=None, preview_path=None,
            n_frames_used=20, canvas_h=1080, canvas_w=1920,
            coverage_min=depth, coverage_max=depth, coverage_thin_frac=0.0,
            coverage_median_depth=float(depth),
            options_json='{"min_max_reject": true, "sigma_clip": false}',
            rejection_mode="min-max-reject",
            calstat="dark+flat", is_mosaic=True,
        )
        blind = any(note.kind == "rejection_blind" for note in stack_health(run, []))
        assert blind is (not reach.reaches), f"disagreed at depth {depth}"


def test_the_min_max_floor_is_the_depth_the_accumulator_actually_trims_at():
    """The note's number has to be the accumulator's own behaviour, not a
    constant that happens to match today. Run the real accumulator either side of
    :data:`MIN_MAX_MIN_FRAMES` and require that the extreme survives below it and
    is gone at it — the fact the sentence ("below that it averages them all in")
    asserts to the user."""
    import numpy as np

    from seestack.stack.accumulator import MinMaxRejectAccumulator
    from seestack.stack.stacker import MIN_MAX_MIN_FRAMES, lone_outlier_min_depth

    floor = MIN_MAX_MIN_FRAMES
    assert lone_outlier_min_depth("min-max-reject", 3.0) == floor

    for depth in (floor - 1, floor):
        acc = MinMaxRejectAccumulator((1, 1), dtype=np.float32)
        acc.add(np.full((1, 1), 1000.0, dtype=np.float32))   # the "satellite"
        for _ in range(depth - 1):
            acc.add(np.full((1, 1), 10.0, dtype=np.float32))
        out = float(acc.result()[0, 0])
        if depth < floor:
            assert out > 10.0, f"the outlier should survive at depth {depth}"
        else:
            assert out == 10.0, f"the outlier should be gone at depth {depth}"


# --- lone_outlier_min_depth: the one definition the three surfaces share -------

def test_min_depth_is_the_order_statistic_floor_for_min_max():
    """Min/max removes an extreme from three samples up, whatever κ says — the
    bound is an order statistic, not a κ·σ test."""
    from seestack.stack.stacker import lone_outlier_min_depth

    for kappa in (1.0, 2.0, 3.0, 5.0):
        assert lone_outlier_min_depth("min-max-reject", kappa) == MIN_MAX_MIN_FRAMES


@pytest.mark.parametrize("mode", ["sigma-clip", "drizzle", "drizzle-reject"])
def test_every_kappa_sigma_spelling_shares_kappa_min_frames(mode):
    """The two drizzle spellings matter: ``combine_method`` says ``"drizzle"``
    (what will run) and ``RejectionStats`` records ``"drizzle-reject"`` (what
    did), and the header cards are stamped from the second. Both are the same
    κ·σ clip, so both must answer with κ-σ's bound — otherwise the finished
    picture and the pre-run warning disagree about the very same pass."""
    from seestack.stack.stacker import lone_outlier_min_depth

    for kappa in (1.5, 2.0, 3.0, 4.0):
        assert lone_outlier_min_depth(mode, kappa) == kappa_min_frames(kappa)


def test_a_plain_mean_has_no_depth_at_which_it_rejects():
    from seestack.stack.stacker import lone_outlier_min_depth

    assert lone_outlier_min_depth("mean", 3.0) is None
    assert lone_outlier_min_depth("", 3.0) is None


@pytest.mark.parametrize("kappa", [1.5, 2.0, 3.0, 4.0])
def test_rejection_reach_reports_exactly_the_shared_bound(kappa):
    """``rejection_reach`` must not carry a second copy of the number: whatever
    the helper says is the bound is what the pre-run verdict quotes."""
    from seestack.stack.stacker import lone_outlier_min_depth

    for opts, mode in (
        (StackOptions(sigma_kappa=kappa), "sigma-clip"),
        (StackOptions(sigma_kappa=kappa, min_max_reject=True), "min-max-reject"),
        (StackOptions(sigma_kappa=kappa, drizzle=True, drizzle_reject=True),
         "drizzle"),
    ):
        reach = rejection_reach(opts, 50)
        assert reach.method == mode
        assert reach.lone_outlier_min_frames == lone_outlier_min_depth(mode, kappa)
