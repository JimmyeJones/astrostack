"""Tests for the pure imaging-activity-calendar engine."""

from __future__ import annotations

from datetime import date

import pytest

from seestack.activity_calendar import (
    build_activity_calendar,
    finalize_calendar,
    night_date_of,
)


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
