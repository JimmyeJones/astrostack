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
