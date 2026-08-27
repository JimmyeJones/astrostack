"""Moon & Sun: lucky-imaging stacks of the Seestar's video captures.

The Seestar writes its Solar/Lunar captures to ``<Target>_video/`` folders that
the FITS pipeline skips, so before this router they were invisible in the app —
a beginner had a Moon video on their NAS and no way to turn it into a picture.

* ``GET  /api/videos`` — the captures sitting in ``incoming/``, plus whether
  each already has a finished still.
* ``POST /api/videos/{id}/grade`` — grade only, so "how picky should I be with
  this capture?" can be answered before a stack is spent finding out.
* ``GET  /api/videos/{id}/quicklook.png`` — the sharpest single frame that pass
  found, so "is this capture worth stacking at all?" is a two-second look.
* ``POST /api/videos/{id}/stack`` — grade → keep the sharpest → align → average.
* ``POST /api/videos/{id}/crop`` / ``…/uncrop`` — trim the empty sky off a
  finished still (or put the full frame back) by slicing the saved picture, so
  changing the framing never costs a second decode of the capture.
* ``POST /api/videos/{id}/sharpen`` — bring out more surface detail on a finished
  still (or take it back off) by re-rendering from the kept original, for the
  same reason: it is a decision you make by looking at the picture.
* ``GET  /api/videos/{id}/preview.png`` / ``…/download.tiff`` — the result.

Captures are addressed by a sanitised id and re-discovered server-side on every
call; no filesystem path ever comes from the client.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from seestack.video.detail import SHARPEN_MAX
from seestack.video.discover import find_video_capture, find_video_captures
from seestack.video.ffmpeg import ffmpeg_available
from seestack.video.quality import quicklook_note, sharpness_profile
from webapp import deps, video

log = logging.getLogger(__name__)

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


class KeepOptionOut(BaseModel):
    """What one keep-% setting would give you on this particular capture."""

    percent: float
    n_frames: int
    sharpness_vs_typical: float
    noise_gain: float


class SharpnessProfileOut(BaseModel):
    """"How steady was your capture?" — the grading pass's own numbers.

    Derived on every request from the scores stored with the result, so it costs
    no extra work at stack time and a future improvement to the advice applies to
    stacks that already exist. Absent (``null``) for a result stacked by a version
    that didn't keep the scores — the page then just doesn't show the panel.
    """

    curve: list[float]
    cut_fraction: float
    options: list[KeepOptionOut]
    suggested_percent: float
    spread: str
    summary: str


class QuickLookOut(BaseModel):
    """The sharpest single frame of a graded capture, and how to read it.

    A full lucky stack decodes a multi-minute video twice before the user learns
    whether the capture was worth keeping. The grading pass already finds the
    best frame, so handing that one frame back turns "should I bother stacking
    this?" into a look instead of a wait. It is emphatically not the product —
    ``note`` says so in as many words.
    """

    url: str
    #: Where the frame sat among the graded ones (1-based), and how many those
    #: were — so the picture is locatable rather than anonymous.
    frame_number: int
    n_graded: int
    note: str


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
    #: Additive: older clients ignore it, older results simply have none.
    sharpness: SharpnessProfileOut | None = None
    #: Framing. ``crop_applied`` — this still was trimmed to the disk, so
    #: ``width``/``height`` are the cropped size and ``source_*`` the stack's own.
    #: ``crop_available`` — it wasn't, and there is enough empty sky around the
    #: disk to be worth offering. All additive with neutral defaults, so a result
    #: stacked by an older version simply reads as "not cropped, nothing to offer".
    crop_applied: bool = False
    crop_available: bool = False
    crop_trim_fraction: float = 0.0
    source_width: int = 0
    source_height: int = 0
    #: True when this still was cropped in place and its full frame is still
    #: saved beside it, so the crop can be undone in one click.
    crop_restorable: bool = False
    #: How hard this picture was sharpened after stacking (0 = not at all).
    #: Additive with a neutral default, so a still made before sharpening
    #: existed reads exactly as what it is: unsharpened.
    sharpen_amount: float = 0.0
    #: True when that strength can still be changed from the saved picture, with
    #: no second decode of the capture. False only for a still whose stack
    #: sharpened it before the soft render was kept beside it — the strength is
    #: still reported, it just can't be moved without re-stacking.
    sharpen_editable: bool = False


class VideoCaptureOut(BaseModel):
    id: str
    label: str
    kind: str
    folder_name: str
    files: list[VideoFileOut]
    total_bytes: int
    result: VideoResultOut | None = None
    #: The grade-only pass ("Check this capture"), when one has been run. Lets a
    #: beginner see how much their frames vary *before* choosing how picky to be.
    #: Additive: ``null`` until they press the button.
    sharpness: SharpnessProfileOut | None = None
    #: The sharpest frame that pass found. Additive and independent of
    #: ``sharpness``: a grade run by an older version has scores but no picture,
    #: and reads as ``null`` here.
    quicklook: QuickLookOut | None = None


class VideoListOut(BaseModel):
    #: False when ffmpeg is missing — the UI shows ``hint`` instead of buttons.
    available: bool
    hint: str | None = None
    incoming_dir: str
    captures: list[VideoCaptureOut]


class VideoGradeRequest(BaseModel):
    #: Which file in the folder to grade (basename). Omit for the longest one.
    file_name: str | None = None


class VideoStackRequest(BaseModel):
    #: Keep the sharpest N% of frames. Bounded to the range the engine accepts
    #: so a stray value fails here with a clear 422 rather than mid-job.
    keep_percent: float = Field(default=30.0, ge=1.0, le=100.0)
    #: Which file in the folder to stack (basename). Omit for the longest one.
    file_name: str | None = None
    align: bool = True
    #: Trim the empty sky around the Moon/Sun so the picture is mostly subject.
    #: Off by default: an omitted field must keep giving the full frame a
    #: previous version produced.
    crop: bool = False
    #: How hard to sharpen the finished picture. Zero — no sharpening at all —
    #: is the default for the same reason: an omitted field must reproduce the
    #: picture the previous version made. Bounded to what the engine offers, so
    #: a stray value fails here with a clear 422 rather than mid-job.
    sharpen: float = Field(default=0.0, ge=0.0, le=SHARPEN_MAX)


def _size_of(path: str) -> int:
    try:
        return Path(path).stat().st_size
    except OSError:
        return 0


def _profile_out(scores, keep_percent: float | None) -> SharpnessProfileOut | None:
    """Adapt the engine's profile to the wire, or ``None`` when there's nothing
    worth showing (no scores, or a capture whose frames all scored zero)."""
    return _adapt_profile(sharpness_profile(scores, keep_percent))


def _adapt_profile(profile) -> SharpnessProfileOut | None:
    """Wire shape for an already-measured profile (``None`` passes through)."""
    if profile is None:
        return None
    return SharpnessProfileOut(
        curve=list(profile.curve),
        cut_fraction=profile.cut_fraction,
        options=[
            KeepOptionOut(
                percent=o.percent,
                n_frames=o.n_frames,
                sharpness_vs_typical=o.sharpness_vs_typical,
                noise_gain=o.noise_gain,
            )
            for o in profile.options
        ],
        suggested_percent=profile.suggested_percent,
        spread=profile.spread,
        summary=profile.summary,
    )


def _grade_panels(
    settings, capture_id: str, files: list[str] | None = None,
) -> tuple[SharpnessProfileOut | None, QuickLookOut | None]:
    """Both halves of a grade-only pass — its profile and its sharpest frame.

    Read together from one ``grade.json`` because a capture's list entry wants
    both and the file carries a score per graded frame; asking twice would read
    a 1500-entry list twice on a page that polls.

    The profile's ``keep_percent`` is ``None`` — nothing has been stacked, so
    there is no cut to mark and no "you kept…" clause. The quick look is offered
    only when the picture is actually on disk, so a grade recorded before it
    existed still shows its curve rather than a broken image.

    ``files`` is the capture's current video files, used to check the saved
    grade still describes one of them: the Seestar re-records into the same
    folder, and a check of *last night's* clip must not stay on screen advising
    on tonight's. A grade that no longer matches reads as "never checked" — the
    panels drop out and the "Check this capture first" button comes back — which
    is one click to a truthful answer rather than a stale one dressed as fresh.
    """
    grade = video.read_grade(settings, capture_id)
    if grade is None:
        return None, None
    try:
        return _grade_panels_from(settings, capture_id, grade, files)
    except Exception:  # noqa: BLE001 — one unusable grade must not fail the page
        # Same reasoning as :func:`_result_out`: ``read_grade`` checks field
        # *names*, not types, so a wrong-typed ``grade.json`` only fails here.
        # It reads as "never checked" — the "Check this capture first" button
        # comes back — rather than 500-ing the whole capture list.
        log.warning(
            "video grade metadata for %s is unusable; reporting no grade",
            capture_id, exc_info=True,
        )
        return None, None


def _grade_panels_from(
    settings, capture_id: str, grade, files: list[str] | None,  # noqa: ANN001
) -> tuple[SharpnessProfileOut | None, QuickLookOut | None]:
    if not video.grade_matches_source(grade, list(files or [])):
        return None, None
    profile = sharpness_profile(grade.scores, None)
    quicklook = None
    if grade.best_index >= 0 and video.has_quicklook(settings, capture_id):
        quicklook = QuickLookOut(
            url=f"/api/videos/{capture_id}/quicklook.png",
            frame_number=grade.best_index + 1,
            n_graded=grade.n_graded,
            note=quicklook_note(
                profile,
                frame_number=grade.best_index + 1,
                n_graded=grade.n_graded,
            ),
        )
    return _adapt_profile(profile), quicklook


def _result_out(settings, capture_id: str) -> VideoResultOut | None:
    """One capture's finished-picture panel, or ``None`` when there isn't a usable one.

    ``read_meta``'s contract is that a damaged ``meta.json`` reads as "no result"
    rather than breaking the page that lists captures — but it only enforces the
    *field names*: a plain dataclass does no type checking, so a JSON-valid but
    wrong-*typed* value (``"width": "big"``, ``"source_name": null`` — a
    hand-edited or foreign-version file on an in-place-upgraded install) survives
    the dataclass and only blows up here, in the Pydantic build, taking the whole
    ``/api/videos`` list with it. Honour the contract at this boundary instead:
    one bad capture reads as "never stacked", the rest of the page is fine.
    """
    meta = video.read_meta(settings, capture_id)
    if meta is None or not video.has_result(settings, capture_id):
        return None
    try:
        return _build_result_out(settings, capture_id, meta)
    except Exception:  # noqa: BLE001 — one unusable result must not fail the page
        log.warning(
            "video result metadata for %s is unusable; reporting no result",
            capture_id, exc_info=True,
        )
        return None


def _build_result_out(settings, capture_id: str, meta) -> VideoResultOut:  # noqa: ANN001
    # A still stacked before framing existed has never been looked at, which is
    # not the same as "nothing to trim" — measure it once, from the picture, so
    # pictures the owner already has get the same offer a new one does.
    meta = video.ensure_framing_measured(settings, capture_id, meta)
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
        sharpness=_profile_out(meta.scores, meta.keep_percent),
        crop_applied=meta.crop_applied,
        crop_available=meta.crop_available,
        crop_trim_fraction=meta.crop_trim_fraction,
        source_width=meta.source_width or meta.width,
        source_height=meta.source_height or meta.height,
        crop_restorable=video.crop_is_restorable(settings, capture_id, meta),
        sharpen_amount=meta.sharpen_amount,
        sharpen_editable=video.can_resharpen(meta),
    )


def _orphaned_stills(settings, listed: set[str]) -> list[VideoCaptureOut]:
    """Finished stills whose source video is no longer in ``incoming/``.

    ``find_video_captures`` deliberately skips a folder with no readable video —
    right for "what can I stack?", wrong for "where is my picture?". Clearing the
    clip off the NAS is the case the in-place crop was built for (it never needs
    the source), and the Gallery card points here, so a still that outlived its
    video must still have a home on this page: without it that button leads to a
    page the picture isn't on, and its 16-bit TIFF, its crop and its sharpness
    panel all become unreachable.

    Listed last, after the captures the user can actually act on, and with an
    empty ``files`` list — which is exactly how the page tells the two apart and
    hides the stacking controls. Best-effort: a video-store problem leaves the
    live captures alone rather than failing the page.
    """
    try:
        metas = video.iter_results(settings)
    except Exception:  # noqa: BLE001 — never fail the page over the extra source
        return []
    out: list[VideoCaptureOut] = []
    for m in metas:
        if m.capture_id in listed:
            continue
        # No files to compare a saved check against — the video is gone — so the
        # grade is trusted as-is rather than hidden. It describes the clip this
        # picture was made from, which is exactly the one the user is looking at.
        profile, quicklook = _grade_panels(settings, m.capture_id)
        out.append(VideoCaptureOut(
            id=m.capture_id,
            label=m.label,
            kind=m.kind,
            # The result folder's own name — the same id every ``/api/videos/{id}``
            # route resolves, so the card's actions keep working.
            folder_name=m.capture_id,
            files=[],
            total_bytes=0,
            result=_result_out(settings, m.capture_id),
            sharpness=profile,
            quicklook=quicklook,
        ))
    return out


def _capture_out(settings, cap) -> VideoCaptureOut:
    """One discovered capture's list entry, result and grade panels included."""
    profile, quicklook = _grade_panels(settings, cap.id, cap.files)
    return VideoCaptureOut(
        id=cap.id,
        label=cap.label,
        kind=cap.kind,
        folder_name=cap.folder_name,
        files=[
            VideoFileOut(name=Path(f).name, size_bytes=_size_of(f)) for f in cap.files
        ],
        total_bytes=cap.total_bytes,
        result=_result_out(settings, cap.id),
        sharpness=profile,
        quicklook=quicklook,
    )


@router.get("/api/videos", response_model=VideoListOut)
def list_videos(request: Request) -> VideoListOut:
    settings = deps.get_settings(request)
    incoming = settings.resolved_incoming_dir
    available = ffmpeg_available()
    captures = [_capture_out(settings, cap) for cap in find_video_captures(incoming)]
    captures.extend(_orphaned_stills(settings, {c.id for c in captures}))
    return VideoListOut(
        available=available,
        hint=None if available else FFMPEG_MISSING_HINT,
        incoming_dir=str(incoming),
        captures=captures,
    )


@router.post("/api/videos/{capture_id}/grade")
def grade_one_video(
    capture_id: str, request: Request, body: VideoGradeRequest | None = None,
) -> dict[str, str]:
    """Grade a capture without stacking it — "how picky should I be with this?"

    Same decode as pass 1 of the stack, so it is a *job* with progress and
    cancel, not a synchronous request: a multi-minute capture takes real time to
    read even when nothing is accumulated.
    """
    settings = deps.get_settings(request)
    jm = deps.get_job_manager(request)
    if not ffmpeg_available():
        raise HTTPException(status_code=503, detail=FFMPEG_MISSING_HINT)
    capture = find_video_capture(settings.resolved_incoming_dir, capture_id)
    if capture is None:
        raise HTTPException(status_code=404, detail="No such video capture")
    req = body or VideoGradeRequest()
    try:
        video.pick_source_file(capture, req.file_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    job = video.submit_video_grade(settings, jm, capture.id, file_name=req.file_name)
    return {"job_id": job.id}


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
        crop=req.crop,
        sharpen=req.sharpen,
    )
    return {"job_id": job.id}


def _safe_capture_id(capture_id: str) -> str:
    """Re-derive an id through the discovery sanitiser, so a crafted one can't
    escape the video results folder. Paths are always resolved server-side."""
    from seestack.video.discover import video_capture_id

    return video_capture_id(capture_id)


@router.post("/api/videos/{capture_id}/crop", response_model=VideoResultOut)
def crop_one_still(capture_id: str, request: Request) -> VideoResultOut:
    """Trim the empty sky off a finished still — no re-stack, no ffmpeg.

    Cropping is a decision made *after* seeing the picture, so acting on it must
    not cost another full decode of a multi-minute capture (which may not even be
    on the NAS any more). The saved artifacts are sliced in place and the full
    frame is kept beside them, so this is reversible via ``…/uncrop``.
    """
    settings = deps.get_settings(request)
    safe_id = _safe_capture_id(capture_id)
    try:
        video.crop_saved_still(settings, safe_id)
    except video.StillCropError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    result = _result_out(settings, safe_id)
    if result is None:  # pragma: no cover - the crop just wrote it
        raise HTTPException(status_code=404, detail="No stacked picture for this capture")
    return result


@router.post("/api/videos/{capture_id}/uncrop", response_model=VideoResultOut)
def restore_one_still(capture_id: str, request: Request) -> VideoResultOut:
    """Put the full frame back after an in-place crop."""
    settings = deps.get_settings(request)
    safe_id = _safe_capture_id(capture_id)
    try:
        video.restore_full_still(settings, safe_id)
    except video.StillCropError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    result = _result_out(settings, safe_id)
    if result is None:  # pragma: no cover - the restore just wrote it
        raise HTTPException(status_code=404, detail="No stacked picture for this capture")
    return result


class VideoSharpenRequest(BaseModel):
    """How hard to sharpen a picture that already exists. 0 removes it."""

    amount: float = Field(default=0.0, ge=0.0, le=SHARPEN_MAX)


@router.post("/api/videos/{capture_id}/sharpen", response_model=VideoResultOut)
def sharpen_one_still(
    capture_id: str, req: VideoSharpenRequest, request: Request,
) -> VideoResultOut:
    """Change how sharp a finished still is — no re-stack, no ffmpeg.

    Exactly the same reasoning as the crop next to it: how much sharpening a
    picture wants is something you can only judge by *looking at it*, so acting
    on that judgement must not cost another multi-minute decode of a capture that
    may not even be on the NAS any more. Every strength is rendered from the
    kept original rather than from the picture on disk, so trying several never
    compounds, and ``amount: 0`` puts the soft picture back.
    """
    settings = deps.get_settings(request)
    safe_id = _safe_capture_id(capture_id)
    try:
        video.sharpen_saved_still(settings, safe_id, req.amount)
    except video.StillCropError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    result = _result_out(settings, safe_id)
    if result is None:  # pragma: no cover - the sharpen just wrote it
        raise HTTPException(status_code=404, detail="No stacked picture for this capture")
    return result


def _result_file(
    request: Request,
    capture_id: str,
    name: str,
    missing: str = "No stacked picture for this capture yet",
) -> Path:
    settings = deps.get_settings(request)
    path = video.result_dir(settings, _safe_capture_id(capture_id)) / name
    if not path.is_file():
        raise HTTPException(status_code=404, detail=missing)
    return path


@router.get("/api/videos/{capture_id}/preview.png")
def video_preview(capture_id: str, request: Request) -> FileResponse:
    return FileResponse(
        _result_file(request, capture_id, video.PNG_NAME), media_type="image/png",
    )


#: Said by both the never-checked and the no-longer-current case, deliberately:
#: a check that no longer describes the clip on disk *is* a capture that hasn't
#: been checked, and one click on "Check this capture first" makes it true again.
_NOT_CHECKED = "This capture hasn't been checked yet, so there's no frame to look at"


@router.get("/api/videos/{capture_id}/quicklook.png")
def video_quicklook(capture_id: str, request: Request) -> FileResponse:
    """The sharpest single frame the last check of this capture found.

    Refuses to serve a frame from a check that no longer describes the clip on
    disk. :func:`_grade_panels` already drops the curve and the quick look from
    the page in that case, but the picture itself lives at a plain URL — so a
    stale tab, a bookmark or a browser cache would still be handed last night's
    frame, which is the very dishonesty that guard exists to remove.

    The capture's *current* files decide it, exactly as the panels do — and, as
    there, "no files" is not a mismatch: an orphaned still whose clip has been
    cleared off the NAS has nothing to disagree with, so its frame still serves.
    """
    settings = deps.get_settings(request)
    safe_id = _safe_capture_id(capture_id)
    path = _result_file(request, capture_id, video.QUICKLOOK_NAME, _NOT_CHECKED)
    grade = video.read_grade(settings, safe_id)
    if grade is not None:
        cap = find_video_capture(settings.resolved_incoming_dir, safe_id)
        if not video.grade_matches_source(grade, list(cap.files) if cap else []):
            raise HTTPException(status_code=404, detail=_NOT_CHECKED)
    return FileResponse(path, media_type="image/png")


@router.get("/api/videos/{capture_id}/download.tiff")
def video_tiff(capture_id: str, request: Request) -> FileResponse:
    path = _result_file(request, capture_id, video.TIFF_NAME)
    return FileResponse(
        path, media_type="image/tiff", filename=f"{capture_id}-stack.tiff",
    )
