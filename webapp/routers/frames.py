"""Per-target frame endpoints: list/sort, accept-reject, bulk, preview image."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse

from seestack.io.project import FrameRow
from seestack.render.thumbnail import THUMB_VERSION, generate_thumbnail, thumbs_dir
from webapp import deps
from webapp.schemas import BulkFrameAction, FrameOut, FramePatch

router = APIRouter(prefix="/api/targets/{safe}/frames", tags=["frames"])

_BAYER_PATTERNS = {"RGGB", "BGGR", "GRBG", "GBRG"}

_SORTABLE = {
    "id", "timestamp_utc", "exposure_s", "fwhm_px", "star_count",
    "sky_adu_median", "eccentricity_median",
}


def _to_out(f: FrameRow) -> FrameOut:
    return FrameOut(
        id=f.id,
        name=Path(f.source_path).name,
        timestamp_utc=f.timestamp_utc,
        exposure_s=f.exposure_s,
        gain=f.gain,
        width_px=f.width_px,
        height_px=f.height_px,
        bayer_pattern=f.bayer_pattern,
        solved=f.wcs_json is not None,
        ra_center_deg=f.ra_center_deg,
        dec_center_deg=f.dec_center_deg,
        ra_hint_deg=f.ra_hint_deg,
        dec_hint_deg=f.dec_hint_deg,
        fwhm_px=f.fwhm_px,
        star_count=f.star_count,
        sky_adu_median=f.sky_adu_median,
        eccentricity_median=f.eccentricity_median,
        streak_detected=f.streak_detected,
        accept=f.accept,
        reject_reason=f.reject_reason,
        user_override=f.user_override,
    )


@router.get("", response_model=list[FrameOut])
def list_frames(
    safe: str,
    request: Request,
    accepted_only: bool = False,
    sort: str = "id",
    order: str = "asc",
    offset: int = 0,
    limit: int = 500,
) -> list[FrameOut]:
    if sort not in _SORTABLE:
        sort = "id"
    lib, proj = deps.open_target_project(request, safe)
    try:
        frames = list(proj.iter_frames(accepted_only=accepted_only))
    finally:
        proj.close()
        lib.close()

    def key(f: FrameRow):
        v = getattr(f, sort)
        return (v is None, v)

    frames.sort(key=key, reverse=(order == "desc"))
    return [_to_out(f) for f in frames[offset : offset + limit]]


@router.get("/{frame_id}", response_model=FrameOut)
def get_frame(safe: str, frame_id: int, request: Request) -> FrameOut:
    lib, proj = deps.open_target_project(request, safe)
    try:
        f = proj.get_frame(frame_id)
        if f is None:
            raise HTTPException(status_code=404, detail="No such frame")
        return _to_out(f)
    finally:
        proj.close()
        lib.close()


@router.patch("/{frame_id}", response_model=FrameOut)
def patch_frame(safe: str, frame_id: int, body: FramePatch, request: Request) -> FrameOut:
    lib, proj = deps.open_target_project(request, safe)
    try:
        f = proj.get_frame(frame_id)
        if f is None:
            raise HTTPException(status_code=404, detail="No such frame")
        patch: dict = {}
        if body.accept is not None:
            patch["accept"] = body.accept
            patch["user_override"] = True
            patch["reject_reason"] = None if body.accept else (body.reject_reason or "user")
        if body.bayer_pattern is not None:
            patch["bayer_pattern"] = body.bayer_pattern
        if patch:
            proj.update_frame(frame_id, **patch)
        return _to_out(proj.get_frame(frame_id))
    finally:
        proj.close()
        lib.close()


@router.post("/bulk")
def bulk_frames(safe: str, body: BulkFrameAction, request: Request) -> dict:
    lib, proj = deps.open_target_project(request, safe)
    try:
        changed = 0
        if body.action in ("accept", "reject") and body.ids:
            accept = body.action == "accept"
            for fid in body.ids:
                proj.update_frame(
                    fid, accept=accept, user_override=True,
                    reject_reason=None if accept else "user",
                )
                changed += 1
        elif body.action == "reject_worst":
            frames = [f for f in proj.iter_frames(accepted_only=True)
                      if getattr(f, body.metric) is not None]
            # Higher FWHM/ecc/sky is worse; higher star_count is better.
            reverse = body.metric != "star_count"
            frames.sort(key=lambda f: getattr(f, body.metric), reverse=reverse)
            n = int(len(frames) * max(0.0, min(1.0, body.fraction)))
            for f in frames[:n]:
                proj.update_frame(
                    f.id, accept=False, user_override=True,
                    reject_reason=f"bulk:{body.metric}",
                )
                changed += 1
        return {"changed": changed}
    finally:
        proj.close()
        lib.close()


@router.get("/{frame_id}/preview")
async def frame_preview(
    safe: str,
    frame_id: int,
    request: Request,
    size: int = 512,
    bayer: str | None = None,
) -> Response:
    size = max(64, min(2048, size))
    # bayer ends up embedded in the cache filename below — it must be one of
    # the four real patterns, both to fail cleanly and so it can never carry
    # a path separator into that filename (see write_stack_outputs' output_name
    # fix for the same class of bug).
    if bayer is not None and bayer.upper() not in _BAYER_PATTERNS:
        raise HTTPException(status_code=400, detail=f"Unknown bayer pattern: {bayer!r}")
    lib, proj = deps.open_target_project(request, safe)
    try:
        f = proj.get_frame(frame_id)
        if f is None:
            raise HTTPException(status_code=404, detail="No such frame")
        src = f.cached_path or f.source_path
        if not src or not Path(src).exists():
            raise HTTPException(status_code=404, detail="Frame file not found on disk")
        pattern = (bayer or f.bayer_pattern or "RGGB").upper()
        cache_dir = thumbs_dir(proj.project_dir)
        out = cache_dir / f"web_{frame_id:06d}_{size}_{pattern}_v{THUMB_VERSION}.png"
        src_path = Path(src)
    finally:
        proj.close()
        lib.close()

    etag = f'"{frame_id}-{size}-{pattern}-{THUMB_VERSION}"'
    if request.headers.get("if-none-match") == etag and out.exists():
        return Response(status_code=304)

    if not out.exists():
        # Rendering is CPU-bound but fast; run it off the event loop and OFF the
        # single job worker so previews never queue behind a stack.
        await run_in_threadpool(
            generate_thumbnail, src_path, out, bayer_pattern=pattern, size=size
        )
    resp = FileResponse(out, media_type="image/png")
    resp.headers["ETag"] = etag
    resp.headers["Cache-Control"] = "public, max-age=86400"
    return resp
