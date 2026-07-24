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
    # Date is the calendar day (UTC), not the full ISO timestamp.
    assert vals[0] == "2026-07-24"
    assert vals[1] == "M 31"
    assert vals[2] == "120"
    # Integration is a plain duration, never raw seconds.
    assert vals[3] == "1h"
    assert vals[4] == "2.4"
    assert vals[5] == "dark+flat"
    assert vals[6] == "no"
    assert vals[7] == "0.0123"
    assert vals[8] == "0.192.0"


def test_integration_formats():
    assert imaging_log_row_values(_row(integration_s=3600 + 24 * 60))[3] == "1h 24m"
    assert imaging_log_row_values(_row(integration_s=18 * 60))[3] == "18m"
    assert imaging_log_row_values(_row(integration_s=7200))[3] == "2h"
    # Unknown / zero / negative → blank, never a wrong value.
    assert imaging_log_row_values(_row(integration_s=None))[3] == ""
    assert imaging_log_row_values(_row(integration_s=0))[3] == ""


def test_missing_optionals_render_blank_not_error():
    vals = imaging_log_row_values(_row(
        date=None, n_subs=None, integration_s=None, median_fwhm_px=None,
        calibration=None, is_mosaic=None, noise_sigma=None, app_version=None,
    ))
    # Calibration reads plainly as "none"; everything else blanks out.
    assert vals == ["", "M 31", "", "", "", "none", "", "", ""]


def test_mosaic_flag_wording():
    assert imaging_log_row_values(_row(is_mosaic=True))[6] == "yes"
    assert imaging_log_row_values(_row(is_mosaic=False))[6] == "no"
    assert imaging_log_row_values(_row(is_mosaic=None))[6] == ""
