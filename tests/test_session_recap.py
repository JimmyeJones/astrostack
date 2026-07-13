"""Last-session recap — plain-language summary of the most recent capture night."""

from datetime import datetime, timedelta

from seestack.io.project import FrameRow, Project
from seestack.session_recap import (
    bucket_reject_reason,
    session_recap,
)


def _frame(ts: datetime | None, *, exposure=10.0, accept=True, reject_reason=None,
           fwhm_px=None):
    return FrameRow(
        source_path=f"/x/{ts}-{accept}-{reject_reason}-{fwhm_px}-{id(ts)}.fit",
        timestamp_utc=ts.isoformat() if ts else None,
        exposure_s=exposure,
        accept=accept,
        reject_reason=reject_reason,
        fwhm_px=fwhm_px,
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


def _add_session(proj, night, *, n, fwhm, accept=True, reject_reason=None):
    """Add ``n`` frames all captured on ``night`` (30 s apart) with the given FWHM."""
    for i in range(n):
        proj.add_frame(_frame(night + timedelta(seconds=30 * i), fwhm_px=fwhm,
                              accept=accept, reject_reason=reject_reason))


def test_quality_drift_flags_a_soft_newest_session(tmp_path):
    """A sharp first night then a soft second night → the recap nudges about focus."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        _add_session(proj, datetime(2026, 7, 1, 22, 0, 0), n=8, fwhm=3.4)   # sharp
        _add_session(proj, datetime(2026, 7, 8, 22, 0, 0), n=8, fwhm=5.2)   # soft
        recap = session_recap(proj)
        assert recap is not None
        d = recap.quality_drift
        assert d is not None
        assert d.kind == "fwhm"
        assert d.latest_fwhm_px == 5.2
        assert d.baseline_fwhm_px == 3.4
        assert d.n_latest == 8 and d.n_baseline == 8
    finally:
        proj.close()


def test_quality_drift_silent_when_newest_is_as_sharp(tmp_path):
    """Two nights of comparable seeing → no nudge (must not nag on normal wobble)."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        _add_session(proj, datetime(2026, 7, 1, 22, 0, 0), n=8, fwhm=3.4)
        _add_session(proj, datetime(2026, 7, 8, 22, 0, 0), n=8, fwhm=3.7)  # 9% softer only
        recap = session_recap(proj)
        assert recap is not None
        assert recap.quality_drift is None
    finally:
        proj.close()


def test_quality_drift_needs_a_prior_session(tmp_path):
    """A single (soft) session has no baseline to compare against → no nudge."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        _add_session(proj, datetime(2026, 7, 8, 22, 0, 0), n=8, fwhm=6.0)
        recap = session_recap(proj)
        assert recap is not None
        assert recap.quality_drift is None
    finally:
        proj.close()


def test_quality_drift_ignores_a_thin_newest_session(tmp_path):
    """Too few measured subs in the newest session → not enough to trust its median."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        _add_session(proj, datetime(2026, 7, 1, 22, 0, 0), n=8, fwhm=3.0)
        _add_session(proj, datetime(2026, 7, 8, 22, 0, 0), n=2, fwhm=6.0)  # only 2 subs
        recap = session_recap(proj)
        assert recap is not None
        assert recap.quality_drift is None
    finally:
        proj.close()


def test_quality_drift_uses_the_best_prior_session_as_baseline(tmp_path):
    """Baseline is the *sharpest* prior night, not the most recent prior one."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        _add_session(proj, datetime(2026, 7, 1, 22, 0, 0), n=8, fwhm=3.0)  # sharpest ever
        _add_session(proj, datetime(2026, 7, 5, 22, 0, 0), n=8, fwhm=4.5)  # a softer night
        _add_session(proj, datetime(2026, 7, 8, 22, 0, 0), n=8, fwhm=5.0)  # newest
        recap = session_recap(proj)
        assert recap is not None
        d = recap.quality_drift
        assert d is not None
        assert d.baseline_fwhm_px == 3.0  # compares against the best, not 4.5
    finally:
        proj.close()


def test_quality_drift_only_counts_accepted_measured_subs(tmp_path):
    """Rejected subs and subs with no FWHM don't feed the per-session median."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        _add_session(proj, datetime(2026, 7, 1, 22, 0, 0), n=6, fwhm=3.4)
        # Newest night: 6 soft accepted subs (drive the drift) plus noise that must
        # not count — a rejected sharp sub and one with no FWHM measured.
        night2 = datetime(2026, 7, 8, 22, 0, 0)
        _add_session(proj, night2, n=6, fwhm=5.2)
        proj.add_frame(_frame(night2 + timedelta(minutes=5), fwhm_px=2.0,
                              accept=False, reject_reason="auto:streak"))
        proj.add_frame(_frame(night2 + timedelta(minutes=6), fwhm_px=None))
        recap = session_recap(proj)
        assert recap is not None
        d = recap.quality_drift
        assert d is not None
        assert d.latest_fwhm_px == 5.2 and d.n_latest == 6  # noise excluded
    finally:
        proj.close()


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
