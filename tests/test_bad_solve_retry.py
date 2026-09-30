"""A sub the stack dropped for a wrong-scale plate solve gets one more solve.

Observer issue #965. ``run_stack`` excludes a sub whose solved plate scale
disagrees with its neighbours and flags it rejected — correctly, it would
reproject at the wrong scale — but the flag was **terminal**, by two independent
routes at once: ``build_solve_arglist`` skips a frame with a truthy ``wcs_json``
(the wrong solve is still in the column, because nothing outside the solve path
clears one) *and* skips a rejected frame whose reason is not ``solve_failed:``,
while ``apply_grade_reaccepts`` only ever reconsiders ``auto:grade`` rejections.
So a night the solver was flaky cost those subs from every future stack,
permanently — and the observer's own control says the flake is not deterministic:
the same bytes solved correctly on the other attempt. His library carries 178
such rows.

These tests pin the retry and, just as importantly, the four places it stands
down: the once-ever ledger that stops a persistently-bad frame being re-solved on
every scan, a hand-graded sub, the displaced-footprint rejection, and a library
that has never had one.
"""

from __future__ import annotations

import json

from seestack.io.project import (
    REJECT_REASON_BAD_SOLVE_FOOTPRINT,
    REJECT_REASON_BAD_SOLVE_SCALE,
)
from seestack.solve.runner import (
    BAD_SOLVE_RETRIED_META_KEY,
    build_solve_arglist,
    reconcile_bad_solve_frames,
)
from seestack.stack.stacker import StackOptions, run_stack
from tests.synth import make_synth_wcs_text
from tests.test_stack_pipeline import _build_project

# The scale the fixture's synthetic WCS carries, and the +9.45 % false solve
# ``tests/test_stack_pipeline.py`` already uses to trip the scale guard.
_GOOD_SCALE = 5.0
_WRONG_SCALE = _GOOD_SCALE * 1.0945


def _project_with_one_false_solve(tmp_path, n: int = 11):
    """``(project, bad_frame_id)`` after a real stack has dropped and flagged it."""
    proj = _build_project(tmp_path, n=n)
    bad = list(proj.iter_frames())[-1]
    proj.update_frame(
        bad.id,
        wcs_json=make_synth_wcs_text(pixscale_arcsec=_WRONG_SCALE),
        pixscale_arcsec=_WRONG_SCALE,
    )
    run_stack(proj, StackOptions(sigma_clip=False, max_workers=2,
                                 output_name="scaleguard"))
    row = proj.get_frame(bad.id)
    assert row.accept is False
    assert row.reject_reason == REJECT_REASON_BAD_SOLVE_SCALE
    return proj, bad.id


def test_a_sub_dropped_for_its_scale_is_offered_one_more_solve(tmp_path):
    """FAIL-BEFORE: nothing ever looked at these frames again."""
    proj, bad_id = _project_with_one_false_solve(tmp_path)
    try:
        # The bug, stated as the solver sees it: every other frame is solved, so
        # the queue is empty, and the one frame that needs solving is not in it.
        assert bad_id not in [fid for fid, *_ in build_solve_arglist(proj)]

        assert reconcile_bad_solve_frames(proj) == [bad_id]

        row = proj.get_frame(bad_id)
        # The wrong solve is gone — all of it, not just the WCS text: the
        # centre, scale and rotation were derived from the same solve, and
        # ``Project.solved_frame_geometry`` reads that scale.
        assert row.wcs_json is None
        assert row.pixscale_arcsec is None
        assert row.ra_center_deg is None and row.dec_center_deg is None
        assert row.rotation_deg is None
        # …and so is the rejection, stamped with when it came back.
        assert row.accept is True
        assert row.reject_reason is None
        assert row.restored_utc is not None
        # Which is the whole point: the solve pass now offers it.
        assert bad_id in [fid for fid, *_ in build_solve_arglist(proj)]
    finally:
        proj.close()


def test_an_unsolved_sub_cannot_reach_a_stack_in_the_meantime(tmp_path):
    """Putting it back changes no picture. Between the retry and a successful
    solve the frame is accepted *and* unsolved, and ``run_stack`` combines only
    frames that are both — so the stack is exactly the one it was."""
    proj, bad_id = _project_with_one_false_solve(tmp_path)
    try:
        reconcile_bad_solve_frames(proj)
        res = run_stack(proj, StackOptions(sigma_clip=False, max_workers=2,
                                          output_name="after_retry"))
        assert res.n_frames_used == 10
        # …and it is not re-flagged either: it was never a candidate.
        assert proj.get_frame(bad_id).accept is True
        assert proj.get_frame(bad_id).reject_reason is None
    finally:
        proj.close()


def test_the_retry_is_offered_once_and_never_again(tmp_path):
    """The bound that makes this safe unattended.

    A re-solve that lands on the same wrong scale is re-rejected by the next
    stack. Without the ledger the pair loops: one fast ASTAP run per bad frame
    per scan, on exactly the nights the owner walked away.
    """
    proj, bad_id = _project_with_one_false_solve(tmp_path)
    try:
        assert reconcile_bad_solve_frames(proj) == [bad_id]
        assert json.loads(proj.get_meta(BAD_SOLVE_RETRIED_META_KEY)) == [bad_id]

        # The re-solve comes back wrong again, and the next stack drops it again.
        proj.update_frame(
            bad_id,
            wcs_json=make_synth_wcs_text(pixscale_arcsec=_WRONG_SCALE),
            pixscale_arcsec=_WRONG_SCALE, accept=True, reject_reason=None,
        )
        run_stack(proj, StackOptions(sigma_clip=False, max_workers=2,
                                     output_name="again"))
        assert proj.get_frame(bad_id).reject_reason == REJECT_REASON_BAD_SOLVE_SCALE

        assert reconcile_bad_solve_frames(proj) == []
        assert proj.get_frame(bad_id).accept is False
    finally:
        proj.close()


def test_a_sub_the_user_graded_by_hand_is_left_alone(tmp_path):
    """Automation never undoes a person's decision."""
    proj, bad_id = _project_with_one_false_solve(tmp_path)
    try:
        proj.update_frame(bad_id, user_override=True)
        assert reconcile_bad_solve_frames(proj) == []
        row = proj.get_frame(bad_id)
        assert row.accept is False
        assert row.wcs_json is not None
    finally:
        proj.close()


def test_the_displaced_footprint_rejection_is_not_retried(tmp_path):
    """Deliberately narrow. A footprint far from the group is much more often a
    genuine stray — a sub from another target in the folder — which would re-solve
    to the same wrong place and be dropped again, for one wasted solve. Only the
    *scale* rejection is the flake the observer measured."""
    proj, bad_id = _project_with_one_false_solve(tmp_path)
    try:
        proj.update_frame(bad_id, reject_reason=REJECT_REASON_BAD_SOLVE_FOOTPRINT)
        assert reconcile_bad_solve_frames(proj) == []
        assert proj.get_frame(bad_id).accept is False
    finally:
        proj.close()


def test_a_library_that_never_had_one_is_not_written_to(tmp_path):
    """No candidates → no ledger, no writes, and nothing to read on any install
    that predates the key."""
    proj = _build_project(tmp_path, n=4)
    try:
        assert reconcile_bad_solve_frames(proj) == []
        assert proj.get_meta(BAD_SOLVE_RETRIED_META_KEY) is None
    finally:
        proj.close()


def test_the_scan_offers_the_retry_in_its_solve_phase(tmp_path):
    """The wiring: it runs where the decision belongs, before the solve arglist
    is built, so the frames it puts back are in *this* pass."""
    from seestack.io.scanner import run_qc_and_solve

    proj, bad_id = _project_with_one_false_solve(tmp_path)
    try:
        summary = run_qc_and_solve(proj, run_qc=False, run_solve=True,
                                   serial=True)
        assert summary["bad_solve_resolve_offered"] == 1
        # It reached the queue this pass rather than the next one.
        assert summary["solve_total"] == 1
    finally:
        proj.close()
