"""The pure "Your year under the stars" recap — :mod:`seestack.yearrecap`.

The module folds the activity calendar's nights into one calendar year, so the
tests below are mostly about *boundaries* (a night in December is not in
January's year), *honesty* (a standout is named only when the data supports it),
and *one voice* (the same night numbers the heatmap shows).
"""

from __future__ import annotations

from seestack.activity_calendar import NightActivity
from seestack.yearrecap import (
    LONGEST_MIN_NIGHTS,
    build_year_recap,
    first_night_by_target,
    longest_night,
    year_empty_message,
    year_first_light_line,
    year_headline,
    year_stats,
    years_with_data,
)


def night(date: str, *, exposure_s=3600.0, n_frames=60, targets=("M 31",),
          fwhm=None, n_measured=0) -> NightActivity:
    return NightActivity(
        date=date, exposure_s=exposure_s, n_frames=n_frames,
        targets=list(targets), median_fwhm_px=fwhm, n_measured=n_measured,
    )


# --- the year boundary ------------------------------------------------------

def test_year_counts_only_that_years_nights():
    nights = [
        night("2025-12-31", exposure_s=100.0, n_frames=2),
        night("2026-01-01", exposure_s=200.0, n_frames=4),
        night("2026-07-04", exposure_s=300.0, n_frames=6),
        night("2027-01-01", exposure_s=400.0, n_frames=8),
    ]
    r = build_year_recap(nights, year=2026)
    assert r.has_anything
    assert r.n_nights == 2
    assert r.total_exposure_s == 500.0
    assert r.n_frames == 10
    assert [n.date for n in r.nights] == ["2026-01-01", "2026-07-04"]


def test_new_years_eve_and_new_years_day_land_in_different_years():
    # The observing-night convention means a session that runs past midnight is
    # already bucketed on its *start* date, so the year boundary is exactly the
    # night label's own year — no off-by-one at the turn of the year.
    nights = [night("2025-12-31"), night("2026-01-01")]
    assert build_year_recap(nights, year=2025).n_nights == 1
    assert build_year_recap(nights, year=2026).n_nights == 1


def test_years_with_data_lists_every_year_ascending():
    nights = [night("2027-03-01"), night("2025-05-05"), night("2025-06-06")]
    assert years_with_data(nights) == (2025, 2027)
    # …and it is reported even for a year that has nothing, so an empty year can
    # point somewhere useful.
    assert build_year_recap(nights, year=2026).years_with_data == (2025, 2027)


def test_unparseable_night_date_is_skipped_not_fatal():
    nights = [night("not-a-date"), night("2026-02-02", exposure_s=60.0)]
    r = build_year_recap(nights, year=2026)
    assert r.n_nights == 1
    assert r.total_exposure_s == 60.0


# --- targets and first light ------------------------------------------------

def test_targets_are_distinct_across_the_years_nights():
    nights = [
        night("2026-01-01", targets=("M 31", "M 42")),
        night("2026-01-02", targets=("M 42",)),
    ]
    r = build_year_recap(nights, year=2026)
    assert r.n_targets == 2
    assert r.target_names == ("M 31", "M 42")


def test_first_light_is_measured_against_the_whole_history_not_the_year():
    # M 31 was first shot in 2025, so 2026 is not its first light however many
    # 2026 nights it appears on. NGC 7000 is genuinely new in 2026.
    nights = [
        night("2025-06-01", targets=("M 31",)),
        night("2026-02-01", targets=("M 31",)),
        night("2026-03-01", targets=("NGC 7000",)),
    ]
    r = build_year_recap(nights, year=2026)
    assert r.first_light_names == ("NGC 7000",)
    assert first_night_by_target(nights)["M 31"].year == 2025


def test_first_lights_are_ordered_by_when_you_first_saw_them():
    nights = [
        night("2026-05-01", targets=("NGC 7000",)),
        night("2026-02-01", targets=("M 42",)),
        night("2026-02-01", targets=("M 42", "M 45")),
    ]
    r = build_year_recap(nights, year=2026)
    assert r.first_light_names == ("M 42", "M 45", "NGC 7000")


def test_first_light_line_spells_out_three_then_counts_the_rest():
    r = build_year_recap(
        [night(f"2026-01-0{i}", targets=(f"T{i}",)) for i in range(1, 6)],
        year=2026,
    )
    assert year_first_light_line(r) == "First light: T1, T2, T3 and 2 more"


def test_first_light_line_reads_as_a_sentence_when_short():
    one = build_year_recap([night("2026-01-01", targets=("M 31",))], year=2026)
    assert year_first_light_line(one) == "First light: M 31"
    two = build_year_recap(
        [night("2026-01-01", targets=("M 31", "M 42"))], year=2026)
    assert year_first_light_line(two) == "First light: M 31 and M 42"


def test_first_light_line_is_empty_when_nothing_is_new():
    nights = [night("2025-01-01", targets=("M 31",)),
              night("2026-01-01", targets=("M 31",))]
    assert year_first_light_line(build_year_recap(nights, year=2026)) == ""


# --- the standout nights ----------------------------------------------------

def test_longest_night_is_the_one_with_the_most_light():
    nights = [
        night("2026-01-01", exposure_s=600.0),
        night("2026-01-05", exposure_s=7200.0),
        night("2026-01-09", exposure_s=1800.0),
    ]
    r = build_year_recap(nights, year=2026)
    assert r.longest_night is not None
    assert r.longest_night.date == "2026-01-05"


def test_longest_night_ties_break_on_the_earlier_date():
    nights = [night("2026-02-02", exposure_s=900.0),
              night("2026-01-01", exposure_s=900.0)]
    assert build_year_recap(nights, year=2026).longest_night.date == "2026-01-01"


def test_longest_night_is_not_named_on_a_single_night_year():
    # "Your longest night" on a one-night year is that night wearing a rosette.
    assert LONGEST_MIN_NIGHTS == 2
    r = build_year_recap([night("2026-01-01", exposure_s=3600.0)], year=2026)
    assert r.has_anything and r.n_nights == 1
    assert r.longest_night is None


def test_longest_night_ignores_nights_that_collected_no_light():
    nights = [night("2026-01-01", exposure_s=0.0),
              night("2026-01-02", exposure_s=0.0)]
    assert longest_night(nights) is None


def test_sharpest_night_uses_the_apps_one_definition():
    # Five measured subs is the floor `activity_calendar.sharpest_night` sets,
    # and two qualifying nights the minimum before naming a best one — reused
    # here rather than re-invented, so the year page and the "best night" card
    # can never disagree about which night was sharp.
    nights = [
        night("2026-01-01", fwhm=4.2, n_measured=20),
        night("2026-01-02", fwhm=2.8, n_measured=20),
        night("2026-01-03", fwhm=1.1, n_measured=2),   # too few to qualify
    ]
    r = build_year_recap(nights, year=2026)
    assert r.sharpest_night is not None
    assert r.sharpest_night.date == "2026-01-02"


def test_sharpest_night_is_silent_when_only_one_night_qualifies():
    nights = [night("2026-01-01", fwhm=3.0, n_measured=20),
              night("2026-01-02", fwhm=None)]
    assert build_year_recap(nights, year=2026).sharpest_night is None


# --- the words --------------------------------------------------------------

def test_headline_reads_as_a_sentence():
    nights = [night(f"2026-01-{d:02d}", exposure_s=3600.0, targets=("M 31", "M 42"))
              for d in range(1, 32)]
    r = build_year_recap(nights, year=2026)
    assert year_headline(r) == (
        "You were out under the stars on 31 nights in 2026 and collected "
        "31 h of light on 2 targets."
    )


def test_headline_is_singular_on_a_one_night_one_target_year():
    r = build_year_recap([night("2026-01-01", exposure_s=1800.0)], year=2026)
    assert year_headline(r) == (
        "You were out under the stars on 1 night in 2026 and collected "
        "30 min of light on 1 target."
    )


def test_headline_drops_a_clause_it_cannot_support():
    # A night that was logged but collected no measurable light must not read
    # "collected 0 s of light" — the clause is dropped, not zeroed.
    r = build_year_recap(
        [night("2026-01-01", exposure_s=0.0), night("2026-01-02", exposure_s=0.0)],
        year=2026,
    )
    assert "of light" not in year_headline(r)
    assert year_headline(r).startswith("You were out under the stars on 2 nights")


def test_headline_is_empty_for_a_year_with_nothing_in_it():
    assert year_headline(build_year_recap([], year=2026)) == ""


def test_stats_are_headline_pairs_with_zeros_dropped():
    nights = [night("2026-01-01", exposure_s=3600.0, n_frames=60,
                    targets=("M 31",)),
              night("2026-01-02", exposure_s=3600.0, n_frames=60,
                    targets=("M 31",))]
    pairs = year_stats(build_year_recap(nights, year=2026))
    assert pairs[0] == ("2.0 h", "of light collected")
    assert ("2", "nights out") in pairs
    assert ("1", "target imaged") in pairs
    assert ("1", "first light") in pairs
    assert ("120", "subs kept") in pairs


def test_stats_are_empty_for_a_year_with_nothing_in_it():
    assert year_stats(build_year_recap([], year=2026)) == []


# --- the empty year ---------------------------------------------------------

def test_empty_year_points_at_the_years_that_do_have_data():
    nights = [night("2024-01-01"), night("2025-01-01")]
    r = build_year_recap(nights, year=2026)
    assert not r.has_anything
    assert r.n_nights == 0 and r.total_exposure_s == 0.0
    assert year_empty_message(r) == (
        "Nothing from 2026 — but 2024 and 2025 have your nights in them.")


def test_empty_year_names_a_single_other_year_in_the_singular():
    r = build_year_recap([night("2025-01-01")], year=2026)
    assert year_empty_message(r) == (
        "Nothing from 2026 — but 2025 has your nights in it.")


def test_empty_library_says_so_kindly_without_naming_a_year():
    r = build_year_recap([], year=2026)
    assert not r.has_anything
    assert r.years_with_data == ()
    assert year_empty_message(r) == (
        "No nights recorded in 2026 yet. Once you've captured and kept some "
        "frames, your year will appear here.")


def test_a_year_with_data_has_no_empty_message():
    assert year_empty_message(build_year_recap([night("2026-01-01")], year=2026)) == ""
