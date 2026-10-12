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
   *sharpest* kept frame and add into a NaN-aware accumulator. Memory: a handful
   of full-frame canvases regardless of video length.

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
#: smeared into the stack. **Applies only to the whole-frame fallback** — when a
#: disk is found, its centre is measured directly, so a large drift is a real
#: drift and the only reason to drop a frame is the disk running off the edge
#: (the owner's solar captures drift up to ~270 px; this limit was 162 px there).
_MAX_SHIFT_FRACTION = 0.15

#: Pixel-noise smoothing (Gaussian σ, px) before the sharpness Laplacian. Without
#: it the score is mostly sensor noise: measured on the owner's raw solar AVI the
#: unsmoothed score ran *against* brightness (r = −0.79), so the dimmest,
#: noisiest frames were kept as the "sharpest".
_SHARPNESS_SMOOTH_SIGMA = 1.0

#: A disk must cover at least this fraction of the frame (and no more than
#: :data:`_DISK_MAX_FRACTION`) to be aligned and graded on; otherwise the whole
#: frame is used, as before.
_DISK_MIN_FRACTION = 0.0005
_DISK_MAX_FRACTION = 0.85

#: How far (px) the windowed correlation may move the disk-centre shift. The
#: centre is good to about a pixel; anything larger is not a refinement.
_MAX_REFINE_PX = 2.0

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
    #: Position of the sharpest frame in :attr:`scores` (``-1`` when there are
    #: no scores). Always filled in — it costs an ``argmax`` over the scalars.
    best_index: int = -1
    #: The sharpest frame itself, as decoded ((H, W, 3) uint8), when the caller
    #: asked for it with ``keep_best_frame=True``. ``None`` otherwise — grading
    #: is the memory-cheap pass and holding a frame is opt-in. Both callers want
    #: it: the "check this capture" pass renders it as the quick look, and
    #: :func:`stack_video` uses its luma as the alignment reference.
    best_frame: np.ndarray | None = None


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


@dataclass(frozen=True)
class _Disk:
    """Where the bright object (Sun, Moon, planet) sits in one frame."""

    cy: float
    cx: float
    y0: int
    y1: int
    x0: int
    x1: int
    touches_edge: bool
    mask: np.ndarray


def _find_disk(luma: np.ndarray) -> _Disk | None:
    """The bright object's centre, extent and pixels — or ``None`` if there isn't one.

    Thresholded halfway between the background (the median) and the bright level
    (the 99.5th percentile), keeping only the **largest** connected region, so a
    hot pixel or a cosmic ray cannot pose as the disk. ``None`` for a frame with
    no clear object, or one the object fills, so callers fall back to the whole
    frame exactly as before.
    """
    from scipy import ndimage

    lum = np.asarray(luma, dtype=np.float32)
    lo = float(np.median(lum))
    hi = float(np.percentile(lum, 99.5))
    if not (math.isfinite(lo) and math.isfinite(hi)) or hi - lo <= 1e-6:
        return None
    mask = lum > lo + 0.5 * (hi - lo)
    labels, n = ndimage.label(mask)
    if n == 0:
        return None
    sizes = np.bincount(labels.ravel())[1:]
    biggest = int(np.argmax(sizes)) + 1
    disk = labels == biggest
    frac = float(sizes[biggest - 1]) / disk.size
    if frac < _DISK_MIN_FRACTION or frac > _DISK_MAX_FRACTION:
        return None
    cy, cx = ndimage.center_of_mass(disk)
    sl = ndimage.find_objects(disk.astype(np.int8))[0]
    y0, y1, x0, x1 = sl[0].start, sl[0].stop, sl[1].start, sl[1].stop
    h, w = disk.shape
    return _Disk(float(cy), float(cx), y0, y1, x0, x1,
                 touches_edge=y0 == 0 or x0 == 0 or y1 == h or x1 == w, mask=disk)


def frame_sharpness(luma: np.ndarray) -> float:
    """Exposure-invariant sharpness score for one frame (higher = sharper).

    Mean squared Laplacian — the standard "is this in focus?" measure — divided
    by the mean brightness squared. The normalisation matters: a thin cloud or
    the Seestar's auto-exposure can change a capture's level between frames, and
    an un-normalised Laplacian would rank the *brightest* frames sharpest.

    **Measured on the disk, after smoothing out pixel noise** *(2026-10-12)*. It
    used to be the whole frame: on the owner's Sun, which covers 7 % of the
    frame, that is mostly black sky and sensor noise, normalised by a mean the
    black sky drags down — so the score ran *against* brightness (r = −0.79 on
    his raw capture) and the dimmest, noisiest frames were kept as the sharpest.
    Now the Laplacian is taken over the disk's bounding box after a light
    Gaussian (:data:`_SHARPNESS_SMOOTH_SIGMA`), and normalised by the disk's own
    mean. A frame with no disk is scored on the whole frame, as before.
    """
    from scipy.ndimage import binary_dilation, gaussian_filter, laplace

    lum = np.asarray(luma, dtype=np.float32)
    disk = _find_disk(lum)
    if disk is None:
        lap = laplace(gaussian_filter(lum, _SHARPNESS_SMOOTH_SIGMA))
        energy = float(np.mean(lap.astype(np.float64) ** 2))
        mean = float(np.mean(lum, dtype=np.float64))
    else:
        # Work in a box around the disk with a margin of dark sky. The sky's
        # Laplacian energy is the noise floor — read noise, the sensor's fixed
        # pattern — and the same floor sits under the disk, so it is subtracted:
        # what is left is detail. Without that, a dimmer frame's noise counts for
        # more after normalising and the haziest frames win.
        pad = max(8, (disk.y1 - disk.y0) // 4)
        y0, x0 = max(0, disk.y0 - pad), max(0, disk.x0 - pad)
        y1, x1 = min(lum.shape[0], disk.y1 + pad), min(lum.shape[1], disk.x1 + pad)
        lap = laplace(gaussian_filter(lum[y0:y1, x0:x1], _SHARPNESS_SMOOTH_SIGMA)).astype(np.float64) ** 2
        inside = disk.mask[y0:y1, x0:x1]
        sky = ~binary_dilation(inside, iterations=4)
        floor = float(np.mean(lap[sky])) if sky.sum() >= 64 else 0.0
        energy = max(0.0, float(np.mean(lap[binary_dilation(inside, iterations=2)])) - floor)
        mean = float(np.mean(lum[disk.mask], dtype=np.float64))
    if not math.isfinite(energy) or mean <= 0:
        return 0.0
    return energy / (mean * mean)


def _sampling_stride(n_frames: int, max_frames: int) -> int:
    """Even-sampling stride so at most ``max_frames`` frames are graded."""
    if n_frames <= 0 or n_frames <= max_frames:
        return 1
    return int(math.ceil(n_frames / max_frames))


def ordinal(n: int) -> str:
    """``2`` → ``"2nd"``, ``13`` → ``"13th"`` — English's own irregularity, once.

    The stride warning below used to be written ``f"every {stride}th frame"``, a
    hard-coded suffix on a computed integer, so a 3,000-frame capture at the
    default ``max_frames`` of 1,500 told the owner it had *"graded every 2th
    frame"*. Pure, so the wording and the arithmetic are testable apart.
    """
    n = int(n)
    if 11 <= abs(n) % 100 <= 13:
        return f"{n}th"
    return f"{n}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(abs(n) % 10, 'th') }"


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


def _measure_disk_shift(
    ref_luma: np.ndarray, ref_disk: _Disk, luma: np.ndarray, disk: _Disk,
) -> tuple[float, float]:
    """(dy, dx) that brings ``disk`` onto ``ref_disk``: centre first, then refined.

    Coarse: the difference of the two disk centres — immune to anything that
    does not move with the disk. Fine: phase correlation of a Hann-windowed
    window that *follows* the disk in each frame, which locks onto the limb and
    the surface detail. **Why not the whole frame any more** *(2026-10-12)*: on
    the owner's raw solar capture the Sun covers 7 % of the frame, and the
    camera's stationary noise pattern — identical in every frame — won the
    whole-frame correlation, so it reported ~0 shift while the disk moved a
    median 22 px: 138 of 143 sampled frames were stacked misaligned.
    """
    ry, rx = int(round(ref_disk.cy)), int(round(ref_disk.cx))
    cy, cx = int(round(disk.cy)), int(round(disk.cx))
    coarse = (float(ry - cy), float(rx - cx))
    half_h = int(0.6 * (ref_disk.y1 - ref_disk.y0)) + 8
    half_w = int(0.6 * (ref_disk.x1 - ref_disk.x0)) + 8
    h, w = luma.shape
    if (min(ry, cy) - half_h < 0 or min(rx, cx) - half_w < 0
            or max(ry, cy) + half_h > h or max(rx, cx) + half_w > w):
        return coarse          # no room for a common window: the centre is still right
    a = ref_luma[ry - half_h:ry + half_h, rx - half_w:rx + half_w].astype(np.float32)
    b = luma[cy - half_h:cy + half_h, cx - half_w:cx + half_w].astype(np.float32)
    win = np.outer(np.hanning(a.shape[0]), np.hanning(a.shape[1])).astype(np.float32)
    fine = _measure_shift((a - a.mean()) * win, (b - b.mean()) * win)
    # The centre is already good to about a pixel, so the refinement may only
    # nudge it. A bigger "correction" is the sensor's fixed pattern lining up
    # with itself at the integer offset between the two windows — measured: it
    # cancelled a real 5 px shift outright — so the centre wins.
    if fine is None or abs(fine[0]) > _MAX_REFINE_PX or abs(fine[1]) > _MAX_REFINE_PX:
        return coarse
    return coarse[0] + fine[0], coarse[1] + fine[1]


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
    keep_best_frame: bool = False,
) -> GradeResult:
    """Decode a capture once and score every frame's sharpness — pass 1 alone.

    Same decode, same sampling and the same ``progress("grade", …)`` /
    ``should_cancel`` contract as :func:`stack_video`, which calls this for its
    first pass. Useful on its own to show the user what their capture looks like
    before they choose how ruthless to be with it.

    ``keep_best_frame`` additionally hands back the sharpest frame itself
    (:attr:`GradeResult.best_frame`), so "what does this capture actually look
    like?" can be answered without decoding the file a second time. It holds
    **exactly one extra frame** — the best one seen so far, replaced as a
    sharper one arrives — so the pass stays flat in memory whatever the video's
    length. Off by default, so a caller that only wants the scores never pays
    for a frame it will not use.

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
            f"Long capture ({vinfo.n_frames} frames) — graded every {ordinal(stride)} frame "
            f"to keep this quick; seeing changes slowly, so the sharp moments are "
            f"still found."
        )

    scores: list[float] = []
    best_index = -1
    best_score = -math.inf
    best_frame: np.ndarray | None = None
    expected = max(1, vinfo.n_frames // stride) if vinfo.n_frames else 0
    for i, frame in enumerate(
        iter_frames(src, stride=stride, width=vinfo.width, height=vinfo.height,
                    pix_fmt=vinfo.pix_fmt)
    ):
        if should_cancel is not None and should_cancel():
            raise VideoStackCancelled("cancelled while grading frames")
        score = frame_sharpness(frame_luma(frame))
        scores.append(score)
        if score > best_score:
            best_score = score
            best_index = i
            if keep_best_frame:
                # ``iter_frames`` yields a fresh copy per iteration, so holding
                # this one keeps nothing else alive — the previous best is
                # dropped here and collected.
                best_frame = frame
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
        best_index=best_index,
        best_frame=best_frame,
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

    Everything kept is aligned onto the **sharpest** frame in the capture, which
    is therefore the one that fixes the result's framing.

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
        # The sharpest frame is the alignment reference (see below), so pass 1
        # hands it back rather than pass 2 hunting for it. Costs exactly one held
        # frame — the pass stays flat in memory — and only when aligning at all.
        keep_best_frame=opts.align,
    )
    scores = list(graded.scores)
    n_graded = graded.n_graded
    stride = graded.stride
    warnings: list[str] = list(graded.warnings)

    # ---- choose the keepers ------------------------------------------------
    n_keep = max(1, int(math.ceil(n_graded * opts.keep_percent / 100.0)))
    # Descending by score, ties broken toward the *earlier* frame — a stable sort
    # of the negated scores. The tie rule is what makes "the sharpest frame is
    # always among the keepers, and it is the one ``grade_video`` held on to"
    # true by construction rather than by luck.
    order = np.argsort(-np.asarray(scores, dtype=np.float64), kind="stable")
    keep_idx = set(int(i) for i in order[:n_keep])
    kept_scores = [scores[i] for i in sorted(keep_idx)]

    # ---- pass 2: align + average ------------------------------------------
    #
    # Align to the *sharpest* kept frame, not the earliest one. Phase correlation
    # locks harder against a crisp reference — a sharp frame gives a tighter
    # correlation peak — so anchoring on whichever keeper happened to come first
    # in decode order makes every other frame's measured shift noisier, and can
    # push a good frame past ``_MAX_SHIFT_FRACTION`` and out of the stack
    # entirely. Aligning to the best frame is also what AutoStakkert/RegiStax do,
    # and it costs nothing: pass 1 already knows which frame that is.
    acc = WeightedSumAccumulator((vinfo.height, vinfo.width, 3), dtype=np.float32)
    ref_index = graded.best_index if opts.align else -1
    ref_luma: np.ndarray | None = (
        frame_luma(graded.best_frame) if graded.best_frame is not None else None
    )
    ref_disk = _find_disk(ref_luma) if ref_luma is not None else None
    # Nothing else needs the reference *frame* once its luma is measured, and it
    # is the one full frame pass 1 was holding.
    graded.best_frame = None
    n_stacked = 0
    n_align_failed = 0
    max_shift = max(2.0, _MAX_SHIFT_FRACTION * min(vinfo.height, vinfo.width))
    done = 0
    for i, frame in enumerate(
        # ``wanted=keep_idx`` hands back ``None`` for the frames this pass is
        # about to discard, which is what stops the decoder demosaicing them: on
        # a CFA (solar/lunar) capture that is ~350 ms a frame, and at the default
        # keep percentage most of pass 2 used to be spent debayering frames it
        # threw away one line later. The frames it *does* keep are decoded and
        # demosaiced exactly as before, so the stacked result is unchanged.
        iter_frames(src, stride=stride, width=vinfo.width, height=vinfo.height,
                    pix_fmt=vinfo.pix_fmt, wanted=keep_idx)
    ):
        if frame is None:
            continue
        if should_cancel is not None and should_cancel():
            raise VideoStackCancelled("cancelled while stacking frames")
        # Decoder output is 0–255; work in 0–1 so the result matches the rest of
        # the engine's display-space convention.
        rgb = frame.astype(np.float32) / 255.0
        if not opts.align or ref_luma is None or i == ref_index:
            # The reference itself goes in unshifted — it is what everything else
            # is being brought onto, so it defines the result's framing. (When
            # pass 1 couldn't hand back a frame we fall back to the old
            # anchor-on-the-first-keeper behaviour, which is still correct.)
            if opts.align and ref_luma is None:
                ref_index = i
                ref_luma = frame_luma(frame)
                ref_disk = _find_disk(ref_luma)
            acc.add(rgb)
            n_stacked += 1
        else:
            luma = frame_luma(frame)
            disk = _find_disk(luma) if ref_disk is not None else None
            if ref_disk is not None and disk is not None:
                # A disk in both: align on it. The only reason to drop the frame
                # is the disk running off the edge — a cut-off disk has a moved
                # centre, so its shift (and its picture) would be wrong.
                if disk.touches_edge:
                    n_align_failed += 1
                else:
                    dy, dx = _measure_disk_shift(ref_luma, ref_disk, luma, disk)
                    acc.add(_shift_frame(rgb, dy, dx))
                    n_stacked += 1
            elif ref_disk is not None:
                n_align_failed += 1     # the disk is gone from this frame (cloud, slew)
            else:
                shift = _measure_shift(ref_luma, luma)
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
