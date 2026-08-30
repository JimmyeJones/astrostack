"""When a picture's subs were *shot*, as observing-night dates.

A stack run records two things that look interchangeable and are not:
``timestamp_utc`` — when the stack *ran* — and the capture window
(``capture_start_utc`` / ``capture_end_utc``, schema 18+) — the earliest and
latest ``DATE-OBS`` among the subs it combined. The two differ by minutes on the
walk-away path and by *years* the moment anyone re-stacks a back catalogue,
which is the exact case this app's owner is in. Anything that says "shot on …"
has to use the second pair.

This module turns that raw window into the dates a person would name: the
**observing nights** the first and last sub belong to, bucketed local
noon-to-noon by :func:`seestack.activity_calendar.night_date_of` — the same
bucketing the imaging calendar, the Nights card and the session recap already
use. Going through that one helper is the point: a caption that named a night by
its raw UTC date would disagree with the Nights card for anybody shooting west
of Greenwich, where an evening's subs land on the *next* UTC day.

Pure and offline: give it the window and the observer's longitude and it returns
``YYYY-MM-DD`` strings (or ``None``), so it is trivially unit-tested and a
missing/unparseable stamp simply drops the clause rather than guessing.
"""

from __future__ import annotations

from seestack.activity_calendar import night_date_of


def capture_night_range(
    capture_start_utc: str | None,
    capture_end_utc: str | None,
    lon_deg: float | None = None,
) -> tuple[str | None, str | None]:
    """``(first_night, last_night)`` as ISO ``YYYY-MM-DD``, or ``(None, None)``.

    ``lon_deg`` is the observer's longitude (+E), resolved by
    :func:`webapp.site_location.resolve_site_lon`; ``None`` falls back to UTC
    noon-to-noon exactly as every other night surface does.

    Either end may be ``None`` on its own — a run recorded with only one usable
    stamp still has an honest single date to show — and an unparseable stamp is
    treated as absent. When only one end survives it is returned as *both*, so a
    caller never has to reason about a half-open range: one date means one night.
    """
    first = _night(capture_start_utc, lon_deg)
    last = _night(capture_end_utc, lon_deg)
    if first is None and last is None:
        return None, None
    if first is None:
        return last, last
    if last is None:
        return first, first
    # A window recorded (or hand-edited) end-first still describes a real range;
    # name it in the order a reader expects rather than refusing it.
    return (first, last) if first <= last else (last, first)


def _night(stamp: str | None, lon_deg: float | None) -> str | None:
    if not stamp:
        return None
    night = night_date_of(str(stamp), lon_deg)
    return night.isoformat() if night is not None else None
