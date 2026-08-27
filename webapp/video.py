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
        quicklook.png ← the sharpest single frame from that pass — a two-second
                        look at what the capture actually holds, before spending
                        a full stack finding out
        stack-full.*  ← the picture as it stood before the first *in-place* edit,
                        so a crop or a sharpen is always undoable

Adding a directory alongside ``incoming/``/``library/``/``state/`` is additive:
nothing existing moves, and an install that never stacks a video never grows one.

In-place edits (the state model — read this before touching them)
-----------------------------------------------------------------
Cropping and sharpening a *finished* still both work off the saved artifacts, so
neither costs another decode of the capture. They compose, and getting that
composition wrong would lose someone's picture, so both are expressed as one
derivation from a single kept original rather than as edits layered on the file:

    stack.*  =  crop( sharpen(stack-full.*, sharpen_amount), crop_box )

``stack-full.*`` is written **once**, the first time an in-place edit happens (or
at stack time when the stack itself sharpened, so the kept copy is still the soft
one). Whatever the *stack* did — including a stack-time crop — is baked into it;
``crop_box`` describes only an in-place crop. Every operation therefore just
changes one number in ``meta.json`` and re-derives, which is what makes each of
them independently reversible:

    crop        crop_box := measured box      → derive   (keeps any sharpen)
    undo crop   crop_box := none              → derive   (keeps any sharpen)
    sharpen     sharpen_amount := a           → derive   (keeps any crop)
    unsharpen   sharpen_amount := 0           → derive   (keeps any crop)

Sharpening always starts from the kept original, never from the already-sharpened
file, so moving the slider can never compound. When neither op is active the
original is simply moved back over ``stack.*`` — byte-for-byte the render the
stack wrote — and no duplicate is left behind.

The one case this cannot serve is a still whose *stack* sharpened it before that
copy was kept (``sharpen_baked > 0``): there is no soft version to go back to, so
the strength is reported but not offered for change.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from seestack.stack.output import write_full_res_png
from seestack.video.detail import SHARPEN_MAX, sharpen_still
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
from webapp.atomicio import write_text_durably
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
#: The sharpest single frame of that pass, display-rendered. Same reasoning as
#: ``grade.json``: it is written by the *check*, never by the stack, so looking
#: at a capture leaves any finished still exactly as it was.
QUICKLOOK_NAME = "quicklook.png"


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
    #: True once the framing has actually been measured for this still. False on
    #: a ``meta.json`` written before framing existed — where ``crop_available``
    #: is False because nobody ever looked, not because there is nothing to trim.
    #: :func:`ensure_framing_measured` tells those two apart and fills it in.
    crop_measured: bool = False
    #: How hard this still was sharpened after stacking (0 = not at all, which is
    #: the default and what every ``meta.json`` written before sharpening existed
    #: reads as). Recorded so the picture can say so rather than leaving the owner
    #: wondering why one Moon looks crisper than the last. This is the amount
    #: *currently* applied to the picture, whichever way it got there.
    sharpen_amount: float = 0.0
    #: How much of that is already baked into the kept original (``stack-full.*``)
    #: and therefore cannot be taken back off. Zero for everything the current
    #: version writes — the stack keeps the *soft* render — and non-zero only for
    #: a still sharpened at stack time by a version that kept no copy, which is
    #: exactly the case where the strength can be reported but not changed.
    sharpen_baked: float = 0.0
    #: The in-place crop's box as ``[y0, x0, y1, x1]`` in the kept original's
    #: pixels, so the picture can be re-derived when something else about it
    #: changes. Empty when no in-place crop is applied. A still cropped in place
    #: by an older version has none; the box is re-measured from the original in
    #: that case, which is deterministic on the same picture.
    crop_box: list[int] = field(default_factory=list)


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
    #: Where the sharpest frame sat in ``scores`` (``-1`` when unknown). Optional
    #: and defaulted so a ``grade.json`` written before the quick look existed
    #: still loads — it simply has no frame to point at.
    best_index: int = -1
    #: Size and modification time of the file that was graded, so a check can
    #: tell whether it still describes the clip on disk. The Seestar writes each
    #: night's capture into the *same* ``<Target>_video/`` folder, so re-recording
    #: replaces ``clip.mp4`` in place while the capture id stays put — without
    #: this stamp last night's scores, advice and quick look would stay on screen
    #: as if they described tonight's clip. Both optional and defaulted to 0,
    #: which reads as "unknown" and is deliberately trusted (see
    #: :func:`grade_matches_source`): an upgrade must never hide a panel that has
    #: been there all along.
    source_size: int = 0
    source_mtime: float = 0.0


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


#: How far apart two modification times may be and still count as the same file.
#: A second of slack costs nothing (a re-recording changes the mtime by minutes at
#: least) and absorbs the coarser timestamp granularity some network filesystems
#: report, which would otherwise invalidate a perfectly good check.
_MTIME_TOLERANCE_S = 1.0


def source_stamp(path: str | Path) -> tuple[int, float]:
    """``(size, mtime)`` of a video file, or ``(0, 0.0)`` when it can't be read.

    ``(0, 0.0)`` is the same "unknown" the older ``grade.json`` files carry, so a
    filesystem that reports no usable stat degrades to today's behaviour —
    trusting the check — rather than to hiding one.
    """
    try:
        st = Path(path).stat()
    except OSError:
        return 0, 0.0
    return int(st.st_size), round(float(st.st_mtime), 3)


def grade_matches_source(meta: VideoGradeMeta, files: list[str]) -> bool:
    """Does a saved check still describe the clip that is on disk?

    Only ever returns ``False`` on a *positive* mismatch — the graded file is
    among ``files``, both stamps are readable, and they disagree. Everything
    else ("unknown" stamp from an older version, the named file not in this
    folder, an unreadable stat) counts as a match, because the cost of the two
    mistakes is not symmetric: showing a stale curve is a small dishonesty,
    while hiding a good one on upgrade would take a panel away from every
    capture the owner has already checked.
    """
    if not meta.source_size and not meta.source_mtime:
        return True
    match = next((f for f in files if Path(f).name == meta.source_name), None)
    if match is None:
        return True
    size, mtime = source_stamp(match)
    if not size and not mtime:
        return True
    return (
        size == meta.source_size
        and abs(mtime - meta.source_mtime) <= _MTIME_TOLERANCE_S
    )


def has_result(settings: Settings, capture_id: str) -> bool:
    return (result_dir(settings, capture_id) / PNG_NAME).is_file()


def has_quicklook(settings: Settings, capture_id: str) -> bool:
    """True when the grade pass's sharpest-frame picture is on disk.

    Asked before the frame is offered, so a grade recorded by an older version
    (which kept the scores but no picture) shows its curve without a broken
    image beside it.
    """
    return (result_dir(settings, capture_id) / QUICKLOOK_NAME).is_file()


def has_tiff(settings: Settings, capture_id: str) -> bool:
    """True when the 16-bit TIFF of this still is on disk.

    Every still stacked since the feature shipped has one, but a half-written
    result can have the PNG without it — so a surface that *offers* the TIFF
    download asks first rather than handing the user a link that 404s.
    """
    return (result_dir(settings, capture_id) / TIFF_NAME).is_file()


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


def count_results(settings: Settings) -> int:
    """How many finished video stills exist — a directory listing, nothing more.

    Deliberately cheaper than :func:`iter_results`: it never opens a
    ``meta.json``, because the only caller (the Dashboard's stats roll-up, which
    the home page polls) needs the *count* to answer "does this user have a
    picture yet?" and nothing else. An install that has never stacked a video
    has no ``video/`` directory and this is a single failed ``iterdir``.
    """
    try:
        entries = list(video_root(settings).iterdir())
    except OSError:
        return 0
    return sum(1 for e in entries if e.is_dir() and (e / PNG_NAME).is_file())


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


# --- Cropping a still that already exists -----------------------------------
#
# Trimming the empty sky is a decision about *framing*, and framing is decided
# by looking at the picture — which means the offer only lands once the still
# exists. Re-stacking to act on it would decode a multi-minute capture a second
# time to change nothing but the crop box, and by then the source video may not
# even be on the NAS any more. So the crop is done on the saved artifacts.
#
# It is exactly as honest as the re-stack: the box is measured on the same
# display-rendered picture, and cropping is a per-pixel-independent slice, so
# trimming the saved PNG gives byte-for-byte the pixels a re-stack with
# ``crop=True`` would have written.


class StillCropError(ValueError):
    """A crop/restore that can't be done, with a line the user can act on."""


#: The picture as it stood before the first in-place edit, kept beside the edited
#: one so every such edit is undoable (see the state model in the module
#: docstring). Written only when one actually happens, so an install that never
#: crops or sharpens a finished still never grows them.
FULL_PNG_NAME = "stack-full.png"
FULL_TIFF_NAME = "stack-full.tiff"


def has_full_frame_backup(settings: Settings, capture_id: str) -> bool:
    """True when a still's pre-edit original is still on disk."""
    return (result_dir(settings, capture_id) / FULL_PNG_NAME).is_file()


def _backup_size(out_dir: Path) -> tuple[int, int] | None:
    """``(width, height)`` of the kept original, or ``None`` if it can't be read.

    One PNG header read — the file's own dimensions are what separate the two
    shapes a kept original can have (see :func:`_backup_is_already_framed`).
    """
    path = out_dir / FULL_PNG_NAME
    if not path.is_file():
        return None
    from PIL import Image

    try:
        with Image.open(path) as img:
            return int(img.size[0]), int(img.size[1])
    except (OSError, ValueError):
        return None


def _backup_is_already_framed(out_dir: Path, meta: VideoStackMeta) -> bool:
    """Whether the kept original already carries the picture's current framing.

    Two very different things end up at ``stack-full.*`` for a cropped still, and
    only their *size* tells them apart:

    * a crop the **stack** applied keeps the *soft* render of the **cropped**
      picture, so the backup is the same size as the picture beside it — there
      is no box to re-apply, and re-measuring one would trim it a second time;
    * an in-place crop keeps the **full frame** it trimmed, which is bigger — a
      rebuild has to re-apply the box or the crop is lost.
    """
    size = _backup_size(out_dir)
    if size is None:
        return False
    width, height = size
    return width <= meta.width and height <= meta.height


def crop_is_restorable(
    settings: Settings, capture_id: str, meta: VideoStackMeta | None,
) -> bool:
    """Whether "Undo crop" would actually give the user a bigger picture back.

    The kept original is now taken by the *first* in-place edit, whichever it is,
    so its mere existence no longer proves there is a crop to undo: a still the
    **stack** cropped and the user then sharpened has one, and it holds the same
    framing the picture already has. Asking the file how big it is answers the
    question exactly, and costs one PNG header read.
    """
    if meta is None or not meta.crop_applied:
        return False
    size = _backup_size(result_dir(settings, capture_id))
    if size is None:
        return False
    width, height = size
    return width > meta.width or height > meta.height


def can_resharpen(meta: VideoStackMeta | None) -> bool:
    """Whether this still's sharpening can still be changed without re-stacking.

    False only for a picture whose stack sharpened it before the soft render was
    kept beside it — there is nothing to go back to, so offering a strength that
    would compound on top of the baked one would be a lie.
    """
    return meta is not None and float(meta.sharpen_baked or 0.0) <= 0.0


def _clear_full_frame_backup(out_dir: Path) -> None:
    """Drop the kept originals.

    Called whenever a *new* still is written: the backup exists to undo an
    in-place crop of the picture that was there, so once that picture has been
    replaced it would restore someone else's render.
    """
    for stale in (out_dir / FULL_PNG_NAME, out_dir / FULL_TIFF_NAME):
        stale.unlink(missing_ok=True)


def _read_png(path: Path):
    """A saved PNG as a 0–1 float image, or ``None`` if it can't be read."""
    import numpy as np
    from PIL import Image

    try:
        with Image.open(path) as img:
            arr = np.asarray(img.convert("RGB"), dtype=np.float32)
    except (OSError, ValueError):
        return None
    return arr / 255.0


def _read_display(out_dir: Path, png_name: str, tiff_name: str):
    """A saved picture as a 0–1 float image, preferring its 16-bit TIFF.

    The TIFF is the same display render at higher precision, so measuring on it
    is what the crop has always done; the PNG keeps a result saved before TIFFs
    existed measurable.
    """
    tiff_path = out_dir / tiff_name
    if tiff_path.is_file():
        try:
            import numpy as np
            import tifffile

            return np.asarray(tifffile.imread(tiff_path), dtype=np.float32) / 65535.0
        except (OSError, ValueError):
            pass
    return _read_png(out_dir / png_name)


def _ensure_orig_backup(out_dir: Path) -> None:
    """Keep the picture as it is now, so an in-place edit can be undone.

    A no-op once the copy exists: the original is whatever stood there before the
    *first* edit, and re-taking it after a crop would freeze the cropped picture
    as the thing every later undo restores.
    """
    import shutil

    if (out_dir / FULL_PNG_NAME).is_file():
        return
    shutil.copy2(out_dir / PNG_NAME, out_dir / FULL_PNG_NAME)
    if (out_dir / TIFF_NAME).is_file():
        shutil.copy2(out_dir / TIFF_NAME, out_dir / FULL_TIFF_NAME)


def _rebuild_still(
    out_dir: Path, *, sharpen: float, box: tuple[int, int, int, int] | None,
) -> tuple[int, int]:
    """Re-derive ``stack.*`` from the kept original. Returns ``(height, width)``.

    Three paths, deliberately, because "nothing to apply" and "crop only" both
    have an exact answer that a float round-trip would spoil:

    * **Neither op** — the original is *moved* back over ``stack.*``, which
      restores the stack's own render byte-for-byte and leaves no duplicate.
    * **Crop only** — each artifact is sliced in its own integer domain, so the
      cropped PNG holds exactly the 8-bit values the original held (and likewise
      the 16-bit TIFF). Nothing is re-quantised.
    * **Sharpened** — the values change anyway, so this one is a real render.
      Each artifact is still derived from its *own* original, so the 16-bit TIFF
      that anyone editing elsewhere downloads is sharpened at full precision
      rather than from the 8-bit picture beside it.

    Every write lands on a temporary first and is swapped in, so a failure part
    way through leaves the picture that was already there.
    """
    import numpy as np
    from PIL import Image

    png_path = out_dir / PNG_NAME
    tiff_path = out_dir / TIFF_NAME
    full_png = out_dir / FULL_PNG_NAME
    full_tiff = out_dir / FULL_TIFF_NAME

    if sharpen <= 0 and box is None:
        with Image.open(full_png) as img:
            width, height = img.size
        full_png.replace(png_path)
        if full_tiff.is_file():
            full_tiff.replace(tiff_path)
        return int(height), int(width)

    if sharpen <= 0:
        y0, x0, y1, x1 = box  # type: ignore[misc]
        tmp_png = out_dir / (PNG_NAME + ".part")
        with Image.open(full_png) as img:
            img.convert("RGB").crop((x0, y0, x1, y1)).save(tmp_png, format="PNG")
        tmp_png.replace(png_path)
        if full_tiff.is_file():
            import tifffile

            arr = np.asarray(tifffile.imread(full_tiff))
            tmp_tiff = out_dir / (TIFF_NAME + ".part")
            tifffile.imwrite(
                tmp_tiff, arr[y0:y1, x0:x1], photometric="rgb", compression="zlib",
            )
            tmp_tiff.replace(tiff_path)
        return int(y1 - y0), int(x1 - x0)

    def derive(arr):
        out = sharpen_still(arr, sharpen)
        if box is not None:
            y0, x0, y1, x1 = box
            out = out[y0:y1, x0:x1]
        return out

    with Image.open(full_png) as img:
        src8 = np.asarray(img.convert("RGB"), dtype=np.float32) / 255.0
    derived = derive(src8)
    tmp_png = out_dir / (PNG_NAME + ".part")
    write_full_res_png(tmp_png, derived)
    tmp_png.replace(png_path)

    if full_tiff.is_file():
        import tifffile

        src16 = np.asarray(tifffile.imread(full_tiff), dtype=np.float32) / 65535.0
        tmp_tiff = out_dir / (TIFF_NAME + ".part")
        _write_tiff16(tmp_tiff, derive(src16))
        tmp_tiff.replace(tiff_path)
    return int(derived.shape[0]), int(derived.shape[1])


def _measured_box(out_dir: Path, meta: VideoStackMeta):
    """The in-place crop's box, re-measured from the original when unrecorded.

    A still cropped by a version that didn't record the box still has to be
    re-derivable, and ``measure_framing`` is deterministic on the same picture —
    it is what chose the box in the first place. Returns ``None`` when this still
    isn't cropped in place, or when the box can no longer be established.
    """
    if not meta.crop_applied:
        return None
    if len(meta.crop_box) == 4:
        return tuple(int(v) for v in meta.crop_box)  # type: ignore[return-value]
    if not (out_dir / FULL_PNG_NAME).is_file():
        return None
    display = _read_display(out_dir, FULL_PNG_NAME, FULL_TIFF_NAME)
    if display is None:
        return None
    framing = measure_framing(display)
    if framing is None or not framing.worthwhile:
        return None
    return tuple(int(v) for v in framing.box)


def ensure_framing_measured(
    settings: Settings, capture_id: str, meta: VideoStackMeta,
) -> VideoStackMeta:
    """Measure the framing of a still that was stacked before framing existed.

    A picture made by an older version has no ``crop_*`` fields at all, so it
    reads as "nothing to trim" when the truth is that nobody ever looked — and
    since the offer is what makes the crop discoverable, those pictures would
    never get one. Now that cropping works off the saved artifacts, the
    measurement can be made from the picture itself, so the owner's existing
    Moon stills are treated exactly like a new one.

    Measured once and written back (the fields are additive; nothing else in the
    file is touched), so this costs one image read per pre-existing still, ever.
    Best-effort: an unreadable picture or a read-only volume leaves the metadata
    as it was rather than failing the page that asked for it.
    """
    if meta.crop_measured or meta.crop_applied:
        return meta
    out_dir = result_dir(settings, capture_id)
    display = _read_png(out_dir / PNG_NAME)
    if display is None:
        return meta
    framing = measure_framing(display)
    worthwhile = framing is not None and framing.worthwhile
    updated = replace(
        meta,
        crop_measured=True,
        crop_available=bool(worthwhile),
        crop_trim_fraction=(
            round(framing.trim_fraction, 4) if worthwhile and framing else 0.0
        ),
    )
    try:
        _write_meta(out_dir, updated)
    except OSError:
        log.debug("could not record the framing for %s", capture_id, exc_info=True)
    return updated


def crop_saved_still(settings: Settings, capture_id: str) -> VideoStackMeta:
    """Trim a finished still to its disk, without decoding the video again.

    Raises :class:`StillCropError` when there is nothing to do — no picture yet,
    already cropped, or no disk with enough sky around it to be worth trimming —
    so the caller always has a sentence to show rather than a silent no-op.
    """
    meta = read_meta(settings, capture_id)
    out_dir = result_dir(settings, capture_id)
    if meta is None or not (out_dir / PNG_NAME).is_file():
        raise StillCropError("There's no finished picture for this capture yet.")
    if meta.crop_applied:
        raise StillCropError("This picture has already been cropped.")

    # Measured on the picture as it stands, which is what the user is looking at
    # and asking to trim — the same thing a re-stack would have measured.
    display = _read_display(out_dir, PNG_NAME, TIFF_NAME)
    if display is None:
        raise StillCropError(
            "This picture couldn't be read back — stack the capture again."
        )

    framing = measure_framing(display)
    if framing is None or not framing.worthwhile:
        raise StillCropError(
            "Nothing worth cropping — the subject already fills the frame, "
            "so the picture was left as it is."
        )

    # Keep the pre-edit picture so the crop is reversible, then derive. The box
    # is measured on the current picture but recorded against the original —
    # they are the same picture whenever no sharpen has been applied, and when
    # one has, the sharpen doesn't move the disk it was measured from.
    _ensure_orig_backup(out_dir)
    box = tuple(int(v) for v in framing.box)
    height, width = _rebuild_still(out_dir, sharpen=_applied_sharpen(meta), box=box)
    updated = replace(
        meta,
        width=int(width),
        height=int(height),
        # The pre-crop size is the stack's own — keep whatever an earlier crop
        # recorded, and fall back to the size this picture had a moment ago.
        source_width=meta.source_width or meta.width,
        source_height=meta.source_height or meta.height,
        crop_applied=True,
        crop_available=False,
        crop_measured=True,
        crop_trim_fraction=round(framing.trim_fraction, 4),
        crop_box=list(box),
    )
    _write_meta(out_dir, updated)
    return updated


def _applied_sharpen(meta: VideoStackMeta) -> float:
    """How much sharpening a rebuild has to *re-apply* to the kept original.

    Zero when the original already carries it (``sharpen_baked``): that picture
    can be cropped and uncropped freely, it simply can't be un-sharpened.
    """
    if float(meta.sharpen_baked or 0.0) > 0.0:
        return 0.0
    return float(meta.sharpen_amount or 0.0)


def sharpen_saved_still(
    settings: Settings, capture_id: str, amount: float,
) -> VideoStackMeta:
    """Change how hard a finished still is sharpened, without decoding again.

    Always rendered from the kept original, never from the picture on disk, so
    moving between strengths — or back to none — can never compound. ``amount``
    of 0 removes the sharpening entirely.
    """
    meta = read_meta(settings, capture_id)
    out_dir = result_dir(settings, capture_id)
    if meta is None or not (out_dir / PNG_NAME).is_file():
        raise StillCropError("There's no finished picture for this capture yet.")
    if not can_resharpen(meta):
        raise StillCropError(
            "This picture was sharpened while it was being stacked, so the "
            "unsharpened version isn't saved beside it — stack the capture "
            "again to change how sharp it is."
        )
    a = float(amount)
    if not (a >= 0.0) or a > SHARPEN_MAX:
        raise StillCropError(
            f"Sharpening has to be between 0 and {SHARPEN_MAX:g}."
        )
    if abs(a - float(meta.sharpen_amount or 0.0)) < 1e-9:
        raise StillCropError("This picture is already sharpened by that much.")

    # Worked out *before* the original is kept, because taking that copy is what
    # would make an unanswerable crop look answerable. A box is only wanted when
    # the kept original is the *bigger, uncropped* frame an in-place crop trimmed;
    # a crop the **stack** applied is already carried by the picture the rebuild
    # starts from — whether that is the cropped soft render it kept beside it, or
    # (with no original at all) the finished picture on disk, which is its own
    # original. Re-measuring a box in either of those cases would crop it twice.
    box = None
    if meta.crop_applied and not _backup_is_already_framed(out_dir, meta):
        if (out_dir / FULL_PNG_NAME).is_file():
            box = _measured_box(out_dir, meta)
            if box is None:
                raise StillCropError(
                    "This picture's crop can't be worked out any more, so "
                    "changing the sharpening would lose it — stack the capture "
                    "again instead."
                )
    _ensure_orig_backup(out_dir)
    height, width = _rebuild_still(out_dir, sharpen=a, box=box)
    updated = replace(
        meta,
        width=int(width),
        height=int(height),
        sharpen_amount=a,
        # Recorded now if it wasn't before, so a later rebuild reproduces this
        # crop exactly rather than re-measuring a sharpened picture. A box we
        # deliberately didn't re-apply is left recorded rather than cleared.
        crop_box=list(box) if box is not None else list(meta.crop_box),
    )
    _write_meta(out_dir, updated)
    return updated


def restore_full_still(settings: Settings, capture_id: str) -> VideoStackMeta:
    """Put the full frame back, undoing :func:`crop_saved_still`.

    Any sharpening survives — it is re-applied to the restored frame, because
    "undo the crop" is not a request to change how sharp the picture is. With
    nothing left to apply the original is simply moved back, so an uncropped,
    unsharpened still leaves no duplicate behind and "can this be undone?" stays
    a simple question of whether the backup is there.
    """
    meta = read_meta(settings, capture_id)
    out_dir = result_dir(settings, capture_id)
    if meta is None:
        raise StillCropError("There's no finished picture for this capture yet.")
    if not (out_dir / FULL_PNG_NAME).is_file():
        raise StillCropError(
            "The full-frame version of this picture isn't saved — stack the "
            "capture again to get it back."
        )
    if meta.crop_applied and _backup_is_already_framed(out_dir, meta):
        # The kept original is the *cropped* soft render, not the full frame —
        # this crop was applied while stacking, so there is nothing bigger to go
        # back to. ``crop_is_restorable`` already hides the offer; refusing here
        # keeps a direct request from quietly relabelling the picture uncropped
        # (and dropping the original the sharpening still needs).
        raise StillCropError(
            "This picture was cropped while it was being stacked, so the full "
            "frame isn't saved beside it — stack the capture again without "
            "cropping to get it back."
        )

    height, width = _rebuild_still(out_dir, sharpen=_applied_sharpen(meta), box=None)
    display = _read_display(out_dir, PNG_NAME, TIFF_NAME)
    framing = measure_framing(display) if display is not None else None
    worthwhile = framing is not None and framing.worthwhile
    updated = replace(
        meta,
        width=int(width),
        height=int(height),
        source_width=0,
        source_height=0,
        crop_applied=False,
        crop_box=[],
        # Re-measured rather than assumed, so the offer that comes back is the
        # honest one for the picture now on disk.
        crop_available=bool(worthwhile),
        crop_measured=True,
        crop_trim_fraction=(
            round(framing.trim_fraction, 4) if worthwhile and framing else 0.0
        ),
    )
    _write_meta(out_dir, updated)
    return updated


def _write_meta(out_dir: Path, meta: VideoStackMeta) -> None:
    """Save a still's result metadata, atomically and durably.

    This file is what makes a finished picture *findable*: without a readable
    ``meta.json`` the still drops off the Moon & Sun page and out of the Gallery
    even though ``stack.png`` and the 16-bit TIFF are sitting right beside it —
    and the only way back is another multi-minute decode of a capture the owner
    may already have cleared off the NAS. It is also rewritten in place every
    time a crop or a re-sharpen changes the picture, so a crash lands in that
    window far more often than the once-per-stack write suggests.

    :func:`webapp.atomicio.write_text_durably` makes the swap atomic (a partial
    write is never observable) and the contents durable before the rename
    publishes them.
    """
    write_text_durably(
        out_dir / META_NAME, json.dumps(asdict(meta), indent=2), suffix=".json.tmp",
    )


def submit_video_stack(
    settings: Settings,
    jm: JobManager,
    capture_id: str,
    *,
    keep_percent: float,
    file_name: str | None = None,
    align: bool = True,
    crop: bool = False,
    sharpen: float = 0.0,
) -> Job:
    """Enqueue a lucky-imaging stack of one video capture."""

    def body(job: Job) -> dict[str, Any]:
        return _video_stack_body(
            settings, job, capture_id,
            keep_percent=keep_percent, file_name=file_name, align=align,
            crop=crop, sharpen=sharpen,
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
            # The sharpest frame comes back with the scores, off the same decode
            # — so "what does this capture actually look like?" costs one held
            # frame rather than a third pass over the file.
            keep_best_frame=True,
        )
    except VideoStackCancelled:
        return {"cancelled": True, "capture_id": capture_id}

    out_dir = result_dir(settings, capture_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_quicklook(out_dir, graded.best_frame)
    # Stamped from the file we just finished reading, so re-recording over it
    # later is detectable — see ``grade_matches_source``.
    source_size, source_mtime = source_stamp(source)
    meta = VideoGradeMeta(
        capture_id=capture_id,
        source_name=Path(source).name,
        created_utc=datetime.now(UTC).isoformat(timespec="seconds"),
        n_graded=graded.n_graded,
        stride=graded.stride,
        scores=[round(float(v), 6) for v in graded.scores],
        warnings=list(graded.warnings),
        best_index=int(graded.best_index),
        source_size=source_size,
        source_mtime=source_mtime,
    )
    # Same reasoning as ``_write_meta``: losing this to a half-write costs the
    # owner the grade pass they waited a full decode for.
    write_text_durably(
        out_dir / GRADE_NAME, json.dumps(asdict(meta), indent=2), suffix=".json.tmp",
    )
    return {"capture_id": capture_id, "n_graded": graded.n_graded}


def _write_quicklook(out_dir: Path, frame) -> None:
    """Save the grade pass's sharpest frame as the quick look, best-effort.

    Rendered with the *same* :func:`normalize_for_display` the finished still
    uses, so the quick look is a fair preview of what the stack will look like —
    one frame's worth of noise apart — rather than a differently-toned picture
    the user then has to reconcile with the result.

    A failure here leaves the grade itself intact: the scores and the advice are
    the substance of a check, and losing the picture must not lose them. Any
    stale quick look from an earlier check is cleared first, so what is on disk
    always belongs to the scores beside it.
    """
    path = out_dir / QUICKLOOK_NAME
    path.unlink(missing_ok=True)
    if frame is None:
        return
    import numpy as np

    try:
        rgb = np.asarray(frame, dtype=np.float32) / 255.0
        write_full_res_png(path, normalize_for_display(rgb))
    except (OSError, ValueError):
        log.debug("could not write the quick look for %s", out_dir.name, exc_info=True)
        path.unlink(missing_ok=True)


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
    sharpen: float = 0.0,
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
    soft = normalize_for_display(result.image)
    # Stacking is an average, and averaging is a low-pass filter — so the last
    # step of every planetary workflow is a sharpen. Done on the *whole* frame,
    # before any crop, so every pixel is sharpened against its real neighbours
    # rather than against a reflected crop edge. A zero amount returns the array
    # untouched, so the default path is byte-for-byte the render it always was.
    display = sharpen_still(soft, sharpen)
    # Framing is measured on the *display-rendered* picture and applied after it,
    # so the tone mapping still sees the whole frame: cropping changes what is in
    # the picture, never how bright it is. Measuring the sharpened picture is
    # deliberate — it is the one saved to disk, so a crop offered now and a crop
    # taken later from the saved artifacts see the same thing.
    warnings = list(result.warnings)
    display, framing = _apply_framing(display, crop, capture.label, warnings)

    out_dir = result_dir(settings, capture_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    write_full_res_png(out_dir / PNG_NAME, display)
    _write_tiff16(out_dir / TIFF_NAME, display)
    _clear_full_frame_backup(out_dir)
    if sharpen > 0:
        # Keep the *soft* render (with the same framing) beside the sharpened
        # one, so the strength stays changeable afterwards without decoding the
        # capture a second time. Only when it would differ: an unsharpened stack
        # is its own original and grows no second copy.
        soft_saved = crop_to_disk(soft, framing) if (
            crop and framing is not None and framing.worthwhile
        ) else soft
        write_full_res_png(out_dir / FULL_PNG_NAME, soft_saved)
        _write_tiff16(out_dir / FULL_TIFF_NAME, soft_saved)

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
        # The framing *was* looked at here, whatever it found — so this still
        # never needs the one-off backfill in ``ensure_framing_measured``.
        crop_measured=True,
        sharpen_amount=float(sharpen),
        # Zero: the copy kept beside a sharpened still is the *soft* render,
        # so the strength stays changeable from here on.
        sharpen_baked=0.0,
    )
    _write_meta(out_dir, meta)
    return {
        "capture_id": capture_id,
        "n_graded": result.n_graded,
        "n_kept": result.n_kept,
        "n_stacked": result.n_stacked,
        "width": meta.width,
        "height": meta.height,
    }
