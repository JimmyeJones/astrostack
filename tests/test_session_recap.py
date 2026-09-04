"""Last-session recap — plain-language summary of the most recent capture night."""

from datetime import datetime, timedelta

from seestack.io.project import FrameRow, Project
from seestack.session_recap import (
    TRANSPARENCY_TREND_DROP_RATIO,
    bucket_reject_reason,
    focus_trend,
    last_session_frames,
    library_session_recap,
    recent_session_window_frames,
    session_recap,
    transparency_trend,
)


def _frame(ts: datetime | None, *, exposure=10.0, accept=True, reject_reason=None,
           fwhm_px=None, transparency_score=None, ra=None, dec=None):
    return FrameRow(
        source_path=f"/x/{ts}-{accept}-{reject_reason}-{fwhm_px}-{transparency_score}-{id(ts)}.fit",
        timestamp_utc=ts.isoformat() if ts else None,
        exposure_s=exposure,
        accept=accept,
        reject_reason=reject_reason,
        fwhm_px=fwhm_px,
        transparency_score=transparency_score,
        ra_center_deg=ra,
        dec_center_deg=dec,
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


def test_quality_drift_uses_the_typical_prior_session_as_baseline(tmp_path):
    """Baseline is the *typical* prior night — the median of the prior nights'
    medians — not the most recent one and not the sharpest one.

    It used to be the sharpest, and that is the bug fixed in v0.319.1: a minimum
    over N samples keeps falling as N grows, so the same ordinary night got
    flagged more and more often the longer the owner stayed on one target.
    """
    proj = Project.create(tmp_path / "p", name="t")
    try:
        _add_session(proj, datetime(2026, 7, 1, 22, 0, 0), n=8, fwhm=3.0)  # sharpest ever
        _add_session(proj, datetime(2026, 7, 5, 22, 0, 0), n=8, fwhm=4.5)  # a softer night
        _add_session(proj, datetime(2026, 7, 8, 22, 0, 0), n=8, fwhm=5.0)  # newest
        recap = session_recap(proj)
        assert recap is not None
        d = recap.quality_drift
        assert d is not None
        # Median of {3.0, 4.5} — neither the most recent prior (4.5) nor the
        # sharpest ever (3.0).
        assert d.baseline_fwhm_px == 3.75
        # …and it is built from every judgeable prior night, not one of them.
        assert d.n_baseline == 16
    finally:
        proj.close()


def test_a_lucky_night_does_not_make_every_later_night_look_soft(tmp_path):
    """The regression. One exceptional night used to become the yardstick for
    every night after it, so an ordinary night on unchanging seeing read as a
    focus problem — and the more nights the owner shot, the more likely that
    became (measured: 13.7 % of ordinary nights flagged after one prior night,
    68 % after twenty). The baseline is now the typical night, so one lucky one
    can't move it."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        # Nine ordinary nights at 3.6 px … and one exceptional 2.4 px night.
        _add_session(proj, datetime(2026, 7, 1, 22, 0, 0), n=8, fwhm=2.4)
        for day in range(2, 11):
            _add_session(proj, datetime(2026, 7, day, 22, 0, 0), n=8, fwhm=3.6)
        # The newest night is entirely ordinary: same seeing as the other eight.
        _add_session(proj, datetime(2026, 7, 12, 22, 0, 0), n=8, fwhm=3.6)
        recap = session_recap(proj)
        assert recap is not None
        # 3.6 vs the old min-baseline 2.4 is 1.5× and +1.2 px — it cleared both
        # floors comfortably and nagged about focus on a night nothing was wrong
        # with. Against the typical 3.6 px night it says nothing.
        assert recap.quality_drift is None
    finally:
        proj.close()


def test_a_genuinely_soft_night_is_still_caught_on_a_long_project(tmp_path):
    """The other half: the fix must not buy quiet by going deaf. Ten ordinary
    nights and one that really is soft — still flagged, and against the honest
    baseline."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        _add_session(proj, datetime(2026, 7, 1, 22, 0, 0), n=8, fwhm=2.4)
        for day in range(2, 11):
            _add_session(proj, datetime(2026, 7, day, 22, 0, 0), n=8, fwhm=3.6)
        _add_session(proj, datetime(2026, 7, 12, 22, 0, 0), n=8, fwhm=5.4)  # really soft
        recap = session_recap(proj)
        assert recap is not None
        d = recap.quality_drift
        assert d is not None
        assert d.latest_fwhm_px == 5.4
        assert d.baseline_fwhm_px == 3.6
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


def test_handles_mixed_tz_aware_and_naive_timestamps(tmp_path):
    """A project holding both a tz-aware (``…+00:00``/``…Z``) and a bare naive
    ``YYYY-MM-DDT…`` timestamp must not crash the session split. The
    ``fits_loader`` fallback can persist an unnormalised header value, so
    ``_parse`` coerces a naive time to UTC — otherwise sorting/subtracting the two
    kinds raises "can't compare offset-naive and offset-aware datetimes"."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        # Aware (as every normal writer stores) …
        proj.add_frame(FrameRow(source_path="/x/a.fit",
                                timestamp_utc="2026-07-08T22:00:00+00:00", exposure_s=10.0))
        # … alongside a bare naive one (the fallback path), same night.
        proj.add_frame(FrameRow(source_path="/x/b.fit",
                                timestamp_utc="2026-07-08T22:00:30", exposure_s=10.0))
        recap = session_recap(proj)  # fails-before: TypeError from the mixed compare
        assert recap is not None
        assert recap.n_frames == 2  # both land in one session, treated as UTC
        assert recap.n_kept == 2
    finally:
        proj.close()


# --- library_session_recap: the combined "Last night" Dashboard card ---------


def test_last_session_frames_trims_to_the_latest_night():
    """The helper drops undatable frames and returns only the trailing night."""
    n1 = datetime(2026, 7, 1, 22, 0, 0)
    n2 = datetime(2026, 7, 8, 22, 0, 0)
    frames = [_frame(None)]  # undatable — dropped
    frames += [_frame(n1 + timedelta(seconds=30 * i)) for i in range(3)]  # last week
    frames += [_frame(n2 + timedelta(seconds=30 * i)) for i in range(4)]  # this night
    last = last_session_frames(frames)
    assert len(last) == 4
    assert all(f.timestamp_utc.startswith("2026-07-08") for f in last)


def test_library_recap_none_when_nothing_datable():
    assert library_session_recap([("M31", "M31", [_frame(None)])]) is None
    assert library_session_recap([]) is None


def test_library_recap_combines_two_targets_shot_the_same_night():
    """Two targets shot back-to-back on one night merge into a single recap; a
    third target last shot a week earlier drops out of 'last night'."""
    night = datetime(2026, 7, 8, 21, 0, 0)
    m31 = [_frame(night + timedelta(seconds=30 * i)) for i in range(6)]
    m31 += [_frame(night + timedelta(minutes=4), accept=False, reject_reason="auto:grade:fwhm")]
    # Shot later the same night (well within the 6 h gap) — combines with M31.
    m42_start = night + timedelta(hours=2)
    m42 = [_frame(m42_start + timedelta(seconds=30 * i)) for i in range(4)]
    m42 += [_frame(m42_start + timedelta(minutes=3), accept=False, reject_reason="auto:streak")]
    # An old target whose only session was a week ago — must be excluded.
    old = [_frame(datetime(2026, 7, 1, 22, 0, 0) + timedelta(seconds=30 * i)) for i in range(5)]

    recap = library_session_recap([
        ("M 31", "M_31", m31),
        ("M 42", "M_42", m42),
        ("NGC 7000", "NGC_7000", old),
    ])
    assert recap is not None
    assert recap.n_targets == 2  # the old target dropped out
    assert recap.n_frames == 12  # 7 (M31) + 5 (M42)
    assert recap.n_kept == 10
    assert recap.n_set_aside == 2
    assert recap.reject_buckets == {"soft": 1, "trailed": 1}
    assert {c.safe for c in recap.targets} == {"M_31", "M_42"}
    # Biggest capture leads the card.
    assert recap.targets[0].safe == "M_31"
    assert recap.targets[0].n_frames == 7
    assert recap.targets[1].n_frames == 5
    # Night span runs from M31's first sub to M42's last.
    assert recap.start_utc == night.isoformat()
    assert recap.end_utc == (m42_start + timedelta(minutes=3)).isoformat()
    assert recap.session_exposure_s == 120.0  # 12 subs × 10 s
    assert recap.kept_exposure_s == 100.0     # 10 kept × 10 s


def test_library_recap_single_target_uses_its_latest_night_only():
    """One target, two nights: the recap covers only the most recent night."""
    n1 = datetime(2026, 7, 1, 22, 0, 0)
    n2 = datetime(2026, 7, 8, 22, 0, 0)
    frames = [_frame(n1 + timedelta(seconds=30 * i)) for i in range(3)]
    frames += [_frame(n2 + timedelta(seconds=30 * i)) for i in range(5)]
    recap = library_session_recap([("M 31", "M_31", frames)])
    assert recap is not None
    assert recap.n_targets == 1
    assert recap.n_frames == 5
    assert recap.targets[0].name == "M 31"


def test_library_recap_counts_a_target_revisited_later_the_same_night():
    """A target imaged at dusk and revisited near dawn — a >6 h *internal* gap —
    must keep BOTH batches when another target shot in between bridges the night.

    Regression: the recap used to trim each target to its own last session before
    merging, so the revisited target's dusk batch (severed from its dawn batch by
    its own >6 h gap) was silently dropped, undercounting the night's frames,
    integration and start time even though a bridging target made it one night."""
    dusk = datetime(2026, 7, 8, 22, 0, 0)          # target A at dusk
    bridge = datetime(2026, 7, 9, 2, 0, 0)         # target B in the middle (4 h later)
    dawn = datetime(2026, 7, 9, 5, 0, 0)           # target A again near dawn (7 h gap on A)
    a = [_frame(dusk + timedelta(seconds=30 * i)) for i in range(3)]
    a += [_frame(dawn + timedelta(seconds=30 * i)) for i in range(3)]
    b = [_frame(bridge + timedelta(seconds=30 * i)) for i in range(3)]

    recap = library_session_recap([("A", "A", a), ("B", "B", b)])
    assert recap is not None
    # All 9 frames belong to the one bridged night (each ≤6 h step); before the
    # fix A's 3 dusk subs were dropped, giving n_frames == 6.
    assert recap.n_frames == 9
    assert recap.n_targets == 2
    a_contrib = next(c for c in recap.targets if c.safe == "A")
    assert a_contrib.n_frames == 6            # dusk (3) + dawn (3), not just dawn
    assert recap.start_utc == dusk.isoformat()  # the night starts at A's dusk sub


def test_library_recap_keeps_an_unbridged_split_night_whole():
    """The same shape as the bridged test above with the bridge taken away — one
    target, one observing night, shot in two goes with bed in between.

    The 6 h gap walk cannot see that as one night: it holds the pre-dawn half
    alone, and the card headed "Last night" reports half the subs and half the
    integration. Handing it the observer's night key widens the cluster back
    over the night it belongs to.
    """
    evening = datetime(2026, 7, 1, 21, 0, 0)      # 21:00 → 23:00
    predawn = datetime(2026, 7, 2, 5, 30, 0)      # 05:30 → 07:30, a 6.5 h gap
    frames = [_frame(evening + timedelta(minutes=10 * i)) for i in range(13)]
    frames += [_frame(predawn + timedelta(minutes=10 * i)) for i in range(13)]

    bare = library_session_recap([("M 42", "M_42", frames)])
    assert bare is not None
    assert bare.n_frames == 13                    # the pre-dawn half only
    assert bare.session_exposure_s == 130.0

    whole = library_session_recap([("M 42", "M_42", frames)],
                                  night_of=_noon_night_key)
    assert whole is not None
    assert whole.n_frames == 26                   # the night the owner shot
    assert whole.session_exposure_s == 260.0
    assert whole.start_utc == evening.isoformat()
    assert whole.targets[0].n_frames == 26


def test_library_recap_night_key_never_reaches_into_an_earlier_night():
    """The widening is bounded by the night key, so the properties the gap walk
    provided still hold: a target last shot a week ago stays out, and a target's
    own earlier night is not swept in."""
    old = datetime(2026, 7, 1, 22, 0, 0)
    evening = datetime(2026, 7, 8, 21, 0, 0)
    predawn = datetime(2026, 7, 9, 5, 30, 0)
    m42 = [_frame(old + timedelta(minutes=10 * i)) for i in range(5)]
    m42 += [_frame(evening + timedelta(minutes=10 * i)) for i in range(13)]
    m42 += [_frame(predawn + timedelta(minutes=10 * i)) for i in range(13)]
    ngc = [_frame(old + timedelta(minutes=10 * i)) for i in range(4)]

    recap = library_session_recap(
        [("M 42", "M_42", m42), ("NGC 7000", "NGC_7000", ngc)],
        night_of=_noon_night_key)
    assert recap is not None
    assert recap.n_targets == 1                   # the week-old target drops out
    assert {c.safe for c in recap.targets} == {"M_42"}
    assert recap.n_frames == 26                   # both halves of the 8th, none of the 1st
    assert recap.start_utc == evening.isoformat()


def test_library_recap_night_key_is_inert_without_a_split():
    """An observer who never splits a night gets the gap walk's own answer, so
    turning the key on cannot change what a normal library's card says."""
    night = datetime(2026, 7, 8, 21, 0, 0)
    a = [_frame(night + timedelta(minutes=10 * i)) for i in range(6)]
    b = [_frame(night + timedelta(hours=2, minutes=10 * i)) for i in range(4)]
    pair = [("A", "A", a), ("B", "B", b)]
    bare = library_session_recap(pair)
    keyed = library_session_recap(pair, night_of=_noon_night_key)
    assert bare == keyed


def test_library_recap_unplaceable_stamps_never_widen_the_night():
    """A night key that cannot place a stamp returns ``None``, and ``None`` is
    never treated as a match — the walk stops there rather than guessing."""
    evening = datetime(2026, 7, 1, 21, 0, 0)
    predawn = datetime(2026, 7, 2, 5, 30, 0)
    frames = [_frame(evening + timedelta(minutes=10 * i)) for i in range(13)]
    frames += [_frame(predawn + timedelta(minutes=10 * i)) for i in range(13)]
    recap = library_session_recap([("M 42", "M_42", frames)],
                                  night_of=lambda _stamp: None)
    assert recap is not None
    assert recap.n_frames == 13                   # unchanged from the bare walk


def test_recent_session_window_keeps_a_bridged_early_batch():
    """The memory-bound window keeps a >6 h-earlier batch of the same night (so it
    can be bridged), while dropping a genuinely prior night far outside the window."""
    prev_night = datetime(2026, 7, 1, 22, 0, 0)    # a week ago — dropped
    dusk = datetime(2026, 7, 8, 22, 0, 0)          # same night as dawn, 7 h earlier
    dawn = datetime(2026, 7, 9, 5, 0, 0)
    frames = [_frame(prev_night + timedelta(seconds=30 * i)) for i in range(4)]
    frames += [_frame(dusk + timedelta(seconds=30 * i)) for i in range(3)]
    frames += [_frame(dawn + timedelta(seconds=30 * i)) for i in range(3)]
    kept = recent_session_window_frames(frames)
    # Both same-night batches survive (dusk is only 7 h < 30 h before dawn); last
    # week's session — far outside the window — is dropped. Unlike
    # last_session_frames, the dusk batch is NOT severed at the target's own gap.
    assert len(kept) == 6
    assert all(not f.timestamp_utc.startswith("2026-07-01") for f in kept)
    # For contrast, the per-target last-session trim would drop the dusk batch too.
    assert len(last_session_frames(frames)) == 3


def test_recent_session_window_empty_without_timestamps():
    assert recent_session_window_frames([]) == []
    assert recent_session_window_frames([_frame(None)]) == []


# --- Per-target "Nights" breakdown -----------------------------------------

from seestack.session_recap import (  # noqa: E402
    FWHM_DRIFT_ABS_PX,
    FWHM_DRIFT_RATIO,
    NIGHT_HAZY_CLOUD_FRACTION,
    _night_verdict,
    night_frame_ids,
    nights_breakdown,
)


def test_nights_breakdown_empty_when_nothing_datable(tmp_path):
    proj = Project.create(tmp_path / "p", name="t")
    try:
        proj.add_frame(_frame(None))
        assert nights_breakdown(proj) == []
    finally:
        proj.close()


def test_nights_breakdown_lists_every_night_newest_first(tmp_path):
    """Three nights → three summaries, newest first, with per-night rollups."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        for wk, (n_keep, fwhm) in enumerate([(5, 3.0), (5, 3.1), (6, 3.0)]):
            base = datetime(2026, 7, 1 + 7 * wk, 22, 0, 0)
            for i in range(n_keep):
                proj.add_frame(_frame(base + timedelta(seconds=30 * i), fwhm_px=fwhm))
        nights = nights_breakdown(proj)
        assert len(nights) == 3
        # Newest first: the last-added night (2026-07-15) leads.
        assert nights[0].start_utc.startswith("2026-07-15")
        assert nights[2].start_utc.startswith("2026-07-01")
        assert [n.n_frames for n in nights] == [6, 5, 5]
        assert all(n.n_set_aside == 0 for n in nights)
        assert nights[0].kept_exposure_s == 60.0  # 6 subs × 10 s
    finally:
        proj.close()


def test_nights_breakdown_flags_a_soft_night_against_the_best(tmp_path):
    """A night materially softer than the target's sharpest night → 'soft', and
    the sharpest night is nodded 'best' (with ≥2 judgeable nights)."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        sharp = datetime(2026, 7, 1, 22, 0, 0)
        for i in range(5):  # sharpest night: FWHM 3.0
            proj.add_frame(_frame(sharp + timedelta(seconds=30 * i), fwhm_px=3.0))
        soft = datetime(2026, 7, 8, 22, 0, 0)
        for i in range(5):  # 4.0 ≥ 3.0×1.25 and ≥ 3.0+0.6 → soft
            proj.add_frame(_frame(soft + timedelta(seconds=30 * i), fwhm_px=4.0))
        nights = nights_breakdown(proj)
        newest, oldest = nights[0], nights[1]
        assert newest.start_utc.startswith("2026-07-08")
        assert newest.verdict == "soft"
        assert newest.is_best is False
        assert oldest.verdict == "sharp"
        assert oldest.is_best is True
        assert oldest.median_fwhm_px == 3.0
    finally:
        proj.close()


def test_nights_breakdown_reports_the_baseline_each_verdict_was_judged_against(tmp_path):
    """A night's verdict is a *comparison*, and the badge that shows it sits next
    to a button offering to discard the night — so the number it was compared
    against comes back on the row, and it is the same leave-one-out median the
    verdict itself used (never the night's own median)."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        for n, fwhm in enumerate((3.0, 3.4, 5.0)):
            base = datetime(2026, 7, 1 + 7 * n, 22, 0, 0)
            for i in range(5):
                proj.add_frame(_frame(base + timedelta(seconds=30 * i), fwhm_px=fwhm))
        nights = nights_breakdown(proj)  # newest first: 5.0, 3.4, 3.0
        assert [n.median_fwhm_px for n in nights] == [5.0, 3.4, 3.0]
        # Each night sees the median of the OTHER two, never its own number.
        assert [n.typical_fwhm_px for n in nights] == [3.2, 4.0, 4.2]
        assert nights[0].verdict == "soft"
        # 5.0 vs a baseline of 3.2 is exactly what the badge must be able to say.
        assert nights[0].median_fwhm_px > nights[0].typical_fwhm_px
    finally:
        proj.close()


def test_nights_breakdown_has_no_baseline_for_a_lone_night(tmp_path):
    """One judgeable night has nothing to be compared against, so there is no
    baseline to report — and the UI must stay silent rather than invent one."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        base = datetime(2026, 7, 8, 22, 0, 0)
        for i in range(5):
            proj.add_frame(_frame(base + timedelta(seconds=30 * i), fwhm_px=3.0))
        nights = nights_breakdown(proj)
        assert len(nights) == 1
        assert nights[0].typical_fwhm_px is None
    finally:
        proj.close()


def test_nights_breakdown_flags_a_cloudy_night_hazy(tmp_path):
    """A night that lost ≥40% of its subs to cloud → 'hazy', which takes
    precedence over a sharpness judgement even if the survivors are sharp."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        base = datetime(2026, 7, 8, 22, 0, 0)
        for i in range(5):  # 5 kept, sharp survivors
            proj.add_frame(_frame(base + timedelta(seconds=30 * i), fwhm_px=3.0))
        for i in range(5):  # 5 set aside as cloudy → 50% ≥ 40%
            proj.add_frame(_frame(base + timedelta(minutes=5, seconds=i),
                                  accept=False, reject_reason="auto:grade:transparency"))
        nights = nights_breakdown(proj)
        assert len(nights) == 1
        assert nights[0].reject_buckets == {"cloudy": 5}
        assert nights[0].verdict == "hazy"
        # A lone night has no baseline to be "best" against.
        assert nights[0].is_best is False
    finally:
        proj.close()


def test_nights_breakdown_no_verdict_when_too_few_measured(tmp_path):
    """A night with fewer than the min measured accepted subs and no cloud
    problem gets no verdict (we don't judge sharpness on thin data)."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        base = datetime(2026, 7, 8, 22, 0, 0)
        for i in range(3):  # only 3 measured accepted subs (< the min of 4)
            proj.add_frame(_frame(base + timedelta(seconds=30 * i), fwhm_px=3.0))
        nights = nights_breakdown(proj)
        assert len(nights) == 1
        assert nights[0].median_fwhm_px is None
        assert nights[0].verdict == ""
    finally:
        proj.close()


def test_night_frame_ids_selects_exactly_one_nights_frames(tmp_path):
    """The bounds a NightSummary carries select exactly that night's frames — the
    other night's are never swept in, since sessions never overlap in time."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        night_a = datetime(2026, 7, 1, 22, 0, 0)
        for i in range(3):
            proj.add_frame(_frame(night_a + timedelta(seconds=30 * i)))
        night_b = datetime(2026, 7, 8, 22, 0, 0)
        for i in range(4):
            proj.add_frame(_frame(night_b + timedelta(seconds=30 * i)))
        nights = nights_breakdown(proj)  # newest first → [B, A]
        b, a = nights
        all_ids = [f.id for f in proj.iter_frames()]
        b_ids = night_frame_ids(proj, b.start_utc, b.end_utc)
        a_ids = night_frame_ids(proj, a.start_utc, a.end_utc)
        assert len(b_ids) == 4 and len(a_ids) == 3
        assert set(b_ids).isdisjoint(a_ids)
        assert set(b_ids) | set(a_ids) == set(all_ids)  # partition, nothing lost
    finally:
        proj.close()


def test_night_frame_ids_accepted_only_skips_already_rejected(tmp_path):
    """accepted_only restricts to the subs the stack actually uses — an already
    set-aside sub is left out (so the set-aside action never re-touches it)."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        base = datetime(2026, 7, 8, 22, 0, 0)
        for i in range(3):
            proj.add_frame(_frame(base + timedelta(seconds=30 * i)))
        proj.add_frame(_frame(base + timedelta(seconds=120),
                              accept=False, reject_reason="auto:streak"))
        [night] = nights_breakdown(proj)
        assert len(night_frame_ids(proj, night.start_utc, night.end_utc)) == 4
        accepted = night_frame_ids(proj, night.start_utc, night.end_utc,
                                   accepted_only=True)
        assert len(accepted) == 3  # the rejected sub is excluded
    finally:
        proj.close()


def test_night_frame_ids_empty_on_unparseable_bounds(tmp_path):
    proj = Project.create(tmp_path / "p", name="t")
    try:
        proj.add_frame(_frame(datetime(2026, 7, 8, 22, 0, 0)))
        assert night_frame_ids(proj, "not-a-date", "also-bad") == []
        assert night_frame_ids(proj, None, None) == []  # type: ignore[arg-type]
    finally:
        proj.close()


def test_one_lucky_night_does_not_badge_the_rest_of_a_long_project_soft(tmp_path):
    """The Nights-card half of the same regression, and the one that mattered
    more: the "soft" badge sits directly beside a one-click **Set aside**, so a
    baseline that drifts down as the project grows steers a beginner toward
    discarding good nights. Measured on unchanging seeing, the share of a
    target's own nights badged soft ran 13.7 % at two nights → 78.6 % at forty.
    """
    proj = Project.create(tmp_path / "p", name="t")
    try:
        # One exceptional night, then nine entirely ordinary ones.
        base = datetime(2026, 7, 1, 22, 0, 0)
        for i in range(5):
            proj.add_frame(_frame(base + timedelta(seconds=30 * i), fwhm_px=2.4))
        for day in range(2, 11):
            night = datetime(2026, 7, day, 22, 0, 0)
            for i in range(5):
                proj.add_frame(_frame(night + timedelta(seconds=30 * i), fwhm_px=3.6))
        nights = nights_breakdown(proj)
        assert len(nights) == 10
        # 3.6 against the old min-baseline of 2.4 is 1.5× and +1.2 px — every one
        # of the nine ordinary nights used to be badged "soft" beside a Set-aside
        # button. Not one of them is now.
        assert [n.verdict for n in nights] == ["sharp"] * 10
        # The lucky night still earns its positive nod — that one *is* a minimum.
        assert sum(n.is_best for n in nights) == 1
        assert nights[-1].median_fwhm_px == 2.4 and nights[-1].is_best
    finally:
        proj.close()


def test_a_genuinely_soft_night_is_still_badged_on_a_long_project(tmp_path):
    """…and the fix didn't buy that quiet by going blind: among nine ordinary
    nights, one that really is soft is still badged, judged against the typical
    night rather than the luckiest one."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        for day in range(1, 10):
            night = datetime(2026, 7, day, 22, 0, 0)
            for i in range(5):
                proj.add_frame(_frame(night + timedelta(seconds=30 * i), fwhm_px=3.2))
        bad = datetime(2026, 7, 11, 22, 0, 0)
        for i in range(5):
            proj.add_frame(_frame(bad + timedelta(seconds=30 * i), fwhm_px=4.6))
        nights = nights_breakdown(proj)
        assert nights[0].start_utc.startswith("2026-07-11")
        assert nights[0].verdict == "soft"
        assert [n.verdict for n in nights[1:]] == ["sharp"] * 9
    finally:
        proj.close()


def test_a_nights_baseline_never_includes_the_night_being_judged(tmp_path):
    """Leave-one-out, by position rather than by value: two nights that measured
    *identically* must each still see the other, or a target whose nights all
    read the same would have an empty baseline."""
    from seestack.session_recap import _typical_other_fwhm

    assert _typical_other_fwhm([3.4], 0) is None          # nothing to compare to
    assert _typical_other_fwhm([3.4, 3.4], 0) == 3.4      # its identical twin, not itself
    assert _typical_other_fwhm([2.4, 3.6, 3.6, 3.6], 0) == 3.6
    # Dropping the outlier leaves the other three unmoved …
    assert _typical_other_fwhm([2.4, 3.6, 3.6, 3.6], 1) == 3.6
    # … and the statistic is a median, so one extreme value can't drag it.
    assert _typical_other_fwhm([0.5, 3.5, 3.6, 3.7, 3.8], 4) == 3.55


def test_night_verdict_pure_helper():
    # Hazy overrides everything once the cloud fraction clears the floor.
    assert _night_verdict(3.0, 3.0, NIGHT_HAZY_CLOUD_FRACTION) == "hazy"
    assert _night_verdict(None, None, 1.0) == "hazy"
    # No median and no cloud problem → no verdict.
    assert _night_verdict(None, 3.0, 0.0) == ""
    # Soft only when BOTH the relative and absolute floors are cleared.
    best = 3.0
    soft = best * FWHM_DRIFT_RATIO + 0.01
    assert soft - best >= FWHM_DRIFT_ABS_PX
    assert _night_verdict(soft, best, 0.0) == "soft"
    # Just under either floor stays sharp.
    assert _night_verdict(best + FWHM_DRIFT_ABS_PX * 0.5, best, 0.0) == "sharp"
    # The best night itself is sharp, never soft.
    assert _night_verdict(best, best, 0.0) == "sharp"


# --- Focus & sharpness through the night (focus_trend) ----------------------

def _focus_proj(proj, fwhms, *, base=None, step_min=3, accept=None):
    """Add a run of subs `step_min` minutes apart in one session, with the given
    per-frame FWHMs (None = unmeasured). `accept` optionally overrides accept per
    frame (default: all accepted)."""
    base = base or datetime(2026, 7, 10, 22, 0, 0)
    for i, fw in enumerate(fwhms):
        acc = True if accept is None else accept[i]
        proj.add_frame(_frame(base + timedelta(minutes=step_min * i),
                              fwhm_px=fw, accept=acc))


def test_focus_trend_steady_night(tmp_path):
    proj = Project.create(tmp_path / "t", "M31")
    try:
        _focus_proj(proj, [2.8, 3.0, 2.7, 2.9, 2.8, 3.1, 2.7, 2.9])
        tr = focus_trend(proj)
        assert tr is not None
        assert tr.verdict == "steady"
        assert tr.n_points == 8 and len(tr.points) == 8
        assert tr.soft_after_utc is None
        assert 2.7 <= tr.median_fwhm_px <= 3.1
        # Points are in capture order, oldest first.
        assert tr.points[0].t_utc == tr.start_utc
        assert tr.points[-1].t_utc == tr.end_utc
    finally:
        proj.close()


def test_focus_trend_flags_a_softening_night(tmp_path):
    proj = Project.create(tmp_path / "t", "M31")
    try:
        # Sharp early, clearly soft late (dew/focus drift): last third ≫ first.
        _focus_proj(proj, [2.6, 2.7, 2.5, 2.8, 3.6, 4.2, 4.5, 4.8, 5.0])
        tr = focus_trend(proj)
        assert tr is not None
        assert tr.verdict == "softened"
        assert tr.late_fwhm_px > tr.early_fwhm_px
        # It names when the soft stretch began (start of the last third).
        assert tr.soft_after_utc is not None
        assert tr.start_utc < tr.soft_after_utc <= tr.end_utc
    finally:
        proj.close()


def test_focus_trend_flags_an_improving_night(tmp_path):
    proj = Project.create(tmp_path / "t", "M31")
    try:
        # Soft early (focus settling in), sharp late — the symmetric case.
        _focus_proj(proj, [5.0, 4.8, 4.5, 4.2, 3.6, 2.8, 2.5, 2.7, 2.6])
        tr = focus_trend(proj)
        assert tr is not None
        assert tr.verdict == "improved"
        assert tr.early_fwhm_px > tr.late_fwhm_px
        assert tr.soft_after_utc is None
    finally:
        proj.close()


def test_focus_trend_needs_enough_measured_subs(tmp_path):
    proj = Project.create(tmp_path / "t", "M31")
    try:
        _focus_proj(proj, [2.8, 3.0, 2.7, 2.9, 2.8])  # only 5 < FOCUS_TREND_MIN_FRAMES
        assert focus_trend(proj) is None
    finally:
        proj.close()


def test_focus_trend_ignores_rejected_and_unmeasured_subs(tmp_path):
    proj = Project.create(tmp_path / "t", "M31")
    try:
        # 8 accepted+measured (enough) plus rejected/unmeasured noise that must
        # not enter the trend.
        fwhms = [2.8, 3.0, 2.7, 2.9, None, 9.9, 2.8, 3.1, 2.7, 2.9]
        accept = [True, True, True, True, True, False, True, True, True, True]
        _focus_proj(proj, fwhms, accept=accept)
        tr = focus_trend(proj)
        assert tr is not None
        assert tr.n_points == 8  # the None + the rejected 9.9 are excluded
        assert all(p.fwhm_px < 4.0 for p in tr.points)
    finally:
        proj.close()


def test_focus_trend_uses_only_the_latest_session(tmp_path):
    proj = Project.create(tmp_path / "t", "M31")
    try:
        # An old soft night, then a >6h gap, then a sharp latest night.
        old = datetime(2026, 7, 8, 22, 0, 0)
        _focus_proj(proj, [5.0] * 8, base=old)
        latest = datetime(2026, 7, 10, 22, 0, 0)
        _focus_proj(proj, [2.7, 2.8, 2.9, 2.7, 2.8, 2.9, 2.7, 2.8], base=latest)
        tr = focus_trend(proj)
        assert tr is not None
        assert tr.verdict == "steady"
        assert tr.median_fwhm_px < 3.0  # measured from the latest (sharp) night only
    finally:
        proj.close()


def test_focus_trend_none_without_timestamps(tmp_path):
    proj = Project.create(tmp_path / "t", "M31")
    try:
        for i in range(8):
            proj.add_frame(_frame(None, fwhm_px=2.8 + i * 0.01))
        assert focus_trend(proj) is None
    finally:
        proj.close()


# --- Clouds & haze through the night (transparency_trend) -------------------

def _transp_proj(proj, scores, *, base=None, step_min=3, accept=None):
    """Add a run of subs `step_min` minutes apart in one session, with the given
    per-frame transparency scores (None = unmeasured). `accept` optionally
    overrides accept per frame (default: all accepted)."""
    base = base or datetime(2026, 7, 10, 22, 0, 0)
    for i, sc in enumerate(scores):
        acc = True if accept is None else accept[i]
        proj.add_frame(_frame(base + timedelta(minutes=step_min * i),
                              transparency_score=sc, accept=acc))


def test_transparency_trend_clear_night(tmp_path):
    proj = Project.create(tmp_path / "t", "M31")
    try:
        _transp_proj(proj, [1000, 1030, 980, 1010, 995, 1020, 990, 1005])
        tr = transparency_trend(proj)
        assert tr is not None
        assert tr.verdict == "clear"
        assert tr.n_points == 8 and len(tr.points) == 8
        assert tr.degraded_after_utc is None
        assert 980 <= tr.median_transparency <= 1030
        # Points are in capture order, oldest first.
        assert tr.points[0].t_utc == tr.start_utc
        assert tr.points[-1].t_utc == tr.end_utc
    finally:
        proj.close()


def test_transparency_trend_flags_clouds_rolling_in(tmp_path):
    proj = Project.create(tmp_path / "t", "M31")
    try:
        # Clear early, clearly murky late (clouds/haze): last third ≪ first.
        _transp_proj(proj, [1000, 1020, 980, 990, 700, 520, 480, 450, 420])
        tr = transparency_trend(proj)
        assert tr is not None
        assert tr.verdict == "degraded"
        assert tr.late_transparency < tr.early_transparency
        # It names when the murky stretch began (start of the last third).
        assert tr.degraded_after_utc is not None
        assert tr.start_utc < tr.degraded_after_utc <= tr.end_utc
    finally:
        proj.close()


def test_transparency_trend_flags_a_clearing_night(tmp_path):
    proj = Project.create(tmp_path / "t", "M31")
    try:
        # Hazy early (thin cloud clearing), clear late — the symmetric case.
        _transp_proj(proj, [420, 450, 480, 520, 700, 990, 980, 1020, 1000])
        tr = transparency_trend(proj)
        assert tr is not None
        assert tr.verdict == "cleared"
        assert tr.late_transparency > tr.early_transparency
        assert tr.degraded_after_utc is None
    finally:
        proj.close()


def test_transparency_trend_needs_enough_measured_subs(tmp_path):
    proj = Project.create(tmp_path / "t", "M31")
    try:
        _transp_proj(proj, [1000, 1010, 990, 1020, 995])  # only 5 < MIN_FRAMES
        assert transparency_trend(proj) is None
    finally:
        proj.close()


def test_transparency_trend_ignores_rejected_and_unmeasured_subs(tmp_path):
    proj = Project.create(tmp_path / "t", "M31")
    try:
        # 8 accepted+measured (enough) plus rejected/unmeasured noise that must
        # not enter the trend.
        scores = [1000, 1030, 980, 1010, None, 50, 995, 1020, 990, 1005]
        accept = [True, True, True, True, True, False, True, True, True, True]
        _transp_proj(proj, scores, accept=accept)
        tr = transparency_trend(proj)
        assert tr is not None
        assert tr.n_points == 8  # the None + the rejected 50 are excluded
        assert all(p.transparency > 900 for p in tr.points)
    finally:
        proj.close()


def test_transparency_trend_uses_only_the_latest_session(tmp_path):
    proj = Project.create(tmp_path / "t", "M31")
    try:
        # An old hazy night, then a >6h gap, then a clear latest night.
        old = datetime(2026, 7, 8, 22, 0, 0)
        _transp_proj(proj, [400] * 8, base=old)
        latest = datetime(2026, 7, 10, 22, 0, 0)
        _transp_proj(proj, [1000, 1010, 990, 1005, 1020, 995, 1000, 1015], base=latest)
        tr = transparency_trend(proj)
        assert tr is not None
        assert tr.verdict == "clear"
        assert tr.median_transparency > 900  # measured from the latest (clear) night only
    finally:
        proj.close()


def test_transparency_trend_none_without_timestamps(tmp_path):
    proj = Project.create(tmp_path / "t", "M31")
    try:
        for i in range(8):
            proj.add_frame(_frame(None, transparency_score=1000 + i))
        assert transparency_trend(proj) is None
    finally:
        proj.close()


# --- Recent capture pace ("how much is a clear night worth to me?") ---------

from statistics import median  # noqa: E402

from seestack.session_recap import (  # noqa: E402
    MIN_PRODUCTIVE_NIGHT_S,
    PACE_LOOKBACK_NIGHTS,
    recent_night_pace_s,
)


def _night(proj, day: int, *, n: int, exposure: float = 10.0, accept: bool = True,
           month: int = 7, year: int = 2026) -> None:
    """Add one capture night of ``n`` subs, 30 s apart from 22:00 UTC."""
    base = datetime(year, month, day, 22, 0, 0)
    for i in range(n):
        proj.add_frame(_frame(base + timedelta(seconds=30 * i),
                              exposure=exposure, accept=accept))


def test_pace_is_the_median_kept_integration_per_recent_night(tmp_path):
    """Three nights of 300 s / 600 s / 900 s kept → a 600 s median pace."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        _night(proj, 1, n=30)   # 300 s
        _night(proj, 8, n=60)   # 600 s
        _night(proj, 15, n=90)  # 900 s
        assert recent_night_pace_s(proj) == 600.0
    finally:
        proj.close()


def test_pace_counts_only_the_kept_subs(tmp_path):
    """Set-aside subs are time spent, not integration gained — the pace is what a
    clear night is really *worth*, so it must follow the kept exposure only."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        for day in (1, 8):
            _night(proj, day, n=40)                 # 400 s kept
            _night(proj, day, n=40, accept=False)   # + 400 s set aside, same night
        assert recent_night_pace_s(proj) == 400.0
    finally:
        proj.close()


def test_pace_uses_only_the_most_recent_nights(tmp_path):
    """A change of habit shows up: old marathon nights outside the lookback
    window can't drag a recent, shorter cadence upward."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        for wk in range(4):  # four old nights of 1200 s
            _night(proj, 1 + 7 * wk, n=120, month=5)
        for wk in range(PACE_LOOKBACK_NIGHTS):  # then five recent 300 s nights
            _night(proj, 1 + 7 * wk, n=30, month=7)
        assert recent_night_pace_s(proj) == 300.0
    finally:
        proj.close()


def test_pace_ignores_a_test_frame_night(tmp_path):
    """A night that kept less than the productive floor is a test frame or two,
    not a session — counting it would halve the median and inflate every ETA."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        _night(proj, 1, n=60)   # 600 s
        _night(proj, 8, n=60)   # 600 s
        _night(proj, 15, n=1)   # 10 s — under MIN_PRODUCTIVE_NIGHT_S
        assert MIN_PRODUCTIVE_NIGHT_S == 120.0
        assert recent_night_pace_s(proj) == 600.0
    finally:
        proj.close()


def test_pace_is_none_from_a_single_night(tmp_path):
    """One session is not a pace — say nothing rather than project a whole goal
    off it."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        _night(proj, 1, n=60)
        assert recent_night_pace_s(proj) is None
    finally:
        proj.close()


def test_pace_is_none_when_recent_nights_kept_almost_nothing(tmp_path):
    """Recent nights that recorded subs but kept next to none give no pace to
    divide by (the Target page says so in words; the library card stays quiet)."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        for day in (1, 8, 15):
            _night(proj, day, n=40, accept=False)
        assert recent_night_pace_s(proj) is None
    finally:
        proj.close()


def test_pace_is_none_without_dated_frames(tmp_path):
    proj = Project.create(tmp_path / "p", name="t")
    try:
        for i in range(20):
            f = _frame(None)
            f.source_path = f"/x/undated-{i}.fit"
            proj.add_frame(f)
        assert recent_night_pace_s(proj) is None
    finally:
        proj.close()


def test_pace_splits_nights_the_same_way_the_nights_card_does(tmp_path):
    """The number must agree with the "Nights" breakdown the user can read: same
    6 h-gap sessions, so a session spanning UTC midnight stays one night."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        # 21:00 → 01:00 across midnight, twice, a week apart.
        for day in (1, 8):
            base = datetime(2026, 7, day, 21, 0, 0)
            for i in range(40):
                proj.add_frame(_frame(base + timedelta(minutes=6 * i)))
        nights = nights_breakdown(proj)
        assert len(nights) == 2  # not four UTC-date buckets
        assert recent_night_pace_s(proj) == median(
            [n.kept_exposure_s for n in nights]
        )
    finally:
        proj.close()


def test_iter_frame_capture_rows_skips_undated_and_defaults_a_null_exposure(tmp_path):
    """The lean three-column read behind the pace: dated rows only, a NULL
    exposure reading as 0.0 exactly as the night rollups treat it."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        proj.add_frame(_frame(datetime(2026, 7, 1, 22, 0, 0), exposure=10.0))
        proj.add_frame(_frame(datetime(2026, 7, 1, 22, 1, 0), accept=False))
        proj.add_frame(_frame(None))
        fid = proj.add_frame(_frame(datetime(2026, 7, 1, 22, 2, 0)))
        proj.update_frame(fid, exposure_s=None)
        rows = sorted(proj.iter_frame_capture_rows())
        assert len(rows) == 3
        assert [r[1] for r in rows] == [10.0, 10.0, 0.0]
        assert [r[2] for r in rows] == [True, False, True]
    finally:
        proj.close()


# --- ...and the same card on a MOSAIC, where the panels are different sky ----

def _mosaic_night(proj, panels, *, base=None, step_min=3):
    """One session that works through `panels` in sequence.

    Each entry is ``(ra_deg, [scores…])`` — a panel's pointing and the
    transparency scores of the subs shot there, in capture order. Panels are
    ~1° apart (a real Seestar mosaic step), which is well clear of the 0.25°
    dither floor `pointing_groups` separates on.
    """
    base = base or datetime(2026, 7, 10, 22, 0, 0)
    i = 0
    for ra, scores in panels:
        for sc in scores:
            proj.add_frame(_frame(base + timedelta(minutes=step_min * i),
                                  transparency_score=sc, ra=ra, dec=41.0))
            i += 1


def test_a_mosaics_emptier_panel_is_not_called_clouds(tmp_path):
    """The fourth site of the position-dependent-metric bug class (after QC
    grading v0.270.2, photometric normalization v0.271.0 and quality weighting
    v0.272.1): `transparency_score` is the median flux of a frame's *brightest
    stars*, so a mosaic panel aimed at an emptier patch of sky records lower
    scores for reasons that have nothing to do with the weather.

    A Seestar working through its panels in sequence therefore ends the night on
    a different patch of sky from the one it started on, and the raw first-third
    vs last-third comparison reads the move as "clouds rolled in after 22:24" —
    on a night that was, by construction here, perfectly steady within every
    panel.
    """
    proj = Project.create(tmp_path / "t", "M31 mosaic")
    try:
        # Two panels, steady within themselves; the second is simply a 2.2×
        # emptier star field. Nothing about the sky changed.
        _mosaic_night(proj, [
            (10.0, [1000, 1020, 980, 1010, 990]),
            (11.0, [455, 445, 460, 450, 440]),
        ])
        tr = transparency_trend(proj)
        assert tr is not None
        # Levelled panel by panel, the night reads as what it is.
        assert tr.verdict == "clear"
        assert tr.degraded_after_utc is None
        assert tr.n_pointings == 2
        # ...and the sparkline the reader sees agrees with that verdict, rather
        # than showing a cliff the caption denies.
        assert max(tr.early_transparency, tr.late_transparency) < (
            min(tr.early_transparency, tr.late_transparency)
            * TRANSPARENCY_TREND_DROP_RATIO)
    finally:
        proj.close()


def test_a_mosaic_night_that_really_did_cloud_over_is_still_caught(tmp_path):
    """The other half: levelling the panels must not blind the card to weather.
    Same two panels, but the sky genuinely collapses across the second half of
    *each* panel — which is a real transparency drop, and still reads as one."""
    proj = Project.create(tmp_path / "t", "M31 mosaic")
    try:
        _mosaic_night(proj, [
            (10.0, [1000, 1020, 980, 400, 380, 360]),
            (11.0, [455, 445, 460, 180, 170, 165]),
        ])
        tr = transparency_trend(proj)
        assert tr is not None
        assert tr.n_pointings == 2
        assert tr.verdict == "degraded"
        assert tr.degraded_after_utc is not None
    finally:
        proj.close()


def test_a_single_pointing_night_is_untouched_by_the_panel_levelling(tmp_path):
    """Fail-neutral: the ordinary target (one pointing, or unsolved subs) must
    come out exactly as it did before the levelling existed — same verdict, same
    numbers, and `n_pointings == 0` so the card says nothing extra."""
    scores = [1000, 1020, 980, 990, 700, 520, 480, 450, 420]
    for ra in (None, 10.0):  # unsolved, then one real pointing (plus a dither)
        proj = Project.create(tmp_path / f"t{ra}", "M31")
        try:
            base = datetime(2026, 7, 10, 22, 0, 0)
            for i, sc in enumerate(scores):
                # ±0.02° of jitter is a dither, not a panel step.
                jitter = None if ra is None else ra + (0.02 if i % 2 else -0.02)
                proj.add_frame(_frame(base + timedelta(minutes=3 * i),
                                      transparency_score=sc, ra=jitter,
                                      dec=None if ra is None else 41.0))
            tr = transparency_trend(proj)
            assert tr is not None
            assert tr.n_pointings == 0
            assert tr.verdict == "degraded"
            assert [p.transparency for p in tr.points] == [float(s) for s in scores]
        finally:
            proj.close()


def test_one_measurable_panel_alone_levels_nothing(tmp_path):
    """A split where only *one* panel carries enough measured subs to have its
    own median: rescaling that panel against un-rescaled neighbours would move
    the night for no honest reason, so nothing is levelled and the card stays
    silent about panels."""
    proj = Project.create(tmp_path / "t", "M31 mosaic")
    try:
        _mosaic_night(proj, [
            (10.0, [1000, 1020, 980, 1010, 990, 1005]),
            (11.0, [450, None]),  # too thin to measure
        ])
        tr = transparency_trend(proj)
        assert tr is not None
        assert tr.n_pointings == 0
    finally:
        proj.close()


# --- A row is one observing NIGHT, not one capture session -------------------
#
# The 6 h gap split and an observing night disagree in exactly one direction: an
# evening run, bed, then a pre-dawn run are two sessions inside one night. On a
# card headed "Nights", whose per-row "Set aside" button is worded about *the
# night*, that split a night's subs across two identically dated rows and let a
# beginner drop only half of a clouded-out night.

def _night_key_utc(ts):
    """The stand-in the webapp supplies for real: bucket a stamp into its local
    noon-to-noon night at longitude 0 (i.e. plain UTC)."""
    from seestack.activity_calendar import night_date_of
    if not ts:
        return None
    d = night_date_of(ts, 0.0)
    return d.isoformat() if d is not None else None


def _split_night(proj, *, evening_fwhm=3.0, predawn_fwhm=3.0):
    """One observing night shot in two goes 8 h apart — 21:00 and then 05:00 the
    next morning, which is the same night by the noon-to-noon rule but two
    sessions by the 6 h gap rule."""
    evening = datetime(2026, 7, 1, 21, 0, 0)
    for i in range(6):
        proj.add_frame(_frame(evening + timedelta(seconds=30 * i), fwhm_px=evening_fwhm))
    predawn = datetime(2026, 7, 2, 5, 0, 0)
    for i in range(4):
        proj.add_frame(_frame(predawn + timedelta(seconds=30 * i), fwhm_px=predawn_fwhm))


def test_a_night_shot_in_two_goes_is_two_sessions_without_the_night_key(tmp_path):
    """The pre-existing behaviour of the *unkeyed* call, pinned so the default
    cannot drift. Every surface that calls itself a night now passes the key;
    the bare call is what a caller with no longitude still gets."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        _split_night(proj)
        nights = nights_breakdown(proj)
        assert len(nights) == 2
        # ...and both halves carry the SAME observing-night label — which is the
        # bug as the owner saw it: two rows, one date.
        assert {_night_key_utc(n.start_utc) for n in nights} == {"2026-07-01"}
    finally:
        proj.close()


def test_a_night_shot_in_two_goes_is_one_row_with_the_night_key(tmp_path):
    """With the night key, the same frames roll up into one night whose bounds
    span both halves — so the row's "Set aside" window covers the whole night."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        _split_night(proj)
        [night] = nights_breakdown(proj, night_of=_night_key_utc)
        assert night.n_frames == 10          # 6 evening + 4 pre-dawn
        assert night.n_kept == 10
        assert night.exposure_s == 100.0     # 10 subs × 10 s
        assert night.start_utc.startswith("2026-07-01T21:00")
        assert night.end_utc.startswith("2026-07-02T05:01")
    finally:
        proj.close()


def test_the_merged_night_hands_set_aside_every_sub_in_it(tmp_path):
    """The point of merging: the window on the row reaches both halves, so the
    one-click action drops the whole night rather than whichever half was
    listed. Pinned through ``night_frame_ids``, which is what the endpoint
    behind the button calls."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        _split_night(proj)
        [night] = nights_breakdown(proj, night_of=_night_key_utc)
        ids = night_frame_ids(proj, night.start_utc, night.end_utc)
        assert len(ids) == 10
        # Before the fix each row reached only its own half.
        halves = nights_breakdown(proj)
        assert [len(night_frame_ids(proj, h.start_utc, h.end_utc)) for h in halves] == [4, 6]
    finally:
        proj.close()


def test_the_merged_night_recomputes_its_statistics_over_the_whole_night(tmp_path):
    """Not "pick one half's numbers": a night whose halves measured 3.0 and 5.0
    has a median over all ten subs, not over the six the first session held."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        _split_night(proj, evening_fwhm=3.0, predawn_fwhm=5.0)
        [night] = nights_breakdown(proj, night_of=_night_key_utc)
        assert night.median_fwhm_px == 3.0   # median of [3,3,3,3,3,3,5,5,5,5]
        # Its verdict is judged against the *other* nights, of which there are
        # none — so there is nothing to call it soft against, and a single night
        # is never nodded "best".
        assert night.typical_fwhm_px is None
        assert night.is_best is False
        assert night.verdict == "sharp"
    finally:
        proj.close()


def test_a_split_night_no_longer_skews_the_soft_baseline(tmp_path):
    """The statistical cost of the old split, and the reason this is more than
    tidying. Two real nights, the first shot in two goes: as sessions the
    baseline is a median over *three* medians, two of which are the same night
    counted twice, so it is dragged toward that night. As nights it is the other
    night's median, full stop."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        _split_night(proj, evening_fwhm=3.0, predawn_fwhm=3.0)
        later = datetime(2026, 7, 8, 22, 0, 0)
        for i in range(5):
            proj.add_frame(_frame(later + timedelta(seconds=30 * i), fwhm_px=4.2))
        nights = nights_breakdown(proj, night_of=_night_key_utc)
        assert len(nights) == 2
        newest, first = nights[0], nights[1]
        assert newest.start_utc.startswith("2026-07-08")
        assert first.typical_fwhm_px == 4.2   # the *other* night, once
        assert newest.typical_fwhm_px == 3.0
        assert newest.verdict == "soft"       # 4.2 ≥ 3.0×1.25 and ≥ 3.0+0.6
        assert first.is_best is True
    finally:
        proj.close()


def test_consecutive_nights_are_never_merged(tmp_path):
    """The direction the two rules *cannot* disagree in, pinned anyway: back-to-
    back nights are more than 6 h apart and carry different night dates, so no
    grouping key can fuse them."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        for day in (1, 2, 3):
            base = datetime(2026, 7, day, 22, 0, 0)
            for i in range(4):
                proj.add_frame(_frame(base + timedelta(seconds=30 * i), fwhm_px=3.0))
        nights = nights_breakdown(proj, night_of=_night_key_utc)
        assert len(nights) == 3
        assert [_night_key_utc(n.start_utc) for n in nights] == [
            "2026-07-03", "2026-07-02", "2026-07-01",
        ]
    finally:
        proj.close()


def test_an_unplaceable_night_never_merges_with_anything(tmp_path):
    """A key of ``None`` means "I can't say which night this is" — two of those
    in a row are not evidence they are the same night, so they stay apart."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        _split_night(proj)
        nights = nights_breakdown(proj, night_of=lambda ts: None)
        assert len(nights) == 2
    finally:
        proj.close()


# --- ...and so is a night the PACE counts ------------------------------------
#
# ``recent_night_pace_s`` is the number behind "about 2 more clear nights", and
# it split the same way the Nights card used to. So a night shot in two goes
# entered the median twice, each entry carrying roughly half the night's light —
# biasing the pace low, and in the direction that matters: the app told a
# beginner they needed *more* clear nights than they did.

_SPLIT_NIGHT_EPOCH = datetime(2026, 7, 1, 21, 0, 0)


def _split_night_of(proj, day: int, *, n_evening: int, n_predawn: int,
                    exposure: float = 10.0) -> None:
    """One observing night shot in two goes 8 h apart (21:00, then 05:00 the next
    morning): the same night by the noon-to-noon rule, two sessions by the 6 h
    gap rule. ``day`` is a whole-day offset from 2026-07-01, so a long run of
    them can't fall off the end of a month."""
    evening = _SPLIT_NIGHT_EPOCH + timedelta(days=day)
    for i in range(n_evening):
        proj.add_frame(_frame(evening + timedelta(seconds=30 * i), exposure=exposure))
    predawn = evening + timedelta(hours=8)
    for i in range(n_predawn):
        proj.add_frame(_frame(predawn + timedelta(seconds=30 * i), exposure=exposure))


def test_pace_counts_a_split_night_once_with_the_night_key(tmp_path):
    """Three nights, each shot in two 300 s goes. As sessions the pace is 300 s —
    half a night's worth — and the ETA it feeds is twice as long as the truth.
    As observing nights it is the 600 s those nights really produced."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        for day in (1, 8, 15):
            _split_night_of(proj, day, n_evening=30, n_predawn=30)
        assert recent_night_pace_s(proj) == 300.0  # the old, halved figure
        assert recent_night_pace_s(proj, night_of=_night_key_utc) == 600.0
    finally:
        proj.close()


def test_pace_agrees_with_the_nights_card_it_claims_to_agree_with(tmp_path):
    """The docstring's own promise, pinned against the rows the Target page
    actually fetches (``/api/targets/{safe}/nights`` passes a night key). Both
    sides must be handed the same key, or the two screens quote different ETAs
    for one picture."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        for day, subs in ((1, (30, 30)), (8, (20, 40)), (15, (45, 45))):
            _split_night_of(proj, day, n_evening=subs[0], n_predawn=subs[1])
        nights = nights_breakdown(proj, night_of=_night_key_utc)
        assert len(nights) == 3
        assert recent_night_pace_s(proj, night_of=_night_key_utc) == median(
            [n.kept_exposure_s for n in nights]
        )
    finally:
        proj.close()


def test_a_split_short_night_stops_vanishing_under_the_productive_floor(tmp_path):
    """The second, larger error the halving caused: ``MIN_PRODUCTIVE_NIGHT_S`` is
    a floor on a *night*, so halving one can push both halves under it and drop a
    genuinely real night from the pace entirely — leaving too few nights to call
    it a pace at all. Merged, the night counts for what it produced."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        # 2 × 100 s per night: each half is under the 120 s floor, the night is not.
        for day in (1, 8, 15):
            _split_night_of(proj, day, n_evening=10, n_predawn=10)
        assert recent_night_pace_s(proj) is None
        assert recent_night_pace_s(proj, night_of=_night_key_utc) == 200.0
    finally:
        proj.close()


def test_pace_lookback_window_reaches_five_nights_not_two_and_a_half(tmp_path):
    """``PACE_LOOKBACK_NIGHTS`` is documented as "long enough that one short night
    doesn't dominate". Counting halves silently halved its reach too: on a
    habitual split-night observer five *sessions* are two and a half nights, so
    the newest night or two decided the pace on their own. Six nights, the oldest
    four long and the newest two short: as nights the median is still the long
    habit (four of the five in window), as sessions it is the last two nights
    alone."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        for day in (0, 7, 14, 21):
            _split_night_of(proj, day, n_evening=120, n_predawn=120)  # 2400 s
        for day in (28, 35):
            _split_night_of(proj, day, n_evening=30, n_predawn=30)    # 600 s
        assert PACE_LOOKBACK_NIGHTS == 5
        # Five nights back = one 600 s night short of the whole long habit.
        assert recent_night_pace_s(proj, night_of=_night_key_utc) == 2400.0
        # Five sessions back reaches only two and a half nights: four of the five
        # entries are the two short nights' halves, so they decide the median on
        # their own and the long habit is outvoted by a night-and-a-half of data.
        assert recent_night_pace_s(proj) == 300.0
    finally:
        proj.close()


def test_pace_with_a_night_key_leaves_ordinary_nights_alone(tmp_path):
    """No-regression: on the ordinary shape — one unbroken run per night — the
    key changes nothing, because a session never spans two nights."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        _night(proj, 1, n=30)   # 300 s
        _night(proj, 8, n=60)   # 600 s
        _night(proj, 15, n=90)  # 900 s
        assert recent_night_pace_s(proj) == 600.0
        assert recent_night_pace_s(proj, night_of=_night_key_utc) == 600.0
    finally:
        proj.close()


def test_pace_with_an_unplaceable_night_key_falls_back_to_sessions(tmp_path):
    """A key that can never place a stamp (no longitude, unparseable stamps) must
    degrade to the old session split rather than fusing everything into one."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        for day in (1, 8, 15):
            _split_night_of(proj, day, n_evening=30, n_predawn=30)
        assert recent_night_pace_s(proj, night_of=lambda ts: None) == 300.0
    finally:
        proj.close()


# --- "it stopped earlier than it usually does" (the morning quiet-capture line) ---

def _night_frames(day: datetime, *, start_h: int, end_h: float, every_min: int = 10):
    """One night's worth of subs from ``start_h`` to ``end_h`` (UTC hours, which
    may run past 24 into the next day), at a steady cadence."""
    out = []
    t = day.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(hours=start_h)
    end = day.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(hours=end_h)
    while t <= end:
        out.append(_frame(t))
        t += timedelta(minutes=every_min)
    return out


def _ends(nights):
    """``session_end_stamps`` over a list of per-night frame lists."""
    from seestack.session_recap import session_end_stamps

    flat = [f for night in nights for f in night]
    return session_end_stamps(flat)


def test_session_end_stamps_gives_one_stamp_per_night_oldest_first():
    from seestack.session_recap import session_end_stamps

    base = datetime(2026, 8, 1)
    nights = [_night_frames(base + timedelta(days=d), start_h=21, end_h=26)
              for d in range(3)]
    ends = session_end_stamps([f for n in nights for f in n])
    assert len(ends) == 3
    assert ends == [n[-1].timestamp_utc for n in nights]


def test_early_stop_fires_when_a_night_ends_hours_before_the_usual_stop():
    from seestack.session_recap import early_stop

    base = datetime(2026, 8, 1)
    # Four nights ending at 02:00, then one that stops at 22:30.
    nights = [_night_frames(base + timedelta(days=d), start_h=21, end_h=26)
              for d in range(4)]
    nights.append(_night_frames(base + timedelta(days=4), start_h=21, end_h=22.5))
    stop = early_stop(_ends(nights))
    assert stop is not None
    assert stop.n_nights_compared == 4
    # 02:00 → 22:30 is three and a half hours early, measured across midnight.
    assert stop.minutes_earlier == 210.0
    assert stop.stopped_utc.startswith("2026-08-05T22:30")


def test_early_stop_is_silent_on_a_night_that_ended_as_usual():
    from seestack.session_recap import early_stop

    base = datetime(2026, 8, 1)
    nights = [_night_frames(base + timedelta(days=d), start_h=21, end_h=26)
              for d in range(5)]
    assert early_stop(_ends(nights)) is None


def test_early_stop_measures_across_midnight_rather_than_around_the_clock():
    """The trap this helper exists to avoid: a target that usually ends at 00:20
    and stopped at 23:40 is forty minutes early, not twenty-three hours late — so
    it must stay *silent*, where a naive time-of-day subtraction would shout."""
    from seestack.session_recap import early_stop

    base = datetime(2026, 8, 1)
    nights = [_night_frames(base + timedelta(days=d), start_h=21, end_h=24.33)
              for d in range(4)]
    nights.append(_night_frames(base + timedelta(days=4), start_h=21, end_h=23.66))
    assert early_stop(_ends(nights)) is None


def test_early_stop_says_nothing_without_enough_nights_to_have_a_habit():
    """A target's first couple of nights have no "usual" — every stop time is as
    typical as every other, so any claim about one would be invented."""
    from seestack.session_recap import early_stop

    base = datetime(2026, 8, 1)
    nights = [_night_frames(base + timedelta(days=d), start_h=21, end_h=26)
              for d in range(2)]
    nights.append(_night_frames(base + timedelta(days=2), start_h=21, end_h=22.0))
    assert early_stop(_ends(nights)) is None


def test_early_stop_ignores_nights_from_a_different_season():
    """The yardstick is a clock time and darkness moves with the season, so a
    night from three months back is not evidence about tonight's habit."""
    from seestack.session_recap import early_stop

    base = datetime(2026, 5, 1)
    old = [_night_frames(base + timedelta(days=d), start_h=21, end_h=26)
           for d in range(4)]
    recent = [_night_frames(datetime(2026, 8, 1), start_h=21, end_h=22.0)]
    assert early_stop(_ends(old + recent)) is None


def test_early_stop_holds_its_tongue_just_under_the_threshold():
    from seestack.session_recap import EARLY_STOP_MIN_MINUTES, early_stop

    base = datetime(2026, 8, 1)
    nights = [_night_frames(base + timedelta(days=d), start_h=21, end_h=26)
              for d in range(4)]
    just_under = 26 - (EARLY_STOP_MIN_MINUTES - 10) / 60.0
    nights.append(_night_frames(base + timedelta(days=4),
                                start_h=21, end_h=just_under))
    assert early_stop(_ends(nights)) is None
    just_over = 26 - (EARLY_STOP_MIN_MINUTES + 10) / 60.0
    nights[-1] = _night_frames(base + timedelta(days=4),
                               start_h=21, end_h=just_over)
    assert early_stop(_ends(nights)) is not None


def test_early_stop_takes_a_median_so_one_odd_night_cannot_set_the_habit():
    """One marathon night must not make every ordinary night after it look like a
    failure — which is exactly what a mean, or a max, would do."""
    from seestack.session_recap import early_stop

    base = datetime(2026, 8, 1)
    nights = [
        _night_frames(base, start_h=21, end_h=31),            # one dusk-to-dawn run
        _night_frames(base + timedelta(days=1), start_h=21, end_h=24.5),
        _night_frames(base + timedelta(days=2), start_h=21, end_h=24.5),
        _night_frames(base + timedelta(days=3), start_h=21, end_h=24.5),
        _night_frames(base + timedelta(days=4), start_h=21, end_h=24.0),
    ]
    assert early_stop(_ends(nights)) is None


# --- the same fact, on the target's own page --------------------------------
#
# The Dashboard's "Last night" card can only ever speak for the library's most
# recent capture night. A target shot on Tuesday and not returned to has this
# fact recorded and nowhere to say it by Thursday, so the newest row of its own
# Nights breakdown carries it.


def _add_all(proj, nights):
    for night in nights:
        for f in night:
            proj.add_frame(f)


def _noon_night_key(stamp):
    """Noon-to-noon observing-night buckets at longitude 0, the shape the
    webapp's ``resolve_night_key`` produces."""
    if not stamp:
        return None
    return (datetime.fromisoformat(stamp) - timedelta(hours=12)).date().isoformat()


def test_nights_breakdown_marks_the_newest_night_that_stopped_early(tmp_path):
    """Four nights ending at 02:00, then one that stops at 22:30 → the newest
    row says so, and no older row does."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        base = datetime(2026, 8, 1)
        nights = [_night_frames(base + timedelta(days=d), start_h=21, end_h=26)
                  for d in range(4)]
        nights.append(_night_frames(base + timedelta(days=4),
                                    start_h=21, end_h=22.5))
        _add_all(proj, nights)
        rows = nights_breakdown(proj)  # newest first
        assert len(rows) == 5
        assert rows[0].ended_early is not None
        assert rows[0].ended_early.minutes_earlier == 210.0
        assert rows[0].ended_early.n_nights_compared == 4
        assert rows[0].ended_early.stopped_utc.startswith("2026-08-05T22:30")
        # The marker is dated by the row it sits on; history is not annotated.
        assert all(r.ended_early is None for r in rows[1:])
    finally:
        proj.close()


def test_nights_breakdown_says_nothing_about_a_night_that_ended_as_usual(tmp_path):
    """Silence is the default — an owner who goes to bed at the same time every
    night must never be told they lost half of one."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        base = datetime(2026, 8, 1)
        _add_all(proj, [_night_frames(base + timedelta(days=d),
                                      start_h=21, end_h=26)
                        for d in range(5)])
        rows = nights_breakdown(proj)
        assert len(rows) == 5
        assert all(r.ended_early is None for r in rows)
    finally:
        proj.close()


def test_nights_breakdown_early_stop_reads_the_same_stamps_as_the_dashboard(tmp_path):
    """A night shot in two goes is ONE row here (``night_of`` merges it) and one
    night on the Dashboard too. Both surfaces judge from the *same* stamps —
    session ends merged by observing night — or they would quote different
    medians for the same night with no way for the reader to tell which is
    right."""
    from seestack.session_recap import (
        early_stop,
        merge_end_stamps_by_night,
        session_end_stamps,
    )

    proj = Project.create(tmp_path / "p", name="t")
    try:
        base = datetime(2026, 8, 1)
        nights = []
        for d in range(4):
            # An evening run, bed, then a pre-dawn run: 21:00 → 04:00 is more
            # than the 6 h session gap, so two sessions inside one night.
            day = base + timedelta(days=d)
            nights.append(_night_frames(day, start_h=19, end_h=21))
            nights.append(_night_frames(day, start_h=28, end_h=29))
        nights.append(_night_frames(base + timedelta(days=4),
                                    start_h=19, end_h=21.5))
        _add_all(proj, nights)
        flat = [f for night in nights for f in night]

        def _night_of(stamp):
            # Noon-to-noon buckets, as the webapp's observing-night key does.
            if not stamp:
                return None
            dt = datetime.fromisoformat(stamp) - timedelta(hours=12)
            return dt.date().isoformat()

        rows = nights_breakdown(proj, night_of=_night_of)
        assert len(rows) == 5  # the four split nights merged back into one each
        # Exactly what ``/api/last-night`` computes for the same target.
        assert rows[0].ended_early == early_stop(
            merge_end_stamps_by_night(session_end_stamps(flat), _night_of))
        assert rows[0].ended_early is not None
        # Four prior *nights* — the same four rows below this one, not the eight
        # capture sessions they were shot in. This is the number the card reads
        # out ("earlier than its last N nights"), so it has to be nights.
        assert rows[0].ended_early.n_nights_compared == 4
        # The shortfall itself is unchanged on this evenly-split shape — three of
        # the five session stamps were night ends, so the median already landed
        # on one. It is the *count* that was wrong, and the shapes where the
        # median moves are the two tests below.
        assert rows[0].ended_early.minutes_earlier == 450.0
    finally:
        proj.close()


def test_early_stop_stays_silent_until_there_are_three_real_nights(tmp_path):
    """Two nights, each shot in two goes, are four session stamps — enough to
    clear ``EARLY_STOP_MIN_PRIOR_NIGHTS`` by counting, and not enough to have a
    habit. The constant exists precisely to keep the note off a target's first
    couple of nights, and counting sessions defeated it: measured on this
    fixture, the session view announces a 2½ h early stop over "3 nights" that
    the owner has not shot.
    """
    from seestack.session_recap import (
        early_stop,
        merge_end_stamps_by_night,
        session_end_stamps,
    )

    proj = Project.create(tmp_path / "p", name="t")
    try:
        base = datetime(2026, 8, 1)
        nights = []
        for d in range(2):
            day = base + timedelta(days=d)
            nights.append(_night_frames(day, start_h=19, end_h=21))
            nights.append(_night_frames(day, start_h=28, end_h=29))
        nights.append(_night_frames(base + timedelta(days=2),
                                    start_h=19, end_h=21.5))
        _add_all(proj, nights)
        flat = [f for night in nights for f in night]
        stamps = session_end_stamps(flat)

        # What shipped before: four "nights" from two, and a verdict.
        assert len(stamps) == 5
        assert early_stop(stamps) is not None
        # What the two real nights actually support: nothing to say yet.
        assert early_stop(merge_end_stamps_by_night(stamps, _noon_night_key)) is None
        assert nights_breakdown(proj, night_of=_noon_night_key)[0].ended_early is None
    finally:
        proj.close()


def test_early_stop_measures_a_three_goes_night_against_when_it_ended(tmp_path):
    """The other direction: on a night habitually shot in three goes, only one
    stamp in three is a true night end, so the median lands on a *mid-night*
    stop and the shortfall all but vanishes. Measured on this fixture the
    session view reports **2½ h** for a night that ended **9½ h** early.
    """
    from seestack.session_recap import (
        early_stop,
        merge_end_stamps_by_night,
        session_end_stamps,
    )

    proj = Project.create(tmp_path / "p", name="t")
    try:
        base = datetime(2026, 8, 1)
        nights = []
        for d in range(3):
            # 19:00–20:30, 03:00–04:00, 10:30–11:00 — three goes, one night.
            day = base + timedelta(days=d)
            nights.append(_night_frames(day, start_h=19, end_h=20.5))
            nights.append(_night_frames(day, start_h=27, end_h=28))
            nights.append(_night_frames(day, start_h=34.5, end_h=35))
        # …and one that stopped at 01:30 instead of running on to 11:00.
        nights.append(_night_frames(base + timedelta(days=3),
                                    start_h=19, end_h=20.5))
        nights.append(_night_frames(base + timedelta(days=3),
                                    start_h=24.5, end_h=25.5))
        _add_all(proj, nights)
        flat = [f for night in nights for f in night]
        stamps = session_end_stamps(flat)

        by_session = early_stop(stamps)
        assert by_session is not None
        assert by_session.minutes_earlier == 150.0    # a mid-night stop as the yardstick
        assert by_session.n_nights_compared == 5      # …over three nights of data

        merged = early_stop(merge_end_stamps_by_night(stamps, _noon_night_key))
        assert merged is not None
        assert merged.minutes_earlier == 570.0        # 01:30 against a usual 11:00
        assert merged.n_nights_compared == 3
        assert nights_breakdown(
            proj, night_of=_noon_night_key)[0].ended_early == merged
    finally:
        proj.close()


# --- "a six-hour gap is not a night" — the recap's own site ------------------
#
# The card is dated with an observing night and sits directly above the Nights
# rows, which are night-shaped. Without a night key the recap is the trailing
# *session*, so on a night shot in two goes the two surfaces reported different
# subs under the identical date — measured on this fixture: 4 vs 10.

def test_recap_of_a_split_night_covers_the_whole_night(tmp_path):
    proj = Project.create(tmp_path / "p", name="t")
    try:
        _split_night(proj)
        recap = session_recap(proj, night_of=_night_key_utc)
        assert recap is not None
        assert recap.n_frames == 10          # both halves, not the trailing 4
        assert recap.n_kept == 10
        assert recap.session_exposure_s == 100.0
        # The span is the night's, evening through pre-dawn.
        assert recap.start_utc.startswith("2026-07-01T21:00")
        assert recap.end_utc.startswith("2026-07-02T05:01")
    finally:
        proj.close()


def test_recap_without_a_night_key_is_still_session_shaped(tmp_path):
    """The key is optional — a caller with no longitude gets the old answer
    rather than a guess, exactly as ``nights_breakdown`` degrades."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        _split_night(proj)
        recap = session_recap(proj)
        assert recap is not None
        assert recap.n_frames == 4
    finally:
        proj.close()


def test_recap_and_nights_breakdown_agree_about_a_split_night(tmp_path):
    """The two cards sit one above the other on the Target page; they must not
    report different subs for the same dated night."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        _split_night(proj)
        recap = session_recap(proj, night_of=_night_key_utc)
        [newest] = nights_breakdown(proj, night_of=_night_key_utc)
        assert recap is not None
        assert (recap.n_frames, recap.n_kept, recap.session_exposure_s) == (
            newest.n_frames, newest.n_kept, newest.exposure_s)
        assert _night_key_utc(recap.start_utc) == _night_key_utc(newest.start_utc)
    finally:
        proj.close()


def test_consecutive_nights_are_still_separate_in_the_recap(tmp_path):
    """Merging must only ever roll up *within* a night — two evenings running
    stay two nights, and the recap covers the newer one alone."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        for i in range(4):
            proj.add_frame(_frame(datetime(2026, 7, 1, 22, 0) + timedelta(minutes=i)))
        for i in range(7):
            proj.add_frame(_frame(datetime(2026, 7, 2, 22, 0) + timedelta(minutes=i)))
        recap = session_recap(proj, night_of=_night_key_utc)
        assert recap is not None and recap.n_frames == 7
    finally:
        proj.close()


def test_recap_never_merges_two_undatable_halves(tmp_path):
    """A night key that can't place a stamp must not guess two unplaceable
    halves are the same night — the recap then behaves exactly as with no key."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        _split_night(proj)
        blind = session_recap(proj, night_of=lambda _ts: None)
        plain = session_recap(proj)
        assert blind is not None and plain is not None
        assert blind.n_frames == plain.n_frames == 4
    finally:
        proj.close()


def test_split_night_drift_compares_whole_nights(tmp_path):
    """The softer-stars nudge compares the newest group against the prior ones.
    Merged by night, a split prior night is one baseline entry rather than two —
    so its two halves can no longer be each other's 'prior night'."""
    proj = Project.create(tmp_path / "p", name="t")
    try:
        # One prior night, itself shot in two goes, with sharp stars…
        _split_night(proj)                                  # 6 + 4 subs at 3.0 px
        # …then a soft night.
        for i in range(8):
            proj.add_frame(_frame(datetime(2026, 7, 3, 22, 0) + timedelta(minutes=i),
                                  fwhm_px=5.0))
        recap = session_recap(proj, night_of=_night_key_utc)
        assert recap is not None and recap.quality_drift is not None
        # One prior *night*, so the sub count behind the baseline is the whole
        # night's ten, not one half's four.
        assert recap.quality_drift.baseline_fwhm_px == 3.0
        assert recap.quality_drift.n_baseline == 10
        assert recap.quality_drift.n_latest == 8
    finally:
        proj.close()
