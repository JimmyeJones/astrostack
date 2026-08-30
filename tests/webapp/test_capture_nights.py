"""``webapp.capture_nights`` — a run's capture window as observing-night dates.

The point of routing this through :func:`seestack.activity_calendar.night_date_of`
rather than slicing the date off the stamp is that an evening's subs straddle UTC
midnight for anybody west of Greenwich. Slicing would put one session's first and
last sub on two different dates, and name a night the Nights card calls something
else.
"""

from __future__ import annotations

from webapp.capture_nights import capture_night_range


def test_one_night_answers_the_same_date_twice():
    assert capture_night_range(
        "2024-11-15T22:01:00Z", "2024-11-16T03:12:00Z") == (
        "2024-11-15", "2024-11-15")


def test_several_nights_answer_the_range():
    assert capture_night_range(
        "2024-11-15T22:01:00Z", "2024-11-18T21:40:00Z") == (
        "2024-11-15", "2024-11-18")


def test_one_evening_far_from_utc_is_one_night_not_two():
    """A single evening in New Zealand (lon +150° ⇒ UTC+10): 20:00 to 04:00
    local on the night of 15 Nov is 10:00–18:00 **UTC on the 15th**, which
    straddles UTC noon. Bucketed without a location the session reads as two
    nights; bucketed by the observer's own noon-to-noon it is the one night the
    Nights card and the imaging calendar already call it."""
    assert capture_night_range(
        "2024-11-15T10:00:00Z", "2024-11-15T18:00:00Z") == (
        "2024-11-14", "2024-11-15")  # no location: UTC noon-to-noon splits it
    assert capture_night_range(
        "2024-11-15T10:00:00Z", "2024-11-15T18:00:00Z", 150.0) == (
        "2024-11-15", "2024-11-15")


def test_a_missing_end_still_names_the_night_it_has():
    assert capture_night_range("2024-11-15T22:01:00Z", None) == (
        "2024-11-15", "2024-11-15")
    assert capture_night_range(None, "2024-11-15T22:01:00Z") == (
        "2024-11-15", "2024-11-15")


def test_no_window_is_no_answer():
    assert capture_night_range(None, None) == (None, None)
    assert capture_night_range("", "") == (None, None)
    assert capture_night_range("not-a-date", "also-not") == (None, None)


def test_a_reversed_window_is_still_reported_in_reading_order():
    assert capture_night_range(
        "2024-11-18T21:40:00Z", "2024-11-15T22:01:00Z") == (
        "2024-11-15", "2024-11-18")
