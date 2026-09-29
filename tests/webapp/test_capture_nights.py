"""``webapp.capture_nights`` — a run's capture window as observing-night dates.

The point of routing this through :func:`seestack.activity_calendar.night_date_of`
rather than slicing the date off the stamp is that an evening's subs straddle UTC
midnight for anybody west of Greenwich. Slicing would put one session's first and
last sub on two different dates, and name a night the Nights card calls something
else.
"""

from __future__ import annotations

import json

from webapp.capture_nights import (
    capture_night_count,
    capture_night_dates,
    capture_night_range,
    cumulative_night_steps,
)


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


# ---- the night *count* -------------------------------------------------
#
# The window above says *when*; only the recorded hours say *how many nights*.
# 15→18 Nov is equally consistent with two nights and with four, and the count
# is the half of the sentence that says how much work a picture was.


def _hours(*stamps: str) -> str:
    return json.dumps(list(stamps))


def test_two_nights_of_subs_count_as_two():
    hours = _hours(
        "2024-11-15T22:00:00Z", "2024-11-15T23:00:00Z",  # night of the 15th
        "2024-11-16T02:00:00Z",                          # still the 15th
        "2024-11-18T21:00:00Z",                          # night of the 18th
    )
    assert capture_night_dates(hours) == ["2024-11-15", "2024-11-18"]
    assert capture_night_count(hours) == 2


def test_a_span_of_four_days_can_be_two_nights():
    """The exact ambiguity this column exists to remove: the same window, two
    different truthful counts, decided only by the hours in between."""
    window = ("2024-11-15T22:00:00Z", "2024-11-18T22:00:00Z")
    assert capture_night_range(*window) == ("2024-11-15", "2024-11-18")
    assert capture_night_count(_hours(*window)) == 2
    assert capture_night_count(_hours(
        *window, "2024-11-16T22:00:00Z", "2024-11-17T22:00:00Z")) == 4


def test_the_count_follows_the_observer_not_utc():
    """Same hours, same helper as the range: an evening in New Zealand
    (lon +150° ⇒ UTC+10) that straddles UTC noon is one night, not two — so the
    count can never contradict the dates the caption names."""
    hours = _hours("2024-11-15T10:00:00Z", "2024-11-15T18:00:00Z")
    assert capture_night_count(hours) == 2          # no location: UTC splits it
    assert capture_night_count(hours, 150.0) == 1
    assert capture_night_dates(hours, 150.0) == ["2024-11-15"]


def test_an_unrecorded_or_unreadable_count_is_none_not_zero():
    """A run from before the app tracked this reads as *silence*. Zero would
    caption a picture as shot on no nights at all."""
    for bad in (None, "", "not json", '{"nights": 4}', "[]", '["nonsense"]'):
        assert capture_night_dates(bad) == []
        assert capture_night_count(bad) is None


def test_a_junk_entry_does_not_take_the_rest_with_it():
    hours = json.dumps(["2024-11-15T22:00:00Z", None, 7, "not-a-date"])
    assert capture_night_count(hours) == 1


# --- cumulative_night_steps: "is the history he already has the reel he asked
#     for?" ------------------------------------------------------------------


def test_a_nested_history_is_the_reel_the_owner_asked_for():
    """Night 1, then nights 1-2, then nights 1-2-3-4: the running night count is
    what lets the card say "up to all 4 nights" instead of "4 stacks"."""
    assert cumulative_night_steps([
        ["2026-05-01"],
        ["2026-05-01", "2026-05-02"],
        ["2026-05-01", "2026-05-02", "2026-05-03", "2026-05-04"],
    ]) == [1, 2, 4]


def test_the_order_the_nights_are_listed_in_does_not_matter():
    """They are sets, not sequences — ``capture_night_dates`` sorts them, but a
    caller that did not must get the same answer."""
    assert cumulative_night_steps([
        ["2026-05-02"],
        ["2026-05-02", "2026-05-01"],
    ]) == [1, 2]


def test_a_reprocess_of_the_same_nights_is_not_a_step():
    """Re-stacking the nights you already had is not a step deeper into the pile,
    so the series is not the cumulative one and nothing is claimed about it."""
    assert cumulative_night_steps([
        ["2026-05-01", "2026-05-02"],
        ["2026-05-01", "2026-05-02"],
    ]) is None


def test_a_restack_of_a_subset_is_not_a_step_either():
    """"I re-stacked just tonight's subs" drops nights the previous step had —
    which `deepening_series` deliberately keeps in the reel, and which this must
    not describe as "nights 1-2"."""
    assert cumulative_night_steps([
        ["2026-05-01", "2026-05-02"],
        ["2026-05-03"],
    ]) is None
    # Adding one night while dropping another is not nesting either.
    assert cumulative_night_steps([
        ["2026-05-01", "2026-05-02"],
        ["2026-05-02", "2026-05-03"],
    ]) is None


def test_one_step_with_no_nights_recorded_silences_the_whole_series():
    """A run from before the app recorded capture hours leaves a hole, and a
    series with a hole in it cannot be *shown* to be nested — "nights 1-3" over a
    step that might be nights 2-4 is worse than the date it carries today."""
    assert cumulative_night_steps([
        ["2026-05-01"],
        [],
        ["2026-05-01", "2026-05-02", "2026-05-03"],
    ]) is None
    assert cumulative_night_steps([[], ["2026-05-01"]]) is None


def test_a_series_too_short_to_be_a_progression_says_nothing():
    assert cumulative_night_steps([]) is None
    assert cumulative_night_steps([["2026-05-01"]]) is None


def test_the_nights_come_from_the_same_bucketing_as_the_dates():
    """End to end through `capture_night_dates`, so the counts this returns and
    the dates the caption names can never be computed two different ways —
    including under a longitude, where the New Zealand evening above is one night
    rather than two."""
    night_one = _hours("2024-11-15T10:00:00Z", "2024-11-15T18:00:00Z")
    both = _hours("2024-11-15T10:00:00Z", "2024-11-15T18:00:00Z",
                  "2024-11-16T10:00:00Z")
    assert cumulative_night_steps([
        capture_night_dates(night_one, 150.0),
        capture_night_dates(both, 150.0),
    ]) == [1, 2]
    # And the longitude is load-bearing rather than decorative: with no location
    # the very same hours bucket noon-to-noon in UTC, which puts the 16th's
    # pre-noon hour back into a night the first step already had — so the two
    # steps hold the identical set, the series is not nested, and the card says
    # nothing rather than counting a night twice.
    assert capture_night_dates(both) == capture_night_dates(night_one)
    assert cumulative_night_steps([
        capture_night_dates(night_one),
        capture_night_dates(both),
    ]) is None
