"""Lucky-imaging stack: video in, one sharp Moon/Sun still out.

Seeing makes a handful of frames in any planetary/lunar video noticeably
sharper than the rest, so the classic recipe (AutoStakkert, RegiStax, Siril's
ser processing) is: grade every frame, throw most of them away, align what's
left on the disk, and average. Averaging *N* frames cuts the noise ~√N while
keeping only the sharp ones keeps the detail — much better than either one
lucky frame (noisy) or all of them (soft).

Two passes, both streaming
--------------------------
A minute of 1080p is ~1800 frames / ~11 GB of pixels, so we never hold the
video in RAM:

1. **Grade.** Decode once, scoring each frame's sharpness and keeping only the
   scalar score. Memory: one frame.
2. **Stack.** Decode again, and for the frames that made the cut, align to the
   first kept frame and add into a NaN-aware accumulator. Memory: a handful of
   full-frame canvases regardless of video length.

Decoding twice is cheaper than the alternatives (holding the best *N* frames
needs *N* frames of RAM; a single pass can't know what "best" means yet) and
keeps the memory bound flat, which is what matters on the NAS.

Deliberately simple (beginner scope): whole-disk alignment, no multi-point
alignment, no derotation, no drizzle. The result flows into the normal editor
if the user wants to sharpen further.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from seestack.stack.accumulator import WeightedSumAccumulator
from seestack.video.ffmpeg import VideoInfo, iter_frames, probe_video

log = logging.getLogger(__name__)

#: Rec.601 luma weights — the same ones the deep-sky aligner uses for its
#: phase-correlation patch, so "sharpness" and "alignment" read the same channel.
_LUMA = (0.299, 0.587, 0.114)

#: Alignment shifts larger than this fraction of the frame's short edge are
#: treated as a failed correlation (a cloud, a dropped frame, the disk leaving
#: the field) rather than real drift, and the frame is skipped instead of being
#: smeared into the stack.
_MAX_SHIFT_FRACTION = 0.15

#: Frames we refuse to work below — a 2-frame "video" has nothing to be lucky
#: about, and the sharpness ranking would be meaningless.
MIN_FRAMES = 3


@dataclass(frozen=True)
class LuckyOptions:
    """User-facing knobs. Every default is chosen to need no explanation."""

    #: Keep the sharpest N% of frames. The classic lucky-imaging trade-off:
    #: lower = sharper but noisier, higher = smoother but softer. 30% is the
    #: usual sweet spot for a steady night and is what AutoStakkert-style
    #: tutorials start beginners on.
    keep_percent: float = 30.0
    #: Never grade more than this many frames — a long capture is evenly
    #: sampled down to it (seeing varies slowly, so an even sample still finds
    #: the good moments). Bounds the run time of a multi-minute video.
    max_frames: int = 1500
    #: Align each kept frame to the first one before averaging. Off gives a
    #: plain average of the sharpest frames (useful only if alignment misfires).
    align: bool = True

    def __post_init__(self) -> None:
        if not (1.0 <= self.keep_percent <= 100.0):
            raise ValueError("keep_percent must be between 1 and 100")
        if self.max_frames < MIN_FRAMES:
            raise ValueError(f"max_frames must be at least {MIN_FRAMES}")


@dataclass
class GradeResult:
    """Pass 1 on its own: every frame's sharpness, and nothing else.

    Grading is the cheap half of a lucky-imaging stack — it decodes once and
    keeps a scalar per frame — so it can be run *before* committing to a stack,
    to answer "how picky should I be with this capture?" while the answer can
    still change what happens. :func:`stack_video` runs it internally too, so
    there is exactly one grading pass in the codebase.
    """

    #: Every graded frame's sharpness, in capture order.
    scores: tuple[float, ...]
    #: Frames actually decoded and graded (after ``max_frames`` sampling).
    n_graded: int
    #: 1 = every frame graded; >1 = the capture was evenly sampled down.
    stride: int
    width: int
    height: int
    source: str = ""
    warnings: list[str] = field(default_factory=list)


@dataclass
class LuckyResult:
    """The stacked still plus the numbers needed to explain it to the user."""

    #: (H, W, 3) float32 mean of the aligned kept frames, in the decoder's 0–1
    #: range. Uncovered pixels (vacated by an alignment shift) are NaN, matching
    #: the engine-wide "NaN = no coverage" rule.
    image: np.ndarray
    width: int
    height: int
    #: Frames actually decoded and graded (after ``max_frames`` sampling).
    n_graded: int
    #: Frames that made the sharpness cut.
    n_kept: int
    #: Of those, how many were successfully aligned and added.
    n_stacked: int
    #: Kept frames dropped because their measured shift was implausibly large.
    n_align_failed: int
    #: 1 = every frame graded; >1 = the capture was evenly sampled down.
    stride: int
    #: Sharpness of the best frame and the median of the kept set, on the
    #: arbitrary-but-monotonic scale of :func:`frame_sharpness`. Their ratio is
    #: what makes "we kept the sharpest 30%" concrete.
    sharpness_best: float
    sharpness_kept_median: float
    sharpness_all_median: float
    #: Which graded frames made the cut (indices into the *sampled* sequence,
    #: ascending). Exposed so the choice is inspectable rather than magic.
    kept_indices: tuple[int, ...] = ()
    #: Every graded frame's sharpness, in capture order. The grading pass computes
    #: these anyway and used to drop them on the floor; keeping them is what lets
    #: :mod:`seestack.video.quality` show the user how steady their capture was and
    #: whether a different keep-% would suit it better.
    scores: tuple[float, ...] = ()
    source: str = ""
    warnings: list[str] = field(default_factory=list)

    @property
    def noise_gain(self) -> float:
        """Roughly how much cleaner than a single frame this is (√N)."""
        return math.sqrt(max(1, self.n_stacked))


class VideoStackCancelled(RuntimeError):
    """Raised out of :func:`stack_video` when ``should_cancel`` goes true."""


def frame_luma(frame: np.ndarray) -> np.ndarray:
    """Rec.601 luma of an (H, W, 3) frame as float32."""
    f = frame.astype(np.float32, copy=False)
    return (_LUMA[0] * f[..., 0] + _LUMA[1] * f[..., 1] + _LUMA[2] * f[..., 2])


def frame_sharpness(luma: np.ndarray) -> float:
    """Exposure-invariant sharpness score for one frame (higher = sharper).

    Mean squared Laplacian — the standard "is this in focus?" measure — divided
    by the frame's mean brightness squared. The normalisation matters here: a
    thin cloud or the Seestar's auto-exposure can change a lunar capture's
    overall level between frames, and an un-normalised Laplacian would then rank
    the *brightest* frames as the sharpest rather than the crispest ones.
    """
    from scipy.ndimage import laplace

    lap = laplace(luma.astype(np.float32, copy=False))
    energy = float(np.mean(lap.astype(np.float64) ** 2))
    mean = float(np.mean(luma.astype(np.float64)))
    if not math.isfinite(energy) or mean <= 0:
        return 0.0
    return energy / (mean * mean)


def _sampling_stride(n_frames: int, max_frames: int) -> int:
    """Even-sampling stride so at most ``max_frames`` frames are graded."""
    if n_frames <= 0 or n_frames <= max_frames:
        return 1
    return int(math.ceil(n_frames / max_frames))


def _measure_shift(ref_luma: np.ndarray, luma: np.ndarray) -> tuple[float, float] | None:
    """Sub-pixel (dy, dx) that brings ``luma`` onto ``ref_luma``, or ``None``.

    Phase cross-correlation on the whole frame: a lunar/solar disk is a single
    high-contrast object filling much of the field, so a global correlation
    locks onto it far more reliably than any star-based method would (there are
    no stars). Returns ``None`` when scikit-image is unavailable or the
    correlation fails, so the caller can fall back to stacking unaligned.
    """
    try:
        from skimage.registration import phase_cross_correlation
    except ImportError:  # pragma: no cover — skimage is a hard dependency
        return None
    try:
        shift, _, _ = phase_cross_correlation(ref_luma, luma, upsample_factor=10)
    except Exception as exc:  # noqa: BLE001 — a bad correlation must not sink the run
        log.debug("video phase_cross_correlation failed: %s", exc)
        return None
    return float(shift[0]), float(shift[1])


def _shift_frame(rgb: np.ndarray, dy: float, dx: float) -> np.ndarray:
    """Sub-pixel shift all three channels, leaving vacated edges as NaN.

    ``cval=np.nan`` with order-1 interpolation makes every output pixel that
    drew on the outside of the frame NaN, so the strip the shift vacates is
    honest "no coverage" rather than a dark band averaged into the result.
    """
    from scipy.ndimage import shift as nd_shift

    out = np.empty_like(rgb, dtype=np.float32)
    for c in range(3):
        out[..., c] = nd_shift(
            rgb[..., c].astype(np.float32, copy=False), shift=(dy, dx),
            order=1, mode="constant", cval=np.nan, prefilter=False,
        )
    return out


def grade_video(
    path: str | Path,
    options: LuckyOptions | None = None,
    *,
    info: VideoInfo | None = None,
    progress: Callable[[str, int, int], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> GradeResult:
    """Decode a capture once and score every frame's sharpness — pass 1 alone.

    Same decode, same sampling and the same ``progress("grade", …)`` /
    ``should_cancel`` contract as :func:`stack_video`, which calls this for its
    first pass. Useful on its own to show the user what their capture looks like
    before they choose how ruthless to be with it.

    Raises ``ValueError`` if the file has fewer than :data:`MIN_FRAMES` usable
    frames, and :class:`~seestack.video.ffmpeg.VideoToolsMissing` if ffmpeg
    isn't installed.
    """
    opts = options or LuckyOptions()
    src = Path(path)
    vinfo = info or probe_video(src)
    warnings: list[str] = []

    stride = _sampling_stride(vinfo.n_frames, opts.max_frames)
    if stride > 1:
        warnings.append(
            f"Long capture ({vinfo.n_frames} frames) — graded every {stride}th frame "
            f"to keep this quick; seeing changes slowly, so the sharp moments are "
            f"still found."
        )

    scores: list[float] = []
    expected = max(1, vinfo.n_frames // stride) if vinfo.n_frames else 0
    for i, frame in enumerate(
        iter_frames(src, stride=stride, width=vinfo.width, height=vinfo.height)
    ):
        if should_cancel is not None and should_cancel():
            raise VideoStackCancelled("cancelled while grading frames")
        scores.append(frame_sharpness(frame_luma(frame)))
        if progress is not None:
            progress("grade", i + 1, expected)

    if len(scores) < MIN_FRAMES:
        raise ValueError(
            f"{src.name} only has {len(scores)} readable frame(s) — a video stack "
            f"needs at least {MIN_FRAMES}."
        )
    return GradeResult(
        scores=tuple(float(s) for s in scores),
        n_graded=len(scores),
        stride=stride,
        width=vinfo.width,
        height=vinfo.height,
        source=str(src),
        warnings=warnings,
    )


def stack_video(
    path: str | Path,
    options: LuckyOptions | None = None,
    *,
    info: VideoInfo | None = None,
    progress: Callable[[str, int, int], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> LuckyResult:
    """Grade → keep the sharpest → align → average one video capture.

    ``progress(stage, done, total)`` is called as the two passes advance
    (``stage`` is ``"grade"`` or ``"stack"``); ``should_cancel`` is polled
    between frames so a cancelled job stops the decoder promptly.

    Raises ``ValueError`` if the file has fewer than :data:`MIN_FRAMES` usable
    frames, and :class:`~seestack.video.ffmpeg.VideoToolsMissing` if ffmpeg
    isn't installed.
    """
    opts = options or LuckyOptions()
    src = Path(path)
    vinfo = info or probe_video(src)

    # ---- pass 1: grade -----------------------------------------------------
    graded = grade_video(
        src, opts, info=vinfo, progress=progress, should_cancel=should_cancel,
    )
    scores = list(graded.scores)
    n_graded = graded.n_graded
    stride = graded.stride
    warnings: list[str] = list(graded.warnings)

    # ---- choose the keepers ------------------------------------------------
    n_keep = max(1, int(math.ceil(n_graded * opts.keep_percent / 100.0)))
    order = np.argsort(np.asarray(scores, dtype=np.float64))[::-1]
    keep_idx = set(int(i) for i in order[:n_keep])
    kept_scores = [scores[i] for i in sorted(keep_idx)]

    # ---- pass 2: align + average ------------------------------------------
    acc = WeightedSumAccumulator((vinfo.height, vinfo.width, 3), dtype=np.float32)
    ref_luma: np.ndarray | None = None
    n_stacked = 0
    n_align_failed = 0
    max_shift = max(2.0, _MAX_SHIFT_FRACTION * min(vinfo.height, vinfo.width))
    done = 0
    for i, frame in enumerate(
        iter_frames(src, stride=stride, width=vinfo.width, height=vinfo.height)
    ):
        if i not in keep_idx:
            continue
        if should_cancel is not None and should_cancel():
            raise VideoStackCancelled("cancelled while stacking frames")
        # Decoder output is 0–255; work in 0–1 so the result matches the rest of
        # the engine's display-space convention.
        rgb = frame.astype(np.float32) / 255.0
        if not opts.align or ref_luma is None:
            if opts.align:
                ref_luma = frame_luma(frame)
            acc.add(rgb)
            n_stacked += 1
        else:
            shift = _measure_shift(ref_luma, frame_luma(frame))
            if shift is None:
                acc.add(rgb)
                n_stacked += 1
            elif abs(shift[0]) > max_shift or abs(shift[1]) > max_shift:
                n_align_failed += 1
            else:
                acc.add(_shift_frame(rgb, shift[0], shift[1]))
                n_stacked += 1
        done += 1
        if progress is not None:
            progress("stack", done, n_keep)

    if n_stacked == 0:
        raise ValueError(
            f"None of the sharpest frames in {src.name} could be aligned — the "
            f"disk may be drifting out of frame."
        )
    if n_align_failed:
        warnings.append(
            f"{n_align_failed} of the sharpest frames moved too far to line up "
            f"and were left out."
        )

    return LuckyResult(
        image=acc.result(),
        width=vinfo.width,
        height=vinfo.height,
        n_graded=n_graded,
        n_kept=n_keep,
        n_stacked=n_stacked,
        n_align_failed=n_align_failed,
        stride=stride,
        sharpness_best=float(max(scores)) if scores else 0.0,
        sharpness_kept_median=float(np.median(kept_scores)) if kept_scores else 0.0,
        sharpness_all_median=float(np.median(scores)) if scores else 0.0,
        kept_indices=tuple(sorted(keep_idx)),
        scores=tuple(float(s) for s in scores),
        source=str(src),
        warnings=warnings,
    )


def normalize_for_display(rgb: np.ndarray, *, gamma: float = 1.0) -> np.ndarray:
    """Gentle, disk-appropriate render of a stacked Moon/Sun still.

    Emphatically **not** the deep-sky auto chain: an STF stretch anchors the
    *sky* median at ~6% grey, which on a lunar frame — where most of the field
    IS the bright disk — blows the disk to white; SCNR and gradient removal
    likewise assume a faint object on a flat sky. A bright disk needs nothing
    more than a linear rescale so the black sky sits at black and the brightest
    real detail sits just below clipping.

    The high anchor is the 99.9th percentile rather than the maximum so a single
    hot pixel or a specular glint can't compress the whole disk, and the low
    anchor is the 1st percentile (the sky around the disk). ``gamma`` < 1
    brightens the mid-tones if a user wants more in the terminator shadows;
    the default 1.0 leaves the linear relationship alone.
    """
    arr = np.asarray(rgb, dtype=np.float32)
    finite = np.isfinite(arr)
    if not finite.any():
        return np.zeros_like(arr)
    covered = arr[finite]
    lo = float(np.percentile(covered, 1.0))
    hi = float(np.percentile(covered, 99.9))
    if not math.isfinite(lo) or not math.isfinite(hi) or hi <= lo:
        lo, hi = float(np.min(covered)), float(np.max(covered))
    if hi <= lo:
        hi = lo + 1e-6
    out = np.clip((arr - lo) / (hi - lo), 0.0, 1.0)
    if gamma != 1.0 and gamma > 0:
        out = np.power(out, gamma, dtype=np.float32)
    # NaN (uncovered, from an alignment shift) renders black, as everywhere else.
    return np.where(np.isfinite(out), out, 0.0).astype(np.float32)
