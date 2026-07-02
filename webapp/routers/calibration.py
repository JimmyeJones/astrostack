"""Calibration masters: build, list and delete library-level dark/flat frames."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from webapp import calibration, deps, pipeline
from seestack.calibrate.masters import VALID_KINDS, VALID_METHODS

router = APIRouter(tags=["calibration"])


@router.get("/api/calibration/masters")
def list_masters(request: Request) -> list[dict[str, Any]]:
    settings = deps.get_settings(request)
    return calibration.list_masters(settings.resolved_library_root)


@router.post("/api/calibration/masters")
def build_master(body: dict[str, Any], request: Request) -> dict[str, str]:
    settings = deps.get_settings(request)
    jm = deps.get_job_manager(request)

    kind = str(body.get("kind", "")).lower()
    if kind not in VALID_KINDS:
        raise HTTPException(status_code=400,
                            detail=f"kind must be one of {VALID_KINDS}")
    method = str(body.get("method", "median")).lower()
    if method not in VALID_METHODS:
        raise HTTPException(status_code=400,
                            detail=f"method must be one of {VALID_METHODS}")
    source_dir = str(body.get("source_dir", "")).strip()
    if not source_dir:
        raise HTTPException(status_code=400, detail="source_dir is required")
    if not Path(source_dir).is_dir():
        raise HTTPException(status_code=400,
                            detail=f"source_dir is not a folder: {source_dir}")
    try:
        sigma = float(body.get("sigma", 3.0))
    except (TypeError, ValueError):
        sigma = 3.0

    job = pipeline.submit_build_master(
        settings, jm, kind=kind, source_dir=source_dir,
        name=str(body.get("name", "")).strip() or None,
        method=method, sigma=sigma,
    )
    return {"job_id": job.id}


@router.delete("/api/calibration/masters/{master_id}")
def delete_master(master_id: int, request: Request) -> dict[str, Any]:
    settings = deps.get_settings(request)
    if not calibration.delete_master(settings.resolved_library_root, master_id):
        raise HTTPException(status_code=404, detail="No such master")
    return {"deleted": master_id}
