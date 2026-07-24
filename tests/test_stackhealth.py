"""Unit tests for the plain-language "How's my stack?" health check."""

from __future__ import annotations

from seestack.io.project import FrameRow, StackRunRow
from seestack.stackhealth import recommended_dark_spec, stack_health


def _run(**kw) -> StackRunRow:
    base = dict(
        id=1, timestamp_utc="2026-07-14T00:00:00+00:00", output_basename="m42",
        fits_path="m42.fits", tiff_path=None, preview_path=None,
        n_frames_used=30, canvas_h=1080, canvas_w=1920,
        coverage_min=30, coverage_max=30, options_json="{}",
        calstat="dark+flat", is_mosaic=False,
    )
    base.update(kw)
    return StackRunRow(**base)


def _frame(*, accept=True, ecc=0.35, reason=None, wcs=None) -> FrameRow:
    return FrameRow(source_path=f"s{id(object())}.fit", accept=accept,
                    eccentricity_median=ecc, reject_reason=reason, wcs_json=wcs)


def _kinds(notes) -> list[str]:
    return [n.kind for n in notes]


def _exp_frame(*, accept=True, exposure_s=10.0, gain=80.0) -> FrameRow:
    return FrameRow(source_path=f"s{id(object())}.fit", accept=accept,
                    exposure_s=exposure_s, gain=gain)


def test_recommended_dark_spec_reads_the_typical_exposure_and_gain():
    """Darks must match the lights, so the spec is the median exposure/gain of
    the accepted subs — the numbers the beginner should dial in."""
    frames = [_exp_frame(exposure_s=10.0, gain=80.0) for _ in range(5)]
    spec = recommended_dark_spec(frames)
    assert spec.exposure_s == 10.0
    assert spec.gain == 80.0


def test_recommended_dark_spec_ignores_rejected_frames():
    frames = [_exp_frame(exposure_s=10.0, gain=80.0) for _ in range(4)]
    # A rejected 30 s frame must not drag the median toward itself.
    frames.append(_exp_frame(accept=False, exposure_s=30.0, gain=200.0))
    spec = recommended_dark_spec(frames)
    assert spec.exposure_s == 10.0 and spec.gain == 80.0


def test_recommended_dark_spec_degrades_when_metadata_missing():
    """No recorded exposure/gain → None fields (the guide shows generic wording,
    never a wrong number)."""
    frames = [_exp_frame(exposure_s=None, gain=None) for _ in range(3)]
    spec = recommended_dark_spec(frames)
    assert spec.exposure_s is None and spec.gain is None
    # A non-positive exposure is treated as unrecorded, too.
    assert recommended_dark_spec([_exp_frame(exposure_s=0.0)]).exposure_s is None


def test_recommended_dark_spec_empty_target():
    spec = recommended_dark_spec([])
    assert spec.exposure_s is None and spec.gain is None


def test_healthy_calibrated_stack_reports_a_positive_note():
    notes = stack_health(_run(), [_frame() for _ in range(10)])
    assert notes  # always at least one
    solid = next(n for n in notes if n.kind == "solid")
    assert solid.severity == "good"
    assert "calibrated" in solid.message and "round stars" in solid.message


def test_missing_calibration_leads_with_an_actionable_note():
    notes = stack_health(_run(calstat=None), [_frame() for _ in range(10)])
    # The calibration note is actionable and must rank first.
    assert notes[0].kind == "calibration"
    assert notes[0].action == "calibration"
    assert "darks" in notes[0].message.lower()


def test_blank_calstat_counts_as_uncalibrated():
    notes = stack_health(_run(calstat="   "), [_frame() for _ in range(5)])
    assert _kinds(notes)[0] == "calibration"


def test_ragged_border_suggests_trim():
    # min far below the peak, and enough frames at the peak for it to matter.
    notes = stack_health(_run(coverage_min=2, coverage_max=30),
                         [_frame() for _ in range(10)])
    trim = next(n for n in notes if n.kind == "coverage")
    assert trim.action == "trim_border"


def test_even_coverage_does_not_suggest_trim():
    notes = stack_health(_run(coverage_min=28, coverage_max=30),
                         [_frame() for _ in range(10)])
    assert "coverage" not in _kinds(notes)


def test_shallow_coverage_peak_does_not_trip_ragged_border():
    # A 3-frame peak is below _COVERAGE_MIN_PEAK, so the ratio is meaningless.
    notes = stack_health(_run(coverage_min=0, coverage_max=3),
                         [_frame() for _ in range(3)])
    assert "coverage" not in _kinds(notes)


def test_elongated_stars_flagged_gently():
    notes = stack_health(_run(), [_frame(ecc=0.72) for _ in range(10)])
    stars = next(n for n in notes if n.kind == "stars")
    assert stars.severity == "info" and stars.action is None
    assert "elongated" in stars.message
    # ...and "round stars" is NOT claimed as a strength.
    solid = next((n for n in notes if n.kind == "solid"), None)
    if solid is not None:
        assert "round stars" not in solid.message


def test_set_aside_subs_get_a_reassuring_note_with_bucket():
    frames = [_frame() for _ in range(8)]
    frames += [_frame(accept=False, reason="auto:streak") for _ in range(2)]
    notes = stack_health(_run(), frames)
    rej = next(n for n in notes if n.kind == "rejects")
    assert rej.severity == "good"
    assert "2 of 10" in rej.message and "trailed" in rej.message


def test_no_frames_still_returns_a_note():
    # A stack with no frame records (older project) never crashes; a calibrated
    # run with no star data still yields the calibration-strength note.
    notes = stack_health(_run(), [])
    assert notes and notes[0].severity in ("good", "info")


def test_actionable_notes_rank_before_reassurance_and_positives():
    # Uncalibrated + ragged border + rejects: actionable first, reassurance last.
    frames = [_frame() for _ in range(8)] + [_frame(accept=False, reason="user")]
    notes = stack_health(_run(calstat=None, coverage_min=1, coverage_max=20), frames)
    order = _kinds(notes)
    assert order.index("calibration") < order.index("rejects")
    assert order.index("coverage") < order.index("rejects")


def test_sigma_clip_rejection_gets_a_plain_language_cleanup_note():
    # A κ-σ stack that clipped a real fraction of samples names the invisible
    # "we removed the trails/cosmic-rays" work in plain language.
    notes = stack_health(
        _run(rejection_mode="sigma-clip", rejection_fraction=0.012),
        [_frame() for _ in range(10)],
    )
    rej = next(n for n in notes if n.kind == "rejection")
    assert rej.severity == "good" and rej.action is None
    assert "1.2%" in rej.message
    assert "satellites" in rej.message and "cosmic-ray" in rej.message


def test_drizzle_reject_also_gets_the_cleanup_note():
    notes = stack_health(
        _run(rejection_mode="drizzle-reject", rejection_fraction=0.004),
        [_frame() for _ in range(10)],
    )
    rej = next(n for n in notes if n.kind == "rejection")
    assert rej.severity == "good"
    assert "0.4%" in rej.message


def test_near_zero_rejection_makes_no_cleanup_claim():
    # A stack that rejected essentially nothing shouldn't claim a clean-up.
    notes = stack_health(
        _run(rejection_mode="sigma-clip", rejection_fraction=0.0),
        [_frame() for _ in range(10)],
    )
    assert "rejection" not in _kinds(notes)


def test_suspiciously_high_rejection_stays_silent_here():
    # Above the honest band a cheerful "we cleaned trails" note could over-claim
    # (κ may be eating real signal) — the beginner card stays quiet.
    notes = stack_health(
        _run(rejection_mode="sigma-clip", rejection_fraction=0.20),
        [_frame() for _ in range(10)],
    )
    assert "rejection" not in _kinds(notes)


def test_min_max_rejection_names_the_guarantee_without_a_percentage():
    # Min/max is structural, so its fraction isn't a clean-up figure — name only
    # what the method guarantees, with no (misleading) percentage.
    notes = stack_health(
        _run(rejection_mode="min-max-reject", rejection_fraction=0.5),
        [_frame() for _ in range(10)],
    )
    rej = next(n for n in notes if n.kind == "rejection")
    assert rej.severity == "good"
    assert "%" not in rej.message
    assert "brightest and darkest" in rej.message


def test_plain_mean_stack_has_no_rejection_note():
    # No rejection ran (both fields NULL) → nothing to say.
    notes = stack_health(_run(), [_frame() for _ in range(10)])
    assert "rejection" not in _kinds(notes)


def test_mostly_unsolved_subs_leads_with_an_actionable_note():
    # A faint field where ASTAP solved only a handful of subs: the whole night
    # collapses to the located few, so the card leads with the highest-value fix.
    frames = [_frame(wcs="{}") for _ in range(20)]      # located
    frames += [_frame(wcs=None) for _ in range(190)]    # accepted but unsolved
    notes = stack_health(_run(), frames)
    assert notes[0].kind == "unsolved"
    assert notes[0].action == "solve_help"
    assert notes[0].severity == "info"
    assert "20 of 210" in notes[0].message
    assert "star database" in notes[0].message.lower()


def test_all_located_subs_get_no_unsolved_note():
    # Every accepted sub plate-solved → nothing to warn about.
    notes = stack_health(_run(), [_frame(wcs="{}") for _ in range(30)])
    assert "unsolved" not in _kinds(notes)


def test_a_few_unsolved_subs_below_the_fraction_stays_silent():
    # 2 of 20 unlocated (10%) is normal attrition, not a solve problem.
    frames = [_frame(wcs="{}") for _ in range(18)] + [_frame(wcs=None) for _ in range(2)]
    notes = stack_health(_run(), frames)
    assert "unsolved" not in _kinds(notes)


def test_no_located_subs_stays_silent_solve_pending():
    # Zero located subs means plate-solve simply hasn't run yet (all accepted
    # frames have no WCS) — that's not a solve *failure* to report, so stay quiet.
    notes = stack_health(_run(), [_frame(wcs=None) for _ in range(30)])
    assert "unsolved" not in _kinds(notes)


def test_too_few_accepted_subs_no_unsolved_note():
    # Below the minimum accepted count the fraction is meaningless (a tiny target),
    # so even a high unlocated share doesn't nag.
    frames = [_frame(wcs="{}") for _ in range(3)] + [_frame(wcs=None) for _ in range(3)]
    notes = stack_health(_run(), frames)
    assert "unsolved" not in _kinds(notes)


def test_unsolved_note_ranks_before_calibration():
    # When both fire, the "most subs couldn't locate" fix outranks calibration —
    # it's the bigger lever on a thin faint-field result.
    frames = [_frame(wcs="{}") for _ in range(10)] + [_frame(wcs=None) for _ in range(30)]
    notes = stack_health(_run(calstat=None), frames)
    order = _kinds(notes)
    assert order.index("unsolved") < order.index("calibration")


def test_rejection_note_ranks_after_actionable_next_steps():
    # A clean-up reassurance must never displace an actionable fix from the top.
    notes = stack_health(
        _run(calstat=None, rejection_mode="sigma-clip", rejection_fraction=0.01),
        [_frame() for _ in range(10)],
    )
    order = _kinds(notes)
    assert order.index("calibration") < order.index("rejection")
