"""Your imaging log — a plain, downloadable record of every night you've imaged.

A beginner keepsake: one row per finished stack, listing the date, target, how
many subs went in, total integration time, typical star sharpness, whether
calibration was applied, and the app version — the numbers the app already
computes and shows scattered across per-target pages, gathered into one tidy CSV
you can open in any spreadsheet, print, or paste into a forum post.

Pure/offline/testable: the webapp gathers :class:`ImagingLogRow` values from the
library and hands them here to render the CSV. No engine recompute, no new DB
columns — every field is already stored on the run/frame records.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass


@dataclass(frozen=True)
class ImagingLogRow:
    """One finished stack, as it will appear in the imaging-log CSV."""

    date: str | None  # ISO timestamp (UTC) the stack was produced
    target_name: str
    n_subs: int | None  # frames combined into the stack
    integration_s: float | None  # effective integration time (seconds)
    median_fwhm_px: float | None  # typical star size for this target (sharpness)
    calibration: str | None  # "dark+flat" / "flat" / None (nothing applied)
    is_mosaic: bool | None
    noise_sigma: float | None  # normalized background noise (lower = cleaner)
    app_version: str | None  # AstroStack version that produced the run


# Column order for the CSV. Kept plain-language (no astro jargon) so a beginner
# reading it in a spreadsheet immediately understands each field.
IMAGING_LOG_COLUMNS = [
    "Date",
    "Target",
    "Subs used",
    "Integration",
    "Typical star size (px)",
    "Calibration",
    "Mosaic",
    "Noise (lower is cleaner)",
    "App version",
]


def _format_date(iso: str | None) -> str:
    """The calendar date (UTC) from an ISO timestamp; ``""`` when unknown.

    Timestamps are stored ISO-8601 (e.g. ``2026-07-24T21:03:11+00:00``); take the
    date portion without importing a parser — robust to a missing time component.
    """
    if not iso:
        return ""
    return iso.strip()[:10]


def _format_integration(seconds: float | None) -> str:
    """``"3h 24m"`` / ``"18m"`` / ``""`` — a legible duration, never raw seconds."""
    if seconds is None or seconds <= 0:
        return ""
    total_min = int(round(seconds / 60.0))
    hours, minutes = divmod(total_min, 60)
    if hours and minutes:
        return f"{hours}h {minutes}m"
    if hours:
        return f"{hours}h"
    return f"{minutes}m"


def _format_calibration(calstat: str | None) -> str:
    return calstat if calstat else "none"


def _format_number(value: float | None, digits: int) -> str:
    if value is None:
        return ""
    return f"{value:.{digits}f}"


def imaging_log_row_values(row: ImagingLogRow) -> list[str]:
    """The ordered cell values for one row (matches ``IMAGING_LOG_COLUMNS``)."""
    return [
        _format_date(row.date),
        row.target_name,
        "" if row.n_subs is None else str(row.n_subs),
        _format_integration(row.integration_s),
        _format_number(row.median_fwhm_px, 1),
        _format_calibration(row.calibration),
        "" if row.is_mosaic is None else ("yes" if row.is_mosaic else "no"),
        _format_number(row.noise_sigma, 4),
        row.app_version or "",
    ]


def build_imaging_log_csv(rows: list[ImagingLogRow]) -> str:
    """Render the imaging-log rows to CSV text (header + one line per run).

    Rows are written in the order given (the caller sorts newest-first). An empty
    list yields a header-only file, never an error, so a brand-new library still
    downloads a valid (if empty) log.
    """
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(IMAGING_LOG_COLUMNS)
    for row in rows:
        writer.writerow(imaging_log_row_values(row))
    return buf.getvalue()
