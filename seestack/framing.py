"""Will-it-fit framing hint: is a target bigger than the Seestar's field of view?

A very common beginner surprise is that the Seestar's single-frame field of view
is small (~1.3° across), while some favourite targets — M31 (~3°), the Pleiades,
the North America Nebula, the Veil — are *larger than one frame*. A beginner who
points at one of those and shoots a single frame gets a cropped result without
realising they needed **mosaic mode**.

This module answers "will it fit?" from a target's angular size alone: pure,
offline, no dependency. It compares the object's major-axis size (arcmin, from the
bundled catalog) against the Seestar's known single-frame field and returns one of
a few friendly, plain-language verdicts — or ``None`` when the size is unknown (we
never guess: absent a size, no hint).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# ZWO Seestar S50 single-frame field of view, in arcminutes. The Seestar images a
# ~1.29° × 0.73° rectangle (250 mm f/5 over its IMX462 sensor), so a frame is ~77'
# on its long edge and ~44' on its short edge. Mosaic mode stitches several frames
# for anything bigger. These are the reference the "will it fit" verdict compares
# against; they're intentionally the *single-frame* field (mosaic is the fix we
# point at, not the baseline).
SEESTAR_FOV_LONG_ARCMIN = 77.0
SEESTAR_FOV_SHORT_ARCMIN = 44.0


@dataclass(frozen=True)
class FramingHint:
    """A plain-language "will it fit in one frame?" verdict for a target.

    ``level`` is a stable machine token the UI can style on; ``text`` is the
    ready-to-render beginner sentence (it names the object nothing — the caller
    prefixes it with the target's name, e.g. "M 31 " + text).
    """

    level: str   # "fits" | "tight" | "mosaic"
    text: str


def framing_hint(
    size_arcmin: float | None,
    *,
    fov_long_arcmin: float = SEESTAR_FOV_LONG_ARCMIN,
    fov_short_arcmin: float = SEESTAR_FOV_SHORT_ARCMIN,
) -> FramingHint | None:
    """Verdict on whether an object of major-axis ``size_arcmin`` fits one frame.

    Returns ``None`` when the size is unknown or non-positive (never guess). The
    frame is rectangular, so we compare against both edges:

    - ``fits``   — smaller than the short edge: comfortably inside a single frame,
      whatever its orientation. No mosaic needed.
    - ``tight``  — between the short and long edges: about as wide as a single
      frame, so it only fits if favourably rotated — a small mosaic gives it
      margin.
    - ``mosaic`` — bigger than the long edge: won't fit a single frame at all;
      mosaic mode is the way to capture all of it.
    """
    if size_arcmin is None or size_arcmin <= 0:
        return None

    if size_arcmin <= fov_short_arcmin:
        return FramingHint(
            "fits",
            "fits comfortably in a single Seestar frame — no mosaic needed.",
        )
    if size_arcmin <= fov_long_arcmin:
        return FramingHint(
            "tight",
            "is about as wide as a single Seestar frame — shoot it in mosaic "
            "mode to frame it with some margin.",
        )
    return FramingHint(
        "mosaic",
        "is bigger than the Seestar's single frame — shoot it in mosaic mode to "
        "capture all of it.",
    )


@dataclass(frozen=True)
class FramingResult:
    """A plain-language "did I frame it well?" verdict for a *finished* stack.

    Where :class:`FramingHint` answers "will it fit?" before the shoot, this
    answers "did it actually land well?" from the result itself. ``level`` is a
    stable machine token the UI can style on; ``text`` is the ready-to-render
    beginner sentence, which — like the hint's — is prefixed by the caller with
    the object's name. ``coverage`` is the fraction (0–1) of the object's extent
    that made it into the frame, and ``off_centre`` how far its centre sits from
    the frame's, as a fraction of the half-frame (0 = dead centre, 1 = on the
    edge).
    """

    level: str        # "centred" | "off_centre" | "clipped" | "partial"
    text: str
    coverage: float
    off_centre: float


# How far off-centre (as a fraction of the half-frame) an object may sit before
# it's worth mentioning. A third of the way out still looks deliberate; beyond
# that a beginner would usually rather have re-centred it.
_OFF_CENTRE_LIMIT = 0.34
# Above this coverage the box maths' rounding is the only thing missing, so the
# verdict may honestly say "all of it".
_ALL_IN = 0.99


def _rounded_pct(fraction: float) -> int:
    """A friendly percentage: rounded to the nearest 5, never 0 or 100 (those
    would contradict the sentence they sit in)."""
    pct = int(round(fraction * 100 / 5.0) * 5)
    return min(95, max(5, pct))


def framing_result_verdict(
    *,
    x_px: float,
    y_px: float,
    width_px: int,
    height_px: int,
    arcsec_per_px: float,
    size_arcmin: float | None,
) -> FramingResult | None:
    """Judge how well a finished stack framed its target.

    Takes the object's position **already projected into the result's pixel
    grid** (``x_px``/``y_px``), the canvas size, its plate scale and the object's
    major-axis size — so this stays pure arithmetic with no WCS, no astropy and
    no I/O, exactly like :mod:`seestack.scalebar`. The caller (the webapp) owns
    the projection, which is the part that needs a WCS.

    Returns ``None`` when the answer would be a guess: no catalog size, a
    non-positive plate scale or canvas, or a non-finite position. We never
    invent a framing verdict — no card is better than a wrong one.

    The object is modelled as a **square box of its major-axis size** centred on
    its catalog position. That is deliberately generous for an elongated galaxy
    seen edge-on (its minor axis is smaller), so the verdict errs toward "some of
    it is outside" rather than quietly promising a beginner that all of it landed.
    """
    if size_arcmin is None or size_arcmin <= 0:
        return None
    if width_px <= 0 or height_px <= 0 or arcsec_per_px <= 0:
        return None
    if not (math.isfinite(x_px) and math.isfinite(y_px)):
        return None

    hi_x, hi_y = float(width_px - 1), float(height_px - 1)
    radius_px = (size_arcmin * 60.0 / arcsec_per_px) / 2.0
    if radius_px <= 0:
        return None

    # Fraction of the object's box that lands inside the canvas.
    span_x = max(0.0, min(x_px + radius_px, hi_x) - max(x_px - radius_px, 0.0))
    span_y = max(0.0, min(y_px + radius_px, hi_y) - max(y_px - radius_px, 0.0))
    coverage = (span_x * span_y) / ((2.0 * radius_px) ** 2)
    coverage = min(1.0, max(0.0, coverage))

    # How far off-centre, as a fraction of the half-frame on its worst axis.
    half_x, half_y = hi_x / 2.0, hi_y / 2.0
    off_centre = max(
        abs(x_px - half_x) / half_x if half_x > 0 else 0.0,
        abs(y_px - half_y) / half_y if half_y > 0 else 0.0,
    )

    if coverage < _ALL_IN:
        # Two very different problems share "some of it is missing", and they have
        # opposite fixes: an object that *would* have fitted was simply pointed at
        # badly (re-centre), while one bigger than the canvas can never fit in a
        # single frame however well aimed (mosaic mode). Say the right one.
        fits_in_frame = 2.0 * radius_px <= hi_x and 2.0 * radius_px <= hi_y
        if fits_in_frame:
            return FramingResult(
                "clipped",
                f"runs off the edge of the frame — about {_rounded_pct(coverage)}% of "
                "it made it in. It would fit whole, so just re-centre it next session.",
                coverage, off_centre,
            )
        return FramingResult(
            "partial",
            f"is bigger than your frame — only about {_rounded_pct(coverage)}% of it "
            "is in this picture. Shoot it in mosaic mode to capture all of it.",
            coverage, off_centre,
        )
    if off_centre > _OFF_CENTRE_LIMIT:
        return FramingResult(
            "off_centre",
            "is all in frame, but sits well off to one side. Re-centring it next "
            "session would give it more room and a bit more margin to crop with.",
            coverage, off_centre,
        )
    return FramingResult(
        "centred",
        "is nicely centred and completely inside the frame — well framed.",
        coverage, off_centre,
    )


@dataclass(frozen=True)
class RecentreCrop:
    """A fractional (0..1) crop rectangle that puts an off-centre object in the
    middle of the picture.

    The bounds use the same fractional convention as the editor's
    ``geometry.crop`` op, so they apply identically to the live-preview proxy and
    the full-resolution export. ``kept`` is the fraction of the frame's *area*
    the crop keeps (0–1), for the "keeps N% of the frame" copy.
    """

    x0: float
    y0: float
    x1: float
    y1: float
    kept: float


# How much clear space to leave around the object's own box, as a fraction of its
# radius. A crop that hugs the object looks cramped — worse than the off-centre
# framing it set out to fix — so a proposal that can't afford this margin is not
# made at all.
_RECENTRE_MARGIN = 0.6
# How far off the *crop's* centre the object may still sit. Cropping to put the
# object dead centre costs far more field than it's worth — an object 50 % of the
# way out would keep only a quarter of the picture — and it isn't what the beginner
# is asking for anyway. The goal is a picture the verdict itself would call well
# framed, so aim comfortably inside its own `_OFF_CENTRE_LIMIT` band rather than at
# the exact middle: the same standard, met with margin to spare.
_RECENTRE_TOLERANCE = 0.25
# Never offer a crop that keeps less than this much of the frame's area. Past that
# the beginner loses more field (and more of the clean, well-stacked interior) than
# the re-centring is worth — with the tolerance above, that's an object more than
# about half-way out to an edge. Same spirit as the verdict's refusal to guess: no
# offer is better than a bad one.
_RECENTRE_MIN_KEPT = 0.40


def recentre_crop(
    *,
    x_px: float,
    y_px: float,
    width_px: int,
    height_px: int,
    arcsec_per_px: float,
    size_arcmin: float | None,
    margin: float = _RECENTRE_MARGIN,
    tolerance: float = _RECENTRE_TOLERANCE,
    min_kept: float = _RECENTRE_MIN_KEPT,
) -> RecentreCrop | None:
    """The largest crop of this picture that brings an off-centre object back to
    the middle.

    Where :func:`framing_result_verdict` says *"it landed off to one side"*, this
    answers *"and here's the picture you could have"*: the biggest rectangle that
    fits inside the frame, keeps the frame's own aspect ratio (so the picture
    doesn't change shape) and leaves the object within ``tolerance`` of its
    centre — i.e. a picture the verdict itself would call well framed. Takes the
    same already-projected inputs as the verdict, so it stays pure arithmetic —
    no WCS, no astropy, no I/O.

    Returns ``None`` — no offer at all — whenever re-centring wouldn't honestly
    help: the object is already near the middle (nothing to fix), the crop can't
    keep :data:`_RECENTRE_MARGIN` of clear space around the object, or it would
    keep less than ``min_kept`` of the frame. Cropping also cannot un-clip an
    object that ran off an edge, and that case falls out of the margin test
    rather than needing its own rule.
    """
    if size_arcmin is None or size_arcmin <= 0:
        return None
    if width_px <= 0 or height_px <= 0 or arcsec_per_px <= 0:
        return None
    if not (math.isfinite(x_px) and math.isfinite(y_px)):
        return None

    hi_x, hi_y = float(width_px - 1), float(height_px - 1)
    if hi_x <= 0 or hi_y <= 0:
        return None
    radius_px = (size_arcmin * 60.0 / arcsec_per_px) / 2.0
    if radius_px <= 0:
        return None

    # Same off-centre measure the verdict reports, so the two always agree about
    # whether this picture is off-centre at all.
    half_x, half_y = hi_x / 2.0, hi_y / 2.0
    off_centre = max(abs(x_px - half_x) / half_x, abs(y_px - half_y) / half_y)
    if off_centre <= _OFF_CENTRE_LIMIT:
        return None  # already about as centred as it needs to be — nothing to offer

    # Per axis, the largest half-size a crop can have. A crop of half-size ``s``
    # whose centre sits within ``tolerance·s`` of the object must still fit the
    # frame, which needs ``s·(1 − tolerance) ≤ distance to the nearer edge``; and
    # it can never be wider than the frame itself.
    slack = 1.0 - min(max(tolerance, 0.0), 0.9)
    max_w = min(half_x, min(x_px, hi_x - x_px) / slack)
    max_h = min(half_y, min(y_px, hi_y - y_px) / slack)
    if max_w <= 0 or max_h <= 0:
        return None

    # Hold the frame's aspect ratio: the binding axis sets both half-sizes.
    aspect = hi_x / hi_y
    half_w = min(max_w, max_h * aspect)
    half_h = half_w / aspect

    # Room for the object plus clear space around it, or no offer.
    needed = radius_px * (1.0 + margin)
    if half_w < needed or half_h < needed:
        return None

    # Put the crop's centre on the object, pulled back only as far as the frame's
    # edges demand — so the object lands as close to the middle as it can get.
    cx = min(max(x_px, half_w), hi_x - half_w)
    cy = min(max(y_px, half_h), hi_y - half_h)

    w, h = float(width_px), float(height_px)
    x0 = min(max((cx - half_w) / w, 0.0), 1.0)
    x1 = min(max((cx + half_w) / w, 0.0), 1.0)
    y0 = min(max((cy - half_h) / h, 0.0), 1.0)
    y1 = min(max((cy + half_h) / h, 0.0), 1.0)
    kept = (x1 - x0) * (y1 - y0)
    if kept < min_kept:
        return None
    return RecentreCrop(x0, y0, x1, y1, kept)
