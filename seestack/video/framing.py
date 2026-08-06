"""Find the Moon/Sun disk in a finished still, so the empty sky can be trimmed.

A Seestar lunar or solar capture is framed generously — the disk sits somewhere
in the middle of a 1080p field and the rest is black sky. The stacked still is
therefore *mostly nothing*: on a typical Moon capture the disk covers well under
a third of the frame, so the picture a beginner downloads, shares or sets as a
wallpaper is a small Moon adrift in a big black rectangle.

Cropping that away is the one framing decision worth making automatically, and
it is safe to make from the picture itself: a lunar/solar disk is the only bright
thing in the field, so "where is the subject?" is a threshold and two profiles,
not a detection problem.

What this module does **not** do, on purpose:

* It never *changes* pixels — :func:`crop_to_disk` returns a view-like slice of
  the image it was given, so the cropped still is byte-for-byte the picture the
  user would have had, minus the sky. (The webapp crops **after**
  :func:`~seestack.video.lucky.normalize_for_display`, so the tone mapping is
  measured on the full frame exactly as before and cropping cannot brighten or
  darken the result.)
* It never crops when there is little to gain, when the bright region fills the
  frame (a close-up solar disk), or when nothing looks like a disk at all — each
  of those returns "not worthwhile" and the caller leaves the picture alone.

Everything here is pure: an array in, numbers out.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

log = logging.getLogger(__name__)

#: Rec.601 luma, matching :func:`seestack.video.lucky.frame_luma` — the disk is
#: found on the same channel the frames were graded and aligned on.
_LUMA = (0.299, 0.587, 0.114)

#: Fraction of the way from the sky level to the disk level at which a pixel
#: counts as "subject". Well below halfway so the dim limb and earthshine stay
#: inside the box, well above the sky so grain doesn't.
_THRESHOLD_FRACTION = 0.25

#: A row/column needs at least this fraction of its pixels above the threshold
#: to count as part of the disk. Rejects hot pixels, a stray star and single-pixel
#: cosmic hits, which would otherwise stretch the box to the whole frame.
_PROFILE_FLOOR_FRACTION = 0.004
#: ...but never fewer than this many pixels, so the floor still bites on a small
#: frame where 0.4 % rounds to zero.
_PROFILE_FLOOR_MIN = 3

#: Breathing room around the disk, as a fraction of its larger side. Enough that
#: the crop never looks like it clipped the limb, small enough to still be a crop.
DEFAULT_MARGIN = 0.06

#: The disk's box must span at least this fraction of the frame's short edge.
#: Below it we are looking at noise or a stray highlight, not a Moon.
_MIN_DISK_SPAN = 0.05

#: Sky and disk must differ by at least this much (in the 0–1 display range) for
#: the threshold to mean anything. A blank, blown-out or all-sky frame doesn't
#: clear it and is left alone.
_MIN_CONTRAST = 0.05

#: Cropping is only offered when it trims at least this much of the frame. A crop
#: that saves 5 % of the pixels isn't worth changing anyone's picture over.
_MIN_TRIM_FRACTION = 0.15


@dataclass(frozen=True)
class DiskFraming:
    """Where the subject is, and whether trimming to it is worth doing."""

    #: Half-open ``(y0, x0, y1, x1)`` of the *crop* — the disk's own bounds plus
    #: the margin, clamped to the frame.
    box: tuple[int, int, int, int]
    #: Half-open ``(y0, x0, y1, x1)`` of the detected disk itself, no margin.
    disk_box: tuple[int, int, int, int]
    #: Area of :attr:`box` ÷ area of the full frame, 0–1. ``0.22`` means a crop
    #: would keep 22 % of the pixels and throw 78 % of empty sky away.
    keep_fraction: float
    #: True when the crop trims enough sky to be worth offering (see
    #: :data:`_MIN_TRIM_FRACTION`). False means "leave the picture alone".
    worthwhile: bool

    @property
    def trim_fraction(self) -> float:
        """Fraction of the frame the crop would throw away, 0–1."""
        return max(0.0, 1.0 - self.keep_fraction)

    @property
    def size(self) -> tuple[int, int]:
        """``(height, width)`` of the cropped picture."""
        y0, x0, y1, x1 = self.box
        return (y1 - y0, x1 - x0)


def _luma(image: np.ndarray) -> np.ndarray:
    """Rec.601 luma of an (H, W, 3) or (H, W) image, NaN read as sky (0)."""
    arr = np.asarray(image, dtype=np.float32)
    if arr.ndim == 3 and arr.shape[2] >= 3:
        lum = (_LUMA[0] * arr[..., 0] + _LUMA[1] * arr[..., 1] + _LUMA[2] * arr[..., 2])
    elif arr.ndim == 2:
        lum = arr
    else:
        raise ValueError("expected an (H, W, 3) or (H, W) image")
    # Uncovered pixels (NaN, vacated by an alignment shift) are sky, not subject.
    return np.nan_to_num(lum.astype(np.float32, copy=False), nan=0.0,
                         posinf=0.0, neginf=0.0)


def _span(counts: np.ndarray, floor: float) -> tuple[int, int] | None:
    """First and last index whose count clears ``floor`` (half-open end)."""
    hits = np.flatnonzero(counts >= floor)
    if hits.size == 0:
        return None
    return int(hits[0]), int(hits[-1]) + 1


def measure_framing(
    image: np.ndarray,
    *,
    margin: float = DEFAULT_MARGIN,
) -> DiskFraming | None:
    """Locate the bright disk in a display-rendered still.

    ``image`` is the finished picture in the 0–1 display range — i.e. the output
    of :func:`~seestack.video.lucky.normalize_for_display`, where the sky already
    sits near black and the disk near white.

    Returns ``None`` when there is nothing disk-like to crop to (a blank frame,
    a frame with no sky/subject contrast, or a bright region too small to be a
    Moon). A :class:`DiskFraming` with ``worthwhile=False`` means "we found the
    disk, but it already fills the frame" — also a reason not to crop, kept
    distinct so the caller can say so.
    """
    lum = _luma(image)
    h, w = lum.shape[:2]
    if h < 4 or w < 4:
        return None

    # Robust sky/subject levels. The 99.5th percentile rather than the max so a
    # single glint can't set the scale; the 5th is comfortably inside the sky.
    sky = float(np.percentile(lum, 5.0))
    peak = float(np.percentile(lum, 99.5))
    if not np.isfinite(sky) or not np.isfinite(peak) or peak - sky < _MIN_CONTRAST:
        return None

    bright = lum > (sky + _THRESHOLD_FRACTION * (peak - sky))
    row_floor = max(_PROFILE_FLOOR_MIN, _PROFILE_FLOOR_FRACTION * w)
    col_floor = max(_PROFILE_FLOOR_MIN, _PROFILE_FLOOR_FRACTION * h)
    rows = _span(bright.sum(axis=1), row_floor)
    cols = _span(bright.sum(axis=0), col_floor)
    if rows is None or cols is None:
        return None

    y0, y1 = rows
    x0, x1 = cols
    disk_h, disk_w = y1 - y0, x1 - x0
    short_edge = min(h, w)
    if max(disk_h, disk_w) < _MIN_DISK_SPAN * short_edge:
        # A speck, not a disk — refuse rather than crop to a hot pixel.
        return None

    pad = int(round(margin * max(disk_h, disk_w)))
    cy0 = max(0, y0 - pad)
    cx0 = max(0, x0 - pad)
    cy1 = min(h, y1 + pad)
    cx1 = min(w, x1 + pad)

    keep = ((cy1 - cy0) * (cx1 - cx0)) / float(h * w)
    return DiskFraming(
        box=(cy0, cx0, cy1, cx1),
        disk_box=(y0, x0, y1, x1),
        keep_fraction=float(keep),
        worthwhile=bool(keep <= 1.0 - _MIN_TRIM_FRACTION),
    )


def crop_to_disk(image: np.ndarray, framing: DiskFraming) -> np.ndarray:
    """Return ``image`` cropped to ``framing.box``. Pixels are untouched."""
    y0, x0, y1, x1 = framing.box
    return np.asarray(image)[y0:y1, x0:x1]
