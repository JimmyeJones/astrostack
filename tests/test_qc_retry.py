"""Transient QC-error retry: a frame that failed QC once is re-offered by the
auto-pipeline (``only_new=True``) so a transient read blip (NAS hiccup, a file
still being written) gets a second chance automatically; a second consecutive
failure is stamped terminal so a genuinely-corrupt file isn't re-QC'd on every
scan forever; and a retry that finally succeeds clears the stale error.

Mirrors the ingest cache-copy retry (v0.94.9) for the QC path.
"""

from __future__ import annotations

import pytest

pytest.importorskip("astropy")

from seestack.io.project import FrameRow, Project
from seestack.qc.metrics import FrameMetrics
from seestack.qc.runner import QCResult, apply_qc_result_to_db, build_qc_arglist


def _ok_result(frame_id: int) -> QCResult:
    return QCResult(
        frame_id=frame_id,
        metrics=FrameMetrics(
            star_count=42, sky_adu_median=100.0, fwhm_px=2.5,
            eccentricity_median=0.2, streak_detected=False, streak_count=0,
        ),
        error=None,
    )


def _err_result(frame_id: int, msg: str = "OSError: truncated") -> QCResult:
    return QCResult(frame_id=frame_id, metrics=None, error=msg)


def test_first_qc_failure_is_retryable_second_is_terminal(tmp_path):
    proj = Project.create(tmp_path / "p", name="T")
    try:
        src = tmp_path / "a.fit"
        src.write_bytes(b"x")
        fid = proj.add_frame(FrameRow(source_path=str(src)))

        # First failure: plain qc_error (retryable), frame stays accepted.
        apply_qc_result_to_db(proj, _err_result(fid))
        f = proj.get_frame(fid)
        assert f.reject_reason.startswith("qc_error:")
        assert f.accept is True
        assert build_qc_arglist(proj, only_new=True)[0][0] == fid  # re-offered

        # Second consecutive failure: terminal, no longer re-offered by the
        # auto-pipeline (only_new), so a corrupt file isn't re-QC'd forever.
        apply_qc_result_to_db(proj, _err_result(fid))
        f = proj.get_frame(fid)
        assert f.reject_reason.startswith("qc_error_final:")
        assert build_qc_arglist(proj, only_new=True) == []

        # A manual full re-QC (only_new=False) still retries even a terminal frame.
        assert build_qc_arglist(proj)[0][0] == fid
    finally:
        proj.close()


def test_qc_retry_that_succeeds_clears_the_stale_error(tmp_path):
    proj = Project.create(tmp_path / "p", name="T")
    try:
        fid = proj.add_frame(FrameRow(source_path="a.fit"))

        apply_qc_result_to_db(proj, _err_result(fid))
        assert proj.get_frame(fid).reject_reason.startswith("qc_error")

        # The retry now reads the frame fine — the stale qc_error must clear so it
        # no longer shows as "couldn't be quality-checked", and metrics land.
        apply_qc_result_to_db(proj, _ok_result(fid))
        f = proj.get_frame(fid)
        assert f.reject_reason is None
        assert f.accept is True
        assert f.star_count == 42
    finally:
        proj.close()


def test_qc_success_does_not_touch_a_user_rejection(tmp_path):
    """A successful QC only clears a qc_error reason — never a user/auto reject."""
    proj = Project.create(tmp_path / "p", name="T")
    try:
        fid = proj.add_frame(FrameRow(source_path="a.fit"))
        proj.update_frame(fid, accept=False, reject_reason="user", user_override=True)
        apply_qc_result_to_db(proj, _ok_result(fid))
        f = proj.get_frame(fid)
        assert f.reject_reason == "user"
        assert f.accept is False
        assert f.star_count == 42  # metrics still written
    finally:
        proj.close()
