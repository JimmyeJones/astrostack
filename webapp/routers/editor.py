"""Non-destructive editor endpoints: op schema, recipes, live proxy preview,
histogram, auto-process, presets, full-res export, and batch apply.

Live preview/histogram run on the cached downsampled proxy via ``run_in_threadpool``
(like ``render_stack_run``); full-res export and batch go through the job worker.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from pydantic import BaseModel

from seestack.edit.histogram import compute_histogram
from seestack.edit.pipeline import apply_recipe
from seestack.edit.proxy import get_proxy
from seestack.edit.recipe import Recipe, recipe_from_dict
from seestack.edit.registry import EditContext
from seestack.edit import presets as presets_mod
from webapp import deps
from webapp.schemas import EditOpOut, editor_ops_schema

router = APIRouter(tags=["editor"])

RECIPE_META_PREFIX = "editor_recipe:"
USER_PRESETS_META_KEY = "editor_user_presets"


# ---- helpers ---------------------------------------------------------------

def _run_info(request: Request, safe: str, run_id: int) -> tuple[Path, Any]:
    """(project_dir, run) for a stack run, or 404. Closes the DB handles."""
    lib, proj = deps.open_target_project(request, safe)
    try:
        run = next((r for r in proj.iter_stack_runs() if r.id == run_id), None)
        pdir = Path(proj.project_dir)
    finally:
        proj.close()
        lib.close()
    if run is None:
        raise HTTPException(status_code=404, detail="No such stack run")
    if not run.fits_path or not Path(run.fits_path).exists():
        raise HTTPException(status_code=404, detail="Run has no FITS to edit")
    return pdir, run


def _decode_recipe_query(request: Request, safe: str, run_id: int, recipe_q: str | None) -> Recipe:
    """Decode a base64url JSON recipe from the query, or fall back to the saved one."""
    if recipe_q:
        try:
            data = json.loads(base64.urlsafe_b64decode(recipe_q.encode()).decode())
            return recipe_from_dict(data)
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="Bad recipe encoding")
    return _load_saved_recipe(request, safe, run_id)


def _load_saved_recipe(request: Request, safe: str, run_id: int) -> Recipe:
    lib, proj = deps.open_target_project(request, safe)
    try:
        raw = proj.get_meta(f"{RECIPE_META_PREFIX}{run_id}")
    finally:
        proj.close()
        lib.close()
    from seestack.edit.recipe import recipe_from_json
    return recipe_from_json(raw)


def _render_png(project_dir: Path, run, recipe: Recipe) -> bytes:
    import io

    from PIL import Image

    rgb, scale = get_proxy(project_dir, run.id, run.fits_path)
    ctx = EditContext(proxy_scale=scale, is_proxy=True, wcs=None)
    out = apply_recipe(rgb, recipe, ctx, for_preview=True)
    u8 = (np.clip(np.nan_to_num(out), 0.0, 1.0) * 255).astype(np.uint8)
    buf = io.BytesIO()
    Image.fromarray(u8, mode="RGB").save(buf, format="PNG")
    return buf.getvalue()


# ---- op schema + presets ---------------------------------------------------

@router.get("/api/editor/ops/schema", response_model=list[EditOpOut])
def ops_schema() -> list[EditOpOut]:
    return editor_ops_schema()


@router.get("/api/editor/presets")
def list_presets(request: Request) -> dict:
    builtin = [
        {"id": pid, "label": p["label"], "group": p["group"],
         "ops": [o.to_dict() for o in p["ops"]]}
        for pid, p in presets_mod.BUILTIN_PRESETS.items()
    ]
    lib = deps.open_library(request)
    try:
        raw = lib.get_meta(USER_PRESETS_META_KEY)
    finally:
        lib.close()
    try:
        user = json.loads(raw) if raw else []
    except (ValueError, TypeError):
        user = []
    return {"builtin": builtin, "user": user}


class PresetCreate(BaseModel):
    label: str
    ops: list[dict]


@router.post("/api/editor/presets")
def create_preset(body: PresetCreate, request: Request) -> dict:
    import uuid

    # Normalize ops through the validator so only known ops/params persist.
    recipe = recipe_from_dict({"ops": body.ops})
    preset = {"id": "user_" + uuid.uuid4().hex[:8], "label": body.label.strip() or "Preset",
              "group": "My presets", "ops": [o.to_dict() for o in recipe.ops]}
    lib = deps.open_library(request)
    try:
        raw = lib.get_meta(USER_PRESETS_META_KEY)
        existing = json.loads(raw) if raw else []
        if not isinstance(existing, list):
            existing = []
        existing.append(preset)
        lib.set_meta(USER_PRESETS_META_KEY, json.dumps(existing))
    finally:
        lib.close()
    return preset


@router.delete("/api/editor/presets/{preset_id}")
def delete_preset(preset_id: str, request: Request) -> dict:
    lib = deps.open_library(request)
    try:
        raw = lib.get_meta(USER_PRESETS_META_KEY)
        existing = json.loads(raw) if raw else []
        existing = [p for p in existing if p.get("id") != preset_id]
        lib.set_meta(USER_PRESETS_META_KEY, json.dumps(existing))
    finally:
        lib.close()
    return {"deleted": preset_id}


# ---- recipe load/save ------------------------------------------------------

@router.get("/api/targets/{safe}/stack-runs/{run_id}/editor/recipe")
def get_recipe(safe: str, run_id: int, request: Request) -> dict:
    return _load_saved_recipe(request, safe, run_id).to_dict()


@router.put("/api/targets/{safe}/stack-runs/{run_id}/editor/recipe")
def put_recipe(safe: str, run_id: int, body: dict, request: Request) -> dict:
    import time

    recipe = recipe_from_dict(body)
    recipe.base_run_id = run_id
    recipe.updated_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    lib, proj = deps.open_target_project(request, safe)
    try:
        proj.set_meta(f"{RECIPE_META_PREFIX}{run_id}", recipe.to_json())
    finally:
        proj.close()
        lib.close()
    return recipe.to_dict()


# ---- live preview + histogram ---------------------------------------------

@router.get("/api/targets/{safe}/stack-runs/{run_id}/editor/preview")
async def edit_preview(safe: str, run_id: int, request: Request,
                       recipe: str | None = None) -> Response:
    project_dir, run = _run_info(request, safe, run_id)
    rec = _decode_recipe_query(request, safe, run_id, recipe)
    png = await run_in_threadpool(_render_png, project_dir, run, rec)
    return Response(content=png, media_type="image/png",
                    headers={"Cache-Control": "no-store"})


@router.get("/api/targets/{safe}/stack-runs/{run_id}/editor/histogram")
async def edit_histogram(safe: str, run_id: int, request: Request,
                         recipe: str | None = None) -> dict:
    project_dir, run = _run_info(request, safe, run_id)
    rec = _decode_recipe_query(request, safe, run_id, recipe)

    def work() -> dict:
        rgb, scale = get_proxy(project_dir, run.id, run.fits_path)
        # Flag a stack whose proxy has no finite pixels (failed solve/stack), so
        # the UI can say "no image data" instead of showing a mystery black frame.
        empty = not bool(np.isfinite(rgb).any())
        ctx = EditContext(proxy_scale=scale, is_proxy=True, wcs=None)
        out = apply_recipe(rgb, rec, ctx, for_preview=True)
        hist = compute_histogram(out)
        hist["empty"] = empty
        return hist

    return await run_in_threadpool(work)


@router.post("/api/targets/{safe}/stack-runs/{run_id}/editor/auto")
async def auto_process(safe: str, run_id: int, request: Request) -> dict:
    project_dir, run = _run_info(request, safe, run_id)

    def work() -> dict:
        rgb, _scale = get_proxy(project_dir, run.id, run.fits_path)
        return presets_mod.auto_recipe(rgb).to_dict()

    return await run_in_threadpool(work)


# ---- export + batch (jobs) -------------------------------------------------

class ExportRequest(BaseModel):
    recipe: dict
    output_name: str | None = None
    tiff_mode: str = "linear"


@router.post("/api/targets/{safe}/stack-runs/{run_id}/editor/export")
def export_run(safe: str, run_id: int, body: ExportRequest, request: Request) -> dict:
    from webapp import pipeline

    settings = deps.get_settings(request)
    jm = deps.get_job_manager(request)
    job = pipeline.submit_editor_export(
        settings, jm, safe, run_id, body.recipe,
        output_name=body.output_name, tiff_mode=body.tiff_mode,
    )
    return {"job_id": job.id}


class PngRequest(BaseModel):
    recipe: dict | None = None


@router.post("/api/targets/{safe}/stack-runs/{run_id}/editor/export-png")
def export_png(safe: str, run_id: int, body: PngRequest, request: Request) -> dict:
    """Kick off a full-resolution PNG render of the recipe. Poll the job, then
    GET .../editor/png/{job_id} to download the result."""
    from webapp import pipeline

    settings = deps.get_settings(request)
    jm = deps.get_job_manager(request)
    job = pipeline.submit_editor_png(settings, jm, safe, run_id, body.recipe or {})
    return {"job_id": job.id}


@router.get("/api/targets/{safe}/stack-runs/{run_id}/editor/png/{job_id}")
def download_png(safe: str, run_id: int, job_id: str, request: Request) -> FileResponse:
    jm = deps.get_job_manager(request)
    job = jm.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="No such job")
    if job.state != "done" or not job.result:
        raise HTTPException(status_code=409, detail=f"PNG not ready (job {job.state})")
    png_path = job.result.get("png_path")
    if not png_path or not Path(png_path).exists():
        raise HTTPException(status_code=404, detail="PNG not found")
    filename = job.result.get("filename") or Path(png_path).name
    return FileResponse(png_path, media_type="image/png", filename=filename)


class BatchRequest(BaseModel):
    items: list[dict]                 # [{"safe": ..., "run_id": ...}, ...]
    recipe: dict | None = None
    preset_id: str | None = None
    output_name: str | None = None
    tiff_mode: str = "linear"


@router.post("/api/editor/batch")
def batch_apply(body: BatchRequest, request: Request) -> dict:
    from webapp import pipeline

    if not body.items:
        raise HTTPException(status_code=400, detail="No items to process")
    recipe = body.recipe
    if recipe is None and body.preset_id:
        pr = presets_mod.preset_recipe(body.preset_id)
        if pr is None:
            raise HTTPException(status_code=404, detail="Unknown preset")
        recipe = pr.to_dict()
    if recipe is None:
        raise HTTPException(status_code=400, detail="Provide a recipe or preset_id")

    settings = deps.get_settings(request)
    jm = deps.get_job_manager(request)
    job = pipeline.submit_editor_batch(
        settings, jm, body.items, recipe,
        output_name=body.output_name, tiff_mode=body.tiff_mode,
    )
    return {"job_id": job.id}
