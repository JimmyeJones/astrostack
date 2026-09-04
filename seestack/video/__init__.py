"""Lucky-imaging stack of a Seestar Solar/Lunar **video** capture.

The Seestar drops its Moon/Sun captures into ``<Target>_video/`` folders as a
plain video file (``.mp4``/``.avi``/``.mov``) rather than a folder of FITS subs,
so the deep-sky path (``seestack.stack``) can't touch them — there are no stars
to plate-solve and no calibration masters to apply. This package is the
**separate, self-contained pipeline** for those: decode → grade every frame by
sharpness → keep the sharpest few → align the disk → average.

**The frames are still Bayer, though**, and this file used to say otherwise. A
solar or planetary capture is normally recorded as the raw sensor mosaic (that
is the point of it — lucky imaging wants unprocessed frames), so
:func:`~seestack.video.ffmpeg.iter_frames` demosaics a single-channel source on
the way out. It has to, because of a property of *this* pipeline in particular:
the disk is static and alignment shifts are near zero, so any **sensor-fixed**
pattern adds coherently across every kept frame instead of averaging down.
Stacking sharpens such an artefact rather than burying it — which is why an
undebayered mosaic showed up as a crisp mesh over the whole Sun rather than as
noise. Worth remembering for any future fixed-pattern source (hot pixels, amp
glow): here they accumulate.

That's "lucky imaging": atmospheric seeing makes a handful of frames in any
video noticeably sharper than the rest, so throwing most of them away and
stacking only the best gives a crisper, much less noisy still than any single
frame.

Deliberately **not** reused from the deep-sky path: plate-solving (a lunar disk
has no stars), calibration masters, and the auto-edit chain (STF / SCNR /
gradient removal would wreck a bright disk). See :func:`~seestack.video.lucky.
normalize_for_display` for the gentle disk-appropriate render used instead.
"""

from seestack.video.detail import SHARPEN_PRESETS, sharpen_still
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
    "SHARPEN_PRESETS",
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
    "sharpen_still",
    "stack_video",
    "video_capture_id",
]
