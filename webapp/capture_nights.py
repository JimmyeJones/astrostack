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

It also answers the question the window *cannot*: **how many nights** a stack is
made of. A window of 15→18 Nov is equally consistent with two nights and with
four, and "600 subs over 4 nights" is what a person actually says about their
picture — so a run also records the hours its subs arrived in
(``capture_hours_json``, schema 19+) and :func:`capture_night_count` buckets
*those* through the very same helper. Counting here rather than at stack time is
deliberate: the count then follows the owner's longitude whenever they set one,
instead of freezing a UTC-bucketed guess into the row.

Pure and offline: give it the window and the observer's longitude and it returns
``YYYY-MM-DD`` strings (or ``None``), so it is trivially unit-tested and a
missing/unparseable stamp simply drops the clause rather than guessing.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

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


def capture_night_dates(
    capture_hours_json: str | None,
    lon_deg: float | None = None,
) -> list[str]:
    """The distinct observing nights a run's subs fall into, as sorted ISO dates.

    ``capture_hours_json`` is the run row's ``capture_hours_json`` (schema 19+):
    a JSON array of on-the-hour UTC instants, one per hour in which a sub was
    taken (see :func:`seestack.stack.stacker._capture_hours`). Bucketing happens
    *here*, at read time, through the same :func:`night_date_of` the range above
    uses — so the count follows the observer's longitude and can never disagree
    with the dates the caption names.

    Returns ``[]`` for a run recorded before the column existed, for malformed
    JSON, and for anything that isn't a list of parseable stamps: a caller then
    says nothing about nights rather than guessing a number.
    """
    if not capture_hours_json:
        return []
    try:
        raw = json.loads(capture_hours_json)
    except (TypeError, ValueError):
        return []
    if not isinstance(raw, list):
        return []
    nights = {night for h in raw if (night := _night(
        h if isinstance(h, str) else None, lon_deg)) is not None}
    return sorted(nights)


def capture_night_count(
    capture_hours_json: str | None,
    lon_deg: float | None = None,
) -> int | None:
    """How many observing nights went into a stack, or ``None`` when unknown.

    ``None`` — not ``0`` — is the "we don't know" answer, so a run from before
    the app recorded it reads as *silence* rather than as a picture shot on no
    nights at all.
    """
    nights = capture_night_dates(capture_hours_json, lon_deg)
    return len(nights) or None


def cumulative_night_steps(
    night_sets: Sequence[Sequence[str]],
) -> list[int] | None:
    """How many nights each step of a series has accumulated, when the series
    really is **cumulative by night** — else ``None``.

    This is the "reel from history" question, asked of stacks that already exist:
    the owner asked for a progression *"night 1; nights 1–2; …"*, and a target he
    has re-stacked as the nights came in already **is** that progression — nobody
    had checked, so the reel called its steps "stacks" and dated them one at a
    time. Given each step's observing nights (from :func:`capture_night_dates`,
    oldest step first) this answers whether every step keeps every night the one
    before it had and adds at least one, and if so returns the running night
    count — ``[1, 2, 4, 5]`` for a reel whose third step brought in two nights at
    once.

    ``None`` — not an empty list — is the "this is not a cumulative series"
    answer, and it is deliberately the answer to every doubt as well:

    * fewer than two steps (there is no progression to describe);
    * **any** step with no nights recorded — a run from before schema 19, or one
      whose hours were unreadable — because a series with a hole in it cannot be
      shown to be nested, and "nights 1–3" over a step that might be nights 2–4
      is worse than the date the frame carries today;
    * a step that *drops* a night the one before it had (re-stacking a subset),
      or repeats the same nights (a reprocess), since neither is a step *deeper*
      into the same growing pile.

    So this only ever fires on the shape the owner described, and everything else
    keeps the labelling it has always had. Pure and offline.
    """
    if len(night_sets) < 2:
        return None
    steps: list[int] = []
    previous: set[str] = set()
    for nights in night_sets:
        current = set(nights)
        if not current:
            return None
        if not (current > previous):
            return None
        steps.append(len(current))
        previous = current
    return steps


def _night(stamp: str | None, lon_deg: float | None) -> str | None:
    if not stamp:
        return None
    night = night_date_of(str(stamp), lon_deg)
    return night.isoformat() if night is not None else None
