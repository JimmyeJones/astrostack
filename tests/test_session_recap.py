"""Last-session recap — plain-language summary of the most recent capture night."""

from datetime import datetime, timedelta

from seestack.io.project import FrameRow, Project
from seestack.session_recap import (
    bucket_reject_reason,
    session_recap,
)


def _frame(ts: datetime | None, *, exposure=10.0, accept=True, reject_reason=None):
    return FrameRow(
        source_path=f"/x/{ts}-{accept}-{reject_reason}-{id(ts)}.fit",
        timestamp_utc=ts.isoformat() if ts else None,
        exposure_s=exposure,
        accept=accept,
        reject_reason=reject_reason,
    )


def test_returns_none_when_no_frames_have_timestamps(tmp_path):
    proj = Project.create(tmp_path / "p", name="t")
    try:
        proj.add_frame(_frame(None))
        assert session_recap(proj) is None
    finally:
        proj.close()


def test_isolates_the_most_recent_session(tmp_path):
    """Two nights a week apart: the recap covers only the latest night's subs."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        night1 = datetime(2026, 7, 1, 22, 0, 0)
        for i in range(5):  # last week's session — must be excluded
            proj.add_frame(_frame(night1 + timedelta(seconds=30 * i)))
        night2 = datetime(2026, 7, 8, 22, 0, 0)
        for i in range(8):  # this session
            proj.add_frame(_frame(night2 + timedelta(seconds=30 * i)))
        for i in range(2):  # two rejected this session
            proj.add_frame(_frame(night2 + timedelta(minutes=5, seconds=i),
                                  accept=False, reject_reason="auto:streak"))

        recap = session_recap(proj)
        assert recap is not None
        assert recap.n_frames == 10  # only night2's 8 kept + 2 rejected
        assert recap.n_kept == 8
        assert recap.n_set_aside == 2
        assert recap.reject_buckets == {"trailed": 2}
        # Integration this session (kept) vs total across all sessions (kept).
        assert recap.kept_exposure_s == 80.0
        assert recap.session_exposure_s == 100.0  # 10 subs × 10 s
        assert recap.total_kept_exposure_s == 130.0  # 5 (night1) + 8 (night2) kept
        assert recap.start_utc == night2.isoformat()
        assert recap.end_utc == (night2 + timedelta(minutes=5, seconds=1)).isoformat()
    finally:
        proj.close()


def test_single_session_is_the_whole_target(tmp_path):
    proj = Project.create(tmp_path / "p", name="t")
    try:
        base = datetime(2026, 7, 8, 21, 0, 0)
        for i in range(3):
            proj.add_frame(_frame(base + timedelta(minutes=i)))
        recap = session_recap(proj)
        assert recap is not None
        assert recap.n_frames == 3 and recap.n_kept == 3 and recap.n_set_aside == 0
        assert recap.reject_buckets == {}
    finally:
        proj.close()


def test_reject_buckets_group_reasons_plainly(tmp_path):
    proj = Project.create(tmp_path / "p", name="t")
    try:
        base = datetime(2026, 7, 8, 21, 0, 0)
        reasons = [
            "auto:streak", "bulk:trailed",              # trailed × 2
            "auto:grade:sky_adu_median",                # cloudy
            "auto:grade:transparency_score",            # cloudy
            "auto:grade:fwhm_px", "auto:grade:eccentricity_median",  # soft × 2
            "qc_error",                                 # unreadable
            "user", None,                               # set aside by you × 2
            "something_weird",                          # other
        ]
        for i, r in enumerate(reasons):
            proj.add_frame(_frame(base + timedelta(seconds=i), accept=False, reject_reason=r))
        recap = session_recap(proj)
        assert recap is not None
        assert recap.reject_buckets == {
            "trailed": 2,
            "cloudy": 2,
            "soft": 2,
            "unreadable": 1,
            "set aside by you": 2,
            "other": 1,
        }
        assert recap.n_kept == 0 and recap.n_set_aside == 10
    finally:
        proj.close()


def test_bucket_reject_reason_direct():
    assert bucket_reject_reason("auto:streak") == "trailed"
    assert bucket_reject_reason("bulk:streaked") == "trailed"
    assert bucket_reject_reason("auto:grade:sky_adu_median") == "cloudy"
    assert bucket_reject_reason("auto:grade:transparency_score") == "cloudy"
    assert bucket_reject_reason("auto:grade:fwhm_px") == "soft"
    assert bucket_reject_reason("auto:fwhm") == "soft"
    assert bucket_reject_reason("qc_error") == "unreadable"
    assert bucket_reject_reason("user") == "set aside by you"
    assert bucket_reject_reason(None) == "set aside by you"
    assert bucket_reject_reason("mystery") == "other"


def test_handles_trailing_z_and_unparseable_timestamps(tmp_path):
    proj = Project.create(tmp_path / "p", name="t")
    try:
        proj.add_frame(FrameRow(source_path="/x/a.fit",
                                timestamp_utc="2026-07-08T22:00:00Z", exposure_s=10.0))
        proj.add_frame(FrameRow(source_path="/x/b.fit",
                                timestamp_utc="2026-07-08T22:00:30Z", exposure_s=10.0))
        proj.add_frame(FrameRow(source_path="/x/c.fit",
                                timestamp_utc="not-a-date", exposure_s=10.0))  # ignored
        recap = session_recap(proj)
        assert recap is not None
        assert recap.n_frames == 2  # the unparseable one is skipped, not crashed on
        assert recap.n_kept == 2
    finally:
        proj.close()
