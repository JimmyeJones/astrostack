"""Dashboard aggregates — one cheap call backing the home overview.

``GET /api/stats`` rolls up the whole library into headline numbers (targets,
frames, integration time, stacks), the most recent stacked images, the current
job activity, and free disk. The registry totals come from
:meth:`Library.campaign_stats` (no per-target SQLite opened); the recent-stacks
strip does open each project, exactly like the Gallery endpoint does.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from webapp import deps, video
from webapp.goals import read_goal_s
from webapp.registry_cache import cached_for_registry, registry_signature
from webapp.site_location import resolve_site_lon

router = APIRouter(tags=["stats"])

# The per-target roll-up opens every project's SQLite, which is the expensive
# part of this endpoint on a library with many targets. We cache that result on
# the app and reuse it while nothing has changed. The cache key is a cheap
# signature of the registry (each target's last-activity stamp), so a completed
# stack — which bumps ``last_activity_utc`` — invalidates it immediately; the TTL
# is only a backstop for changes the signature can't see (e.g. a deleted run).
_STATS_CACHE_TTL_S = 30.0


class RecentStack(BaseModel):
    safe: str
    target_name: str
    run_id: int
    output_basename: str
    timestamp_utc: str
    n_frames_used: int
    has_preview: bool
    # Whether the run's full-resolution FITS exists — gates the "Full-res PNG"
    # download so it's only offered when there's a FITS to render at native size.
    has_fits: bool = False
    preview_url: str


class StatsResponse(BaseModel):
    n_targets: int
    n_frames: int
    n_frames_accepted: int
    total_exposure_s: float
    integration_hours: float
    acceptance_rate: float | None
    n_stack_runs: int
    n_targets_with_stacks: int
    active_jobs: int
    recent_stacks: list[RecentStack]
    disk: dict
    #: Finished Moon/Sun stills (``<data_root>/video/``). Additive with a
    #: default, so an older frontend ignores it. These are pictures the library
    #: roll-up above genuinely cannot see — a video capture ingests no FITS,
    #: solves nothing and creates no stack run — so anything asking "does this
    #: user have a picture yet?" has to count them separately, or tell someone
    #: holding a finished Moon picture that they haven't made one.
    n_video_stills: int = 0


# The combined "Last night" card opens each project to read its frames, so it's
# cached on the app like the stack roll-up above. The signature keys on each
# target's last-activity stamp, which bumps whenever new frames are ingested, so
# a fresh scan invalidates it promptly; the TTL backstops changes the signature
# can't see.
_LAST_NIGHT_CACHE_TTL_S = 60.0


class TargetNightOut(BaseModel):
    name: str
    safe: str
    n_frames: int
    n_kept: int
    n_set_aside: int
    exposure_s: float
    kept_exposure_s: float


class LastNightResponse(BaseModel):
    """The library's most recent capture night, combined across targets."""

    n_targets: int
    n_frames: int
    n_kept: int
    n_set_aside: int
    session_exposure_s: float
    kept_exposure_s: float
    start_utc: str | None = None
    end_utc: str | None = None
    # The *observing night* this session belongs to, as ISO ``YYYY-MM-DD`` — the
    # noon-to-noon local bucket the imaging calendar, the per-target Nights card
    # and the "Last session" recap all use. Additive and optional: ``None`` when
    # the start time can't be parsed, and an older frontend keeps labelling from
    # the raw UTC stamps.
    night_date: str | None = None
    targets: list[TargetNightOut] = []
    reject_buckets: dict[str, int] = {}


# The library-progress roll-up opens each project once to read its (optional)
# user-set integration goal, so it's cached on the app like the roll-ups above.
# The signature keys on each target's activity + accepted-frame count so a fresh
# scan invalidates it; a short TTL backstops a goal edit (which doesn't bump
# ``last_activity_utc``) so a just-changed goal shows within a minute.
_PROGRESS_CACHE_TTL_S = 60.0


class TargetProgressOut(BaseModel):
    """One target's inputs for the Dashboard "Target progress" overview. The
    readiness verdict itself is computed client-side (single source of truth in
    ``readiness.ts``) from these — accumulated integration, the catalog object
    type (for the per-type goal), and any user-set goal override."""

    safe: str
    name: str
    total_exposure_s: float
    object_type: str | None = None
    goal_s: float | None = None
    # This target's recent productive pace — median kept integration per clear
    # night over its last few nights (seconds), or null when there isn't enough
    # history to call it a pace. Lets the overview turn "how far to go?" into
    # "about N more clear nights", the same figure the Target page derives
    # client-side from its night list. Additive and optional: an older frontend
    # ignores it, and a null simply means the row says nothing about nights.
    recent_pace_s: float | None = None


def _collect_progress(lib, targets) -> list[TargetProgressOut]:
    """For every target that has collected some light, gather the inputs the
    readiness overview needs: total integration, the offline catalog object type,
    any user-set goal, and the target's recent per-night pace. Opens each project
    once for the cheap goal-meta read plus a three-column scan of its dated frames
    (the object type is resolved offline from the library entry). A broken project
    is skipped, never 500s the dashboard."""
    from seestack.io.project import Project
    from seestack.nightplan import load_catalog
    from seestack.objectinfo import identify_object
    from seestack.session_recap import recent_night_pace_s

    catalog = load_catalog()
    rows: list[TargetProgressOut] = []
    for t in targets:
        # Nothing to say for a target with no accepted light yet — mirrors the
        # readiness card, which renders nothing at zero integration.
        if not (t.total_exposure_s and t.total_exposure_s > 0):
            continue
        info = identify_object(t.name, t.ra_deg, t.dec_deg, catalog=catalog)
        goal_s: float | None = None
        pace_s: float | None = None
        proj = None
        try:
            proj = Project.open(lib.target_dir(t))
            goal_s = read_goal_s(proj)
            pace_s = recent_night_pace_s(proj)
        except Exception:  # noqa: BLE001 — a broken project must not 500 the dashboard
            pass
        finally:
            if proj is not None:
                proj.close()
        rows.append(TargetProgressOut(
            safe=t.safe_name,
            name=t.name,
            total_exposure_s=t.total_exposure_s,
            object_type=info.type if info is not None else None,
            goal_s=goal_s,
            recent_pace_s=pace_s,
        ))
    return rows


@router.get("/api/library-progress", response_model=list[TargetProgressOut])
def get_library_progress(request: Request) -> list[TargetProgressOut]:
    """Per-target integration progress for the Dashboard "Target progress" card —
    how close each target is to a clean image, across the whole library. Returns
    an empty list until some light has been collected. Read-only aggregation over
    the registry + a cheap per-target goal read, cached on the app between scans.
    """
    lib = deps.open_library(request)
    try:
        targets = lib.list_targets()
        rows = cached_for_registry(
            request.app, "library_progress", registry_signature(targets),
            lambda: _collect_progress(lib, targets),
            ttl_s=_PROGRESS_CACHE_TTL_S,
        )
    finally:
        lib.close()
    return rows


# The "Your sky, so far" summary is registry-only (no per-target SQLite opened),
# so it's already cheap; we cache it mainly to avoid re-``stat``-ing every
# target's preview file on each render. The signature keys on each target's
# activity + accepted-frame count + latest preview, so a fresh scan or a new
# stack invalidates it promptly; the TTL backstops changes the signature misses.
_SUMMARY_CACHE_TTL_S = 60.0


class SummaryTargetOut(BaseModel):
    """A standout or hero target in the "Your sky, so far" summary."""

    safe: str
    name: str
    total_exposure_s: float
    integration_hours: float
    n_frames_accepted: int
    thumbnail_url: str | None = None


class LibrarySummaryResponse(BaseModel):
    """Whole-library personal-progress roll-up for the "Your sky, so far" page."""

    n_targets_imaged: int
    n_subs_kept: int
    total_integration_s: float
    integration_hours: float
    first_light_utc: str | None = None
    longest_target: SummaryTargetOut | None = None
    most_imaged_target: SummaryTargetOut | None = None
    heroes: list[SummaryTargetOut] = []


def _summary_target_out(t) -> SummaryTargetOut:  # noqa: ANN001 — SummaryTarget
    return SummaryTargetOut(
        safe=t.safe,
        name=t.name,
        total_exposure_s=t.total_exposure_s,
        integration_hours=round(t.total_exposure_s / 3600.0, 2),
        n_frames_accepted=t.n_frames_accepted,
        # The target thumbnail endpoint serves the latest stack preview; only
        # offer it for a target we know still has one on disk.
        thumbnail_url=(f"/api/targets/{t.safe}/thumbnail" if t.has_preview else None),
    )


@router.get("/api/library/summary", response_model=LibrarySummaryResponse)
def get_library_summary(request: Request) -> LibrarySummaryResponse:
    """The "Your sky, so far" whole-library progress summary — total kept
    integration, subs kept, targets imaged, first-light date, the standout
    targets, and a hero grid of finished pictures. Registry-only, read-only
    aggregation over data already on disk; cached on the app between scans.
    Returns zeroed tallies (and ``null`` standouts) until some light is
    collected."""
    from seestack.library_summary import summarize_library

    lib = deps.open_library(request)
    try:
        targets = lib.list_targets()
        sig = tuple(sorted(
            (t.safe_name, t.last_activity_utc or "", t.n_frames_accepted,
             t.last_stack_preview or "")
            for t in targets
        ))
        cache = getattr(request.app.state, "summary_cache", None)
        now = time.monotonic()
        if cache and cache["sig"] == sig and (now - cache["at"]) < _SUMMARY_CACHE_TTL_S:
            summary = cache["data"]
        else:
            summary = summarize_library(
                targets,
                preview_exists=lambda p: bool(p) and Path(p).exists(),
            )
            request.app.state.summary_cache = {"sig": sig, "at": now, "data": summary}
    finally:
        lib.close()

    return LibrarySummaryResponse(
        n_targets_imaged=summary.n_targets_imaged,
        n_subs_kept=summary.n_subs_kept,
        total_integration_s=summary.total_integration_s,
        integration_hours=round(summary.total_integration_s / 3600.0, 2),
        first_light_utc=summary.first_light_utc,
        longest_target=(
            _summary_target_out(summary.longest_target)
            if summary.longest_target else None
        ),
        most_imaged_target=(
            _summary_target_out(summary.most_imaged_target)
            if summary.most_imaged_target else None
        ),
        heroes=[_summary_target_out(h) for h in summary.heroes],
    )


def _rollup_stacks(lib, targets) -> tuple[list[RecentStack], int, int]:
    """Open each target's project and collect its stack runs. Expensive — this
    is what the cache below is protecting."""
    from seestack.io.project import Project

    recent: list[RecentStack] = []
    n_stack_runs = 0
    n_targets_with_stacks = 0
    for t in targets:
        proj = None
        try:
            proj = Project.open(lib.target_dir(t))
            target_runs = 0
            for run in proj.iter_stack_runs():
                target_runs += 1
                has_preview = bool(run.preview_path and Path(run.preview_path).exists())
                has_fits = bool(run.fits_path and Path(run.fits_path).exists())
                recent.append(RecentStack(
                    safe=t.safe_name,
                    target_name=t.name,
                    run_id=run.id,
                    output_basename=run.output_basename,
                    timestamp_utc=run.timestamp_utc,
                    n_frames_used=run.n_frames_used,
                    has_preview=has_preview,
                    has_fits=has_fits,
                    preview_url=f"/api/targets/{t.safe_name}/stack-runs/{run.id}/preview",
                ))
            n_stack_runs += target_runs
            if target_runs:
                n_targets_with_stacks += 1
        except Exception:  # noqa: BLE001 — a broken project must not 500 the dashboard
            pass
        finally:
            if proj is not None:
                proj.close()
    recent.sort(key=lambda r: r.timestamp_utc, reverse=True)
    return recent, n_stack_runs, n_targets_with_stacks


def _collect_last_night(lib, targets):
    """Open each project, trim it to its most recent session, and combine every
    target's latest night into one recap. Expensive (opens every project) — the
    caller caches it. A broken project is skipped, never 500s the dashboard."""
    from seestack.io.project import Project
    from seestack.session_recap import (
        library_session_recap,
        recent_session_window_frames,
    )

    rows: list[tuple[str, str, list]] = []
    for t in targets:
        proj = None
        try:
            proj = Project.open(lib.target_dir(t))
            # Keep only each target's recent-night *window* inside the loop so we
            # never hold every target's full frame list at once (memory-bounded),
            # but — unlike a per-target last-session trim — without severing a
            # night that another target bridges: the precise cross-target "last
            # night" cut is made inside library_session_recap.
            last = recent_session_window_frames(list(proj.iter_frames()))
            if last:
                rows.append((t.name, t.safe_name, last))
        except Exception:  # noqa: BLE001 — a broken project must not 500 the dashboard
            pass
        finally:
            if proj is not None:
                proj.close()
    return library_session_recap(rows)


@router.get("/api/last-night", response_model=LastNightResponse | None)
def get_last_night(request: Request) -> LastNightResponse | None:
    """The library's most recent capture night, combined across every target —
    the Dashboard "what did last night give me?" card. Returns ``null`` when no
    frame anywhere carries a capture timestamp. Read-only aggregation over the
    frames table, cached on the app between scans.

    The card also gets the **observing-night** date the session belongs to,
    bucketed noon-to-noon in the observer's local time exactly as the imaging
    calendar and the per-target Nights / Last-session cards do. It is resolved
    *outside* the recap cache so a longitude change in Settings takes effect on
    the next request rather than waiting out the TTL."""
    from seestack.activity_calendar import night_date_of

    settings = deps.get_settings(request)
    lib = deps.open_library(request)
    try:
        targets = lib.list_targets()
        sig = tuple(sorted(
            (t.safe_name, t.last_activity_utc or "") for t in targets
        ))
        cache = getattr(request.app.state, "last_night_cache", None)
        now = time.monotonic()
        if cache and cache["sig"] == sig and (now - cache["at"]) < _LAST_NIGHT_CACHE_TTL_S:
            recap = cache["data"]
        else:
            recap = _collect_last_night(lib, targets)
            request.app.state.last_night_cache = {"sig": sig, "at": now, "data": recap}
        lon = resolve_site_lon(request, lib, settings.site_lon)
    finally:
        lib.close()

    if recap is None:
        return None
    night = night_date_of(recap.start_utc, lon) if recap.start_utc else None
    return LastNightResponse(
        n_targets=recap.n_targets,
        n_frames=recap.n_frames,
        n_kept=recap.n_kept,
        n_set_aside=recap.n_set_aside,
        session_exposure_s=recap.session_exposure_s,
        kept_exposure_s=recap.kept_exposure_s,
        start_utc=recap.start_utc,
        end_utc=recap.end_utc,
        night_date=night.isoformat() if night is not None else None,
        targets=[
            TargetNightOut(
                name=c.name, safe=c.safe,
                n_frames=c.n_frames, n_kept=c.n_kept, n_set_aside=c.n_set_aside,
                exposure_s=c.exposure_s, kept_exposure_s=c.kept_exposure_s,
            )
            for c in recap.targets
        ],
        reject_buckets=recap.reject_buckets,
    )


@router.get("/api/stats", response_model=StatsResponse)
def get_stats(request: Request, recent_limit: int = 8) -> StatsResponse:
    import shutil

    # Clamp the user-supplied slice size like every other int query param in the
    # routers (render `size`, frame_preview `size`): a negative value would slice
    # `recent[:-n]` and silently drop stacks, and 0 would hand back an empty strip
    # — both wrong for "the most recent N".
    recent_limit = max(1, min(100, recent_limit))
    settings = deps.get_settings(request)
    jm = deps.get_job_manager(request)

    lib = deps.open_library(request)
    try:
        camp = lib.campaign_stats()
        targets = lib.list_targets()
        # Cheap signature over the registry: the roll-up only changes when the
        # set of targets, their activity stamp, or their latest-stack preview
        # does. Any of those bumps when a stack completes, so the cache refreshes
        # promptly; the TTL backstops the rare same-second collision.
        sig = tuple(sorted(
            (t.safe_name, t.last_activity_utc or "", t.last_stack_preview or "")
            for t in targets
        ))
        cache = getattr(request.app.state, "stats_cache", None)
        now = time.monotonic()
        if cache and cache["sig"] == sig and (now - cache["at"]) < _STATS_CACHE_TTL_S:
            recent, n_stack_runs, n_targets_with_stacks = cache["data"]
        else:
            recent, n_stack_runs, n_targets_with_stacks = _rollup_stacks(lib, targets)
            request.app.state.stats_cache = {
                "sig": sig, "at": now,
                "data": (recent, n_stack_runs, n_targets_with_stacks),
            }
    finally:
        lib.close()

    disk: dict = {}
    try:
        usage = shutil.disk_usage(settings.data_root)
        disk = {
            "total_gb": round(usage.total / 1e9, 1),
            "used_gb": round(usage.used / 1e9, 1),
            "free_gb": round(usage.free / 1e9, 1),
        }
    except OSError:
        pass

    n_frames = camp["n_frames"]
    n_accepted = camp["n_frames_accepted"]
    total_exposure_s = camp["total_exposure_s"]
    active = len([j for j in jm.list(limit=100) if j.state in ("queued", "running")])

    return StatsResponse(
        n_targets=camp["n_targets"],
        n_frames=n_frames,
        n_frames_accepted=n_accepted,
        total_exposure_s=total_exposure_s,
        integration_hours=round(total_exposure_s / 3600.0, 2),
        acceptance_rate=(n_accepted / n_frames) if n_frames else None,
        n_stack_runs=n_stack_runs,
        n_targets_with_stacks=n_targets_with_stacks,
        active_jobs=active,
        recent_stacks=recent[:recent_limit],
        disk=disk,
        n_video_stills=video.count_results(settings),
    )


# "Your imaging calendar" — a temporal, whole-hobby activity heatmap. Opening
# every project to read its capture timestamps is the expensive part, so the
# result is cached on the app exactly like the roll-ups above; the signature
# keys on each target's activity stamp so a fresh scan invalidates it promptly.
_ACTIVITY_CACHE_TTL_S = 120.0


class NightActivityOut(BaseModel):
    date: str            # observing-night date, ISO ``YYYY-MM-DD``
    exposure_s: float
    n_frames: int
    targets: list[str]


class ActivityCalendarOut(BaseModel):
    """The library's imaging activity over a trailing window of nights, one cell
    per observing night — the Dashboard "your imaging calendar" heatmap."""

    start_date: str
    end_date: str
    months: int
    nights: list[NightActivityOut] = []
    n_nights: int
    total_exposure_s: float
    nights_this_month: int
    best_streak_nights: int


def _collect_activity_calendar(lib, targets, *, today, months, lon_deg):
    """Stream every target's capture timestamps into a per-night accumulator and
    finalize the trailing-window calendar. Memory-bounded — each project's frames
    are folded and released before the next opens — and a broken project is
    skipped, never 500s the dashboard."""
    from seestack.activity_calendar import accumulate_nights, finalize_calendar
    from seestack.io.project import Project

    acc: dict = {}
    for t in targets:
        proj = None
        try:
            proj = Project.open(lib.target_dir(t))
            # Accepted-only so the calendar's per-night exposure agrees with the
            # stats tile's kept-frame total (which counts accept=1). Counting
            # rejected/set-aside subs here painted a clouded-out, fully-rejected
            # night as a deep "long night" cell and over-reported total exposure
            # versus the tile beside it.
            accumulate_nights(
                ((f.timestamp_utc, f.exposure_s, t.name)
                 for f in proj.iter_frames(accepted_only=True)),
                acc, lon_deg=lon_deg,
            )
        except Exception:  # noqa: BLE001 — a broken project must not 500 the dashboard
            pass
        finally:
            if proj is not None:
                proj.close()
    return finalize_calendar(acc, today=today, months=months)


def _cached_activity_calendar(request: Request, months: int):
    """The trailing-window activity calendar, from the app cache when warm.

    Extracted so the recap poster can reuse the *same* cached result as the
    Dashboard heatmap — opening every project to read capture timestamps is the
    expensive part, and asking for a night count shouldn't pay for it twice.
    """
    settings = deps.get_settings(request)
    lib = deps.open_library(request)
    try:
        targets = lib.list_targets()
        # Explicit Settings longitude wins; otherwise sniff it from a frame's FITS
        # header (the common Seestar case), so noon-to-noon bucketing is right out
        # of the box even when the owner never configured a location. Shared with
        # the Target page's Nights card so the two never name a night differently.
        lon = resolve_site_lon(request, lib, settings.site_lon)
        offset_h = (lon / 15.0) if lon is not None else 0.0
        today = (datetime.now(timezone.utc) + timedelta(hours=offset_h)).date()

        sig = (
            months, lon,
            tuple(sorted((t.safe_name, t.last_activity_utc or "") for t in targets)),
        )
        cache = getattr(request.app.state, "activity_calendar_cache", None)
        now = time.monotonic()
        if cache and cache["sig"] == sig and (now - cache["at"]) < _ACTIVITY_CACHE_TTL_S:
            return cache["data"]
        cal = _collect_activity_calendar(
            lib, targets, today=today, months=months, lon_deg=lon)
        request.app.state.activity_calendar_cache = {
            "sig": sig, "at": now, "data": cal}
        return cal
    finally:
        lib.close()


@router.get("/api/activity-calendar", response_model=ActivityCalendarOut)
def get_activity_calendar(request: Request, months: int = 12) -> ActivityCalendarOut:
    """The library's imaging activity as a calendar heatmap — one cell per
    observing night, shaded by that night's total capture time. Read-only
    aggregation over the frames tables, cached on the app between scans. Nights
    are bucketed noon-to-noon in the observer's local time (from ``site_lon`` when
    set, else a frame's ``SITELONG`` header, else UTC), so a single midnight-
    spanning session lands in one cell."""
    months = max(1, min(24, months))
    cal = _cached_activity_calendar(request, months)

    return ActivityCalendarOut(
        start_date=cal.start_date,
        end_date=cal.end_date,
        months=cal.months,
        nights=[
            NightActivityOut(
                date=n.date, exposure_s=n.exposure_s,
                n_frames=n.n_frames, targets=n.targets,
            )
            for n in cal.nights
        ],
        n_nights=cal.n_nights,
        total_exposure_s=cal.total_exposure_s,
        nights_this_month=cal.nights_this_month,
        best_streak_nights=cal.best_streak_nights,
    )


# --- "Share your sky": a recap poster of everything you've captured ---------
#
# The numbers a hobbyist is quietly proud of (nights out, integration, targets,
# subs kept, biggest project) already exist on the "Your sky, so far" page — but
# only as a web page nobody else can see. These two read-only endpoints turn the
# same figures into something shareable: the copy-paste caption, and a square
# poster with the user's own best picture as the backdrop.


class RecapStatOut(BaseModel):
    value: str
    label: str


class RecapOut(BaseModel):
    """The shareable recap of the whole library.

    ``has_anything`` is false until some light has been collected — the caller's
    cue to hide the share card entirely rather than offer an empty poster."""

    has_anything: bool
    caption: str
    since: str
    stats: list[RecapStatOut] = []
    window_months: int
    n_nights: int
    n_targets: int
    n_subs_kept: int
    total_integration_s: float
    top_target_name: str | None = None
    top_target_integration_s: float | None = None
    # The "what else you pointed at" line ("Also shot: M 42, NGC 7000 and 5
    # more"), or "" on a one-target library. Additive; the poster carries the
    # same line.
    also_shot: str = ""


def _recap_facts(request: Request, months: int):
    """Collect the recap facts from the roll-ups the app already serves.

    Registry-only for the totals/standouts (:func:`summarize_library`), plus the
    activity calendar's night count — both read through their existing caches, so
    a recap costs nothing the Dashboard hasn't already paid for.
    """
    from seestack.library_summary import summarize_library
    from seestack.recap import RecapFacts

    lib = deps.open_library(request)
    try:
        summary = summarize_library(
            lib.list_targets(),
            preview_exists=lambda p: bool(p) and Path(p).exists(),
        )
    finally:
        lib.close()
    cal = _cached_activity_calendar(request, months)
    top = summary.longest_target
    # The rest of what you pointed at, ranked by integration — every imaged
    # target (not just the ones with a finished picture), minus the biggest
    # project, which has its own line. A few more than the line prints, so the
    # pure layer's de-duplication still has something to work with.
    others = tuple(
        t.name for t in summary.imaged_ranked
        if top is None or t.safe != top.safe
    )[:8]
    return summary, RecapFacts(
        total_integration_s=summary.total_integration_s,
        n_targets=summary.n_targets_imaged,
        n_subs_kept=summary.n_subs_kept,
        n_nights=cal.n_nights,
        window_months=months,
        first_light_utc=summary.first_light_utc,
        top_target_name=top.name if top is not None else None,
        top_target_integration_s=top.total_exposure_s if top is not None else None,
        other_target_names=others,
    )


@router.get("/api/recap", response_model=RecapOut)
def get_recap(request: Request, months: int = 12) -> RecapOut:
    """The shareable "your sky, so far" recap — the poster's own figures plus the
    copy-paste caption to post beside it. Read-only; returns
    ``has_anything=false`` (and empty text) on a library that hasn't collected
    any light yet, so the share card self-hides instead of offering a blank
    poster."""
    from seestack.recap import (
        recap_caption, recap_other_targets_line, recap_since_line, recap_stats,
    )

    months = max(1, min(24, months))
    summary, facts = _recap_facts(request, months)
    stats = recap_stats(facts)
    return RecapOut(
        has_anything=bool(stats),
        caption=recap_caption(facts),
        since=recap_since_line(facts),
        stats=[RecapStatOut(value=v, label=lbl) for v, lbl in stats],
        window_months=months,
        n_nights=facts.n_nights or 0,
        n_targets=summary.n_targets_imaged,
        n_subs_kept=summary.n_subs_kept,
        total_integration_s=summary.total_integration_s,
        top_target_name=facts.top_target_name,
        top_target_integration_s=facts.top_target_integration_s,
        also_shot=recap_other_targets_line(facts),
    )


def _recap_hero(request: Request, summary):
    """The user's own best picture for the poster backdrop, or ``None``.

    The heroes are already ranked by integration, so the first one that still has
    a readable preview on disk is "your biggest finished project". Best-effort:
    an unreadable or deleted preview simply falls through to the next, and an
    all-empty list gives the poster its plain deep-space background rather than
    an error."""
    from PIL import Image

    lib = deps.open_library(request)
    try:
        by_safe = {t.safe_name: t for t in lib.list_targets()}
        for hero in summary.heroes:
            entry = by_safe.get(hero.safe)
            path = getattr(entry, "last_stack_preview", None) if entry else None
            if not path:
                continue
            try:
                with Image.open(path) as img:
                    return img.convert("RGB")
            except Exception:  # noqa: BLE001 — a bad preview must not sink the poster
                continue
    finally:
        lib.close()
    return None


@router.get("/api/recap.jpg")
def get_recap_poster(request: Request, months: int = 12) -> Response:
    """Download the recap as one square, social-ready JPEG.

    Rendered on demand from the same figures ``/api/recap`` reports, over the
    user's own best picture. Nothing is written to the library — this is a
    display-time render, like the share export."""
    import io

    from seestack.recap import draw_recap_poster

    months = max(1, min(24, months))
    summary, facts = _recap_facts(request, months)
    poster = draw_recap_poster(facts, hero=_recap_hero(request, summary))
    buf = io.BytesIO()
    poster.save(buf, format="JPEG", quality=92)
    return Response(
        content=buf.getvalue(),
        media_type="image/jpeg",
        headers={"Content-Disposition": 'attachment; filename="my-sky-so-far.jpg"'},
    )


def _collect_imaging_log(lib, targets) -> list:
    """Walk the library and build one imaging-log row per finished stack run.

    Expensive (opens every project + reads each frame's stored FWHM), but this is
    a deliberate one-tap download, not a page render, so it isn't cached. A broken
    project is skipped, never 500s the download.
    """
    from statistics import median

    from seestack.imaging_log import ImagingLogRow
    from seestack.io.project import Project

    rows: list[ImagingLogRow] = []
    for t in targets:
        proj = None
        try:
            proj = Project.open(lib.target_dir(t))
            # Typical star size for this target: the median of its accepted frames'
            # already-stored FWHM (measured by QC — no image recompute here).
            fwhms = [
                f.fwhm_px
                for f in proj.iter_frames(accepted_only=True)
                if f.fwhm_px is not None and f.fwhm_px > 0
            ]
            median_fwhm = float(median(fwhms)) if fwhms else None
            for run in proj.iter_stack_runs():
                # Prefer *this stack's own* measured sharpness (per-run, schema
                # ≥ 14) so the log reflects each night's result; fall back to the
                # target-wide frame median for older runs that predate the column.
                run_fwhm = (
                    run.stack_fwhm_px
                    if run.stack_fwhm_px is not None and run.stack_fwhm_px > 0
                    else median_fwhm
                )
                rows.append(ImagingLogRow(
                    date=run.timestamp_utc,
                    target_name=t.name,
                    n_subs=run.n_frames_used,
                    integration_s=run.total_exposure_s,
                    median_fwhm_px=run_fwhm,
                    calibration=run.calstat,
                    is_mosaic=run.is_mosaic,
                    noise_sigma=run.noise_sigma,
                    app_version=run.engine_version,
                ))
        except Exception:  # noqa: BLE001 — a broken project must not 500 the download
            pass
        finally:
            if proj is not None:
                proj.close()
    # Newest first, so a beginner's most recent night sits at the top of the log.
    rows.sort(key=lambda r: (r.date or ""), reverse=True)
    return rows


@router.get("/api/imaging-log.csv")
def get_imaging_log(request: Request) -> Response:
    """Download a plain-CSV record of every finished stack — the beginner's
    imaging journal. One row per stack run (date, target, subs, integration,
    typical star size, calibration, mosaic, noise, app version), newest first.
    An empty library yields a header-only file, never an error."""
    from seestack.imaging_log import build_imaging_log_csv

    lib = deps.open_library(request)
    try:
        rows = _collect_imaging_log(lib, lib.list_targets())
    finally:
        lib.close()
    csv_text = build_imaging_log_csv(rows)
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="imaging-log.csv"'},
    )
