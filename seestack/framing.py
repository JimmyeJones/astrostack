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


# Panels have to overlap or there is nothing for the stitch to align on, so a
# panel *steps* by less than its own width. A tenth of a frame is the usual
# margin (and what the Seestar's own mosaic mode leaves), which is why the grid
# below tiles by ``fov - overlap`` after the first panel rather than by ``fov``.
MOSAIC_PANEL_OVERLAP = 0.10


@dataclass(frozen=True)
class MosaicPlan:
    """"How big a mosaic?" — the panel grid an object's span actually needs.

    ``framing_hint`` tells a beginner to "shoot it in mosaic mode" and stops
    exactly where their next question starts: *how big a mosaic?* A non-expert
    has no idea whether that means a 2×2 or a 4×5, so they either don't start or
    under-shoot. ``text`` is a complete, ready-to-render sentence (unlike the
    hint's verb phrase, it needs no name prefix), and ``cols``/``rows`` are along
    the frame's long and short edges respectively.
    """

    cols: int
    rows: int
    panels: int
    text: str


def _panels_across(extent_arcmin: float, fov_arcmin: float, step_arcmin: float) -> int:
    """How many overlapping panels of ``fov`` span ``extent`` along one axis.

    The *first* panel covers a full field; each one after it adds only its step
    (the rest is the overlap the stitch needs). One panel whenever the extent
    fits a single field — the overlap is between panels, so it can't eat into a
    one-panel field.
    """
    if extent_arcmin <= fov_arcmin:
        return 1
    return int(math.ceil((extent_arcmin - fov_arcmin) / step_arcmin)) + 1


def mosaic_plan(
    size_arcmin: float | None,
    size_minor_arcmin: float | None = None,
    *,
    fov_long_arcmin: float = SEESTAR_FOV_LONG_ARCMIN,
    fov_short_arcmin: float = SEESTAR_FOV_SHORT_ARCMIN,
    overlap: float = MOSAIC_PANEL_OVERLAP,
) -> MosaicPlan | None:
    """The panel grid needed to capture an object of this angular size.

    ``size_arcmin`` is the major axis and ``size_minor_arcmin`` the minor one;
    when the catalog records no minor axis the object is treated as **square**
    (its major axis both ways), which errs toward a bigger mosaic rather than
    promising a beginner that a too-small one will do. The object is assumed to
    be laid along the frame's long edge — the arrangement anyone would choose.

    Returns ``None`` when the size is unknown or the object fits in a single
    frame, so the caller says nothing rather than planning a one-panel "mosaic".
    """
    if size_arcmin is None or size_arcmin <= 0:
        return None
    major = float(size_arcmin)
    minor = major
    if size_minor_arcmin is not None and size_minor_arcmin > 0:
        minor = min(float(size_minor_arcmin), major)

    keep = max(0.0, min(0.9, float(overlap)))
    cols = _panels_across(major, fov_long_arcmin, fov_long_arcmin * (1.0 - keep))
    rows = _panels_across(minor, fov_short_arcmin, fov_short_arcmin * (1.0 - keep))
    if cols <= 1 and rows <= 1:
        return None

    panels = cols * rows
    return MosaicPlan(
        cols=cols, rows=rows, panels=panels,
        text=(f"About a {cols}×{rows} mosaic ({panels} panels) covers all of it."),
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


@dataclass(frozen=True)
class RecentreOutcome:
    """What asking for a re-centring crop came to — the crop, or *why not*.

    :func:`recentre_crop` answers only "is there an offer?", which leaves the
    worst-framed pictures with *less* to say than the mildly off-centre ones: a
    picture too far out to rescue silently gets no offer and no explanation. This
    carries the reason alongside, so a caller can say the honest sentence instead
    of going quiet. ``reason`` is a stable machine token:

    - ``None`` — there *is* a crop (``crop`` is set).
    - ``"unknown_size"`` / ``"degenerate"`` — nothing measurable to work from.
    - ``"centred"`` — already about as centred as it needs to be; nothing to fix.
    - ``"cramped"`` — a crop that met the aim would hug the object too tightly.
    - ``"too_destructive"`` — the crop exists but would throw away too much of
      the frame to be worth offering. ``kept`` is the fraction (0–1) it *would*
      have kept, which is the number that makes the refusal explainable.
    """

    crop: RecentreCrop | None
    reason: str | None
    kept: float | None = None


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
    the middle, or ``None`` when there is no honest offer to make.

    Thin view over :func:`recentre_outcome` for the callers that only care
    whether there is an offer — one implementation, two views, so the offer and
    its explanation can never disagree.
    """
    return recentre_outcome(
        x_px=x_px, y_px=y_px, width_px=width_px, height_px=height_px,
        arcsec_per_px=arcsec_per_px, size_arcmin=size_arcmin,
        margin=margin, tolerance=tolerance, min_kept=min_kept,
    ).crop


def recentre_outcome(
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
) -> RecentreOutcome:
    """The largest crop of this picture that brings an off-centre object back to
    the middle — and, when there isn't one, why not.

    Where :func:`framing_result_verdict` says *"it landed off to one side"*, this
    answers *"and here's the picture you could have"*: the biggest rectangle that
    fits inside the frame, keeps the frame's own aspect ratio (so the picture
    doesn't change shape) and leaves the object within ``tolerance`` of its
    centre — i.e. a picture the verdict itself would call well framed. Takes the
    same already-projected inputs as the verdict, so it stays pure arithmetic —
    no WCS, no astropy, no I/O.

    The crop is ``None`` — no offer at all — whenever re-centring wouldn't
    honestly help: the object is already near the middle (nothing to fix), the
    crop can't keep :data:`_RECENTRE_MARGIN` of clear space around the object, or
    it would keep less than ``min_kept`` of the frame. Cropping also cannot
    un-clip an object that ran off an edge, and that case falls out of the margin
    test rather than needing its own rule. Each of those carries its own
    ``reason`` (see :class:`RecentreOutcome`).
    """
    if size_arcmin is None or size_arcmin <= 0:
        return RecentreOutcome(None, "unknown_size")
    if width_px <= 0 or height_px <= 0 or arcsec_per_px <= 0:
        return RecentreOutcome(None, "degenerate")
    if not (math.isfinite(x_px) and math.isfinite(y_px)):
        return RecentreOutcome(None, "degenerate")

    hi_x, hi_y = float(width_px - 1), float(height_px - 1)
    if hi_x <= 0 or hi_y <= 0:
        return RecentreOutcome(None, "degenerate")
    radius_px = (size_arcmin * 60.0 / arcsec_per_px) / 2.0
    if radius_px <= 0:
        return RecentreOutcome(None, "degenerate")

    # Same off-centre measure the verdict reports, so the two always agree about
    # whether this picture is off-centre at all.
    half_x, half_y = hi_x / 2.0, hi_y / 2.0
    off_centre = max(abs(x_px - half_x) / half_x, abs(y_px - half_y) / half_y)
    if off_centre <= _OFF_CENTRE_LIMIT:
        # Already about as centred as it needs to be — nothing to offer.
        return RecentreOutcome(None, "centred")

    # Per axis, the largest half-size a crop can have. A crop of half-size ``s``
    # whose centre sits within ``tolerance·s`` of the object must still fit the
    # frame, which needs ``s·(1 − tolerance) ≤ distance to the nearer edge``; and
    # it can never be wider than the frame itself.
    slack = 1.0 - min(max(tolerance, 0.0), 0.9)
    max_w = min(half_x, min(x_px, hi_x - x_px) / slack)
    max_h = min(half_y, min(y_px, hi_y - y_px) / slack)
    if max_w <= 0 or max_h <= 0:
        return RecentreOutcome(None, "cramped")

    # Hold the frame's aspect ratio: the binding axis sets both half-sizes.
    aspect = hi_x / hi_y
    half_w = min(max_w, max_h * aspect)
    half_h = half_w / aspect

    # Room for the object plus clear space around it, or no offer.
    needed = radius_px * (1.0 + margin)
    if half_w < needed or half_h < needed:
        return RecentreOutcome(None, "cramped")

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
        # The one refusal worth explaining: the crop exists and we know exactly
        # how little of the picture it would leave, so a caller can say so rather
        # than going quiet on the worst-framed pictures.
        return RecentreOutcome(None, "too_destructive", kept)
    return RecentreOutcome(RecentreCrop(x0, y0, x1, y1, kept), None, kept)


# Below this the pointing is close enough that "nudge it" would be noise — a
# Seestar's own go-to and field rotation move it by more than this between
# sessions anyway, so a smaller correction isn't something a beginner can act on.
NUDGE_MIN_DEG = 0.05

#: Compass names for the eight 45° sectors, starting at due North and running
#: through East (the way a position angle is measured on the sky).
_COMPASS = ("north", "north-east", "east", "south-east",
            "south", "south-west", "west", "north-west")


@dataclass(frozen=True)
class RecentreNudge:
    """Which way — and how far — to move the telescope so the object lands in the
    middle next session.

    ``direction`` is one of eight plain compass words; ``degrees`` is the angular
    move; ``text`` is the ready-to-render sentence. ``short`` is the same move as
    a chip-sized phrase ("1.0° south") for surfaces with no room for the
    sentence — the night planner's dense target row — so the two never drift into
    two roundings of one number.
    """

    direction: str
    degrees: float
    text: str
    short: str = ""


def _friendly_degrees(deg: float) -> str:
    """A move a Seestar owner can actually aim by: degrees once it's a tenth of
    one or more, arcminutes below that (where "0.0°" would say nothing)."""
    if deg >= 0.1:
        return f"{deg:.1f}°"
    return f"{int(round(deg * 60.0))}'"


def recentre_nudge(
    *,
    centre_ra_deg: float,
    centre_dec_deg: float,
    object_ra_deg: float,
    object_dec_deg: float,
    min_deg: float = NUDGE_MIN_DEG,
) -> RecentreNudge | None:
    """Turn "re-centre it next session" into something a beginner can do.

    The framing verdict can already tell someone their target landed off to one
    side or ran off an edge — but "re-centre it" is advice you can't act on
    without knowing *which way*. This answers that from the two sky positions the
    caller already has: where the picture's centre actually pointed, and where the
    object really is. The mount has to move **toward** the object, so the
    direction is simply the object's bearing from the field centre.

    Deliberately spherical, not pixel-based: working from RA/Dec sidesteps every
    image-orientation sign hazard (a rotated canvas, a North-up-saved preview, the
    CD-matrix parity) — the answer is the same whichever way the picture is turned,
    because the sky isn't.

    Returns ``None`` when the answer would be noise or a guess: a non-finite
    input, a position at/over the pole (where "east" stops meaning anything
    useful), or a correction below ``min_deg``.
    """
    values = (centre_ra_deg, centre_dec_deg, object_ra_deg, object_dec_deg)
    if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in values):
        return None
    if abs(centre_dec_deg) >= 89.5 or abs(object_dec_deg) >= 89.5:
        return None

    d_dec = float(object_dec_deg) - float(centre_dec_deg)          # + = north
    d_ra = (float(object_ra_deg) - float(centre_ra_deg) + 180.0) % 360.0 - 180.0
    # RA degrees shrink toward the poles; convert to a true angular offset.
    d_east = d_ra * math.cos(math.radians((object_dec_deg + centre_dec_deg) / 2.0))

    degrees = math.hypot(d_east, d_dec)
    if not math.isfinite(degrees) or degrees < min_deg:
        return None

    # Position angle: 0° at North, increasing toward East — the convention the
    # compass names below are laid out in.
    bearing = math.degrees(math.atan2(d_east, d_dec)) % 360.0
    direction = _COMPASS[int(round(bearing / 45.0)) % 8]
    return RecentreNudge(
        direction,
        degrees,
        f"Next time, nudge your Seestar about {_friendly_degrees(degrees)} "
        f"{direction} before you start, and it'll sit in the middle.",
        f"{_friendly_degrees(degrees)} {direction}",
    )
