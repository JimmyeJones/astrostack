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
