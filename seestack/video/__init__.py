"""Lucky-imaging stack of a Seestar Solar/Lunar **video** capture.

The Seestar drops its Moon/Sun captures into ``<Target>_video/`` folders as a
plain video file (``.mp4``/``.avi``/``.mov``) rather than a folder of FITS subs,
so the deep-sky path (``seestack.stack``) can't touch them — there are no stars
to plate-solve and no Bayer FITS to calibrate. This package is the **separate,
self-contained pipeline** for those: decode → grade every frame by sharpness →
keep the sharpest few → align the disk → average.

That's "lucky imaging": atmospheric seeing makes a handful of frames in any
video noticeably sharper than the rest, so throwing most of them away and
stacking only the best gives a crisper, much less noisy still than any single
frame.

Deliberately **not** reused from the deep-sky path: plate-solving (a lunar disk
has no stars), calibration masters, and the auto-edit chain (STF / SCNR /
gradient removal would wreck a bright disk). See :func:`~seestack.video.lucky.
normalize_for_display` for the gentle disk-appropriate render used instead.
"""

from seestack.video.discover import (
    VIDEO_EXTENSIONS,
    VideoCapture,
    find_video_captures,
    video_capture_id,
)
from seestack.video.ffmpeg import (
    VideoInfo,
    VideoToolsMissing,
    ffmpeg_available,
    iter_frames,
    probe_video,
)
from seestack.video.lucky import (
    GradeResult,
    LuckyOptions,
    LuckyResult,
    grade_video,
    normalize_for_display,
    stack_video,
)

__all__ = [
    "VIDEO_EXTENSIONS",
    "GradeResult",
    "LuckyOptions",
    "LuckyResult",
    "VideoCapture",
    "VideoInfo",
    "VideoToolsMissing",
    "ffmpeg_available",
    "find_video_captures",
    "grade_video",
    "iter_frames",
    "normalize_for_display",
    "probe_video",
    "stack_video",
    "video_capture_id",
]
