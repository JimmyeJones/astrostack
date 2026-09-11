"""Unit tests for the pure imaging-log CSV builder (``seestack/imaging_log.py``).

The webapp gathers ``ImagingLogRow`` values from the library; these cover the
pure formatting + CSV rendering with no webapp/DB in the loop.
"""

from __future__ import annotations

import csv
import io

from seestack.imaging_log import (
    IMAGING_LOG_COLUMNS,
    ImagingLogRow,
    build_imaging_log_csv,
    imaging_log_row_values,
)


def _row(**kw) -> ImagingLogRow:
    base = dict(
        date="2026-07-24T21:03:11+00:00",
        target_name="M 31",
        n_subs=120,
        integration_s=3600.0,
        median_fwhm_px=2.4,
        calibration="dark+flat",
        is_mosaic=False,
        noise_sigma=0.0123,
        app_version="0.192.0",
        capture_night_start="2026-07-19",
        capture_night_end="2026-07-19",
    )
    base.update(kw)
    return ImagingLogRow(**base)


def _parse(csv_text: str) -> list[list[str]]:
    return list(csv.reader(io.StringIO(csv_text)))


def test_empty_library_yields_header_only():
    rows = _parse(build_imaging_log_csv([]))
    assert rows == [IMAGING_LOG_COLUMNS]


def test_one_row_per_run_with_expected_columns():
    parsed = _parse(build_imaging_log_csv([_row(), _row(target_name="M 42")]))
    assert parsed[0] == IMAGING_LOG_COLUMNS
    assert len(parsed) == 3  # header + 2 runs
    assert parsed[1][1] == "M 31"
    assert parsed[2][1] == "M 42"


def test_row_values_are_beginner_legible():
    vals = imaging_log_row_values(_row())
    # The leading column is the night the subs were SHOT, not the day the stack
    # ran — a log of "every night you've imaged" that led with the processing
    # stamp dated a re-stack of a back catalogue to the afternoon it was made.
    assert vals[0] == "2026-07-19"
    assert vals[1] == "M 31"
    assert vals[2] == "120"
    # Integration is a plain duration, never raw seconds.
    assert vals[3] == "1.0 h"
    assert vals[4] == "2.4"
    assert vals[5] == "dark+flat"
    assert vals[6] == "no"
    assert vals[7] == "0.0123"
    assert vals[8] == "0.192.0"
    # …and the processing stamp is still here, at the end, under its real name.
    assert vals[9] == "2026-07-24"


def test_the_two_dates_are_labelled_and_neither_moved_the_other_s_columns():
    """`Shot` leads, `Stacked` is appended — an existing spreadsheet keeps every
    column it had, and nothing is lost."""
    assert IMAGING_LOG_COLUMNS[0] == "Shot"
    assert IMAGING_LOG_COLUMNS[-1] == "Stacked"
    assert IMAGING_LOG_COLUMNS[1:-1] == [
        "Target", "Subs used", "Integration", "Typical star size (px)",
        "Calibration", "Mosaic", "Noise (lower is cleaner)", "App version",
    ]
    assert len(imaging_log_row_values(_row())) == len(IMAGING_LOG_COLUMNS)


def test_a_multi_night_stack_names_the_span():
    vals = imaging_log_row_values(
        _row(capture_night_start="2024-11-15", capture_night_end="2024-11-18"))
    # "to", not an en dash: this is a spreadsheet cell, where a dash reads as
    # arithmetic.
    assert vals[0] == "2024-11-15 to 2024-11-18"
    # A window recorded end-first still reads in the order a person expects.
    assert imaging_log_row_values(
        _row(capture_night_start="2024-11-18",
             capture_night_end="2024-11-15"))[0] == "2024-11-15 to 2024-11-18"
    # One end alone is one honest night, not half a range.
    assert imaging_log_row_values(
        _row(capture_night_start=None, capture_night_end="2024-11-18"))[0] == "2024-11-18"


def test_a_run_from_before_the_app_tracked_nights_says_nothing_rather_than_guessing():
    """The date-honesty rule: never reach for the stamp that is to hand. A
    pre-schema-18 run has no window, so the column is blank — the stack date is
    still there in `Stacked`, where it is true."""
    vals = imaging_log_row_values(
        _row(capture_night_start=None, capture_night_end=None))
    assert vals[0] == ""
    assert vals[9] == "2026-07-24"


def test_integration_formats():
    # The app's one integration vocabulary (see
    # `tests/fixtures/integration_format.json`) — not a third spelling for the
    # log column a beginner pastes beside the picture's own page.
    assert imaging_log_row_values(_row(integration_s=3600 + 24 * 60))[3] == "1.4 h"
    assert imaging_log_row_values(_row(integration_s=18 * 60))[3] == "18 min"
    assert imaging_log_row_values(_row(integration_s=7200))[3] == "2.0 h"
    # Unknown / zero / negative → blank, never a wrong value.
    assert imaging_log_row_values(_row(integration_s=None))[3] == ""
    assert imaging_log_row_values(_row(integration_s=0))[3] == ""


def test_missing_optionals_render_blank_not_error():
    vals = imaging_log_row_values(_row(
        date=None, n_subs=None, integration_s=None, median_fwhm_px=None,
        calibration=None, is_mosaic=None, noise_sigma=None, app_version=None,
        capture_night_start=None, capture_night_end=None,
    ))
    # Calibration reads plainly as "none"; everything else blanks out — both
    # date columns included.
    assert vals == ["", "M 31", "", "", "", "none", "", "", "", ""]


def test_mosaic_flag_wording():
    assert imaging_log_row_values(_row(is_mosaic=True))[6] == "yes"
    assert imaging_log_row_values(_row(is_mosaic=False))[6] == "no"
    assert imaging_log_row_values(_row(is_mosaic=None))[6] == ""


def test_the_log_is_ordered_by_the_night_it_leads_with_not_the_day_it_was_stacked():
    """The bug the ordering had: the leading column is the *night*, and the sort
    was on the *processing stamp*, so the first column of the file was not
    monotonic. The fixture is a re-stack of a back catalogue done in one sitting
    — exactly what "Reprocess everything" produces — where the two orders are
    opposite.
    """
    old_night_restacked_last = _row(
        target_name="old night", capture_night_start="2024-11-15",
        capture_night_end="2024-11-15", date="2026-07-24T15:00:00+00:00")
    new_night_restacked_first = _row(
        target_name="new night", capture_night_start="2026-06-01",
        capture_night_end="2026-06-01", date="2026-07-24T09:00:00+00:00")
    parsed = _parse(build_imaging_log_csv(
        [old_night_restacked_last, new_night_restacked_first]))
    assert [r[1] for r in parsed[1:]] == ["new night", "old night"]
    # Both dates are still on every row — the fix moved which one *orders*, not
    # which one is shown.
    assert parsed[1][0] == "2026-06-01" and parsed[1][-1] == "2026-07-24"


def test_two_restacks_of_one_night_lead_with_the_newer_run():
    """The tie-break: the night cannot separate them, so "which run is newest"
    decides — the one question the processing stamp is the right answer to."""
    parsed = _parse(build_imaging_log_csv([
        _row(target_name="older run", date="2026-07-20T09:00:00+00:00"),
        _row(target_name="newer run", date="2026-07-24T09:00:00+00:00"),
    ]))
    assert [r[1] for r in parsed[1:]] == ["newer run", "older run"]


def test_a_run_with_no_recorded_night_is_placed_by_the_date_it_does_show():
    """A pre-schema-18 run (most of a library that was upgraded rather than
    re-stacked) has no night, so it is ordered by its processing date — the same
    "fall back to the labelled stamp" rule the screen's date label uses, so the
    order always follows the date the row actually displays. It must not sink to
    the bottom of an upgraded library's whole log, and must not claim a night."""
    parsed = _parse(build_imaging_log_csv([
        _row(target_name="night known", capture_night_start="2024-11-15",
             capture_night_end="2024-11-15", date="2026-07-01T09:00:00+00:00"),
        _row(target_name="no night", capture_night_start=None,
             capture_night_end=None, date="2026-07-20T09:00:00+00:00"),
    ]))
    assert [r[1] for r in parsed[1:]] == ["no night", "night known"]
    assert parsed[1][0] == ""


def test_rows_the_ordering_cannot_separate_keep_the_order_they_arrived_in():
    """A stable sort, so a caller's own grouping survives where the key ties."""
    parsed = _parse(build_imaging_log_csv([
        _row(target_name="M 31"), _row(target_name="M 42"),
        _row(target_name="M 81"),
    ]))
    assert [r[1] for r in parsed[1:]] == ["M 31", "M 42", "M 81"]


def test_a_row_with_no_dates_at_all_still_renders():
    parsed = _parse(build_imaging_log_csv([
        _row(target_name="dateless", date=None,
             capture_night_start=None, capture_night_end=None),
        _row(target_name="dated"),
    ]))
    assert [r[1] for r in parsed[1:]] == ["dated", "dateless"]
