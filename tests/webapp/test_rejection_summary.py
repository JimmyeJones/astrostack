"""Unit tests for the pure 'why were some frames left out?' grouping helper."""

from webapp.rejection_summary import summarize_rejections


def _keys(summary):
    return {b["key"]: b["count"] for b in summary["buckets"]}


def test_reasons_group_into_friendly_buckets():
    counts = {
        "auto:streak": 4,          # trailed
        "bulk:streaked": 2,        # trailed
        "bulk:trailed": 1,         # trailed
        "auto:grade:star_count": 3,        # clouds
        "auto:grade:sky_adu_median": 1,    # clouds
        "auto:grade:transparency_score": 2,  # clouds
        "auto:grade:fwhm_px": 5,           # soft
        "auto:grade:eccentricity_median": 1,  # soft
        "qc:fwhm": 2,              # soft (qc: metric)
        "solve_failed:no star database": 3,  # solve_failed
        "user": 4,                 # removed
        "qc_error_final:boom": 1,  # error
        "auto:grade:weird_metric": 1,  # other (unknown metric)
    }
    s = summarize_rejections(counts, n_accepted=100)
    k = _keys(s)
    assert k["trailed"] == 7
    assert k["clouds"] == 6
    assert k["soft"] == 8
    assert k["solve_failed"] == 3
    assert k["removed"] == 4
    assert k["error"] == 1
    assert k["other"] == 1
    assert s["dropped"] == sum(counts.values())
    assert s["used"] == 100


def test_buckets_are_in_canonical_presentation_order():
    # Regardless of input dict order, buckets come back trailed→clouds→soft→
    # solve_failed→removed→error→other.
    counts = {"user": 1, "qc_error:x": 1, "auto:streak": 1,
              "auto:grade:fwhm_px": 1, "auto:grade:star_count": 1,
              "solve_failed:foo": 1}
    s = summarize_rejections(counts, n_accepted=10)
    order = [b["key"] for b in s["buckets"]]
    assert order == ["trailed", "clouds", "soft", "solve_failed", "removed", "error"]


def test_zero_and_negative_counts_are_ignored():
    s = summarize_rejections({"user": 0, "auto:streak": -3, "qc:fwhm": 2},
                             n_accepted=8)
    assert _keys(s) == {"soft": 2}
    assert s["dropped"] == 2


def test_empty_counts_yields_no_buckets_and_a_zero_fraction():
    s = summarize_rejections({}, n_accepted=50)
    assert s["buckets"] == []
    assert s["dropped"] == 0
    assert s["dropped_fraction"] == 0.0
    assert s["used"] == 50


def test_verdict_thresholds():
    # <10% dropped → healthy.
    assert summarize_rejections({"user": 5}, n_accepted=95)["verdict"]["tone"] == "good"
    # 10–30% → solid but a few dropped.
    assert summarize_rejections({"user": 20}, n_accepted=80)["verdict"]["tone"] == "ok"
    # >=30% → lots dropped, reassure they still stacked the good ones.
    assert summarize_rejections({"user": 40}, n_accepted=60)["verdict"]["tone"] == "warn"


def test_dropped_fraction_is_reported():
    s = summarize_rejections({"auto:streak": 12, "user": 8}, n_accepted=180)
    assert s["dropped"] == 20
    assert s["used"] == 180
    assert s["dropped_fraction"] == round(20 / 200, 4)


def test_negative_accepted_is_floored():
    s = summarize_rejections({"user": 3}, n_accepted=-5)
    assert s["used"] == 0
    assert s["dropped_fraction"] == 1.0


def test_accepted_unsolved_frames_are_left_out_not_counted_as_used():
    # The owner's gibberish case: 500 subs accepted, only 3 plate-solved, none
    # rejected. Before the fix the summary said "used 500, healthy night"; now it
    # honestly reports 3 used, 497 left out because they aren't located yet.
    s = summarize_rejections({}, n_accepted=500, n_unsolved=497)
    k = _keys(s)
    assert k == {"unsolved": 497}
    assert s["used"] == 3
    assert s["dropped"] == 497
    assert s["dropped_fraction"] == round(497 / 500, 4)


def test_unsolved_dominant_verdict_nudges_plate_solve():
    # When unsolved subs outnumber what actually stacked, lead with a plate-solve
    # nudge (the actionable cause), not the generic cloud/wind copy.
    s = summarize_rejections({}, n_accepted=500, n_unsolved=497)
    assert s["verdict"]["tone"] == "warn"
    assert "Plate Solve" in s["verdict"]["text"]


def test_unsolved_combines_with_rejected_frames():
    # Rejected (accept=0) and unsolved-accepted subs are distinct causes and both
    # count as left-out; used stays accepted-and-solved.
    s = summarize_rejections({"user": 10}, n_accepted=100, n_unsolved=20)
    k = _keys(s)
    assert k["removed"] == 10
    assert k["unsolved"] == 20
    assert s["used"] == 80          # 100 accepted − 20 unsolved
    assert s["dropped"] == 30       # 10 rejected + 20 unsolved


def test_a_few_unsolved_among_many_solved_stays_calm():
    # A handful of not-yet-solved subs among a healthy stack keeps a calm verdict
    # (the plate-solve nudge only fires when unsolved dominates), but the frames
    # are still surfaced honestly as left-out.
    s = summarize_rejections({}, n_accepted=400, n_unsolved=8)
    assert s["used"] == 392
    assert _keys(s) == {"unsolved": 8}
    assert s["verdict"]["tone"] == "good"


# --- high-drop verdict names the dominant actionable cause ------------------

def test_high_drop_soft_dominated_names_focus():
    # A high-drop night that's mostly soft/elongated stars gets a specific,
    # actionable headline (check focus/dew) instead of the generic "cloud or wind".
    s = summarize_rejections({"auto:grade:fwhm_px": 30, "auto:streak": 5},
                             n_accepted=65)
    v = s["verdict"]
    assert v["tone"] == "warn"
    assert "focus" in v["text"]
    assert "cloud or wind" not in v["text"]


def test_high_drop_cloud_dominated_names_clouds():
    s = summarize_rejections({"auto:grade:star_count": 30, "user": 5},
                             n_accepted=65)
    v = s["verdict"]
    assert v["tone"] == "warn"
    assert "cloud, haze or moonlight" in v["text"]


def test_high_drop_solve_failed_dominated_names_location():
    s = summarize_rejections({"solve_failed:no stars": 30, "user": 5},
                             n_accepted=65)
    v = s["verdict"]
    assert v["tone"] == "warn"
    assert "located in the sky" in v["text"]


def test_high_drop_unsolved_dominated_nudges_plate_solve_even_when_used_is_larger():
    # Unsolved dominates the *dropped* frames but doesn't outnumber what stacked,
    # so the top-level plate-solve nudge (unsolved >= used) doesn't fire — the
    # dominant-cause branch still names it and points at Plate Solve.
    s = summarize_rejections({"user": 10}, n_accepted=100, n_unsolved=40)
    v = s["verdict"]
    assert s["used"] == 60 and s["dropped"] == 50   # unsolved 40 < used 60
    assert v["tone"] == "warn"
    assert "Plate Solve" in v["text"]


def test_high_drop_mixed_night_keeps_the_generic_reassurance():
    # No single bucket is strictly the majority (18 soft / 18 clouds of 36) → the
    # generic copy stays (naming one of two co-dominant causes would mislead).
    s = summarize_rejections({"auto:grade:fwhm_px": 18, "auto:grade:star_count": 18},
                             n_accepted=64)
    v = s["verdict"]
    assert v["tone"] == "warn"
    assert "usually cloud or wind" in v["text"]


def test_high_drop_trailed_dominated_stays_generic_reassuring():
    # Trailed frames are the stacker doing its job (nothing for the user to fix),
    # so even when they dominate, the headline stays the generic reassurance
    # rather than inventing an action.
    s = summarize_rejections({"auto:streak": 30, "user": 5}, n_accepted=65)
    v = s["verdict"]
    assert v["tone"] == "warn"
    assert "usually cloud or wind" in v["text"]


def test_mid_drop_is_unaffected_by_a_dominant_bucket():
    # The dominant-cause copy is only for the high-drop (>=30%) branch; a solid
    # 10-30% night keeps its calm "still a solid stack" line even if soft-heavy.
    s = summarize_rejections({"auto:grade:fwhm_px": 20}, n_accepted=80)
    v = s["verdict"]
    assert v["tone"] == "ok"
    assert "solid stack" in v["text"]
