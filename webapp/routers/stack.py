"""Stacking: options schema, per-target defaults, trigger, history, downloads."""

from __future__ import annotations

import contextlib
import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse

from webapp import deps, pipeline
from webapp.schemas import (
    STACK_DEFAULTS_META_KEY,
    StackOptionField,
    StackRunOut,
    stack_option_fields,
)

router = APIRouter(tags=["stack"])

# Asinh stretch + black-point bounds for the renderer. Both are 0..1: stretch
# is how hard to lift faint detail; black is the black point (higher = darker
# background). See seestack.render.thumbnail.asinh_stretch.
_STRETCH_MIN, _STRETCH_MAX = 0.0, 1.0
_BLACK_MIN, _BLACK_MAX = 0.0, 1.0
_STRETCH_DEFAULT, _BLACK_DEFAULT = 0.5, 0.35


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _run_fits_path(request: Request, safe: str, run_id: int) -> tuple[str, str | None]:
    """Return (basename, fits_path) for a run, or raise 404."""
    lib, proj = deps.open_target_project(request, safe)
    try:
        run = next((r for r in proj.iter_stack_runs() if r.id == run_id), None)
    finally:
        proj.close()
        lib.close()
    if run is None:
        raise HTTPException(status_code=404, detail="No such run")
    return run.output_basename, run.fits_path


@router.get("/api/stack/options/schema", response_model=list[StackOptionField])
def options_schema() -> list[StackOptionField]:
    return stack_option_fields()


@router.get("/api/targets/{safe}/stack-defaults")
def get_stack_defaults(safe: str, request: Request) -> dict[str, Any]:
    settings = deps.get_settings(request)
    lib, proj = deps.open_target_project(request, safe)
    try:
        raw = proj.get_meta(STACK_DEFAULTS_META_KEY)
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
        proj.set_meta(STACK_DEFAULTS_META_KEY, json.dumps(clean))
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


# NOTE: declared before the "/{kind}" download route so "render" isn't
# swallowed by that catch-all path parameter.
@router.get("/api/targets/{safe}/stack-runs/{run_id}/render")
async def render_stack_run(
    safe: str, run_id: int, request: Request,
    stretch: float = _STRETCH_DEFAULT, black: float = _BLACK_DEFAULT, size: int = 1024,
) -> Response:
    """Live, adjustable re-render of a run's stacked FITS (full dynamic range).

    ``stretch`` (0..1) → how hard the asinh curve lifts faint detail; ``black``
    (0..1) → the black point (higher = darker background). Runs in a threadpool
    so it never blocks the job worker.
    """
    _, fits_path = _run_fits_path(request, safe, run_id)
    if not fits_path or not Path(fits_path).exists():
        raise HTTPException(status_code=404, detail="No FITS for this run to render")

    from seestack.render.thumbnail import render_stack_png
    png = await run_in_threadpool(
        render_stack_png, fits_path,
        stretch=_clamp(stretch, _STRETCH_MIN, _STRETCH_MAX),
        black=_clamp(black, _BLACK_MIN, _BLACK_MAX),
        max_width=int(_clamp(size, 128, 4096)),
    )
    return Response(content=png, media_type="image/png",
                    headers={"Cache-Control": "no-store"})


@router.post("/api/targets/{safe}/stack-runs/{run_id}/preview")
async def save_stack_preview(
    safe: str, run_id: int, body: dict[str, Any], request: Request,
) -> dict[str, Any]:
    """Persist a stretch as the run's preview PNG.

    Re-renders from the FITS at the chosen stretch/black point and overwrites
    the run's ``preview_path`` so the new look shows everywhere the preview is
    used (history thumbnails and the Sky Map).
    """
    lib, proj = deps.open_target_project(request, safe)
    try:
        run = next((r for r in proj.iter_stack_runs() if r.id == run_id), None)
    finally:
        proj.close()
        lib.close()
    if run is None:
        raise HTTPException(status_code=404, detail="No such run")
    if not run.fits_path or not Path(run.fits_path).exists():
        raise HTTPException(status_code=404, detail="No FITS for this run to render")
    if not run.preview_path:
        raise HTTPException(status_code=400, detail="Run has no preview path to overwrite")

    stretch = _clamp(float(body.get("stretch", _STRETCH_DEFAULT)), _STRETCH_MIN, _STRETCH_MAX)
    black = _clamp(float(body.get("black", _BLACK_DEFAULT)), _BLACK_MIN, _BLACK_MAX)

    from seestack.render.thumbnail import render_stack_png
    png = await run_in_threadpool(
        render_stack_png, run.fits_path,
        stretch=stretch, black=black, max_width=1024,
    )
    Path(run.preview_path).write_bytes(png)
    return {"ok": True, "stretch": stretch, "black": black}


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
    download = kind in ("fits", "tiff", "preview")
    return FileResponse(
        path, media_type=media,
        filename=filename if download else None,
    )


@router.delete("/api/targets/{safe}/stack-runs/{run_id}")
def delete_stack_run(safe: str, run_id: int, request: Request) -> dict:
    from webapp.routers.storage import delete_run_artifacts

    from seestack.edit.proxy import clear_proxy

    lib, proj = deps.open_target_project(request, safe)
    try:
        run = next((r for r in proj.iter_stack_runs() if r.id == run_id), None)
        if run is not None:
            delete_run_artifacts(run)
        proj.delete_stack_run(run_id)
        # Drop the editor's cached proxy + saved recipe for this run.
        clear_proxy(Path(proj.project_dir), run_id)
        with contextlib.suppress(Exception):
            proj.set_meta(f"editor_recipe:{run_id}", "")
    finally:
        proj.close()
        lib.close()
    return {"deleted": run_id}
