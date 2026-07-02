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

from fastapi import APIRouter, Request
from pydantic import BaseModel

from webapp import deps

router = APIRouter(tags=["gallery"])


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
                for run in proj.iter_stack_runs():
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
                        has_preview=has_preview,
                        has_fits=bool(run.fits_path and Path(run.fits_path).exists()),
                        has_tiff=bool(run.tiff_path and Path(run.tiff_path).exists()),
                        preview_url=(
                            f"/api/targets/{t.safe_name}/stack-runs/{run.id}/preview"
                        ),
                        options=options,
                        reusable=_is_reusable(options),
                    ))
            finally:
                if proj is not None:
                    proj.close()
    finally:
        lib.close()

    # Newest first across all targets.
    items.sort(key=lambda it: it.timestamp_utc, reverse=True)
    return GalleryResponse(items=items)
