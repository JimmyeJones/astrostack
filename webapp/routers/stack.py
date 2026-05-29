"""Stacking: options schema, per-target defaults, trigger, history, downloads."""

from __future__ import annotations

import contextlib
import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from webapp import deps, pipeline
from webapp.schemas import StackOptionField, StackRunOut, stack_option_fields

router = APIRouter(tags=["stack"])

_STACK_DEFAULTS_META_KEY = "web_stack_defaults"


@router.get("/api/stack/options/schema", response_model=list[StackOptionField])
def options_schema() -> list[StackOptionField]:
    return stack_option_fields()


@router.get("/api/targets/{safe}/stack-defaults")
def get_stack_defaults(safe: str, request: Request) -> dict[str, Any]:
    settings = deps.get_settings(request)
    lib, proj = deps.open_target_project(request, safe)
    try:
        raw = proj.get_meta(_STACK_DEFAULTS_META_KEY)
    finally:
        proj.close()
        lib.close()
    merged = dict(settings.default_stack_options)
    if raw:
        with contextlib.suppress(json.JSONDecodeError):
            merged.update(json.loads(raw))
    # Fill any missing keys from the dataclass defaults via the schema.
    for fld in stack_option_fields():
        merged.setdefault(fld.key, fld.default)
    return merged


@router.put("/api/targets/{safe}/stack-defaults")
def put_stack_defaults(safe: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
    valid = {fld.key for fld in stack_option_fields()}
    clean = {k: v for k, v in body.items() if k in valid}
    lib, proj = deps.open_target_project(request, safe)
    try:
        proj.set_meta(_STACK_DEFAULTS_META_KEY, json.dumps(clean))
    finally:
        proj.close()
        lib.close()
    return clean


@router.post("/api/targets/{safe}/stack")
def trigger_stack(safe: str, body: dict[str, Any], request: Request) -> dict[str, str]:
    settings = deps.get_settings(request)
    jm = deps.get_job_manager(request)
    # Validate the target exists.
    lib, proj = deps.open_target_project(request, safe)
    proj.close()
    lib.close()
    job = pipeline.submit_stack(settings, jm, safe, body or {})
    return {"job_id": job.id}


@router.get("/api/targets/{safe}/stack-runs", response_model=list[StackRunOut])
def list_stack_runs(safe: str, request: Request) -> list[StackRunOut]:
    lib, proj = deps.open_target_project(request, safe)
    try:
        runs = list(proj.iter_stack_runs())
    finally:
        proj.close()
        lib.close()
    out = []
    for r in runs:
        out.append(StackRunOut(
            id=r.id,
            timestamp_utc=r.timestamp_utc,
            output_basename=r.output_basename,
            n_frames_used=r.n_frames_used,
            canvas_w=r.canvas_w,
            canvas_h=r.canvas_h,
            coverage_min=r.coverage_min,
            coverage_max=r.coverage_max,
            has_fits=bool(r.fits_path and Path(r.fits_path).exists()),
            has_tiff=bool(r.tiff_path and Path(r.tiff_path).exists()),
            has_preview=bool(r.preview_path and Path(r.preview_path).exists()),
            notes=r.notes,
        ))
    return out


_KIND_FIELDS = {
    "preview": ("preview_path", "image/png"),
    "fits": ("fits_path", "application/fits"),
    "tiff": ("tiff_path", "image/tiff"),
}


@router.get("/api/targets/{safe}/stack-runs/{run_id}/{kind}")
def download_stack_run(safe: str, run_id: int, kind: str, request: Request) -> FileResponse:
    if kind not in _KIND_FIELDS:
        raise HTTPException(status_code=404, detail="Unknown artifact")
    attr, media = _KIND_FIELDS[kind]
    lib, proj = deps.open_target_project(request, safe)
    try:
        run = next((r for r in proj.iter_stack_runs() if r.id == run_id), None)
    finally:
        proj.close()
        lib.close()
    if run is None:
        raise HTTPException(status_code=404, detail="No such run")
    path = getattr(run, attr)
    if not path or not Path(path).exists():
        raise HTTPException(status_code=404, detail=f"No {kind} for this run")
    filename = f"{run.output_basename}{Path(path).suffix}"
    download = kind in ("fits", "tiff")
    return FileResponse(
        path, media_type=media,
        filename=filename if download else None,
    )


@router.delete("/api/targets/{safe}/stack-runs/{run_id}")
def delete_stack_run(safe: str, run_id: int, request: Request) -> dict:
    lib, proj = deps.open_target_project(request, safe)
    try:
        proj.delete_stack_run(run_id)
    finally:
        proj.close()
        lib.close()
    return {"deleted": run_id}
