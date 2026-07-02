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
    from webapp import calibration

    settings = deps.get_settings(request)
    jm = deps.get_job_manager(request)
    # Validate the target exists.
    lib, proj = deps.open_target_project(request, safe)
    proj.close()
    lib.close()

    body = dict(body or {})
    # Calibration: accept only master *ids* and resolve them to server-side
    # paths here. Raw dark_path/flat_path from the client are never honoured.
    body.pop("dark_path", None)
    body.pop("flat_path", None)
    body.pop("flat_dark_path", None)
    dark_id = body.pop("dark_master_id", None)
    flat_id = body.pop("flat_master_id", None)
    flat_dark_id = body.pop("flat_dark_master_id", None)
    try:
        dark_path, flat_path, flat_dark_path = calibration.resolve_master_paths(
            settings.resolved_library_root, dark_id, flat_id, flat_dark_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if dark_path:
        body["dark_path"] = dark_path
    if flat_path:
        body["flat_path"] = flat_path
    if flat_dark_path:
        body["flat_dark_path"] = flat_dark_path

    job = pipeline.submit_stack(settings, jm, safe, body)
    return {"job_id": job.id}


@router.post("/api/targets/{safe}/channel-combine")
def channel_combine(safe: str, body: dict[str, Any], request: Request) -> dict[str, str]:
    """Combine several mono stacks (assigned to L/R/G/B) into one colour run
    recorded under ``safe``."""
    settings = deps.get_settings(request)
    jm = deps.get_job_manager(request)
    lib, proj = deps.open_target_project(request, safe)
    proj.close()
    lib.close()

    items = body.get("items") or []
    if not isinstance(items, list) or not items:
        raise HTTPException(status_code=400, detail="items (list of channel assignments) required")
    weights = body.get("weights") if isinstance(body.get("weights"), dict) else None
    job = pipeline.submit_channel_combine(
        settings, jm, safe, items,
        output_name=str(body.get("output_name") or "").strip() or None,
        weights=weights,
    )
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
            total_exposure_s=r.total_exposure_s,
            reusable=_run_is_reusable(r.options_json),
        ))
    return out


def _run_is_reusable(options_json: str | None) -> bool:
    """A run's settings can pre-fill the Stack form unless it's an editor-recipe
    or channel-combine run (those carry no stack knobs)."""
    if not options_json:
        return False
    try:
        parsed = json.loads(options_json)
    except json.JSONDecodeError:
        return False
    return (isinstance(parsed, dict)
            and "editor_recipe" not in parsed
            and "channel_combine" not in parsed)


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


# Human-relevant provenance cards, in display order. Keys not present in a
# given FITS are simply skipped, so this works for old stacks (no provenance),
# newer stacks, channel-combines (NCOMBINE/STACKMTD) and editor exports
# (STACKMTD/EDITFROM) alike.
_INFO_CARDS = (
    "OBJECT", "NFRAMES", "NCOMBINE", "EXPOSURE", "EXPTOTAL",
    "DATE-OBS", "DATE-END", "STACKER", "STACKMTD", "COLORTYP",
    "EDITFROM", "CREATOR", "DATE",
)


# NOTE: declared before the "/{kind}" download route so "info" isn't swallowed
# by that catch-all path parameter.
@router.get("/api/targets/{safe}/stack-runs/{run_id}/info")
def stack_run_info(safe: str, run_id: int, request: Request) -> dict[str, Any]:
    """Read the provenance header cards from a run's master FITS.

    Lets the History view show "how this stack was made" (integration time,
    frame count, method, dates) straight from the self-documenting FITS header —
    no extra storage, just a cheap header read.
    """
    _, fits_path = _run_fits_path(request, safe, run_id)
    if not fits_path or not Path(fits_path).exists():
        raise HTTPException(status_code=404, detail="No FITS for this run")

    from astropy.io import fits as _fits

    cards: list[dict[str, Any]] = []
    integration_s: float | None = None
    n_frames: int | None = None
    try:
        header = _fits.getheader(fits_path)
    except Exception as exc:  # noqa: BLE001 — a corrupt header shouldn't 500
        raise HTTPException(status_code=422,
                            detail=f"Could not read FITS header: {exc}") from exc
    for key in _INFO_CARDS:
        if key not in header:
            continue
        value = header[key]
        # astropy returns Undefined/complex types for a few cards; coerce to a
        # JSON-safe scalar so the response never fails to serialise.
        if not isinstance(value, (str, int, float, bool)):
            value = str(value)
        cards.append({
            "key": key,
            "value": value,
            "comment": str(header.comments[key]) or None,
        })
        if key == "EXPTOTAL":
            with contextlib.suppress(TypeError, ValueError):
                integration_s = float(value)
        if key in ("NFRAMES", "NCOMBINE") and n_frames is None:
            with contextlib.suppress(TypeError, ValueError):
                n_frames = int(value)
    return {"run_id": run_id, "integration_s": integration_s,
            "n_frames": n_frames, "cards": cards}


@router.get("/api/targets/{safe}/stack-runs/{run_id}/options")
def stack_run_options(safe: str, run_id: int, request: Request) -> dict[str, Any]:
    """Return a run's stack settings as a form-ready payload, so the Stack form
    can pre-fill from a previous run ("reuse these settings").

    The recorded ``options_json`` stores server-resolved calibration *paths*
    (never client-writable); those are reverse-mapped back to the master ids the
    form uses, and the run's ``output_name`` is dropped so reusing settings can't
    silently overwrite the earlier run's output. Editor-recipe and
    channel-combine runs carry no reusable stack settings → 400.
    """
    settings = deps.get_settings(request)
    lib, proj = deps.open_target_project(request, safe)
    try:
        run = next((r for r in proj.iter_stack_runs() if r.id == run_id), None)
    finally:
        proj.close()
        lib.close()
    if run is None:
        raise HTTPException(status_code=404, detail="No such run")
    try:
        parsed = json.loads(run.options_json) if run.options_json else {}
    except json.JSONDecodeError:
        parsed = {}
    if not isinstance(parsed, dict) or "editor_recipe" in parsed or "channel_combine" in parsed:
        raise HTTPException(status_code=400,
                            detail="This run has no reusable stack settings")

    from webapp import calibration

    valid = {fld.key for fld in stack_option_fields()}
    options = {k: v for k, v in parsed.items() if k in valid}
    options.pop("output_name", None)  # a fresh run gets a fresh name
    # Reverse-map server-resolved calibration paths → master ids for the form.
    lib_root = settings.resolved_library_root
    for path_key, id_key in (
        ("dark_path", "dark_master_id"),
        ("flat_path", "flat_master_id"),
        ("flat_dark_path", "flat_dark_master_id"),
    ):
        mid = calibration.master_id_for_path(lib_root, parsed.get(path_key))
        if mid is not None:
            options[id_key] = mid
        options.pop(path_key, None)  # never hand raw paths to the client/form
    return {"run_id": run_id, "options": options}


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
