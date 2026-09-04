"""``frames.restored_utc`` — the record that a sub was *put back*, and by whom.

The Target page can only say "your picture was made before these subs came back"
if something wrote down *when* they came back. Three reconsiderations un-reject a
sub today and none of them left a trace, so this file pins that all three now
stamp, that nothing else does, and that the stamp is the one shape the
comparison against a stack run's ``timestamp_utc`` needs.

The negative tests matter as much as the positive ones: a stamp written where no
restoration happened would put a permanent "re-stack me" nudge on a target whose
picture is perfectly fine.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

pytest.importorskip("astropy")

from seestack.io.project import (
    REJECT_REASON_FILE_MISSING,
    FrameRow,
    Project,
    restoration_stamp,
)
from seestack.qc.runner import reconcile_streak_rejections
from seestack.session_recap import parse_capture_time

_T0 = datetime(2026, 3, 14, 21, 0, tzinfo=timezone.utc)


def _stamp(minutes: float) -> str:
    return (_T0 + timedelta(minutes=minutes)).isoformat().replace("+00:00", "Z")


def test_the_stamp_parses_and_is_now():
    """It is compared against a stack run's ``timestamp_utc``, which is written
    as an aware ISO-8601 instant — so this has to parse into the same kind of
    thing, or the comparison silently never fires."""
    when = parse_capture_time(restoration_stamp())
    assert when is not None and when.tzinfo is not None
    assert abs((datetime.now(timezone.utc) - when).total_seconds()) < 60


def test_a_rescued_galaxy_sub_records_when_it_came_back(tmp_path):
    """The v0.346.0 path: a stationary flagged component is re-accepted, and now
    says when. Fails before — ``restored_utc`` was ``None`` on every frame."""
    proj = Project.create(tmp_path / "p", name="NGC 4565")
    try:
        for i in range(10):
            proj.add_frame(FrameRow(source_path=f"clean{i}.fit",
                                    timestamp_utc=_stamp(7 * i), accept=True))
        streaked = [proj.add_frame(FrameRow(
            source_path=f"streak{i}.fit", timestamp_utc=_stamp(40 * i),
            streak_detected=True, streak_count=1,
            streak_cx=0.51 + 0.005 * i, streak_cy=0.49,
            accept=False, reject_reason="auto:streak")) for i in range(6)]
        assert set(reconcile_streak_rejections(proj)) == set(streaked)
        for fid in streaked:
            f = proj.get_frame(fid)
            assert f.accept is True
            assert parse_capture_time(f.restored_utc) is not None
    finally:
        proj.close()


def test_a_sub_that_was_never_set_aside_carries_no_stamp(tmp_path):
    """The silence half: an ordinary accepted sub must never look like it came
    back, or every healthy target grows a permanent re-stack nudge."""
    proj = Project.create(tmp_path / "p", name="NGC 4565")
    try:
        for i in range(10):
            proj.add_frame(FrameRow(source_path=f"clean{i}.fit",
                                    timestamp_utc=_stamp(7 * i), accept=True))
        streaked = [proj.add_frame(FrameRow(
            source_path=f"streak{i}.fit", timestamp_utc=_stamp(40 * i),
            streak_detected=True, streak_count=1,
            streak_cx=0.51 + 0.005 * i, streak_cy=0.49,
            accept=False, reject_reason="auto:streak")) for i in range(6)]
        reconcile_streak_rejections(proj)
        for f in proj.iter_frames():
            if f.id in streaked:
                continue
            assert f.restored_utc is None
    finally:
        proj.close()


def test_a_real_trail_that_stays_rejected_carries_no_stamp(tmp_path):
    """A sub that was *not* put back has nothing to record — the stamp means
    "came back", not "was reconsidered"."""
    proj = Project.create(tmp_path / "p", name="M 31")
    try:
        for i in range(12):
            proj.add_frame(FrameRow(source_path=f"c{i}.fit",
                                    timestamp_utc=_stamp(7 * i), accept=True))
        spots = [(0.13, 0.22), (0.86, 0.35), (0.40, 0.92), (0.72, 0.08)]
        sats = [proj.add_frame(FrameRow(
            source_path=f"sat{i}.fit", timestamp_utc=_stamp(50 * i),
            streak_detected=True, streak_count=1, streak_cx=x, streak_cy=y,
            accept=False, reject_reason="auto:streak"))
            for i, (x, y) in enumerate(spots)]
        assert reconcile_streak_rejections(proj) == []
        for fid in sats:
            f = proj.get_frame(fid)
            assert f.accept is False
            assert f.restored_utc is None
    finally:
        proj.close()


def test_a_missing_file_that_reappears_records_when_it_came_back(tmp_path):
    """The walk-away path: the drive comes back, the sub does too, and the
    published picture was made without it."""
    src = tmp_path / "sub_001.fit"
    src.write_bytes(b"x")
    proj = Project.create(tmp_path / "p", name="M 42")
    try:
        fid = proj.add_frame(FrameRow(
            source_path=str(src), timestamp_utc=_stamp(0),
            accept=False, reject_reason=REJECT_REASON_FILE_MISSING))
        assert proj.restore_missing_frames() == [fid]
        f = proj.get_frame(fid)
        assert f.accept is True and f.reject_reason is None
        assert parse_capture_time(f.restored_utc) is not None
    finally:
        proj.close()


def test_a_still_missing_file_carries_no_stamp(tmp_path):
    """Nothing came back, so nothing is recorded — and the nudge stays quiet on
    an install that is genuinely still missing its subs."""
    proj = Project.create(tmp_path / "p", name="M 42")
    try:
        fid = proj.add_frame(FrameRow(
            source_path=str(tmp_path / "gone.fit"), timestamp_utc=_stamp(0),
            accept=False, reject_reason=REJECT_REASON_FILE_MISSING))
        assert proj.restore_missing_frames() == []
        assert proj.get_frame(fid).restored_utc is None
    finally:
        proj.close()


def test_a_regraded_sub_records_when_it_came_back(tmp_path):
    """The third path: auto-grade reconsiders a rejection on a bigger population
    and puts the sub back."""
    from seestack.qc.grading import GradeReport, apply_grade_reaccepts

    proj = Project.create(tmp_path / "p", name="M 81")
    try:
        fid = proj.add_frame(FrameRow(
            source_path="graded.fit", timestamp_utc=_stamp(0),
            accept=False, reject_reason="auto:grade:fwhm_px"))
        held = proj.add_frame(FrameRow(
            source_path="mine.fit", timestamp_utc=_stamp(5),
            accept=False, reject_reason="user", user_override=True))
        report = GradeReport(sensitivity="normal", threshold=2.5, n_accepted=0,
                             n_considered=0, re_accept=[fid, held])
        assert apply_grade_reaccepts(proj, report) == [fid]
        assert parse_capture_time(proj.get_frame(fid).restored_utc) is not None
        # The user's own decision is untouched, stamp included.
        assert proj.get_frame(held).restored_utc is None
    finally:
        proj.close()


def test_restored_frame_stamps_lists_only_stack_ready_subs(tmp_path):
    """A restored sub that is still unsolved would not go into a re-stack, so
    promising it would be a promise the re-stack couldn't keep. It self-heals the
    moment the solve lands."""
    now = restoration_stamp()
    proj = Project.create(tmp_path / "p", name="M 51")
    try:
        proj.add_frame(FrameRow(source_path="solved.fit", accept=True,
                                wcs_json="{}", restored_utc=now))
        proj.add_frame(FrameRow(source_path="unsolved.fit", accept=True,
                                restored_utc=now))
        proj.add_frame(FrameRow(source_path="rejected.fit", accept=False,
                                wcs_json="{}", reject_reason="user",
                                restored_utc=now))
        proj.add_frame(FrameRow(source_path="ordinary.fit", accept=True,
                                wcs_json="{}"))
        assert proj.restored_frame_stamps() == [now]
    finally:
        proj.close()
