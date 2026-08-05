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


def test_rejection_blind_note_silent_on_a_drizzle_run():
    notes = stack_health(
        _run(n_frames_used=5, rejection_mode="drizzle-reject",
             options_json='{"drizzle": true, "drizzle_reject": true}'),
        [_frame() for _ in range(5)],
    )
    assert "rejection_blind" not in _kinds(notes)


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
