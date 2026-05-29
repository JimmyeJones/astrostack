"""Pipeline triggers: scan the incoming folder, or QC+solve one target."""

from __future__ import annotations

from fastapi import APIRouter, Request

from webapp import deps, pipeline
from webapp.schemas import ScanRequest

router = APIRouter(tags=["pipeline"])


@router.post("/api/scan")
def trigger_scan(request: Request, body: ScanRequest | None = None) -> dict[str, str]:
    settings = deps.get_settings(request)
    jm = deps.get_job_manager(request)
    root = body.root if body else None
    job = pipeline.submit_pipeline(settings, jm, root=root)
    return {"job_id": job.id}


@router.post("/api/targets/{safe}/qc-solve")
def trigger_qc_solve(safe: str, request: Request) -> dict[str, str]:
    settings = deps.get_settings(request)
    jm = deps.get_job_manager(request)
    # Ensure target exists.
    lib, proj = deps.open_target_project(request, safe)
    proj.close()
    lib.close()
    job = pipeline.submit_qc_solve(settings, jm, safe)
    return {"job_id": job.id}
