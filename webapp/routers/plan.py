"""'Tonight' night-planner endpoint.

``GET /api/plan/tonight`` returns an offline, ranked list of deep-sky targets
worth pointing the scope at tonight: the user's own library targets ("already
targeted", annotated with what they've captured) plus bundled catalogs — the
Messier objects and a curated set of popular non-Messier NGC/IC targets — ("not
yet targeted"), each scored by altitude, usable window and Moon proximity
(see :mod:`seestack.nightplan`).

The observer location comes from Settings when set, otherwise it's read
best-effort from a solved frame's FITS header (``SITELAT``/``SITELONG`` — the
Seestar writes these), so a Seestar owner usually needs to configure nothing.
Everything is read-only: this never touches stacks, frames or settings.
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import date as _date
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, Response

from seestack.nightplan import (
    WEEK_NIGHTS,
    HorizonProfile,
    LibraryTarget,
    NextObservingWindow,
    Observer,
    WeekPlan,
    best_months,
    load_catalog,
    moon_interference,
    next_observing_windows,
    plan_tonight,
    plan_week,
    rank_targets_now,
    suggest_targets,
)
from webapp import deps
from webapp.goals import read_goal_s
from webapp.ics import IcsEvent, to_ics
from webapp.registry_cache import cached_for_registry, registry_signature
from webapp.site_location import detect_site_from_library as _detect_site_from_library

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/plan", tags=["plan"])

# How far ahead the `date` picker may plan. Deep-sky observability a couple of
# months out is still useful ("when's the next dark-sky window for M31?"); beyond
# that the request is almost always a typo, and pinning a horizon keeps the offline
# ephemeris cheap. One day of slack behind "today" absorbs timezone skew (a viewer
# west of UTC whose local calendar day trails UTC's can still ask for "tonight").
_MAX_LOOKAHEAD_DAYS = 60


def _reference_for_date(plan_date: _date, lon_deg: float) -> datetime:
    """A UTC reference instant at local solar noon on ``plan_date``.

    The night planner derives "tonight" as the dark window around the solar
    midnight *following* its reference moment (see
    ``nightplan._find_dark_window``), so aiming the reference at local noon on the
    chosen date lands squarely on that date's night regardless of the observer's
    longitude. Local noon in UTC is ``12:00 − lon/15`` hours (east of Greenwich is
    earlier in UTC); the engine's ±12 h solar-noon search corrects any residual
    equation-of-time offset.
    """
    noon_utc = datetime(plan_date.year, plan_date.month, plan_date.day,
                        12, 0, 0, tzinfo=timezone.utc)
    return noon_utc - timedelta(hours=lon_deg / 15.0)


def _detect_site_from_fits(request: Request) -> tuple[float, float] | None:
    """Best-effort observer lat/lon from a recent frame's FITS header.

    Opens the library and delegates to the shared, bounded header probe
    (:func:`webapp.site_location.detect_site_from_library`).
    """
    lib = deps.open_library(request)
    try:
        return _detect_site_from_library(lib)
    finally:
        lib.close()


def _resolve_observer(request: Request, settings) -> tuple[Observer | None, str]:  # noqa: ANN001
    """Resolve the observer location and how it was found.

    Explicit Settings location wins; otherwise sniff a solved frame's FITS header
    (the common Seestar case). Returns ``(observer, source)`` where ``source`` is
    ``"settings"`` / ``"fits"`` / ``"none"`` (``observer`` is ``None`` only for
    ``"none"``) — so every planning surface resolves the site the same way and the
    UI can explain where the location came from.
    """
    if settings.site_lat is not None and settings.site_lon is not None:
        return (Observer(lat_deg=float(settings.site_lat),
                         lon_deg=float(settings.site_lon),
                         elevation_m=float(settings.site_elevation_m or 0.0)),
                "settings")
    site = _detect_site_from_fits(request)
    if site is not None:
        return (Observer(lat_deg=site[0], lon_deg=site[1],
                         elevation_m=float(settings.site_elevation_m or 0.0)),
                "fits")
    return None, "none"


def _library_targets(request: Request) -> list[LibraryTarget]:
    """Library targets that have a position, for the 'already targeted' set.

    Each row is annotated with its catalog-resolved object type/constellation via
    the same ``identify_object`` path the Dashboard "Target progress" card uses, so
    the two surfaces agree (previously these were left blank, so every already-owned
    target bucketed as "Other" and got the flat 4 h goal, contradicting the card).

    The same reasoning carries the user's own **integration goal**: the planner's
    "have I shot enough of this?" row hint has to answer with the goal the user
    set, or the two screens disagree about the same target — a target the owner
    deliberately wants 12 h of would read "Plenty — try something new" here at
    7 h, while the Target page correctly says "keep going". Read exactly as the
    Dashboard roll-up reads it (a project-meta lookup, tolerating a garbage value
    as unset); a project that won't open simply keeps the per-type default rather
    than failing the whole plan.

    The same open also reads the target's **recent per-night pace**, so a row can
    say "~1 more clear night finishes this" at the moment the user is choosing
    what to point at — the figure the Dashboard and Target page already show,
    rather than a vague "Nearly there". That read is the expensive one (it scans
    every dated frame; measured ~5 ms a target against ~0.6 ms for the goal
    alone), so the whole annotated list is cached behind the shared
    registry-signature cache the Dashboard roll-up uses.
    """
    lib = deps.open_library(request)
    try:
        targets = lib.list_targets()
        return cached_for_registry(
            request.app, "plan_library_targets", registry_signature(targets),
            lambda: _annotate_library_targets(lib, targets),
        )
    finally:
        lib.close()


def _annotate_library_targets(lib, targets) -> list[LibraryTarget]:  # noqa: ANN001
    """Build the annotated 'already targeted' rows (see :func:`_library_targets`)."""
    from seestack.objectinfo import identify_object
    from seestack.session_recap import recent_night_pace_s
    from webapp.framing_advice import newest_picture_nudge

    catalog = load_catalog()
    out: list[LibraryTarget] = []
    for t in targets:
        if t.ra_deg is None or t.dec_deg is None:
            continue
        info = identify_object(t.name, float(t.ra_deg), float(t.dec_deg),
                               catalog=catalog)
        goal_s: float | None = None
        pace_s: float | None = None
        nudge = None
        proj = None
        try:
            proj = lib.open_target(t.safe_name)
            goal_s = read_goal_s(proj)
            pace_s = recent_night_pace_s(proj)
            # "Nudge a little south before you start" — the framing advice from
            # this target's newest picture, brought forward from the morning-after
            # card to the screen someone reads while pointing the scope. One more
            # FITS header read per already-shot target, which is why it sits
            # inside the same registry-signature cache as the pace read above.
            nudge = newest_picture_nudge(proj, info)
        except Exception:  # noqa: BLE001 — a broken project must not 500 the plan
            pass
        finally:
            if proj is not None:
                proj.close()
        out.append(LibraryTarget(
            safe=t.safe_name, name=t.name,
            ra_deg=float(t.ra_deg), dec_deg=float(t.dec_deg),
            frames_accepted=int(t.n_frames_accepted or 0),
            total_exposure_s=float(t.total_exposure_s or 0.0),
            object_type=info.type if info is not None else "",
            con=info.constellation_abbr if info is not None else "",
            goal_s=goal_s,
            recent_pace_s=pace_s,
            recentre_nudge=nudge,
        ))
    return out


@router.get("/tonight")
def get_tonight(
    request: Request,
    when: str | None = Query(default=None, description="ISO-8601 UTC time; defaults to now"),
    date: str | None = Query(default=None, description="YYYY-MM-DD calendar night to plan; defaults to today"),
    min_alt: int | None = Query(default=None, ge=0, le=80),
) -> dict[str, Any]:
    """Ranked observability plan for a night (see module docstring).

    By default this plans tonight. Pass ``date=YYYY-MM-DD`` to plan an upcoming
    night instead (up to ``_MAX_LOOKAHEAD_DAYS`` ahead) — the same offline
    computation, aimed at that date's dark window. ``when`` (a precise ISO
    timestamp) still takes precedence when supplied, for callers that want an
    exact reference moment.
    """
    settings = deps.get_settings(request)

    # Validate an optional calendar-date pick up front so a bad/too-far date is a
    # clean 422 (its reference instant is resolved against the observer below,
    # once the longitude is known — local noon depends on it).
    plan_date: _date | None = None
    if date:
        try:
            plan_date = _date.fromisoformat(date)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Bad 'date' (expected YYYY-MM-DD)") from exc
        today = datetime.now(timezone.utc).date()
        # Both bounds carry one day of timezone slack: `today` is UTC's calendar
        # day, but the frontend date picker offers `local_today ± N` from the
        # *browser's* local date. A viewer west of UTC (local date trailing UTC)
        # can still ask for "tonight" (the −1 on the min); a viewer east of UTC in
        # their local morning (local date leading UTC by a day) picks a max of
        # `UTC_today + N + 1`, so the upper bound needs the symmetric +1 or the
        # farthest date the app's own picker allows would 422 for them.
        if not (today - timedelta(days=1) <= plan_date <= today + timedelta(days=_MAX_LOOKAHEAD_DAYS + 1)):
            raise HTTPException(
                status_code=422,
                detail=f"'date' must be within the next {_MAX_LOOKAHEAD_DAYS} days",
            )

    if when:
        try:
            ref = datetime.fromisoformat(when)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Bad 'when' timestamp") from exc
        if ref.tzinfo is None:
            ref = ref.replace(tzinfo=timezone.utc)
    elif plan_date is not None:
        # Provisional (UTC-noon) reference; refined to local noon once we know the
        # observer's longitude. If no observer resolves, only `generated_utc` in the
        # location-less response uses it, so UTC noon is a fine stand-in there.
        ref = datetime(plan_date.year, plan_date.month, plan_date.day,
                       12, 0, 0, tzinfo=timezone.utc)
    else:
        ref = datetime.now(timezone.utc)

    min_altitude = min_alt if min_alt is not None else int(settings.min_target_altitude_deg)

    # Resolve the observer: explicit Settings location wins; otherwise sniff a
    # frame header (the common Seestar case). None → the UI prompts for a site.
    observer, location_source = _resolve_observer(request, settings)

    if observer is None:
        return {
            "location_source": "none",
            "observer": None,
            "generated_utc": ref.astimezone(timezone.utc).isoformat(),
            "dark_window": None,
            "moon_illumination": None,
            "moon_waxing": None,
            "min_altitude_deg": min_altitude,
            "targets": [],
        }

    # With the observer's longitude known, aim a calendar-date pick at that night's
    # local solar noon (a precise `when` is left exactly as the caller supplied it).
    if plan_date is not None and not when:
        ref = _reference_for_date(plan_date, observer.lon_deg)

    plan = plan_tonight(
        observer, ref, min_altitude_deg=float(min_altitude),
        library_targets=_library_targets(request),
        horizon=HorizonProfile.from_pairs(settings.horizon_profile),
    )
    payload = asdict(plan)
    payload["location_source"] = location_source
    return payload


@router.get("/best-tonight")
def get_best_tonight(
    request: Request,
    when: str | None = Query(default=None, description="ISO-8601 UTC time; defaults to now"),
    min_alt: int | None = Query(default=None, ge=0, le=80),
    limit: int = Query(default=3, ge=1, le=10),
) -> dict[str, Any]:
    """"Best use of your scope right now" — the user's *own* targets, ranked.

    The companion to ``/tonight`` (which ranks everything, including the bundled
    catalog, over the whole night): this answers the narrower question a beginner
    asks when the sky unexpectedly clears — *of the targets I've already started,
    which one is up right now and would most benefit from another hour?* Scored by
    :func:`seestack.nightplan.rank_targets_now` as "how well-placed it is at this
    moment" × "how much another hour would actually cut its noise".

    Read-only: it never starts a capture or changes a setting. Degrades instead of
    erroring — with no location resolved it still ranks on "would more subs help?"
    alone and says so — and returns an empty ``picks`` list whenever there's
    nothing worth suggesting, so the UI can simply hide itself.
    """
    settings = deps.get_settings(request)
    if when:
        try:
            ref = datetime.fromisoformat(when)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Bad 'when' timestamp") from exc
        if ref.tzinfo is None:
            ref = ref.replace(tzinfo=timezone.utc)
    else:
        ref = datetime.now(timezone.utc)

    min_altitude = min_alt if min_alt is not None else int(settings.min_target_altitude_deg)
    observer, location_source = _resolve_observer(request, settings)
    plan = rank_targets_now(
        observer, ref, _library_targets(request),
        min_altitude_deg=float(min_altitude),
        horizon=HorizonProfile.from_pairs(settings.horizon_profile),
        limit=limit,
    )
    payload = asdict(plan)
    payload["location_source"] = location_source
    return payload


#: How long a computed week plan may be served from cache. Matched to the bucket
#: below, so one bucket's answer is reused for exactly the span it describes.
_WEEK_CACHE_TTL_S = 300.0
#: "Now" is rounded down to this many minutes for the cache signature. It is the
#: planner's own observability sampling step (``_observability_batch`` walks the
#: darkness at 5-minute stamps), so a cached plan is never staler than the
#: resolution of the times it reports.
_WEEK_CACHE_BUCKET_MINUTES = 5


def _cached_week_plan(
    request: Request,
    settings: Any,
    observer: Observer,
    start: datetime,
    *,
    nights: int,
    min_altitude: int,
) -> WeekPlan:
    """The week plan for these inputs, served from the registry cache when warm.

    Shared by the ``/week`` payload and its ``.ics`` download so the calendar a
    user adds is, by construction, the same plan the card in front of them shows
    — the two cannot report different nights or times for the same request.

    A week costs ``nights`` dark-window searches, and that search — not the
    per-target work — is the whole bill: measured on a London site over 7 nights,
    **0.96 s for one target and 1.07 s for eighty**, because :func:`plan_week`
    runs one vectorised observability batch per night over the whole library.
    (The shape it replaced — ``next_observing_windows`` per target — was **9.7 s
    at ten targets**, since it re-searched every night's darkness once per
    target.) Flat in the library size is the right cost, but a second of
    ephemeris on every card render is still a second, so the answer is cached
    behind the same registry-signature cache the Dashboard roll-ups use.

    The signature carries every input, plus "now" bucketed to
    :data:`_WEEK_CACHE_BUCKET_MINUTES` — the planner's own sampling step, so a
    cached answer can never be staler than the resolution of the numbers it
    reports. (Only the first night is time-dependent at all: it is the one
    clipped to "now".) A changed location, altitude floor, horizon, night count
    or library rebuilds rather than serves.
    """
    targets = _library_targets(request)
    horizon = HorizonProfile.from_pairs(settings.horizon_profile)
    bucket = start.astimezone(timezone.utc).replace(second=0, microsecond=0)
    bucket = bucket.replace(minute=(bucket.minute // _WEEK_CACHE_BUCKET_MINUTES)
                            * _WEEK_CACHE_BUCKET_MINUTES)
    sig = (
        bucket.isoformat(), int(nights), min_altitude,
        observer.lat_deg, observer.lon_deg, observer.elevation_m,
        tuple(tuple(p) for p in (settings.horizon_profile or [])),
        # Depth is in the signature because the ``WEEK_MAX_TARGETS`` cap selects
        # *by* it (``plan_week`` keeps the most-shot targets): a night's capture
        # can change which forty targets get planned without adding a target or
        # moving one, and a signature blind to that would keep serving the old
        # selection. Free on a library under the cap, where the set is everything
        # either way.
        tuple((t.safe, t.ra_deg, t.dec_deg, t.total_exposure_s, t.frames_accepted)
              for t in targets),
    )
    return cached_for_registry(
        request.app, "plan_week", sig,
        lambda: plan_week(
            observer, targets,
            start_utc=start,
            nights=int(nights),
            min_altitude_deg=float(min_altitude),
            horizon=horizon,
        ),
        ttl_s=_WEEK_CACHE_TTL_S,
    )


@router.get("/week")
def get_plan_week(
    request: Request,
    when: str | None = Query(default=None,
                             description="ISO-8601 UTC reference to plan from; defaults to now"),
    min_alt: int | None = Query(default=None, ge=0, le=80),
    nights: int = Query(default=WEEK_NIGHTS, ge=1, le=14,
                        description="How many nights ahead to look"),
) -> dict[str, Any]:
    """"Plan my week" — which of *your own* targets to point at, on which night.

    The cross-target, multi-night view none of the other planners give:
    ``/tonight`` ranks everything for tonight, ``/best-tonight`` ranks your own
    targets right now, and ``/next-session/{safe}`` plans *one* target forward.
    This is the question a beginner who only gets out on a clear weekend actually
    has — *"your best shot this week is M31 on Thursday; M42 is better Saturday"*.

    Library targets only (this is "finish what I've got"; ``/suggest`` covers
    discovery), capped at :data:`~seestack.nightplan.WEEK_MAX_TARGETS`, and the
    counts come back on the payload so the UI can be honest when a big library was
    trimmed. Read-only and offline. With no location resolved, ``nights`` is empty
    and ``location_source`` tells the UI which prompt to show — the card
    self-hides rather than guessing.
    """
    settings = deps.get_settings(request)

    start = datetime.now(timezone.utc)
    if when:
        try:
            start = datetime.fromisoformat(when)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Bad 'when' timestamp") from exc
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)

    observer, location_source = _resolve_observer(request, settings)
    min_altitude = min_alt if min_alt is not None else int(settings.min_target_altitude_deg)

    if observer is None:
        return {
            "location_source": location_source,
            "observer": None,
            "min_altitude_deg": min_altitude,
            "horizon_active": False,
            "nights_scanned": int(nights),
            "generated_utc": start.astimezone(timezone.utc).isoformat(),
            "nights": [],
            "targets": [],
            "n_targets_considered": 0,
            "n_targets_with_position": 0,
        }

    plan = _cached_week_plan(request, settings, observer, start,
                             nights=int(nights), min_altitude=min_altitude)
    payload = asdict(plan)
    payload["location_source"] = location_source
    return payload


# How many nights ahead to scan for a target's next good window, and how many
# such windows to return. Two weeks covers "come back when the Moon's out of the
# way" without turning one request into a long ephemeris grind; three windows is
# enough to say "your next session — and the couple after it" when a goal needs
# more than one night.
#
# ``_NEXT_SESSION_WANT`` is only the *default*: a caller that needs to count
# further ahead — the finish forecast, which says "you could finish around
# <date>" by looking at the n-th window for an n-night goal — may ask for up to
# ``_NEXT_SESSION_WANT_MAX``. The 14-night scan is unchanged either way, so a
# bigger ``want`` is a bigger slice of the same search, never a longer one; the
# scan horizon stays the real limit, and a goal it can't reach still returns
# fewer windows (an honest silence) rather than a guess.
_NEXT_SESSION_NIGHTS = 14
_NEXT_SESSION_WANT = 3
_NEXT_SESSION_WANT_MAX = 8


@router.get("/next-session/{safe}")
def get_next_session(
    safe: str,
    request: Request,
    min_alt: int | None = Query(default=None, ge=0, le=80),
    when: str | None = Query(default=None,
                             description="ISO-8601 UTC reference to plan from; defaults to now"),
    want: int | None = Query(default=None, ge=1, le=_NEXT_SESSION_WANT_MAX,
                             description="How many windows to return; defaults to 3"),
) -> dict[str, Any]:
    """When to next point the scope at *this* target — the forward-looking
    companion to ``/tonight``.

    Returns the next few nights (``want`` of them, ``_NEXT_SESSION_WANT`` by
    default) this target clears the altitude floor for a usable stretch of
    darkness, so the Target page can turn "you're 2 h short of a good M31" into
    "…and Thursday 22:40 → 02:10 is your next good window". Read-only and
    offline. ``windows`` is empty (the card self-hides) when no location is set,
    the target has no position, or nothing is well-placed in the horizon;
    ``target_has_position``/``location_source`` let the UI explain which.
    """
    settings = deps.get_settings(request)

    start = datetime.now(timezone.utc)
    if when:
        try:
            start = datetime.fromisoformat(when)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Bad 'when' timestamp") from exc
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)

    lib = deps.open_library(request)
    try:
        entry = lib.find_target(safe)
    finally:
        lib.close()
    if entry is None:
        raise HTTPException(status_code=404, detail="Unknown target")

    observer, location_source = _resolve_observer(request, settings)
    min_altitude = min_alt if min_alt is not None else int(settings.min_target_altitude_deg)
    has_position = entry.ra_deg is not None and entry.dec_deg is not None
    n_want = _NEXT_SESSION_WANT if want is None else int(want)

    base: dict[str, Any] = {
        "location_source": location_source,
        "observer": asdict(observer) if observer is not None else None,
        "target_has_position": has_position,
        "min_altitude_deg": min_altitude,
        "nights_scanned": _NEXT_SESSION_NIGHTS,
        "windows": [],
    }
    if observer is None or not has_position:
        return base

    wins = next_observing_windows(
        observer, float(entry.ra_deg), float(entry.dec_deg),
        start_utc=start,
        min_altitude_deg=float(min_altitude),
        horizon=HorizonProfile.from_pairs(settings.horizon_profile),
        nights=_NEXT_SESSION_NIGHTS, want=n_want,
    )
    base["windows"] = [{
        "dark_start_utc": w.dark_start.isoformat(),
        "dark_end_utc": w.dark_end.isoformat(),
        "usable_start_utc": w.usable_start.isoformat() if w.usable_start else None,
        "usable_end_utc": w.usable_end.isoformat() if w.usable_end else None,
        "max_altitude_deg": w.max_altitude_deg,
        "minutes_above_min_alt": w.minutes_above_min_alt,
        "moon_illumination": w.moon_illumination,
        "moon_up_fraction": w.moon_up_fraction,
        "score": w.score,
    } for w in wins]
    return base


def _window_ics_event(safe: str, name: str, w: Any, location: str) -> IcsEvent:
    """Turn one observing window into a plain-language calendar event.

    Uses the *usable* stretch (target above the altitude floor) when the planner
    computed one, else the whole dark window; the description is jargon-free so a
    beginner reading the reminder on the night knows exactly what to do."""
    start = w.usable_start or w.dark_start
    end = w.usable_end or w.dark_end
    hours = max(0.0, (end - start).total_seconds() / 3600.0)
    if hours >= 1.0:
        span = f"about {hours:.0f} clear hour{'s' if round(hours) != 1 else ''}"
    else:
        span = f"about {round(hours * 60)} clear minutes"
    moon_pct = round(max(0.0, min(1.0, w.moon_illumination)) * 100)
    moon_where = "up" if w.moon_up_fraction > 0.5 else "down"
    description = (
        f"{name} climbs to {round(w.max_altitude_deg)}°, {span} of darkness to "
        f"reach your goal. Moon {moon_pct}% and mostly {moon_where}. "
        "Bring the Seestar out."
    )
    # Deterministic per (target, start) so re-adding updates the same calendar
    # entry instead of duplicating it.
    uid = f"{safe}-{start.astimezone(timezone.utc):%Y%m%dT%H%M%SZ}@astrostack"
    return IcsEvent(
        uid=uid, start=start, end=end,
        summary=f"Image {name}", description=description, location=location,
    )


@router.get("/next-session/{safe}/calendar.ics")
def get_next_session_ics(
    safe: str,
    request: Request,
    min_alt: int | None = Query(default=None, ge=0, le=80),
    when: str | None = Query(default=None,
                             description="ISO-8601 UTC reference to plan from; defaults to now"),
) -> Response:
    """Download the next few good observing windows for *this* target as an
    ``.ics`` calendar file, so a beginner can one-tap "Add to calendar" and their
    phone reminds them on the night. Read-only and offline (``.ics`` is just
    text — no calendar account, no network). 404s on an unknown target or when
    there's no upcoming window, so the file is never blank."""
    settings = deps.get_settings(request)

    start = datetime.now(timezone.utc)
    if when:
        try:
            start = datetime.fromisoformat(when)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Bad 'when' timestamp") from exc
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)

    lib = deps.open_library(request)
    try:
        entry = lib.find_target(safe)
    finally:
        lib.close()
    if entry is None:
        raise HTTPException(status_code=404, detail="Unknown target")

    observer, _ = _resolve_observer(request, settings)
    min_altitude = min_alt if min_alt is not None else int(settings.min_target_altitude_deg)
    has_position = entry.ra_deg is not None and entry.dec_deg is not None
    if observer is None or not has_position:
        raise HTTPException(status_code=404,
                            detail="No observing window to add (set a location first)")

    wins = next_observing_windows(
        observer, float(entry.ra_deg), float(entry.dec_deg),
        start_utc=start,
        min_altitude_deg=float(min_altitude),
        horizon=HorizonProfile.from_pairs(settings.horizon_profile),
        nights=_NEXT_SESSION_NIGHTS, want=_NEXT_SESSION_WANT,
    )
    if not wins:
        raise HTTPException(status_code=404, detail="No upcoming window to add")

    location = f"{observer.lat_deg:.4f}, {observer.lon_deg:.4f}"
    events = [_window_ics_event(safe, entry.name, w, location) for w in wins]
    body = to_ics(events)
    filename = f"{safe}-next-session.ics"
    return Response(
        content=body,
        media_type="text/calendar",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _week_night_as_window(night: Any) -> NextObservingWindow:
    """Adapt one planned :class:`WeekNight` to the window shape the calendar
    serialiser already understands.

    The week plan carries ISO strings (it is a JSON payload) and keeps the Moon's
    illumination on the *night* rather than on the pick; :func:`_window_ics_event`
    wants datetimes and one flat window. Converting here rather than writing a
    second event builder is what keeps the two calendars' wording — and, more
    importantly, their ``UID`` scheme — identical, so adding the week after
    adding a target's next session *updates* the shared night instead of
    duplicating it. Only called for a night that has a ``best`` pick.
    """
    best = night.best
    return NextObservingWindow(
        dark_start=datetime.fromisoformat(night.dark_start_utc),
        dark_end=datetime.fromisoformat(night.dark_end_utc),
        usable_start=(datetime.fromisoformat(best.usable_start_utc)
                      if best.usable_start_utc else None),
        usable_end=(datetime.fromisoformat(best.usable_end_utc)
                    if best.usable_end_utc else None),
        max_altitude_deg=best.max_altitude_deg,
        minutes_above_min_alt=best.minutes_above_min_alt,
        moon_illumination=night.moon_illumination,
        # A placed pick always has a usable window, so the planner always measured
        # this; 0.0 only defensively, which reads as "Moon down" — the quieter
        # error if it were ever missing.
        moon_up_fraction=(best.moon_up_fraction if best.moon_up_fraction is not None
                          else 0.0),
        score=best.score,
    )


@router.get("/week/calendar.ics")
def get_plan_week_ics(
    request: Request,
    when: str | None = Query(default=None,
                             description="ISO-8601 UTC reference to plan from; defaults to now"),
    min_alt: int | None = Query(default=None, ge=0, le=80),
    nights: int = Query(default=WEEK_NIGHTS, ge=1, le=14,
                        description="How many nights ahead to look"),
) -> Response:
    """Download the planned week as an ``.ics`` calendar file — one event per
    night, titled with what to point at that night.

    "Plan my week" tells you Saturday is your M 31 night; this is what stops you
    having to remember it. Same machinery, same inputs and the same cached plan
    as :func:`get_plan_week`, so the calendar can never disagree with the card
    that offers it. Read-only and offline (``.ics`` is just text — no calendar
    account, no network).

    Only nights that actually have a pick become events: an entry reading
    "nothing is well placed" is worse than no entry, and a blank calendar is
    worse than an honest 404.
    """
    settings = deps.get_settings(request)

    start = datetime.now(timezone.utc)
    if when:
        try:
            start = datetime.fromisoformat(when)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Bad 'when' timestamp") from exc
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)

    observer, _ = _resolve_observer(request, settings)
    if observer is None:
        raise HTTPException(status_code=404,
                            detail="No week to add (set a location first)")

    min_altitude = min_alt if min_alt is not None else int(settings.min_target_altitude_deg)
    plan = _cached_week_plan(request, settings, observer, start,
                             nights=int(nights), min_altitude=min_altitude)

    location = f"{observer.lat_deg:.4f}, {observer.lon_deg:.4f}"
    events = [
        _window_ics_event(n.best.safe, n.best.name, _week_night_as_window(n), location)
        for n in plan.nights if n.best is not None
    ]
    if not events:
        raise HTTPException(status_code=404, detail="No nights to add this week")

    body = to_ics(events)
    return Response(
        content=body,
        media_type="text/calendar",
        headers={"Content-Disposition": 'attachment; filename="astrostack-week.ics"'},
    )


@router.get("/best-months/{safe}")
def get_best_months(
    safe: str,
    request: Request,
    min_alt: int | None = Query(default=None, ge=0, le=80),
    when: str | None = Query(default=None,
                             description="ISO-8601 UTC reference; the year is scanned. Defaults to now"),
) -> dict[str, Any]:
    """"Best time of year to shoot this target" — a seasonal-observability strip.

    The plan-ahead companion to ``/next-session`` (which looks ~two weeks out):
    it answers "when *this year* can I actually get this object?" by scanning the
    twelve months and reporting, for a representative night of each, how high the
    target climbs during darkness and how long it stays up. So the Target page can
    say "a winter target — best Nov–Feb" for M42 and "a summer target" for the
    Cygnus region. Read-only and offline. ``months`` is empty (the strip
    self-hides) when no location is set or the target has no solved position;
    ``target_has_position``/``location_source`` let the UI explain which.
    """
    settings = deps.get_settings(request)

    ref = datetime.now(timezone.utc)
    if when:
        try:
            ref = datetime.fromisoformat(when)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Bad 'when' timestamp") from exc
        if ref.tzinfo is None:
            ref = ref.replace(tzinfo=timezone.utc)

    lib = deps.open_library(request)
    try:
        entry = lib.find_target(safe)
    finally:
        lib.close()
    if entry is None:
        raise HTTPException(status_code=404, detail="Unknown target")

    observer, location_source = _resolve_observer(request, settings)
    min_altitude = min_alt if min_alt is not None else int(settings.min_target_altitude_deg)
    has_position = entry.ra_deg is not None and entry.dec_deg is not None

    base: dict[str, Any] = {
        "location_source": location_source,
        "observer": asdict(observer) if observer is not None else None,
        "target_has_position": has_position,
        "min_altitude_deg": min_altitude,
        "year": ref.year,
        "months": [],
    }
    if observer is None or not has_position:
        return base

    rows = best_months(
        observer, float(entry.ra_deg), float(entry.dec_deg),
        year=ref.year,
        min_altitude_deg=float(min_altitude),
        horizon=HorizonProfile.from_pairs(settings.horizon_profile),
    )
    base["months"] = [{
        "month": r.month,
        "max_transit_alt_deg": r.max_transit_alt_deg,
        "usable_dark_minutes": r.usable_dark_minutes,
        "dark_minutes": r.dark_minutes,
    } for r in rows]
    return base


@router.get("/moon/{safe}")
def get_moon_interference(
    safe: str,
    request: Request,
    when: str | None = Query(default=None,
                             description="ISO-8601 UTC reference to plan from; defaults to now"),
) -> dict[str, Any]:
    """"Is the Moon going to wash this out tonight?" — a plain-language Moon-
    interference readout for *this* target.

    A bright Moon near a faint target floods the sky background and buries the
    signal — the single biggest avoidable reason a beginner's faint-nebula night
    disappoints — and a non-expert has no intuition for it. This turns the offline
    ephemeris into one honest verdict + sentence (Moon phase / illumination, its
    altitude, and its separation from this target at tonight's darkest moment), so
    the Target page can nudge "point at a bright galaxy or cluster instead" before
    a clear night is wasted. Read-only and offline. ``moon`` is null (the card
    self-hides) when no location is set or the target has no position;
    ``target_has_position``/``location_source`` let the UI explain which.
    """
    settings = deps.get_settings(request)

    start = datetime.now(timezone.utc)
    if when:
        try:
            start = datetime.fromisoformat(when)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Bad 'when' timestamp") from exc
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)

    lib = deps.open_library(request)
    try:
        entry = lib.find_target(safe)
    finally:
        lib.close()
    if entry is None:
        raise HTTPException(status_code=404, detail="Unknown target")

    observer, location_source = _resolve_observer(request, settings)
    has_position = entry.ra_deg is not None and entry.dec_deg is not None

    base: dict[str, Any] = {
        "location_source": location_source,
        "observer": asdict(observer) if observer is not None else None,
        "target_has_position": has_position,
        "moon": None,
    }
    if observer is None or not has_position:
        return base

    mi = moon_interference(
        observer, float(entry.ra_deg), float(entry.dec_deg), when_utc=start,
    )
    base["moon"] = asdict(mi)
    return base


# How many not-yet-captured showpieces to suggest tonight. One to three keeps the
# "try something new" card a gentle nudge, not a wall of choices for a beginner.
_SUGGEST_LIMIT = 3


@router.get("/suggest")
def get_suggested_targets(
    request: Request,
    when: str | None = Query(default=None,
                             description="ISO-8601 UTC reference; defaults to now"),
    min_alt: int | None = Query(default=None, ge=0, le=80),
) -> dict[str, Any]:
    """"Try something new tonight" — a few famous, beginner-friendly showpiece
    targets the user has **not** already captured that are well-placed tonight.

    The discovery companion to ``/tonight`` (which ranks everything, mostly the
    library) and ``/next-session`` (which plans a target you already have): it
    answers the beginner's "what's a good, easy thing to point at tonight?" from
    the curated showpiece whitelist, excluding anything already in the library.
    Read-only and offline. ``suggestions`` is empty (the card self-hides) when no
    location is set, nothing new is well-placed, or the library already covers the
    whitelist; ``location_source`` lets the UI explain a missing location."""
    settings = deps.get_settings(request)

    start = datetime.now(timezone.utc)
    if when:
        try:
            start = datetime.fromisoformat(when)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Bad 'when' timestamp") from exc
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)

    observer, location_source = _resolve_observer(request, settings)
    min_altitude = min_alt if min_alt is not None else int(settings.min_target_altitude_deg)

    base: dict[str, Any] = {
        "location_source": location_source,
        "observer": asdict(observer) if observer is not None else None,
        "min_altitude_deg": min_altitude,
        "suggestions": [],
    }
    if observer is None:
        return base

    lib_coords = [(t.ra_deg, t.dec_deg) for t in _library_targets(request)]
    suggestions = suggest_targets(
        observer, start,
        library_coords=lib_coords,
        min_altitude_deg=float(min_altitude),
        limit=_SUGGEST_LIMIT,
        horizon=HorizonProfile.from_pairs(settings.horizon_profile),
    )
    base["suggestions"] = [asdict(s) for s in suggestions]
    return base


def _catalog_object(catalog_id: str):  # noqa: ANN202
    """The bundled catalog object for ``catalog_id``, or ``None`` if unknown.

    Only *showpiece* ids are addressable here — the ``.ics`` link exists to back
    the suggestion card, so a non-showpiece (or bogus) id is a 404, not a way to
    calendar arbitrary catalog rows."""
    from seestack.nightplan import _SHOWPIECE_IDS

    if catalog_id not in _SHOWPIECE_IDS:
        return None
    for obj in load_catalog():
        if obj.id == catalog_id:
            return obj
    return None


@router.get("/suggest/{catalog_id}/calendar.ics")
def get_suggest_ics(
    catalog_id: str,
    request: Request,
    min_alt: int | None = Query(default=None, ge=0, le=80),
    when: str | None = Query(default=None,
                             description="ISO-8601 UTC reference; defaults to now"),
) -> Response:
    """Download the next few good observing windows for a *suggested* (not-yet-
    captured) showpiece as an ``.ics`` file, so a beginner can one-tap "Add to
    calendar" the new target the discovery card recommended. Read-only and offline,
    mirroring the per-target ``.ics``. 404s on an unknown/non-showpiece id or when
    there's no upcoming window, so the file is never blank."""
    settings = deps.get_settings(request)

    start = datetime.now(timezone.utc)
    if when:
        try:
            start = datetime.fromisoformat(when)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Bad 'when' timestamp") from exc
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)

    obj = _catalog_object(catalog_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Unknown target")

    observer, _ = _resolve_observer(request, settings)
    min_altitude = min_alt if min_alt is not None else int(settings.min_target_altitude_deg)
    if observer is None:
        raise HTTPException(status_code=404,
                            detail="No observing window to add (set a location first)")

    wins = next_observing_windows(
        observer, float(obj.ra_deg), float(obj.dec_deg),
        start_utc=start,
        min_altitude_deg=float(min_altitude),
        horizon=HorizonProfile.from_pairs(settings.horizon_profile),
        nights=_NEXT_SESSION_NIGHTS, want=_NEXT_SESSION_WANT,
    )
    if not wins:
        raise HTTPException(status_code=404, detail="No upcoming window to add")

    # Prefer the friendly common name; fall back to the catalog id (a few famous
    # objects have no proper name). A stable, filesystem-safe slug for the UID/file.
    display_name = obj.name or obj.id
    slug = obj.id.replace(" ", "_")
    location = f"{observer.lat_deg:.4f}, {observer.lon_deg:.4f}"
    events = [_window_ics_event(slug, display_name, w, location) for w in wins]
    body = to_ics(events)
    filename = f"{slug}-next-session.ics"
    return Response(
        content=body,
        media_type="text/calendar",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
