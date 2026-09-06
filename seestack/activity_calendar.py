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


def parse_utc(timestamp_utc: str) -> datetime | None:
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


#: The app writes UTC stamps in more than one shape — ``…Z`` from the job
#: manager and the library registry, a full ``isoformat()`` offset from the
#: stacker — so anything comparing two of them must parse rather than compare
#: strings. Kept as the module-private name this file has always used, with
#: :func:`parse_utc` as the public one other modules import.
_parse_utc = parse_utc


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


# How many *measured* subs a night needs before its median star size is worth
# quoting. A one- or two-frame median is the frame, not the night — and the
# whole point of "your best night" is that it says something about the night.
SHARPEST_MIN_MEASURED = 5

# And how many qualifying nights the library needs before naming a best one.
# "Your sharpest night" on a library with one measured night is just "your only
# night" wearing a rosette.
SHARPEST_MIN_NIGHTS = 2

# --- "Was last night off for you?" -----------------------------------------
#
# How many *earlier* qualifying nights are needed before there is a "usual" to
# measure the latest night against. Higher than SHARPEST_MIN_NIGHTS on purpose:
# naming the better of two nights is harmless, but telling someone a night went
# wrong on the strength of two prior nights is how a feature earns a reputation
# for crying wolf.
OFF_NIGHT_MIN_BASELINE_NIGHTS = 4

# Latest night's median star size ÷ the baseline. Seeing genuinely varies night
# to night for reasons nobody can fix, so the bar is set well past ordinary
# variation — this is a nudge to go and look at the lens, and it is only worth
# making when the answer is probably yes.
OFF_NIGHT_FATTER_ABOVE = 1.30
OFF_NIGHT_MUCH_FATTER_ABOVE = 1.60


def _median(values: list[float]) -> float | None:
    """Median of a non-empty list, or ``None``. Sorts a copy, so the input is
    left untouched (the caller keeps accumulating into it)."""
    if not values:
        return None
    s = sorted(values)
    mid = len(s) // 2
    return s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2.0


@dataclass
class _NightAgg:
    """Mutable per-night accumulator used while folding frames."""

    exposure_s: float = 0.0
    n_frames: int = 0
    targets: set[str] = field(default_factory=set)
    # Every *measured* star size captured that night, in pixels. Only frames QC
    # actually measured land here, so a night of unmeasured subs simply has no
    # star size rather than a fabricated one. Bounded by the frame count the
    # caller is already streaming.
    fwhms: list[float] = field(default_factory=list)


@dataclass
class NightActivity:
    """One imaged night in the calendar."""

    date: str            # observing-night date, ISO ``YYYY-MM-DD``
    exposure_s: float    # Σ exposure of every sub captured that night
    n_frames: int        # subs captured that night (kept or set aside)
    targets: list[str]   # distinct target names shot that night (sorted)
    # Typical star size that night (median of the subs QC measured), or None
    # when nothing on that night was measured. Additive — every field above is
    # unchanged, so an older consumer reads exactly what it always did.
    median_fwhm_px: float | None = None
    n_measured: int = 0  # subs that night with a measured star size


@dataclass
class OffNightRead:
    """A plain-language read on whether the most recent night went wrong."""

    level: str               # 'fatter' | 'much_fatter'
    label: str               # short chip text
    text: str                # one sentence: what was measured + what to check
    night: str               # ISO date of the night being reported
    baseline_nights: int     # earlier qualifying nights behind "your usual"
    ratio: float             # latest night's median FWHM ÷ the baseline's
    median_fwhm_px: float    # that night's median star size
    baseline_fwhm_px: float  # the owner's usual, over the earlier nights


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
    # The window's sharpest night — the one whose subs measured the smallest
    # stars — or None when too little was measured to name one honestly (see
    # :func:`sharpest_night`). Additive and defaulted, so an older consumer of
    # this dataclass is unaffected.
    sharpest: NightActivity | None = None
    # "Was last night off for you?" — the most recent night's star size against
    # the earlier nights *in this window*, or None when there is nothing worth
    # saying (see :func:`off_night`). The window is the right baseline rather
    # than a limitation: "your usual" should mean the way the kit behaves now,
    # not two years ago on a different focuser. Additive and defaulted.
    off_night: OffNightRead | None = None


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
    but still marks the night as imaged.

    A tuple may carry an **optional fourth element**, the frame's measured star
    size ``fwhm_px``, which feeds the per-night median behind "your sharpest
    night". It is read positionally and only when present, so every existing
    3-tuple caller folds byte-for-byte as before; a ``None`` or non-finite value
    is skipped rather than counted as a measurement."""
    for entry in entries:
        timestamp_utc, exposure_s, target_name = entry[0], entry[1], entry[2]
        fwhm_px = entry[3] if len(entry) > 3 else None
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
        if fwhm_px is not None:
            try:
                f = float(fwhm_px)
            except (TypeError, ValueError):
                continue
            # A non-finite or non-positive "measurement" is a failed measurement.
            if f == f and f > 0.0 and f != float("inf"):
                agg.fwhms.append(f)


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


def nights_from(
    acc: dict[date, _NightAgg],
    *,
    start: date | None = None,
    end: date | None = None,
) -> list[NightActivity]:
    """The folded accumulator as date-ascending :class:`NightActivity` rows,
    optionally clipped to ``start``…``end`` (both inclusive).

    Public because the accumulator itself is private plumbing: a caller that
    wants a *different* slice of the same fold — the year recap wants whole
    calendar years, the heatmap wants a trailing window — should get the rows
    through one conversion rather than reaching into ``_NightAgg`` and inventing
    a second definition of what a night's numbers are. With no bounds it returns
    every night that was folded."""
    ordered = [
        d for d in sorted(acc)
        if (start is None or d >= start) and (end is None or d <= end)
    ]
    return [
        NightActivity(
            date=d.isoformat(),
            exposure_s=round(acc[d].exposure_s, 3),
            n_frames=acc[d].n_frames,
            targets=sorted(acc[d].targets),
            median_fwhm_px=(
                None if (m := _median(acc[d].fwhms)) is None else round(m, 3)
            ),
            n_measured=len(acc[d].fwhms),
        )
        for d in ordered
    ]


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

    nights = nights_from(acc, start=start, end=today)
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
        sharpest=sharpest_night(nights),
        off_night=off_night(nights),
    )


def sharpest_night(nights: list[NightActivity]) -> NightActivity | None:
    """The night whose subs measured the **smallest stars**, or ``None``.

    "Which of my nights was actually the good one?" is a question a beginner
    asks and the app has never answered: the Target page's Nights card ranks the
    nights of *one* object, but nothing says which night of the whole hobby was
    the sharpest. Star size (FWHM, in pixels) is the measure the rest of the app
    already uses for that judgement — the session recap's sharp/soft verdict and
    the Nights card both read the same median — so this stays in one voice
    rather than inventing a second definition of "good".

    Honest by construction, and silent rather than wrong:

    * a night needs :data:`SHARPEST_MIN_MEASURED` measured subs to qualify — a
      one-frame median describes the frame, not the night;
    * at least :data:`SHARPEST_MIN_NIGHTS` nights must qualify, because naming
      the best of one is not a fact about the sky;
    * ties break on the earlier date, so the answer is deterministic.

    Pure and offline: it reads only what :func:`finalize_calendar` already
    computed.
    """
    ranked = [
        n for n in nights
        if n.median_fwhm_px is not None and n.n_measured >= SHARPEST_MIN_MEASURED
    ]
    if len(ranked) < SHARPEST_MIN_NIGHTS:
        return None
    return min(ranked, key=lambda n: (n.median_fwhm_px, n.date))


def off_night(nights: list[NightActivity]) -> OffNightRead | None:
    """"Was last night off for you?" — the latest night's star size against the
    owner's own whole-history usual, or ``None`` when there is nothing to say.

    The app already measures every accepted sub's star size and already trends it
    *within* one session (``session_recap.focus_trend``, early third vs late
    third) — which catches focus drifting away over a night but is blind to a
    night that was simply soft from the first frame: dew that formed before the
    first sub, a focus left wrong from last time, or a night of poor seeing. That
    night looks perfectly "steady" to the session trend, and the owner finds out
    weeks later when a stack comes out mushy.

    So this compares the whole night against *the observer's own history across
    every target*, which is the only yardstick that exists offline: star size in
    pixels is a property of the optics, the focus and the air, not of the object,
    so nights of different targets are comparable on one install. It reads only
    what :func:`finalize_calendar` already folded, so it costs nothing beyond the
    library walk the heatmap pays for anyway.

    Silent rather than wrong, in four ways:

    * a night must carry :data:`SHARPEST_MIN_MEASURED` measured subs to count at
      all — on either side of the comparison;
    * there must be :data:`OFF_NIGHT_MIN_BASELINE_NIGHTS` *earlier* qualifying
      nights, so the latest night is never its own yardstick;
    * the baseline is the **median of the per-night medians**, so one glorious or
      one dreadful night doesn't move "usual";
    * and it speaks only when the latest night is materially *fatter*. A normal
      night says nothing (praising one would make the card noise), and a sharp
      night is "your best night"'s job, not this one's.

    Deliberately never a diagnosis: seeing is not a fault, so the copy offers the
    likely causes and asks the owner to *check*, in that order.
    """
    qualifying = [
        n for n in nights
        if n.median_fwhm_px is not None
        and n.median_fwhm_px > 0
        and n.n_measured >= SHARPEST_MIN_MEASURED
    ]
    if len(qualifying) < OFF_NIGHT_MIN_BASELINE_NIGHTS + 1:
        return None
    # ``nights`` is date-ascending out of ``nights_from``; sort defensively so a
    # caller handing over a re-ordered list still gets the genuinely latest one.
    qualifying.sort(key=lambda n: n.date)
    latest = qualifying[-1]
    earlier = qualifying[:-1]
    baseline = _median([n.median_fwhm_px for n in earlier])  # type: ignore[misc]
    if baseline is None or not (baseline > 0):
        return None
    ratio = float(latest.median_fwhm_px) / float(baseline)  # type: ignore[arg-type]
    if ratio <= OFF_NIGHT_FATTER_ABOVE:
        return None
    level = "much_fatter" if ratio > OFF_NIGHT_MUCH_FATTER_ABOVE else "fatter"
    percent = abs(round((ratio - 1.0) * 100))
    if level == "much_fatter":
        label = "Much softer than usual"
        text = (
            f"On {latest.date} your stars came out about {percent}% fatter than "
            f"your usual night — a big change. Dew on the lens, focus left wrong, "
            f"or simply a night of poor seeing are the usual reasons. Worth "
            f"checking the lens and re-running autofocus before your next session."
        )
    else:
        label = "Softer than usual"
        text = (
            f"On {latest.date} your stars came out about {percent}% fatter than "
            f"your usual night. That is often dew on the lens or a little focus "
            f"drift, though it can just be poor seeing. Worth a quick look before "
            f"your next session."
        )
    return OffNightRead(
        level=level, label=label, text=text, night=latest.date,
        baseline_nights=len(earlier), ratio=round(ratio, 3),
        median_fwhm_px=float(latest.median_fwhm_px),  # type: ignore[arg-type]
        baseline_fwhm_px=round(float(baseline), 3),
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
