"""Stacking: options schema, per-target defaults, trigger, history, downloads."""

from __future__ import annotations

import contextlib
import json
import os
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
    validate_stack_options,
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


def _run_auto_edit_note(request: Request, safe: str, run_id: int) -> str | None:
    """The plain-language "what the unattended auto-edit did" note for a run, or
    ``None`` when the run wasn't auto-edited by a background job (a manual/un-edited
    run). Read from project meta so the History Info panel can explain a result the
    user didn't drive."""
    from webapp.routers.editor import AUTO_EDIT_NOTE_PREFIX

    lib, proj = deps.open_target_project(request, safe)
    try:
        return proj.get_meta(f"{AUTO_EDIT_NOTE_PREFIX}{run_id}")
    finally:
        proj.close()
        lib.close()


def _run_auto_edit_sky_cast(request: Request, safe: str, run_id: int) -> dict | None:
    """The finished picture's residual sky-background cast (r/g/b sky medians +
    a neutral/colour verdict) measured by the unattended auto-edit, or ``None``
    when the run wasn't auto-edited by a background job (older runs / manual
    edits). Read from project meta so the History Info panel can show whether the
    hands-off Auto path landed the background neutral."""
    from webapp.routers.editor import AUTO_EDIT_SKYCAST_PREFIX

    lib, proj = deps.open_target_project(request, safe)
    try:
        raw = proj.get_meta(f"{AUTO_EDIT_SKYCAST_PREFIX}{run_id}")
    finally:
        proj.close()
        lib.close()
    if not raw:
        return None
    with contextlib.suppress(ValueError, TypeError):
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    return None


def _run_auto_edit_color_cal(request: Request, safe: str, run_id: int) -> dict | None:
    """Which colour-calibration (white-balance) path the unattended auto-edit
    actually ran and on how many stars (``mode_used`` gray_star/gaia/
    background_neutral/none, ``n_stars_used``, ``notes``), or ``None`` when the run
    wasn't auto-edited by a background job. Read from project meta so the History
    Info panel can tell the user whether the hands-off Auto path really
    white-balanced their image (and by which route)."""
    from webapp.routers.editor import AUTO_EDIT_COLORCAL_PREFIX

    lib, proj = deps.open_target_project(request, safe)
    try:
        raw = proj.get_meta(f"{AUTO_EDIT_COLORCAL_PREFIX}{run_id}")
    finally:
        proj.close()
        lib.close()
    if not raw:
        return None
    with contextlib.suppress(ValueError, TypeError):
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    return None


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
    # For a *never-configured* target (no per-target saved defaults and no
    # global default_stack_options), turn smart auto outlier removal on in the
    # form the beginner sees. auto_reject (v0.143.0) picks min/max vs kappa-sigma
    # from the sub count, so a short first-light stack actually drops a lone
    # satellite/plane trail plain kappa-sigma is blind to below ~11 frames. This
    # only seeds the returned form values — the persisted engine default and any
    # explicitly-saved config are untouched, so a user who ever saved defaults
    # keeps exactly what they saved and the unattended path is byte-for-byte
    # unchanged (§9 upgrade-safe: no stored default flips).
    if not raw and not settings.default_stack_options:
        merged.setdefault("auto_reject", True)
    # Fill any missing keys from the dataclass defaults via the schema.
    for fld in stack_option_fields():
        merged.setdefault(fld.key, fld.default)
    return merged


@router.put("/api/targets/{safe}/stack-defaults")
def put_stack_defaults(safe: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
    valid = {fld.key for fld in stack_option_fields()}
    clean = {k: v for k, v in body.items() if k in valid}
    # Don't persist a default that would later fail every stack cryptically.
    try:
        validate_stack_options(clean)
    except ValueError as exc:
        raise HTTPException(status_code=400,
                            detail=f"invalid stack option: {exc}") from exc
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
    # Reject a bad enum/range up front with a plain-language 400 rather than
    # accepting the run and failing cryptically deep in the engine later.
    try:
        validate_stack_options(body)
    except ValueError as exc:
        raise HTTPException(status_code=400,
                            detail=f"invalid stack option: {exc}") from exc
    # Calibration: accept only master *ids* and resolve them to server-side
    # paths here. Raw dark_path/flat_path from the client are never honoured.
    body.pop("dark_path", None)
    body.pop("flat_path", None)
    body.pop("flat_dark_path", None)
    body.pop("bias_path", None)
    dark_id = body.pop("dark_master_id", None)
    flat_id = body.pop("flat_master_id", None)
    flat_dark_id = body.pop("flat_dark_master_id", None)
    bias_id = body.pop("bias_master_id", None)
    try:
        dark_path, flat_path, flat_dark_path, bias_path = calibration.resolve_master_paths(
            settings.resolved_library_root, dark_id, flat_id, flat_dark_id, bias_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400,
                            detail=f"invalid calibration master id: {exc}") from exc
    if dark_path:
        body["dark_path"] = dark_path
    if flat_path:
        body["flat_path"] = flat_path
    if flat_dark_path:
        body["flat_dark_path"] = flat_dark_path
    if bias_path:
        body["bias_path"] = bias_path

    job = pipeline.submit_stack(settings, jm, safe, body)
    return {"job_id": job.id}


@router.get("/api/targets/{safe}/stack-estimate")
def stack_estimate(
    safe: str, request: Request,
    drizzle: bool = False, drizzle_scale: float = 1.5,
    drizzle_reject: bool = False, mosaic_canvas: str = "auto",
) -> dict[str, Any]:
    """Dry-run sizing for a stack: output canvas + estimated peak memory,
    computed without stacking, so the Stack form can warn *before* a run is
    submitted and refused for OOM (e.g. "Drizzle ×2 → 7680×4320, ≈2.1 GB peak,
    over the ~1.4 GB budget").

    Only the canvas-affecting knobs matter to sizing, so those are the only query
    params. Returns 422 (not 500) when there's nothing solved to size yet, with
    the same guidance ``run_stack`` gives."""
    from seestack.stack.stacker import StackOptions, estimate_stack

    settings = deps.get_settings(request)
    lib, proj = deps.open_target_project(request, safe)
    try:
        options = StackOptions(
            drizzle=bool(drizzle),
            drizzle_scale=float(drizzle_scale),
            drizzle_reject=bool(drizzle_reject),
            mosaic_canvas=str(mosaic_canvas),
        )
        try:
            est = estimate_stack(proj, options,
                                 memory_budget_gb=settings.max_stack_memory_gb)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        proj.close()
        lib.close()
    return {
        "n_frames": est.n_frames,
        "canvas_w": est.canvas_w,
        "canvas_h": est.canvas_h,
        "output_w": est.output_w,
        "output_h": est.output_h,
        "is_mosaic": est.is_mosaic,
        "peak_bytes": est.peak_bytes,
        "peak_gb": round(est.peak_bytes / 1e9, 2),
        "budget_bytes": est.budget_bytes,
        "budget_gb": round(est.budget_bytes / 1e9, 2),
        "would_exceed": est.would_exceed,
        "suggested_drizzle_scale": est.suggested_drizzle_scale,
        "suggested_reference_canvas": est.suggested_reference_canvas,
    }


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
        # The pinned "cover" run (library-level), so the History card can mark it.
        entry = lib.find_target(safe)
        cover_id = entry.cover_stack_run_id if entry is not None else None
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
            is_cover=(cover_id is not None and r.id == cover_id),
            notes=r.notes,
            total_exposure_s=r.total_exposure_s,
            reusable=_run_is_reusable(r.options_json),
            transparency_ratio=r.transparency_ratio,
            noise_sigma=r.noise_sigma,
            calstat=r.calstat,
            options=_parse_options(r.options_json),
            engine_version=r.engine_version,
        ))
    return out


def _parse_options(options_json: str | None) -> dict:
    """Parse a run's stored options_json into a dict for the UI (combine-method
    badge). Returns an empty dict when unset or malformed."""
    if not options_json:
        return {}
    try:
        parsed = json.loads(options_json)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


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
    north_up: bool = False,
) -> Response:
    """Live, adjustable re-render of a run's stacked FITS (full dynamic range).

    ``stretch`` (0..1) → how hard the asinh curve lifts faint detail; ``black``
    (0..1) → the black point (higher = darker background). ``north_up`` rotates
    the rendered image so celestial North points up (like reference photos of the
    object), using the run's own WCS — a no-op when the run has no WCS or the
    correction is trivial. Runs in a threadpool so it never blocks the job worker.
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
        north_up=bool(north_up),
    )
    return Response(content=png, media_type="image/png",
                    headers={"Cache-Control": "no-store"})


@router.get("/api/targets/{safe}/stack-runs/{run_id}/sky-overlay")
async def sky_overlay(safe: str, run_id: int, request: Request) -> Response:
    """The run's preview as an RGBA PNG with uncovered (NaN / no-coverage) pixels
    transparent, for the Sky map.

    The stored preview PNG is opaque RGB with NaN→black, so an irregular
    union-mosaic footprint shows as an ugly black rectangle on the sky. This serves
    the same preview pixels with an alpha channel keyed off the stack's coverage
    mask, so the mosaic shows its true shape. Same pixel grid/dimensions as the
    preview, so the WCS built for the preview grid still places it (unchanged
    placement). Falls back to the opaque preview when there's no FITS to derive
    coverage from (older/edited runs), so it never regresses to a 404."""
    lib, proj = deps.open_target_project(request, safe)
    try:
        run = next((r for r in proj.iter_stack_runs() if r.id == run_id), None)
    finally:
        proj.close()
        lib.close()
    if run is None:
        raise HTTPException(status_code=404, detail="No such run")
    preview_path = run.preview_path
    if not preview_path or not Path(preview_path).exists():
        raise HTTPException(status_code=404, detail="No preview for this run")
    fits_path = run.fits_path

    from seestack.render.thumbnail import overlay_rgba_png, stack_coverage_mask

    def work() -> bytes:
        preview = Path(preview_path).read_bytes()
        if fits_path and Path(fits_path).exists():
            try:
                return overlay_rgba_png(preview, stack_coverage_mask(fits_path))
            except Exception:  # noqa: BLE001 — a broken FITS just serves the opaque preview
                return preview
        return preview

    png = await run_in_threadpool(work)
    return Response(content=png, media_type="image/png",
                    headers={"Cache-Control": "no-store"})


@router.get("/api/targets/{safe}/stack-runs/{run_id}/annotations")
async def stack_run_annotations(safe: str, run_id: int, request: Request) -> dict[str, Any]:
    """The catalog deep-sky objects that fall inside this run's field.

    Turns "what are these other fuzzy blobs?" into named objects: projects the
    bundled offline deep-sky catalog (Messier + popular NGC/IC) through the run's
    solved output WCS — read from its master FITS header, which the stacker merges
    the canvas WCS into — and returns those whose centre lands inside the frame.
    Pure and offline: no network, no new dependency. Pixel coordinates are on the
    run's own FITS grid (``width`` × ``height``); the frontend positions a label
    over any scaled preview via ``x_px / width``. Returns an empty ``objects`` list
    (never 404s where a run exists) when the run has no FITS or an unsolved /
    degenerate WCS, so the caller never has to special-case an unsolved run.

    Runs the header read + projection in a threadpool so it never blocks the job
    worker."""
    _, fits_path = _run_fits_path(request, safe, run_id)  # raises 404 for an unknown run

    def work() -> dict[str, Any]:
        from seestack.annotate import objects_in_field
        from seestack.io.wcs_io import celestial_wcs_from_fits

        wcs, width, height = celestial_wcs_from_fits(fits_path) if fits_path else (None, 0, 0)
        objs = objects_in_field(wcs, width, height)
        return {
            "width": width,
            "height": height,
            "objects": [
                {
                    "catalog_id": o.catalog_id,
                    "name": o.name,
                    "type": o.type,
                    "ra_deg": o.ra_deg,
                    "dec_deg": o.dec_deg,
                    "x_px": o.x_px,
                    "y_px": o.y_px,
                }
                for o in objs
            ],
        }

    return await run_in_threadpool(work)


# The "watch your picture come together" progress reel is written as a sibling
# of each run's FITS (``{stem}_progress.webp`` — or ``.png`` APNG when the Pillow
# build lacks WEBP), resolved from the basename exactly like the coverage map, so
# a re-stack's archived runs keep serving their own reel.
_PROGRESS_MEDIA = {".webp": "image/webp", ".png": "image/png"}


def _run_progress_reel(fits_path: str | None) -> Path | None:
    """Resolve the progress-reel sibling for a run's FITS path, if it exists."""
    if not fits_path:
        return None
    fp = Path(fits_path)
    stem = fp.name[:-len(fp.suffix)] if fp.suffix else fp.name
    for suffix in ("_progress.webp", "_progress.png"):
        cand = fp.with_name(f"{stem}{suffix}")
        if cand.exists():
            return cand
    return None


@router.get("/api/targets/{safe}/stack-runs/{run_id}/progress-info")
async def stack_progress_info(
    safe: str, run_id: int, request: Request,
) -> dict[str, Any]:
    """Whether this run has a "watch it appear" reel, and how many frames.

    Lightweight probe so the UI can decide whether to show the player without
    downloading the animation. ``available`` is false (not a 404) when the run
    simply wasn't stacked with ``save_progress`` on — the common case."""
    _, fits_path = _run_fits_path(request, safe, run_id)
    reel = _run_progress_reel(fits_path)
    if reel is None:
        return {"available": False, "frames": 0, "format": ""}

    def probe() -> int:
        from PIL import Image
        try:
            with Image.open(reel) as im:
                return int(getattr(im, "n_frames", 1))
        except Exception:  # noqa: BLE001 — a broken reel just reads as unavailable
            return 0

    frames = await run_in_threadpool(probe)
    # ``format`` (``webp``/``png``) lets the UI name a shared/downloaded clip with
    # the right extension; the reel itself carries the correct media type.
    return {"available": frames > 1, "frames": frames,
            "format": reel.suffix.lstrip(".")}


@router.get("/api/targets/{safe}/stack-runs/{run_id}/progress")
def stack_progress_reel(
    safe: str, run_id: int, request: Request,
) -> FileResponse:
    """Serve the run's progress-reel animation (WEBP or APNG), or 404."""
    _, fits_path = _run_fits_path(request, safe, run_id)
    reel = _run_progress_reel(fits_path)
    if reel is None:
        raise HTTPException(status_code=404, detail="No progress reel for this run")
    media = _PROGRESS_MEDIA.get(reel.suffix, "application/octet-stream")
    return FileResponse(reel, media_type=media,
                        filename=f"{Path(fits_path).stem}_progress{reel.suffix}")


# --- "Night after night" cross-run deepening reel ---------------------------
# Unlike the per-run progress reel (frames piling on *within one stack*), this is
# a per-*target* animation across successive re-stacks: the same object getting
# cleaner and deeper as more subs / more nights pile on. It's rendered on demand
# from the master FITS the app already archives (each re-stack keeps the previous
# master as a timestamped sibling and repoints its history row), and cached beside
# the outputs with a content signature so it's rebuilt only when a stack is
# added/re-run/deleted. Purely additive + read-only (see seestack.render.deepening).


def _deepening_runs(proj) -> list:
    """A target's stack runs that still have a master FITS on disk, ordered
    oldest → newest — the chronological deepening series."""
    runs = [r for r in proj.iter_stack_runs()
            if r.fits_path and Path(r.fits_path).exists()]
    runs.sort(key=lambda r: (r.timestamp_utc or "", r.id or 0))
    return runs


def _deepening_signature(runs: list) -> str:
    """Content signature of the ordered FITS series — a cached reel is reused
    until the series changes (a new/re-run/deleted stack), then rebuilt."""
    import hashlib

    parts = []
    for r in runs:
        try:
            st = os.stat(r.fits_path)
            parts.append(f"{r.id}:{st.st_mtime_ns}:{st.st_size}")
        except OSError:
            parts.append(f"{r.id}:0:0")
    return hashlib.sha1("|".join(parts).encode()).hexdigest()


def _build_or_get_deepening_reel(runs: list) -> Path | None:
    """Return the cached deepening reel for ``runs`` (oldest → newest), rebuilding
    it when the series signature has changed. Blocking (loads + encodes FITS), so
    callers dispatch it to a threadpool."""
    if len(runs) < 2:
        return None
    newest = runs[-1]
    out_dir = Path(newest.fits_path).parent
    basename = newest.output_basename or "master"
    sig = _deepening_signature(runs)
    sig_file = out_dir / f"{basename}_deepening.sig"
    for suffix in ("_deepening.webp", "_deepening.png"):
        cand = out_dir / f"{basename}{suffix}"
        if cand.exists() and sig_file.exists():
            with contextlib.suppress(OSError):
                if sig_file.read_text().strip() == sig:
                    return cand
    # (Re)build: clear any stale reel of either format first so a format change
    # (WEBP↔APNG) can't leave two files that the resolver disagrees on.
    for suffix in ("_deepening.webp", "_deepening.png"):
        with contextlib.suppress(OSError):
            (out_dir / f"{basename}{suffix}").unlink()
    from seestack.render.deepening import build_deepening_reel

    path = build_deepening_reel([r.fits_path for r in runs], out_dir, basename)
    if path is None:
        return None
    with contextlib.suppress(OSError):
        sig_file.write_text(sig)
    return path


@router.get("/api/targets/{safe}/deepening-reel/info")
def deepening_reel_info(safe: str, request: Request) -> dict[str, Any]:
    """Whether this target has a multi-stack "night after night" reel, plus the
    caption figures (how many stacks, first/last sub counts + dates). Lightweight
    (no render): ``available`` is false — not a 404 — when the target has fewer
    than two stacks on disk, so the card simply self-hides."""
    lib, proj = deps.open_target_project(request, safe)
    try:
        runs = _deepening_runs(proj)
    finally:
        proj.close()
        lib.close()
    if len(runs) < 2:
        return {"available": False, "n_stacks": len(runs)}
    from PIL import features

    return {
        "available": True,
        "n_stacks": len(runs),
        "first_subs": runs[0].n_frames_used,
        "last_subs": runs[-1].n_frames_used,
        "first_utc": runs[0].timestamp_utc,
        "last_utc": runs[-1].timestamp_utc,
        "format": "webp" if features.check("webp") else "png",
    }


@router.get("/api/targets/{safe}/deepening-reel")
async def deepening_reel(safe: str, request: Request) -> FileResponse:
    """Serve the target's "night after night" deepening animation (WEBP or APNG),
    building/caching it on demand. 404 when the target has fewer than two stacks."""
    lib, proj = deps.open_target_project(request, safe)
    try:
        runs = _deepening_runs(proj)
    finally:
        proj.close()
        lib.close()
    if len(runs) < 2:
        raise HTTPException(status_code=404, detail="Not enough stacks for a deepening reel")
    reel = await run_in_threadpool(_build_or_get_deepening_reel, runs)
    if reel is None:
        raise HTTPException(status_code=404, detail="Could not build a deepening reel")
    media = _PROGRESS_MEDIA.get(reel.suffix, "application/octet-stream")
    return FileResponse(reel, media_type=media, filename=reel.name)


@router.get("/api/targets/{safe}/stack-runs/{run_id}/render-suggestion")
async def render_stretch_suggestion(
    safe: str, run_id: int, request: Request,
) -> dict[str, Any]:
    """Suggest asinh ``stretch``/``black`` for the History live-render sliders
    from the run's own linear data, so opening "Adjust" starts on a well-exposed
    look that matches the STF preview thumbnail instead of a fixed 0.5/0.35 that
    can jump brighter or darker. Mirrors the editor's stretch suggestion but for
    the History ``…/render`` surface (measures the identical pixels that endpoint
    stretches). Returns ``{stretch, black}`` null when there's no useful
    suggestion (too little dynamic range) or the run is a display-space export
    (its sliders are a no-op — nothing to anchor)."""
    _, fits_path = _run_fits_path(request, safe, run_id)
    if not fits_path or not Path(fits_path).exists():
        raise HTTPException(status_code=404, detail="No FITS for this run to render")

    from seestack.edit.stretch import STRETCH_TARGET_BG, suggest_asinh_stretch
    from seestack.render.orient import NORTH_UP_MIN_DEG
    from seestack.render.thumbnail import load_stack_rgb, stack_north_up_deg

    def work() -> dict[str, Any]:
        # "North up" is a pure orientation fix from the run's own WCS, so it's
        # offered on a linear stack *or* a display-space export that kept its WCS;
        # only surface it when there's a real, more-than-trivial correction.
        angle = stack_north_up_deg(fits_path)
        north_up_deg = angle if (angle is not None and abs(angle) >= NORTH_UP_MIN_DEG) else None
        rgb, display_space = load_stack_rgb(fits_path, max_width=1024)
        if display_space:
            return {"stretch": None, "black": None, "north_up_deg": north_up_deg}
        sug = suggest_asinh_stretch(rgb)
        if sug is None:
            return {"stretch": None, "black": None, "north_up_deg": north_up_deg}
        return {"stretch": sug[0], "black": sug[1], "target_bg": STRETCH_TARGET_BG,
                "north_up_deg": north_up_deg}

    return await run_in_threadpool(work)


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

    try:
        stretch = _clamp(float(body.get("stretch", _STRETCH_DEFAULT)), _STRETCH_MIN, _STRETCH_MAX)
        black = _clamp(float(body.get("black", _BLACK_DEFAULT)), _BLACK_MIN, _BLACK_MAX)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400,
                            detail=f"stretch/black must be numbers: {exc}") from exc

    from seestack.render.thumbnail import render_stack_png
    png = await run_in_threadpool(
        render_stack_png, run.fits_path,
        stretch=stretch, black=black, max_width=1024,
    )
    Path(run.preview_path).write_bytes(png)
    return {"ok": True, "stretch": stretch, "black": black}


_BAYER_PATTERNS = {"RGGB", "BGGR", "GRBG", "GBRG"}


def _pick_reference_sub(proj: Any) -> Any | None:
    """Choose a *good* single accepted sub to stand in for "one raw frame".

    Picks the sharpest accepted frame (lowest measured FWHM), tie-broken by id so
    the choice is deterministic, so the comparison is honest — a genuinely good
    frame, not a cloud-ruined one — rather than stacked in our favour. Falls back
    to the first accepted frame (then any frame) when no FWHM is measured, and
    returns ``None`` only when the target has no frames at all.
    """
    frames = list(proj.iter_frames(accepted_only=True))
    if not frames:
        frames = list(proj.iter_frames())
    if not frames:
        return None
    with_fwhm = [f for f in frames if f.fwhm_px is not None]
    if with_fwhm:
        return min(with_fwhm, key=lambda f: (f.fwhm_px, f.id or 0))
    return frames[0]


@router.get("/api/targets/{safe}/stack-runs/{run_id}/one-sub-vs-stack")
def one_sub_vs_stack_info(safe: str, run_id: int, request: Request) -> dict[str, Any]:
    """Whether a "one frame vs your stack" reveal is available for this run, plus
    the plain-language caption fields the card fills in from the run's own data.

    A beginner drops hundreds of subs in and gets one clean picture, but never sees
    the *before* — this powers a read-only card that puts a single noisy sub next to
    the finished stack so they can see (and share) exactly what stacking bought them.

    ``available`` is ``false`` (not a 404, where the run exists) when the run has no
    stored preview to compare against, or the target has no frame to render — so the
    card self-hides on an older/edited run instead of erroring. Every caption field
    is best-effort (``null`` when its datum is missing) so the card degrades to a
    shorter line rather than printing blanks.
    """
    lib, proj = deps.open_target_project(request, safe)
    try:
        run = next((r for r in proj.iter_stack_runs() if r.id == run_id), None)
        if run is None:
            raise HTTPException(status_code=404, detail="No such run")
        has_preview = bool(run.preview_path and Path(run.preview_path).exists())
        ref = _pick_reference_sub(proj) if has_preview else None
        sub_exposure_s = ref.exposure_s if ref is not None else None
    finally:
        proj.close()
        lib.close()
    return {
        "available": has_preview and ref is not None,
        "n_frames": run.n_frames_used,
        "sub_exposure_s": sub_exposure_s,
        "integration_s": run.total_exposure_s,
    }


@router.get("/api/targets/{safe}/stack-runs/{run_id}/reference-sub")
async def reference_sub_png(safe: str, run_id: int, request: Request) -> Response:
    """Render the run's representative single sub, stretched to match the stack
    preview, as PNG — the "before" half of the one-frame-vs-stack reveal.

    Debayers the sharpest accepted frame and applies the identical export
    autostretch that produced the run's stored preview, so the only visible
    difference between this and the stack is noise/detail (never brightness). Runs
    in a threadpool so it never blocks the job worker.
    """
    lib, proj = deps.open_target_project(request, safe)
    try:
        run = next((r for r in proj.iter_stack_runs() if r.id == run_id), None)
        if run is None:
            raise HTTPException(status_code=404, detail="No such run")
        ref = _pick_reference_sub(proj)
        if ref is None:
            raise HTTPException(status_code=404, detail="No frame to render for this run")
        src = ref.cached_path or ref.source_path
        if not src or not Path(src).exists():
            raise HTTPException(status_code=404, detail="Frame file not found on disk")
        pattern = (ref.bayer_pattern or "RGGB").upper()
        if pattern not in _BAYER_PATTERNS:
            pattern = "RGGB"
        src_path = str(src)
    finally:
        proj.close()
        lib.close()

    from seestack.render.thumbnail import render_sub_preview

    png = await run_in_threadpool(
        render_sub_preview, src_path, bayer_pattern=pattern, max_width=1024,
    )
    return Response(content=png, media_type="image/png",
                    headers={"Cache-Control": "no-store"})


def _measure_noise_ratio(fits_path: str, sub_path: str, pattern: str) -> float | None:
    """Background-noise reduction factor between one sub and the linear master.

    Loads both on the **linear**, **native-resolution** scale (never the display
    PNGs, never one box-averaged and the other strided — either would distort the
    ratio), bounds each to an equal central crop for memory, and returns their
    σ ratio. ``None`` when the master is a tone-mapped editor/display-space export
    (its linear σ is meaningless) or either side can't be measured. Threadpool-safe.
    """
    import numpy as np
    from astropy.io import fits as _fits

    from seestack.io.fits_loader import bilinear_debayer, load_seestar_raw
    from seestack.qc.noise_ratio import noise_ratio
    from seestack.stack.output import fits_is_display_space

    try:
        if fits_is_display_space(fits_path):
            return None
    except Exception:  # noqa: BLE001 — an unreadable master → no honest number
        return None

    def _central_crop(rgb: np.ndarray, size: int = 1024) -> np.ndarray:
        h, w = rgb.shape[:2]
        y0 = max(0, (h - size) // 2)
        x0 = max(0, (w - size) // 2)
        return rgb[y0:y0 + size, x0:x0 + size]

    try:
        # Linear master (native res; NaN preserved for uncovered pixels).
        arr = np.asarray(_fits.getdata(fits_path), dtype=np.float32)
        if arr.ndim == 3:                       # (channels, H, W) → (H, W, channels)
            stack_rgb = np.transpose(arr, (1, 2, 0))
            if stack_rgb.shape[2] == 1:
                stack_rgb = np.repeat(stack_rgb, 3, axis=2)
            elif stack_rgb.shape[2] > 3:
                stack_rgb = stack_rgb[..., :3]
        else:                                   # 2-D mono → grey RGB
            stack_rgb = np.stack([arr, arr, arr], axis=-1)
        stack_rgb = _central_crop(stack_rgb)

        # Linear sub: debayer at native res (no decimation), same central crop.
        sub_raw, info = load_seestar_raw(sub_path, debayer=False, out_dtype=np.float32)
        sub_rgb = bilinear_debayer(
            sub_raw, pattern=(pattern or info.bayer_pattern or "RGGB"))
        sub_rgb = _central_crop(sub_rgb)
    except Exception:  # noqa: BLE001 — best-effort; the badge just omits the number
        return None

    return noise_ratio(sub_rgb, stack_rgb)


@router.get("/api/targets/{safe}/stack-runs/{run_id}/one-sub-vs-stack/noise")
async def one_sub_vs_stack_noise(safe: str, run_id: int, request: Request) -> dict[str, Any]:
    """The concrete "stacking cut your noise ~N×" number for the reveal card.

    Measures the background-noise σ of a representative single sub against the
    finished linear master and returns their ratio (``{"ratio": float|null}``) —
    which lands near √(n_frames) on a healthy weighted-mean stack. Its own lazy,
    best-effort endpoint so the info card stays cheap: any missing datum, an
    edited/display-space export, or an unmeasurable image returns ``null`` and the
    badge simply omits the number.
    """
    lib, proj = deps.open_target_project(request, safe)
    try:
        run = next((r for r in proj.iter_stack_runs() if r.id == run_id), None)
        if run is None:
            raise HTTPException(status_code=404, detail="No such run")
        fits_path = run.fits_path
        ref = _pick_reference_sub(proj)
        src = (ref.cached_path or ref.source_path) if ref is not None else None
        pattern = (ref.bayer_pattern or "RGGB").upper() if ref is not None else "RGGB"
        if pattern not in _BAYER_PATTERNS:
            pattern = "RGGB"
    finally:
        proj.close()
        lib.close()

    if (not fits_path or not Path(fits_path).exists()
            or not src or not Path(src).exists()):
        return {"ratio": None}

    ratio = await run_in_threadpool(_measure_noise_ratio, str(fits_path), str(src), pattern)
    return {"ratio": ratio}


# Human-relevant provenance cards, in display order. Keys not present in a
# given FITS are simply skipped, so this works for old stacks (no provenance),
# newer stacks, channel-combines (NCOMBINE/STACKMTD) and editor exports
# (STACKMTD/EDITFROM) alike.
_INFO_CARDS = (
    "OBJECT", "NFRAMES", "NCOMBINE", "EXPOSURE", "EXPTOTAL",
    "DATE-OBS", "DATE-END", "STACKER", "STACKMTD", "COLORTYP", "CALSTAT",
    "EDITFROM", "DECONPSF", "BKGSIGMA", "CREATOR", "DATE",
)

# Editor exports stamp each enabled op as an ``AstroStack: op.id(args)`` FITS
# HISTORY card (see webapp/pipeline._recipe_history). This prefix picks ours out
# of any other HISTORY cards a downstream tool may have added.
_HISTORY_PREFIX = "AstroStack: "


def _parse_processing_chain(header: Any) -> list[dict[str, Any]]:
    """Parse the ``AstroStack: op.id(args)`` HISTORY cards an editor export
    writes into a friendly, ordered processing chain, so the Info panel can show
    "Processing: Stretch → Noise reduction → Sharpen" without the user opening
    the FITS in Siril. Non-AstroStack HISTORY cards are ignored; unknown op ids
    fall back to the raw id."""
    if "HISTORY" not in header:
        return []
    from seestack.edit.registry import get_op

    chain: list[dict[str, Any]] = []
    for card in header["HISTORY"]:
        text = str(card).strip()
        if not text.startswith(_HISTORY_PREFIX):
            continue
        op_id = text[len(_HISTORY_PREFIX):].split("(", 1)[0].strip()
        if not op_id:
            continue
        spec = get_op(op_id)
        chain.append({"op": op_id, "label": spec.label if spec is not None else op_id})
    return chain


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

    # Quality-weighting summary (present only on quality-weighted stacks). Parsed
    # into a friendly object rather than raw cards so the panel can show a single
    # "N frames down-weighted · weights lo–hi" line.
    weighting: dict[str, Any] | None = None
    if "WGTMODE" in header:
        weighting = {"mode": str(header["WGTMODE"])}
        for hk, k in (("WGTNDOWN", "n_downweighted"),):
            with contextlib.suppress(KeyError, TypeError, ValueError):
                weighting[k] = int(header[hk])
        for hk, k in (("WGTMIN", "min"), ("WGTMAX", "max"), ("WGTMED", "median")):
            with contextlib.suppress(KeyError, TypeError, ValueError):
                weighting[k] = float(header[hk])

    # Photometric-normalization summary (present only on normalized stacks), parsed
    # the same way so the panel can show a single "N frames gain-matched · scales
    # lo–hi" line and the user can trust the (off-by-default) normalization did
    # something.
    photometric: dict[str, Any] | None = None
    if "PHOTNORM" in header:
        photometric = {"mode": str(header["PHOTNORM"])}
        for hk, k in (("PHOTNADJ", "n_adjusted"),):
            with contextlib.suppress(KeyError, TypeError, ValueError):
                photometric[k] = int(header[hk])
        for hk, k in (("PHOTMIN", "min"), ("PHOTMAX", "max"), ("PHOTMED", "median")):
            with contextlib.suppress(KeyError, TypeError, ValueError):
                photometric[k] = float(header[hk])

    # Dark exposure-scaling summary (present only when a master dark was actually
    # scaled to the subs' exposure), parsed the same way so the panel can show a
    # single "Dark scaled to sub exposure · 30s → 10s" line — the user can trust
    # the off-by-default scale_dark_to_light option did something.
    dark_scaling: dict[str, Any] | None = None
    if "DARKSCAL" in header:
        dark_scaling = {"mode": str(header["DARKSCAL"])}
        for hk, k in (("DARKDEXP", "dark_exposure"), ("DARKLEXP", "light_exposure")):
            with contextlib.suppress(KeyError, TypeError, ValueError):
                dark_scaling[k] = float(header[hk])

    # Rejection summary (present only on κ-σ stacks), parsed the same way so the
    # panel can show a single "Rejection clipped ~0.4% of samples" trust line —
    # the user can see the rejection removed transient outliers without
    # over-clipping real signal.
    rejection: dict[str, Any] | None = None
    if "REJMODE" in header:
        rejection = {"mode": str(header["REJMODE"])}
        for hk, k in (("REJNREJ", "n_rejected"), ("REJNTOT", "n_contributed")):
            with contextlib.suppress(KeyError, TypeError, ValueError):
                rejection[k] = int(header[hk])
        for hk, k in (("REJFRAC", "fraction"),):
            with contextlib.suppress(KeyError, TypeError, ValueError):
                rejection[k] = float(header[hk])

    # Frame-accounting summary (present on stacks recorded once the stacker began
    # stamping it): how many subs it attempted to combine and how many couldn't be
    # aligned. Lets the panel honestly report "1,850 of 2,000 subs combined; 150
    # couldn't be aligned" and flag a large align-failure fraction (usually mixed
    # targets / bad plate-solves). Omitted on older masters that lack the cards.
    frame_accounting: dict[str, Any] | None = None
    if "NOFFERED" in header:
        frame_accounting = {}
        for hk, k in (("NOFFERED", "n_offered"), ("NALIGNFL", "n_align_failed")):
            with contextlib.suppress(KeyError, TypeError, ValueError):
                frame_accounting[k] = int(header[hk])
        if "n_offered" not in frame_accounting:
            frame_accounting = None

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
    processing = _parse_processing_chain(header)
    auto_edit = _run_auto_edit_note(request, safe, run_id)
    sky_cast = _run_auto_edit_sky_cast(request, safe, run_id)
    color_cal = _run_auto_edit_color_cal(request, safe, run_id)
    # For a stack that carries provenance but came out *uncalibrated* (no CALSTAT
    # card — the stacker stamps it only when masters were applied), see whether the
    # library holds a master that's usable but for one concrete, fixable thing, and
    # surface a specific fix instead of the generic "build or pick a master" copy.
    calibration_advice = None
    if cards and "CALSTAT" not in header:
        calibration_advice = _uncalibrated_advice(request, safe)
    return {"run_id": run_id, "integration_s": integration_s,
            "n_frames": n_frames, "weighting": weighting,
            "photometric": photometric, "dark_scaling": dark_scaling,
            "rejection": rejection, "frame_accounting": frame_accounting,
            "auto_edit": auto_edit, "sky_cast": sky_cast,
            "color_cal": color_cal,
            "calibration_advice": calibration_advice,
            "processing": processing, "cards": cards}


def _uncalibrated_advice(request: Request, safe: str) -> str | None:
    """Best-effort actionable hint for why this target's stack was uncalibrated.

    Reads the target's median exposure/gain/temperature and the library masters
    (the same signals the Stack form's calibration suggestions use) and asks
    :func:`calibration.diagnose_uncalibrated` for a specific fix. Never raises — a
    diagnosis is a nicety, so any failure just yields the generic copy.
    """
    from webapp import calibration

    try:
        settings = deps.get_settings(request)
        lib, proj = deps.open_target_project(request, safe)
        try:
            frames = list(proj.iter_frames(accepted_only=True))
        finally:
            proj.close()
            lib.close()
        exposure_s = _median([f.exposure_s for f in frames if f.exposure_s])
        gain = _median([f.gain for f in frames if f.gain is not None])
        sensor_temp_c = _median(
            [f.sensor_temp_c for f in frames if f.sensor_temp_c is not None])
        masters = calibration.list_masters(settings.resolved_library_root)
        return calibration.diagnose_uncalibrated(
            masters, exposure_s=exposure_s, gain=gain, sensor_temp_c=sensor_temp_c)
    except Exception:  # noqa: BLE001 — advice is optional; never fail the info read
        return None


def _median(values: list[float]) -> float | None:
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return None
    n = len(vals)
    return vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2.0


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
        ("bias_path", "bias_master_id"),
    ):
        mid = calibration.master_id_for_path(lib_root, parsed.get(path_key))
        if mid is not None:
            options[id_key] = mid
        options.pop(path_key, None)  # never hand raw paths to the client/form
    return {"run_id": run_id, "options": options}


@router.get("/api/targets/{safe}/stack-runs/{run_id}/wallpaper")
def download_wallpaper(safe: str, run_id: int, request: Request,
                       aspect: str = "phone") -> Response:
    """Crop + size the finished stack preview into a ready-to-set wallpaper.

    ``aspect`` is one of ``phone`` / ``desktop`` / ``square``. The preview is
    cropped to that shape centred on the plate-solved target (falling back to the
    image centre when the run has no WCS or the target has no known position),
    downscaled to a sane device resolution without upsampling, and returned as a
    share-friendly JPEG. Read-only: nothing on disk changes.

    Registered *before* the ``/{kind}`` artifact route below so the literal
    ``wallpaper`` path segment isn't swallowed as an artifact kind.
    """
    from seestack.wallpaper import (
        WALLPAPER_PRESETS,
        png_size,
        render_wallpaper_jpeg,
        wallpaper_target_pixel,
    )

    preset = WALLPAPER_PRESETS.get(aspect)
    if preset is None:
        raise HTTPException(status_code=400, detail="Unknown wallpaper aspect")

    lib, proj = deps.open_target_project(request, safe)
    try:
        run = next((r for r in proj.iter_stack_runs() if r.id == run_id), None)
        entry = lib.find_target(safe)
    finally:
        proj.close()
        lib.close()
    if run is None:
        raise HTTPException(status_code=404, detail="No such run")
    png_path = run.preview_path
    if not png_path or not Path(png_path).exists():
        raise HTTPException(status_code=404, detail="No preview for this run")

    preview = Path(png_path).read_bytes()
    # Locate the target in the preview grid from the run's own WCS; None → centre.
    target_px = None
    ra = entry.ra_deg if entry is not None else None
    dec = entry.dec_deg if entry is not None else None
    if ra is not None and dec is not None and run.fits_path:
        size = png_size(preview)
        if size is not None:
            target_px = wallpaper_target_pixel(run.fits_path, ra, dec, size[0], size[1])

    data = render_wallpaper_jpeg(preview, preset, target_px)
    filename = f"{run.output_basename}_{aspect}_wallpaper.jpg"
    return Response(
        content=data, media_type="image/jpeg",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/api/targets/{safe}/stack-runs/{run_id}/{kind}")
def download_stack_run(safe: str, run_id: int, kind: str, request: Request,
                       north_up: bool = False, nameplate: bool = False) -> Response:
    # "jpeg" is a share-friendly transcode of the stored preview PNG (no separate
    # file on disk), served at the same resolution; the rest map to stored paths.
    if kind not in _KIND_FIELDS and kind != "jpeg":
        raise HTTPException(status_code=404, detail="Unknown artifact")
    lib, proj = deps.open_target_project(request, safe)
    try:
        run = next((r for r in proj.iter_stack_runs() if r.id == run_id), None)
        # The library entry supplies the target-name fallback for the nameplate
        # (fetched while the library is open, before it's closed below).
        entry = lib.find_target(safe) if run is not None and kind == "jpeg" else None
    finally:
        proj.close()
        lib.close()
    if run is None:
        raise HTTPException(status_code=404, detail="No such run")
    if kind == "jpeg":
        from seestack.stack.output import png_bytes_to_jpeg
        png_path = run.preview_path
        if not png_path or not Path(png_path).exists():
            raise HTTPException(status_code=404, detail="No preview for this run")
        preview = Path(png_path).read_bytes()
        # north_up rotates the shared picture so celestial North points up (like
        # reference photos of the object), using the run's own WCS — a no-op (the
        # bytes are returned untouched) when the run has no WCS or the correction
        # is trivial, so the ordinary download is byte-for-byte unchanged.
        if north_up:
            fits_path = run.fits_path
            if fits_path and Path(fits_path).exists():
                from seestack.render.thumbnail import orient_preview_north_up
                try:
                    preview = orient_preview_north_up(preview, fits_path)
                except Exception:  # noqa: BLE001 — a broken FITS just shares the un-oriented preview
                    pass
        # nameplate bakes the same tasteful acquisition footer the editor share
        # export offers (target · integration · date · gear) onto this direct
        # download — drawn last so it stays at the foot of a north-up-oriented
        # image. Best-effort provenance: a field it can't read is simply omitted,
        # and an empty nameplate is a clean no-op, so the default download is
        # byte-for-byte unchanged.
        plate = None
        if nameplate:
            plate = pipeline._nameplate_fields(run.fits_path or "", entry, run)
        data = png_bytes_to_jpeg(preview, nameplate=plate)
        filename = f"{run.output_basename}.jpg"
        return Response(
            content=data, media_type="image/jpeg",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    attr, media = _KIND_FIELDS[kind]
    path = getattr(run, attr)
    if not path or not Path(path).exists():
        raise HTTPException(status_code=404, detail=f"No {kind} for this run")
    filename = f"{run.output_basename}{Path(path).suffix}"
    download = kind in ("fits", "tiff", "preview")
    return FileResponse(
        path, media_type=media,
        filename=filename if download else None,
    )


_MAX_NOTES_LEN = 500


@router.patch("/api/targets/{safe}/stack-runs/{run_id}")
def update_stack_run(
    safe: str, run_id: int, body: dict[str, Any], request: Request,
) -> dict:
    """Update a run's free-text notes/label.

    The only mutable field is ``notes`` (a short user label like "best RGB v2").
    Whitespace is trimmed; an empty string clears the note. Length is capped so
    a stray paste can't bloat the DB. Additive — the ``notes`` column already
    exists, so this is upgrade-safe.
    """
    if "notes" not in body:
        raise HTTPException(status_code=422, detail="Missing 'notes' field")
    raw = body["notes"]
    if raw is not None and not isinstance(raw, str):
        raise HTTPException(status_code=422, detail="'notes' must be a string or null")
    notes: str | None = raw.strip() if isinstance(raw, str) else None
    if notes == "":
        notes = None
    if notes is not None and len(notes) > _MAX_NOTES_LEN:
        notes = notes[:_MAX_NOTES_LEN]

    lib, proj = deps.open_target_project(request, safe)
    try:
        updated = proj.set_stack_run_notes(run_id, notes)
    finally:
        proj.close()
        lib.close()
    if not updated:
        raise HTTPException(status_code=404, detail="No such run")
    return {"id": run_id, "notes": notes}


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
