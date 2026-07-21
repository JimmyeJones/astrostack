"""Last-session recap — plain-language summary of the most recent capture night."""

from datetime import datetime, timedelta

from seestack.io.project import FrameRow, Project
from seestack.session_recap import (
    bucket_reject_reason,
    last_session_frames,
    library_session_recap,
    recent_session_window_frames,
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
