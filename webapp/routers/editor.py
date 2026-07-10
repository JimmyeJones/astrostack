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

from seestack.edit.coverage_trim import coverage_is_mosaic, largest_covered_rect
from seestack.edit.histogram import compute_histogram
from seestack.edit.ops.detail import deconv_understates_on_proxy
from seestack.edit.ops.stars import star_reduce_overstates_on_proxy
from seestack.edit.pipeline import apply_recipe
from seestack.edit.proxy import coverage_path_for, get_proxy, load_coverage
from seestack.edit.recipe import Recipe, recipe_from_dict
from seestack.edit.registry import EditContext
from seestack.edit import presets as presets_mod
from webapp import deps
from webapp.schemas import EditOpOut, editor_ops_schema

router = APIRouter(tags=["editor"])

RECIPE_META_PREFIX = "editor_recipe:"
# Plain-language "what Auto did (and why)" note, stamped per run whenever an
# *unattended* job auto-edits it (Process-target / reprocess-everything / watcher
# auto-stack). Surfaced on the History Info panel so a beginner sees what the
# silent auto-edit did to a result they didn't drive. Absent on manual/un-edited
# runs, so it only ever annotates runs the auto-edit actually touched.
AUTO_EDIT_NOTE_PREFIX = "editor_auto_note:"
USER_PRESETS_META_KEY = "editor_user_presets"
# A single, user-designated "house style" recipe stored library-wide (not per
# target). Once set, the editor offers it as a one-click seed on any run that has
# no saved edit yet — so a repeat imager's default look is one click away on every
# new target, without diving into the Presets menu. Off until the user sets it.
DEFAULT_RECIPE_META_KEY = "editor_default_recipe"


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


def _run_display_space(run: Any) -> bool:
    """True when this run's stacked image is already tone-mapped display space (an
    editor export), so the editor proxy must not default-stretch it again — the
    re-edit double-stretch. Read from the run's own ``options_json`` (written by
    the editor export), so it needs no FITS read on the hot preview path. Old
    runs (no flag) return False → today's linear-stack behaviour."""
    import json as _json

    if not getattr(run, "options_json", None):
        return False
    try:
        return bool(_json.loads(run.options_json).get("display_space", False))
    except (ValueError, TypeError):
        return False


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


def _load_run_coverage_strided(run):
    """The run's per-pixel coverage map, strided down if huge so the O(h·w) sweeps
    and distribution checks stay cheap. ``None`` when there's no coverage sibling
    (a single-field image whose stack wrote no coverage FITS)."""
    cov_path = coverage_path_for(run.fits_path)
    if not cov_path.exists():
        return None
    step = 1
    try:
        from astropy.io import fits as _fits

        hdr = _fits.getheader(cov_path)
        dim = max(int(hdr.get("NAXIS1", 0)), int(hdr.get("NAXIS2", 0)))
        if dim > _TRIM_MAX_DIM:
            step = -(-dim // _TRIM_MAX_DIM)  # ceil division
    except (OSError, ValueError):
        step = 1
    return load_coverage(run.fits_path, step=step)


def _run_is_mosaic(run, coverage=None, *, load: bool = False) -> bool:
    """Whether a run is a mosaic (union canvas). Uses the stacker's *authoritative*
    persisted ``is_mosaic`` flag when present; for legacy runs recorded before that
    flag existed, falls back to the coverage map's distribution (``coverage_is_mosaic``).
    Never the old ``coverage_max > coverage_min`` test — the reprojection border is
    uncovered, so that minimum is ~always 0 and it mislabels single-field stacks.

    ``coverage`` may be a coverage array already loaded by the caller (no extra
    I/O); when it's ``None`` and ``load`` is set, the coverage map is loaded here."""
    if run.is_mosaic is not None:
        return bool(run.is_mosaic)
    if coverage is None and load:
        coverage = _load_run_coverage_strided(run)
    if coverage is not None:
        return bool(coverage_is_mosaic(coverage))
    return False


def _trim_rect_for_run(run, min_frac: float = 0.5
                       ) -> tuple[float, float, float, float] | None:
    """Fractional ``(x0, y0, x1, y1)`` bounds of the largest well-covered rectangle
    of a run's coverage map (the ragged mosaic border trimmed away), or ``None``
    when there's no coverage sibling or nothing worth trimming (a full-frame
    result). Shared by the "Trim border" suggestion and Auto-process."""
    cov = _load_run_coverage_strided(run)
    if cov is None:
        return None
    rect = largest_covered_rect(cov, min_frac=min_frac)
    if rect is None:
        return None
    return (round(rect[0], 4), round(rect[1], 4), round(rect[2], 4), round(rect[3], 4))


def build_auto_recipe_for_run(project_dir: Path, run, median_fwhm: float | None) -> Recipe:
    """The one-click Auto recipe for a run, built from its own proxy — the same
    logic the ``…/editor/auto`` endpoint serves, factored out so the one-click
    "Process target" job can chain an auto-edit onto the stack it just produced
    without re-implementing it. A mosaic stack gets a coverage-leveling pass (and,
    when meaningful, a border trim) prepended; a single-field stack is unchanged."""
    rgb, _scale = get_proxy(project_dir, run.id, run.fits_path)
    is_mosaic = _run_is_mosaic(run, load=True)
    trim = _trim_rect_for_run(run) if is_mosaic else None
    return presets_mod.auto_recipe(
        rgb, median_fwhm=median_fwhm, is_mosaic=is_mosaic, trim_crop=trim)


def build_auto_analysis_for_run(project_dir: Path, run, median_fwhm: float | None) -> dict:
    """The measured cues that *drove* the Auto recipe for a run — the causal
    inputs behind the ops (sky level, background noise, star size, mosaic trim).
    Mirrors ``build_auto_recipe_for_run`` exactly (same proxy, same mosaic verdict,
    same trim rect) so the reported numbers match the recipe it would build, but
    returns only the analysis so the ``…/editor/auto`` Recipe response shape stays
    unchanged (a separate, additive sibling endpoint serves this)."""
    rgb, _scale = get_proxy(project_dir, run.id, run.fits_path)
    is_mosaic = _run_is_mosaic(run, load=True)
    trim = _trim_rect_for_run(run) if is_mosaic else None
    return presets_mod.analyze_auto_inputs(
        rgb, median_fwhm=median_fwhm, is_mosaic=is_mosaic, trim_crop=trim)


def build_preset_suggestion_for_run(project_dir: Path, run) -> dict:
    """Coarsely classify a run's own proxy and, when one archetype is clear, suggest
    the matching built-in preset (galaxy / nebula / star cluster) — a hint the editor
    shows as a one-click "try this preset?" chip. Read-only: it never changes the Auto
    recipe or persists anything, so a mis-suggestion costs a click, not an image.
    Declines (``preset_id=None``) on an ambiguous or blank field."""
    rgb, _scale = get_proxy(project_dir, run.id, run.fits_path)
    out = presets_mod.classify_target(rgb)
    # Only the user-facing fields; the raw cues stay server-side (debug/tests only).
    return {"preset_id": out["preset_id"], "label": out["label"],
            "reason": out["reason"], "confidence": out["confidence"]}


def render_run_display_array(project_dir: Path, run, recipe: Recipe) -> np.ndarray:
    """Render a recipe on the run's live-preview proxy and return the display-space
    RGB array (values in 0..1, NaN = uncovered). Shared by the PNG preview endpoint
    and the "Process target" auto-edit's thumbnail render."""
    rgb, scale = get_proxy(project_dir, run.id, run.fits_path)
    ctx = EditContext(proxy_scale=scale, is_proxy=True, wcs=None,
                      coverage=_proxy_coverage(run.fits_path, scale),
                      already_display=_run_display_space(run))
    return apply_recipe(rgb, recipe, ctx, for_preview=True)


def _render_png(project_dir: Path, run, recipe: Recipe) -> bytes:
    import io

    from PIL import Image

    out = render_run_display_array(project_dir, run, recipe)
    u8 = (np.clip(np.nan_to_num(out), 0.0, 1.0) * 255).astype(np.uint8)
    buf = io.BytesIO()
    Image.fromarray(u8, mode="RGB").save(buf, format="PNG")
    return buf.getvalue()


def _render_coverage_png(project_dir: Path, run, recipe: Recipe | None = None) -> bytes | None:
    """Render the run's per-pixel frame-coverage map (strided to the preview
    proxy so it lines up with the shown image) as a viridis-coloured PNG — dark
    blue where the fewest frames overlap (the ragged mosaic edges / gaps),
    yellow where the most do. A colour heatmap reads the coverage gradient at a
    glance and is visually distinct from the grayscale star mask. ``None`` when
    the run has no coverage sibling (a single-field image).

    When a ``recipe`` is supplied, its *enabled geometry ops* (crop/rotate/resize)
    are applied to the coverage map first, so the overlay tracks the reshaped
    preview instead of showing the raw full frame (which no longer lines up once a
    crop/rotate is in the recipe). Only geometry ops move the map; tone ops are
    ignored. NaN = uncovered is preserved through the transform."""
    import io

    from PIL import Image

    from seestack.edit.ops.geometry import apply_geometry_to_map
    from seestack.render.colormap import apply_viridis

    rgb, scale = get_proxy(project_dir, run.id, run.fits_path)
    cov = _proxy_coverage(run.fits_path, scale)
    if cov is None:
        return None
    if recipe is not None:
        ctx = EditContext(proxy_scale=scale, is_proxy=True, wcs=None)
        cov = apply_geometry_to_map(cov, recipe, ctx)
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
                      coverage=_proxy_coverage(run.fits_path, scale),
                      already_display=_run_display_space(run))
    if recipe is not None:
        sub = _recipe_before_uid(recipe, uid,
                                 drop_ids=("stars.reduce", "stars.boost_nebula"))
        # Mask the display-space image the op gates on, but in the *un-reshaped*
        # frame (geometry ops stripped) — then reshape the mask with the recipe's
        # geometry below, so the overlay lands in the same crop/rotate/resize frame
        # as the edited preview and the coverage map (matching the sized image box).
        # Otherwise a mask computed before a trailing crop is full-frame and, shown
        # in the cropped box, squishes so its stars no longer sit where they do in
        # the edit. No-op when the recipe has no geometry op (the common case).
        sub = Recipe(ops=[o for o in sub.ops if not o.id.startswith("geometry.")],
                     version=sub.version, base_run_id=sub.base_run_id)
        img = apply_recipe(rgb, sub, ctx, for_preview=True)
    else:
        img = rgb
    mask = star_mask(img, size_px=size_px, grow=grow, ctx=ctx)
    if recipe is not None:
        from seestack.edit.ops.geometry import apply_geometry_to_map
        mask = apply_geometry_to_map(mask, recipe, ctx)
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


# ---- personal default recipe ("my house style") ---------------------------

class DefaultRecipeOut(BaseModel):
    """The user's library-wide default editor recipe, offered as a one-click seed
    on any run with no saved edit. ``count`` is 0 (and ``ops`` empty) when the user
    hasn't set one — the editor then simply doesn't offer it. The ops are validated
    on load (stale ops dropped, params clamped), so applying them can never 500."""

    ops: list[dict] = []
    count: int = 0


def _load_default_recipe(lib) -> DefaultRecipeOut:
    """Read + validate the stored default recipe. A stale/garbage store degrades to
    "no default" rather than erroring."""
    raw = lib.get_meta(DEFAULT_RECIPE_META_KEY)
    if not raw:
        return DefaultRecipeOut(ops=[], count=0)
    try:
        rec = recipe_from_dict(json.loads(raw))
    except (ValueError, TypeError):
        return DefaultRecipeOut(ops=[], count=0)
    ops = [op.to_dict() for op in rec.ops]
    return DefaultRecipeOut(ops=ops, count=len(ops))


@router.get("/api/editor/default-recipe", response_model=DefaultRecipeOut)
def get_default_recipe(request: Request) -> DefaultRecipeOut:
    """The user's saved default recipe (validated), or an empty one if unset."""
    lib = deps.open_library(request)
    try:
        return _load_default_recipe(lib)
    finally:
        lib.close()


class DefaultRecipeIn(BaseModel):
    ops: list[dict] = []


@router.put("/api/editor/default-recipe", response_model=DefaultRecipeOut)
def put_default_recipe(body: DefaultRecipeIn, request: Request) -> DefaultRecipeOut:
    """Save the current edit as the library-wide default. Ops are normalised through
    the validator so only known ops/params persist; an empty list clears the
    default (same as DELETE). Additive/opt-in — nothing changes for other runs until
    the user chooses to apply it."""
    recipe = recipe_from_dict({"ops": body.ops})
    ops = [op.to_dict() for op in recipe.ops]
    lib = deps.open_library(request)
    try:
        lib.set_meta(DEFAULT_RECIPE_META_KEY, json.dumps({"ops": ops}))
    finally:
        lib.close()
    return DefaultRecipeOut(ops=ops, count=len(ops))


@router.delete("/api/editor/default-recipe", response_model=DefaultRecipeOut)
def delete_default_recipe(request: Request) -> DefaultRecipeOut:
    """Clear the user's saved default recipe."""
    lib = deps.open_library(request)
    try:
        lib.set_meta(DEFAULT_RECIPE_META_KEY, json.dumps({"ops": []}))
    finally:
        lib.close()
    return DefaultRecipeOut(ops=[], count=0)


# ---- recipe load/save ------------------------------------------------------

@router.get("/api/targets/{safe}/stack-runs/{run_id}/editor/recipe")
def get_recipe(safe: str, run_id: int, request: Request) -> dict:
    return _load_saved_recipe(request, safe, run_id).to_dict()


class AutoNoteOut(BaseModel):
    """The plain-language "what Auto did (and why)" note that an *unattended*
    auto-edit job (Process-target / reprocess-everything / watcher auto-stack)
    stamped on this run. ``note`` is ``None`` unless a background job auto-edited
    the run — a hand-built or interactively-Auto'd recipe stores none — so the
    editor only ever shows it for a recipe the user didn't build themselves, and a
    hand-built recipe can never surface a stale explanation."""

    note: str | None = None


@router.get("/api/targets/{safe}/stack-runs/{run_id}/editor/auto-note",
            response_model=AutoNoteOut)
def get_auto_note(safe: str, run_id: int, request: Request) -> AutoNoteOut:
    """Return the stored auto-edit note for this run (or ``None``). Read-only;
    lets the editor explain a recipe applied by a background job — the same
    reasoning the History Info panel shows (v0.92.0) — on the surface the
    Process-target deep-link actually lands the user on."""
    lib, proj = deps.open_target_project(request, safe)
    try:
        note = proj.get_meta(f"{AUTO_EDIT_NOTE_PREFIX}{run_id}")
    finally:
        proj.close()
        lib.close()
    return AutoNoteOut(note=note or None)


class PreviousRecipeOut(BaseModel):
    """The most recent *other* stack run's saved editor recipe, offered as a
    one-click carry-over so a re-stacked target keeps the look the user dialled in
    on an earlier run. ``run_id`` is ``None`` when no earlier run has a saved
    (non-empty) edit. The ops are validated on load (stale ops dropped, params
    clamped), so applying them can never 500 the editor."""

    run_id: int | None = None
    ops: list[dict] = []
    count: int = 0


@router.get("/api/targets/{safe}/stack-runs/{run_id}/editor/previous-recipe",
            response_model=PreviousRecipeOut)
def previous_recipe(safe: str, run_id: int, request: Request) -> PreviousRecipeOut:
    """Find the newest *other* run of this target that carries a non-empty saved
    recipe, so the editor can offer "use my previous run's edit" when the current
    run has none — keeping a multi-night project visually consistent across
    re-stacks with one click. Read-only; nothing is written or seeded server-side."""
    from seestack.edit.recipe import recipe_from_json

    lib, proj = deps.open_target_project(request, safe)
    try:
        runs = list(proj.iter_stack_runs())  # newest first (timestamp DESC)
        for run in runs:
            if run.id == run_id:
                continue
            raw = proj.get_meta(f"{RECIPE_META_PREFIX}{run.id}")
            if not raw:
                continue
            rec = recipe_from_json(raw)
            if rec.ops:
                return PreviousRecipeOut(
                    run_id=run.id,
                    ops=[op.to_dict() for op in rec.ops],
                    count=len(rec.ops),
                )
    finally:
        proj.close()
        lib.close()
    return PreviousRecipeOut(run_id=None, ops=[], count=0)


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
async def denoise_suggestion(safe: str, run_id: int, request: Request,
                             recipe: str | None = None,
                             uid: str | None = None) -> DenoiseSuggestionOut:
    """Suggest a denoise strength from the run's measured background noise, so the
    user doesn't have to hand-tune the 0..1 knob — mirrors the PSF-from-stars
    button for deconvolution. Robust σ of adjacent-pixel differences, normalized
    to the image's own signal range and mapped to the op's strength slider.

    Denoise is a *linear-stage* op, so the honest measurement is the **linear**
    image entering it. When ``recipe``+``uid`` are supplied (the per-op "From your
    image" button) the ops *before* this denoise op are applied first — with the
    default stretch suppressed (``auto_stretch=False``) so the σ is measured on
    linear data, never a tone-mapped one — before estimating the noise. This
    mirrors the recipe-aware levels/stretch/curve suggestions, so a linear
    background/gradient or colour-balance op ahead of denoise (the Auto recipe
    puts both there) is reflected in the suggested strength instead of ignored.
    With no ``recipe`` the raw proxy is measured exactly as before, so the "Your
    data" noise chip and bulk apply (which want the stack's *inherent* noise) are
    unchanged."""
    from seestack.edit.noise import suggest_denoise_strength

    project_dir, run = _run_info(request, safe, run_id)
    sub: Recipe | None = None
    if recipe is not None:
        rec = _decode_recipe_query(request, safe, run_id, recipe)
        sub = _recipe_before_uid(rec, uid, drop_ids=("detail.denoise",))

    def work() -> DenoiseSuggestionOut:
        rgb, scale = get_proxy(project_dir, run.id, run.fits_path)
        measured = rgb
        if sub is not None:
            ctx = EditContext(proxy_scale=scale, is_proxy=True, wcs=None,
                              coverage=_proxy_coverage(run.fits_path, scale),
                              already_display=_run_display_space(run))
            measured = apply_recipe(rgb, sub, ctx, for_preview=True, auto_stretch=False)
        sigma, strength = suggest_denoise_strength(measured)
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
                          coverage=_proxy_coverage(run.fits_path, scale),
                          already_display=_run_display_space(run))
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


class StretchSuggestionOut(BaseModel):
    """Data-driven Strength + Black point for the asinh ``tone.stretch`` op,
    solved from the run's own linear data (sky floor → black; sky median lifted
    to a pleasant dark-sky grey). ``stretch``/``black`` are ``None`` when there's
    no useful suggestion (too few finite pixels or no dynamic range). ``target_bg``
    is the display-space grey (0..1) the strength aims the sky at, so the UI can
    name the goal the number solves for; ``None`` when there's no suggestion."""

    stretch: float | None
    black: float | None
    target_bg: float | None = None


@router.get("/api/targets/{safe}/stack-runs/{run_id}/editor/stretch-suggestion",
            response_model=StretchSuggestionOut)
async def stretch_suggestion(safe: str, run_id: int, request: Request,
                             recipe: str | None = None,
                             uid: str | None = None) -> StretchSuggestionOut:
    """Suggest asinh Strength + Black point for the Stretch op from the run's own
    linear data — the one major tonal control still without a "From your image"
    button. The image *entering* the Stretch op (any prior linear ops applied) is
    measured, the sky floor put at black and the sky median solved to a clean
    dark-sky grey, so a beginner gets a well-exposed asinh stretch to nudge from
    instead of hand-guessing the two sliders. Mirrors the Levels suggestion."""
    from seestack.edit.stretch import STRETCH_TARGET_BG, suggest_asinh_stretch

    project_dir, run = _run_info(request, safe, run_id)
    rec = _decode_recipe_query(request, safe, run_id, recipe)
    # Drop the stretch op(s) when the uid is absent, so the measurement sees the
    # linear image the stretch will receive (never the stretch's own output).
    sub = _recipe_before_uid(rec, uid, drop_ids=("tone.stretch",))

    def work() -> StretchSuggestionOut:
        rgb, scale = get_proxy(project_dir, run.id, run.fits_path)
        ctx = EditContext(proxy_scale=scale, is_proxy=True, wcs=None,
                          coverage=_proxy_coverage(run.fits_path, scale))
        # Measure the *linear* image the stretch op will receive: apply the prior
        # (linear) ops but suppress the default-stretch fallback, so we never
        # measure a tone-mapped image.
        out = apply_recipe(rgb, sub, ctx, for_preview=True, auto_stretch=False)
        sug = suggest_asinh_stretch(out)
        if sug is None:
            return StretchSuggestionOut(stretch=None, black=None)
        return StretchSuggestionOut(
            stretch=sug[0], black=sug[1], target_bg=STRETCH_TARGET_BG)

    return await run_in_threadpool(work)


class CurveSuggestionOut(BaseModel):
    """Data-driven starting tone curve for the ``tone.curves`` op — a gentle,
    strictly-monotone midtone-lift curve derived from the display-space histogram
    of the image entering the op. ``points`` is an ordered list of ``[x, y]``
    control points (endpoints pinned at 0/1), or ``None`` when there's no useful
    suggestion (too few finite pixels, a degenerate range, or a typical tone
    already at/above the target). ``target_bg`` is the display-space grey the
    midtone lift aims for, so the UI can name the goal; ``None`` when there's no
    suggestion."""

    points: list[list[float]] | None
    target_bg: float | None = None


@router.get("/api/targets/{safe}/stack-runs/{run_id}/editor/curve-suggestion",
            response_model=CurveSuggestionOut)
async def curve_suggestion(safe: str, run_id: int, request: Request,
                           recipe: str | None = None,
                           uid: str | None = None) -> CurveSuggestionOut:
    """Suggest a gentle starting tone curve for the Curves op from the histogram of
    the display-space image *entering* that op (all ops before it applied), so a
    beginner gets a pleasant contrast start to nudge instead of a flat identity
    line. Mirrors the other data-driven "From your image" buttons."""
    from seestack.edit.curve import CURVE_TARGET_BG, suggest_tone_curve

    project_dir, run = _run_info(request, safe, run_id)
    rec = _decode_recipe_query(request, safe, run_id, recipe)
    sub = _recipe_before_uid(rec, uid, drop_ids=("tone.curves",))

    def work() -> CurveSuggestionOut:
        rgb, scale = get_proxy(project_dir, run.id, run.fits_path)
        ctx = EditContext(proxy_scale=scale, is_proxy=True, wcs=None,
                          coverage=_proxy_coverage(run.fits_path, scale),
                          already_display=_run_display_space(run))
        out = apply_recipe(rgb, sub, ctx, for_preview=True)
        pts = suggest_tone_curve(out)
        if pts is None:
            return CurveSuggestionOut(points=None)
        return CurveSuggestionOut(points=pts, target_bg=CURVE_TARGET_BG)

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
    instead of hand-dragging the crop bounds. Only offered on a mosaic (the
    stacker's persisted verdict, or the coverage distribution for legacy runs); a
    single-field stack is left untouched. The coverage map already written next to
    the stack drives it.
    """
    project_dir, run = _run_info(request, safe, run_id)
    if run.is_mosaic is False:  # authoritative single-field — no coverage I/O
        return TrimSuggestionOut(is_mosaic=False, crop=None)

    def work() -> TrimSuggestionOut:
        if not _run_is_mosaic(run, load=True):
            return TrimSuggestionOut(is_mosaic=False, crop=None)
        rect = _trim_rect_for_run(run, min_frac=min_frac)
        crop = None if rect is None else TrimCrop(x0=rect[0], y0=rect[1],
                                                  x1=rect[2], y1=rect[3])
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
                          coverage=_proxy_coverage(run.fits_path, scale),
                          already_display=_run_display_space(run))
        errors: list[str] = []
        out = apply_recipe(rgb, rec, ctx, for_preview=True, errors=errors)
        hist = compute_histogram(out)
        hist["empty"] = empty
        hist["errors"] = errors  # ops that failed (surfaced near the preview)
        # Surface the proxy geometry so the editor can tell the user the live
        # preview is downscaled (a ≤1500 px proxy of what may be a 150 MP mosaic),
        # which sets expectations for why fine detail reads differently than the
        # full-res export. proxy_scale = full_width / proxy_width (>=1). These are
        # the *raw* proxy dims (before the recipe), so the "downscaled ×N" caption
        # keeps describing the true decimation of the source.
        h, w = rgb.shape[:2]
        hist["proxy_scale"] = round(float(scale), 3)
        hist["proxy_width"] = int(w)
        hist["proxy_height"] = int(h)
        # The dims of the *rendered* preview (after the recipe's geometry ops —
        # crop/rotate/resize — reshape the frame). The preview PNG has this shape,
        # so the editor must size its image box from these (not the raw proxy dims)
        # or a cropped preview gets letterboxed inside the un-cropped aspect and
        # every percentage overlay (Split divider, trim rectangle) mis-aligns.
        # Equal to proxy_width/height when the recipe has no reshaping geometry op.
        oh, ow = out.shape[:2]
        hist["render_width"] = int(ow)
        hist["render_height"] = int(oh)
        # Whether this run is a mosaic (union canvas). The "Coverage leveling" op,
        # the trim/coverage-overlay tools and the mosaic banner are only meaningful
        # on a mosaic; on a single-field stack they're a deliberate no-op. Uses the
        # stacker's persisted verdict (or the already-loaded coverage distribution
        # for legacy runs) — not coverage_max>min, which is ~always true.
        hist["is_mosaic"] = _run_is_mosaic(run, ctx.coverage)
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
        # A star-reduction op's live preview *overstates* the full-res export when
        # the proxy is decimated enough that the star size collapses below one
        # proxy pixel: the erosion footprint clamps up to 1 px (= scale full-res
        # px), physically larger than the export's, so the preview over-reduces
        # the stars. Flag it so the editor can honestly caption that the export
        # will apply *less* star reduction than the preview shows (the opposite
        # direction of deconv). Only enabled star-reduce ops count.
        hist["star_reduce_preview_overstates"] = any(
            op.enabled and op.id == "stars.reduce"
            and star_reduce_overstates_on_proxy(
                float(op.params.get("size", 2)), float(scale))
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
async def edit_coverage_map(safe: str, run_id: int, request: Request,
                            recipe: str | None = None) -> Response:
    """Viridis-coloured heatmap of the run's frame-coverage map (yellow = most
    frames overlap, dark blue = uncovered), so a user can *see* the ragged,
    low-coverage mosaic edges the "Trim border" / "Coverage leveling" tools
    address. 404 when the run has no coverage sibling (a single-field image).

    When ``recipe`` is passed, its enabled geometry ops (crop/rotate/resize) are
    applied to the coverage map so the overlay tracks the reshaped preview; older
    clients omit it and get the raw full-frame coverage."""
    project_dir, run = _run_info(request, safe, run_id)
    rec = _decode_recipe_query(request, safe, run_id, recipe) if recipe else None
    png = await run_in_threadpool(_render_coverage_png, project_dir, run, rec)
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

    def work() -> dict:
        # Shared with the "Process target" auto-edit chain: a mosaic stack gets a
        # coverage-leveling pass (and a border trim when meaningful) prepended; a
        # single-field stack is unchanged. Uses the stacker's authoritative
        # is_mosaic verdict, never the old coverage_max>min heuristic.
        return build_auto_recipe_for_run(project_dir, run, median_fwhm).to_dict()

    return await run_in_threadpool(work)


@router.post("/api/targets/{safe}/stack-runs/{run_id}/editor/auto-analysis")
async def auto_analysis(safe: str, run_id: int, request: Request) -> dict:
    """The *measured cues* Auto read from this run's own data — sky level,
    background noise, median star size, and mosaic trim — so the editor can tell
    the user *why* Auto chose the steps it did ("tuned to your ~0.10 sky and
    4.7 px stars"), not just which ops ran. Additive sibling of ``…/editor/auto``;
    it never persists anything and leaves the Recipe response shape untouched."""
    project_dir, run = _run_info(request, safe, run_id)
    lib, proj = deps.open_target_project(request, safe)
    try:
        median_fwhm = proj.median_fwhm()
    finally:
        proj.close()
        lib.close()

    def work() -> dict:
        return build_auto_analysis_for_run(project_dir, run, median_fwhm)

    return await run_in_threadpool(work)


@router.post("/api/targets/{safe}/stack-runs/{run_id}/editor/preset-suggestion")
async def preset_suggestion(safe: str, run_id: int, request: Request) -> dict:
    """Suggest a starting *preset* from the run's own content — "this looks like a
    star cluster / nebula / galaxy — try the matching preset?". A read-only hint the
    editor offers alongside Auto-process; it classifies the proxy coarsely and returns
    ``preset_id=None`` when nothing is clearly one archetype (the general Auto recipe
    stays the safe fallback). Additive sibling of ``…/editor/auto``; it never persists
    anything and doesn't change what Auto emits."""
    project_dir, run = _run_info(request, safe, run_id)

    def work() -> dict:
        return build_preset_suggestion_for_run(project_dir, run)

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
