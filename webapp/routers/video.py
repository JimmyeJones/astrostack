"""Moon & Sun: lucky-imaging stacks of the Seestar's video captures.

The Seestar writes its Solar/Lunar captures to ``<Target>_video/`` folders that
the FITS pipeline skips, so before this router they were invisible in the app —
a beginner had a Moon video on their NAS and no way to turn it into a picture.

* ``GET  /api/videos`` — the captures sitting in ``incoming/``, plus whether
  each already has a finished still.
* ``POST /api/videos/{id}/stack`` — grade → keep the sharpest → align → average.
* ``GET  /api/videos/{id}/preview.png`` / ``…/download.tiff`` — the result.

Captures are addressed by a sanitised id and re-discovered server-side on every
call; no filesystem path ever comes from the client.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from seestack.video.discover import find_video_capture, find_video_captures
from seestack.video.ffmpeg import ffmpeg_available
from webapp import deps, video

router = APIRouter(tags=["video"])

#: Plain-language line shown when the container has no ffmpeg, so the page
#: explains itself instead of offering a button that can only fail.
FFMPEG_MISSING_HINT = (
    "Video stacking needs ffmpeg, which isn't in this container. Update to a "
    "current AstroStack image — it bundles ffmpeg — and this page will light up."
)


class VideoFileOut(BaseModel):
    name: str
    size_bytes: int


class VideoResultOut(BaseModel):
    created_utc: str
    source_name: str
    width: int
    height: int
    keep_percent: float
    n_graded: int
    n_kept: int
    n_stacked: int
    n_align_failed: int
    stride: int
    warnings: list[str] = []
    preview_url: str
    tiff_url: str


class VideoCaptureOut(BaseModel):
    id: str
    label: str
    kind: str
    folder_name: str
    files: list[VideoFileOut]
    total_bytes: int
    result: VideoResultOut | None = None


class VideoListOut(BaseModel):
    #: False when ffmpeg is missing — the UI shows ``hint`` instead of buttons.
    available: bool
    hint: str | None = None
    incoming_dir: str
    captures: list[VideoCaptureOut]


class VideoStackRequest(BaseModel):
    #: Keep the sharpest N% of frames. Bounded to the range the engine accepts
    #: so a stray value fails here with a clear 422 rather than mid-job.
    keep_percent: float = Field(default=30.0, ge=1.0, le=100.0)
    #: Which file in the folder to stack (basename). Omit for the longest one.
    file_name: str | None = None
    align: bool = True


def _size_of(path: str) -> int:
    try:
        return Path(path).stat().st_size
    except OSError:
        return 0


def _result_out(settings, capture_id: str) -> VideoResultOut | None:
    meta = video.read_meta(settings, capture_id)
    if meta is None or not video.has_result(settings, capture_id):
        return None
    return VideoResultOut(
        created_utc=meta.created_utc,
        source_name=meta.source_name,
        width=meta.width,
        height=meta.height,
        keep_percent=meta.keep_percent,
        n_graded=meta.n_graded,
        n_kept=meta.n_kept,
        n_stacked=meta.n_stacked,
        n_align_failed=meta.n_align_failed,
        stride=meta.stride,
        warnings=list(meta.warnings),
        preview_url=f"/api/videos/{capture_id}/preview.png",
        tiff_url=f"/api/videos/{capture_id}/download.tiff",
    )


@router.get("/api/videos", response_model=VideoListOut)
def list_videos(request: Request) -> VideoListOut:
    settings = deps.get_settings(request)
    incoming = settings.resolved_incoming_dir
    available = ffmpeg_available()
    captures = [
        VideoCaptureOut(
            id=cap.id,
            label=cap.label,
            kind=cap.kind,
            folder_name=cap.folder_name,
            files=[
                VideoFileOut(name=Path(f).name, size_bytes=_size_of(f)) for f in cap.files
            ],
            total_bytes=cap.total_bytes,
            result=_result_out(settings, cap.id),
        )
        for cap in find_video_captures(incoming)
    ]
    return VideoListOut(
        available=available,
        hint=None if available else FFMPEG_MISSING_HINT,
        incoming_dir=str(incoming),
        captures=captures,
    )


@router.post("/api/videos/{capture_id}/stack")
def stack_one_video(
    capture_id: str, request: Request, body: VideoStackRequest | None = None,
) -> dict[str, str]:
    settings = deps.get_settings(request)
    jm = deps.get_job_manager(request)
    if not ffmpeg_available():
        raise HTTPException(status_code=503, detail=FFMPEG_MISSING_HINT)
    capture = find_video_capture(settings.resolved_incoming_dir, capture_id)
    if capture is None:
        raise HTTPException(status_code=404, detail="No such video capture")
    req = body or VideoStackRequest()
    try:
        video.pick_source_file(capture, req.file_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    job = video.submit_video_stack(
        settings, jm, capture.id,
        keep_percent=req.keep_percent,
        file_name=req.file_name,
        align=req.align,
    )
    return {"job_id": job.id}


def _result_file(request: Request, capture_id: str, name: str) -> Path:
    settings = deps.get_settings(request)
    # Re-derive the id through the discovery helper's sanitiser so a crafted
    # ``capture_id`` can't escape the video results directory.
    from seestack.video.discover import video_capture_id

    safe_id = video_capture_id(capture_id)
    path = video.result_dir(settings, safe_id) / name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="No stacked picture for this capture yet")
    return path


@router.get("/api/videos/{capture_id}/preview.png")
def video_preview(capture_id: str, request: Request) -> FileResponse:
    return FileResponse(
        _result_file(request, capture_id, video.PNG_NAME), media_type="image/png",
    )


@router.get("/api/videos/{capture_id}/download.tiff")
def video_tiff(capture_id: str, request: Request) -> FileResponse:
    path = _result_file(request, capture_id, video.TIFF_NAME)
    return FileResponse(
        path, media_type="image/tiff", filename=f"{capture_id}-stack.tiff",
    )
