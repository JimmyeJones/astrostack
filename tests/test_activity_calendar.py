"""Tests for the pure imaging-activity-calendar engine."""

from __future__ import annotations

from datetime import date

import pytest

from seestack.activity_calendar import build_activity_calendar, night_date_of


def test_night_date_groups_a_midnight_spanning_session_into_one_night():
    # A UTC-noon-to-noon session: dusk-side at 22:00 and pre-dawn at 03:00 the
    # next calendar day both belong to the night of the earlier date.
    assert night_date_of("2026-07-10T22:00:00Z") == date(2026, 7, 10)
    assert night_date_of("2026-07-11T03:00:00Z") == date(2026, 7, 10)
    # Just after local noon rolls to the new night.
    assert night_date_of("2026-07-11T13:00:00Z") == date(2026, 7, 11)


def test_night_date_uses_longitude_for_local_time():
    # 02:00 UTC at +150°E is midday-ish local (UTC+10) → still the same night as
    # the prior evening under noon-to-noon, but the *date* shifts vs pure UTC.
    # +150E → +10h; 2026-07-11T02:00Z local = 12:00 on the 11th → night of 11th.
    assert night_date_of("2026-07-11T02:00:00Z", lon_deg=150.0) == date(2026, 7, 11)
    # Same instant with no location bucketed as UTC noon-to-noon → night of 10th.
    assert night_date_of("2026-07-11T02:00:00Z") == date(2026, 7, 10)


def test_night_date_none_on_garbage_or_empty():
    assert night_date_of("") is None
    assert night_date_of("not-a-date") is None
    # A naive stamp is treated as UTC, not rejected.
    assert night_date_of("2026-07-10T22:00:00") == date(2026, 7, 10)


def _entries():
    # Two nights: 2026-07-10 (M31, 3 subs incl. one after midnight) and
    # 2026-07-12 (M42, 2 subs). 2026-07-11 is a gap (clouded out).
    return [
        ("2026-07-10T22:00:00Z", 60.0, "M31"),
        ("2026-07-10T23:30:00Z", 60.0, "M31"),
        ("2026-07-11T02:00:00Z", 60.0, "M31"),   # after midnight → still 07-10
        ("2026-07-12T21:00:00Z", 30.0, "M42"),
        ("2026-07-12T21:30:00Z", 30.0, "M42"),
    ]


def test_build_buckets_by_night_with_totals_and_targets():
    cal = build_activity_calendar(_entries(), today=date(2026, 7, 12), months=12)
    assert cal.n_nights == 2
    assert [n.date for n in cal.nights] == ["2026-07-10", "2026-07-12"]
    first, second = cal.nights
    assert first.n_frames == 3 and first.exposure_s == 180.0
    assert first.targets == ["M31"]
    assert second.n_frames == 2 and second.exposure_s == 60.0
    assert second.targets == ["M42"]
    assert cal.total_exposure_s == 240.0


def test_best_streak_counts_consecutive_nights_only():
    # Three consecutive nights then a gap then one more → best run is 3.
    entries = [
        ("2026-07-01T22:00:00Z", 10.0, "A"),
        ("2026-07-02T22:00:00Z", 10.0, "A"),
        ("2026-07-03T22:00:00Z", 10.0, "A"),
        ("2026-07-06T22:00:00Z", 10.0, "A"),
    ]
    cal = build_activity_calendar(entries, today=date(2026, 7, 6), months=12)
    assert cal.n_nights == 4
    assert cal.best_streak_nights == 3


def test_nights_this_month_only_counts_todays_calendar_month():
    entries = [
        ("2026-06-28T22:00:00Z", 10.0, "A"),   # previous month
        ("2026-07-02T22:00:00Z", 10.0, "A"),
        ("2026-07-20T22:00:00Z", 10.0, "A"),
    ]
    cal = build_activity_calendar(entries, today=date(2026, 7, 24), months=12)
    assert cal.n_nights == 3
    assert cal.nights_this_month == 2


def test_window_drops_nights_older_than_the_month_horizon():
    entries = [
        ("2024-01-01T22:00:00Z", 10.0, "old"),   # well outside a 12-month window
        ("2026-07-01T22:00:00Z", 10.0, "recent"),
    ]
    cal = build_activity_calendar(entries, today=date(2026, 7, 24), months=12)
    assert [n.targets for n in cal.nights] == [["recent"]]
    assert cal.n_nights == 1
    # Window endpoints are reported so the frontend can size the grid.
    assert cal.end_date == "2026-07-24"
    assert cal.start_date < cal.end_date


def test_empty_library_is_valid_but_empty():
    cal = build_activity_calendar([], today=date(2026, 7, 24), months=12)
    assert cal.n_nights == 0
    assert cal.nights == []
    assert cal.total_exposure_s == 0.0
    assert cal.nights_this_month == 0
    assert cal.best_streak_nights == 0
    assert cal.end_date == "2026-07-24"


def test_missing_exposure_counts_the_night_but_adds_zero_seconds():
    cal = build_activity_calendar(
        [("2026-07-10T22:00:00Z", None, "A")], today=date(2026, 7, 10), months=12,
    )
    assert cal.n_nights == 1
    assert cal.nights[0].n_frames == 1
    assert cal.nights[0].exposure_s == 0.0


def test_unparseable_or_empty_timestamps_are_skipped():
    cal = build_activity_calendar(
        [
            ("", 10.0, "A"),
            (None, 10.0, "A"),
            ("garbage", 10.0, "A"),
            ("2026-07-10T22:00:00Z", 10.0, "A"),
        ],
        today=date(2026, 7, 10),
        months=12,
    )
    assert cal.n_nights == 1
    assert cal.nights[0].n_frames == 1


@pytest.mark.parametrize("months", [1, 3, 12])
def test_window_scales_with_months(months):
    cal = build_activity_calendar([], today=date(2026, 7, 24), months=months)
    assert cal.months == months
    # A larger month count reaches further back.
    assert cal.start_date <= "2026-07-24"


def test_months_floored_to_at_least_one():
    cal = build_activity_calendar([], today=date(2026, 7, 24), months=0)
    assert cal.months == 1


# ---- "your best night": the sharpest night of the whole hobby --------------
#
# The calendar says how much you collected each night. This says which night was
# actually the *good* one — measured the same way the rest of the app judges a
# night (median star size in pixels, smaller is sharper), so the answers agree.


def _night(day: int, fwhms, target="A"):
    """One night's worth of entries: ``len(fwhms)`` subs, each with its measured
    star size (or None for an unmeasured sub)."""
    return [
        (f"2026-07-{day:02d}T22:00:00Z", 10.0, target, f) for f in fwhms
    ]


def test_sharpest_night_is_the_one_with_the_smallest_stars():
    cal = build_activity_calendar(
        _night(10, [3.4, 3.6, 3.5, 3.7, 3.5])
        + _night(11, [2.3, 2.5, 2.4, 2.4, 2.6])   # the good one
        + _night(12, [4.1, 4.0, 4.2, 4.0, 4.3]),
        today=date(2026, 7, 20), months=12,
    )
    assert cal.sharpest is not None
    assert cal.sharpest.date == "2026-07-11"
    assert cal.sharpest.median_fwhm_px == 2.4
    assert cal.sharpest.n_measured == 5
    # Every night still carries its own median, so a caller can rank differently.
    assert [n.median_fwhm_px for n in cal.nights] == [3.5, 2.4, 4.1]


def test_a_thinly_measured_night_cannot_win():
    # One sub that happened to be sharp is a fact about the sub, not the night —
    # it must not out-rank a night of five measured subs.
    cal = build_activity_calendar(
        _night(10, [3.4, 3.6, 3.5, 3.7, 3.5])
        + _night(11, [3.0, 3.1, 3.2, 3.0, 3.1])
        + _night(12, [1.1]),
        today=date(2026, 7, 20), months=12,
    )
    assert cal.sharpest is not None
    assert cal.sharpest.date == "2026-07-11"


def test_no_sharpest_night_when_only_one_night_qualifies():
    # "The best of one" is not a fact about the sky — stay silent.
    cal = build_activity_calendar(
        _night(10, [3.4, 3.6, 3.5, 3.7, 3.5]) + _night(11, [2.0, 2.1]),
        today=date(2026, 7, 20), months=12,
    )
    assert cal.sharpest is None


def test_no_sharpest_night_when_nothing_was_measured():
    cal = build_activity_calendar(
        _night(10, [None] * 6) + _night(11, [None] * 6),
        today=date(2026, 7, 20), months=12,
    )
    assert cal.sharpest is None
    assert all(n.median_fwhm_px is None for n in cal.nights)
    assert all(n.n_measured == 0 for n in cal.nights)


def test_unmeasurable_star_sizes_are_not_counted_as_measurements():
    # A failed measurement stored as 0, a negative, a NaN or a non-number must
    # not enter the median — a fabricated 0 px would win every comparison.
    cal = build_activity_calendar(
        _night(10, [3.0, 3.2, 3.1, 3.3, 3.2])
        + _night(11, [0.0, -1.0, float("nan"), "x", None, 2.9, 3.0, 2.8, 3.1, 2.9]),
        today=date(2026, 7, 20), months=12,
    )
    night11 = next(n for n in cal.nights if n.date == "2026-07-11")
    assert night11.n_measured == 5
    assert night11.median_fwhm_px == 2.9
    assert cal.sharpest is not None and cal.sharpest.date == "2026-07-11"


def test_three_tuple_entries_still_fold_exactly_as_before():
    # Every existing caller passes (timestamp, exposure, target). The star size
    # is a 4th, optional element — a 3-tuple must keep working untouched.
    cal = build_activity_calendar(
        [("2026-07-10T22:00:00Z", 10.0, "A"),
         ("2026-07-10T23:00:00Z", 10.0, "B")],
        today=date(2026, 7, 20), months=12,
    )
    assert cal.n_nights == 1
    assert cal.nights[0].n_frames == 2
    assert cal.nights[0].exposure_s == 20.0
    assert cal.nights[0].targets == ["A", "B"]
    assert cal.nights[0].median_fwhm_px is None
    assert cal.sharpest is None


def test_sharpest_night_ties_break_on_the_earlier_date():
    cal = build_activity_calendar(
        _night(10, [2.5] * 5) + _night(11, [2.5] * 5),
        today=date(2026, 7, 20), months=12,
    )
    assert cal.sharpest is not None and cal.sharpest.date == "2026-07-10"


def test_sharpest_night_only_considers_nights_inside_the_window():
    # A brilliant night from two years ago isn't "your best night" on a
    # 12-month page — the window that drops it from the grid drops it here too.
    old = [("2024-01-05T22:00:00Z", 10.0, "A", 1.5) for _ in range(6)]
    cal = build_activity_calendar(
        old + _night(10, [3.0] * 5) + _night(11, [2.8] * 5),
        today=date(2026, 7, 20), months=12,
    )
    assert cal.sharpest is not None and cal.sharpest.date == "2026-07-11"
