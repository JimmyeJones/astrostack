"""Unit tests for the plain-language "How's my stack?" health check."""

from __future__ import annotations

from seestack.io.project import FrameRow, StackRunRow
from seestack.stackhealth import stack_health


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


def _frame(*, accept=True, ecc=0.35, reason=None) -> FrameRow:
    return FrameRow(source_path=f"s{id(object())}.fit", accept=accept,
                    eccentricity_median=ecc, reject_reason=reason)


def _kinds(notes) -> list[str]:
    return [n.kind for n in notes]


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
