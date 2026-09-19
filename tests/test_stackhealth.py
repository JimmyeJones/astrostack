"""Unit tests for the plain-language "How's my stack?" health check."""

from __future__ import annotations

from seestack.io.project import FrameRow, StackRunRow
from seestack.stackhealth import (
    CLEAN_BACKGROUND_SIGMA,
    background_reads_clean,
    recommended_dark_spec,
    seam_scale_is_current,
    stack_health,
    stored_seam_verdict,
    uneven_grain_verdict,
)


def _run(**kw) -> StackRunRow:
    base = dict(
        id=1, timestamp_utc="2026-07-14T00:00:00+00:00", output_basename="m42",
        fits_path="m42.fits", tiff_path=None, preview_path=None,
        n_frames_used=30, canvas_h=1080, canvas_w=1920,
        coverage_min=30, coverage_max=30, coverage_thin_frac=0.0,
        options_json="{}",
        calstat="dark+flat", is_mosaic=False,
        # Every run a real stacker writes carries the version that made it, and
        # since v0.313.1 the seam figure is read against it (a pre-fix figure is
        # on a scale today's thresholds over-read — see
        # ``stored_seam_verdict``). Leaving it unset here would silently make
        # every fixture an *undated* run, i.e. exercise the cautious path in
        # tests that are about something else; the old-scale cases say so
        # explicitly instead.
        engine_version="0.446.4",
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
    assert spec.exposures_s == ()


# --- "at the same settings as your subs" is a claim about a set --------------
#
# A target is one *folder*, never one exposure (`seestack/io/scanner.py` groups
# by folder and has never heard of exposure), so a Seestar owner who shoots 10 s
# on a bright night and 30 s on a faint one owns a target with two lengths in it.
# The median then names a length none of their subs was shot at, under the words
# "at the same settings as your subs".


def test_a_target_shot_at_two_lengths_reports_both_of_them():
    """The sharpest case: an even 10 s / 30 s split has a median of 20 s, and a
    night of 20 s darks matches nothing the owner owns."""
    frames = ([_exp_frame(exposure_s=10.0) for _ in range(3)]
              + [_exp_frame(exposure_s=30.0) for _ in range(3)])
    spec = recommended_dark_spec(frames)
    assert spec.exposure_s == 20.0  # the median every existing reader gates on
    assert spec.exposures_s == (10.0, 30.0)


def test_an_uneven_split_still_reports_the_minority_length():
    """Two-thirds right is not right: the 30 s subs need their own dark."""
    frames = ([_exp_frame(exposure_s=10.0) for _ in range(4)]
              + [_exp_frame(exposure_s=30.0) for _ in range(2)])
    spec = recommended_dark_spec(frames)
    assert spec.exposure_s == 10.0
    assert spec.exposures_s == (10.0, 30.0)


def test_the_ordinary_single_length_target_reports_exactly_one():
    """Every library that has never changed sub length is untouched — and header
    rounding (9.998 against 10.0) must not read as a second exposure."""
    assert recommended_dark_spec(
        [_exp_frame(exposure_s=10.0) for _ in range(5)]).exposures_s == (10.0,)
    spec = recommended_dark_spec(
        [_exp_frame(exposure_s=10.0), _exp_frame(exposure_s=9.998)])
    assert len(spec.exposures_s) == 1


def test_a_rejected_frames_length_is_not_offered_as_a_dark_to_shoot():
    """The set is over the *accepted* subs, like the median beside it — darks for
    frames that will never be stacked are a wasted night."""
    frames = [_exp_frame(exposure_s=10.0) for _ in range(4)]
    frames.append(_exp_frame(accept=False, exposure_s=30.0))
    assert recommended_dark_spec(frames).exposures_s == (10.0,)


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
    # A large share of the picture is thin, and enough frames at the peak for it
    # to matter.
    notes = stack_health(_run(coverage_min=2, coverage_max=30,
                              coverage_thin_frac=0.4),
                         [_frame() for _ in range(10)])
    trim = next(n for n in notes if n.kind == "coverage")
    assert trim.action == "trim_border"


def test_even_coverage_does_not_suggest_trim():
    notes = stack_health(_run(coverage_min=28, coverage_max=30,
                              coverage_thin_frac=0.0),
                         [_frame() for _ in range(10)])
    assert "coverage" not in _kinds(notes)


def test_shallow_coverage_peak_does_not_trip_ragged_border():
    # A 3-frame peak is below _COVERAGE_MIN_PEAK, so nothing about the coverage
    # distribution is worth advising on yet.
    notes = stack_health(_run(coverage_min=0, coverage_max=3,
                              coverage_thin_frac=0.4),
                         [_frame() for _ in range(3)])
    assert "coverage" not in _kinds(notes)


# --- the border note is judged by how much is thin, not by the thinnest pixel --
# ``coverage_min`` is the extreme minimum, which is 1 on any dithered stack (some
# fringe pixel was touched once) and 0 on any mosaic (the canvas corners are
# uncovered) — so the old ``coverage_min <= 0.25 * coverage_max`` test fired on
# every stack the app has ever produced, and its complement, the "even coverage"
# praise, could never be earned by anybody.


def test_a_dithered_stack_is_not_told_its_edges_are_ragged():
    # Measured on real run_stack output: a +/-6 px dither on a 480 px frame leaves
    # 0.2-0.6 % of the picture thin, at 8, 32 and 128 subs alike. The old test saw
    # coverage_min=8, coverage_max=128 and called that a ragged border.
    notes = stack_health(_run(coverage_min=8, coverage_max=128,
                              coverage_thin_frac=0.006),
                         [_frame() for _ in range(10)])
    assert "coverage" not in _kinds(notes)


def test_a_dithered_stack_can_now_be_praised_for_even_coverage():
    notes = stack_health(_run(coverage_min=8, coverage_max=128,
                              coverage_thin_frac=0.006),
                         [_frame() for _ in range(10)])
    solid = next(n for n in notes if n.kind == "solid")
    assert "even coverage" in solid.message


# --- and the black *around* the picture, which the note above cannot see ------
# The thin share is a ratio over covered pixels, so a canvas that is a third
# empty corners reads 0.00 on it. The empty share is the only thing that can
# explain the black bands a mosaic's union canvas leaves.


def test_a_mostly_empty_canvas_says_what_the_black_is():
    # A diagonal two-panel mosaic measures ~37% empty on real run_stack output,
    # with a thin share of 0.00 — i.e. the note above stays silent on it.
    notes = stack_health(_run(coverage_min=0, coverage_max=30,
                              coverage_thin_frac=0.0, uncovered_frac=0.37),
                         [_frame() for _ in range(10)])
    assert "coverage" not in _kinds(notes)
    black = next(n for n in notes if n.kind == "uncovered")
    assert "37%" in black.message
    # It explains before it offers: nothing is wrong with the picture itself.
    assert "normal" in black.message
    assert black.severity == "info"
    assert black.action == "trim_border"


def test_an_ordinary_canvas_is_not_told_about_a_border_nobody_can_see():
    # Measured on real run_stack output: an undithered single field on the
    # reference canvas is already 3.1% empty (reprojection leaves a NaN margin a
    # couple of pixels wide), a dithered union canvas 5.1%, and a regular
    # 1x3 / 2x2 mosaic 4.1% / 3.1%. None of those is a black band.
    for share in (0.031, 0.051, 0.041):
        notes = stack_health(_run(coverage_min=0, coverage_max=30,
                                  coverage_thin_frac=0.0, uncovered_frac=share),
                             [_frame() for _ in range(10)])
        assert "uncovered" not in _kinds(notes), share


def test_a_run_recorded_before_the_empty_share_existed_stays_silent():
    """The column is NULL on every run the owner already has until the heal
    fills it in; "unknown" must never be read as "none"."""
    notes = stack_health(_run(coverage_min=0, coverage_max=30,
                              coverage_thin_frac=0.0, uncovered_frac=None),
                         [_frame() for _ in range(10)])
    assert "uncovered" not in _kinds(notes)


def test_a_shallow_stack_is_not_told_about_its_empty_canvas():
    # Same peak floor the thin note uses: below it the coverage distribution
    # isn't worth advising on yet.
    notes = stack_health(_run(coverage_min=0, coverage_max=3,
                              coverage_thin_frac=0.0, uncovered_frac=0.4),
                         [_frame() for _ in range(3)])
    assert "uncovered" not in _kinds(notes)


def test_a_ragged_mosaic_can_say_both_things_ranked_thin_first():
    """They are different facts about different pixels — noisy-but-covered edges
    and empty canvas — so a canvas with both keeps both, thin first."""
    notes = stack_health(_run(coverage_min=0, coverage_max=30,
                              coverage_thin_frac=0.4, uncovered_frac=0.3),
                         [_frame() for _ in range(10)])
    kinds = _kinds(notes)
    assert kinds.index("coverage") < kinds.index("uncovered")


def test_a_genuinely_ragged_mosaic_still_gets_the_note_and_says_how_much():
    # The 12/1/1-panel mosaic this was measured on: 62 % of the picture holds
    # under a quarter of the peak frame count.
    notes = stack_health(_run(coverage_min=0, coverage_max=13,
                              coverage_thin_frac=0.6176, is_mosaic=True),
                         [_frame() for _ in range(10)])
    trim = next(n for n in notes if n.kind == "coverage")
    assert trim.action == "trim_border"
    assert "62%" in trim.message
    solid = next((n for n in notes if n.kind == "solid"), None)
    assert solid is None or "even coverage" not in solid.message


def test_a_run_from_before_the_measure_says_nothing_either_way():
    # An older master (schema < 20) records no share. Neither the warning nor the
    # praise may be invented from the old proxy: it is known-wrong, so repeating
    # it for old runs would be knowingly repeating a false alarm.
    notes = stack_health(_run(coverage_min=1, coverage_max=128,
                              coverage_thin_frac=None),
                         [_frame() for _ in range(10)])
    assert "coverage" not in _kinds(notes)
    solid = next((n for n in notes if n.kind == "solid"), None)
    assert solid is None or "even coverage" not in solid.message


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
    notes = stack_health(_run(calstat=None, coverage_min=1, coverage_max=20,
                              coverage_thin_frac=0.4), frames)
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


def _solve_failed(**kw):
    """An accepted sub ASTAP *tried* and could not locate. A failed solve stamps
    ``solve_failed:`` and leaves ``accept`` alone, so this is what a real one looks
    like — and what tells it apart from a sub the solver hasn't reached yet."""
    return _frame(wcs=None, reason="solve_failed:no star match", **kw)


def test_mostly_unsolved_subs_leads_with_an_actionable_note():
    # A faint field where ASTAP solved only a handful of subs: the whole night
    # collapses to the located few, so the card leads with the highest-value fix.
    frames = [_frame(wcs="{}") for _ in range(20)]      # located
    frames += [_solve_failed() for _ in range(190)]     # tried, couldn't locate
    notes = stack_health(_run(), frames)
    assert notes[0].kind == "unsolved"
    assert notes[0].action == "solve_help"
    assert notes[0].severity == "info"
    assert "20 of 210" in notes[0].message
    assert "star database" in notes[0].message.lower()


def test_subs_the_solver_has_not_reached_yet_are_not_counted_as_failures():
    """D2: a scan ingests every new sub *before* any of them is solved, so an
    unlocated sub with no ``solve_failed:`` mark is pending, not a failure. Counting
    those made the note fire mid-pipeline on a healthy night — 84 of 120 "couldn't
    be located" — and point at a setup problem that does not exist."""
    frames = [_frame(wcs="{}") for _ in range(36)]      # solved so far
    frames += [_frame(wcs=None) for _ in range(84)]     # queued, not yet tried
    assert "unsolved" not in _kinds(stack_health(_run(), frames))

    # …and the note still fires once those same subs have actually been tried.
    tried = [_frame(wcs="{}") for _ in range(36)] + [_solve_failed() for _ in range(84)]
    notes = stack_health(_run(), tried)
    assert notes[0].kind == "unsolved"
    assert "36 of 120" in notes[0].message


def test_a_night_in_progress_counts_only_the_subs_already_tried():
    """The denominator is what the solver has finished with, so the ratio a
    beginner reads is the true failure rate — not one diluted by a queue."""
    frames = [_frame(wcs="{}") for _ in range(6)]       # located
    frames += [_solve_failed() for _ in range(6)]       # tried and failed
    frames += [_frame(wcs=None) for _ in range(300)]    # still queued
    notes = stack_health(_run(), frames)
    unsolved = next(n for n in notes if n.kind == "unsolved")
    assert "6 of 12" in unsolved.message
    assert "the other 6" in unsolved.message


def test_all_located_subs_get_no_unsolved_note():
    # Every accepted sub plate-solved → nothing to warn about.
    notes = stack_health(_run(), [_frame(wcs="{}") for _ in range(30)])
    assert "unsolved" not in _kinds(notes)


def test_a_few_unsolved_subs_below_the_fraction_stays_silent():
    # 2 of 20 unlocated (10%) is normal attrition, not a solve problem.
    frames = [_frame(wcs="{}") for _ in range(18)] + [_solve_failed() for _ in range(2)]
    notes = stack_health(_run(), frames)
    assert "unsolved" not in _kinds(notes)


def test_no_located_subs_stays_silent_solve_pending():
    # Zero located subs means plate-solve simply hasn't run yet (all accepted
    # frames have no WCS) — that's not a solve *failure* to report, so stay quiet.
    notes = stack_health(_run(), [_frame(wcs=None) for _ in range(30)])
    assert "unsolved" not in _kinds(notes)


def test_too_few_accepted_subs_no_unsolved_note():
    # Below the minimum tried count the fraction is meaningless (a tiny target),
    # so even a high unlocated share doesn't nag.
    frames = [_frame(wcs="{}") for _ in range(3)] + [_solve_failed() for _ in range(3)]
    notes = stack_health(_run(), frames)
    assert "unsolved" not in _kinds(notes)


def test_unsolved_note_ranks_before_calibration():
    # When both fire, the "most subs couldn't locate" fix outranks calibration —
    # it's the bigger lever on a thin faint-field result.
    frames = [_frame(wcs="{}") for _ in range(10)] + [_solve_failed() for _ in range(30)]
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


def test_roughly_aligned_note_fires_on_a_large_share():
    """A large share of contributing subs left only roughly aligned → a soft, no-
    gate note naming the soft-star cause."""
    notes = stack_health(
        _run(n_frames_used=100, n_roughly_aligned=40),
        [_frame() for _ in range(100)],
    )
    ra = next((n for n in notes if n.kind == "roughly_aligned"), None)
    assert ra is not None
    assert ra.severity == "info"
    assert "40 of 100" in ra.message
    assert "roughly aligned" in ra.message


def test_roughly_aligned_note_silent_below_the_fraction():
    # 1 of 100 (1%) is real but not worth a note (< 20% gate).
    notes = stack_health(
        _run(n_frames_used=100, n_roughly_aligned=1),
        [_frame() for _ in range(100)],
    )
    assert "roughly_aligned" not in _kinds(notes)


def test_roughly_aligned_note_silent_on_a_tiny_stack():
    # 3 of 5 is 60%, but a 5-sub stack is too small for the fraction to mean much.
    notes = stack_health(
        _run(n_frames_used=5, n_roughly_aligned=3),
        [_frame() for _ in range(5)],
    )
    assert "roughly_aligned" not in _kinds(notes)


def test_roughly_aligned_note_silent_when_null_or_zero():
    """Older runs / refine-off runs record NULL, and a refine run with nothing
    rough records 0 — both must stay silent (no note)."""
    for val in (None, 0):
        notes = stack_health(
            _run(n_frames_used=100, n_roughly_aligned=val),
            [_frame() for _ in range(100)],
        )
        assert "roughly_aligned" not in _kinds(notes)


def _fwhm_frame(fwhm: float | None, *, accept=True) -> FrameRow:
    return FrameRow(source_path=f"s{id(object())}.fit", accept=accept, fwhm_px=fwhm)


def test_soft_stars_note_fires_when_the_stack_is_bloated_vs_its_subs():
    """The finished stack's stars are materially fatter than the subs that made
    them → a soft, no-gate note pointing at registration smear."""
    # Subs median FWHM 3.0 px; stack FWHM 5.0 px → 1.67× ≥ 1.5× floor.
    frames = [_fwhm_frame(3.0) for _ in range(8)]
    notes = stack_health(_run(stack_fwhm_px=5.0), frames)
    sf = next((n for n in notes if n.kind == "soft_stars"), None)
    assert sf is not None
    assert sf.severity == "info"
    assert sf.action is None
    assert "fatter" in sf.message


def test_soft_stars_note_silent_when_the_stack_matches_its_subs():
    """A well-registered stack holds the subs' sharpness → no note."""
    frames = [_fwhm_frame(3.0) for _ in range(8)]
    notes = stack_health(_run(stack_fwhm_px=3.1), frames)  # 1.03× < 1.5×
    assert "soft_stars" not in _kinds(notes)


def test_soft_stars_note_silent_when_the_stack_fwhm_is_missing():
    """Old runs / too-few-stars record NULL stack_fwhm_px → stay silent."""
    frames = [_fwhm_frame(3.0) for _ in range(8)]
    notes = stack_health(_run(stack_fwhm_px=None), frames)
    assert "soft_stars" not in _kinds(notes)


def test_soft_stars_note_silent_with_too_few_sub_fwhm_measurements():
    """Fewer than the minimum subs recorded a FWHM → no meaningful median, so no
    note even if the one measured sub is much sharper than the stack."""
    frames = [_fwhm_frame(3.0) for _ in range(4)] + [_fwhm_frame(None) for _ in range(4)]
    notes = stack_health(_run(stack_fwhm_px=6.0), frames)
    assert "soft_stars" not in _kinds(notes)


def test_soft_stars_note_ignores_rejected_subs_for_the_sub_median():
    """Only accepted subs anchor the comparison — a rejected soft sub must not
    inflate the sub median and mask real bloat."""
    # Accepted subs are sharp (2.0 px); a rejected 8.0 px sub must be ignored, so
    # the stack at 3.5 px is 1.75× the accepted median → note fires.
    frames = [_fwhm_frame(2.0) for _ in range(6)]
    frames += [_fwhm_frame(8.0, accept=False) for _ in range(3)]
    notes = stack_health(_run(stack_fwhm_px=3.5), frames)
    assert "soft_stars" in _kinds(notes)


# ---------------------------------------------------------------------------
# κ-σ couldn't bite at this frame count (a lone trail survived, silently).
# ---------------------------------------------------------------------------

def _note(notes, kind):
    return next((n for n in notes if n.kind == kind), None)


def test_rejection_blind_note_fires_on_a_small_sigma_clip_stack():
    """At n=5 a lone outlier's z-score against stats that include it is 4/√5 ≈
    1.79 — below κ=3 — so the two-pass clip provably removed nothing, and the
    satellite trail is in the picture with nothing else saying so."""
    notes = stack_health(
        _run(n_frames_used=5, rejection_mode="sigma-clip", rejection_fraction=0.0,
             options_json='{"sigma_clip": true, "sigma_kappa": 3.0}'),
        [_frame() for _ in range(5)],
    )
    note = _note(notes, "rejection_blind")
    assert note is not None
    assert "5 subs" in note.message
    assert "11 frames" in note.message      # the honest κ-effective threshold
    assert "Auto outlier removal" in note.message
    assert note.action == "restack"
    assert note.severity == "info"          # a nudge, never alarming


def test_rejection_blind_note_silent_once_kappa_sigma_can_actually_clip():
    notes = stack_health(
        _run(n_frames_used=40, rejection_mode="sigma-clip", rejection_fraction=0.002,
             options_json='{"sigma_clip": true, "sigma_kappa": 3.0}'),
        [_frame() for _ in range(40)],
    )
    assert "rejection_blind" not in _kinds(notes)


def test_rejection_blind_note_silent_at_exactly_the_threshold():
    """11 frames is the first count where κ=3 can reject, so it must not fire."""
    notes = stack_health(
        _run(n_frames_used=11, rejection_mode="sigma-clip",
             options_json='{"sigma_kappa": 3.0}'),
        [_frame() for _ in range(11)],
    )
    assert "rejection_blind" not in _kinds(notes)


def test_rejection_blind_note_silent_when_min_max_was_used():
    """An auto-picked small stack uses the order-statistic drop, which *does*
    work at n=5 — there is nothing to warn about."""
    notes = stack_health(
        _run(n_frames_used=5, rejection_mode="min-max-reject",
             options_json='{"auto_reject": true, "min_max_reject": true}'),
        [_frame() for _ in range(5)],
    )
    assert "rejection_blind" not in _kinds(notes)


def test_rejection_blind_note_fires_on_a_shallow_mosaic_that_clears_the_count():
    """Audit finding A6, the after-the-fact half. A 2×2 mosaic three subs deep
    holds twelve frames — past the κ=3 threshold of 11 — so the note stayed
    silent, while every pixel on the canvas saw only three samples and the κ-σ
    pass clipped nothing (``REJFRAC 0.0``). The peak per-pixel coverage is the
    honest depth: when even the *best*-covered pixel is below the threshold, no
    pixel anywhere could have been clipped."""
    notes = stack_health(
        _run(n_frames_used=12, coverage_min=3, coverage_max=3, is_mosaic=True,
             rejection_mode="sigma-clip", rejection_fraction=0.0,
             options_json='{"sigma_clip": true, "sigma_kappa": 3.0}'),
        [_frame() for _ in range(12)],
    )
    note = _note(notes, "rejection_blind")
    assert note is not None
    # ...and it names the count the user can act on, not the target's total —
    # "with only 12 subs" beside a 12-sub badge reads as nonsense.
    assert "3 subs overlapping at any one spot" in note.message
    assert "11 frames" in note.message
    assert note.action == "restack"


def test_rejection_blind_note_silent_on_a_mosaic_whose_panels_are_deep_enough():
    """The other direction: a mosaic whose thinnest overlap still clears the
    threshold is genuinely protected, so nothing fires."""
    notes = stack_health(
        _run(n_frames_used=400, coverage_min=20, coverage_max=60, is_mosaic=True,
             rejection_mode="sigma-clip", rejection_fraction=0.003,
             options_json='{"sigma_clip": true, "sigma_kappa": 3.0}'),
        [_frame() for _ in range(40)],
    )
    assert "rejection_blind" not in _kinds(notes)


def test_rejection_blind_note_fires_on_a_drizzle_run_too_thin_to_clip():
    """This used to be ``…_silent_on_a_drizzle_run``, which pinned the defect:
    drizzle's two-pass rejection is the same κ·σ clip with the same κ, so a
    5-sub drizzled run stamps ``REJMODE = drizzle-reject`` and ``REJFRAC 0.0``
    while the trail stays in the picture. Measured, not argued — see
    ``tests/test_drizzle_reject.py``'s depth sweep."""
    notes = stack_health(
        _run(n_frames_used=5, coverage_min=5, coverage_max=5,
             rejection_mode="drizzle-reject", rejection_fraction=0.0,
             options_json='{"drizzle": true, "drizzle_reject": true,'
                          ' "sigma_kappa": 3.0}'),
        [_frame() for _ in range(5)],
    )
    note = _note(notes, "rejection_blind")
    assert note is not None
    assert "drizzle's own outlier removal" in note.message
    assert "11 frames" in note.message
    # The cure differs: "Auto outlier removal" alone is a no-op while drizzle is
    # on, so the note must not offer it as the fix on its own.
    assert "More subs" in note.message
    assert "drizzle off" in note.message
    assert note.action == "restack"


def test_rejection_blind_note_silent_on_a_deep_enough_drizzle_run():
    """The other direction, so the new branch cannot become a standing lecture:
    once the clip can bite, nothing fires."""
    notes = stack_health(
        _run(n_frames_used=40, coverage_min=30, coverage_max=40,
             rejection_mode="drizzle-reject", rejection_fraction=0.002,
             options_json='{"drizzle": true, "drizzle_reject": true,'
                          ' "sigma_kappa": 3.0}'),
        [_frame() for _ in range(40)],
    )
    assert "rejection_blind" not in _kinds(notes)


def test_rejection_blind_note_fires_on_a_drizzled_mosaic_deep_by_frame_count():
    """The owner's own shape, and the reason this branch is worth having: four
    panels, 40 subs — comfortably past 11 — but only ten land on any one spot,
    so no pixel on the canvas could be clipped."""
    notes = stack_health(
        _run(n_frames_used=40, coverage_min=8, coverage_max=10, is_mosaic=True,
             rejection_mode="drizzle-reject", rejection_fraction=0.0,
             options_json='{"drizzle": true, "drizzle_reject": true,'
                          ' "sigma_kappa": 3.0}'),
        [_frame() for _ in range(40)],
    )
    note = _note(notes, "rejection_blind")
    assert note is not None
    assert "10 subs overlapping at any one spot" in note.message


def test_rejection_blind_note_leaves_min_max_alone():
    """A min/max drop is an order statistic, not a κ·σ clip — it removes an
    extreme from 3 subs up, so widening the note to drizzle must not have
    swept it in as well."""
    notes = stack_health(
        _run(n_frames_used=5, coverage_min=5, coverage_max=5,
             rejection_mode="min-max-reject",
             options_json='{"min_max_reject": true}'),
        [_frame() for _ in range(5)],
    )
    assert "rejection_blind" not in _kinds(notes)


def test_rejection_blind_note_fires_when_min_max_had_nothing_to_spare():
    """min/max has a floor of its own, and it is a **per-pixel** one: the
    accumulator drops nothing where fewer than three subs reached the pixel
    (``test_min_max_reject_small_coverage_falls_back_to_mean`` pins that — two
    samples come out as their plain mean, outlier included). So a run can record
    ``REJMODE = min-max-reject`` while no pixel on the canvas was trimmed at all,
    and the reassurance below used to promise, of that same picture, that a lone
    trail "can't show up in your final image"."""
    notes = stack_health(
        _run(n_frames_used=8, coverage_min=1, coverage_max=2, is_mosaic=True,
             coverage_median_depth=2.0, rejection_mode="min-max-reject",
             rejection_fraction=0.0,
             options_json='{"auto_reject": true, "min_max_reject": true}'),
        [_frame() for _ in range(8)],
    )
    note = _note(notes, "rejection_blind")
    assert note is not None
    assert "2 subs overlapping at any one spot" in note.message
    # The floor named is min/max's own order-statistic one, never κ-σ's 11.
    assert "3 subs on a pixel" in note.message
    assert "11" not in note.message
    # No switch helps here, so the note offers no re-stack action and no knob.
    assert note.action is None
    assert "Auto outlier removal" not in note.message
    # …and the praise stands down rather than contradicting it.
    assert "rejection" not in _kinds(notes)


def test_rejection_blind_note_fires_where_half_a_mosaic_is_under_the_min_max_floor():
    """The reachable shape: a mosaic part-way through its panels. The overlaps
    clear the floor, so the *peak* says nothing is wrong — but over at least half
    the canvas only two subs landed, and there min/max averaged the trail in."""
    notes = stack_health(
        _run(n_frames_used=20, coverage_min=1, coverage_max=8, is_mosaic=True,
             coverage_median_depth=2.0, rejection_mode="min-max-reject",
             rejection_fraction=0.05,
             options_json='{"auto_reject": true, "min_max_reject": true}'),
        [_frame() for _ in range(20)],
    )
    note = _note(notes, "rejection_blind")
    assert note is not None
    assert "Over at least half of this picture no more than 2 subs" in note.message
    assert "couldn't drop anything there" in note.message
    assert "rejection" not in _kinds(notes)


def test_min_max_praise_survives_a_stack_that_really_was_trimmed():
    """The control, and the half that must not change: a min/max run whose
    pixels are genuinely deep enough keeps its reassurance and stays silent."""
    notes = stack_health(
        _run(n_frames_used=6, coverage_min=6, coverage_max=6,
             coverage_median_depth=6.0, rejection_mode="min-max-reject",
             rejection_fraction=0.3,
             options_json='{"auto_reject": true, "min_max_reject": true}'),
        [_frame() for _ in range(6)],
    )
    assert "rejection_blind" not in _kinds(notes)
    assert "brightest and darkest" in _note(notes, "rejection").message


def test_min_max_blind_note_stays_silent_on_a_run_with_no_coverage_recorded():
    """An older run records no median and a zero peak, so the depth falls back to
    the frame count — which for min/max is three or more by construction
    (``combine_method`` will not dispatch it below that). Nothing fires, i.e. the
    upgrade adds notes only where the stored map proves one."""
    notes = stack_health(
        _run(n_frames_used=5, coverage_min=0, coverage_max=0,
             coverage_median_depth=None, rejection_mode="min-max-reject",
             options_json='{"min_max_reject": true}'),
        [_frame() for _ in range(5)],
    )
    assert "rejection_blind" not in _kinds(notes)
    assert _note(notes, "rejection") is not None


def test_rejection_blind_note_silent_when_no_rejection_pass_was_recorded():
    """An old run (pre-schema-10) records no mode; we can't claim what its
    rejection did or didn't do, so say nothing rather than guess."""
    notes = stack_health(
        _run(n_frames_used=5, rejection_mode=None),
        [_frame() for _ in range(5)],
    )
    assert "rejection_blind" not in _kinds(notes)


def test_rejection_blind_note_uses_the_run_s_own_kappa():
    """A looser κ crosses over sooner, so the threshold — and whether the note
    fires at all — must come from the run's stored κ, not a hard-coded 11."""
    loose = dict(n_frames_used=8, rejection_mode="sigma-clip")
    # κ=2 crosses over at 7 frames, so 8 subs is genuinely fine.
    quiet = stack_health(_run(**loose, options_json='{"sigma_kappa": 2.0}'),
                         [_frame() for _ in range(8)])
    assert "rejection_blind" not in _kinds(quiet)
    # The same 8-sub stack at the default κ=3 (threshold 11) still can't clip.
    loud = stack_health(_run(**loose, options_json='{"sigma_kappa": 3.0}'),
                        [_frame() for _ in range(8)])
    assert _note(loud, "rejection_blind") is not None


def test_rejection_blind_note_falls_back_to_the_default_kappa():
    """A garbled/absent options_json shouldn't silence a real warning — every
    shipped default has used κ=3, so assume it."""
    for bad in ("", "not json", "[]", '{"sigma_kappa": null}',
                '{"sigma_kappa": 0}'):
        notes = stack_health(
            _run(n_frames_used=4, rejection_mode="sigma-clip", options_json=bad),
            [_frame() for _ in range(4)],
        )
        assert _note(notes, "rejection_blind") is not None, bad


def test_rejection_blind_note_singularises_a_one_sub_stack():
    note = _note(stack_health(
        _run(n_frames_used=1, rejection_mode="sigma-clip"), [_frame()]),
        "rejection_blind")
    assert note is not None and "1 sub," in note.message


def test_rejection_blind_note_ranks_below_the_calibration_next_step():
    """Calibration is still the bigger lever; the card shows two notes, so this
    must not displace it."""
    notes = stack_health(
        _run(n_frames_used=5, rejection_mode="sigma-clip", calstat=None),
        [_frame() for _ in range(5)],
    )
    kinds = _kinds(notes)
    assert kinds.index("calibration") < kinds.index("rejection_blind")


# ---- mosaic panel seams ---------------------------------------------------

def test_a_mosaic_whose_panels_evened_out_says_so():
    """The reassurance half: a measured seam step well inside the picture's own
    grain means the joins matched, and saying so is the whole point of measuring
    it — the owner had to spot the *broken* case by eye because nothing ever
    reported the good one either."""
    note = _note(stack_health(_run(is_mosaic=True, seam_residual=0.12),
                              [_frame() for _ in range(20)]), "seams_flat")
    assert note is not None
    assert note.severity == "good"
    assert "seams" in note.message
    assert _note(stack_health(_run(is_mosaic=True, seam_residual=0.12),
                              [_frame()]), "seams") is None


def test_a_mosaic_with_a_surviving_panel_step_is_named_in_plain_words():
    """The failure this exists to catch: a coherent sky step across the joins,
    several times the grain, which shows as a seam grid once stretched."""
    note = _note(stack_health(_run(is_mosaic=True, seam_residual=2.6),
                              [_frame() for _ in range(20)]), "seams")
    assert note is not None
    assert note.severity == "info"          # never alarming
    assert "2.6" in note.message            # the measured figure, said out loud
    assert "seams" in note.message
    # and it must not simultaneously claim the panels evened out
    assert _note(stack_health(_run(is_mosaic=True, seam_residual=2.6),
                              [_frame()]), "seams_flat") is None


def test_the_seam_warning_hands_over_the_tool_it_names():
    """The note's advice ends at "the editor's background tools can even it out
    further" — advice with nowhere to click. Every other actionable note carries
    an ``action`` key the card turns into a one-click link, and this one must too,
    or the beginner is told a tool exists and left to find it."""
    note = _note(stack_health(_run(is_mosaic=True, seam_residual=2.6),
                              [_frame() for _ in range(20)]), "seams")
    assert note is not None
    assert note.action == "background"
    # The reassurance half has nothing to do, so it stays a bare sentence.
    flat = _note(stack_health(_run(is_mosaic=True, seam_residual=0.12),
                              [_frame() for _ in range(20)]), "seams_flat")
    assert flat is not None and flat.action is None


def test_an_ambiguous_seam_measurement_says_nothing_either_way():
    """Real large-scale structure crossing panels puts a floor under the
    measurement that has nothing to do with seams, so a middling number is
    genuinely ambiguous — neither claim would be honest."""
    notes = stack_health(_run(is_mosaic=True, seam_residual=1.2),
                         [_frame() for _ in range(20)])
    assert _note(notes, "seams") is None
    assert _note(notes, "seams_flat") is None


def test_a_single_field_stack_never_mentions_seams():
    """A single-field stack has one coverage level and therefore no joins to
    compare, so the stacker records NULL — both notes self-hide by construction,
    exactly as they do for runs made before this was measured."""
    notes = stack_health(_run(seam_residual=None), [_frame() for _ in range(20)])
    assert _note(notes, "seams") is None
    assert _note(notes, "seams_flat") is None


def test_a_non_finite_seam_measurement_is_ignored():
    """A NaN/inf can only come from a broken measurement; say nothing rather
    than render "nan× the grain"."""
    for bad in (float("nan"), float("inf"), float("-inf")):
        notes = stack_health(_run(is_mosaic=True, seam_residual=bad), [_frame()])
        assert _note(notes, "seams") is None
        assert _note(notes, "seams_flat") is None


def test_the_seam_warning_ranks_below_the_actionable_next_steps():
    """It's a "worth a look" observation, not the biggest lever — calibration
    and the unlocatable-subs note still lead, since the card shows only two."""
    notes = stack_health(
        _run(is_mosaic=True, seam_residual=3.0, calstat=None),
        [_frame() for _ in range(20)],
    )
    kinds = _kinds(notes)
    assert kinds.index("calibration") < kinds.index("seams")


# ---- which scale a stored seam figure is on -------------------------------
# v0.313.1 changed what ``seam_residual`` *means* (it stopped charging each
# coverage level's own estimation noise to the seam) and no stored row was ever
# re-measured, so a library that has been shooting for a while holds both scales
# at once and the same two thresholds are being read against two different
# quantities. Measured on the owner's own library: of 38 pairs of runs whose
# inputs are byte-identical, every one reads lower after the fix, and **25 of
# them change the displayed verdict** — 20 of those off "check".

def test_a_seam_figure_from_before_the_estimator_fix_is_not_read_as_a_warning():
    """The one that reaches the owner: an old run's "check" is a claim about a
    picture that today's estimator may not make at all, printed beside a frame
    count identical to the new run's — and on Compare it becomes a sentence
    about one of the two stacks of the same files."""
    old = _run(is_mosaic=True, seam_residual=2.4, engine_version="0.287.2")
    notes = stack_health(old, [_frame() for _ in range(20)])
    assert _note(notes, "seams") is None
    # …and it does not flip to the compliment either. Silence is the answer the
    # ambiguous middle band already uses; a second kind of "we don't know" would
    # be a new thing for a reader to learn.
    assert _note(notes, "seams_flat") is None


def test_an_old_run_whose_panels_matched_keeps_its_compliment():
    """The half that must NOT be withdrawn, and the reason this is a reading rule
    rather than a blanket silence. The fix can only ever move a figure *down*
    (``se >= 0`` on both ends of the max−min, over an unchanged yardstick), so a
    figure already below the "flat" bar is still below it however it is
    re-measured — the compliment is honest without reading a pixel."""
    old = _run(is_mosaic=True, seam_residual=0.12, engine_version="0.287.2")
    note = _note(stack_health(old, [_frame() for _ in range(20)]), "seams_flat")
    assert note is not None


def test_a_run_stacked_since_the_fix_is_read_exactly_as_before():
    """The common case, and the one that must not move: a figure on today's
    scale is read by today's thresholds, unchanged."""
    fresh = _run(is_mosaic=True, seam_residual=2.4, engine_version="0.401.1")
    note = _note(stack_health(fresh, [_frame() for _ in range(20)]), "seams")
    assert note is not None
    assert "2.4" in note.message


def test_a_re_measured_figure_is_believed_whatever_stacked_the_run():
    """``engine_version`` dates the *stack*; ``seam_scale`` dates the *figure*.
    They differ for exactly the runs the heal has touched — an old mosaic whose
    joins were measured from the master it already wrote — and the figure's own
    stamp has to win, or healing one would achieve nothing."""
    healed = _run(is_mosaic=True, seam_residual=2.4,
                  engine_version="0.287.2", seam_scale=2)
    note = _note(stack_health(healed, [_frame() for _ in range(20)]), "seams")
    assert note is not None


def test_a_figure_nobody_can_date_is_read_on_the_safe_side():
    """A run from before the version column, and a version string this cannot
    read, are both "we don't know which estimator wrote this" — which has one
    safe answer and it is not "warn them"."""
    for version in (None, "", "dev", "0.313.1-rc1"):
        undated = _run(is_mosaic=True, seam_residual=2.4,
                       engine_version=version)
        notes = stack_health(undated, [_frame() for _ in range(20)])
        assert _note(notes, "seams") is None, version
        # The compliment still survives, on the same one-sided argument.
        flat = _run(is_mosaic=True, seam_residual=0.12, engine_version=version)
        assert _note(stack_health(flat, [_frame() for _ in range(20)]),
                     "seams_flat") is not None, version


def test_the_scale_boundary_is_the_release_that_moved_the_number():
    """Pinned as a version comparison, not a string one: 0.313.1 is current and
    0.313.0 is not, and a two-part or four-part version still orders."""
    assert seam_scale_is_current(None, "0.313.1")
    assert seam_scale_is_current(None, "0.313.2")
    assert seam_scale_is_current(None, "0.446.4")
    assert seam_scale_is_current(None, "1.0.0")
    assert not seam_scale_is_current(None, "0.313.0")
    assert not seam_scale_is_current(None, "0.312.9")
    assert not seam_scale_is_current(None, "0.287.2")
    assert not seam_scale_is_current(None, "0.99.99")
    # A recorded generation wins outright, either way.
    assert seam_scale_is_current(2, "0.287.2")
    assert not seam_scale_is_current(1, "0.446.4")
    assert seam_scale_is_current(3, None)      # a future generation is not older


def test_the_reading_rule_is_the_same_one_every_surface_uses():
    """The chip, the Gallery card and the health note all resolve through this,
    so the rule is stated once. Asserted directly so a caller that starts
    re-typing it is a failing test rather than a second opinion."""
    assert stored_seam_verdict(2.4, None, "0.287.2") is None
    assert stored_seam_verdict(2.4, None, "0.401.1") == "check"
    assert stored_seam_verdict(0.3, None, "0.287.2") == "flat"
    assert stored_seam_verdict(1.2, None, "0.287.2") is None   # already silent
    assert stored_seam_verdict(None, None, "0.287.2") is None


# --- "did the stack get what its subs should have bought?" (√N yardstick) -----
# The judgement itself is `noise_vs_expected`, shared with the "One frame vs your
# stack" card so the two surfaces can never describe the same stack differently;
# the 0.7 factor under it is measured against the real estimator in
# tests/test_noise_ratio_expectation.py.

def test_noise_vs_expected_reads_a_healthy_stack_as_expected():
    import math

    from seestack.stackhealth import noise_vs_expected

    # An ideal 100-sub stack measures ~√100 = 10×.
    assert noise_vs_expected(10.0, 100) == "expected"
    # …and anything at or above 0.7·√N is still "expected", boundary included.
    assert noise_vs_expected(0.7 * math.sqrt(100), 100) == "expected"
    assert noise_vs_expected(0.7 * math.sqrt(100) - 1e-6, 100) == "low"


def test_noise_vs_expected_is_silent_without_something_honest_to_say():
    from seestack.stackhealth import NOISE_EXPECTED_MIN_FRAMES, noise_vs_expected

    assert noise_vs_expected(None, 100) is None          # never measured
    assert noise_vs_expected(float("nan"), 100) is None  # unmeasurable image
    assert noise_vs_expected(0.0, 100) is None
    assert noise_vs_expected(-2.0, 100) is None
    assert noise_vs_expected(5.0, None) is None
    # Below the floor √N is meaningless — one unlucky reference sub swings the
    # ratio more than the physics does, so we judge nothing.
    assert noise_vs_expected(1.0, NOISE_EXPECTED_MIN_FRAMES - 1) is None
    assert noise_vs_expected(1.0, NOISE_EXPECTED_MIN_FRAMES) == "low"


def test_underperforming_stack_gets_the_note_on_the_health_card():
    """The whole point of the move: this warning used to live only behind the
    History page's collapsed "See the difference" reveal, which the person who
    needs it never opens."""
    frames = [_frame() for _ in range(40)]
    notes = stack_health(_run(n_frames_used=100), frames, noise_ratio=4.0)
    assert "noise_low" in _kinds(notes)
    msg = next(n.message for n in notes if n.kind == "noise_low")
    assert "100 subs should cut the background noise about 10×" in msg
    assert "nearer 4×" in msg
    # Gentle: it suggests a cause, never asserts a fault, and offers no action
    # button (there is nothing to press — the fix is on the next clear night).
    assert "usually means" in msg
    assert next(n for n in notes if n.kind == "noise_low").action is None


def test_a_healthy_stack_gets_no_underperformance_note():
    frames = [_frame() for _ in range(40)]
    assert "noise_low" not in _kinds(
        stack_health(_run(n_frames_used=100), frames, noise_ratio=10.0))


def test_the_note_self_hides_with_no_stamped_measurement():
    """A Target page view must never trigger a measurement, so a run nothing has
    measured yet simply says nothing — the default for every existing run."""
    frames = [_frame() for _ in range(40)]
    assert "noise_low" not in _kinds(stack_health(_run(n_frames_used=100), frames))
    assert "noise_low" not in _kinds(
        stack_health(_run(n_frames_used=100), frames, noise_ratio=None))


def test_the_note_ranks_below_a_concrete_cause():
    """When something names *why* the stack underperformed, that is the better
    advice — the yardstick note is what to show when nothing else explains it."""
    frames = [_frame() for _ in range(40)]
    run = _run(n_frames_used=100, n_roughly_aligned=40)
    kinds = _kinds(stack_health(run, frames, noise_ratio=4.0))
    assert kinds.index("roughly_aligned") < kinds.index("noise_low")


def test_a_small_stack_is_never_judged_by_the_yardstick():
    frames = [_frame() for _ in range(5)]
    assert "noise_low" not in _kinds(
        stack_health(_run(n_frames_used=6, coverage_min=6, coverage_max=6),
                     frames, noise_ratio=1.0))


def test_a_mosaic_is_never_judged_against_its_whole_frame_count():
    """The ratio is measured over a *central crop* of the master, and on a mosaic
    canvas no pixel there ever saw more than its own panel's subs — while
    n_frames_used counts the whole target's. A four-panel mosaic 100 subs deep
    per panel achieves ~√100 = 10× and would be asked for √400 = 20×, so it reads
    "low" at every depth however well it was shot. The owner shoots mosaics, and
    a wrong "your picture underperformed" is far worse than saying nothing."""
    from seestack.stackhealth import noise_vs_expected

    # The exact shape above: healthy per panel, "low" against the target total.
    assert noise_vs_expected(10.0, 400) == "low"          # the false alarm…
    assert noise_vs_expected(10.0, 400, is_mosaic=True) is None   # …suppressed
    # The reassurance is withheld too — the same denominator is behind it.
    assert noise_vs_expected(20.0, 400, is_mosaic=True) is None
    # A single field is unaffected.
    assert noise_vs_expected(20.0, 400, is_mosaic=False) == "expected"
    assert noise_vs_expected(20.0, 400) == "expected"
    # A run stacked before the flag existed (schema < 8) withholds too: "might be
    # a mosaic" is not a licence to accuse it.
    assert noise_vs_expected(20.0, 400, is_mosaic=None) is None
    assert noise_vs_expected(10.0, 400, is_mosaic=None) is None


def test_the_health_note_stays_off_a_mosaic():
    frames = [_frame() for _ in range(40)]
    mosaic = _run(n_frames_used=400, is_mosaic=True, coverage_min=1, coverage_max=100)
    assert "noise_low" not in _kinds(stack_health(mosaic, frames, noise_ratio=10.0))
    # …and the identical run as a single field still gets the nudge, so the
    # suppression is the mosaic flag and nothing else.
    single = _run(n_frames_used=400, is_mosaic=False, coverage_min=1, coverage_max=100)
    assert "noise_low" in _kinds(stack_health(single, frames, noise_ratio=10.0))


# --- the honest mosaic yardstick: the depth at the crop the ratio came from ---
# v0.331.2 fixed the mosaic false alarm by *silence*, because nothing recorded
# how deep the measured crop actually was. Now something does, so a mosaic is
# judged rather than skipped — against its own panel depth, never the target's
# whole frame count.

def test_a_mosaic_is_judged_against_the_depth_at_the_measured_crop():
    """The exact shape of the false alarm, now answered rather than dodged: a
    four-panel mosaic 100 subs deep per panel achieves ~√100 = 10×, which is
    healthy for the pixels the ratio was measured over — even though the run
    used 400 frames."""
    from seestack.stackhealth import noise_vs_expected

    assert noise_vs_expected(10.0, 400) == "low"                  # the alarm…
    assert noise_vs_expected(10.0, 400, is_mosaic=True) is None    # …silenced…
    # …and now answered honestly, in both directions.
    assert noise_vs_expected(10.0, 400, is_mosaic=True, crop_depth=100) \
        == "expected"
    assert noise_vs_expected(4.0, 400, is_mosaic=True, crop_depth=100) == "low"


def test_the_mosaic_yardstick_is_the_crop_depth_not_the_whole_count():
    """The number the sentence may name. Getting this wrong is how the false
    alarm came back in v0.331.2's predecessor."""
    from seestack.stackhealth import noise_yardstick_frames

    assert noise_yardstick_frames(400, True, 100) == 100
    # A single field's every pixel saw every frame, so the run's own count is
    # the honest one — and a stray crop depth may not quietly re-grade it.
    assert noise_yardstick_frames(400, False, 100) == 400
    assert noise_yardstick_frames(400, False) == 400


def test_a_mosaic_with_no_measured_crop_depth_stays_silent():
    """Every way the depth can be unavailable — an older run, a tidied output
    dir, an unreadable sibling — must leave the mosaic exactly as quiet as it is
    today. Being told a healthy picture underperformed is the expensive error."""
    from seestack.stackhealth import noise_vs_expected, noise_yardstick_frames

    assert noise_vs_expected(10.0, 400, is_mosaic=True, crop_depth=None) is None
    assert noise_vs_expected(20.0, 400, is_mosaic=True, crop_depth=None) is None
    assert noise_yardstick_frames(400, True, None) is None
    # A nonsense depth is "unknown", not "zero subs deep".
    assert noise_yardstick_frames(400, True, 0) is None
    assert noise_yardstick_frames(400, True, -3) is None
    assert noise_yardstick_frames(400, True, "deep") is None
    # An unclassified run (schema < 8) still withholds, depth or no depth.
    assert noise_yardstick_frames(400, None, 100) is None
    assert noise_vs_expected(10.0, 400, is_mosaic=None, crop_depth=100) is None


def test_a_thin_mosaic_panel_is_below_the_floor_like_any_other_stack():
    """√N means nothing under the floor whichever count supplied the N — a
    3-sub panel of a 400-frame mosaic is judged no more than a 3-sub stack."""
    from seestack.stackhealth import NOISE_EXPECTED_MIN_FRAMES, noise_vs_expected

    thin = NOISE_EXPECTED_MIN_FRAMES - 1
    assert noise_vs_expected(1.0, 400, is_mosaic=True, crop_depth=thin) is None
    assert noise_vs_expected(1.0, 400, is_mosaic=True,
                             crop_depth=NOISE_EXPECTED_MIN_FRAMES) == "low"


def test_the_mosaic_health_note_names_the_panel_depth_not_the_target_total():
    """A mosaic that really did underperform now gets the note — and the
    sentence says "the middle of this mosaic", because "400 subs should give
    20×" is simply not a claim about a panel."""
    frames = [_frame() for _ in range(40)]
    mosaic = _run(n_frames_used=400, is_mosaic=True,
                  coverage_min=1, coverage_max=100)
    notes = stack_health(mosaic, frames, noise_ratio=4.0, noise_crop_depth=100)
    msg = next((n.message for n in notes if n.kind == "noise_low"), None)
    assert msg is not None
    assert "About 100 subs cover the middle of this mosaic" in msg
    assert "about 10× (√100)" in msg
    assert "nearer 4×" in msg
    # The whole target's count must not appear anywhere in the sentence.
    assert "400" not in msg
    # Still a suggestion with nothing to press, like the single-field note.
    assert "usually means" in msg
    assert next(n for n in notes if n.kind == "noise_low").action is None


def test_a_healthy_mosaic_gets_no_note_now_that_it_can_be_judged():
    """The direction that matters most: measuring the depth must not turn the
    suppression into a warning. 10× on 100-deep panels is healthy."""
    frames = [_frame() for _ in range(40)]
    mosaic = _run(n_frames_used=400, is_mosaic=True,
                  coverage_min=1, coverage_max=100)
    assert "noise_low" not in _kinds(
        stack_health(mosaic, frames, noise_ratio=10.0, noise_crop_depth=100))


def test_a_single_field_note_is_untouched_by_the_new_argument():
    """Upgrade safety, stated as a test: a crop depth may never change what a
    single-field stack is told, however far it is from the frame count."""
    frames = [_frame() for _ in range(40)]
    single = _run(n_frames_used=100, is_mosaic=False)
    plain = stack_health(single, frames, noise_ratio=4.0)
    withdepth = stack_health(single, frames, noise_ratio=4.0,
                             noise_crop_depth=9)
    assert [(n.kind, n.message) for n in plain] == \
        [(n.kind, n.message) for n in withdepth]
    assert "100 subs should cut the background noise about 10×" in \
        next(n.message for n in plain if n.kind == "noise_low")


# --- what "thin coverage" is measured against (v0.389.2) ---------------------
#
# The share this note fires on was measured against the coverage map's *peak*
# until v0.389.2. On a tiled mosaic the peak is where panels overlap, so ordinary
# panel interiors counted as a ragged border and the panel told a mosaic owner
# that most of his picture was one — offering a "Trim border" that, post-D1,
# keeps the whole canvas. The measure now uses the same panel-depth reference the
# trim does, so the note and its action cannot disagree.


def _mosaic_coverage(rows: int, cols: int, depths, panel: int = 120,
                     overlap: float = 0.10):
    import numpy as np

    step = int(round(panel * (1.0 - overlap)))
    cov = np.zeros((step * (rows - 1) + panel, step * (cols - 1) + panel))
    for r in range(rows):
        for c in range(cols):
            cov[r * step:r * step + panel,
                c * step:c * step + panel] += float(depths[(r, c)])
    return cov


def test_no_ragged_border_note_on_a_mosaic_whose_panels_are_simply_panels():
    """End to end through the real measure, on the shape the owner shoots: a 2×2
    mosaic at 6/6/6/3 subs. Fails before — it reported 22 % "thin" and offered a
    trim that keeps 92 % of the canvas, i.e. does nothing about what it
    described."""
    from seestack.stack.stacker import coverage_thin_fraction

    cov = _mosaic_coverage(2, 2, {(0, 0): 6, (0, 1): 6, (1, 0): 6, (1, 1): 3})
    notes = stack_health(
        _run(n_frames_used=21, is_mosaic=True, coverage_min=3, coverage_max=21,
             coverage_thin_frac=coverage_thin_fraction(cov)),
        [_frame() for _ in range(21)],
    )
    assert "coverage" not in _kinds(notes)
    assert not any(n.action == "trim_border" for n in notes)
    # …and it is praised for what it is, rather than warned about.
    assert "even coverage" in _note(notes, "solid").message


def test_a_real_ragged_border_still_gets_the_note_and_the_trim():
    """The measure is not simply quieter: a genuine thin edge still fires, and
    the note now says edge rather than "the best-covered part"."""
    notes = stack_health(
        _run(coverage_thin_frac=0.18, coverage_max=30),
        [_frame() for _ in range(30)],
    )
    note = _note(notes, "coverage")
    assert note is not None
    assert "18%" in note.message and "thin edge" in note.message
    assert note.action == "trim_border"


# --- κ-σ's reach on a mosaic, judged on the depth half the picture is at ------


def test_rejection_blind_note_fires_where_half_a_mosaic_is_below_the_threshold():
    """The other half of A6. ``coverage_max`` is the corner where four panels
    meet, so a 2×2 three subs deep with a 12-deep overlap corner cleared the κ=3
    threshold of 11 and the note stayed silent — while κ-σ was blind over
    essentially the whole canvas. Fails before: no note at all."""
    notes = stack_health(
        _run(n_frames_used=12, coverage_min=3, coverage_max=12, is_mosaic=True,
             coverage_median_depth=3.0, rejection_mode="sigma-clip",
             rejection_fraction=0.0,
             options_json='{"sigma_clip": true, "sigma_kappa": 3.0}'),
        [_frame() for _ in range(12)],
    )
    note = _note(notes, "rejection_blind")
    assert note is not None
    assert "at least half of this picture no more than 3 subs overlap" in note.message
    assert "couldn't drop anything there" in note.message
    assert "11 frames" in note.message
    assert note.action == "restack"


def test_the_provable_everywhere_wording_still_wins_when_the_peak_is_shallow():
    """When even the deepest pixel is below the threshold the stronger claim is
    true, and the note must keep making it rather than retreating to "half"."""
    notes = stack_health(
        _run(n_frames_used=12, coverage_min=3, coverage_max=3, is_mosaic=True,
             coverage_median_depth=3.0, rejection_mode="sigma-clip",
             options_json='{"sigma_clip": true, "sigma_kappa": 3.0}'),
        [_frame() for _ in range(12)],
    )
    note = _note(notes, "rejection_blind")
    assert note is not None
    assert "3 subs overlapping at any one spot" in note.message
    assert "at least half" not in note.message


def test_a_deep_mosaic_stays_silent_even_with_the_median_known():
    """It can only ever make the note fire in more cases — never fewer, and never
    on a mosaic whose panels really are deep enough."""
    notes = stack_health(
        _run(n_frames_used=400, coverage_min=20, coverage_max=60, is_mosaic=True,
             coverage_median_depth=30.0, rejection_mode="sigma-clip",
             rejection_fraction=0.003,
             options_json='{"sigma_clip": true, "sigma_kappa": 3.0}'),
        [_frame() for _ in range(40)],
    )
    assert "rejection_blind" not in _kinds(notes)


def test_a_run_recorded_before_the_median_existed_keeps_the_old_test_exactly():
    """Upgrade safety: None means "unknown", and an unknown median must leave the
    peak test to the letter — no new note on the owner's existing library."""
    notes = stack_health(
        _run(n_frames_used=12, coverage_min=3, coverage_max=12, is_mosaic=True,
             coverage_median_depth=None, rejection_mode="sigma-clip",
             options_json='{"sigma_clip": true, "sigma_kappa": 3.0}'),
        [_frame() for _ in range(12)],
    )
    assert "rejection_blind" not in _kinds(notes)


# --- The uncalibrated note stops claiming a speckle the app has measured away --
#
# Found by reading a dogfood pass's own printed block as one paragraph
# (2026-09-19, `--mosaic --editor --incoming-lag`, otherwise CLEAN): the
# readiness card an inch above the health card had *measured* the same
# background — "across most of it the background already looks clean at 4 min
# (grain 0.001)" — while this note told the same reader, about the same picture,
# that darks "would cut the background speckle". One card guessing at what
# another had measured.


def test_a_measured_clean_background_stops_the_note_claiming_speckle():
    """The offer stays; the unearned magnitude claim goes.

    Fails before the fix: the old note said "would cut the background speckle"
    on every uncalibrated run whatever its σ.
    """
    notes = stack_health(_run(calstat=None, noise_sigma=0.001),
                         [_frame() for _ in range(10)])
    note = next(n for n in notes if n.kind == "calibration")
    # Still the same note, still ranked and wired the same way — only the
    # sentence about *this* picture's grain changed.
    assert note.action == "calibration"
    assert notes[0].kind == "calibration"
    assert "darks" in note.message.lower()
    assert "background speckle" not in note.message
    assert "already measures clean" in note.message
    # What darks still buy on a picture whose sky is already clean: the part a
    # robust σ cannot see.
    assert "hot pixels" in note.message


def test_a_grainy_background_keeps_todays_sentence_byte_for_byte():
    """Above the bar nothing moves — this fix may only ever make the app say
    *less* than it measured, never more."""
    notes = stack_health(_run(calstat=None, noise_sigma=0.08),
                         [_frame() for _ in range(10)])
    note = next(n for n in notes if n.kind == "calibration")
    assert note.message == (
        "No darks or flats were applied to this stack. Adding master darks "
        "would cut the background speckle and hot pixels.")


def test_an_unmeasured_run_is_not_called_clean():
    """A run recorded before the σ column existed, or one the estimator
    declined, carries no measurement — so it keeps the general wording rather
    than being told its background is clean on no evidence."""
    for sigma in (None, float("nan"), 0.0, -1.0):
        notes = stack_health(_run(calstat=None, noise_sigma=sigma),
                             [_frame() for _ in range(10)])
        note = next(n for n in notes if n.kind == "calibration")
        assert "already measures clean" not in note.message, sigma
        assert "background speckle" in note.message, sigma


def test_background_reads_clean_is_the_one_bar_and_it_is_the_frontends():
    """`CLEAN_BACKGROUND_SIGMA` is not a bar invented here — it is the number
    `frontend/src/components/target/grainProjection.ts::CLEAN_SIGMA` already
    prints "the background already looks clean" from, and the two cards
    disagreeing about one picture is what it exists to stop. Pinned on both
    sides (see `grainProjection.test.ts`) so neither can drift alone."""
    assert CLEAN_BACKGROUND_SIGMA == 0.02
    assert background_reads_clean(CLEAN_BACKGROUND_SIGMA) is True
    assert background_reads_clean(0.0201) is False
    assert background_reads_clean("not a number") is False


def test_a_calibrated_run_says_nothing_about_darks_however_clean_it_is():
    """The σ branch is reached only through the uncalibrated gate — a stack that
    *did* get its masters must not acquire a new note from this."""
    notes = stack_health(_run(calstat="dark+flat", noise_sigma=0.001),
                         [_frame() for _ in range(10)])
    assert "calibration" not in _kinds(notes)


def test_the_clean_sentence_states_the_scope_it_was_measured_over():
    """On a mosaic, σ is one figure for the whole canvas and is dominated by the
    part that got the most subs — so "the background here already measures
    clean" would be the same over-claim in a new place on a canvas this very
    card calls 1.4× grainier over a quarter of itself.

    The bundled 2×2's own figures (3 subs against 6 over 23 % of the canvas),
    which is the shape the owner's multi-night mosaics have. Fails before the
    scope clause: the sentence read "The background here already measures
    clean" beside a note saying part of it is grainier.
    """
    notes = stack_health(
        _run(calstat=None, noise_sigma=0.001, is_mosaic=True,
             grain_ratio=1.43, grain_thin_frames=3, grain_deep_frames=6,
             grain_thin_share=0.2257),
        [_frame() for _ in range(10)])
    cal = next(n for n in notes if n.kind == "calibration")
    assert "Across most of it the background already measures clean" in cal.message
    assert "The background here" not in cal.message
    # It is the same page saying both, so the pair has to hold together.
    grain = next(n for n in notes if n.kind == "grain_uneven")
    assert "grain only comes down with more light" in grain.message


def test_an_evenly_deep_picture_keeps_the_unqualified_clean_sentence():
    """A single field, and a mosaic whose panels match, have nothing to scope —
    the scope clause must not leak onto them."""
    for extra in ({}, dict(is_mosaic=True, grain_ratio=1.0,
                           grain_thin_frames=6, grain_deep_frames=6,
                           grain_thin_share=0.2)):
        notes = stack_health(_run(calstat=None, noise_sigma=0.001, **extra),
                             [_frame() for _ in range(10)])
        cal = next(n for n in notes if n.kind == "calibration")
        assert "The background here already measures clean" in cal.message
        assert "Across most of it" not in cal.message


def test_uneven_grain_verdict_is_the_one_reader_of_those_four_figures():
    """Both sentences that depend on it read the same function — a note that
    cannot explain its ratio must not claim one, in either place."""
    full = dict(grain_ratio=1.43, grain_thin_frames=3, grain_deep_frames=6,
                grain_thin_share=0.2257)
    assert uneven_grain_verdict(_run(**full)) == "uneven"
    # Any missing figure withdraws the verdict, and with it the scope clause.
    for missing in ("grain_thin_frames", "grain_deep_frames", "grain_thin_share"):
        partial = dict(full, **{missing: None})
        assert uneven_grain_verdict(_run(**partial)) is None
        notes = stack_health(_run(calstat=None, noise_sigma=0.001, **partial),
                             [_frame() for _ in range(10)])
        cal = next(n for n in notes if n.kind == "calibration")
        assert "Across most of it" not in cal.message, missing


# --- …and the other half of that same claim: the gain ------------------------
#
# The block above makes the argument for the exposure, and the gain sat one line
# below it taking the median it warns against. The gain case is the sharper one:
# an exposure is a quantity, so a median between 10 s and 30 s is at least a
# length a camera could be set to — a gain is a discrete *setting*, so the
# median of 80 and 200 is 140, a number the Seestar cannot be dialled to at all,
# printed under an instruction to go and dial it in.


def test_the_dark_guide_never_asks_for_a_gain_the_camera_cannot_be_set_to():
    """Fail-before: ``gain`` was ``statistics.median``, so a target shot half at
    80 and half at 200 told the owner to shoot his darks at gain 140."""
    frames = ([_exp_frame(gain=80.0) for _ in range(3)]
              + [_exp_frame(gain=200.0) for _ in range(3)])
    spec = recommended_dark_spec(frames)
    assert spec.gain == 80.0
    assert spec.gain != 140.0
    # …and the set travels beside it, so the guide can ask for a set per gain
    # the way it already asks for a set per length.
    assert spec.gains == (80.0, 200.0)


def test_the_dark_guide_names_the_gain_most_of_the_subs_were_shot_at():
    """Not the median, and not the first one seen: the setting the most subs
    actually carry, so the darks the owner shoots calibrate the largest part of
    the stack."""
    frames = ([_exp_frame(gain=80.0) for _ in range(4)]
              + [_exp_frame(gain=200.0) for _ in range(2)])
    assert recommended_dark_spec(frames).gain == 80.0
    frames = ([_exp_frame(gain=80.0) for _ in range(2)]
              + [_exp_frame(gain=200.0) for _ in range(4)])
    assert recommended_dark_spec(frames).gain == 200.0


def test_the_dark_guide_is_unchanged_on_a_single_gain_target():
    """Every ordinary target — one setting all year. The mode, the median and
    the only value are the same number, and the set is one entry, so the guide's
    sentence is byte-for-byte what it was."""
    spec = recommended_dark_spec([_exp_frame(gain=80.0) for _ in range(5)])
    assert spec.gain == 80.0
    assert spec.gains == (80.0,)
    # A header round-trip is one setting, not two — the engine's own grouping.
    jittered = recommended_dark_spec(
        [_exp_frame(gain=g) for g in (80.0, 80.0002, 79.9998)])
    assert len(jittered.gains) == 1


def test_the_dark_guides_gain_set_is_silent_when_nothing_recorded_one():
    spec = recommended_dark_spec([_exp_frame(gain=None) for _ in range(3)])
    assert spec.gain is None and spec.gains == ()
    assert recommended_dark_spec([]).gains == ()
