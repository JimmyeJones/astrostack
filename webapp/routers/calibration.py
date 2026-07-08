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
    try:
        is_dir = Path(source_dir).is_dir()
    except (OSError, ValueError):
        # e.g. an embedded null byte raises ValueError on some platforms
        # rather than returning False — still a client-supplied bad path (400),
        # not a server fault (500).
        is_dir = False
    if not is_dir:
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


def _median(values: list[float]) -> float | None:
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return None
    n = len(vals)
    return vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2.0


@router.get("/api/targets/{safe}/calibration-suggestions")
def calibration_suggestions(safe: str, request: Request) -> dict[str, Any]:
    """Recommend the dark/flat masters that best match this target's frames.

    Reads the median exposure/gain/sensor-temperature of the target's accepted
    frames and ranks the library's masters against them, so a beginner doesn't
    have to know which dark/flat goes with which lights. Purely advisory — the
    Stack form still lets the user pick anything (or nothing).
    """
    settings = deps.get_settings(request)
    lib, proj = deps.open_target_project(request, safe)
    try:
        frames = list(proj.iter_frames(accepted_only=True))
    finally:
        proj.close()
        lib.close()
    exposure_s = _median([f.exposure_s for f in frames if f.exposure_s])
    gain = _median([f.gain for f in frames if f.gain is not None])
    sensor_temp_c = _median([f.sensor_temp_c for f in frames if f.sensor_temp_c is not None])

    masters = calibration.list_masters(settings.resolved_library_root)
    rec = calibration.recommend_masters(
        masters, exposure_s=exposure_s, gain=gain, sensor_temp_c=sensor_temp_c)
    rec["n_frames"] = len(frames)
    return rec


@router.delete("/api/calibration/masters/{master_id}")
def delete_master(master_id: int, request: Request) -> dict[str, Any]:
    settings = deps.get_settings(request)
    if not calibration.delete_master(settings.resolved_library_root, master_id):
        raise HTTPException(status_code=404, detail="No such master")
    return {"deleted": master_id}
