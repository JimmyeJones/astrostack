"""Gallery: every stacked image across all targets, with its stacking settings.

``GET /api/gallery`` returns one entry per stack run (newest first) — its
preview URL, basic stats, and the full set of :class:`StackOptions` that
produced it (parsed from the run's ``options_json``). The frontend renders this
as a browsable grid where each image can show exactly how it was stacked.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

from webapp import deps

router = APIRouter(tags=["gallery"])

# How many pictures the "best" wall returns at most. A generous cap so the
# frontend can show a full wall and slice a shorter Dashboard strip from the
# same response; the ranker returns fewer when the Library holds fewer targets.
BEST_PICTURES_MAX = 24
# The wall needs at least this many finished stacks to be worth showing — with
# one picture there's nothing to curate, so the endpoint self-hides (empty list).
BEST_PICTURES_MIN = 2


class GalleryItem(BaseModel):
    safe: str
    target_name: str
    run_id: int
    output_basename: str
    timestamp_utc: str
    n_frames_used: int
    canvas_w: int
    canvas_h: int
    # Effective integration time in seconds (None for pre-schema-4 runs).
    total_exposure_s: float | None
    # User label/notes for this run (e.g. "best RGB v2"), if set. Surfaced on the
    # card and matched by the Gallery search box alongside the target name.
    notes: str | None = None
    has_preview: bool
    has_fits: bool
    has_tiff: bool
    preview_url: str
    # Full StackOptions used for this run (parsed from options_json), so the UI
    # can display exactly how the image was produced. Empty dict if unparseable.
    options: dict[str, Any]
    # True when this run's settings can pre-fill the Stack form ("reuse settings").
    # False for editor-recipe / channel-combine runs, which carry no stack knobs.
    reusable: bool = False
    # Median transparency of the stacked frames ÷ the target's clear-sky baseline
    # (< ~0.6 ⇒ hazy). None for pre-schema-5 runs; drives a "hazy night" badge.
    transparency_ratio: float | None = None
    # Background-noise σ of the stacked image, normalized to its own signal range
    # (lower = cleaner). None for pre-schema-6 runs; drives a noise readout.
    noise_sigma: float | None = None
    # Which calibration masters were applied to the lights ("dark+flat", …), or
    # None when uncalibrated / pre-schema-7; drives a "dark+flat" chip.
    calstat: str | None = None


class GalleryResponse(BaseModel):
    items: list[GalleryItem]


def _parse_options(options_json: str | None) -> dict[str, Any]:
    if not options_json:
        return {}
    try:
        parsed = json.loads(options_json)
    except (json.JSONDecodeError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _is_reusable(options: dict[str, Any]) -> bool:
    """A run's settings can pre-fill the Stack form unless it's an editor-recipe
    or channel-combine run (those carry no stack knobs)."""
    return "editor_recipe" not in options and "channel_combine" not in options


@router.get("/api/gallery", response_model=GalleryResponse)
def get_gallery(request: Request) -> GalleryResponse:
    items: list[GalleryItem] = []
    lib = deps.open_library(request)
    try:
        from seestack.io.project import Project

        for t in lib.list_targets():
            proj = None
            try:
                proj = Project.open(lib.target_dir(t))
                runs = list(proj.iter_stack_runs())
            except Exception:  # noqa: BLE001 — a broken project must not 500 the gallery
                # One unreadable/corrupt project DB — or one stamped with a newer
                # schema after an image rollback (Project.open raises RuntimeError)
                # — must not hide *every* target's images. Skip it, like
                # stats.py / storage.py already do for the same call.
                if proj is not None:
                    proj.close()
                continue
            try:
                for run in runs:
                    has_preview = bool(run.preview_path and Path(run.preview_path).exists())
                    options = _parse_options(run.options_json)
                    items.append(GalleryItem(
                        safe=t.safe_name,
                        target_name=t.name,
                        run_id=run.id,
                        output_basename=run.output_basename,
                        timestamp_utc=run.timestamp_utc,
                        n_frames_used=run.n_frames_used,
                        canvas_w=run.canvas_w,
                        canvas_h=run.canvas_h,
                        total_exposure_s=run.total_exposure_s,
                        notes=run.notes,
                        has_preview=has_preview,
                        has_fits=bool(run.fits_path and Path(run.fits_path).exists()),
                        has_tiff=bool(run.tiff_path and Path(run.tiff_path).exists()),
                        preview_url=(
                            f"/api/targets/{t.safe_name}/stack-runs/{run.id}/preview"
                        ),
                        options=options,
                        reusable=_is_reusable(options),
                        transparency_ratio=run.transparency_ratio,
                        noise_sigma=run.noise_sigma,
                        calstat=run.calstat,
                    ))
            finally:
                if proj is not None:
                    proj.close()
    finally:
        lib.close()

    # Newest first across all targets.
    items.sort(key=lambda it: it.timestamp_utc, reverse=True)
    return GalleryResponse(items=items)


class BestPicture(BaseModel):
    """One entry on the auto-curated *My best pictures* wall — the fields the wall
    (and its lightbox/share/download) need, plus the ranking ``score`` (0–1) so the
    UI can show a transparent "why it's here" line."""

    safe: str
    target_name: str
    run_id: int
    output_basename: str
    timestamp_utc: str
    n_frames_used: int
    canvas_w: int
    canvas_h: int
    total_exposure_s: float | None
    noise_sigma: float | None
    has_preview: bool
    has_fits: bool
    has_tiff: bool
    preview_url: str
    # Quality-blend score in [0, 1], relative to this Library's own collection.
    score: float


class BestPicturesResponse(BaseModel):
    items: list[BestPicture]


@router.get("/api/gallery/best", response_model=BestPicturesResponse)
def get_best_pictures(
    request: Request,
    limit: int = Query(BEST_PICTURES_MAX, ge=1, le=BEST_PICTURES_MAX),
) -> BestPicturesResponse:
    """Auto-curated cross-target portfolio: the newest *finished* stack of every
    target, ranked best-first by the transparent quality blend
    (:func:`seestack.portfolio.rank_portfolio`). Read-only aggregation over the
    Library — no schema/state change. Self-hides (empty list) until at least
    :data:`BEST_PICTURES_MIN` targets have a finished picture, so a brand-new
    install shows nothing rather than a wall of one."""
    from seestack.io.project import Project
    from seestack.portfolio import PortfolioEntry, rank_portfolio

    # One representative per target: its newest run that actually has a rendered
    # preview on disk (a "finished picture"), keyed so the ranker's result maps
    # straight back to the full record.
    by_key: dict[str, BestPicture] = {}
    entries: list[PortfolioEntry] = []

    lib = deps.open_library(request)
    try:
        for t in lib.list_targets():
            proj = None
            try:
                proj = Project.open(lib.target_dir(t))
                runs = list(proj.iter_stack_runs())
            except Exception:  # noqa: BLE001 — one broken project must not 500 the wall
                # Same guard the gallery/stats/storage cross-target reads use: a
                # corrupt or newer-schema (rolled-back) project DB is skipped, not
                # allowed to hide every other target's best picture.
                if proj is not None:
                    proj.close()
                continue
            try:
                # runs are newest-first; take the newest with a preview on disk.
                newest = next(
                    (r for r in runs
                     if r.preview_path and Path(r.preview_path).exists()),
                    None,
                )
                if newest is None:
                    continue
                key = f"{t.safe_name}:{newest.id}"
                by_key[key] = BestPicture(
                    safe=t.safe_name,
                    target_name=t.name,
                    run_id=newest.id,
                    output_basename=newest.output_basename,
                    timestamp_utc=newest.timestamp_utc,
                    n_frames_used=newest.n_frames_used,
                    canvas_w=newest.canvas_w,
                    canvas_h=newest.canvas_h,
                    total_exposure_s=newest.total_exposure_s,
                    noise_sigma=newest.noise_sigma,
                    has_preview=True,
                    has_fits=bool(newest.fits_path and Path(newest.fits_path).exists()),
                    has_tiff=bool(newest.tiff_path and Path(newest.tiff_path).exists()),
                    preview_url=(
                        f"/api/targets/{t.safe_name}/stack-runs/{newest.id}/preview"
                    ),
                    score=0.0,  # filled in from the ranking below
                )
                entries.append(PortfolioEntry(
                    key=key,
                    n_frames_used=newest.n_frames_used,
                    total_exposure_s=newest.total_exposure_s,
                    noise_sigma=newest.noise_sigma,
                    coverage_max=newest.coverage_max,
                ))
            finally:
                if proj is not None:
                    proj.close()
    finally:
        lib.close()

    # Not enough finished pictures to curate → self-hide.
    if len(by_key) < BEST_PICTURES_MIN:
        return BestPicturesResponse(items=[])

    ranked = rank_portfolio(entries, limit=limit)
    items: list[BestPicture] = []
    for r in ranked:
        pic = by_key[r.key]
        items.append(pic.model_copy(update={"score": r.score}))
    return BestPicturesResponse(items=items)
