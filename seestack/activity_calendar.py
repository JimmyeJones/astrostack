"""Your imaging calendar — a temporal, whole-hobby activity heatmap.

The app already answers *what did I shoot?* per target and *what did last night
give me?*, but nothing shows a beginner the **rhythm** of their hobby across
time: how many nights they've been out this month, when the last good clear run
was, whether they're keeping it up. Those are the motivating, come-back-tomorrow
questions a hobbyist asks — the astro equivalent of a fitness app's activity
ring — and the raw material (every sub's capture timestamp + exposure) is
already sitting in the library's frames tables.

This module turns those timestamps into a GitHub-contributions-style calendar:
one cell per **observing night**, shaded by how much you captured that night.
It is pure, offline and deterministic — it just folds ``(timestamp, exposure,
target)`` tuples into per-night buckets — so it needs no network and is trivially
testable.

Observing-night convention
--------------------------
A single night's subs straddle local midnight (you start after dusk and shoot
past 12), so bucketing on the raw calendar date would split one session across
two cells. Instead we bucket on the **observing night**: the date of the local
*noon-to-noon* window a timestamp falls in — i.e. shift the local time back 12 h
and take the date. Everything from local noon on day *D* to local noon on *D+1*
is "the night of *D*". This matches the same-night-across-midnight grouping the
session recap already relies on, and is the standard astronomical convention.

"Local" is derived from the observer's longitude when it's known (each 15° of
east longitude ≈ 1 h ahead of UTC — an offline, dependency-free approximation
that is plenty accurate for a whole-night bucket). With no configured location
we fall back to UTC noon-to-noon, which still groups a night correctly for most
observers and is fully deterministic.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

# Days per month used to size the "last N months" window from a month count.
# Approximate on purpose — the window is a friendly horizon, not an exact
# calendar boundary, and keeping it day-based makes the result deterministic
# without a calendar-math dependency.
_DAYS_PER_MONTH = 30.4375


def _parse_utc(timestamp_utc: str) -> datetime | None:
    """Parse an ISO-8601 capture timestamp into an aware UTC datetime, or None.

    Frames store ``timestamp_utc`` as an ISO string (usually ``...Z`` or with an
    offset, occasionally naive). We treat a naive stamp as UTC. Anything
    unparseable yields None so a single bad row is skipped, never fatal."""
    if not timestamp_utc:
        return None
    s = timestamp_utc.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def night_date_of(timestamp_utc: str, lon_deg: float | None = None) -> date | None:
    """The observing-night date a capture timestamp belongs to (see module docs),
    or None when the timestamp can't be parsed.

    ``lon_deg`` is the observer's longitude (+E); when given it approximates local
    time as ``UTC + lon/15`` hours. The night is the date of ``local_time − 12 h``,
    so a whole dusk-to-dawn session lands in one cell regardless of midnight."""
    dt = _parse_utc(timestamp_utc)
    if dt is None:
        return None
    offset_h = (lon_deg / 15.0) if lon_deg is not None else 0.0
    local = dt + timedelta(hours=offset_h)
    return (local - timedelta(hours=12)).date()


@dataclass
class _NightAgg:
    """Mutable per-night accumulator used while folding frames."""

    exposure_s: float = 0.0
    n_frames: int = 0
    targets: set[str] = field(default_factory=set)


@dataclass
class NightActivity:
    """One imaged night in the calendar."""

    date: str            # observing-night date, ISO ``YYYY-MM-DD``
    exposure_s: float    # Σ exposure of every sub captured that night
    n_frames: int        # subs captured that night (kept or set aside)
    targets: list[str]   # distinct target names shot that night (sorted)


@dataclass
class ActivityCalendar:
    """The whole-hobby activity heatmap over a trailing window of nights."""

    start_date: str          # first day of the window, ISO
    end_date: str            # last day of the window (``today``), ISO
    months: int              # the requested window size, in months
    nights: list[NightActivity]  # imaged nights in the window, date-ascending
    n_nights: int            # how many nights were imaged in the window
    total_exposure_s: float  # Σ exposure across the window
    nights_this_month: int   # imaged nights in ``today``'s calendar month
    best_streak_nights: int  # longest run of consecutive imaged nights in the window


def accumulate_nights(
    entries: Iterable[tuple[str | None, float | None, str]],
    acc: dict[date, _NightAgg],
    *,
    lon_deg: float | None = None,
) -> None:
    """Fold ``(timestamp_utc, exposure_s, target_name)`` tuples into ``acc``
    (keyed by observing-night date), summing exposure and counting subs.

    Mutates ``acc`` in place so a caller can stream one target's frames at a time
    without ever holding the whole library's frame list in memory. A tuple with
    an unparseable/empty timestamp is skipped; a missing exposure counts as 0 s
    but still marks the night as imaged."""
    for timestamp_utc, exposure_s, target_name in entries:
        if not timestamp_utc:
            continue
        night = night_date_of(timestamp_utc, lon_deg)
        if night is None:
            continue
        agg = acc.get(night)
        if agg is None:
            agg = acc[night] = _NightAgg()
        agg.exposure_s += float(exposure_s) if exposure_s else 0.0
        agg.n_frames += 1
        if target_name:
            agg.targets.add(target_name)


def _best_streak(nights: list[date]) -> int:
    """Longest run of consecutive calendar dates in a sorted, de-duplicated list."""
    best = run = 0
    prev: date | None = None
    for d in nights:
        if prev is not None and (d - prev).days == 1:
            run += 1
        else:
            run = 1
        best = max(best, run)
        prev = d
    return best


def finalize_calendar(
    acc: dict[date, _NightAgg], *, today: date, months: int,
) -> ActivityCalendar:
    """Turn a folded night accumulator into the trailing-window calendar.

    Keeps only nights within the last ``months`` (approximately, day-based) up to
    and including ``today``; nights outside the window are dropped. ``today`` is
    injected (not read from the clock) so the result is deterministic and
    testable."""
    months = max(1, int(months))
    window_days = int(round(months * _DAYS_PER_MONTH))
    start = today - timedelta(days=window_days - 1)

    in_window = {d: a for d, a in acc.items() if start <= d <= today}
    ordered = sorted(in_window)

    nights = [
        NightActivity(
            date=d.isoformat(),
            exposure_s=round(in_window[d].exposure_s, 3),
            n_frames=in_window[d].n_frames,
            targets=sorted(in_window[d].targets),
        )
        for d in ordered
    ]
    total = round(sum(a.exposure_s for a in in_window.values()), 3)
    this_month = sum(
        1 for d in ordered if d.year == today.year and d.month == today.month
    )
    return ActivityCalendar(
        start_date=start.isoformat(),
        end_date=today.isoformat(),
        months=months,
        nights=nights,
        n_nights=len(nights),
        total_exposure_s=total,
        nights_this_month=this_month,
        best_streak_nights=_best_streak(ordered),
    )


def build_activity_calendar(
    entries: Iterable[tuple[str | None, float | None, str]],
    *,
    today: date,
    months: int = 12,
    lon_deg: float | None = None,
) -> ActivityCalendar:
    """Convenience one-shot: fold ``entries`` and finalize in a single call.

    The webapp streams frames per target into :func:`accumulate_nights` instead
    (to stay memory-bounded across a big library); this helper is for callers
    that already have all the tuples in hand (and for tests)."""
    acc: dict[date, _NightAgg] = {}
    accumulate_nights(entries, acc, lon_deg=lon_deg)
    return finalize_calendar(acc, today=today, months=months)
