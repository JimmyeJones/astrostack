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

from seestack.io.project import readable_frame_path
from seestack.stackhealth import seam_verdict
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
) -> dict[str, Any]:
    """Dry-run sizing for a stack: output canvas + estimated peak memory,
    computed without stacking, so the Stack form can warn *before* a run is
    submitted and refused for OOM (e.g. "Drizzle ×2 → 7680×4320, ≈2.1 GB peak,
    over the ~1.4 GB budget").

    Only the sizing-affecting knobs are query params: the canvas ones (drizzle /
    scale / reject / canvas mode) plus the min/max-reject knobs, because extra
    outlier passes hold ``2k`` extra canvas planes the run-time guard charges — so
    passing them keeps the pre-submit peak honest for a k>1 reject and lets the
    over-budget fix offer "drop the extra passes". Returns 422 (not 500) when
    there's nothing solved to size yet, with the same guidance ``run_stack``
    gives."""
    from seestack.stack.stacker import StackOptions, estimate_stack

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
    from webapp.routers.editor import EXPORTED_RECIPE_META_PREFIX, RECIPE_META_PREFIX

    lib, proj = deps.open_target_project(request, safe)
    try:
        runs = list(proj.iter_stack_runs())
        # The pinned "cover" run (library-level), so the History card can mark it.
        entry = lib.find_target(safe)
        cover_id = entry.cover_stack_run_id if entry is not None else None
        # Two small meta reads per run, so every surface that shows a run's
        # picture can tell an un-exported saved edit from a finished one (see
        # ``_unexported_edit``): the saved recipe, and the one an export of this
        # run already rendered. Both live in the same already-open DB.
        unexported = {
            r.id: _unexported_edit(
                r.options_json,
                proj.get_meta(f"{RECIPE_META_PREFIX}{r.id}"),
                proj.get_meta(f"{EXPORTED_RECIPE_META_PREFIX}{r.id}"),
            )
            for r in runs
        }
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
            stack_fwhm_px=r.stack_fwhm_px,
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


def _unexported_edit(options_json: str | None, recipe_json: str | None,
                     exported_recipe_json: str | None = None) -> bool:
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
    again — that second-round edit is as invisible as the first one was."""
    look = _recipe_look(recipe_json)
    if not look:
        # No recipe, unreadable, or every op disabled — nothing unfinished.
        return False
    opts = _parse_options(options_json)
    if opts.get("preview_display_space"):
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
    download matches the preview the user clicked."""
    from webapp.routers.editor import RECIPE_META_PREFIX

    lib, proj = deps.open_target_project(request, safe)
    try:
        run = next((r for r in proj.iter_stack_runs() if r.id == run_id), None)
        if run is None or not run.fits_path or not Path(run.fits_path).exists():
            raise HTTPException(
                status_code=404,
                detail="No FITS for this run to render at full resolution")
        basename, fits_path = run.output_basename, run.fits_path
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

    if recipe_dict is not None:
        png = await run_in_threadpool(
            pipeline.render_run_recipe_fullres_png, fits_path, recipe_dict,
            max_long_edge=_FULL_RES_PNG_MAX_LONG_EDGE, north_up=bool(north_up),
        )
    else:
        from seestack.render.thumbnail import render_preview_png_full_res
        png = await run_in_threadpool(
            render_preview_png_full_res, fits_path,
            max_long_edge=_FULL_RES_PNG_MAX_LONG_EDGE, north_up=bool(north_up),
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


def _arcsec_per_px(wcs) -> float | None:  # noqa: ANN001
    """The local plate scale (arcsec/px) of a run's celestial WCS — the mean of
    the two axis scales, which is exact for the square, unrotated Seestar grid
    and a sane average for a mosaic canvas. ``None`` when there is no usable WCS
    or the scale can't be measured, so every caller can omit its answer cleanly
    rather than working from a made-up number."""
    if wcs is None:
        return None
    try:
        from astropy.wcs.utils import proj_plane_pixel_scales

        scales_deg = proj_plane_pixel_scales(wcs)  # deg/px per axis
        scale = float(sum(scales_deg) / len(scales_deg)) * 3600.0
    except Exception:  # noqa: BLE001 — a degenerate WCS just means "no answer"
        return None
    return scale if scale > 0 else None


def _scale_bar_from_wcs(wcs, width: int, height: int):  # noqa: ANN001, ANN202
    """A :class:`~seestack.scalebar.ScaleBar` for a run from its celestial WCS
    and :func:`_arcsec_per_px`, via the pure :func:`scale_bar_for`. Returns
    ``None`` when there is no usable WCS or scale, so the caller omits the scale
    bar cleanly."""
    from seestack.scalebar import scale_bar_for

    if wcs is None or width <= 0:
        return None
    arcsec_per_px = _arcsec_per_px(wcs)
    if arcsec_per_px is None:
        return None
    return scale_bar_for(arcsec_per_px, width, height)


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

    def work() -> dict[str, Any] | None:
        from seestack.framing import framing_result_verdict, recentre_outcome
        from seestack.io.wcs_io import celestial_wcs_from_fits

        wcs, width, height = celestial_wcs_from_fits(fits_path)
        if wcs is None:
            return None
        try:
            xs, ys = wcs.world_to_pixel_values(info.ra_deg, info.dec_deg)
            x_px, y_px = float(xs), float(ys)
        except Exception:  # noqa: BLE001 — a degenerate WCS just means "no verdict"
            return None
        scale = _arcsec_per_px(wcs)
        if scale is None:
            return None
        v = framing_result_verdict(
            x_px=x_px, y_px=y_px, width_px=width, height_px=height,
            arcsec_per_px=scale, size_arcmin=info.size_arcmin,
        )
        if v is None:
            return None
        # "Re-centre this picture": the crop that would bring an off-centre object
        # back to the middle, offered only when the verdict is exactly that — a
        # clipped or oversized object can't be helped by cropping, and a centred
        # one has nothing to gain. The engine refuses on its own terms too
        # (too destructive, or too cramped around the object), so this is `null`
        # far more often than it isn't. An offer, never an automatic change.
        outcome = recentre_outcome(
            x_px=x_px, y_px=y_px, width_px=width, height_px=height,
            arcsec_per_px=scale, size_arcmin=info.size_arcmin,
        ) if v.level == "off_centre" else None
        rc = outcome.crop if outcome else None
        return {
            "level": v.level,
            "text": v.text,
            "coverage": v.coverage,
            "off_centre": v.off_centre,
            # Fractional (0..1) crop bounds in the editor's own `geometry.crop`
            # convention, plus the fraction of the frame it keeps.
            "recentre": None if rc is None else {
                "x0": rc.x0, "y0": rc.y0, "x1": rc.x1, "y1": rc.y1, "kept": rc.kept,
            },
            # Why there is no offer, when the verdict said "off to one side" but
            # cropping can't help. Present so the *worst*-framed pictures don't
            # get less help than the mildly off-centre ones: the caller can say
            # "cropping back to the middle would leave only about a fifth of the
            # picture" instead of going quiet. `kept` is what that crop would have
            # kept (0–1), and is only meaningful for `too_destructive`.
            "recentre_refused": None if (outcome is None or rc is not None) else {
                "reason": outcome.reason, "kept": outcome.kept,
            },
            # The name the sentence is prefixed with, so one voice covers this
            # card and the pre-shoot "will it fit?" hint.
            "object_name": info.name or info.id,
            "size_arcmin": info.size_arcmin,
        }

    return await run_in_threadpool(work)


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
    in-place Auto edit (its sliders are a no-op — nothing to anchor)."""
    lib, proj = deps.open_target_project(request, safe)
    try:
        run = next((r for r in proj.iter_stack_runs() if r.id == run_id), None)
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
        if preview_ds:
            return {"stretch": None, "black": None, "north_up_deg": north_up_deg}
        rgb, display_space = load_stack_rgb(fits_path, max_width=1024)
        if display_space:
            return {"stretch": None, "black": None, "north_up_deg": north_up_deg}
        # Anchor the asinh sky target to the *export* grey (the value the History/
        # Gallery thumbnail the user just clicked is rendered at), not the editor's
        # brighter default, so opening Adjust starts on that thumbnail's look
        # instead of jumping ~2× brighter.
        sug = suggest_asinh_stretch(rgb, target_bg=EXPORT_AUTOSTRETCH_TARGET_BG)
        if sug is None:
            return {"stretch": None, "black": None, "north_up_deg": north_up_deg}
        return {"stretch": sug[0], "black": sug[1],
                "target_bg": EXPORT_AUTOSTRETCH_TARGET_BG,
                "north_up_deg": north_up_deg}

    return await run_in_threadpool(work)


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
    north_up = bool(body.get("north_up", False))

    from seestack.render.thumbnail import render_stack_png
    from seestack.stack.output import fits_is_display_space
    png = await run_in_threadpool(
        render_stack_png, run.fits_path,
        stretch=stretch, black=black, max_width=1024, north_up=north_up,
    )
    Path(run.preview_path).write_bytes(png)

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
    finally:
        proj.close()
        lib.close()
    return {"ok": True, "stretch": stretch, "black": black, "north_up": north_up}


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
    stored preview to compare against, the target has no frame to render, or the run
    is a **display-space editor export** — its preview is a bespoke tone-mapped image
    a raw sub can't be honestly matched to (the noise-ratio endpoint already bails on
    the same runs), so the card self-hides rather than showing two mismatched tone
    curves. Every caption field is best-effort (``null`` when its datum is missing) so
    the card degrades to a shorter line rather than printing blanks.
    """
    from seestack.stack.output import fits_is_display_space

    lib, proj = deps.open_target_project(request, safe)
    try:
        run = next((r for r in proj.iter_stack_runs() if r.id == run_id), None)
        if run is None:
            raise HTTPException(status_code=404, detail="No such run")
        has_preview = bool(run.preview_path and Path(run.preview_path).exists())
        # A display-space export is tone-mapped verbatim; a raw sub STF/asinh
        # render can't match it, so don't offer the reveal for those runs. An
        # in-place Auto-edited run's preview is likewise a recipe result (its FITS
        # stays linear, so only the run marker catches it).
        display_space = _preview_is_display_space(run.options_json) or bool(
            run.fits_path and Path(run.fits_path).exists()
            and fits_is_display_space(run.fits_path)
        )
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
        src = readable_frame_path(ref)
        if not src:
            raise HTTPException(status_code=404, detail="Frame file not found on disk")
        pattern = (ref.bayer_pattern or "RGGB").upper()
        if pattern not in _BAYER_PATTERNS:
            pattern = "RGGB"
        src_path = str(src)
        # If the run's preview was re-saved with a custom asinh stretch (History
        # "Adjust"), render the sub through that same curve so the reveal's two
        # halves differ only in noise/detail — not a tone offset. Both columns are
        # NULL for the common default-STF preview, where we keep the STF render.
        stretch = run.preview_stretch
        black = run.preview_black
    finally:
        proj.close()
        lib.close()

    from seestack.render.thumbnail import render_sub_preview

    png = await run_in_threadpool(
        render_sub_preview, src_path, bayer_pattern=pattern, max_width=1024,
        stretch=stretch, black=black,
    )
    return Response(content=png, media_type="image/png",
                    headers={"Cache-Control": "no-store"})


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
                      ("NROUGHAL", "n_roughly_aligned")):
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


@router.get("/api/targets/{safe}/stack-runs/{run_id}/wallpaper")
def download_wallpaper(safe: str, run_id: int, request: Request,
                       aspect: str = "phone", north_up: bool = False) -> Response:
    """Crop + size the finished stack preview into a ready-to-set wallpaper.

    ``aspect`` is one of ``phone`` / ``desktop`` / ``square``. The preview is
    cropped to that shape centred on the plate-solved target (falling back to the
    image centre when the run has no WCS or the target has no known position),
    downscaled to a sane device resolution without upsampling, and returned as a
    share-friendly JPEG. ``north_up`` first rotates the picture so celestial North
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

    # North-up rotates the picture *and* moves the target pixel, so re-centre the
    # crop on the rotated position. Only when a real WCS + more-than-trivial angle
    # exists; otherwise the preview (and target pixel) are left untouched.
    if north_up and run.fits_path and Path(run.fits_path).exists():
        try:
            angle = stack_north_up_deg(run.fits_path)
            if angle is not None and abs(angle) >= NORTH_UP_MIN_DEG:
                size = png_size(preview)
                preview = orient_preview_north_up(preview, run.fits_path)
                if target_px is not None and size is not None:
                    target_px = rotate_point_north_up(
                        target_px[0], target_px[1], size[0], size[1], angle)
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
