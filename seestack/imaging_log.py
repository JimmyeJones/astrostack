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
processing stamp keeps its place at the end, under "Stacked". And the rows are
**ordered by the night too** (:func:`imaging_log_sort_key`) — the column the file
leads with had been left non-monotonic by a sort on the processing stamp, which
after a "Reprocess everything" put the whole log in an order unrelated to when
anything was shot.

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


def imaging_log_sort_key(row: ImagingLogRow) -> tuple[str, str]:
    """How recent this row is, for a **descending** sort: ``(night, stacked)``.

    A log of "every night you've imaged" is ordered by the *night*, which is the
    column it leads with — not by the afternoon the computer did its part. The
    two used to disagree: the caller sorted on the processing stamp while the
    leading column carried the capture window, so the log's first column was not
    monotonic, and after a **Reprocess everything** (which re-stamps every run
    within minutes of each other) the whole file came out in an order that has
    nothing to do with when anything was shot. Every row shows both dates, so
    neither value is hidden by this — only which one decides the order.

    ``capture_night_start`` is already the noon-to-noon night key
    (``webapp.capture_nights``), so comparing the ISO strings *is* comparing
    nights. A run recorded before the app tracked the window (schema < 18, i.e.
    most of a library upgraded rather than re-stacked) has no night, and falls
    back to its processing date — the same "use the labelled stamp when the real
    date is unknown" rule ``pictureDateLabel`` applies on screen, so the order
    always follows the date each row actually displays. The stacked stamp is the
    tie-break, so two re-stacks of one night lead with the newer run.

    **Not** in tension with the shipped rule "never flip a *sort* to capture
    time" (see ``SHIPPED.md``, "sweep every date"): that rule is about lists of
    **runs**, where "which run is newest" is the question — History's ordering,
    and the Library tile's. This file is a list of **nights**.
    """
    night = (row.capture_night_start or "").strip()[:10]
    stacked = _format_date(row.date)
    return (night or stacked, stacked)


def build_imaging_log_csv(rows: list[ImagingLogRow]) -> str:
    """Render the imaging-log rows to CSV text (header + one line per run).

    Ordered here, newest night first (:func:`imaging_log_sort_key`), rather than
    by the caller: one place decides both the columns and the order, so the
    leading column and the row order cannot end up answering different
    questions. The sort is stable, so rows the key cannot separate keep the
    order they arrived in. An empty list yields a header-only file, never an
    error, so a brand-new library still downloads a valid (if empty) log.
    """
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(IMAGING_LOG_COLUMNS)
    for row in sorted(rows, key=imaging_log_sort_key, reverse=True):
        writer.writerow(imaging_log_row_values(row))
    return buf.getvalue()
