"""Dashboard aggregates — one cheap call backing the home overview.

``GET /api/stats`` rolls up the whole library into headline numbers (targets,
frames, integration time, stacks), the most recent stacked images, the current
job activity, and free disk. The registry totals come from
:meth:`Library.campaign_stats` (no per-target SQLite opened); the recent-stacks
strip does open each project, exactly like the Gallery endpoint does.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from pydantic import BaseModel

from webapp import deps

router = APIRouter(tags=["stats"])


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


@router.get("/api/stats", response_model=StatsResponse)
def get_stats(request: Request, recent_limit: int = 8) -> StatsResponse:
    import shutil

    settings = deps.get_settings(request)
    jm = deps.get_job_manager(request)

    lib = deps.open_library(request)
    recent: list[RecentStack] = []
    n_stack_runs = 0
    n_targets_with_stacks = 0
    try:
        camp = lib.campaign_stats()
        from seestack.io.project import Project

        for t in lib.list_targets():
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
    finally:
        lib.close()

    recent.sort(key=lambda r: r.timestamp_utc, reverse=True)

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
