"""Your imaging log — a plain, downloadable record of every night you've imaged.

A beginner keepsake: one row per finished stack, listing the nights it was shot
on, the target, how many subs went in, total integration time, typical star
sharpness, whether calibration was applied, the app version, and the day it was
stacked — the numbers the app already computes and shows scattered across
per-target pages, gathered into one tidy CSV you can open in any spreadsheet,
print, or paste into a forum post.

**The two dates are different facts and the log says which is which.** Its
leading column used to be headed "Date" and filled with the *stack's* timestamp,
so a log of "every night you've imaged" dated a re-stack of a back catalogue to
the afternoon the button was pressed. The nights now lead, under "Shot"; the
processing stamp keeps its place at the end, under "Stacked".

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

    date: str | None  # ISO timestamp (UTC) the stack was **produced** (not shot)
    target_name: str
    n_subs: int | None  # frames combined into the stack
    integration_s: float | None  # effective integration time (seconds)
    median_fwhm_px: float | None  # typical star size for this target (sharpness)
    calibration: str | None  # "dark+flat" / "flat" / None (nothing applied)
    is_mosaic: bool | None
    noise_sigma: float | None  # normalized background noise (lower = cleaner)
    app_version: str | None  # AstroStack version that produced the run
    #: The observing nights this stack's subs were **shot** on (ISO
    #: ``YYYY-MM-DD``, the noon-to-noon bucket every other night surface uses),
    #: equal for a single-night stack. This is what a log of "every night you've
    #: imaged" is *about*; ``date`` above is when the computer did its part, and
    #: filling the log's leading column with it dated a re-stack of a back
    #: catalogue to the afternoon someone pressed the button. Both ``None`` on a
    #: run recorded before the app tracked the window (schema 18), which prints
    #: blank rather than falling back to the stamp it has to hand.
    capture_night_start: str | None = None
    capture_night_end: str | None = None


# Column order for the CSV. Kept plain-language (no astro jargon) so a beginner
# reading it in a spreadsheet immediately understands each field.
#
# "Stacked" is deliberately *appended* rather than inserted beside "Shot": a user
# who has already built a spreadsheet on this file keeps every column where it
# was, and the value that used to head the row is still here under its real name.
IMAGING_LOG_COLUMNS = [
    "Shot",
    "Target",
    "Subs used",
    "Integration",
    "Typical star size (px)",
    "Calibration",
    "Mosaic",
    "Noise (lower is cleaner)",
    "App version",
    "Stacked",
]


def _format_date(iso: str | None) -> str:
    """The calendar date (UTC) from an ISO timestamp; ``""`` when unknown.

    Timestamps are stored ISO-8601 (e.g. ``2026-07-24T21:03:11+00:00``); take the
    date portion without importing a parser — robust to a missing time component.
    """
    if not iso:
        return ""
    return iso.strip()[:10]


def _format_night_range(start: str | None, end: str | None) -> str:
    """The nights a stack's subs were shot on — ``"2024-11-15"``,
    ``"2024-11-15 to 2024-11-18"``, or ``""`` when the app never recorded them.

    Spelled "to" rather than an en dash on purpose: this is a spreadsheet cell,
    where ``2024-11-15 – 2024-11-18`` reads as arithmetic. A single night (or an
    end equal to, or missing from, the start) degrades to the one date, so a
    normal night's row is a plain ISO date any spreadsheet will parse.

    That — and keeping both dates in full — is all this spelling has to itself.
    Everything else about naming a window is
    :func:`seestack.nightrange.format_night_range`, shared with the screen and the
    baked caption, so the row a beginner exports describes the same night the
    same way the picture beside it does.
    """
    from seestack.nightrange import ISO, format_night_range

    return format_night_range(start, end, style=ISO)


def _format_integration(seconds: float | None) -> str:
    """``"3.4 h"`` / ``"18 min"`` / ``""`` — a legible duration, never raw seconds.

    Delegates to the app's one integration vocabulary (``sharecard`` mirrors the
    SPA's ``formatIntegration``) rather than spelling a third one: this log is
    the row a beginner pastes into a forum post beside the very picture whose
    page said "3.4 h", and it used to say "3h 24m".
    """
    from seestack.sharecard import format_duration

    return format_duration(seconds)


def _format_calibration(calstat: str | None) -> str:
    return calstat if calstat else "none"


def _format_number(value: float | None, digits: int) -> str:
    if value is None:
        return ""
    return f"{value:.{digits}f}"


def imaging_log_row_values(row: ImagingLogRow) -> list[str]:
    """The ordered cell values for one row (matches ``IMAGING_LOG_COLUMNS``)."""
    return [
        _format_night_range(row.capture_night_start, row.capture_night_end),
        row.target_name,
        "" if row.n_subs is None else str(row.n_subs),
        _format_integration(row.integration_s),
        _format_number(row.median_fwhm_px, 1),
        _format_calibration(row.calibration),
        "" if row.is_mosaic is None else ("yes" if row.is_mosaic else "no"),
        _format_number(row.noise_sigma, 4),
        row.app_version or "",
        _format_date(row.date),
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
