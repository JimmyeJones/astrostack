"""Reclaiming streaked subs: streaked frames can be kept (flagged, not rejected)
so a stack with per-pixel rejection removes the streak instead of the whole sub.
"""

from __future__ import annotations

import pytest

pytest.importorskip("astropy")

from seestack.io.project import FrameRow, Project
from seestack.qc.metrics import FrameMetrics
from seestack.qc.runner import QCResult, apply_qc_result_to_db


def _streak_result(frame_id: int) -> QCResult:
    return QCResult(
        frame_id=frame_id,
        metrics=FrameMetrics(
            star_count=42, sky_adu_median=100.0, fwhm_px=2.5,
            eccentricity_median=0.2, streak_detected=True, streak_count=1,
        ),
        error=None,
    )


def test_streak_frame_rejected_by_default(tmp_path):
    proj = Project.create(tmp_path / "p", name="T")
    try:
        fid = proj.add_frame(FrameRow(source_path="a.fit"))
        apply_qc_result_to_db(proj, _streak_result(fid))  # auto_reject default True
        f = proj.get_frame(fid)
        assert f.streak_detected is True
        assert f.accept is False
        assert f.reject_reason == "auto:streak"
    finally:
        proj.close()


def test_streak_frame_kept_when_auto_reject_off(tmp_path):
    proj = Project.create(tmp_path / "p", name="T")
    try:
        fid = proj.add_frame(FrameRow(source_path="a.fit"))
        apply_qc_result_to_db(proj, _streak_result(fid), auto_reject=False)
        f = proj.get_frame(fid)
        # Flagged so the UI/stack can see it, but still accepted so per-pixel
        # rejection at stack time can clean it rather than discarding it whole.
        assert f.streak_detected is True
        assert f.accept is True
        assert f.reject_reason is None
        # Metrics are still written either way.
        assert f.star_count == 42
    finally:
        proj.close()


def test_keep_does_not_override_user_rejection(tmp_path):
    """A user who explicitly rejected a frame keeps that decision regardless."""
    proj = Project.create(tmp_path / "p", name="T")
    try:
        fid = proj.add_frame(FrameRow(source_path="a.fit"))
        proj.update_frame(fid, accept=False, reject_reason="user", user_override=True)
        apply_qc_result_to_db(proj, _streak_result(fid), auto_reject=True)
        f = proj.get_frame(fid)
        # auto:streak must not clobber a user override.
        assert f.accept is False
        assert f.reject_reason == "user"
    finally:
        proj.close()
