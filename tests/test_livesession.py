"""'Tonight, live' — the session happening *right now*, from the frames table."""

from datetime import datetime, timedelta, timezone

from seestack.io.project import FrameRow, Project
from seestack.livesession import (
    CONDITIONS_MIN_FRAMES,
    CONDITIONS_WINDOW_FRAMES,
    LIVE_STALE_MINUTES,
    QUIET_CEILING_MINUTES,
    QUIET_MIN_FRAMES,
    live_session,
)
from seestack.session_recap import last_session_frames

NOW = datetime(2026, 7, 8, 23, 30, 0, tzinfo=timezone.utc)


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


def _fill(proj, start, n, *, step_s=30, **kw):
    """Add ``n`` subs ``step_s`` apart from ``start``, returning the last stamp."""
    last = start
    for i in range(n):
        last = start + timedelta(seconds=step_s * i)
        proj.add_frame(_frame(last, **kw))
    return last


def test_no_datable_frames_reports_nothing(tmp_path):
    proj = Project.create(tmp_path / "p", name="t")
    try:
        proj.add_frame(_frame(None))
        assert live_session(proj, now=NOW) is None
    finally:
        proj.close()


def test_a_night_still_filling_up_reads_as_active(tmp_path):
    """The whole point: subs landing now → active, with tonight's counts only."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        # Last week's night — must not be counted in tonight's totals.
        _fill(proj, NOW - timedelta(days=7), 40)
        # Tonight: 30 kept + 6 set aside, the newest a minute ago.
        _fill(proj, NOW - timedelta(minutes=60), 30, step_s=60)
        _fill(proj, NOW - timedelta(minutes=6), 6, step_s=60,
              accept=False, reject_reason="auto:grade:sky")
        live = live_session(proj, now=NOW)
        assert live is not None
        assert live.active is True
        assert live.n_frames == 36
        assert live.n_kept == 30
        assert live.n_set_aside == 6
        # Integration so far is the *kept* exposure, which is what a goal counts.
        assert live.kept_exposure_s == 300.0
        assert live.session_exposure_s == 360.0
        # …and the all-time figure still spans both nights.
        assert live.total_kept_exposure_s == 700.0
        assert live.reject_buckets == {"cloudy": 6}
        assert live.minutes_since_latest is not None
        assert live.minutes_since_latest < 2.0
    finally:
        proj.close()


def test_a_finished_night_is_reported_but_not_active(tmp_path):
    """A session that stopped hours ago is still summarised — with active False —
    so the page can fall back to the recap instead of showing nothing."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        _fill(proj, NOW - timedelta(hours=5), 20, step_s=60)
        live = live_session(proj, now=NOW)
        assert live is not None
        assert live.active is False
        assert live.n_frames == 20
        assert live.minutes_since_latest > LIVE_STALE_MINUTES
    finally:
        proj.close()


def test_a_gap_shorter_than_the_stale_window_stays_active(tmp_path):
    """A cloud the mount waits out, or a re-point, must not read as 'stopped' —
    that is exactly the wrong answer for someone asking 'is it still working?'."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        _fill(proj, NOW - timedelta(minutes=49), 20, step_s=60)  # last sub 30 min ago
        live = live_session(proj, now=NOW)
        assert live is not None
        assert live.active is True
        assert 29.0 < live.minutes_since_latest < 32.0
    finally:
        proj.close()


def test_the_stale_boundary_is_the_configured_one(tmp_path):
    proj = Project.create(tmp_path / "p", name="t")
    try:
        latest = _fill(proj, NOW - timedelta(hours=2), 10, step_s=60)
        # Exactly on the boundary counts as active; a minute past does not.
        on = latest + timedelta(minutes=LIVE_STALE_MINUTES)
        assert live_session(proj, now=on).active is True
        assert live_session(proj, now=on + timedelta(minutes=1)).active is False
    finally:
        proj.close()


def test_a_sub_stamped_in_the_future_reads_as_just_now(tmp_path):
    """A mis-set camera clock must never produce a negative age (or an inactive
    night while subs are visibly landing)."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        _fill(proj, NOW + timedelta(minutes=10), 6, step_s=60)
        live = live_session(proj, now=NOW)
        assert live.minutes_since_latest == 0.0
        assert live.active is True
    finally:
        proj.close()


def test_conditions_grade_the_rolling_window_not_the_whole_night(tmp_path):
    """Cloud rolling in at 2 a.m. must show up even after a great first half —
    the reason to look at a rolling window rather than the night's average."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        _fill(proj, NOW - timedelta(hours=3), 100, step_s=60)          # all kept
        _fill(proj, NOW - timedelta(minutes=20), 20, step_s=60,        # all lost
              accept=False, reject_reason="auto:grade:sky")
        live = live_session(proj, now=NOW)
        c = live.conditions
        assert c.n_recent == CONDITIONS_WINDOW_FRAMES
        assert c.n_recent_kept == 0
        assert c.verdict == "poor"
        assert c.recent_buckets == {"cloudy": CONDITIONS_WINDOW_FRAMES}
        # The night as a whole is still overwhelmingly kept — the rolling read is
        # the *only* thing that catches this.
        assert live.n_kept == 100
    finally:
        proj.close()


def test_a_clean_night_grades_good_and_quotes_star_size(tmp_path):
    proj = Project.create(tmp_path / "p", name="t")
    try:
        _fill(proj, NOW - timedelta(minutes=40), 20, step_s=60, fwhm_px=3.0)
        c = live_session(proj, now=NOW).conditions
        assert c.verdict == "good"
        assert c.n_recent_kept == 20
        assert c.median_fwhm_px == 3.0
    finally:
        proj.close()


def test_a_patchy_stretch_grades_mixed(tmp_path):
    proj = Project.create(tmp_path / "p", name="t")
    try:
        # 13 of the last 20 kept → 65%: below "good", above "poor".
        _fill(proj, NOW - timedelta(minutes=40), 13, step_s=60)
        _fill(proj, NOW - timedelta(minutes=20), 7, step_s=60,
              accept=False, reject_reason="auto:streak")
        c = live_session(proj, now=NOW).conditions
        assert c.verdict == "mixed"
        assert (c.n_recent, c.n_recent_kept) == (20, 13)
        assert c.recent_buckets == {"trailed": 7}
    finally:
        proj.close()


def test_too_few_subs_to_grade_says_unknown_not_bad(tmp_path):
    """A night two subs old is not a bad night — it's an unmeasured one."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        _fill(proj, NOW - timedelta(minutes=3), CONDITIONS_MIN_FRAMES - 1, step_s=60,
              accept=False, reject_reason="auto:grade:fwhm")
        c = live_session(proj, now=NOW).conditions
        assert c.verdict == "unknown"
        assert c.n_recent == CONDITIONS_MIN_FRAMES - 1
    finally:
        proj.close()


def test_star_size_is_measured_over_kept_subs_only(tmp_path):
    """A rejected sub's bloated FWHM is precisely what was thrown away — letting
    it into the median would report conditions worse than the picture's."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        _fill(proj, NOW - timedelta(minutes=30), 10, step_s=60, fwhm_px=2.5)
        _fill(proj, NOW - timedelta(minutes=15), 5, step_s=60, fwhm_px=99.0,
              accept=False, reject_reason="auto:grade:fwhm")
        c = live_session(proj, now=NOW).conditions
        assert c.median_fwhm_px == 2.5
    finally:
        proj.close()


def test_unmeasured_subs_leave_star_size_unstated(tmp_path):
    """Frames still queued for QC carry no FWHM — say nothing, never zero."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        _fill(proj, NOW - timedelta(minutes=20), 10, step_s=60)
        c = live_session(proj, now=NOW).conditions
        assert c.median_fwhm_px is None
        assert c.verdict == "good"
    finally:
        proj.close()


def test_the_newest_thumbnail_is_a_kept_frame(tmp_path):
    """The page shows the freshest sub the app actually *kept* — showing one it
    just set aside would be the app illustrating its own rejects."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        _fill(proj, NOW - timedelta(minutes=30), 9, step_s=60)
        proj.add_frame(_frame(NOW - timedelta(minutes=20)))          # the keeper
        _fill(proj, NOW - timedelta(minutes=5), 3, step_s=60,
              accept=False, reject_reason="auto:streak")
        live = live_session(proj, now=NOW)
        keeper_ids = [f.id for f in last_session_frames(list(proj.iter_frames()))
                      if f.accept]
        assert live.newest_kept_frame_id == keeper_ids[-1]
    finally:
        proj.close()


def test_a_night_with_nothing_kept_has_no_thumbnail_to_show(tmp_path):
    proj = Project.create(tmp_path / "p", name="t")
    try:
        _fill(proj, NOW - timedelta(minutes=20), 8, step_s=60,
              accept=False, reject_reason="auto:grade:sky")
        live = live_session(proj, now=NOW)
        assert live.newest_kept_frame_id is None
        assert live.kept_exposure_s == 0.0
    finally:
        proj.close()


def test_the_session_cut_is_the_shared_one(tmp_path):
    """Single source of truth: the trailing cluster this reports must be exactly
    the one every other night-shaped screen sees, never a second definition."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        _fill(proj, NOW - timedelta(days=3), 12)
        _fill(proj, NOW - timedelta(days=1), 7)
        _fill(proj, NOW - timedelta(minutes=30), 5, step_s=60)
        live = live_session(proj, now=NOW)
        shared = last_session_frames(list(proj.iter_frames()))
        assert live.n_frames == len(shared) == 5
        assert live.start_utc == shared[0].timestamp_utc
        assert live.latest_utc == shared[-1].timestamp_utc
    finally:
        proj.close()


def test_a_naive_capture_stamp_is_read_as_utc(tmp_path):
    """The tz-naive fallback the FITS loader can persist must not crash the age
    arithmetic (or silently offset the night)."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        naive = NOW.replace(tzinfo=None) - timedelta(minutes=10)
        _fill(proj, naive, 6, step_s=60)
        live = live_session(proj, now=NOW)
        assert live.active is True
        assert 4.0 < live.minutes_since_latest < 6.0
    finally:
        proj.close()


# --- "capture seems to have gone quiet" -------------------------------------
#
# The walked-away failure: the Seestar stops mid-night and nothing says so. Every
# test here is about the *narrowing* — a night that simply ended must stay silent.


def test_a_session_that_stopped_mid_run_reads_quiet(tmp_path):
    """30 subs a minute apart, then nothing for 90 minutes: the stall case."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        _fill(proj, NOW - timedelta(minutes=119), 30, step_s=60)
        live = live_session(proj, now=NOW)
        assert live is not None
        assert live.active is False
        assert live.quiet is True
        # The cadence it is judged against travels with the verdict, so the UI
        # can say "a sub about every minute, then nothing".
        assert live.typical_gap_minutes == 1.0
        # 6 × 1 min is under the live-stale floor, so the floor is what applied.
        assert live.quiet_after_minutes == LIVE_STALE_MINUTES
    finally:
        proj.close()


def test_a_night_still_filling_up_is_never_quiet(tmp_path):
    """`quiet` is strictly narrower than `not active` — both can't be true."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        _fill(proj, NOW - timedelta(minutes=40), 30, step_s=60)
        live = live_session(proj, now=NOW)
        assert live.active is True
        assert live.quiet is False
    finally:
        proj.close()


def test_a_night_that_simply_finished_is_not_quiet(tmp_path):
    """Past the session gap this is *last night*, and the recap tells that story
    — a live "capture may have stopped" warning would be nonsense in daylight."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        _fill(proj, NOW - timedelta(hours=9), 30, step_s=60)
        live = live_session(proj, now=NOW)
        assert live.active is False
        assert live.quiet is False
    finally:
        proj.close()


def test_a_handful_of_subs_going_quiet_says_nothing(tmp_path):
    """Below the frame floor there was no run of arrivals to have stopped."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        _fill(proj, NOW - timedelta(minutes=120), QUIET_MIN_FRAMES - 1, step_s=600)
        live = live_session(proj, now=NOW)
        assert live.typical_gap_minutes is None
        assert live.quiet is False
    finally:
        proj.close()


def test_a_session_that_never_got_going_says_nothing(tmp_path):
    """Enough subs, but they span under QUIET_MIN_SESSION_MINUTES — a couple of
    test frames, not a night that was interrupted."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        _fill(proj, NOW - timedelta(minutes=60), 10, step_s=10)
        live = live_session(proj, now=NOW)
        assert live.typical_gap_minutes is not None
        assert live.quiet is False
    finally:
        proj.close()


def test_the_wait_scales_with_the_targets_own_cadence(tmp_path):
    """One sub every 20 minutes: 45 minutes of silence is an ordinary gap, so the
    note holds off until six cadences have passed."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        _fill(proj, NOW - timedelta(minutes=90 + 20 * 9), 10, step_s=20 * 60)
        live = live_session(proj, now=NOW)
        assert live.typical_gap_minutes == 20.0
        assert live.quiet_after_minutes == 120.0
        assert live.quiet is False          # 90 min quiet, wait is 120
        later = live_session(proj, now=NOW + timedelta(minutes=40))
        assert later.quiet is True          # 130 min quiet
    finally:
        proj.close()


def test_a_very_slow_cadence_still_gets_noticed_the_same_night(tmp_path):
    """The ceiling: six × an hour-long cadence would be six hours, by which time
    the session gap has already closed and nothing would ever be said."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        _fill(proj, NOW - timedelta(minutes=200 + 60 * 9), 10, step_s=3600)
        live = live_session(proj, now=NOW)
        assert live.typical_gap_minutes == 60.0
        assert live.quiet_after_minutes == QUIET_CEILING_MINUTES
        assert live.quiet is True
    finally:
        proj.close()


def test_one_long_pause_does_not_redefine_the_cadence(tmp_path):
    """A dither/refocus hole is why the cadence is a median, not a mean: with the
    mean (≈4.2 min) the wait would stretch past the floor and the stall below
    would go unmentioned."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        start = NOW - timedelta(minutes=180)
        _fill(proj, start, 10, step_s=60)
        # One 40-minute hole mid-session, then the cadence resumes.
        _fill(proj, start + timedelta(minutes=49), 10, step_s=60)
        live = live_session(proj, now=NOW)
        assert live.typical_gap_minutes == 1.0
        assert live.quiet_after_minutes == LIVE_STALE_MINUTES
        assert live.quiet is True
    finally:
        proj.close()


def test_the_quiet_read_survives_an_undatable_sub(tmp_path):
    """An undatable frame is dropped by the session cut, so the cadence is
    measured over what is left rather than crashing on a None stamp."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        _fill(proj, NOW - timedelta(minutes=119), 30, step_s=60)
        proj.add_frame(_frame(None))
        live = live_session(proj, now=NOW)
        assert live.quiet is True
    finally:
        proj.close()
