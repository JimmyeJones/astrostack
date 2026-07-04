"""Non-destructive editor endpoints: op schema, recipes, live proxy preview,
histogram, auto-process, presets, full-res export, and batch apply.

Live preview/histogram run on the cached downsampled proxy via ``run_in_threadpool``
(like ``render_stack_run``); full-res export and batch go through the job worker.
"""

from __future__ import annotations

import base64
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from pydantic import BaseModel

from seestack.edit.coverage_trim import largest_covered_rect
from seestack.edit.histogram import compute_histogram
from seestack.edit.ops.detail import deconv_understates_on_proxy
from seestack.edit.pipeline import apply_recipe
from seestack.edit.proxy import coverage_path_for, get_proxy, load_coverage
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


def _proxy_coverage(fits_path: str, scale: float) -> np.ndarray | None:
    """The run's per-pixel coverage map, strided to the live-preview proxy so the
    "Coverage leveling" op works in preview and matches the full-res export. The
    proxy is built by striding with ``step = round(proxy_scale)`` (see
    ``build_proxy``), so we decimate the coverage the same way. None when the run
    has no coverage sibling (a single-field image)."""
    return load_coverage(fits_path, step=max(1, int(round(scale))))


def _render_png(project_dir: Path, run, recipe: Recipe) -> bytes:
    import io

    from PIL import Image

    rgb, scale = get_proxy(project_dir, run.id, run.fits_path)
    ctx = EditContext(proxy_scale=scale, is_proxy=True, wcs=None,
                      coverage=_proxy_coverage(run.fits_path, scale))
    out = apply_recipe(rgb, recipe, ctx, for_preview=True)
    u8 = (np.clip(np.nan_to_num(out), 0.0, 1.0) * 255).astype(np.uint8)
    buf = io.BytesIO()
    Image.fromarray(u8, mode="RGB").save(buf, format="PNG")
    return buf.getvalue()


def _render_coverage_png(project_dir: Path, run) -> bytes | None:
    """Render the run's per-pixel frame-coverage map (strided to the preview
    proxy so it lines up with the shown image) as a viridis-coloured PNG — dark
    blue where the fewest frames overlap (the ragged mosaic edges / gaps),
    yellow where the most do. A colour heatmap reads the coverage gradient at a
    glance and is visually distinct from the grayscale star mask. ``None`` when
    the run has no coverage sibling (a single-field image)."""
    import io

    from PIL import Image

    from seestack.render.colormap import apply_viridis

    rgb, scale = get_proxy(project_dir, run.id, run.fits_path)
    cov = _proxy_coverage(run.fits_path, scale)
    if cov is None:
        return None
    finite = np.isfinite(cov)
    peak = float(cov[finite].max()) if finite.any() else 0.0
    norm = np.zeros(cov.shape, dtype=np.float32)
    if peak > 0:
        norm = np.clip(np.nan_to_num(cov, nan=0.0) / peak, 0.0, 1.0)
    rgb_map = apply_viridis(norm)
    buf = io.BytesIO()
    Image.fromarray(rgb_map, mode="RGB").save(buf, format="PNG")
    return buf.getvalue()


def _render_star_mask_png(project_dir: Path, run, size_px: float, grow: float,
                          recipe: Recipe | None = None, uid: str | None = None) -> bytes:
    """Render the soft star mask (the same map that gates star ops) as a grayscale
    PNG, so the user can *see* what the editor treats as stars vs background.

    The star ops (``stars.reduce`` / ``stars.boost_nebula``) run in display space
    (post-stretch) and gate on the *stretched* image at their position in the
    pipeline — where faint stars pop out of the noise. Computing the overlay on the
    raw **linear** proxy instead drastically under-represents what the ops touch
    (faint stars sit in the noise floor there). So when a recipe is supplied, apply
    it up to (but not including) the selected star op and mask the resulting
    display-space image; fall back to the linear proxy only when no recipe is given
    (e.g. an old client)."""
    import io

    from PIL import Image

    from seestack.edit.starmask import star_mask

    rgb, scale = get_proxy(project_dir, run.id, run.fits_path)
    ctx = EditContext(proxy_scale=scale, is_proxy=True, wcs=None,
                      coverage=_proxy_coverage(run.fits_path, scale))
    if recipe is not None:
        sub = _recipe_before_uid(recipe, uid,
                                 drop_ids=("stars.reduce", "stars.boost_nebula"))
        img = apply_recipe(rgb, sub, ctx, for_preview=True)
    else:
        img = rgb
    mask = star_mask(img, size_px=size_px, grow=grow, ctx=ctx)
    u8 = (np.clip(np.nan_to_num(mask), 0.0, 1.0) * 255).astype(np.uint8)
    buf = io.BytesIO()
    Image.fromarray(u8, mode="L").save(buf, format="PNG")
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


# Gaussian FWHM → σ, and the bounds the deconvolution op's ``psf_sigma`` accepts
# (kept in step with the EditParam definition in seestack/edit/ops/detail.py).
_FWHM_TO_SIGMA = 1.0 / (2.0 * math.sqrt(2.0 * math.log(2.0)))  # ≈ 0.4247
_PSF_SIGMA_MIN = 0.5
_PSF_SIGMA_MAX = 5.0


class PsfSuggestionOut(BaseModel):
    """A data-driven default PSF width for editor deconvolution, derived from
    the target's measured star sizes. ``None`` when no frame carries an FWHM."""

    fwhm_px: float | None
    psf_sigma: float | None


@router.get("/api/targets/{safe}/editor/psf-suggestion", response_model=PsfSuggestionOut)
def psf_suggestion(safe: str, request: Request) -> PsfSuggestionOut:
    """Suggest a deconvolution PSF σ from the target's median star FWHM, so the
    user doesn't have to hand-guess a Gaussian width — the QC layer already
    measured it. σ = FWHM / (2·√(2·ln2)), clamped to the op's slider range."""
    lib, proj = deps.open_target_project(request, safe)
    try:
        fwhm = proj.median_fwhm()
    finally:
        proj.close()
        lib.close()
    if fwhm is None or fwhm <= 0:
        return PsfSuggestionOut(fwhm_px=None, psf_sigma=None)
    sigma = max(_PSF_SIGMA_MIN, min(_PSF_SIGMA_MAX, fwhm * _FWHM_TO_SIGMA))
    return PsfSuggestionOut(fwhm_px=round(fwhm, 3), psf_sigma=round(sigma, 2))


# The sharpen op's radius slider bounds/step (kept in step with the EditParam in
# seestack/edit/ops/detail.py). A good unsharp-mask radius is on the scale of the
# star's own blur, so we reuse the FWHM→σ conversion the PSF suggestion uses.
_SHARPEN_RADIUS_MIN = 0.5
_SHARPEN_RADIUS_MAX = 10.0
_SHARPEN_RADIUS_STEP = 0.5


class SharpenSuggestionOut(BaseModel):
    """A data-driven sharpen radius derived from the target's median star FWHM
    (radius ≈ the star's Gaussian σ), so the user doesn't hand-guess a radius.
    ``None`` when no frame carries an FWHM."""

    fwhm_px: float | None
    radius: float | None


@router.get("/api/targets/{safe}/editor/sharpen-suggestion", response_model=SharpenSuggestionOut)
def sharpen_suggestion(safe: str, request: Request) -> SharpenSuggestionOut:
    """Suggest an unsharp-mask radius from the target's median star FWHM, so the
    user doesn't hand-guess — mirrors the PSF-from-stars button. The star's
    Gaussian σ (= FWHM / 2·√(2·ln2)) is the natural detail scale to enhance;
    clamped to the op's slider range and rounded to its step."""
    lib, proj = deps.open_target_project(request, safe)
    try:
        fwhm = proj.median_fwhm()
    finally:
        proj.close()
        lib.close()
    if fwhm is None or fwhm <= 0:
        return SharpenSuggestionOut(fwhm_px=None, radius=None)
    raw = fwhm * _FWHM_TO_SIGMA
    radius = max(_SHARPEN_RADIUS_MIN, min(_SHARPEN_RADIUS_MAX, raw))
    radius = round(radius / _SHARPEN_RADIUS_STEP) * _SHARPEN_RADIUS_STEP
    return SharpenSuggestionOut(fwhm_px=round(fwhm, 3), radius=round(radius, 2))


# The star-reduction op's ``size`` slider bounds/step (kept in step with the
# EditParam in seestack/edit/ops/stars.py). ``size`` is a star-scale in pixels —
# the same physical quantity the FWHM measures — so the median star FWHM is the
# natural data-driven default, rounded to the op's integer step and clamped.
_STAR_SIZE_MIN = 1
_STAR_SIZE_MAX = 8


class StarSizeSuggestionOut(BaseModel):
    """A data-driven star size for the star-reduction op, derived from the
    target's median star FWHM (``size`` ≈ the star's diameter in px), so the user
    doesn't hand-guess. ``None`` when no frame carries an FWHM."""

    fwhm_px: float | None
    size: int | None


@router.get("/api/targets/{safe}/editor/star-size-suggestion",
            response_model=StarSizeSuggestionOut)
def star_size_suggestion(safe: str, request: Request) -> StarSizeSuggestionOut:
    """Suggest a star-reduction ``size`` from the target's median star FWHM, so the
    user doesn't hand-guess how big their stars are — mirrors the sharpen/PSF
    from-stars buttons. ``size`` is a star-scale in px, so the FWHM maps directly:
    rounded to the op's integer step and clamped to its slider range."""
    lib, proj = deps.open_target_project(request, safe)
    try:
        fwhm = proj.median_fwhm()
    finally:
        proj.close()
        lib.close()
    if fwhm is None or fwhm <= 0:
        return StarSizeSuggestionOut(fwhm_px=None, size=None)
    size = int(max(_STAR_SIZE_MIN, min(_STAR_SIZE_MAX, round(fwhm))))
    return StarSizeSuggestionOut(fwhm_px=round(fwhm, 3), size=size)


class DenoiseSuggestionOut(BaseModel):
    """A data-driven starting strength for the editor's noise-reduction op,
    derived from the run's own background noise. ``None`` when the proxy has no
    measurable image data."""

    noise_sigma: float | None
    strength: float | None


@router.get("/api/targets/{safe}/stack-runs/{run_id}/editor/denoise-suggestion",
            response_model=DenoiseSuggestionOut)
async def denoise_suggestion(safe: str, run_id: int, request: Request) -> DenoiseSuggestionOut:
    """Suggest a denoise strength from the run's measured background noise, so the
    user doesn't have to hand-tune the 0..1 knob — mirrors the PSF-from-stars
    button for deconvolution. Robust σ of adjacent-pixel differences, normalized
    to the image's own signal range and mapped to the op's strength slider."""
    from seestack.edit.noise import suggest_denoise_strength

    project_dir, run = _run_info(request, safe, run_id)

    def work() -> DenoiseSuggestionOut:
        rgb, _scale = get_proxy(project_dir, run.id, run.fits_path)
        sigma, strength = suggest_denoise_strength(rgb)
        return DenoiseSuggestionOut(noise_sigma=sigma, strength=strength)

    return await run_in_threadpool(work)


class LevelsSuggestionOut(BaseModel):
    """Data-driven black/white points for the ``tone.levels`` op, from low/high
    percentiles of the image *as it enters the op*. ``black``/``white`` are ``None``
    when there's no useful suggestion (too few finite pixels or a near-empty range).
    ``gamma`` is an optional midtone lift that lands the image's typical tone at a
    pleasant target grey after those points are applied; ``None`` when no meaningful
    lift exists (older clients simply ignore the field). ``gamma_target`` is the
    display-space grey (0..1) that lift aims for, so the UI can name the goal the
    number solves for; ``None`` when there's no gamma suggestion."""

    black: float | None
    white: float | None
    gamma: float | None = None
    gamma_target: float | None = None


def _recipe_before_uid(rec: Recipe, uid: str | None,
                       drop_ids: tuple[str, ...] = ("tone.levels",)) -> Recipe:
    """A copy of ``rec`` truncated to the ops *before* the one with ``uid`` (so a
    suggestion/overlay measures the display-space image that op will receive). When
    ``uid`` isn't present, drop every op whose id is in ``drop_ids`` instead — the
    next-best proxy for "the image without this adjustment"."""
    ops = rec.ops
    idx = next((i for i, op in enumerate(ops) if op.uid == uid), None)
    kept = ops[:idx] if idx is not None else [op for op in ops if op.id not in drop_ids]
    return Recipe(ops=list(kept), version=rec.version, base_run_id=rec.base_run_id)


@router.get("/api/targets/{safe}/stack-runs/{run_id}/editor/levels-suggestion",
            response_model=LevelsSuggestionOut)
async def levels_suggestion(safe: str, run_id: int, request: Request,
                            recipe: str | None = None,
                            uid: str | None = None) -> LevelsSuggestionOut:
    """Suggest black & white points for the Levels op from the histogram of the
    image *entering* that op (all ops before it in the recipe applied), so a
    beginner gets a safe auto-levels they can then nudge instead of hand-guessing
    the two 0..1 sliders. Mirrors the other data-driven "From your image" buttons.
    """
    from seestack.edit.levels import (
        GAMMA_TARGET,
        suggest_levels_gamma,
        suggest_levels_points,
    )

    project_dir, run = _run_info(request, safe, run_id)
    rec = _decode_recipe_query(request, safe, run_id, recipe)
    sub = _recipe_before_uid(rec, uid)

    def work() -> LevelsSuggestionOut:
        rgb, scale = get_proxy(project_dir, run.id, run.fits_path)
        ctx = EditContext(proxy_scale=scale, is_proxy=True, wcs=None,
                          coverage=_proxy_coverage(run.fits_path, scale))
        out = apply_recipe(rgb, sub, ctx, for_preview=True)
        pts = suggest_levels_points(out)
        if pts is None:
            return LevelsSuggestionOut(black=None, white=None)
        gamma = suggest_levels_gamma(out, pts[0], pts[1])
        return LevelsSuggestionOut(
            black=pts[0], white=pts[1], gamma=gamma,
            gamma_target=GAMMA_TARGET if gamma is not None else None,
        )

    return await run_in_threadpool(work)


# Cap the coverage grid the O(h·w) largest-rectangle sweep runs on: a mosaic's
# full-res coverage map can be >100 MP, but fractional crop bounds need nowhere
# near that precision, so we stride it down first (mirrors the proxy decimation).
_TRIM_MAX_DIM = 512


class TrimCrop(BaseModel):
    x0: float
    y0: float
    x1: float
    y1: float


class TrimSuggestionOut(BaseModel):
    """A one-click "trim the ragged mosaic border" suggestion. ``crop`` is the
    fractional (0..1) rectangle of the largest well-covered area to set the
    ``geometry.crop`` op to, or ``None`` when there's nothing worth trimming
    (a single-field stack, uniform coverage, or an already-full-frame result)."""

    is_mosaic: bool
    crop: TrimCrop | None


@router.get("/api/targets/{safe}/stack-runs/{run_id}/editor/trim-suggestion",
            response_model=TrimSuggestionOut)
async def trim_suggestion(safe: str, run_id: int, request: Request,
                          min_frac: float = 0.5) -> TrimSuggestionOut:
    """Suggest a crop to the largest well-covered rectangle of a mosaic, so a
    user can trim the ragged, low-coverage union-canvas edges in one click
    instead of hand-dragging the crop bounds. Only offered on a mosaic (uneven
    panel overlap → ``coverage_max > coverage_min``); a single-field stack is
    left untouched. The coverage map already written next to the stack drives it.
    """
    project_dir, run = _run_info(request, safe, run_id)
    is_mosaic = bool(int(run.coverage_max) > int(run.coverage_min))
    if not is_mosaic:
        return TrimSuggestionOut(is_mosaic=False, crop=None)

    def work() -> TrimSuggestionOut:
        cov_path = coverage_path_for(run.fits_path)
        if not cov_path.exists():
            return TrimSuggestionOut(is_mosaic=True, crop=None)
        # Stride the (possibly huge) coverage map down before the rectangle sweep.
        step = 1
        try:
            from astropy.io import fits as _fits

            hdr = _fits.getheader(cov_path)
            dim = max(int(hdr.get("NAXIS1", 0)), int(hdr.get("NAXIS2", 0)))
            if dim > _TRIM_MAX_DIM:
                step = -(-dim // _TRIM_MAX_DIM)  # ceil division
        except (OSError, ValueError):
            step = 1
        cov = load_coverage(run.fits_path, step=step)
        if cov is None:
            return TrimSuggestionOut(is_mosaic=True, crop=None)
        rect = largest_covered_rect(cov, min_frac=min_frac)
        crop = None if rect is None else TrimCrop(x0=round(rect[0], 4), y0=round(rect[1], 4),
                                                  x1=round(rect[2], 4), y1=round(rect[3], 4))
        return TrimSuggestionOut(is_mosaic=True, crop=crop)

    return await run_in_threadpool(work)


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
        ctx = EditContext(proxy_scale=scale, is_proxy=True, wcs=None,
                          coverage=_proxy_coverage(run.fits_path, scale))
        errors: list[str] = []
        out = apply_recipe(rgb, rec, ctx, for_preview=True, errors=errors)
        hist = compute_histogram(out)
        hist["empty"] = empty
        hist["errors"] = errors  # ops that failed (surfaced near the preview)
        # Surface the proxy geometry so the editor can tell the user the live
        # preview is downscaled (a ≤1500 px proxy of what may be a 150 MP mosaic),
        # which sets expectations for why fine detail reads differently than the
        # full-res export. proxy_scale = full_width / proxy_width (>=1).
        h, w = rgb.shape[:2]
        hist["proxy_scale"] = round(float(scale), 3)
        hist["proxy_width"] = int(w)
        hist["proxy_height"] = int(h)
        # Whether this run is a mosaic (uneven panel overlap → coverage spans a
        # range). The "Coverage leveling" op is only meaningful on a mosaic; on a
        # single-field stack (uniform coverage) it's a deliberate no-op, so the
        # editor can tell the user the control won't do anything here.
        hist["is_mosaic"] = bool(int(run.coverage_max) > int(run.coverage_min))
        # A deconvolution op's live preview understates the full-res export when
        # the proxy is decimated enough that its PSF collapses to the floor (a
        # near-no-op kernel) — a fundamental limit of the sub-pixel blur on the
        # decimated grid. Flag it so the editor can honestly caption that the
        # preview shows less deconvolution than the export applies, instead of
        # silently misleading. Only enabled deconv ops count.
        hist["deconv_preview_understates"] = any(
            op.enabled and op.id == "detail.deconvolve"
            and deconv_understates_on_proxy(
                float(op.params.get("psf_sigma", 1.5)), float(scale))
            for op in rec.ops
        )
        return hist

    return await run_in_threadpool(work)


@router.get("/api/targets/{safe}/stack-runs/{run_id}/editor/star-mask")
async def edit_star_mask(safe: str, run_id: int, request: Request,
                         size_px: float = 4.0, grow: float = 0.5,
                         recipe: str | None = None, uid: str | None = None) -> Response:
    """Grayscale preview of the star mask (~white on stars, black elsewhere) that
    drives the star-reduce / boost-nebula ops. `size_px` matches the ops' star
    size (reduce uses 2× its `size`; boost-nebula uses `size` directly).

    `recipe`/`uid` (the current edit recipe and the selected star op) make the
    overlay reflect the *display-space* image the op actually gates on — the ops
    run post-stretch, so masking the raw linear proxy badly under-counts faint
    stars. Omitting them falls back to the linear proxy (old-client behaviour)."""
    size_px = max(0.5, min(50.0, size_px))
    grow = max(0.0, min(3.0, grow))
    project_dir, run = _run_info(request, safe, run_id)
    rec = _decode_recipe_query(request, safe, run_id, recipe) if recipe else None
    png = await run_in_threadpool(_render_star_mask_png, project_dir, run,
                                  size_px, grow, rec, uid)
    return Response(content=png, media_type="image/png",
                    headers={"Cache-Control": "no-store"})


@router.get("/api/targets/{safe}/stack-runs/{run_id}/editor/coverage-map")
async def edit_coverage_map(safe: str, run_id: int, request: Request) -> Response:
    """Viridis-coloured heatmap of the run's frame-coverage map (yellow = most
    frames overlap, dark blue = uncovered), so a user can *see* the ragged,
    low-coverage mosaic edges the "Trim border" / "Coverage leveling" tools
    address. 404 when the run has no coverage sibling (a single-field image)."""
    project_dir, run = _run_info(request, safe, run_id)
    png = await run_in_threadpool(_render_coverage_png, project_dir, run)
    if png is None:
        raise HTTPException(status_code=404, detail="No coverage map for this run")
    return Response(content=png, media_type="image/png",
                    headers={"Cache-Control": "no-store"})


@router.post("/api/targets/{safe}/stack-runs/{run_id}/editor/auto")
async def auto_process(safe: str, run_id: int, request: Request) -> dict:
    project_dir, run = _run_info(request, safe, run_id)
    # The target's median star FWHM sizes the auto sharpen radius to the data
    # (same conversion as the sharpen-from-stars button), not a fixed guess.
    lib, proj = deps.open_target_project(request, safe)
    try:
        median_fwhm = proj.median_fwhm()
    finally:
        proj.close()
        lib.close()

    # A mosaic stack (uneven panel overlap → coverage_max > coverage_min) gets a
    # coverage-leveling pass prepended so its panel steps are flattened; a
    # single-field stack (uniform coverage) is unchanged.
    coverage_span = (int(run.coverage_min), int(run.coverage_max))

    def work() -> dict:
        rgb, _scale = get_proxy(project_dir, run.id, run.fits_path)
        return presets_mod.auto_recipe(
            rgb, median_fwhm=median_fwhm, coverage_span=coverage_span).to_dict()

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
