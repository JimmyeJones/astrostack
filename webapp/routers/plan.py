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
    HorizonProfile,
    LibraryTarget,
    Observer,
    load_catalog,
    next_observing_windows,
    plan_tonight,
    suggest_targets,
)
from webapp import deps
from webapp.ics import IcsEvent, to_ics

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/plan", tags=["plan"])

# Cap how many frames we probe for a site location so a big library with no
# SITELAT header anywhere can't turn one request into thousands of header reads.
_MAX_SITE_PROBE_FRAMES = 24

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


def _parse_angle(value: Any) -> float | None:
    """Parse a FITS angle that may be a float (deg) or a 'DD:MM:SS' string."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        pass
    # Sexagesimal 'DD:MM:SS' / 'DD MM SS'.
    parts = s.replace(":", " ").split()
    try:
        nums = [float(p) for p in parts]
    except ValueError:
        return None
    if not nums:
        return None
    sign = -1.0 if nums[0] < 0 or s.lstrip().startswith("-") else 1.0
    deg = abs(nums[0])
    if len(nums) > 1:
        deg += nums[1] / 60.0
    if len(nums) > 2:
        deg += nums[2] / 3600.0
    return sign * deg


def _site_from_header(header: dict) -> tuple[float, float] | None:
    """(lat, lon) in degrees from a raw FITS header, or None if absent/bad."""
    lat = _parse_angle(header.get("SITELAT"))
    lon = _parse_angle(header.get("SITELONG") or header.get("SITELONG "))
    if lat is None or lon is None:
        return None
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return None
    return lat, lon


def _detect_site_from_fits(request: Request) -> tuple[float, float] | None:
    """Best-effort observer lat/lon from a recent frame's FITS header.

    Reads headers only (fast, no pixel data), tries the cached copy before the
    original NAS path, and bails after a bounded number of probes. Any read
    error is swallowed — a missing site just means the caller must configure one.
    """
    from seestack.io.fits_loader import load_header
    from seestack.io.project import Project

    lib = deps.open_library(request)
    probed = 0
    try:
        for entry in lib.list_targets():
            proj = None
            try:
                proj = Project.open(lib.target_dir(entry))
                for frame in proj.iter_frames(accepted_only=True):
                    if probed >= _MAX_SITE_PROBE_FRAMES:
                        return None
                    for path in (frame.cached_path, frame.source_path):
                        if not path:
                            continue
                        probed += 1
                        try:
                            info = load_header(path)
                        except Exception:  # noqa: BLE001 — unreadable frame, move on
                            continue
                        site = _site_from_header(info.raw_header)
                        if site is not None:
                            return site
                        break  # one readable path per frame is enough
            except Exception:  # noqa: BLE001 — a broken project must not 500 the plan
                continue
            finally:
                if proj is not None:
                    proj.close()
    finally:
        lib.close()
    return None


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
    """Library targets that have a position, for the 'already targeted' set."""
    lib = deps.open_library(request)
    try:
        out: list[LibraryTarget] = []
        for t in lib.list_targets():
            if t.ra_deg is None or t.dec_deg is None:
                continue
            out.append(LibraryTarget(
                safe=t.safe_name, name=t.name,
                ra_deg=float(t.ra_deg), dec_deg=float(t.dec_deg),
                frames_accepted=int(t.n_frames_accepted or 0),
                total_exposure_s=float(t.total_exposure_s or 0.0),
            ))
        return out
    finally:
        lib.close()


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


# How many nights ahead to scan for a target's next good window, and how many
# such windows to return. Two weeks covers "come back when the Moon's out of the
# way" without turning one request into a long ephemeris grind; three windows is
# enough to say "your next session — and the couple after it" when a goal needs
# more than one night.
_NEXT_SESSION_NIGHTS = 14
_NEXT_SESSION_WANT = 3


@router.get("/next-session/{safe}")
def get_next_session(
    safe: str,
    request: Request,
    min_alt: int | None = Query(default=None, ge=0, le=80),
    when: str | None = Query(default=None,
                             description="ISO-8601 UTC reference to plan from; defaults to now"),
) -> dict[str, Any]:
    """When to next point the scope at *this* target — the forward-looking
    companion to ``/tonight``.

    Returns the next few nights (up to ``_NEXT_SESSION_WANT``) this target clears
    the altitude floor for a usable stretch of darkness, so the Target page can
    turn "you're 2 h short of a good M31" into "…and Thursday 22:40 → 02:10 is
    your next good window". Read-only and offline. ``windows`` is empty (the card
    self-hides) when no location is set, the target has no position, or nothing is
    well-placed in the horizon; ``target_has_position``/``location_source`` let the
    UI explain which.
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
        nights=_NEXT_SESSION_NIGHTS, want=_NEXT_SESSION_WANT,
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
