"""Tests for automatic frame-quality grading (seestack.qc.grading).

The grading module is a pure function over FrameRows, so these tests build
synthetic frame populations directly — one metric perturbed at a time — and
assert on which frames get recommended and why.
"""

from __future__ import annotations

import math

import pytest

from seestack.io.project import FrameRow
from seestack.qc.grading import (
    MAX_REJECT_FRACTION,
    MIN_FRAMES_FOR_GRADING,
    SENSITIVITY_THRESHOLDS,
    apply_grade_report,
    best_frame,
    grade_frames,
)


def make_frame(
    i: int,
    *,
    fwhm: float | None = 3.0,
    stars: int | None = 400,
    sky: float | None = 1200.0,
    ecc: float | None = 0.40,
    transp: float | None = 5000.0,
    accept: bool = True,
    user_override: bool = False,
) -> FrameRow:
    return FrameRow(
        source_path=f"/lib/target/frame_{i:04d}.fit",
        id=i,
        fwhm_px=fwhm,
        star_count=stars,
        sky_adu_median=sky,
        eccentricity_median=ecc,
        transparency_score=transp,
        accept=accept,
        user_override=user_override,
    )


def make_frame_like(f: FrameRow, **overrides) -> FrameRow:
    """A copy of ``f`` with fields overridden — for handing a frame back to
    ``grade_frames(reconsider=…)`` as a rejected row."""
    import dataclasses

    return dataclasses.replace(f, **overrides)


def clean_population(n: int = 40, seed: int = 7) -> list[FrameRow]:
    """A realistic, well-behaved night: small correlated wobble on each metric."""
    import random

    rng = random.Random(seed)
    frames = []
    for i in range(1, n + 1):
        jitter = rng.gauss(0.0, 1.0)
        frames.append(make_frame(
            i,
            fwhm=3.0 + 0.15 * jitter + rng.gauss(0, 0.05),
            stars=int(400 + 20 * -jitter + rng.gauss(0, 8)),
            sky=1200.0 + 40 * jitter + rng.gauss(0, 15),
            ecc=0.40 + 0.03 * abs(jitter) + rng.gauss(0, 0.01),
            transp=5000.0 - 150 * abs(jitter) + rng.gauss(0, 60),
        ))
    return frames


def recommended_ids(report) -> set[int]:
    return {r.frame_id for r in report.recommendations}


# ---------------------------------------------------------------------------
# Core behaviour
# ---------------------------------------------------------------------------


def test_clean_population_yields_no_recommendations():
    report = grade_frames(clean_population())
    assert report.recommendations == []
    assert report.capped is False
    assert set(report.metrics_used) == {
        "fwhm_px", "eccentricity_median", "sky_adu_median",
        "star_count", "transparency_score",
    }


def test_soft_frame_flagged_on_fwhm_with_plain_language_reason():
    frames = clean_population()
    frames.append(make_frame(99, fwhm=8.0))  # badly out of focus / cloud
    report = grade_frames(frames)
    assert recommended_ids(report) == {99}
    rec = report.recommendations[0]
    assert rec.primary_metric == "fwhm_px"
    assert rec.name == "frame_0099.fit"
    reason = rec.reasons[0]
    assert reason.z >= report.threshold
    assert "softer than typical" in reason.label
    assert "8.0 px" in reason.label


def test_direction_awareness_never_flags_unusually_good_frames():
    frames = clean_population()
    frames.append(make_frame(90, fwhm=1.2))       # unusually sharp
    frames.append(make_frame(91, sky=200.0))      # unusually dark sky
    frames.append(make_frame(92, stars=1400))     # unusually rich field
    frames.append(make_frame(93, transp=20000.0)) # unusually transparent
    frames.append(make_frame(94, ecc=0.05))       # unusually round stars
    report = grade_frames(frames)
    assert recommended_ids(report) == set()


def test_cloudy_frame_flags_low_star_count_and_bright_sky():
    frames = clean_population()
    frames.append(make_frame(99, stars=25, sky=9000.0))
    report = grade_frames(frames)
    assert recommended_ids(report) == {99}
    metrics = {r.metric for r in report.recommendations[0].reasons}
    assert "star_count" in metrics
    assert "sky_adu_median" in metrics
    # Reasons are sorted worst-first and the primary metric matches.
    zs = [r.z for r in report.recommendations[0].reasons]
    assert zs == sorted(zs, reverse=True)
    assert report.recommendations[0].primary_metric == report.recommendations[0].reasons[0].metric


def test_hazy_frame_flags_low_transparency():
    frames = clean_population()
    frames.append(make_frame(99, transp=900.0))
    report = grade_frames(frames)
    assert recommended_ids(report) == {99}
    assert report.recommendations[0].primary_metric == "transparency_score"


def test_trailed_frame_flags_high_eccentricity():
    frames = clean_population()
    frames.append(make_frame(99, ecc=0.95))
    report = grade_frames(frames)
    assert recommended_ids(report) == {99}
    assert report.recommendations[0].primary_metric == "eccentricity_median"


def test_zero_star_count_is_maximally_bad_not_a_crash():
    frames = clean_population()
    frames.append(make_frame(99, stars=0))  # solid cloud
    report = grade_frames(frames)
    assert recommended_ids(report) == {99}
    z = report.recommendations[0].reasons[0].z
    assert math.isfinite(z)  # JSON-safe, not inf


# ---------------------------------------------------------------------------
# Robustness / safety rails
# ---------------------------------------------------------------------------


def test_stable_night_tiny_deviation_is_not_flagged():
    # A rock-stable night collapses the MAD, so a harmless 0.2 px FWHM bump
    # becomes a giant z-score. The practical-significance floor must keep
    # auto-grade quiet — 3.2 px vs 3.0 px is not a bad frame.
    import random

    rng = random.Random(11)
    frames = [make_frame(i, fwhm=3.0 + rng.gauss(0, 0.01)) for i in range(1, 41)]
    frames.append(make_frame(99, fwhm=3.2))
    report = grade_frames(frames, sensitivity="aggressive")
    assert recommended_ids(report) == set()
    # …but a genuinely soft frame on the same stable night still flags.
    frames.append(make_frame(98, fwhm=4.5))
    report = grade_frames(frames)
    assert recommended_ids(report) == {98}


def test_metric_with_too_few_samples_is_skipped():
    # Only 5 frames carry transparency — below MIN_FRAMES_FOR_GRADING.
    frames = clean_population(n=30)
    for f in frames:
        f.transparency_score = None
    for f in frames[:4]:
        f.transparency_score = 5000.0
    frames.append(make_frame(99, transp=10.0))
    report = grade_frames(frames)
    assert "transparency_score" in report.metrics_skipped
    assert "transparency_score" not in report.metrics_used
    assert recommended_ids(report) == set()  # nothing else is wrong with 99
    assert MIN_FRAMES_FOR_GRADING > 5


def test_zero_mad_population_still_flags_outlier_via_fallback_scale():
    # 21 identical FWHMs (MAD == 0) but a wider mean deviation from a few
    # spread frames — the meanAD fallback must still catch a gross outlier.
    frames = [make_frame(i, fwhm=3.0) for i in range(1, 22)]
    for i, f in enumerate(frames[:6]):
        f.fwhm_px = 3.0 + 0.1 * (i + 1)
    frames.append(make_frame(99, fwhm=9.0))
    report = grade_frames(frames)
    assert 99 in recommended_ids(report)


def test_identical_population_skips_metric_instead_of_dividing_by_zero():
    frames = [make_frame(i) for i in range(1, 25)]  # all metrics identical
    report = grade_frames(frames)
    assert report.recommendations == []
    for m in ("fwhm_px", "star_count", "sky_adu_median",
              "eccentricity_median", "transparency_score"):
        assert m in report.metrics_skipped
        assert "no spread" in report.metrics_skipped[m]


def test_missing_metrics_are_tolerated():
    frames = clean_population()
    frames.append(FrameRow(source_path="/x/bare.fit", id=99))  # no metrics at all
    report = grade_frames(frames)
    assert recommended_ids(report) == set()


def test_reject_cap_limits_recommendations_to_worst_offenders():
    frames = clean_population(n=30)
    # A catastrophic half-night: 15 frames with increasingly bad FWHM.
    bad_ids = list(range(100, 115))
    for k, fid in enumerate(bad_ids):
        frames.append(make_frame(fid, fwhm=8.0 + k))
    report = grade_frames(frames)
    cap = max(1, int(report.n_considered * MAX_REJECT_FRACTION))
    assert report.capped is True
    assert len(report.recommendations) == cap
    # The kept ones are the worst by z: the highest FWHM ids.
    kept = recommended_ids(report)
    assert kept == set(bad_ids[-cap:])


def test_user_override_frames_are_never_recommended_but_inform_stats():
    frames = clean_population()
    # The user explicitly accepted this awful frame — their call stands.
    frames.append(make_frame(99, fwhm=9.0, user_override=True))
    report = grade_frames(frames)
    assert recommended_ids(report) == set()
    assert report.n_considered == len(frames) - 1


def test_rejected_frames_are_excluded_entirely():
    frames = clean_population()
    frames.append(make_frame(99, fwhm=9.0, accept=False))
    report = grade_frames(frames)
    assert recommended_ids(report) == set()
    assert report.n_accepted == len(frames) - 1


def test_sensitivity_ordering_is_monotonic():
    frames = clean_population()
    frames.append(make_frame(97, fwhm=3.9))   # mild
    frames.append(make_frame(98, fwhm=4.6))   # moderate
    frames.append(make_frame(99, fwhm=9.0))   # gross
    cons = recommended_ids(grade_frames(frames, sensitivity="conservative"))
    bal = recommended_ids(grade_frames(frames, sensitivity="balanced"))
    aggr = recommended_ids(grade_frames(frames, sensitivity="aggressive"))
    assert cons <= bal <= aggr
    assert 99 in cons  # the gross one is caught even conservatively
    assert SENSITIVITY_THRESHOLDS["aggressive"] < SENSITIVITY_THRESHOLDS["balanced"]


def test_unknown_sensitivity_raises():
    with pytest.raises(ValueError, match="sensitivity"):
        grade_frames(clean_population(), sensitivity="yolo")


def test_log_domain_catches_multiplicative_star_loss():
    # Star counts spread multiplicatively (300–500); a frame at 60 is a ~7×
    # drop that linear σ over this spread might miss but log-domain must catch.
    import random

    rng = random.Random(3)
    frames = [
        make_frame(i, stars=int(400 * math.exp(rng.gauss(0, 0.12))))
        for i in range(1, 41)
    ]
    frames.append(make_frame(99, stars=60))
    report = grade_frames(frames)
    assert 99 in recommended_ids(report)


def test_two_night_bimodal_population_is_not_nuked():
    # A worse-but-usable second night (softer seeing, brighter sky, 50% of the
    # data) widens the robust spread rather than reading as "half the frames
    # are outliers" — auto-grade must stay quiet, at every sensitivity. Down-
    # weighting a mediocre night is quality weighting's job, not rejection's.
    import random

    rng = random.Random(2)
    frames = [make_frame(i, fwhm=3.0 + rng.gauss(0, 0.15),
                         sky=1200 + rng.gauss(0, 50)) for i in range(1, 51)]
    frames += [make_frame(i, fwhm=4.5 + rng.gauss(0, 0.2),
                          sky=2200 + rng.gauss(0, 80)) for i in range(51, 101)]
    for sens in ("conservative", "balanced", "aggressive"):
        assert recommended_ids(grade_frames(frames, sensitivity=sens)) == set()


# ---------------------------------------------------------------------------
# apply_grade_report (DB integration)
# ---------------------------------------------------------------------------


def test_apply_grade_report_rejects_with_reason_and_respects_user(tmp_path):
    from seestack.io.project import Project

    proj = Project.create(tmp_path, "GradeTest")
    try:
        frames = clean_population()
        frames.append(make_frame(0, fwhm=9.0))   # will be flagged
        for f in frames:
            f.id = None  # let the DB assign ids
            proj.add_frame(f)
        db_frames = list(proj.iter_frames(accepted_only=True))
        report = grade_frames(db_frames)
        assert len(report.recommendations) == 1
        flagged_id = report.recommendations[0].frame_id

        # The user re-accepts (overrides) another flagged-style frame first to
        # prove apply re-checks state: mark the flagged frame user_override.
        proj.update_frame(flagged_id, user_override=True)
        assert apply_grade_report(proj, report) == []
        assert proj.get_frame(flagged_id).accept is True

        # Clear the override — now apply really rejects it.
        proj.update_frame(flagged_id, user_override=False)
        changed = apply_grade_report(proj, report)
        assert changed == [flagged_id]
        f = proj.get_frame(flagged_id)
        assert f.accept is False
        assert f.reject_reason == "auto:grade:fwhm_px"
        # Machine decision — user_override must stay False (like auto:streak).
        assert f.user_override is False

        # Idempotent: re-applying changes nothing (frame already rejected).
        assert apply_grade_report(proj, report) == []
    finally:
        proj.close()


# ---------------------------------------------------------------------------
# reconsider / re_accept — machine decisions are reversible
# ---------------------------------------------------------------------------


def test_reconsider_re_accepts_a_frame_the_bigger_population_no_longer_flags():
    """A frame rejected against a small, tight population is no longer an
    outlier once the night's real spread arrives — so it comes back."""
    early = [make_frame(i, fwhm=3.0 + 0.01 * i) for i in range(1, 16)]
    borderline = make_frame(99, fwhm=4.2)
    first = grade_frames(early + [borderline])
    assert recommended_ids(first) == {99}
    assert first.re_accept == []

    # The night goes on: the population is now genuinely spread, so 4.2 px is
    # ordinary. Grade the survivors with the earlier reject handed back in.
    later = early + [make_frame(200 + i, fwhm=3.0 + 0.85 * (i % 4)) for i in range(60)]
    rejected = make_frame(99, fwhm=4.2, accept=False)
    second = grade_frames(later, reconsider=[rejected])
    assert 99 not in recommended_ids(second)
    assert second.re_accept == [99]


def test_reconsider_keeps_a_frame_rejected_when_it_is_still_an_outlier():
    """A genuinely bad sub stays rejected when reconsidered: it is recommended
    again (so nothing changes) and never lands in ``re_accept``."""
    frames = clean_population()
    rejected = make_frame(0, fwhm=9.0, accept=False)
    report = grade_frames(frames, reconsider=[rejected])
    assert 0 in recommended_ids(report)
    assert report.re_accept == []


def test_reconsider_ignores_user_decisions():
    """Only auto-grade's own machine decisions are reconsidered — a frame the
    user set aside is neither re-accepted nor re-graded."""
    frames = clean_population()
    mine = make_frame(0, fwhm=3.0, accept=False, user_override=True)
    report = grade_frames(frames, reconsider=[mine])
    assert report.re_accept == []
    assert 0 not in recommended_ids(report)


def test_reconsider_is_a_fixed_point_across_repeated_grading():
    """The combined set is invariant under auto-grade's own accept/reject moves,
    so re-grading the same data converges instead of ratcheting: the second pass
    reproduces exactly the first pass's decision, with nothing to re-accept."""
    frames = clean_population(n=60, seed=11)
    frames += [make_frame(500 + i, fwhm=5.5 + 0.3 * i) for i in range(4)]
    first = grade_frames(frames)
    flagged = recommended_ids(first)
    assert flagged

    survivors = [f for f in frames if f.id not in flagged]
    reconsider = [
        make_frame_like(f, accept=False) for f in frames if f.id in flagged
    ]
    second = grade_frames(survivors, reconsider=reconsider)
    assert recommended_ids(second) == flagged
    assert second.re_accept == []


def test_reconsider_holds_the_cap_against_the_original_population():
    """Grading over the combined set is what makes the ``max_reject_fraction``
    rail cumulative: the cap is measured against everything auto-grade has ever
    considered, not against a shrinking survivor set."""
    frames = clean_population(n=40, seed=13)
    frames += [make_frame(600 + i, fwhm=6.0 + 0.4 * i) for i in range(20)]
    first = grade_frames(frames)
    flagged = recommended_ids(first)
    survivors = [f for f in frames if f.id not in flagged]
    reconsider = [make_frame_like(f, accept=False) for f in frames if f.id in flagged]

    second = grade_frames(survivors, reconsider=reconsider)
    # Population = survivors + reconsidered = the original 60 considered frames.
    cap = int(60 * MAX_REJECT_FRACTION)
    assert len(second.recommendations) <= cap
    # Without the reconsider list the same survivors would be re-graded against
    # themselves — the shrinking-denominator cascade the cap has to prevent.
    assert second.n_considered == 60


def test_apply_grade_reaccepts_puts_back_only_auto_grade_rejects(tmp_path):
    from seestack.io.project import Project
    from seestack.qc.grading import GradeReport, apply_grade_reaccepts

    proj = Project.create(tmp_path, "ReAcceptTest")
    try:
        ids = []
        for f in clean_population(n=4):
            f.id = None
            ids.append(proj.add_frame(f))
        auto, streak, mine, still_ok = ids
        proj.update_frame(auto, accept=False, reject_reason="auto:grade:fwhm_px")
        proj.update_frame(streak, accept=False, reject_reason="auto:streak")
        proj.update_frame(mine, accept=False, reject_reason="auto:grade:fwhm_px",
                          user_override=True)

        report = GradeReport(sensitivity="balanced", threshold=3.5,
                             n_accepted=1, n_considered=1,
                             re_accept=[auto, streak, mine, still_ok])
        assert apply_grade_reaccepts(proj, report) == [auto]
        assert proj.get_frame(auto).accept is True
        assert proj.get_frame(auto).reject_reason is None
        assert proj.get_frame(streak).accept is False
        assert proj.get_frame(mine).accept is False
        # Idempotent: a second apply has nothing left to do.
        assert apply_grade_reaccepts(proj, report) == []
    finally:
        proj.close()


# --- best_frame: the pre-stack "First look" pick -------------------------------

def test_best_frame_picks_the_sharpest_accepted_sub():
    frames = [
        make_frame(1, fwhm=3.2, stars=400),
        make_frame(2, fwhm=2.1, stars=380),  # sharpest
        make_frame(3, fwhm=2.9, stars=500),
    ]
    best = best_frame(frames)
    assert best is not None and best.id == 2


def test_best_frame_breaks_fwhm_ties_by_star_count():
    frames = [
        make_frame(1, fwhm=2.5, stars=300),
        make_frame(2, fwhm=2.5, stars=520),  # same FWHM, more stars
        make_frame(3, fwhm=2.5, stars=410),
    ]
    best = best_frame(frames)
    assert best is not None and best.id == 2


def test_best_frame_ignores_rejected_frames():
    frames = [
        make_frame(1, fwhm=1.8, stars=600, accept=False),  # sharpest but rejected
        make_frame(2, fwhm=2.6, stars=400),
    ]
    best = best_frame(frames)
    assert best is not None and best.id == 2


def test_best_frame_requires_a_measured_fwhm():
    # Nothing QC'd yet — accepted frames but no FWHM measured -> None.
    frames = [make_frame(1, fwhm=None, stars=None), make_frame(2, fwhm=None, stars=300)]
    assert best_frame(frames) is None


def test_best_frame_none_on_empty():
    assert best_frame([]) is None


def test_best_frame_tolerates_missing_star_count_in_tiebreak():
    # A missing star_count must not crash the tiebreak; it ranks below a measured one.
    frames = [
        make_frame(1, fwhm=2.5, stars=None),
        make_frame(2, fwhm=2.5, stars=100),
    ]
    best = best_frame(frames)
    assert best is not None and best.id == 2


def test_best_frame_is_deterministic_on_full_ties():
    # Identical FWHM and stars -> stable pick by lowest id.
    frames = [make_frame(3, fwhm=2.5, stars=400), make_frame(1, fwhm=2.5, stars=400)]
    best = best_frame(frames)
    assert best is not None and best.id == 1


# --- Mosaic panels are different patches of sky ------------------------------
# Grading flux-like metrics against the whole target reads a legitimately
# star-poor panel as cloud and can flag every one of its subs (2026-08-17 audit).


def mosaic_population(
    n_per_panel: int = 40,
    panel_seps_deg: tuple[float, ...] = (0.0, 1.0, 2.0, 3.0, 4.0, 5.0),
    poor_panel: int | None = None,
    poor_star_ratio: float = 0.25,
    seed: int = 11,
) -> list[FrameRow]:
    """A mosaic: several panels, each a *different* patch of sky.

    Every panel is shot in identical conditions (same seeing, same sky, same
    transparency); they differ only in how rich the star field happens to be,
    which is a property of where the telescope is pointed, not of the night.
    ``poor_panel`` is star-poor by ``poor_star_ratio`` — a real, healthy panel
    that simply looks at emptier sky.
    """
    import random

    rng = random.Random(seed)
    frames: list[FrameRow] = []
    fid = 0
    for panel, sep in enumerate(panel_seps_deg):
        base_stars = 400 * (poor_star_ratio if panel == poor_panel else 1.0)
        for _ in range(n_per_panel):
            f = make_frame(
                fid,
                fwhm=3.0 + rng.uniform(-0.1, 0.1),
                stars=int(base_stars * rng.uniform(0.95, 1.05)),
                sky=1200.0 * rng.uniform(0.98, 1.02),
                ecc=0.40 + rng.uniform(-0.01, 0.01),
                transp=5000.0 * rng.uniform(0.98, 1.02),
            )
            # Panels stepped along declination; a few arc-seconds of dither
            # inside each one, exactly as a Seestar does.
            frames.append(make_frame_like(
                f, ra_center_deg=83.6, dec_center_deg=-5.4 + sep,
            ))
            frames[-1] = make_frame_like(
                frames[-1],
                dec_center_deg=frames[-1].dec_center_deg + rng.uniform(-0.01, 0.01),
            )
            fid += 1
    return frames


def test_a_star_poor_mosaic_panel_is_not_rejected_as_cloud():
    """The regression: a mosaic panel pointed at emptier sky must be judged
    against *itself*, not against the richer panels beside it.

    Fail-before: the whole target's star-count population made the poor panel's
    every sub a z≈27 outlier ("far fewer stars than typical — likely cloud")
    and 25% of the target — every one the rail would allow — was recommended for
    rejection. All of it is good data, and ``auto_grade_frames`` acts on its own.
    """
    frames = mosaic_population(poor_panel=2)
    poor_ids = {f.id for f in frames if f.star_count is not None and f.star_count < 200}
    assert len(poor_ids) == 40, "fixture should have one clearly star-poor panel"

    report = grade_frames(frames)
    assert report.pointing_groups == 6, "each panel is its own population"
    assert "star_count" in report.metrics_per_pointing
    flagged = {g.frame_id for g in report.recommendations}
    assert not (flagged & poor_ids), (
        "a star-poor panel is a patch of sky, not cloud: "
        f"{len(flagged & poor_ids)} of its subs were recommended for rejection"
    )
    assert not report.recommendations, "nothing here is actually a bad sub"


def test_real_cloud_inside_one_mosaic_panel_is_still_caught():
    """Per-panel populations must not blind auto-grade: a genuinely clouded sub
    is still an outlier against its *own* panel, which is the right comparison."""
    frames = mosaic_population(poor_panel=2)
    clouded = [f for f in frames if f.id in (0, 1)]
    rest = [f for f in frames if f.id not in (0, 1)]
    frames = [
        make_frame_like(f, star_count=30, sky_adu_median=4000.0) for f in clouded
    ] + rest

    report = grade_frames(frames)
    flagged = {g.frame_id for g in report.recommendations}
    assert flagged == {0, 1}, f"expected only the clouded subs, got {sorted(flagged)}"
    reasons = {r.metric for g in report.recommendations for r in g.reasons}
    assert "star_count" in reasons


def test_single_pointing_targets_grade_exactly_as_before():
    """The split only applies when a target genuinely has multiple panels; an
    ordinary dithered single-field target must be graded target-wide, as it
    always has been — no behaviour change for the common case."""
    frames = mosaic_population(panel_seps_deg=(0.0,), n_per_panel=40)
    report = grade_frames(frames)
    assert report.pointing_groups == 0
    assert report.metrics_per_pointing == []

    # …and an unsolved target (no pointing at all) likewise.
    unsolved = clean_population(40)
    assert grade_frames(unsolved).pointing_groups == 0


def test_a_panel_cannot_lose_more_than_the_rail_allows():
    """The target-wide 25% rail is measured against the whole target, so on a
    six-panel mosaic one small panel could still lose every sub without ever
    reaching it. The same fraction now applies within each panel."""
    frames = mosaic_population(n_per_panel=40)
    # Wreck one entire panel for real (heavy cloud on every sub of panel 0).
    wrecked = {f.id for f in frames[:40]}
    frames = [
        make_frame_like(f, star_count=5, sky_adu_median=9000.0, fwhm_px=9.0)
        if f.id in wrecked else f
        for f in frames
    ]
    report = grade_frames(frames)
    flagged = {g.frame_id for g in report.recommendations}
    hit = len(flagged & wrecked)
    assert 0 < hit <= int(40 * MAX_REJECT_FRACTION), (
        f"the per-panel rail should keep this to <= 10 subs, got {hit}")
    assert report.capped


def test_a_panel_too_thin_to_grade_falls_back_to_the_whole_target():
    """A panel with too few subs to carry a robust population must not be left
    ungraded — it falls back to the target-wide yardstick, i.e. exactly today's
    behaviour for those frames."""
    frames = mosaic_population(n_per_panel=40, panel_seps_deg=(0.0, 1.0, 2.0))
    # A fourth, barely-started panel: below MIN_FRAMES_FOR_GRADING.
    tail = [
        make_frame_like(
            make_frame(1000 + i, stars=8, sky=9000.0),
            ra_center_deg=83.6, dec_center_deg=-5.4 + 9.0,
        )
        for i in range(MIN_FRAMES_FOR_GRADING - 5)
    ]
    report = grade_frames(frames + tail)
    assert report.pointing_groups == 3, "the thin panel isn't a population"
    flagged = {g.frame_id for g in report.recommendations}
    assert flagged & {f.id for f in tail}, (
        "clouded subs in a thin panel must still be graded, target-wide")
