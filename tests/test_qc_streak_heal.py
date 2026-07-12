"""A frame auto-rejected as a streak self-heals on a clean re-QC.

``apply_qc_result_to_db`` already clears a stale ``qc_error`` reject reason when
QC later succeeds. The sibling case — a frame auto-rejected ``auto:streak`` that
is no longer a streak on a subsequent full re-QC (``only_new=False``) — must heal
the same way, else a now-clean frame is silently kept out of the stack with a
contradictory ``accept=False`` / ``streak_detected=False`` record. The heal must
never touch a user override or a non-streak reject reason (mirrors
``reconcile_streak_rejections``' un-reject-only contract).
"""

from __future__ import annotations

import pytest

pytest.importorskip("astropy")

from seestack.io.project import FrameRow, Project
from seestack.qc.metrics import FrameMetrics
from seestack.qc.runner import QCResult, apply_qc_result_to_db


def _result(frame_id: int, *, streak: bool) -> QCResult:
    return QCResult(
        frame_id=frame_id,
        metrics=FrameMetrics(
            star_count=42, sky_adu_median=100.0, fwhm_px=2.5,
            eccentricity_median=0.2, streak_detected=streak,
            streak_count=(2 if streak else 0),
        ),
        error=None,
    )


def _add(proj: Project, name: str) -> int:
    return proj.add_frame(FrameRow(source_path=name))


def test_auto_streak_reject_self_heals_on_clean_reqc(tmp_path):
    proj = Project.create(tmp_path / "p", name="T")
    try:
        fid = _add(proj, "a.fit")
        # Streak detected -> auto-rejected.
        apply_qc_result_to_db(proj, _result(fid, streak=True))
        f = proj.get_frame(fid)
        assert f.accept is False and f.reject_reason == "auto:streak"

        # Clean re-QC -> the frame is un-rejected (no contradictory record).
        apply_qc_result_to_db(proj, _result(fid, streak=False))
        f = proj.get_frame(fid)
        assert f.accept is True
        assert f.reject_reason is None
        assert f.streak_detected is False
    finally:
        proj.close()


def test_heal_respects_user_override(tmp_path):
    proj = Project.create(tmp_path / "p", name="T")
    try:
        fid = _add(proj, "b.fit")
        apply_qc_result_to_db(proj, _result(fid, streak=True))
        proj.update_frame(fid, user_override=True)  # user pins the rejection
        apply_qc_result_to_db(proj, _result(fid, streak=False))
        f = proj.get_frame(fid)
        assert f.accept is False
        assert f.reject_reason == "auto:streak"  # untouched
    finally:
        proj.close()


def test_still_streaked_frame_stays_rejected(tmp_path):
    proj = Project.create(tmp_path / "p", name="T")
    try:
        fid = _add(proj, "c.fit")
        apply_qc_result_to_db(proj, _result(fid, streak=True))
        apply_qc_result_to_db(proj, _result(fid, streak=True))
        f = proj.get_frame(fid)
        assert f.accept is False
        assert f.reject_reason == "auto:streak"
    finally:
        proj.close()


def test_heal_leaves_a_non_streak_reject_reason_untouched(tmp_path):
    proj = Project.create(tmp_path / "p", name="T")
    try:
        fid = _add(proj, "d.fit")
        proj.update_frame(fid, accept=False, reject_reason="manual", user_override=True)
        apply_qc_result_to_db(proj, _result(fid, streak=False))
        f = proj.get_frame(fid)
        assert f.accept is False
        assert f.reject_reason == "manual"  # only auto:streak is healed
    finally:
        proj.close()
