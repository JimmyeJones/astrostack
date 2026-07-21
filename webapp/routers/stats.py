"""Dashboard aggregates — one cheap call backing the home overview.

``GET /api/stats`` rolls up the whole library into headline numbers (targets,
frames, integration time, stacks), the most recent stacked images, the current
job activity, and free disk. The registry totals come from
:meth:`Library.campaign_stats` (no per-target SQLite opened); the recent-stacks
strip does open each project, exactly like the Gallery endpoint does.
"""

from __future__ import annotations

import time
from pathlib import Path

from fastapi import APIRouter, Request
from pydantic import BaseModel

from webapp import deps

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
    targets: list[TargetNightOut] = []
    reject_buckets: dict[str, int] = {}


# The library-progress roll-up opens each project once to read its (optional)
# user-set integration goal, so it's cached on the app like the roll-ups above.
# The signature keys on each target's activity + accepted-frame count so a fresh
# scan invalidates it; a short TTL backstops a goal edit (which doesn't bump
# ``last_activity_utc``) so a just-changed goal shows within a minute.
_PROGRESS_CACHE_TTL_S = 60.0

# Project-meta key holding a target's user-set integration goal (accepted-sub
# exposure, seconds). Mirrors ``routers.targets._GOAL_META_KEY`` — kept in sync
# by hand (a tiny stable constant); read-only here.
_GOAL_META_KEY = "integration_goal_s"


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


def _read_goal_s(proj) -> float | None:  # noqa: ANN001
    """Parse a target's stored integration goal, tolerating a stale/garbage value
    (treated as unset) so a hand-edited project can never 500 the overview."""
    raw = proj.get_meta(_GOAL_META_KEY)
    if raw is None:
        return None
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return None
    if not (val > 0) or val != val:  # non-positive or NaN → unset
        return None
    return val


def _collect_progress(lib, targets) -> list[TargetProgressOut]:
    """For every target that has collected some light, gather the inputs the
    readiness overview needs: total integration, the offline catalog object type,
    and any user-set goal. Opens each project only for the cheap goal-meta read
    (the object type is resolved offline from the library entry). A broken
    project is skipped, never 500s the dashboard."""
    from seestack.io.project import Project
    from seestack.nightplan import load_catalog
    from seestack.objectinfo import identify_object

    catalog = load_catalog()
    rows: list[TargetProgressOut] = []
    for t in targets:
        # Nothing to say for a target with no accepted light yet — mirrors the
        # readiness card, which renders nothing at zero integration.
        if not (t.total_exposure_s and t.total_exposure_s > 0):
            continue
        info = identify_object(t.name, t.ra_deg, t.dec_deg, catalog=catalog)
        goal_s: float | None = None
        proj = None
        try:
            proj = Project.open(lib.target_dir(t))
            goal_s = _read_goal_s(proj)
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
        sig = tuple(sorted(
            (t.safe_name, t.last_activity_utc or "", t.n_frames_accepted)
            for t in targets
        ))
        cache = getattr(request.app.state, "progress_cache", None)
        now = time.monotonic()
        if cache and cache["sig"] == sig and (now - cache["at"]) < _PROGRESS_CACHE_TTL_S:
            rows = cache["data"]
        else:
            rows = _collect_progress(lib, targets)
            request.app.state.progress_cache = {"sig": sig, "at": now, "data": rows}
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
                recent.append(RecentStack(
                    safe=t.safe_name,
                    target_name=t.name,
                    run_id=run.id,
                    output_basename=run.output_basename,
                    timestamp_utc=run.timestamp_utc,
                    n_frames_used=run.n_frames_used,
                    has_preview=has_preview,
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
    frames table, cached on the app between scans."""
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
    finally:
        lib.close()

    if recap is None:
        return None
    return LastNightResponse(
        n_targets=recap.n_targets,
        n_frames=recap.n_frames,
        n_kept=recap.n_kept,
        n_set_aside=recap.n_set_aside,
        session_exposure_s=recap.session_exposure_s,
        kept_exposure_s=recap.kept_exposure_s,
        start_utc=recap.start_utc,
        end_utc=recap.end_utc,
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
    )
