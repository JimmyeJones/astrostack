"""Drizzle for the Moon/Sun stacker — "Auto, when worth it", as on deep-sky.

The owner asked for the lucky-imaging stack to "use drizzles when possible",
after the deep-sky side learnt to drizzle itself (v0.494.0,
:mod:`seestack.stack.autodrizzle`). A lucky stack is close to the ideal case
for it: it keeps hundreds of frames, and seeing nudges every one of them by a
fraction of a pixel, so the same scene is sampled at hundreds of slightly
different phases. Dropping each kept frame's samples onto a **finer** grid at
its measured shift — instead of shifting a sensor-sized picture and averaging —
recovers detail no single frame holds.

**A Bayer drizzle on a raw capture.** The owner's solar/lunar captures are the
raw colour-filter mosaic (:func:`seestack.video.ffmpeg.source_is_cfa_mosaic`),
which :func:`~seestack.video.ffmpeg.iter_frames` debayers. Debayering
*interpolates* two of the three colours at every pixel, and that interpolation
is exactly the resolution a drizzle is meant to win back. So on a CFA stream
only each pixel's **own** colour is deposited — a red site feeds the red plane
and nothing else — and the finer grid is filled by the frames' motion rather
than by a neighbour average. The bilinear debayer keeps every native sample
unchanged (it only fills the missing sites), so the native value is read
straight back out of the debayered frame; nothing has to decode twice. A stream
that is already colour deposits all three channels at every pixel.

"Worth it" is the same two questions :mod:`~seestack.stack.autodrizzle` asks,
measured on numbers this stack already has:

1. **Enough frames** — at least :data:`LUCKY_DRIZZLE_MIN_FRAMES` stacked, the
   engine's own "typically 200+" (``drizzle_path``'s recommendation, which is
   :data:`~seestack.stack.autodrizzle.AUTO_DRIZZLE_MIN_SAMPLES_PER_PIXEL`). A
   lucky frame covers the whole canvas, so frames *are* samples per pixel here.
2. **They really moved sub-pixel** — the measured shifts' sub-pixel phases
   spread at least :data:`LUCKY_DRIZZLE_MIN_SPREAD_PX` on **both** axes
   (:func:`~seestack.stack.autodrizzle.dither_spread_px`, the same wrap-safe
   measurement deep-sky uses). Frames that all sat on the same phase give a
   finer grid with nothing new in it.

The answer is only known once pass 2 has measured every shift, so the stacker
runs this accumulator **beside** the ordinary one and keeps whichever the
answer picks. Memory stays flat in video length: one ×``scale``² canvas of
sums and one of weights, never a held frame (:data:`LUCKY_DRIZZLE_MAX_OUTPUT_PIXELS`
caps it). When the frame count alone already says no, the stacker never builds
it at all, so a short capture pays nothing.

Nothing here reads a setting or touches I/O.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from seestack.stack.autodrizzle import AUTO_DRIZZLE_SCALE, dither_spread_px

#: Stacked frames below which a lucky drizzle is the wrong call. The engine's
#: "typically 200+" samples per output pixel — and a lucky frame lands on every
#: pixel of the canvas, so its stacked-frame count is that number directly. At
#: the default keep of 30 % that is a capture of ~670 graded frames, which the
#: owner's solar runs clear several times over (his 4,487-frame capture keeps 449).
LUCKY_DRIZZLE_MIN_FRAMES = 200

#: Worst-axis sub-pixel spread of the **measured** shifts below which the frames
#: are judged not to have moved. Lower than deep-sky's
#: :data:`~seestack.stack.autodrizzle.AUTO_DRIZZLE_MIN_DITHER_PX` (0.2) on
#: purpose: that bar is read off plate-solved positions, this one off the disk
#: aligner's own correlation, which leans a little towards whole pixels.
#: Measured through :func:`~seestack.video.lucky._measure_disk_shift` on raw
#: ``GBRG`` fixtures (80 frames each, 2026-10-20): phases filling the pixel (true
#: spread 0.28) read **0.20** with detail finer than the Bayer cell and 0.25 with
#: coarser detail; a still disk reads **0.00**; a ±0.15 px wobble (true 0.08)
#: reads 0.06. 0.15 keeps the first clear and the other two well under.
LUCKY_DRIZZLE_MIN_SPREAD_PX = 0.15

#: The finer grid's size, as a multiple of the camera's. The same ×1.5 the
#: deep-sky auto-drizzle asks for, and for the same reason: it is the step that
#: pays on a well-dithered set without spreading the samples too thin.
LUCKY_DRIZZLE_SCALE = AUTO_DRIZZLE_SCALE

#: The largest finer canvas (in output pixels) this will build. A 1080p capture
#: at ×1.5 is 4.7 MP — about 110 MB of sums and weights — so this leaves room for
#: a 4K-class sensor while refusing a canvas that would not fit beside the rest
#: of a NAS's work.
LUCKY_DRIZZLE_MAX_OUTPUT_PIXELS = 12_000_000

#: Measured cost of depositing one kept frame, in seconds per source megapixel
#: (2026-10-20, a 1920×1080 frame on a 4-vCPU container, one thread: 0.08 s for
#: a raw capture, 0.16 s for a colour one — three colours at every pixel). The
#: midpoint, rounded up; only used to tell the owner roughly how much longer the
#: stack will take — a sentence on the running job, never a gate.
LUCKY_DRIZZLE_SECONDS_PER_MEGAPIXEL = 0.06

#: A finer-grid pixel is "covered" only when every colour plane collected at
#: least this fraction of that plane's typical weight. The canvas edges and the
#: strip a shift vacates come back NaN — "no coverage", as everywhere else —
#: rather than as a noisy average of a sample or two.
_MIN_RELATIVE_WEIGHT = 0.25

#: Why the stack did (or did not) drizzle — machine-readable, for the sentence.
REASON_DRIZZLED = "drizzled"
REASON_OFF = "off"
REASON_NOT_ALIGNED = "not_aligned"
REASON_TOO_FEW_FRAMES = "too_few_frames"
REASON_TOO_LITTLE_MOTION = "too_little_motion"
REASON_TOO_BIG = "too_big"


def output_shape(height: int, width: int, scale: float = LUCKY_DRIZZLE_SCALE) -> tuple[int, int]:
    """The finer canvas's (H, W) for a ``height`` × ``width`` capture."""
    return int(round(height * scale)), int(round(width * scale))


def planned(
    *, enabled: bool, align: bool, n_keep: int, height: int, width: int,
    scale: float = LUCKY_DRIZZLE_SCALE,
) -> str | None:
    """Can this stack drizzle at all? ``None`` = try it; else the reason it won't.

    Everything here is known **before** pass 2 starts: whether the owner allows
    it, whether frames are aligned (an unaligned stack has no shifts to drizzle
    with), whether enough frames are being kept, and whether the canvas fits.
    The motion test needs pass 2's shifts and is :func:`decide`'s job.
    """
    if not enabled:
        return REASON_OFF
    if not align:
        return REASON_NOT_ALIGNED
    if n_keep < LUCKY_DRIZZLE_MIN_FRAMES:
        return REASON_TOO_FEW_FRAMES
    oh, ow = output_shape(height, width, scale)
    if oh * ow > LUCKY_DRIZZLE_MAX_OUTPUT_PIXELS:
        return REASON_TOO_BIG
    return None


@dataclass(frozen=True)
class DrizzleDecision:
    """What :func:`decide` concluded, with the numbers behind it."""

    reason: str
    #: 1.0 unless the drizzle was kept.
    scale: float
    #: Worst-axis sub-pixel spread of the measured shifts (``None`` = unmeasured).
    spread_px: float | None = None

    @property
    def drizzled(self) -> bool:
        return self.reason == REASON_DRIZZLED


def decide(
    shifts: Sequence[tuple[float, float]], *, n_stacked: int,
    scale: float = LUCKY_DRIZZLE_SCALE,
) -> DrizzleDecision:
    """After pass 2: keep the drizzle, or fall back to the camera-sized stack.

    ``shifts`` is one ``(dy, dx)`` per stacked frame, the reference's ``(0, 0)``
    included.
    """
    if n_stacked < LUCKY_DRIZZLE_MIN_FRAMES:
        return DrizzleDecision(REASON_TOO_FEW_FRAMES, 1.0)
    spread = dither_spread_px([(dx, dy) for dy, dx in shifts])
    worst = None if spread is None else min(spread.x, spread.y)
    if worst is None or worst < LUCKY_DRIZZLE_MIN_SPREAD_PX:
        return DrizzleDecision(REASON_TOO_LITTLE_MOTION, 1.0, worst)
    return DrizzleDecision(REASON_DRIZZLED, float(scale), worst)


def extra_seconds(n_frames: int, height: int, width: int) -> float:
    """Roughly how much longer pass 2 takes with the drizzle running beside it."""
    return max(0.0, float(n_frames)) * (height * width / 1e6) * LUCKY_DRIZZLE_SECONDS_PER_MEGAPIXEL


def sentence(decision: DrizzleDecision | None, n_stacked: int) -> str:
    """One plain sentence saying what the drizzle did — empty when it was off.

    "Off" says nothing at all: the owner chose the camera-sized picture, and a
    stack that drizzles nothing is exactly the picture every earlier version
    made, so there is nothing to explain.
    """
    if decision is None or decision.reason in (REASON_OFF, REASON_NOT_ALIGNED):
        return ""
    if decision.drizzled:
        return (
            f"Drizzled to {decision.scale:g}× the camera's resolution using "
            f"{n_stacked} frames — the small shifts between them let the stack "
            f"recover finer detail than any one frame holds."
        )
    if decision.reason == REASON_TOO_FEW_FRAMES:
        return (
            f"Kept at camera resolution — drizzle needs at least "
            f"{LUCKY_DRIZZLE_MIN_FRAMES} stacked frames and this had {n_stacked}. "
            f"A longer capture, or keeping more of it, would get there."
        )
    if decision.reason == REASON_TOO_LITTLE_MOTION:
        return (
            "Kept at camera resolution — the frames barely moved against each "
            "other, so a finer grid would have had no new detail to fill it."
        )
    if decision.reason == REASON_TOO_BIG:
        return "Kept at camera resolution — this capture is too large to drizzle safely."
    return ""


#: The CFA layouts, top-left / top-right / bottom-left / bottom-right of the
#: 2×2 cell — the same table :func:`seestack.io.fits_loader.bilinear_debayer`
#: debayers with, so a site's colour here is the colour it was debayered as.
_LAYOUTS = {
    "RGGB": ("r", "g", "g", "b"),
    "BGGR": ("b", "g", "g", "r"),
    "GRBG": ("g", "r", "b", "g"),
    "GBRG": ("g", "b", "r", "g"),
}
_CHANNEL = {"r": 0, "g": 1, "b": 2}


def _parity_channels(pattern: str | None) -> list[tuple[int, int, tuple[int, ...]]]:
    """Per 2×2-cell position ``(py, px)``, the channels its pixels sampled natively.

    A CFA site sampled one colour; a pixel of a colour stream sampled all three.
    """
    cells = ((0, 0), (0, 1), (1, 0), (1, 1))
    if pattern is None:
        return [(py, px, (0, 1, 2)) for py, px in cells]
    layout = _LAYOUTS[pattern.upper()]
    return [(py, px, (_CHANNEL[c],)) for (py, px), c in zip(cells, layout, strict=True)]


def _lattice_span(start: int, n: int, step: int, limit: int) -> tuple[int, int]:
    """Which of ``start, start+step, …`` (``n`` of them) fall inside ``[0, limit)``."""
    lo = 0 if start >= 0 else (step - 1 - start) // step   # ceil(-start / step)
    hi = min(n, (limit - 1 - start) // step + 1) if start < limit else 0
    return lo, max(lo, hi)


class LuckyDrizzle:
    """A finer-grid accumulator fed one shifted frame at a time.

    Each native sample is spread over the four finer-grid pixels around where
    it lands (bilinear weights summing to one), so every output pixel ends as
    a weighted mean of the samples that fell near it across all the frames.

    **Why it is a handful of slice-adds and not a scatter.** A frame's shift is
    one ``(dy, dx)`` for every pixel, and at ×1.5 two input pixels are exactly
    three output pixels — so the pixels of one 2×2-cell position (every red
    site, say) land on a regular lattice of step 3 with *one* shared fractional
    offset. Each of the four cell positions is therefore four strided ``+=``
    of a quarter-size array with constant weights: the same arithmetic a
    per-sample scatter would do, measured ~7× faster on a 1080p frame.
    """

    def __init__(
        self, height: int, width: int, *, pattern: str | None,
        scale: float = LUCKY_DRIZZLE_SCALE,
    ) -> None:
        step = 2.0 * float(scale)
        if abs(step - round(step)) > 1e-9:
            raise ValueError("the lucky drizzle needs a scale that is a multiple of 0.5")
        self.height, self.width = int(height), int(width)
        self.scale = float(scale)
        self._step = int(round(step))
        self.out_h, self.out_w = output_shape(self.height, self.width, self.scale)
        self._sum = np.zeros((3, self.out_h, self.out_w), dtype=np.float32)
        self._wt = np.zeros((3, self.out_h, self.out_w), dtype=np.float32)
        self._cells = _parity_channels(pattern)
        self.n_frames = 0

    def add(self, rgb: np.ndarray, dy: float, dx: float) -> None:
        """Deposit one (H, W, 3) frame that ``(dy, dx)`` brings onto the reference."""
        s, step = self.scale, self._step
        for py, px, channels in self._cells:
            block = rgb[py::2, px::2]
            nh, nw = block.shape[:2]
            # Pixel centres: input coordinate u sits at (u + 0.5)·s − 0.5 on the
            # finer grid, after the shift that brings it onto the reference.
            oy = (py + dy + 0.5) * s - 0.5
            ox = (px + dx + 0.5) * s - 0.5
            iy, ix = math.floor(oy), math.floor(ox)
            fy, fx = oy - iy, ox - ix
            for ky, wy in ((0, 1.0 - fy), (1, fy)):
                r0 = iy + ky
                i0, i1 = _lattice_span(r0, nh, step, self.out_h)
                if i1 <= i0 or wy <= 0.0:
                    continue
                rows = slice(r0 + step * i0, r0 + step * (i1 - 1) + 1, step)
                for kx, wx in ((0, 1.0 - fx), (1, fx)):
                    c0 = ix + kx
                    j0, j1 = _lattice_span(c0, nw, step, self.out_w)
                    w = np.float32(wy * wx)
                    if j1 <= j0 or w <= 0.0:
                        continue
                    cols = slice(c0 + step * j0, c0 + step * (j1 - 1) + 1, step)
                    for c in channels:
                        self._sum[c, rows, cols] += w * block[i0:i1, j0:j1, c]
                        self._wt[c, rows, cols] += w
        self.n_frames += 1

    def result(self) -> np.ndarray:
        """(out_H, out_W, 3) float32 weighted mean; NaN where not covered."""
        covered = np.ones((self.out_h, self.out_w), dtype=bool)
        for c in range(3):
            positive = self._wt[c][self._wt[c] > 0]
            if positive.size == 0:
                return np.full((self.out_h, self.out_w, 3), np.nan, dtype=np.float32)
            covered &= self._wt[c] >= _MIN_RELATIVE_WEIGHT * float(np.median(positive))
        with np.errstate(invalid="ignore", divide="ignore"):
            mean = self._sum / self._wt
        out = np.moveaxis(mean, 0, -1).astype(np.float32)
        out[~covered] = np.nan
        return out


__all__ = [
    "LUCKY_DRIZZLE_MAX_OUTPUT_PIXELS",
    "LUCKY_DRIZZLE_MIN_FRAMES",
    "LUCKY_DRIZZLE_MIN_SPREAD_PX",
    "LUCKY_DRIZZLE_SCALE",
    "DrizzleDecision",
    "LuckyDrizzle",
    "decide",
    "extra_seconds",
    "output_shape",
    "planned",
    "sentence",
]
