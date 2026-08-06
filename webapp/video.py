"""Video ("Stack video") job body + result store.

The Seestar's Moon/Sun captures arrive as a video file in a ``<Target>_video/``
folder, which the FITS scanner skips — there are no subs to ingest, so these
never become library targets and none of the per-target machinery (project DB,
plate-solve, calibration, stack runs) applies. This module is therefore a small
self-contained store rather than an extension of the library:

    <data_root>/video/<capture id>/
        stack.png     ← the finished still, display-rendered (what the user sees)
        stack.tiff    ← 16-bit, for anyone who wants to edit it elsewhere
        meta.json     ← how it was made, so the result can explain itself
        grade.json    ← a grade-only pass (every frame's sharpness), so the user
                        can see what their capture looks like before stacking it

Adding a directory alongside ``incoming/``/``library/``/``state/`` is additive:
nothing existing moves, and an install that never stacks a video never grows one.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from seestack.stack.output import write_full_res_png
from seestack.video.discover import VideoCapture, find_video_capture
from seestack.video.ffmpeg import ffmpeg_available, probe_video
from seestack.video.framing import crop_to_disk, measure_framing
from seestack.video.lucky import (
    LuckyOptions,
    VideoStackCancelled,
    grade_video,
    normalize_for_display,
    stack_video,
)
from webapp.config import Settings
from webapp.jobs import Job, JobManager

log = logging.getLogger(__name__)

#: Job kind for the video stack, so the Jobs page can label it.
JOB_KIND = "video_stack"
#: ...and for the grade-only pass, which answers "how picky should I be?" before
#: the user spends a full stack finding out.
JOB_KIND_GRADE = "video_grade"

PNG_NAME = "stack.png"
TIFF_NAME = "stack.tiff"
META_NAME = "meta.json"
#: Written by the grade-only pass. Kept **beside** ``meta.json`` rather than in
#: it so checking a capture can never disturb a still that is already stacked.
GRADE_NAME = "grade.json"


def video_root(settings: Settings) -> Path:
    """Where finished video stills live. Created on first use, never on boot."""
    return Path(settings.data_root) / "video"


def result_dir(settings: Settings, capture_id: str) -> Path:
    return video_root(settings) / capture_id


@dataclass
class VideoStackMeta:
    """Everything needed to describe a finished still to the user."""

    capture_id: str
    label: str
    kind: str
    source_name: str
    created_utc: str
    width: int
    height: int
    keep_percent: float
    n_graded: int
    n_kept: int
    n_stacked: int
    n_align_failed: int
    stride: int
    aligned: bool
    sharpness_best: float
    sharpness_kept_median: float
    sharpness_all_median: float
    warnings: list[str]
    #: Every graded frame's sharpness score, in capture order. Optional and last
    #: so a ``meta.json`` written by an older version still loads (it simply has
    #: no profile, and the page hides the panel). Rounded on the way out — the
    #: scores are only ever compared as ratios, so six significant figures is far
    #: more than the advice needs and keeps a 1500-frame capture's file small.
    scores: list[float] = field(default_factory=list)
    #: True when the still was trimmed to the disk (``width``/``height`` are then
    #: the *cropped* size). Optional with a default so an older ``meta.json``
    #: reads as "not cropped", which is exactly what it was.
    crop_applied: bool = False
    #: True when this (uncropped) still has enough empty sky around the disk that
    #: cropping is worth offering. Always False once a crop has been applied.
    crop_available: bool = False
    #: Fraction of the full frame the crop trims, or would trim — 0.0 when there
    #: is nothing to trim or no disk was found.
    crop_trim_fraction: float = 0.0
    #: The stack's size *before* any crop. 0 means "same as width/height".
    source_width: int = 0
    source_height: int = 0


def read_meta(settings: Settings, capture_id: str) -> VideoStackMeta | None:
    """Load a capture's saved result metadata, or ``None`` if never stacked.

    Best-effort: a truncated/hand-edited ``meta.json`` reads as "no result"
    rather than breaking the page that lists captures.
    """
    path = result_dir(settings, capture_id) / META_NAME
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    try:
        known = {f: raw[f] for f in VideoStackMeta.__dataclass_fields__ if f in raw}
        return VideoStackMeta(**known)  # type: ignore[arg-type]
    except TypeError:
        log.debug("video meta for %s is missing fields; ignoring", capture_id)
        return None


@dataclass
class VideoGradeMeta:
    """A grade-only pass: what the capture's frames look like, no stack made."""

    capture_id: str
    source_name: str
    created_utc: str
    n_graded: int
    stride: int
    scores: list[float]
    warnings: list[str] = field(default_factory=list)


def read_grade(settings: Settings, capture_id: str) -> VideoGradeMeta | None:
    """Load a capture's saved grade-only pass, or ``None`` if never checked.

    Best-effort in the same way as :func:`read_meta`: a truncated or
    hand-edited file reads as "never checked" rather than breaking the page.
    """
    path = result_dir(settings, capture_id) / GRADE_NAME
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    try:
        known = {f: raw[f] for f in VideoGradeMeta.__dataclass_fields__ if f in raw}
        return VideoGradeMeta(**known)  # type: ignore[arg-type]
    except TypeError:
        log.debug("video grade for %s is missing fields; ignoring", capture_id)
        return None


def has_result(settings: Settings, capture_id: str) -> bool:
    return (result_dir(settings, capture_id) / PNG_NAME).is_file()


def iter_results(settings: Settings) -> list[VideoStackMeta]:
    """Every finished video still on disk, newest first.

    Read straight from ``<data_root>/video/`` rather than from the incoming
    folder, so a still keeps showing up after the user has cleared the source
    video off the NAS — the picture is the thing they want to find again, not
    the capture it came from.

    A folder is a "finished still" only when it has both the rendered PNG and a
    readable ``meta.json``; a half-written or hand-edited result is skipped
    exactly as :func:`read_meta` skips it for the Moon & Sun page, so no caller
    has to guess at a label or a date.
    """
    root = video_root(settings)
    try:
        entries = sorted(root.iterdir(), key=lambda p: p.name)
    except OSError:
        # No video/ directory yet (the common case on an install that has never
        # stacked one), or an unreadable one — either way there is nothing to show.
        return []
    results: list[VideoStackMeta] = []
    for entry in entries:
        if not entry.is_dir() or not (entry / PNG_NAME).is_file():
            continue
        meta = read_meta(settings, entry.name)
        if meta is not None:
            # The folder name is the addressable id (it is what
            # ``/api/videos/{id}/preview.png`` resolves), so it wins over
            # whatever the file happens to say — a hand-edited ``capture_id``
            # must not hand a caller a URL that 404s.
            results.append(replace(meta, capture_id=entry.name))
    results.sort(key=lambda m: m.created_utc, reverse=True)
    return results


def pick_source_file(capture: VideoCapture, requested_name: str | None) -> str:
    """Choose which file in the folder to stack.

    ``requested_name`` is matched against the *basenames* the discovery pass
    found — a client can never hand us a path, matching the calibration-master
    rule (paths are resolved server-side, always).
    """
    if not capture.files:
        raise ValueError("this capture folder has no video files")
    if requested_name:
        for path in capture.files:
            if Path(path).name == requested_name:
                return path
        raise ValueError(f"{requested_name!r} is not a video in this capture folder")
    # No choice made: the longest recording is almost always the real capture
    # (a stray short clip is usually a mis-tap), and size is a fair proxy.
    return max(capture.files, key=lambda p: _size_of(p))


def _size_of(path: str) -> int:
    try:
        return Path(path).stat().st_size
    except OSError:
        return 0


def _write_tiff16(path: Path, rgb) -> None:
    """16-bit TIFF of an already display-rendered image (values 0–1)."""
    import numpy as np
    import tifffile

    u16 = (np.clip(np.nan_to_num(rgb, nan=0.0), 0.0, 1.0) * 65535.0).astype(np.uint16)
    tifffile.imwrite(path, u16, photometric="rgb", compression="zlib")


def submit_video_stack(
    settings: Settings,
    jm: JobManager,
    capture_id: str,
    *,
    keep_percent: float,
    file_name: str | None = None,
    align: bool = True,
    crop: bool = False,
) -> Job:
    """Enqueue a lucky-imaging stack of one video capture."""

    def body(job: Job) -> dict[str, Any]:
        return _video_stack_body(
            settings, job, capture_id,
            keep_percent=keep_percent, file_name=file_name, align=align,
            crop=crop,
        )

    return jm.submit(JOB_KIND, body, target=capture_id)


def submit_video_grade(
    settings: Settings,
    jm: JobManager,
    capture_id: str,
    *,
    file_name: str | None = None,
) -> Job:
    """Enqueue a grade-only pass — decode once, score every frame, stack nothing.

    The cheap half of :func:`submit_video_stack`, run on its own so the user can
    see how much their capture's sharpness actually varies *before* choosing how
    ruthless to be with it. Writes only ``grade.json``; an existing stacked still
    and its metadata are left exactly as they were.
    """

    def body(job: Job) -> dict[str, Any]:
        return _video_grade_body(settings, job, capture_id, file_name=file_name)

    return jm.submit(JOB_KIND_GRADE, body, target=capture_id)


def _resolve_source(settings: Settings, capture_id: str, file_name: str | None):
    """``(capture, source path)`` for a job, or a clear failure. Server-side only."""
    if not ffmpeg_available():
        raise RuntimeError(
            "Video stacking needs ffmpeg, which isn't installed in this container. "
            "Update to a current AstroStack image (it bundles ffmpeg) and try again."
        )
    capture = find_video_capture(settings.resolved_incoming_dir, capture_id)
    if capture is None:
        raise RuntimeError(f"No video capture called {capture_id!r} in the incoming folder.")
    return capture, pick_source_file(capture, file_name)


def _video_grade_body(
    settings: Settings,
    job: Job,
    capture_id: str,
    *,
    file_name: str | None,
) -> dict[str, Any]:
    _capture, source = _resolve_source(settings, capture_id, file_name)
    job.set_progress("probe", 0, 0, f"Reading {Path(source).name}")
    info = probe_video(source)

    def on_progress(stage: str, done: int, total: int) -> None:
        job.set_progress("grade", done, total, "Grading every frame for sharpness")

    try:
        graded = grade_video(
            source, LuckyOptions(), info=info,
            progress=on_progress,
            should_cancel=job.cancel_requested,
        )
    except VideoStackCancelled:
        return {"cancelled": True, "capture_id": capture_id}

    out_dir = result_dir(settings, capture_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    meta = VideoGradeMeta(
        capture_id=capture_id,
        source_name=Path(source).name,
        created_utc=datetime.now(UTC).isoformat(timespec="seconds"),
        n_graded=graded.n_graded,
        stride=graded.stride,
        scores=[round(float(v), 6) for v in graded.scores],
        warnings=list(graded.warnings),
    )
    (out_dir / GRADE_NAME).write_text(
        json.dumps(asdict(meta), indent=2), encoding="utf-8",
    )
    return {"capture_id": capture_id, "n_graded": graded.n_graded}


def _apply_framing(display, crop: bool, label: str, warnings: list[str]):
    """Measure where the disk is, and crop to it when the user asked for that.

    Always measures (it is a threshold and two profiles on an image already in
    memory — cheap next to decoding a video twice), because the measurement is
    what lets the finished still say "there is a lot of empty sky here, want it
    trimmed?" to someone who didn't know to ask beforehand.

    Returns ``(image, framing)``. A capture with no disk to find, or one whose
    disk already fills the frame, comes back with the picture untouched — and if
    a crop *was* asked for, a plain-language line saying why it didn't happen,
    so an unchanged picture is never a silent no-op.
    """
    framing = measure_framing(display)
    if not crop:
        return display, framing
    if framing is None or not framing.worthwhile:
        warnings.append(
            f"Nothing worth cropping — the {label} already fills the frame, "
            f"so the picture was left as it is."
        )
        return display, framing
    return crop_to_disk(display, framing), framing


def _video_stack_body(
    settings: Settings,
    job: Job,
    capture_id: str,
    *,
    keep_percent: float,
    file_name: str | None,
    align: bool,
    crop: bool = False,
) -> dict[str, Any]:
    capture, source = _resolve_source(settings, capture_id, file_name)
    job.set_progress("probe", 0, 0, f"Reading {Path(source).name}")
    info = probe_video(source)

    options = LuckyOptions(keep_percent=keep_percent, align=align)

    def on_progress(stage: str, done: int, total: int) -> None:
        if stage == "grade":
            job.set_progress("grade", done, total, "Grading every frame for sharpness")
        else:
            job.set_progress("stack", done, total, f"Stacking the sharpest {total} frames")

    try:
        result = stack_video(
            source, options,
            info=info,
            progress=on_progress,
            # ``cancel_requested`` is a method, not a property — passing the
            # bound method itself would read as permanently truthy and cancel
            # every run on its first frame.
            should_cancel=job.cancel_requested,
        )
    except VideoStackCancelled:
        return {"cancelled": True, "capture_id": capture_id}

    job.set_progress("save", 0, 0, "Saving your picture")
    display = normalize_for_display(result.image)
    # Framing is measured on the *display-rendered* picture and applied after it,
    # so the tone mapping still sees the whole frame: cropping changes what is in
    # the picture, never how bright it is.
    warnings = list(result.warnings)
    display, framing = _apply_framing(display, crop, capture.label, warnings)

    out_dir = result_dir(settings, capture_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    write_full_res_png(out_dir / PNG_NAME, display)
    _write_tiff16(out_dir / TIFF_NAME, display)

    meta = VideoStackMeta(
        capture_id=capture_id,
        label=capture.label,
        kind=capture.kind,
        source_name=Path(source).name,
        created_utc=datetime.now(UTC).isoformat(timespec="seconds"),
        width=int(display.shape[1]),
        height=int(display.shape[0]),
        keep_percent=float(keep_percent),
        n_graded=result.n_graded,
        n_kept=result.n_kept,
        n_stacked=result.n_stacked,
        n_align_failed=result.n_align_failed,
        stride=result.stride,
        aligned=bool(align),
        sharpness_best=result.sharpness_best,
        sharpness_kept_median=result.sharpness_kept_median,
        sharpness_all_median=result.sharpness_all_median,
        warnings=warnings,
        scores=[round(float(v), 6) for v in result.scores],
        crop_applied=bool(crop and framing is not None and framing.worthwhile),
        crop_available=bool(not crop and framing is not None and framing.worthwhile),
        crop_trim_fraction=(
            round(framing.trim_fraction, 4)
            if framing is not None and framing.worthwhile else 0.0
        ),
        source_width=result.width,
        source_height=result.height,
    )
    (out_dir / META_NAME).write_text(
        json.dumps(asdict(meta), indent=2), encoding="utf-8",
    )
    return {
        "capture_id": capture_id,
        "n_graded": result.n_graded,
        "n_kept": result.n_kept,
        "n_stacked": result.n_stacked,
        "width": meta.width,
        "height": meta.height,
    }
