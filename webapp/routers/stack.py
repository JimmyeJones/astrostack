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

from seestack.edit.proxy import rejection_map_path_for
from seestack.io.project import readable_frame_path
from seestack.previewcrop import UNKNOWN as CROP_UNKNOWN
from seestack.previewcrop import PreviewCrop, crop_pixel_box, parse_preview_crop
from seestack.stackhealth import seam_verdict
from webapp import deps, pipeline
from webapp.capture_nights import capture_night_count, capture_night_range
from webapp.preview_orient import (
    baked_north_up_deg,
    recovered_north_up_deg,
    remaining_north_up_deg,
)
from webapp.schemas import (
    STACK_DEFAULTS_META_KEY,
    StackOptionField,
    StackRunOut,
    stack_option_fields,
    validate_stack_options,
)
from webapp.site_location import resolve_site_lon

router = APIRouter(tags=["stack"])

# Asinh stretch + black-point bounds for the renderer. Both are 0..1: stretch
# is how hard to lift faint detail; black is the black point (higher = darker
# background). See seestack.render.thumbnail.asinh_stretch.
_STRETCH_MIN, _STRETCH_MAX = 0.0, 1.0
_BLACK_MIN, _BLACK_MAX = 0.0, 1.0
_STRETCH_DEFAULT, _BLACK_DEFAULT = 0.5, 0.35


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _run_row(request: Request, safe: str, run_id: int):  # noqa: ANN201
    """The run's own DB row, or raise 404. The row is a plain dataclass, so it
    stays readable after the project is closed."""
    lib, proj = deps.open_target_project(request, safe)
    try:
        run = next((r for r in proj.iter_stack_runs() if r.id == run_id), None)
    finally:
        proj.close()
        lib.close()
    if run is None:
        raise HTTPException(status_code=404, detail="No such run")
    return run


def _run_fits_path(request: Request, safe: str, run_id: int) -> tuple[str, str | None]:
    """Return (basename, fits_path) for a run, or raise 404."""
    run = _run_row(request, safe, run_id)
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


def _run_calibration_skipped(request: Request, safe: str, run_id: int) -> list[str]:
    """Plain-language reasons a run had to skip the calibration masters the user
    explicitly saved for this target (an empty list when it skipped none).

    The unattended binder is deliberately fail-soft — a master deleted since it was
    saved, or one built for another camera, is dropped rather than failing the
    overnight job — but that leaves the user with a less-calibrated picture and the
    reason only in the server log. Stamped by ``pipeline._stack_target`` and read
    back here so History can say it out loud."""
    lib, proj = deps.open_target_project(request, safe)
    try:
        raw = proj.get_meta(
            f"{pipeline.CALIBRATION_SKIPPED_META_PREFIX}{run_id}")
    finally:
        proj.close()
        lib.close()
    if not raw:
        return []
    with contextlib.suppress(ValueError, TypeError):
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [str(item) for item in parsed if isinstance(item, str)]
    return []


def _run_calibration_warnings(request: Request, safe: str, run_id: int) -> list[str]:
    """Plain-language mismatches between a calibration master this run *did* apply
    and the subs it calibrated (an empty list when everything matched).

    Distinct from :func:`_run_calibration_skipped`, which reports a master that was
    **dropped**: here the master was used, and that is precisely the problem — a
    dark shot at another exposure or a very different sensor temperature
    over/under-subtracts its pedestal on *every* frame, crushing the background or
    leaving dark current behind. The engine has always measured this
    (``CalibrationMasters.calibration_warnings``) but only wrote it to the server
    log, which nobody running a walk-away stack reads. Stamped by
    ``pipeline._stack_target`` and read back here so History can say it out loud."""
    lib, proj = deps.open_target_project(request, safe)
    try:
        raw = proj.get_meta(
            f"{pipeline.CALIBRATION_WARNINGS_META_PREFIX}{run_id}")
    finally:
        proj.close()
        lib.close()
    if not raw:
        return []
    with contextlib.suppress(ValueError, TypeError):
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [str(item) for item in parsed if isinstance(item, str)]
    return []


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
        # A valid-JSON *non-dict* (a legacy/hand-edited/foreign-version meta row —
        # this endpoint's writer only ever stores a dict) survives json.loads but
        # would make merged.update() raise TypeError, 500-ing the Stack form load.
        # Guard it exactly like every sibling meta reader above so a malformed row
        # degrades to "no saved defaults" rather than breaking the page.
        with contextlib.suppress(json.JSONDecodeError):
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                merged.update(parsed)
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


#: The calibration-master picks the Stack form posts alongside the engine
#: options. They're not ``StackOptions`` fields (they resolve to server-side
#: paths at stack time), so the schema whitelist below drops them — but the user
#: still expects "Save as defaults" to remember them and pre-fill the form next
#: visit. We persist them into the same per-target blob so the manual Stack form
#: round-trips them; ``coerce_stack_options`` harmlessly ignores them on the
#: walk-away auto-stack path (unknown keys are dropped), so this is inert there.
_MASTER_ID_KEYS = ("dark_master_id", "flat_master_id", "flat_dark_master_id", "bias_master_id")


def _coerce_master_id(value: Any) -> int | None:
    """A Stack-form master pick → an int id, or ``None`` for "not selected"."""
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@router.put("/api/targets/{safe}/stack-defaults")
def put_stack_defaults(safe: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
    valid = {fld.key for fld in stack_option_fields()}
    # A cleared numeric field posts ``null`` ("use the default"); never persist it
    # as a saved default, or it would flow back into every future stack (including
    # the walk-away auto-stack) and die in the engine with a raw ``TypeError``.
    clean = {k: v for k, v in body.items() if k in valid and v is not None}
    # Don't persist a default that would later fail every stack cryptically.
    try:
        validate_stack_options(clean)
    except ValueError as exc:
        raise HTTPException(status_code=400,
                            detail=f"invalid stack option: {exc}") from exc
    # Also remember the calibration-master picks so the form pre-fills them next
    # time (they used to be silently dropped, leaving the selects empty). Only
    # persist a key the user actually posted, coerced to a clean int id (or
    # ``None`` to clear a previously-saved pick).
    for key in _MASTER_ID_KEYS:
        if key in body:
            clean[key] = _coerce_master_id(body[key])
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
    min_max_reject: bool = False, min_max_reject_count: int = 1,
    auto_reject: bool = False, sigma_kappa: float = 3.0,
    sigma_clip: bool = True,
) -> dict[str, Any]:
    """Dry-run sizing for a stack: output canvas + estimated peak memory,
    computed without stacking, so the Stack form can warn *before* a run is
    submitted and refused for OOM (e.g. "Drizzle ×2 → 7680×4320, ≈2.1 GB peak,
    over the ~1.4 GB budget").

    Only the sizing-affecting knobs are query params: the canvas ones (drizzle /
    scale / reject / canvas mode) plus the min/max-reject knobs, because extra
    outlier passes hold ``2k`` extra canvas planes the run-time guard charges — so
    passing them keeps the pre-submit peak honest for a k>1 reject and lets the
    over-budget fix offer "drop the extra passes". ``sigma_clip`` is passed for
    ``rejection_reach`` below rather than for sizing — it cannot move the peak
    here, since the rejection-map plane it gates is only allocated when
    ``record_rejection_map`` is set and this dry run never sets it. Returns 422
    (not 500) when there's nothing solved to size yet, with the same guidance
    ``run_stack`` gives."""
    from seestack.stack.stacker import (
        StackOptions,
        auto_reject_method,
        auto_reject_switch_frames,
        estimate_stack,
        rejection_reach,
    )

    settings = deps.get_settings(request)
    lib, proj = deps.open_target_project(request, safe)
    try:
        options = StackOptions(
            drizzle=bool(drizzle),
            drizzle_scale=float(drizzle_scale),
            drizzle_reject=bool(drizzle_reject),
            mosaic_canvas=str(mosaic_canvas),
            min_max_reject=bool(min_max_reject),
            min_max_reject_count=int(min_max_reject_count),
            auto_reject=bool(auto_reject),
            sigma_kappa=float(sigma_kappa),
            sigma_clip=bool(sigma_clip),
        )
        try:
            est = estimate_stack(proj, options,
                                 memory_budget_gb=settings.max_stack_memory_gb)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        proj.close()
        lib.close()
    # Pass the mosaic's per-pixel depth so the form's "can this remove a satellite
    # trail?" line answers for the pixels the picture will actually have. On a
    # single field ``panel_depth`` is None and this is the frame count, as before.
    reach = rejection_reach(options, est.n_frames, depth=est.panel_depth)
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
        # The single least-destructive one-click fix + the memory it lands at,
        # matching the run-time refusal message (None when the run fits or no one
        # lever obviously does).
        "memory_fix": (
            {
                "kind": est.memory_fix.kind,
                "value": est.memory_fix.value,
                "peak_bytes": est.memory_fix.peak_bytes,
                "peak_gb": round(est.memory_fix.peak_bytes / 1e9, 2),
            }
            if est.memory_fix is not None
            else None
        ),
        # What this stack would print at, and the drizzle scale that reaches one
        # size bigger — the canvas said in the unit a human wants, while the knob
        # that sets it is still on screen. ``bigger_*`` are null whenever there is
        # nothing honest to offer (already the largest paper, past useful
        # super-resolution, or the bigger canvas busts the memory budget).
        "print_plan": (
            {
                "name": est.print_plan.name,
                "dpi": est.print_plan.dpi,
                "text": est.print_plan.text,
                "bigger_name": est.print_plan.bigger_name,
                "bigger_drizzle_scale": est.print_plan.bigger_drizzle_scale,
                "bigger_text": est.print_plan.bigger_text,
            }
            if est.print_plan is not None
            else None
        ),
        # What "Auto outlier removal" actually resolves to for this many frames.
        # With it on, the engine *overrides* the sigma-clip / min-max toggles, so
        # a form that still shows them as live tells the beginner the opposite of
        # what will run. Answered here rather than re-derived in the browser so
        # the form and the picker can never drift. ``null`` means the toggles
        # below really are live — auto is off, or drizzle is on (drizzle has its
        # own two-pass rejection and auto leaves the toggles alone).
        "auto_reject_resolved": (
            {
                "method": auto_reject_method(options.sigma_kappa, est.n_frames),
                "switch_at_frames": auto_reject_switch_frames(options.sigma_kappa),
                "n_frames": est.n_frames,
            }
            if options.auto_reject and not options.drizzle
            else None
        ),
        # Can the rejection this stack is configured for actually drop a lone
        # satellite trail at this frame count? κ-σ dispatches from 4 frames but
        # is mathematically blind to a single outlier until ``kappa_min_frames``
        # (11 at the default κ=3), so between the two it runs and clips nothing.
        # ``seestack.stackhealth`` already tells the user that *after* the stack;
        # this is the same helper answering *before* it, while the toggles that
        # would fix it are still on screen. Always present.
        "rejection_reach": {
            "method": reach.method,
            "n_frames": reach.n_frames,
            "lone_outlier_min_frames": reach.lone_outlier_min_frames,
            "reaches": reach.reaches,
        },
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
    from webapp.routers.editor import (
        AUTO_EDIT_BAKED_LOOK_PREFIX,
        EXPORTED_RECIPE_META_PREFIX,
        RECIPE_META_PREFIX,
    )

    lib, proj = deps.open_target_project(request, safe)
    try:
        runs = list(proj.iter_stack_runs())
        # The pinned "cover" run (library-level), so the History card can mark it.
        entry = lib.find_target(safe)
        cover_id = entry.cover_stack_run_id if entry is not None else None
        # Three small meta reads per run, so every surface that shows a run's
        # picture can tell an un-exported saved edit from a finished one (see
        # ``_unexported_edit``): the saved recipe, the one an export of this run
        # already rendered, and the look an in-place auto-edit baked into the
        # preview. All live in the same already-open DB.
        unexported = {
            r.id: _unexported_edit(
                r.options_json,
                proj.get_meta(f"{RECIPE_META_PREFIX}{r.id}"),
                proj.get_meta(f"{EXPORTED_RECIPE_META_PREFIX}{r.id}"),
                proj.get_meta(f"{AUTO_EDIT_BAKED_LOOK_PREFIX}{r.id}"),
            )
            for r in runs
        }
        # The observer's longitude, so each run's capture window can be named by
        # the *observing night* it belongs to — the same noon-to-noon bucket the
        # Nights card and the imaging calendar use. Resolved while the library is
        # still open (and memoised on the app), so History and the Nights card
        # can never name one session's subs two different dates.
        lon = resolve_site_lon(request, lib, deps.get_settings(request).site_lon)
    finally:
        proj.close()
        lib.close()
    out = []
    for r in runs:
        # What the stored preview shows of the canvas — an auto-edit border trim,
        # or geometry we can't reconcile at all. The pins/scale bar are measured
        # on the un-cropped FITS grid, so the UI needs both to draw on those bytes.
        crop = parse_preview_crop(r.preview_crop_json)
        night_start, night_end = capture_night_range(
            r.capture_start_utc, r.capture_end_utc, lon)
        nights = capture_night_count(
            getattr(r, "capture_hours_json", None), lon)
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
            # Does this run carry the "what stacking removed" map? Answered here,
            # from the same stat() sweep ``has_fits``/``has_preview`` already do,
            # so the card can decide whether to offer the overlay without one
            # extra header read per run on every History page load. False on
            # every run that didn't record one, which is every run today and all
            # of them before the option existed.
            has_rejection_map=bool(
                r.fits_path and rejection_map_path_for(r.fits_path).exists()),
            is_cover=(cover_id is not None and r.id == cover_id),
            notes=r.notes,
            total_exposure_s=r.total_exposure_s,
            reusable=_run_is_reusable(r.options_json),
            capture_night_start=night_start,
            capture_night_end=night_end,
            capture_nights=nights,
            transparency_ratio=r.transparency_ratio,
            noise_sigma=r.noise_sigma,
            stack_fwhm_px=r.stack_fwhm_px,
            # A recorded angle is passed through verbatim (including an explicit
            # 0.0 — that is a statement, not an absence); only a run from before
            # the column existed falls through to the recovery, so History stops
            # drawing its pins and scale bar on a picture an old save turned.
            preview_north_up_deg=(
                r.preview_north_up_deg if r.preview_north_up_deg is not None
                else (recovered_north_up_deg(r) or None)
            ),
            preview_crop=(
                {"x0": crop.x0, "y0": crop.y0, "x1": crop.x1, "y1": crop.y1}
                if isinstance(crop, PreviewCrop) else None
            ),
            preview_geometry_unknown=(crop == CROP_UNKNOWN),
            seam_residual=r.seam_residual,
            seam_verdict=seam_verdict(r.seam_residual),
            calstat=r.calstat,
            options=_parse_options(r.options_json),
            engine_version=r.engine_version,
            unexported_edit=unexported.get(r.id, False),
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


def _preview_is_display_space(options_json: str | None) -> bool:
    """True when a run's stored preview PNG is a tone-mapped display-space image —
    an in-place "Process target" Auto edit (``preview_display_space`` marker) whose
    FITS stays linear, so ``fits_is_display_space`` alone wouldn't catch it. Such a
    preview can't be honestly matched by a raw STF sub render or anchored by an
    asinh stretch suggestion, so the parity surfaces self-hide for it just as they
    do for a display-space *export* whose FITS is stamped."""
    if not options_json:
        return False
    try:
        parsed = json.loads(options_json)
    except json.JSONDecodeError:
        return False
    return isinstance(parsed, dict) and bool(parsed.get("preview_display_space", False))


def _recipe_look(recipe_json: str | None) -> list | None:
    """The part of a saved recipe that decides the finished picture.

    An ordered ``[[op id, sorted (key, value) params], …]`` over the recipe's
    **enabled** ops — i.e. everything the render depends on and nothing else. The
    fields deliberately left out are the ones two recipes describing the same
    picture can legitimately disagree on: each op's random ``uid``, and the
    recipe-level ``base_run_id`` / ``updated_utc`` (``put_recipe`` re-stamps the
    timestamp on every Save, so a byte comparison would call an unchanged edit
    changed).

    ``None`` when there is no recipe or it can't be read; ``[]`` when every op is
    disabled — a recipe that changes nothing. Both are "no look", which is why
    :func:`_unexported_edit` can test them together.
    """
    if not recipe_json:
        return None
    try:
        parsed = json.loads(recipe_json)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    ops = parsed.get("ops")
    if not isinstance(ops, list):
        return None
    look: list = []
    for op in ops:
        if not isinstance(op, dict) or not op.get("enabled", True):
            continue
        params = op.get("params")
        # Sorted by key so two recipes that differ only in JSON key order match.
        # Keys are unique, so no value is ever compared during the sort.
        items = sorted(params.items()) if isinstance(params, dict) else []
        look.append([op.get("id"), items])
    return look


def _baked_look_disagrees(baked_look_json: str | None, look: list | None) -> bool:
    """True when an auto-edit's **stamped** baked look (``AUTO_EDIT_BAKED_LOOK_PREFIX``)
    says the run's stored preview shows a *different* picture from the recipe now
    saved on it — i.e. the user re-opened a "Process target" run, changed something
    and pressed Save, so the recipe and the baked bytes have drifted apart.

    ``False`` whenever we can't tell — no stamp (every run auto-edited before the
    stamp existed, and every run that was never auto-edited at all), or a stamp that
    won't parse. That is deliberately the pre-stamp behaviour: the guard only ever
    fires where it has evidence, so an upgrading install sees no change.
    """
    if not baked_look_json:
        return False
    try:
        baked = json.loads(baked_look_json)
    except (json.JSONDecodeError, TypeError, ValueError):
        return False
    if not isinstance(baked, list):
        return False
    # Compared as JSON, not as Python objects: a look's per-op params are
    # ``(key, value)`` *tuples*, which survive a round-trip through the stamp as
    # lists, so `==` would call every stamp a mismatch. Both sides serialise
    # identically, and the ordering ``_recipe_look`` imposes makes the text
    # canonical.
    return json.dumps(baked) != json.dumps(look)


def _unexported_edit(options_json: str | None, recipe_json: str | None,
                     exported_recipe_json: str | None = None,
                     baked_look_json: str | None = None) -> bool:
    """True when this run carries a **saved editor recipe that its stored preview
    does not show** — the user edited the picture, pressed Save, and never
    exported.

    Why it matters: every surface that shows "your picture" (the Target page's
    hero, History, the Gallery) serves the run's *baked* preview PNG. For an
    export — or an in-place "Process target" Auto edit — that preview genuinely
    is the finished look. But a saved-only recipe lives in the project DB and
    nowhere else, so the app keeps showing the plain auto-stretch of the linear
    stack and the user's work is invisible outside the editor. Flagging it lets
    those surfaces say so honestly (and offer to finish the export) instead of
    quietly presenting an image the user didn't make.

    False when there is no recipe, when the recipe is unparseable, when every op
    in it is disabled — a recipe that changes nothing is not an unfinished edit —
    and for an in-place "Process target" Auto edit, whose recipe *is* what its
    preview shows.

    Note which display-space marker is checked and which is not, because the two
    are written by different paths and only one of them bakes the stored recipe:
    ``preview_display_space`` marks the in-place Auto edit, which stamps the
    recipe it just baked onto the *same* run (``pipeline._auto_process_run``), so
    a recipe there is already visible and must not be flagged. ``display_space``
    marks an editor *export*, which writes a **new** run and deliberately stores
    no recipe on it — so a recipe on such a run can only have come from the user
    re-opening that export, editing it further and saving, which is exactly the
    unfinished edit this flags. Excluding it would silently miss every
    second-round edit.

    ``exported_recipe_json`` is the recipe an export of *this* run actually
    rendered (``editor_exported:<run_id>``, stamped by
    ``pipeline._apply_editor_to_run``). Without it — every install from before the
    marker existed, and every run that has never been exported — the answer is
    exactly what it always was. With it, a saved recipe describing the same
    picture as the one already exported is **finished**, not unfinished: doing the
    thing the app asked for has to be able to stop it asking. Compared by
    :func:`_recipe_look`, so re-saving an unchanged edit (which re-stamps
    ``updated_utc``) stays quiet, while changing a parameter and saving speaks up
    again — that second-round edit is as invisible as the first one was.

    ``baked_look_json`` is the look the in-place Auto edit actually baked into the
    preview (``editor_auto_baked_look:<run_id>``). The ``preview_display_space``
    exemption above assumes the saved recipe *is* what the preview shows, which stops
    being true the moment the user re-opens such a run, tweaks it and saves — and
    that second-round edit is exactly as invisible as any other. With the stamp in
    hand we can tell the two apart, so a drifted run loses the exemption and is
    flagged like any other unfinished edit. Without it (a run auto-edited before the
    stamp existed) the answer is exactly what it always was."""
    look = _recipe_look(recipe_json)
    if not look:
        # No recipe, unreadable, or every op disabled — nothing unfinished.
        return False
    opts = _parse_options(options_json)
    if opts.get("preview_display_space") and not _baked_look_disagrees(
            baked_look_json, look):
        return False
    # Already exported *this* look ⇒ finished. Anything else ⇒ still unfinished.
    return not (exported_recipe_json and _recipe_look(exported_recipe_json) == look)


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


# A practical ceiling on the downloaded PNG's long edge: a Seestar single field
# (~1080–1920 px) or a 2× drizzle (~3840 px) comes out at true native resolution,
# while a 100+ MP union mosaic is capped so the render/response stays within the
# RAM-capped NAS's budget. The full-res FITS/TIFF remain for the true native
# pixels of such a giant mosaic.
_FULL_RES_PNG_MAX_LONG_EDGE = 8000


# NOTE: declared before the "/{kind}" catch-all download route below so the
# literal "full-res-png" segment isn't swallowed as an artifact kind.
@router.get("/api/targets/{safe}/stack-runs/{run_id}/full-res-png")
async def download_full_res_png(
    safe: str, run_id: int, request: Request, north_up: bool = False,
) -> Response:
    """The finished picture as a **native-resolution PNG** — the same look as the
    gallery/History thumbnail, just at full output resolution instead of the
    1024 px preview cap.

    This is the direct answer to the "my downloaded picture is low-res" report: the
    FITS/TIFF already carry full-resolution pixels but aren't easily viewable, and
    the quick PNG button serves the small preview. This serves the picture the user
    sees at full size. ``north_up`` rotates it so celestial North points up (like
    the shared JPEG), a no-op when the run has no usable WCS. Runs in a threadpool
    so it never blocks the job worker.

    A "Process target" auto-edit leaves the FITS linear and stores the finished look
    as the run's editor recipe, so for such a run the plain STF render would serve
    the *un-edited* master. When the run's preview is a baked display-space edit and
    a saved recipe exists, render that recipe at native resolution instead, so the
    download matches the preview the user clicked.

    For the same reason the render also takes the North-up turn a past "Adjust →
    North up → Save" baked into the stored preview, whether or not ``north_up``
    was asked for: those bytes are what every other surface shows, and this render
    starts from the canvas-grid FITS, so without it the download comes back
    rotated away from the picture it claims to be."""
    from webapp.routers.editor import RECIPE_META_PREFIX

    lib, proj = deps.open_target_project(request, safe)
    try:
        run = next((r for r in proj.iter_stack_runs() if r.id == run_id), None)
        if run is None or not run.fits_path or not Path(run.fits_path).exists():
            raise HTTPException(
                status_code=404,
                detail="No FITS for this run to render at full resolution")
        basename, fits_path = run.output_basename, run.fits_path
        # The stretch History's "Adjust" save baked into the stored preview, if
        # the user tuned one (NULL on an unadjusted or display-space run).
        preview_stretch, preview_black = run.preview_stretch, run.preview_black
        recipe_json = None
        if _preview_is_display_space(run.options_json):
            recipe_json = proj.get_meta(f"{RECIPE_META_PREFIX}{run_id}")
    finally:
        proj.close()
        lib.close()

    recipe_dict = None
    if recipe_json:
        with contextlib.suppress(json.JSONDecodeError):
            parsed = json.loads(recipe_json)
            if isinstance(parsed, dict):
                recipe_dict = parsed

    # A run whose preview a past "Adjust → North up → Save" turned shows that
    # turned picture *everywhere* — the thumbnail, the big view, the share JPEG,
    # the wallpaper — because all of them serve the stored bytes. This render
    # starts from the FITS instead, which is on the canvas grid, so without this
    # it would hand back the same picture rotated back: a download that visibly
    # disagrees with the picture the user clicked on, under a menu item that says
    # it is that picture at full size. The turn is applied whenever the stored
    # bytes carry one, whether or not this request asked for it — and asking for
    # it as well is the same render, not a second rotation, because both mean
    # "the run's own full North-up correction".
    # In the threadpool because the recovered-angle path reads the preview's PNG
    # header and the master's WCS, and this endpoint is async.
    render_north_up = bool(north_up) or bool(
        await run_in_threadpool(baked_north_up_deg, run))

    if recipe_dict is not None:
        png = await run_in_threadpool(
            pipeline.render_run_recipe_fullres_png, fits_path, recipe_dict,
            max_long_edge=_FULL_RES_PNG_MAX_LONG_EDGE, north_up=render_north_up,
        )
    else:
        # A run the user tuned in History's "Adjust" has its stored preview baked
        # through the *asinh* curve, not the STF — and the thumbnail, share-JPEG
        # and wallpaper all serve those bytes. Carry the saved stretch/black into
        # the full-res render so this download shows the same picture instead of
        # silently reverting to the autostretch. An unadjusted run (columns NULL)
        # keeps the STF exactly as before.
        from seestack.render.thumbnail import render_preview_png_full_res
        png = await run_in_threadpool(
            render_preview_png_full_res, fits_path,
            max_long_edge=_FULL_RES_PNG_MAX_LONG_EDGE, north_up=render_north_up,
            stretch=preview_stretch, black=preview_black,
        )
    filename = f"{basename}_fullres.png"
    return Response(
        content=png, media_type="image/png",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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
    coverage from (older/edited runs), so it never regresses to a 404.

    When the stored preview was saved **North-up** (History's "Adjust"), the
    coverage mask is taken through the same rotation before compositing — the mask
    comes off the un-rotated FITS, so without that its transparent regions land
    where the picture no longer is."""
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
    north_up_deg = baked_north_up_deg(run)
    crop = parse_preview_crop(run.preview_crop_json)

    from seestack.render.orient import rotate_mask_north_up
    from seestack.render.thumbnail import overlay_rgba_png, stack_coverage_mask

    def work() -> bytes:
        preview = Path(preview_path).read_bytes()
        if fits_path and Path(fits_path).exists():
            try:
                if crop == CROP_UNKNOWN:
                    # The stored preview came out of a recipe whose geometry we
                    # can't reconcile with the canvas, so there is no honest way
                    # to line the mask up with it. Serve the opaque preview
                    # rather than punch transparency through the wrong pixels.
                    return preview
                mask = stack_coverage_mask(fits_path)
                if isinstance(crop, PreviewCrop):
                    # The picture is a *crop* of the canvas (an auto-edit border
                    # trim); the mask comes off the un-cropped FITS, so take the
                    # same rectangle out of it before it drives the alpha.
                    mx0, my0, mx1, my1 = crop_pixel_box(
                        crop, mask.shape[1], mask.shape[0])
                    mask = mask[my0:my1, mx0:mx1]
                if north_up_deg:
                    mask = rotate_mask_north_up(mask, north_up_deg)
                return overlay_rgba_png(preview, mask)
            except Exception:  # noqa: BLE001 — a broken FITS just serves the opaque preview
                return preview
        return preview

    png = await run_in_threadpool(work)
    return Response(content=png, media_type="image/png",
                    headers={"Cache-Control": "no-store"})


@router.get("/api/targets/{safe}/stack-runs/{run_id}/rejection-overlay")
async def rejection_overlay(
    safe: str, run_id: int, request: Request, north_up: bool = False,
) -> Response:
    """A transparent PNG showing *where* outlier rejection dropped samples, sized
    to the run's stored preview so it lays straight over the picture.

    The trust line already says rejection clipped ~0.4% of samples; this is the
    other half — the satellite trains, plane trails and cosmic rays the stack
    quietly removed, laid over the user's own image. Only runs that were asked to
    record a map have one (``StackOptions.record_rejection_map``, off by
    default); every other run 404s, which the History card reads as "no overlay
    for this one" rather than as a failure.

    Geometry follows the *stored preview* exactly the way ``sky_overlay`` does —
    the same crop rectangle for an auto-edit border trim, the same North-up
    rotation — because the map comes off the un-cropped, un-rotated canvas and
    would otherwise highlight a trail where the trail no longer is. A preview
    whose geometry can't be reconciled with the canvas (``CROP_UNKNOWN``) serves
    no overlay at all rather than a misaligned one.

    ``north_up`` composes the *same* on-the-fly turn ``…/preview?north_up=true``
    applies to the stored bytes (nothing on disk changes there either), so the
    tint can stay in register with a picture the viewer is looking at North-up
    instead of stepping aside. It is the **remainder** — a preview a past save
    already baked the rotation into is turned no further — read from the one
    helper that decides what the picture itself gets
    (:func:`~seestack.render.thumbnail.preview_north_up_remainder_deg`), so the
    two can't drift. The turn is applied to the drop-count *plane*, before the
    RGBA tint is built, which is why the overlay's alpha is never at risk: the
    transparent PNG is rendered at the rotated size rather than rotated itself.
    """
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
    if not run.fits_path:
        raise HTTPException(status_code=404, detail="No rejection map for this run")
    map_path = rejection_map_path_for(run.fits_path)
    if not map_path.exists():
        raise HTTPException(status_code=404, detail="No rejection map for this run")
    crop = parse_preview_crop(run.preview_crop_json)
    if crop == CROP_UNKNOWN:
        raise HTTPException(status_code=404,
                            detail="Preview geometry can't be matched to the map")
    north_up_deg = baked_north_up_deg(run)

    from seestack.render.orient import north_up_pixel_transform, rotate_plane_north_up
    from seestack.render.thumbnail import (
        preview_north_up_remainder_deg,
        rejection_overlay_png,
    )

    # The extra turn this request wants on top of whatever the stored bytes
    # already carry — 0.0 (a no-op) unless asked for, so the bare URL every
    # existing surface embeds is byte-for-byte unchanged. An unreadable FITS
    # degrades to "don't turn", the same way the preview endpoint's own turn
    # does, rather than failing a request that has a perfectly good map.
    extra_deg = 0.0
    if north_up:
        with contextlib.suppress(Exception):
            extra_deg = preview_north_up_remainder_deg(
                run.fits_path, already_deg=north_up_deg)

    def work() -> bytes:
        import io

        import numpy as np
        from astropy.io import fits as _fits
        from PIL import Image

        with _fits.open(map_path) as hdul:
            dens = np.asarray(hdul[0].data, dtype=np.float32)
        if isinstance(crop, PreviewCrop):
            cx0, cy0, cx1, cy1 = crop_pixel_box(crop, dens.shape[1], dens.shape[0])
            dens = dens[cy0:cy1, cx0:cx1]
        if north_up_deg:
            dens = rotate_plane_north_up(dens, north_up_deg)
        with Image.open(io.BytesIO(Path(preview_path).read_bytes())) as im:
            size = im.size
        if extra_deg:
            # Two turns, exactly as the picture takes them: the stored bytes were
            # rotated by `north_up_deg` when they were saved, and this request
            # rotates *those* bytes again. Composing them into one angle would
            # land on a different pixel grid than the picture does.
            dens = rotate_plane_north_up(dens, extra_deg)
            geom = north_up_pixel_transform(size[0], size[1], extra_deg)
            if geom is not None:
                size = (geom[2], geom[3])
        return rejection_overlay_png(dens, size)

    try:
        png = await run_in_threadpool(work)
    except Exception as exc:  # noqa: BLE001 — a broken sibling is "no overlay"
        raise HTTPException(
            status_code=404, detail="Rejection map could not be read") from exc
    return Response(content=png, media_type="image/png",
                    headers={"Cache-Control": "no-store"})


def _scale_bar_from_wcs(wcs, width: int, height: int):  # noqa: ANN001, ANN202
    """A :class:`~seestack.scalebar.ScaleBar` for a run from its celestial WCS
    and :func:`~seestack.io.wcs_io.arcsec_per_px`, via the pure
    :func:`scale_bar_for`. Returns ``None`` when there is no usable WCS or scale,
    so the caller omits the scale bar cleanly."""
    from seestack.io.wcs_io import arcsec_per_px
    from seestack.scalebar import scale_bar_for

    if wcs is None or width <= 0:
        return None
    scale = arcsec_per_px(wcs)
    if scale is None:
        return None
    return scale_bar_for(scale, width, height)


def _png_width(png_data: bytes) -> int:
    """The pixel width of an encoded PNG, or 0 when it can't be read (which
    simply means "no scale bar" rather than a failed download)."""
    from io import BytesIO

    from PIL import Image

    try:
        with Image.open(BytesIO(png_data)) as img:
            return int(img.size[0])
    except Exception:  # noqa: BLE001 — an unreadable preview just gets no marks
        return 0


def _unrotated_preview_size(fits_path: str) -> tuple[int, int] | None:
    """The ``(width, height)`` a run's preview had *before* any North-up turn.

    ``save_stack_preview`` renders through ``render_stack_png`` at
    :data:`~seestack.render.thumbnail.PREVIEW_MAX_WIDTH`, so the master's own
    dimensions give that grid exactly. ``None`` when the master can't be read, so
    the caller falls back to the stored PNG's size (which is the same thing for
    every preview nobody saved North-up)."""
    from seestack.io.wcs_io import celestial_wcs_from_fits
    from seestack.render.thumbnail import preview_grid_size

    try:
        _wcs, full_w, full_h = celestial_wcs_from_fits(fits_path)
    except Exception:  # noqa: BLE001 — an unreadable master just uses the stored size
        return None
    if full_w <= 0 or full_h <= 0:
        return None
    return preview_grid_size(full_w, full_h)


def _unrotated_preview_width(png_data: bytes, fits_path: str | None,
                             baked_north_up: float) -> int:
    """The width of a run's preview **before** any North-up turn — what the scale
    bar's stored fraction is a fraction *of*.

    A rotate-with-expand grows the canvas without changing the pixel scale, so
    measuring the bar against a preview a past save already rotated draws it the
    wrong length. The stored bytes are the only thing on hand, so recover the
    un-rotated grid the way it was made: ``save_stack_preview`` renders through
    ``render_stack_png`` at :data:`~seestack.render.thumbnail.PREVIEW_MAX_WIDTH`,
    so the master's own dimensions give it exactly. Falls back to the PNG's own
    width — which is right for every un-rotated preview, i.e. all of them until
    someone saves one North-up — whenever there is no baked rotation to undo or
    no master to read it from."""
    if not baked_north_up or not fits_path:
        return _png_width(png_data)
    flat = _unrotated_preview_size(fits_path)
    return flat[0] if flat is not None else _png_width(png_data)


def _sky_marks_for_run(fits_path: str | None, preview_width: int,
                       north_up_deg: float = 0.0,
                       crop: PreviewCrop | str | None = None):  # noqa: ANN202
    """The scale bar + North/East rose to bake onto a run's shared picture.

    Reads the run's own master-FITS WCS, turns its pixel scale into a round bar
    (:func:`seestack.scalebar.scale_bar_for`) and asks the same WCS where North
    and East point (:func:`seestack.skymarks.sky_directions`). ``preview_width``
    is the width of the image the marks will be drawn on **before** any
    North-up rotation, because the bar's length is stored as a fraction of the
    picture's width and a rotate-with-expand changes the canvas without changing
    the scale. ``north_up_deg`` is the rotation actually applied to those pixels,
    so the rose follows them.

    ``crop`` is what the stored preview shows of the canvas (an auto-edit border
    trim). The bar's length is a fraction of the *canvas* width, so on a cropped
    picture the same on-sky length covers a larger fraction of what's left —
    divide by the crop's width fraction. :data:`~seestack.previewcrop.UNKNOWN`
    means the geometry can't be reconciled, so no bar is drawn at all rather than
    a wrong one. (The rose is unaffected: a crop moves no pixel's orientation.)

    Always returns a :class:`~seestack.skymarks.SkyMarks` — an empty one (a
    clean no-op when drawn) for a run with no FITS, no WCS or an unusable scale,
    so the caller never has to special-case an older/edited run."""
    from seestack.skymarks import SkyMarks, rotated, sky_directions

    if not fits_path or not Path(fits_path).exists() or preview_width <= 0:
        return SkyMarks()
    if crop == CROP_UNKNOWN:
        return SkyMarks()
    from seestack.io.wcs_io import celestial_wcs_from_fits

    try:
        wcs, width, height = celestial_wcs_from_fits(fits_path)
    except Exception:  # noqa: BLE001 — a broken FITS just means "no marks"
        return SkyMarks()
    if wcs is None:
        return SkyMarks()
    # Size the bar against the part of the canvas the picture actually shows, so
    # its round length is chosen for the visible field and its `fraction` is
    # already a fraction of *this* picture's width.
    bx0, by0, bx1, by1 = crop_pixel_box(
        crop if isinstance(crop, PreviewCrop) else None, width, height)
    bar = _scale_bar_from_wcs(wcs, bx1 - bx0, by1 - by0)
    directions = rotated(sky_directions(wcs, width, height), north_up_deg)
    return SkyMarks(
        bar_px=(bar.fraction * preview_width) if bar is not None else None,
        # ASCII prime marks: the ′/″ in `bar.label` have no glyph in the
        # bundled face and would bake a hollow box into the picture (v0.282.1).
        bar_label=bar.ascii_label if bar is not None else "",
        directions=directions,
    )


def _object_labels_for_run(fits_path: str | None, north_up_deg: float,
                           crop: PreviewCrop | str | None = None):  # noqa: ANN202
    """The catalog object names to bake onto a run's shared picture.

    Same source as the on-screen overlay — the bundled offline catalog projected
    through this run's own solved output WCS (:func:`seestack.annotate.
    objects_in_field`) — so the file a beginner posts says exactly what the card
    they shared it from said.

    Two geometries have to be honoured, and unlike the browser overlay there is
    no toggle to fall back to, so both **refuse rather than guess**:

    * **Rotation.** The pins are measured on the un-rotated FITS grid. A picture
      that has been turned — by ``?north_up=true`` or by a past "Adjust → North
      up → Save" that baked the turn into the stored bytes — no longer matches
      that grid, and a rotate-with-expand moves every pixel *and* grows the
      canvas. So a turned picture is shared unlabelled rather than mis-plotted.
    * **Crop.** A stored preview can be a border trim of the canvas
      (the one-click auto-edit does this on a mosaic). That one *is* reconcilable
      — re-base each pin onto the visible rectangle, which is what
      :func:`~seestack.objectlabels.place_labels` takes ``crop_box`` for — and an
      object outside the trim simply drops out. A crop whose geometry can't be
      reconciled at all (:data:`~seestack.previewcrop.UNKNOWN`) refuses, like the
      scale bar.

    Always returns an :class:`~seestack.objectlabels.ObjectLabels` — an empty
    (falsey) one for every refusal and for a run with no FITS, no WCS, or no
    catalog object in frame — so the caller never special-cases them and the
    plain share stays byte-for-byte what it was."""
    from seestack.objectlabels import ObjectLabels, place_labels

    if not fits_path or not Path(fits_path).exists():
        return ObjectLabels()
    if north_up_deg:
        return ObjectLabels()
    if crop == CROP_UNKNOWN:
        return ObjectLabels()
    from seestack.annotate import objects_in_field
    from seestack.io.wcs_io import celestial_wcs_from_fits

    try:
        wcs, width, height = celestial_wcs_from_fits(fits_path)
    except Exception:  # noqa: BLE001 — a broken FITS just means "no labels"
        return ObjectLabels()
    if wcs is None:
        return ObjectLabels()
    box = crop_pixel_box(crop if isinstance(crop, PreviewCrop) else None,
                         width, height)
    return place_labels(objects_in_field(wcs, width, height), width, height,
                        crop_box=box)


@router.get("/api/targets/{safe}/stack-runs/{run_id}/framing")
async def stack_run_framing(safe: str, run_id: int, request: Request) -> dict[str, Any] | None:
    """"Did I frame it well?" — a plain-language verdict on how this finished
    stack actually caught its target.

    The app already tells a beginner *before* the shoot whether a target fits one
    Seestar frame (`framing_hint`). Nothing told them afterwards whether it
    landed well — the most common framing surprise (the object off-centre, or
    half of it running off an edge) is only discoverable once the picture exists,
    and by then a whole night has been spent. This answers it from the result:
    the catalog object's centre and size, projected through the run's own solved
    output WCS.

    Returns ``null`` — never a 404 for a run that exists, and never a guess —
    when the target doesn't match the catalog, has no vetted size, or the run has
    no usable celestial WCS. Read-only; the header read + projection run in a
    threadpool so they never block the job worker."""
    from seestack.objectinfo import identify_object

    _, fits_path = _run_fits_path(request, safe, run_id)  # raises 404 for an unknown run
    lib = deps.open_library(request)
    try:
        entry = lib.find_target(safe)
        info = (
            identify_object(entry.name, entry.ra_deg, entry.dec_deg)
            if entry is not None else None
        )
    finally:
        lib.close()
    if info is None or info.size_arcmin is None or not fits_path:
        return None

    # The verdict itself lives in `webapp.framing_advice` because the night
    # planner repeats its *nudge* on the row of a target the user already owns —
    # the one moment "nudge a little south" is actionable is while they're
    # pointing the scope, not the morning after. One definition, one voice.
    from webapp.framing_advice import framing_payload

    return await run_in_threadpool(framing_payload, fits_path, info)


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
    run = _run_row(request, safe, run_id)  # raises 404 for an unknown run
    fits_path = run.fits_path

    def work() -> dict[str, Any]:
        from seestack.annotate import objects_in_field
        from seestack.io.wcs_io import celestial_wcs_from_fits
        from seestack.skymarks import sky_directions

        wcs, width, height = celestial_wcs_from_fits(fits_path) if fits_path else (None, 0, 0)
        objs = objects_in_field(wcs, width, height)
        directions = sky_directions(wcs, width, height)
        # "How far would `…/preview?north_up=true` actually turn this picture?" —
        # 0.0 when it would hand back the stored bytes untouched, reported as null
        # so a surface can decide whether offering the turn is worth a control at
        # all. That is deliberately **not** `applied_north_up_deg(fits)`, which
        # answers the different question "how far is this run's *data* from North
        # up?": on a run whose preview a past "Adjust → North up → Save" already
        # turned, the renderer passes the baked angle as `already_deg` and applies
        # only the remainder — i.e. nothing — while the data is still just as far
        # from North as it ever was. `remaining_north_up_deg` mirrors that
        # renderer's own arithmetic rather than re-deriving it, so this can never
        # disagree with what a rotated render does. It re-reads the header rather
        # than taking the `wcs` above; a second header read is cheap, and
        # re-deriving the threshold here to save it is exactly the drift the
        # shared helpers exist to prevent.
        north_up_deg = remaining_north_up_deg(run)
        # The picture a user actually looks at (and shares) can be a *crop* of
        # this canvas — the one-click "Process target" auto-edit trims a mosaic's
        # ragged border. The drawn bar is already re-based client-side, but the
        # sentence beside it ("the whole frame is about 5.4 full Moons wide") is a
        # claim about the *field*, and a canvas-sized one overstates a trimmed
        # picture by up to ~1/0.7×. So measure a second, honest bar on the visible
        # rectangle — the same helper and the same pixel box the shared JPEG's
        # baked marks already use (:func:`_sky_marks_for_run`) — and let the
        # frontend pick whichever matches what is on screen (History's live Adjust
        # render is the *full* canvas, so both answers have to be available).
        # ``None`` unless the run really is cropped, so an uncropped run's payload
        # is byte-for-byte what it was.
        crop = parse_preview_crop(run.preview_crop_json)
        preview_bar = None
        if isinstance(crop, PreviewCrop):
            cx0, cy0, cx1, cy1 = crop_pixel_box(crop, width, height)
            preview_bar = _scale_bar_from_wcs(wcs, cx1 - cx0, cy1 - cy0)
        return {
            "width": width,
            "height": height,
            "north_up_deg": north_up_deg or None,
            # "Which way is up?" — where North and East point on this run's own
            # pixel grid, so the in-app overlay can draw the same rose the shared
            # JPEG bakes (v0.284.0) instead of the file and the screen disagreeing.
            # Same numbers, same helper, one definition. None when the run has no
            # usable orientation — the overlay then simply omits the rose rather
            # than drawing a made-up direction.
            "directions": (
                {"north_deg": directions.north_deg, "east_deg": directions.east_deg}
                if directions is not None else None
            ),
            # "How big is this in the sky?" — a round scale bar + full-Moon
            # comparison from the run's own local pixel scale, so a beginner can
            # read (and share) the picture's true angular size. None when the run
            # has no usable celestial WCS (older/edited runs) — the overlay then
            # simply doesn't offer it. Sized against the FITS-grid width; the
            # frontend scales its `fraction` to whatever preview it renders.
            "scale_bar": (
                sb.to_dict()
                if (sb := _scale_bar_from_wcs(wcs, width, height)) is not None
                else None
            ),
            # The same bar measured on the part of the canvas the *stored preview*
            # actually shows, for the surfaces that display those bytes (and for
            # the caption that describes them). Its ladder rung is re-chosen for
            # the visible field, so it is a complete, self-consistent answer rather
            # than a rescaled fraction — and its `frame_arcmin` / `moon_comparison`
            # describe the picture on screen instead of the canvas behind it.
            # ``null`` when the run isn't cropped (use `scale_bar`) or has no
            # usable WCS. Absent on an older backend, which reads the same way.
            "preview_scale_bar": (
                preview_bar.to_dict() if preview_bar is not None else None
            ),
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

    # Version tag: bump when the *render output* changes for an unchanged series
    # (e.g. burned-in per-frame date/sub labels, v2) so existing cached reels are
    # rebuilt in place rather than serving a stale label-less animation.
    parts = ["v2-labels"]
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
    from seestack.render.deepening import build_deepening_reel, deepening_frame_label

    # Per-frame provenance labels, so a downloaded/shared clip carries its own
    # "28 Jun · 120 subs" story frame by frame (each frame from the same run row
    # the info endpoint already reads).
    labels = [deepening_frame_label(r.timestamp_utc, r.n_frames_used) for r in runs]
    path = build_deepening_reel([r.fits_path for r in runs], out_dir, basename,
                                labels=labels)
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


# --- Share-ready "zoom clip" -------------------------------------------------
# A short looping push-in on ONE finished picture, for posting. Unlike the two
# animations above (the progress reel and the deepening reel, both of which show a
# stack accumulating *over time*) this is a purely spatial camera move over the
# finished frame — see seestack.render.zoomclip. Rendered on demand from the run's
# stored preview PNG (the same bytes the wallpaper/share exports use, so it matches
# the picture on screen for every kind of run) and cached beside the outputs with a
# content signature, so a repeat download is a plain file read.

_ZOOM_CLIP_SUFFIXES = ("_zoom.webp", "_zoom.png")


def _target_pixel_in_preview(run: Any, entry: Any,
                             preview_png: bytes) -> tuple[float, float] | None:
    """Where the catalogued target sits in a run's **stored preview bytes**, or
    ``None`` to centre on the image instead.

    Two things can put those bytes on a different grid from the master, and both
    have to be undone before the WCS answer means anything: an auto-edit border
    trim (``preview_crop``), and a North-up turn a past "Adjust → Save" baked in
    (``preview_north_up_deg``) — so the mapping is done on the un-rotated grid and
    the answer turned by the same angle. One definition, two callers (the wallpaper
    crop and the zoom clip), because getting either half wrong re-centres the
    picture on empty sky.
    """
    from seestack.wallpaper import (
        png_size,
        rotate_point_north_up,
        wallpaper_target_pixel,
    )

    ra = entry.ra_deg if entry is not None else None
    dec = entry.dec_deg if entry is not None else None
    if ra is None or dec is None or not run.fits_path:
        return None
    baked = baked_north_up_deg(run)
    flat_size = png_size(preview_png)
    if baked:
        flat_size = _unrotated_preview_size(run.fits_path) or flat_size
    if flat_size is None:
        return None
    target_px = wallpaper_target_pixel(
        run.fits_path, ra, dec, flat_size[0], flat_size[1],
        parse_preview_crop(run.preview_crop_json))
    if target_px is not None and baked:
        target_px = rotate_point_north_up(
            target_px[0], target_px[1], flat_size[0], flat_size[1], baked)
    return target_px


def _zoom_clip_signature(preview_path: Path,
                         focus_xy: tuple[float, float] | None) -> str:
    """Content signature of a run's clip — the preview bytes it was made from plus
    the point it zooms onto, so a re-edited preview (or a target that has since
    been plate-solved) rebuilds rather than serving yesterday's move."""
    import hashlib

    # Version tag: bump when the *render output* changes for an unchanged preview,
    # so cached clips are rebuilt in place instead of serving the old schedule.
    parts = ["v1"]
    try:
        st = os.stat(preview_path)
        parts.append(f"{st.st_mtime_ns}:{st.st_size}")
    except OSError:
        parts.append("0:0")
    parts.append("centre" if focus_xy is None
                 else f"{focus_xy[0]:.1f},{focus_xy[1]:.1f}")
    return hashlib.sha1("|".join(parts).encode()).hexdigest()


def _build_or_get_zoom_clip(preview_path: Path, basename: str,
                            focus_xy: tuple[float, float] | None) -> Path | None:
    """Return the cached zoom clip for this run's preview, rebuilding it when the
    signature has changed. Blocking (decodes + encodes an animation), so callers
    dispatch it to a threadpool."""
    out_dir = preview_path.parent
    sig = _zoom_clip_signature(preview_path, focus_xy)
    sig_file = out_dir / f"{basename}_zoom.sig"
    for suffix in _ZOOM_CLIP_SUFFIXES:
        cand = out_dir / f"{basename}{suffix}"
        if cand.exists() and sig_file.exists():
            with contextlib.suppress(OSError):
                if sig_file.read_text().strip() == sig:
                    return cand
    # (Re)build: clear any stale clip of either format first, so a format change
    # (WEBP↔APNG) can't leave two files the resolver disagrees on.
    for suffix in _ZOOM_CLIP_SUFFIXES:
        with contextlib.suppress(OSError):
            (out_dir / f"{basename}{suffix}").unlink()
    from seestack.render.zoomclip import build_zoom_clip

    try:
        data = preview_path.read_bytes()
    except OSError:
        return None
    path = build_zoom_clip(data, out_dir, basename, focus_xy=focus_xy)
    if path is None:
        return None
    with contextlib.suppress(OSError):
        sig_file.write_text(sig)
    return path


def _zoom_clip_inputs(request: Request, safe: str,
                      run_id: int) -> tuple[Any, Path | None, tuple[float, float] | None]:
    """``(run, preview_path, focus_xy)`` for a run's zoom clip — the one DB read
    both endpoints below need. ``preview_path`` is ``None`` when the run has no
    stored picture to move the camera over, which is what makes the card self-hide
    rather than 404 at the user."""
    lib, proj = deps.open_target_project(request, safe)
    try:
        run = next((r for r in proj.iter_stack_runs() if r.id == run_id), None)
        entry = lib.find_target(safe)
    finally:
        proj.close()
        lib.close()
    if run is None:
        raise HTTPException(status_code=404, detail="No such run")
    if not run.preview_path or not Path(run.preview_path).exists():
        return (run, None, None)
    preview_path = Path(run.preview_path)
    focus_xy = None
    with contextlib.suppress(OSError):
        focus_xy = _target_pixel_in_preview(run, entry, preview_path.read_bytes())
    return (run, preview_path, focus_xy)


@router.get("/api/targets/{safe}/stack-runs/{run_id}/zoom-clip/info")
def zoom_clip_info(safe: str, run_id: int, request: Request) -> dict[str, Any]:
    """Whether a share-ready zoom clip can be made of this run, and how it will be
    framed. Lightweight (no render): ``available`` is false — not a 404 — when the
    run has no stored preview, so the button simply doesn't appear.

    ``centred_on_target`` says whether the move aims at the plate-solved object or
    at the picture's own brightest part, so the UI can be honest about it in one
    short line rather than implying a solve it doesn't have."""
    _run, preview_path, focus_xy = _zoom_clip_inputs(request, safe, run_id)
    if preview_path is None:
        return {"available": False}
    from PIL import features

    from seestack.render.zoomclip import (
        CLIP_HOLD_SECONDS,
        CLIP_IN_SECONDS,
        CLIP_ZOOM,
        zoom_clip_size,
    )
    from seestack.wallpaper import png_size

    size = None
    with contextlib.suppress(OSError):
        size = png_size(preview_path.read_bytes())
    out = zoom_clip_size(*size) if size else None
    return {
        "available": True,
        "format": "webp" if features.check("webp") else "png",
        "centred_on_target": focus_xy is not None,
        "zoom": CLIP_ZOOM,
        # The whole loop: in, hold, and back out again.
        "seconds": round(2 * CLIP_IN_SECONDS + CLIP_HOLD_SECONDS, 1),
        "width": out[0] if out else None,
        "height": out[1] if out else None,
    }


@router.get("/api/targets/{safe}/stack-runs/{run_id}/zoom-clip")
async def zoom_clip(safe: str, run_id: int, request: Request) -> FileResponse:
    """Serve this run's looping zoom clip (WEBP, or APNG where Pillow has no WEBP),
    building and caching it on demand. 404 when the run has no stored preview."""
    run, preview_path, focus_xy = _zoom_clip_inputs(request, safe, run_id)
    if preview_path is None:
        raise HTTPException(status_code=404, detail="No preview for this run")
    basename = run.output_basename or "master"
    clip = await run_in_threadpool(_build_or_get_zoom_clip, preview_path,
                                   basename, focus_xy)
    if clip is None:
        raise HTTPException(status_code=404, detail="Could not build a zoom clip")
    media = _PROGRESS_MEDIA.get(clip.suffix, "application/octet-stream")
    return FileResponse(clip, media_type=media, filename=clip.name)


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
    suggestion (too little dynamic range) or the run is a display-space export /
    in-place Auto edit (its sliders are a no-op — nothing to anchor).

    It also answers *what saving here would cost*: ``processed_preview`` is true
    when the stored picture is an in-place "Process target" Auto edit, whose
    tone-mapped bytes a plain slider save replaces with a stretch of the linear
    FITS, and ``can_keep_processed`` is true when that run's recipe is still on
    disk, so the save can re-bake the processed picture instead (see
    ``save_stack_preview``'s ``keep_processed``). Both default false, which is
    every ordinary run.
    """
    lib, proj = deps.open_target_project(request, safe)
    try:
        run = next((r for r in proj.iter_stack_runs() if r.id == run_id), None)
        # One cheap meta read while the DB is open: is the recipe that made this
        # picture still there to re-bake?
        recipe_json = _saved_recipe_json(proj, run) if run is not None else None
    finally:
        proj.close()
        lib.close()
    if run is None:
        raise HTTPException(status_code=404, detail="No such run")
    fits_path = run.fits_path
    if not fits_path or not Path(fits_path).exists():
        raise HTTPException(status_code=404, detail="No FITS for this run to render")
    # An in-place Auto-edited run's preview is the recipe's tone-mapped result, not
    # an STF/asinh render of its (still-linear) FITS — an asinh suggestion can't
    # match it, so anchor nothing (Adjust falls back to its neutral defaults), the
    # same as a display-space export whose FITS is stamped.
    preview_ds = _preview_is_display_space(run.options_json)

    from seestack.edit.stretch import suggest_asinh_stretch
    from seestack.render.orient import NORTH_UP_MIN_DEG
    from seestack.render.thumbnail import load_stack_rgb, stack_north_up_deg
    from seestack.stack.output import EXPORT_AUTOSTRETCH_TARGET_BG

    def work() -> dict[str, Any]:
        # "North up" is a pure orientation fix from the run's own WCS, so it's
        # offered on a linear stack *or* a display-space export that kept its WCS;
        # only surface it when there's a real, more-than-trivial correction.
        angle = stack_north_up_deg(fits_path)
        north_up_deg = angle if (angle is not None and abs(angle) >= NORTH_UP_MIN_DEG) else None
        # Only a run whose *FITS is still linear* loses anything to a slider save:
        # an editor export's own preview is a plain render of its display-space
        # FITS, so re-rendering it reproduces the same picture.
        processed = bool(preview_ds and not _run_fits_is_display_space(run))
        warn = {"processed_preview": processed,
                "can_keep_processed": processed and bool(recipe_json)}
        if preview_ds:
            return {"stretch": None, "black": None, "north_up_deg": north_up_deg, **warn}
        rgb, display_space = load_stack_rgb(fits_path, max_width=1024)
        if display_space:
            return {"stretch": None, "black": None, "north_up_deg": north_up_deg, **warn}
        # Anchor the asinh sky target to the *export* grey (the value the History/
        # Gallery thumbnail the user just clicked is rendered at), not the editor's
        # brighter default, so opening Adjust starts on that thumbnail's look
        # instead of jumping ~2× brighter.
        sug = suggest_asinh_stretch(rgb, target_bg=EXPORT_AUTOSTRETCH_TARGET_BG)
        if sug is None:
            return {"stretch": None, "black": None, "north_up_deg": north_up_deg, **warn}
        return {"stretch": sug[0], "black": sug[1],
                "target_bg": EXPORT_AUTOSTRETCH_TARGET_BG,
                "north_up_deg": north_up_deg, **warn}

    return await run_in_threadpool(work)


def _run_fits_is_display_space(run: Any) -> bool:
    """True when the run's own master FITS is already tone-mapped (an editor
    export). Best-effort: an unreadable/absent FITS answers False, which is the
    linear assumption every caller here already makes."""
    from seestack.stack.output import fits_is_display_space

    if not run.fits_path or not Path(run.fits_path).exists():
        return False
    try:
        return bool(fits_is_display_space(run.fits_path))
    except Exception:  # noqa: BLE001 — a broken header just means "assume linear"
        return False


def _saved_recipe_json(proj: Any, run: Any) -> str | None:
    """This run's stored editor recipe, if it's there and parses — or ``None``.

    Deliberately **drift-blind**, unlike :func:`_auto_edit_recipe_json`: this
    answers "is there a recipe we could bake into a preview", not "does the
    stored preview show this recipe". Re-baking a drifted run *ends* the drift
    (the render and the look stamped beside it come from the same recipe, which
    is what the stamp means), so the drift is a reason to re-render, not to
    decline.
    """
    from webapp.routers.editor import RECIPE_META_PREFIX

    raw = proj.get_meta(f"{RECIPE_META_PREFIX}{run.id}")
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    if not isinstance(parsed, dict) or not isinstance(parsed.get("ops"), list):
        return None
    return raw


async def _save_processed_preview(
    request: Request, safe: str, run: Any, *, north_up: bool,
) -> dict[str, Any]:
    """The "keep my processed picture" half of ``save_stack_preview``.

    Re-bakes the run's stored **recipe** into its preview PNG — optionally rotated
    North-up — instead of rendering a plain stretch of the linear FITS. That makes
    the Adjust panel's one genuinely wanted control on an already-finished picture
    (rotation) stop costing the user the picture: before this, ticking "North up"
    and saving replaced their processed image — on the Target hero, in the Gallery,
    on the Library tile and possibly as the target's cover — with a flat stretch,
    silently, and only someone who knew to re-export from the editor could get it
    back.

    Writes exactly what ``pipeline._auto_edit_process_run`` writes for these runs
    (the recipe render, its crop, the baked-look stamp, the display-space marker),
    plus the rotation this save applied — so the picture, the marker and the stamp
    can't disagree afterwards. The stretch columns are cleared, because these bytes
    are not an asinh render and nothing should match against one.
    """
    from webapp.pipeline import _rendered_preview_crop
    from webapp.routers.editor import (
        AUTO_EDIT_BAKED_LOOK_PREFIX,
        render_run_display_array,
    )
    from seestack.edit.recipe import recipe_from_json
    from seestack.render.thumbnail import applied_north_up_deg, orient_preview_north_up
    from seestack.stack.output import _write_preview_png

    # Only a run whose picture *is* a processed one has anything to keep. On an
    # ordinary linear run this would silently turn a saved editor recipe into the
    # run's thumbnail and mark it display-space — a different feature (the
    # "unexported edit → finish" flow) reached by a path nothing offers. Refuse
    # rather than quietly do it.
    if not _preview_is_display_space(run.options_json):
        raise HTTPException(
            status_code=400,
            detail="This run's picture isn't a processed one — save a stretch instead",
        )
    lib, proj = deps.open_target_project(request, safe)
    try:
        recipe_json = _saved_recipe_json(proj, run)
        project_dir = proj.project_dir
    finally:
        proj.close()
        lib.close()
    if not recipe_json:
        raise HTTPException(
            status_code=400,
            detail="This run has no saved edit to re-apply — save a stretch instead",
        )
    recipe = recipe_from_json(recipe_json)
    preview_path = Path(run.preview_path)

    def work() -> tuple[str | None, float]:
        out = render_run_display_array(project_dir, run, recipe)
        # Measured on the *un-rotated* render, the way every consumer composes it
        # (crop the canvas-grid quantity first, then turn it).
        crop_json = _rendered_preview_crop(project_dir, run.id, recipe, out.shape[:2])
        _write_preview_png(preview_path, out, already_display=True)
        if not north_up:
            return crop_json, 0.0
        # Turn the bytes we just wrote rather than the array, so the rotation goes
        # through the one helper the share/download path uses — and record the
        # angle from the same rules, so the two can never disagree.
        rotated = orient_preview_north_up(preview_path.read_bytes(), run.fits_path)
        preview_path.write_bytes(rotated)
        return crop_json, applied_north_up_deg(run.fits_path)

    crop_json, north_up_deg = await run_in_threadpool(work)

    lib, proj = deps.open_target_project(request, safe)
    try:
        proj.set_stack_preview_stretch(run.id, None, None)
        proj.set_stack_preview_north_up(run.id, north_up_deg)
        proj.set_stack_preview_crop(run.id, crop_json)
        proj.set_run_preview_display_space(run.id)
        proj.set_meta(f"{AUTO_EDIT_BAKED_LOOK_PREFIX}{run.id}",
                      json.dumps(_recipe_look(recipe_json)))
    finally:
        proj.close()
        lib.close()
    return {"ok": True, "kept_processed": True, "stretch": None, "black": None,
            "north_up": north_up, "north_up_deg": north_up_deg}


@router.post("/api/targets/{safe}/stack-runs/{run_id}/preview")
async def save_stack_preview(
    safe: str, run_id: int, body: dict[str, Any], request: Request,
) -> dict[str, Any]:
    """Persist a stretch as the run's preview PNG.

    Re-renders from the FITS at the chosen stretch/black point and overwrites
    the run's ``preview_path`` so the new look shows everywhere the preview is
    used (history thumbnails and the Sky Map). ``north_up`` (default false)
    rotates the saved image so celestial North points up, matching what the user
    sees on screen when they save while the History "North up" toggle is on — a
    no-op when the run has no usable WCS.

    The rotation that was actually applied is recorded on the run, because the Sky
    map has to follow these pixels: without it the map placed the *un-rotated*
    canvas geometry (and an un-rotated coverage footprint) against a rotated
    picture, tilting the tile and putting its transparent gaps in the wrong place.

    ``keep_processed`` (default false — every existing client and every ordinary
    run is byte-for-byte unchanged) takes the other path for a run whose picture
    is an in-place "Process target" Auto edit: the preview is re-baked from that
    run's own stored recipe instead of from the sliders, so ticking "North up" on
    a finished picture rotates it rather than replacing it with a plain stretch.
    See :func:`_save_processed_preview`.
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

    north_up_req = bool(body.get("north_up", False))
    if bool(body.get("keep_processed", False)):
        return await _save_processed_preview(request, safe, run, north_up=north_up_req)

    try:
        stretch = _clamp(float(body.get("stretch", _STRETCH_DEFAULT)), _STRETCH_MIN, _STRETCH_MAX)
        black = _clamp(float(body.get("black", _BLACK_DEFAULT)), _BLACK_MIN, _BLACK_MAX)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400,
                            detail=f"stretch/black must be numbers: {exc}") from exc
    north_up = north_up_req

    from seestack.render.thumbnail import applied_north_up_deg, render_stack_png
    from seestack.stack.output import fits_is_display_space
    png = await run_in_threadpool(
        render_stack_png, run.fits_path,
        stretch=stretch, black=black, max_width=1024, north_up=north_up,
    )
    Path(run.preview_path).write_bytes(png)
    # The rotation the render actually applied — 0.0 when the toggle was off, when
    # the run has no WCS, or when the correction was sub-threshold. Always written
    # (never left alone), so re-saving *without* North up clears a rotation an
    # earlier save recorded rather than leaving the Sky map following a ghost.
    north_up_deg = (
        await run_in_threadpool(applied_north_up_deg, run.fits_path)
        if north_up else 0.0
    )

    # Record the saved stretch on the run so the "one frame vs your stack" reveal
    # renders its sub half through the *same* asinh curve (keeping the two halves
    # honestly comparable). A display-space export ignores the sliders (rendered
    # verbatim), so leave its columns NULL — the reveal self-hides for those runs.
    is_display = await run_in_threadpool(fits_is_display_space, run.fits_path)
    lib, proj = deps.open_target_project(request, safe)
    try:
        proj.set_stack_preview_stretch(
            run_id,
            None if is_display else stretch,
            None if is_display else black,
        )
        proj.set_stack_preview_north_up(run_id, north_up_deg)
        # This render comes straight off the master FITS, so it covers the whole
        # canvas — clear any border trim a previous "Process target" auto-edit
        # baked into the old bytes, exactly as the North-up angle above is always
        # written rather than left alone. A stale crop would have every surface
        # that lines up with the preview correcting for a trim that is gone.
        proj.set_stack_preview_crop(run_id, None)
        # ...and for the same reason, these bytes are no longer a recipe result.
        # Saving from Adjust replaces a "Process target" auto-edit's tone-mapped
        # preview with a plain stretch of the linear FITS (the recipe itself is
        # untouched and still reopens in the editor), so leaving the marker and the
        # baked-look stamp behind would have the reveal put its single sub through
        # an Auto recipe the picture beside it no longer shows — the same
        # disagreement the stamp exists to catch, reached without ever opening the
        # editor. Cleared together with the crop, on the same "always written,
        # never left alone" rule; a linear run is unaffected either way, and the
        # stretch recorded just above is what the reveal should match against now.
        if _preview_is_display_space(run.options_json) and not is_display:
            from webapp.routers.editor import AUTO_EDIT_BAKED_LOOK_PREFIX
            proj.set_run_preview_display_space(run_id, False)
            proj.delete_meta(f"{AUTO_EDIT_BAKED_LOOK_PREFIX}{run_id}")
    finally:
        proj.close()
        lib.close()
    return {"ok": True, "stretch": stretch, "black": black, "north_up": north_up,
            "north_up_deg": north_up_deg}


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


def _auto_edit_recipe_json(proj: Any, run: Any) -> str | None:
    """The editor recipe an **in-place "Process target" Auto edit** baked into this
    run's stored preview — or ``None`` when the run isn't one of those.

    This is what lets the reveal survive the one-click path. A "Process target" run
    keeps a **linear** FITS and rewrites only its preview PNG to the Auto recipe's
    result (``pipeline._auto_edit_process_run``), stamping ``preview_display_space``
    and storing the recipe under ``editor_recipe:<run_id>``. Given that recipe, the
    single sub can be rendered through the *same* ops, so the two halves of the
    reveal differ only in how many frames went in — a fairer comparison than the
    STF match a plain linear run gets, not a looser one.

    ``None`` (⇒ the reveal stays hidden, as before) for:

    * a genuine editor **export** — its FITS is itself display-space
      (``fits_is_display_space``), so there is no linear picture to reason about and
      the recipe on it, if any, describes a *second-round* edit of the export;
    * an ordinary linear run, which already has the honest STF/asinh match;
    * an auto-edited run whose recipe is missing or unreadable, where we'd be
      guessing at what its preview shows; and
    * an auto-edited run whose recipe has since **drifted** from the picture its
      preview shows — the user re-opened it, changed a parameter and saved, which
      rewrites the recipe but not the baked bytes. Rendering the sub through the new
      recipe would then differ from the stack half by an *edit* as well as by frame
      count, which is the one thing this comparison must never show, so the reveal
      stands down to hidden exactly as it does for a missing recipe.

    Like every other surface that reads this marker (see ``_unexported_edit``), it
    takes the stored recipe to *be* what the stored preview shows — which is what
    ``_auto_edit_process_run`` writes, in one step, for these runs — but only as far
    as the baked-look stamp it writes alongside them agrees. No stamp (a run
    auto-edited before it existed) means "can't tell", and the assumption stands.
    """
    from seestack.stack.output import fits_is_display_space

    if not _preview_is_display_space(run.options_json):
        return None
    if run.fits_path and Path(run.fits_path).exists() and fits_is_display_space(run.fits_path):
        return None
    from webapp.routers.editor import AUTO_EDIT_BAKED_LOOK_PREFIX, RECIPE_META_PREFIX

    raw = proj.get_meta(f"{RECIPE_META_PREFIX}{run.id}")
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    if not isinstance(parsed, dict) or not isinstance(parsed.get("ops"), list):
        return None
    if _baked_look_disagrees(
            proj.get_meta(f"{AUTO_EDIT_BAKED_LOOK_PREFIX}{run.id}"),
            _recipe_look(raw)):
        return None
    return raw


def _display_space_without_recipe(run: Any, recipe_json: str | None) -> bool:
    """True when this run's stored preview is tone-mapped and we have **no** way to
    put a single sub through the same processing — i.e. the reveal (and the
    before/after download, gated identically) must stay hidden.

    Falls to ``False`` for an in-place Auto edit once its recipe is in hand, which
    is what makes the reveal reachable on the one-click path."""
    from seestack.stack.output import fits_is_display_space

    if recipe_json:
        return False
    return _preview_is_display_space(run.options_json) or bool(
        run.fits_path and Path(run.fits_path).exists()
        and fits_is_display_space(run.fits_path)
    )


def _render_sub_through_recipe(src_path: str, pattern: str, recipe_json: str) -> bytes:
    """PNG bytes of one raw sub put through a saved editor recipe — the "before"
    half of the reveal on an auto-edited run. Threadpool-safe (pure inputs)."""
    import io

    import numpy as np
    from PIL import Image

    from seestack.edit.recipe import recipe_from_dict
    from webapp.routers.editor import render_sub_display_array

    recipe = recipe_from_dict(json.loads(recipe_json))
    out = render_sub_display_array(src_path, recipe, bayer_pattern=pattern,
                                   max_width=1024)
    u8 = (np.clip(np.nan_to_num(out), 0.0, 1.0) * 255).astype(np.uint8)
    buf = io.BytesIO()
    Image.fromarray(u8, mode="RGB").save(buf, format="PNG")
    return buf.getvalue()


@router.get("/api/targets/{safe}/stack-runs/{run_id}/one-sub-vs-stack")
def one_sub_vs_stack_info(safe: str, run_id: int, request: Request) -> dict[str, Any]:
    """Whether a "one frame vs your stack" reveal is available for this run, plus
    the plain-language caption fields the card fills in from the run's own data.

    A beginner drops hundreds of subs in and gets one clean picture, but never sees
    the *before* — this powers a read-only card that puts a single noisy sub next to
    the finished stack so they can see (and share) exactly what stacking bought them.

    ``available`` is ``false`` (not a 404, where the run exists) when the run has no
    stored preview to compare against, the target has no frame to render, or the run
    is a **display-space editor export** — its preview is a bespoke tone-mapped image
    a raw sub can't be honestly matched to (the noise-ratio endpoint already bails on
    the same runs), so the card self-hides rather than showing two mismatched tone
    curves. Every caption field is best-effort (``null`` when its datum is missing) so
    the card degrades to a shorter line rather than printing blanks.

    The **one-click "Process target"** run is the exception, and the reason this is
    worth more than its narrow gate suggests: its preview is a recipe result too,
    but its FITS stays linear and the recipe is stored on the run, so the sub can be
    put through that *same* recipe (``matched_by: "recipe"``). Without that, the app's
    most convincing moment was missing from the one journey a beginner is most likely
    to take. A plain linear run keeps the stretch match (``matched_by: "stretch"``).
    """
    lib, proj = deps.open_target_project(request, safe)
    try:
        run = next((r for r in proj.iter_stack_runs() if r.id == run_id), None)
        if run is None:
            raise HTTPException(status_code=404, detail="No such run")
        has_preview = bool(run.preview_path and Path(run.preview_path).exists())
        # A display-space *export* is tone-mapped verbatim with no linear picture
        # behind it; a raw sub can't be matched to it either way, so those runs
        # stay hidden. An in-place Auto edit is display-space too, but recoverable
        # — see _auto_edit_recipe_json.
        recipe_json = _auto_edit_recipe_json(proj, run) if has_preview else None
        display_space = _display_space_without_recipe(run, recipe_json)
        ref = _pick_reference_sub(proj) if (has_preview and not display_space) else None
        sub_exposure_s = ref.exposure_s if ref is not None else None
    finally:
        proj.close()
        lib.close()
    return {
        "available": has_preview and not display_space and ref is not None,
        "n_frames": run.n_frames_used,
        "sub_exposure_s": sub_exposure_s,
        "integration_s": run.total_exposure_s,
        # Additive: how the two halves were made comparable, so the card can say
        # "put through the same edit" where that is what actually happened.
        "matched_by": "recipe" if recipe_json else "stretch",
    }


@router.get("/api/targets/{safe}/stack-runs/{run_id}/reference-sub")
async def reference_sub_png(safe: str, run_id: int, request: Request) -> Response:
    """Render the run's representative single sub, processed to match the stack
    preview, as PNG — the "before" half of the one-frame-vs-stack reveal.

    Debayers the sharpest accepted frame and puts it through whatever produced the
    run's stored preview, so the only visible difference between this and the stack
    is noise/detail (never brightness):

      * a plain linear run — the identical export autostretch, or the run's saved
        asinh curve if History "Adjust" overwrote its preview;
      * an in-place "Process target" **Auto edit** — the run's own stored recipe
        (``_auto_edit_recipe_json``), so both halves carry identical processing.

    Runs in a threadpool so it never blocks the job worker.
    """
    lib, proj = deps.open_target_project(request, safe)
    try:
        run = next((r for r in proj.iter_stack_runs() if r.id == run_id), None)
        if run is None:
            raise HTTPException(status_code=404, detail="No such run")
        ref = _pick_reference_sub(proj)
        if ref is None:
            raise HTTPException(status_code=404, detail="No frame to render for this run")
        src = readable_frame_path(ref)
        if not src:
            raise HTTPException(status_code=404, detail="Frame file not found on disk")
        pattern = (ref.bayer_pattern or "RGGB").upper()
        if pattern not in _BAYER_PATTERNS:
            pattern = "RGGB"
        src_path = str(src)
        recipe_json = _auto_edit_recipe_json(proj, run)
        if _display_space_without_recipe(run, recipe_json):
            # The stack half is tone-mapped and we have no way to put a sub
            # through the same processing (a display-space export, or an
            # auto-edited run whose recipe is missing, unreadable, or has drifted
            # from the one its preview shows). The card already self-hides on
            # exactly these runs and the download beside it already 404s — say the
            # same thing here rather than serving a half that doesn't match.
            raise HTTPException(
                status_code=404,
                detail="This run's picture is an edited export, so a raw frame "
                       "can't be matched to it honestly.")
        # If the run's preview was re-saved with a custom asinh stretch (History
        # "Adjust"), render the sub through that same curve so the reveal's two
        # halves differ only in noise/detail — not a tone offset. Both columns are
        # NULL for the common default-STF preview, where we keep the STF render.
        stretch = run.preview_stretch
        black = run.preview_black
    finally:
        proj.close()
        lib.close()

    if recipe_json:
        png = await run_in_threadpool(
            _render_sub_through_recipe, src_path, pattern, recipe_json)
        return Response(content=png, media_type="image/png",
                        headers={"Cache-Control": "no-store"})

    from seestack.render.thumbnail import render_sub_preview

    png = await run_in_threadpool(
        render_sub_preview, src_path, bayer_pattern=pattern, max_width=1024,
        stretch=stretch, black=black,
    )
    return Response(content=png, media_type="image/png",
                    headers={"Cache-Control": "no-store"})


@router.get("/api/targets/{safe}/stack-runs/{run_id}/before-after.jpg")
async def before_after_jpeg(safe: str, run_id: int, request: Request,
                            width: int = 0) -> Response:
    """Download the reveal as one shareable picture: the representative single sub
    beside the finished stack, labelled, under a plain-language caption.

    The in-app reveal (``one-sub-vs-stack``) is the most convincing thing the app
    does — and it can't leave the app, so the one picture a non-astro friend
    actually understands ("this grainy frame → this clean photo, same little
    telescope") could only be screenshotted. This composes it on demand from the
    two renders that already exist: nothing is written to the library, exactly
    like the montage wall (``/api/gallery/montage.jpg``) and the recap poster.

    Gated **identically to the reveal** — 404 (rather than an unfair pairing) when
    the run has no stored preview, no frame to render, or is a display-space
    editor export whose bespoke tone curve a raw sub can't honestly match — so the
    download button self-hides on exactly the runs the card already hides on. That
    includes the in-place Auto edit, where "identically" now means *available*: the
    sub goes through the run's own recipe, like the reveal's left half.
    Composed in a threadpool, like every other render here, so it never blocks
    the job worker.
    """
    lib, proj = deps.open_target_project(request, safe)
    try:
        run = next((r for r in proj.iter_stack_runs() if r.id == run_id), None)
        if run is None:
            raise HTTPException(status_code=404, detail="No such run")
        entry = lib.find_target(safe)
        preview_path = run.preview_path
        if not preview_path or not Path(preview_path).exists():
            raise HTTPException(status_code=404, detail="No preview for this run")
        recipe_json = _auto_edit_recipe_json(proj, run)
        if _display_space_without_recipe(run, recipe_json):
            raise HTTPException(
                status_code=404,
                detail="This run's picture is an edited export, so a raw frame "
                       "can't be matched to it honestly.")
        ref = _pick_reference_sub(proj)
        if ref is None:
            raise HTTPException(status_code=404, detail="No frame to render for this run")
        src = readable_frame_path(ref)
        if not src:
            raise HTTPException(status_code=404, detail="Frame file not found on disk")
        pattern = (ref.bayer_pattern or "RGGB").upper()
        if pattern not in _BAYER_PATTERNS:
            pattern = "RGGB"
        src_path = str(src)
        # The run's own saved tone curve, exactly as `reference-sub` uses it, so
        # the two halves of the download differ only in noise/detail.
        stretch = run.preview_stretch
        black = run.preview_black
        name = (entry.name if entry is not None else None) or safe
        n_frames = run.n_frames_used
        integration_s = run.total_exposure_s
        sub_exposure_s = ref.exposure_s
        basename = run.output_basename
    finally:
        proj.close()
        lib.close()

    from seestack.beforeafter import (
        DEFAULT_WIDTH,
        before_after_caption,
        build_before_after,
        panel_labels,
    )

    asked = int(width) if width else DEFAULT_WIDTH

    def _compose() -> bytes:
        import io

        from PIL import Image

        from seestack.render.thumbnail import render_sub_preview

        if recipe_json:
            sub_png = _render_sub_through_recipe(src_path, pattern, recipe_json)
        else:
            sub_png = render_sub_preview(src_path, bayer_pattern=pattern,
                                         max_width=1024, stretch=stretch, black=black)
        with Image.open(io.BytesIO(sub_png)) as raw:
            before = raw.convert("RGB")
        with Image.open(preview_path) as stored:
            after = stored.convert("RGB")
        image = build_before_after(
            before, after,
            caption=before_after_caption(name, n_frames, sub_exposure_s,
                                         integration_s),
            labels=panel_labels(n_frames, sub_exposure_s),
            width=asked,
        )
        if image is None:  # pragma: no cover — both halves were just loaded
            raise HTTPException(status_code=404, detail="Nothing to compare")
        buf = io.BytesIO()
        image.save(buf, format="JPEG", quality=92)
        return buf.getvalue()

    data = await run_in_threadpool(_compose)
    return Response(
        content=data, media_type="image/jpeg",
        headers={"Content-Disposition":
                 f'attachment; filename="{basename}_before-after.jpg"'},
    )


# Both sides of the noise measurement are bounded to this square, taken from the
# centre of each image — enough background to estimate σ robustly, small enough
# that a giant mosaic master costs a patch rather than a canvas.
_NOISE_CROP_PX = 1024


def _crop_origin(h: int, w: int, size: int = _NOISE_CROP_PX) -> tuple[int, int]:
    """Top-left corner of the central ``size``² crop of an ``h``×``w`` image.

    Shared by the master's windowed read and the sub's in-memory crop so the two
    sides are measured over the *same* part of the field, whichever route the
    pixels arrived by."""
    return max(0, (h - size) // 2), max(0, (w - size) // 2)


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

    def _central_crop(rgb: np.ndarray, size: int = _NOISE_CROP_PX) -> np.ndarray:
        y0, x0 = _crop_origin(*rgb.shape[:2], size=size)
        return rgb[y0:y0 + size, x0:x0 + size]

    try:
        # Linear master (native res; NaN preserved for uncovered pixels). Read
        # **only the central crop** off the memory-mapped HDU: this endpoint is
        # fetched eagerly on every Target-page load and every finished-Jobs card,
        # and `getdata(...)` + `asarray(dtype=float32)` materialises the *whole*
        # master first (FITS is big-endian, so the dtype cast is a full copy and
        # byte-swap, not a view) — 1.8 GB of transient allocation for a 150 MP
        # mosaic on the RAM-capped NAS, to measure a 1024² patch. Slicing the
        # memmap first touches only the pages the crop covers (measured: 46 MB →
        # 0 MB peak on a 48 MB master). Same pixels, same ratio.
        with _fits.open(fits_path, memmap=True) as hdul:
            # First HDU carrying pixels — what `getdata` used to pick for us.
            # Touching `.data` on a memmapped HDU doesn't read it, so this scan
            # stays as cheap as the crop it's about to take.
            data = next((h.data for h in hdul if h.data is not None), None)
            if data is None:
                return None
            if data.ndim == 3:                  # (channels, H, W)
                y0, x0 = _crop_origin(data.shape[1], data.shape[2])
                arr = np.asarray(
                    data[:, y0:y0 + _NOISE_CROP_PX, x0:x0 + _NOISE_CROP_PX],
                    dtype=np.float32)
                stack_rgb = np.transpose(arr, (1, 2, 0))
                if stack_rgb.shape[2] == 1:
                    stack_rgb = np.repeat(stack_rgb, 3, axis=2)
                elif stack_rgb.shape[2] > 3:
                    stack_rgb = stack_rgb[..., :3]
            else:                               # 2-D mono → grey RGB
                y0, x0 = _crop_origin(data.shape[0], data.shape[1])
                arr = np.asarray(
                    data[y0:y0 + _NOISE_CROP_PX, x0:x0 + _NOISE_CROP_PX],
                    dtype=np.float32)
                stack_rgb = np.stack([arr, arr, arr], axis=-1)

        # Linear sub: debayer at native res (no decimation), same central crop.
        sub_raw, info = load_seestar_raw(sub_path, debayer=False, out_dtype=np.float32)
        sub_rgb = bilinear_debayer(
            sub_raw, pattern=(pattern or info.bayer_pattern or "RGGB"))
        sub_rgb = _central_crop(sub_rgb)
    except Exception:  # noqa: BLE001 — best-effort; the badge just omits the number
        return None

    return noise_ratio(sub_rgb, stack_rgb)


# Where the measured noise-reduction ratio is remembered, per stack run. The
# number is a pure function of two immutable things — the finished master and
# the representative sub it is measured against — but the endpoint that serves
# it is fetched **eagerly** on every Target-page load and on every finished
# "Process target" card, and each miss reloads the master's crop *and* debayers
# a full native-resolution sub. On the RAM-capped NAS that is real disk churn
# for a number that never changes, so the first measurement is stamped here and
# every later view reads it. Registered in ``webapp.run_meta`` so deleting the
# run takes its stamp with it. See :func:`_cached_noise_ratio`.
NOISE_RATIO_META_PREFIX = "noise_ratio:"

# Bump when the *meaning* of the stored payload changes, so an old stamp is
# re-measured rather than misread.
_NOISE_RATIO_CACHE_VERSION = 1


def _noise_ratio_fingerprint(fits_path: str, ref_id: int | None) -> dict[str, Any] | None:
    """What the stored ratio was measured *from*, so a stale stamp can't be served.

    The run row is immutable, but the two inputs are addressed by path: the
    master could be rewritten in place by some future flow, and
    :func:`_pick_reference_sub` picks the *sharpest accepted* sub, which changes
    the moment the user accepts or rejects a frame. Both are cheap to
    fingerprint (one ``stat`` and an id), so the cache is exact rather than
    merely probable. ``None`` when the master can't be stat-ed — then nothing is
    cached and the measurement runs as before.
    """
    try:
        st = os.stat(fits_path)
    except OSError:
        return None
    return {
        "v": _NOISE_RATIO_CACHE_VERSION,
        "ref": int(ref_id) if ref_id is not None else None,
        "mtime_ns": int(st.st_mtime_ns),
        "size": int(st.st_size),
    }


def _cached_noise_ratio(proj: Any, run_id: int,
                        fingerprint: dict[str, Any]) -> tuple[bool, float | None]:
    """``(hit, ratio)`` for a stamped measurement matching ``fingerprint``.

    ``hit`` is False on a missing, unparsable or stale stamp — including one
    written against a different master or a different representative sub — so a
    miss always falls through to a fresh measurement. A stamped ``null`` (an
    edited/display-space export, or an unmeasurable image) is a real hit: it is
    just as stable as a number, and re-deriving it costs the same FITS open.
    """
    raw = proj.get_meta(f"{NOISE_RATIO_META_PREFIX}{run_id}")
    if not raw:
        return False, None
    try:
        stamp = json.loads(raw)
    except (ValueError, TypeError):
        return False, None
    if not isinstance(stamp, dict):
        return False, None
    if any(stamp.get(k) != v for k, v in fingerprint.items()):
        return False, None
    ratio = stamp.get("ratio")
    if ratio is None:
        return True, None
    try:
        return True, float(ratio)
    except (TypeError, ValueError):
        return False, None


@router.get("/api/targets/{safe}/stack-runs/{run_id}/one-sub-vs-stack/noise")
async def one_sub_vs_stack_noise(safe: str, run_id: int, request: Request) -> dict[str, Any]:
    """The concrete "stacking cut your noise ~N×" number for the reveal card.

    Measures the background-noise σ of a representative single sub against the
    finished linear master and returns their ratio (``{"ratio": float|null}``) —
    which lands near √(n_frames) on a healthy weighted-mean stack. Its own lazy,
    best-effort endpoint so the info card stays cheap: any missing datum, an
    edited/display-space export, or an unmeasurable image returns ``null`` and the
    badge simply omits the number.

    The first measurement for a run is **remembered** (``NOISE_RATIO_META_PREFIX``,
    fingerprinted on the master and the representative sub) so the repeat views
    this endpoint actually gets don't reload the master and re-debayer a sub for
    a number that cannot have changed. The stamp is a cache, never a source of
    truth: any mismatch, or a project that can't be written, simply measures.
    """
    lib, proj = deps.open_target_project(request, safe)
    try:
        run = next((r for r in proj.iter_stack_runs() if r.id == run_id), None)
        if run is None:
            raise HTTPException(status_code=404, detail="No such run")
        fits_path = run.fits_path
        ref = _pick_reference_sub(proj)
        ref_id = getattr(ref, "id", None) if ref is not None else None
        src = readable_frame_path(ref) if ref is not None else None
        pattern = (ref.bayer_pattern or "RGGB").upper() if ref is not None else "RGGB"
        if pattern not in _BAYER_PATTERNS:
            pattern = "RGGB"
        fingerprint = (
            _noise_ratio_fingerprint(fits_path, ref_id) if fits_path else None
        )
        if fingerprint is not None:
            hit, cached = _cached_noise_ratio(proj, run_id, fingerprint)
            if hit:
                return {"ratio": cached}
    finally:
        proj.close()
        lib.close()

    if (not fits_path or not Path(fits_path).exists()
            or not src or not Path(src).exists()):
        return {"ratio": None}

    ratio = await run_in_threadpool(_measure_noise_ratio, str(fits_path), str(src), pattern)
    if fingerprint is not None:
        # Best-effort stamp — a read-only or busy project must still serve the
        # number it just measured.
        with contextlib.suppress(Exception):
            wlib, wproj = deps.open_target_project(request, safe)
            try:
                wproj.set_meta(
                    f"{NOISE_RATIO_META_PREFIX}{run_id}",
                    json.dumps({**fingerprint, "ratio": ratio}),
                )
            finally:
                wproj.close()
                wlib.close()
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

    # The other half of the weighting story: quality weighting was on, but the
    # method that actually ran (order-statistic min/max) combines by rank and
    # ignores per-frame weights, so WGTMODE above is deliberately absent. Without
    # this the panel can only stay silent, which reads as "weighting was off" —
    # the same picture for two very different situations.
    weighting_skipped: dict[str, Any] | None = None
    if "WGTSKIP" in header:
        weighting_skipped = {"reason": str(header["WGTSKIP"])}
        with contextlib.suppress(KeyError, TypeError, ValueError):
            weighting_skipped["auto"] = bool(header["WGTSKAUT"])
        with contextlib.suppress(KeyError, TypeError, ValueError):
            weighting_skipped["min_frames"] = int(header["WGTSKMIN"])

    # Photometric-normalization summary (present only on normalized stacks), parsed
    # the same way so the panel can show a single "N frames gain-matched · scales
    # lo–hi" line and the user can trust the normalization did something. ``auto``
    # says the mosaic path enabled it rather than the user — a run nobody ticked a
    # box for should still be able to explain itself.
    photometric: dict[str, Any] | None = None
    if "PHOTNORM" in header:
        photometric = {"mode": str(header["PHOTNORM"])}
        for hk, k in (("PHOTNADJ", "n_adjusted"),):
            with contextlib.suppress(KeyError, TypeError, ValueError):
                photometric[k] = int(header[hk])
        with contextlib.suppress(KeyError, TypeError, ValueError):
            photometric["auto"] = bool(header["PHOTAUTO"])
        for hk, k in (("PHOTMIN", "min"), ("PHOTMAX", "max"), ("PHOTMED", "median")):
            with contextlib.suppress(KeyError, TypeError, ValueError):
                photometric[k] = float(header[hk])
        # Why it ran, and over how many mosaic panels — a mosaic normalizes
        # itself (the user never ticked a box), and each panel is gain-matched
        # against its own subs rather than against the other panels.
        with contextlib.suppress(KeyError, TypeError, ValueError):
            photometric["auto"] = bool(header["PHOTAUTO"])
        with contextlib.suppress(KeyError, TypeError, ValueError):
            photometric["n_panels"] = int(header["PHOTPANL"])

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
        # …and whether this run also kept the *spatial* record of those drops, so
        # the picture can offer "show me what was removed". Only True when the
        # sibling map is actually there: the run asked for it (``REJMAP``) *and*
        # the file survived (a hand-tidied output dir, a restored-from-backup run).
        # Absent on every run recorded before the feature, which reads as no
        # overlay — the same as False, without claiming the run refused one.
        if header.get("REJMAP"):
            rejection["has_map"] = rejection_map_path_for(fits_path).exists()

    # "Your picture came out slightly less zoomed-in" — an unattended run whose
    # drizzle canvas didn't fit the memory budget and was stepped down to the
    # largest super-resolution scale that did, instead of refusing to make a
    # picture at all (``stacker`` stamps DRZSCLAD/DRZSCLRQ). Nobody was watching
    # the job that decided it, so this is the only place the owner can learn why
    # last night's image is a different size from the one before. Absent — and the
    # line omitted — on every run that fitted, which is all of them on a healthy
    # box.
    drizzle_degraded: dict[str, Any] | None = None
    if "DRZSCLAD" in header:
        drizzle_degraded = {"reason": "memory"}
        for hk, k in (("DRZSCLAD", "applied"), ("DRZSCLRQ", "requested")):
            with contextlib.suppress(KeyError, TypeError, ValueError):
                drizzle_degraded[k] = float(header[hk])
        if "applied" not in drizzle_degraded:
            drizzle_degraded = None

    # Frame-accounting summary (present on stacks recorded once the stacker began
    # stamping it): how many subs it attempted to combine and how many couldn't be
    # aligned. Lets the panel honestly report "1,850 of 2,000 subs combined; 150
    # couldn't be aligned" and flag a large align-failure fraction (usually mixed
    # targets / bad plate-solves). Omitted on older masters that lack the cards.
    frame_accounting: dict[str, Any] | None = None
    if "NOFFERED" in header:
        frame_accounting = {}
        for hk, k in (("NOFFERED", "n_offered"), ("NALIGNFL", "n_align_failed"),
                      ("NUNREAD", "n_unreadable"),
                      ("NREADERR", "n_read_errors"),
                      ("NREADREC", "n_read_recovered"),
                      ("NROUGHAL", "n_roughly_aligned"),
                      # How far sub-pixel refine reached: how many reference
                      # patches the run built (one per mosaic panel that earned
                      # one) and how many contributing subs still fell outside
                      # all of them, so a mosaic owner can read the reach off the
                      # run rather than infer it. Absent on older masters.
                      ("NREFPANL", "n_refine_patches"),
                      ("NREFSKIP", "n_refine_out_of_reach")):
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
    # Recorded (not inferred) reasons this run dropped a saved calibration pick.
    # Stronger evidence than ``calibration_advice``, which can only re-derive a
    # likely cause from the library — and it's the only thing that knows about a
    # master *deleted* since it was saved. Reported even when the run *is*
    # calibrated: a bound flat doesn't excuse a silently-dropped dark.
    calibration_skipped = _run_calibration_skipped(request, safe, run_id)
    # Mismatches in a master this run *did* apply — the opposite failure to
    # ``calibration_skipped`` and invisible without this: the picture looks
    # calibrated (CALSTAT is stamped) while a wrong-exposure dark quietly
    # over-subtracts on every frame.
    calibration_warnings = _run_calibration_warnings(request, safe, run_id)
    return {"run_id": run_id, "integration_s": integration_s,
            "n_frames": n_frames, "weighting": weighting,
            "weighting_skipped": weighting_skipped,
            "photometric": photometric, "dark_scaling": dark_scaling,
            "rejection": rejection, "frame_accounting": frame_accounting,
            "drizzle_degraded": drizzle_degraded,
            "auto_edit": auto_edit, "sky_cast": sky_cast,
            "color_cal": color_cal,
            "calibration_advice": calibration_advice,
            "calibration_skipped": calibration_skipped,
            "calibration_warnings": calibration_warnings,
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
            masters, exposure_s=exposure_s, gain=gain, sensor_temp_c=sensor_temp_c,
            width_px=calibration.modal_dim([f.width_px for f in frames]),
            height_px=calibration.modal_dim([f.height_px for f in frames]))
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


#: Long-edge ceiling for the *shared* picture (the JPEG behind Share / Download
#: JPEG / the keepsake / "with scale & compass"). Big enough that a post or a
#: 6×4 print is sharp on any modern screen, small enough that a share stays a
#: quick render and a messaging-app-friendly file — the stored 1024 px preview it
#: replaces is neither.
SHARE_JPEG_MAX_LONG_EDGE = 2560


def _native_picture_source(run: Any, preview_png: bytes, baked_north_up: float,
                           needed_long_edge: int) -> bytes | None:
    """A **native-resolution** render of the same picture the stored preview shows,
    up to ``needed_long_edge`` px — or ``None`` to use the stored preview bytes as
    before.

    The stored preview is capped at 1024 px
    (:data:`~seestack.render.thumbnail.PREVIEW_MAX_WIDTH`), which is the resolution
    of every picture this app hands over: the wallpaper cropped it (a ~470 px-wide
    lock screen for a 1170 px phone) and the share JPEG re-encoded it. The
    full-resolution pixels are right there in the run's FITS, and
    :func:`~seestack.render.thumbnail.render_preview_png_full_res` is the renderer
    that already reproduces the stored preview's own look at a chosen size (it is
    what the "Full-res PNG" download serves), so each caller asks it for exactly
    the pixels it needs — decimated *during* the FITS load, so the memory cost is
    bounded by the request, not by the canvas.

    Declines — leaving the caller bit-for-bit as it was — whenever the render
    could show a *different* picture from the one on screen:

    * a preview a past "Adjust → North up → Save" baked a rotation into (the FITS
      grid is the un-rotated one, and matching a baked angle is the North-up
      view's question, not this one);
    * a "Process target" run, whose preview is a display-space auto-edit that only
      the saved recipe can reproduce (the full-res render of *that* is a whole
      editor pipeline at native size — worth it for an explicit "native size"
      download, not yet for a one-tap share: see the backlog follow-on);
    * a preview that shows only part of the canvas (an auto-crop border trim);
    * a run with no readable FITS, or one whose canvas is no bigger than the
      preview already is — where there is nothing to gain.
    """
    from seestack.previewcrop import parse_preview_crop
    from seestack.render.thumbnail import render_preview_png_full_res
    from seestack.wallpaper import png_size

    if baked_north_up:
        return None
    if _preview_is_display_space(run.options_json):
        return None
    crop = parse_preview_crop(run.preview_crop_json)
    if crop is not None:
        return None                       # a trimmed preview isn't the whole canvas
    fits_path = run.fits_path
    if not fits_path or not Path(fits_path).exists():
        return None
    size = png_size(preview_png)
    if size is None:
        return None
    preview_long = max(size)
    # Cheap gate before any render: the canvas the preview came from is recorded on
    # the run, so a stack that never had more pixels than its preview is skipped
    # without touching the FITS.
    canvas = [d for d in (run.canvas_w, run.canvas_h) if d]
    if canvas and max(canvas) <= preview_long:
        return None
    needed = int(needed_long_edge)
    if needed <= preview_long:
        return None
    try:
        png = render_preview_png_full_res(
            fits_path, max_long_edge=needed,
            stretch=run.preview_stretch, black=run.preview_black)
    except Exception:  # noqa: BLE001 — a broken FITS just falls back to the preview
        return None
    rendered = png_size(png)
    if rendered is None or max(rendered) <= preview_long:
        return None                       # no more pixels than we already had
    return png


@router.get("/api/targets/{safe}/stack-runs/{run_id}/wallpaper")
def download_wallpaper(safe: str, run_id: int, request: Request,
                       aspect: str = "phone", north_up: bool = False) -> Response:
    """Crop + size the finished stack preview into a ready-to-set wallpaper.

    ``aspect`` is one of ``phone`` / ``desktop`` / ``square``. The picture is
    cropped to that shape centred on the plate-solved target (falling back to the
    image centre when the run has no WCS or the target has no known position),
    downscaled to a sane device resolution without upsampling, and returned as a
    share-friendly JPEG. Its source is a native-resolution re-render of the run's
    own FITS where one can be made faithfully (see
    :func:`_wallpaper_native_source`) — the stored preview is capped at 1024 px,
    which is a third of a phone screen — and the stored preview bytes otherwise.
    ``north_up`` first rotates the picture so celestial North
    points up (like every reference photo of the object), using the run's own WCS —
    a no-op when the run has no WCS or the correction is trivial, so the ordinary
    request is byte-for-byte unchanged. Read-only: nothing on disk changes.

    Registered *before* the ``/{kind}`` artifact route below so the literal
    ``wallpaper`` path segment isn't swallowed as an artifact kind.
    """
    from seestack.render.orient import NORTH_UP_MIN_DEG
    from seestack.render.thumbnail import orient_preview_north_up, stack_north_up_deg
    from seestack.wallpaper import (
        WALLPAPER_PRESETS,
        png_size,
        render_wallpaper_jpeg,
        rotate_point_north_up,
        wallpaper_source_long_edge,
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
    # What the stored bytes already carry: History's "Adjust → North up → Save"
    # overwrites the preview with a rotated render and records the angle. Both
    # halves below map from the FITS grid, so neither may assume the stored
    # preview is still on it.
    baked_north_up = baked_north_up_deg(run)
    # A wallpaper wants device-resolution pixels, and the stored preview is capped
    # at 1024 px — so where the same picture can be re-rendered from the run's own
    # FITS at the size the crop needs, that is the source instead. Declines to
    # `None` (and everything below reads the stored bytes exactly as before)
    # whenever the render could differ from the picture on screen.
    prev_size = png_size(preview)
    native = _native_picture_source(
        run, preview, baked_north_up,
        wallpaper_source_long_edge(prev_size[0], prev_size[1], preset),
    ) if prev_size else None
    if native is not None:
        preview = native
    # Locate the target in the preview grid from the run's own WCS; None → centre.
    # Shared with the zoom clip, which has to frame on the identical point.
    # Measured against whichever bytes won above — both are the same picture on the
    # same grid, so only the scale differs.
    target_px = _target_pixel_in_preview(run, entry, preview)

    # North-up rotates the picture *and* moves the target pixel, so re-centre the
    # crop on the rotated position. Only the rotation still *missing* from the
    # stored bytes is applied — turning a preview a past save already oriented
    # would share it 180° from the picture on screen.
    if north_up and run.fits_path and Path(run.fits_path).exists():
        try:
            total = stack_north_up_deg(run.fits_path)
            total = 0.0 if total is None or abs(total) < NORTH_UP_MIN_DEG else total
            remaining = total - baked_north_up
            if abs(remaining) >= NORTH_UP_MIN_DEG:
                size = png_size(preview)
                preview = orient_preview_north_up(
                    preview, run.fits_path, already_deg=baked_north_up)
                if target_px is not None and size is not None:
                    target_px = rotate_point_north_up(
                        target_px[0], target_px[1], size[0], size[1], remaining)
        except Exception:  # noqa: BLE001 — a broken FITS just yields the un-oriented wallpaper
            pass

    data = render_wallpaper_jpeg(preview, preset, target_px)
    filename = f"{run.output_basename}_{aspect}_wallpaper.jpg"
    return Response(
        content=data, media_type="image/jpeg",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/api/targets/{safe}/stack-runs/{run_id}/{kind}")
def download_stack_run(safe: str, run_id: int, kind: str, request: Request,
                       north_up: bool = False, nameplate: bool = False,
                       keepsake: bool = False, scale: bool = False,
                       label_objects: bool = False) -> Response:
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
        # What the *stored bytes* already carry: History's "Adjust → North up →
        # Save" overwrites the preview with a rotated render and records the
        # angle. Everything below is measured against the FITS grid, so it has to
        # start from this rather than assume the preview is the un-rotated one.
        baked_north_up = baked_north_up_deg(run)
        # This is the picture people actually *share* — posted, sent to family,
        # printed 6×4 — and it was a re-encode of the 1024 px preview. Where the
        # same picture can be re-rendered from the run's own master it is served at
        # share resolution instead; `None` keeps the stored bytes, exactly as
        # before. Everything baked on below (the marks, the caption, the matte) is
        # sized as a *fraction* of the picture, so all of it scales with this.
        native = _native_picture_source(run, preview, baked_north_up,
                                        SHARE_JPEG_MAX_LONG_EDGE)
        if native is not None:
            preview = native
        # The width the scale bar is measured against: the bar's length is a
        # *fraction* of the picture's width, and a rotate-with-expand grows the
        # canvas without changing the pixel scale, so it must be the width of the
        # picture *before* any North-up turn — including one a past save baked in.
        # Only paid for when marks were actually asked for.
        preview_width = (
            _unrotated_preview_width(preview, run.fits_path, baked_north_up)
            if scale else 0
        )
        # How far the pixels the marks are drawn on sit from the FITS grid, so the
        # rose can follow them. Not "how far this request turned them": a run
        # saved North-up arrives already turned, and its rose was wrong even
        # without `north_up` asked for.
        applied_north_up = baked_north_up
        # north_up rotates the shared picture so celestial North points up (like
        # reference photos of the object), using the run's own WCS — a no-op (the
        # bytes are returned untouched) when the run has no WCS, when the
        # correction is trivial, or when a past save already turned them exactly
        # that far, so the ordinary download is byte-for-byte unchanged.
        if north_up:
            fits_path = run.fits_path
            if fits_path and Path(fits_path).exists():
                from seestack.render.thumbnail import (
                    applied_north_up_deg,
                    orient_preview_north_up,
                    stack_north_up_deg,
                )
                try:
                    preview = orient_preview_north_up(
                        preview, fits_path, already_deg=baked_north_up)
                    # After that call the bytes sit at the run's *total* North-up
                    # correction, however much of it a past save had already
                    # baked in — unless there is no usable WCS to compute one, in
                    # which case they keep exactly what the save left.
                    if stack_north_up_deg(fits_path) is not None:
                        applied_north_up = applied_north_up_deg(fits_path)
                except Exception:  # noqa: BLE001 — a broken FITS just shares the un-oriented preview
                    pass
        # nameplate bakes the same tasteful acquisition footer the editor share
        # export offers (target · integration · date · gear) onto this direct
        # download — drawn last so it stays at the foot of a north-up-oriented
        # image. Best-effort provenance: a field it can't read is simply omitted,
        # and an empty nameplate is a clean no-op, so the default download is
        # byte-for-byte unchanged.
        # keepsake frames the picture on a dark matte with the same facts set
        # *beneath* it — the print-and-post variant, where nameplate draws them
        # as a bar over the picture. Both read the same provenance; which one
        # wins when both are asked for is `png_bytes_to_jpeg`'s rule (keepsake,
        # so the caption is never drawn twice), stated in one place rather than
        # re-derived here.
        plate = None
        if nameplate or keepsake:
            plate = pipeline._nameplate_fields(
                run.fits_path or "", entry, run,
                deps.get_settings(request).site_lon)
        # scale bakes the two marks every published astrophoto carries — a scale
        # bar and a North/East rose — along the *top* edge, from the run's own
        # solved WCS. They layer under the caption variants above (the caption
        # zone is the bottom edge), and a run with no usable WCS draws nothing,
        # so the plain download stays byte-for-byte unchanged.
        marks = None
        if scale:
            marks = _sky_marks_for_run(run.fits_path, preview_width,
                                       applied_north_up,
                                       parse_preview_crop(run.preview_crop_json))
        # label_objects bakes the named catalog objects in the field onto the
        # shared picture — the same pins and names the Target page draws on
        # screen, which otherwise vanish the moment the file leaves the app. It
        # refuses (draws nothing) on a picture whose geometry no longer matches
        # the grid the pins were measured on; see _object_labels_for_run.
        labels = None
        if label_objects:
            labels = _object_labels_for_run(
                run.fits_path, applied_north_up,
                parse_preview_crop(run.preview_crop_json))
        data = png_bytes_to_jpeg(
            preview,
            nameplate=plate if nameplate else None,
            keepsake=plate if keepsake else None,
            sky_marks=marks,
            object_labels=labels,
        )
        # Each baked-on variant carries its own filename so saving two of them
        # can't have one silently overwrite the other in the downloads folder.
        suffix = ("_keepsake" if keepsake
                  else ("_labelled" if label_objects
                        else ("_scale" if scale else "")))
        filename = f"{run.output_basename}{suffix}.jpg"
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
    if kind == "preview" and north_up:
        # Preview the North-up turn on the *stored* bytes, without a live render.
        # History's Adjust panel needs this on a "Process target" run: there the
        # picture on disk is a processed one, so swapping it for a render of the
        # linear master just to show which way up it would be shows a picture
        # neither Save button writes. Nothing on disk changes — the rotation is
        # applied to a copy on the way out — so the bare URL every other surface
        # embeds is byte-for-byte unchanged, and FITS/TIFF still never rotate.
        from seestack.render.thumbnail import orient_preview_north_up

        data = Path(path).read_bytes()
        fits_path = run.fits_path
        if fits_path and Path(fits_path).exists():
            # A broken FITS just serves the stored bytes, un-turned — the same
            # degrade the JPEG path takes for the same reason.
            with contextlib.suppress(Exception):
                data = orient_preview_north_up(
                    data, fits_path, already_deg=baked_north_up_deg(run))
        return Response(
            content=data, media_type=media,
            headers={
                "Cache-Control": "no-cache",
                "Content-Disposition": f'attachment; filename="{filename}"',
            },
        )
    # The preview PNG is regenerated *in place* (same path) by "Save as preview"
    # and the Process-target auto-edit, but every gallery/dashboard/compare
    # surface embeds it at the bare, unversioned URL. Without an explicit
    # Cache-Control, FileResponse sends only ETag/Last-Modified, so a browser
    # applies RFC 9111 heuristic freshness (~10% of file age — up to a day on an
    # old stack) and keeps showing the pre-regeneration pixels even after a
    # reload. `no-cache` forces a cheap conditional revalidation (a 304 when the
    # bytes are unchanged, fresh bytes the moment they change) so a re-saved
    # preview appears immediately everywhere. FITS/TIFF are immutable per run, so
    # they keep the default (cacheable) behaviour.
    headers = {"Cache-Control": "no-cache"} if kind == "preview" else None
    return FileResponse(
        path, media_type=media,
        filename=filename if download else None,
        headers=headers,
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
    from seestack.edit.proxy import clear_proxy
    from webapp.routers.storage import purge_stack_run
    from webapp.run_meta import delete_run_meta

    lib, proj = deps.open_target_project(request, safe)
    try:
        run = next((r for r in proj.iter_stack_runs() if r.id == run_id), None)
        if run is not None:
            # Files, row, editor proxy and every per-run annotation, in one place
            # (shared with "Prune old stacks" so the two can't drift).
            purge_stack_run(proj, run)
        else:
            # No such row — still drop anything an earlier partial delete left.
            proj.delete_stack_run(run_id)
            clear_proxy(Path(proj.project_dir), run_id)
            delete_run_meta(proj, run_id)
    finally:
        proj.close()
        lib.close()
    return {"deleted": run_id}
