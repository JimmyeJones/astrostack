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
