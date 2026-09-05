"""Will-it-fit framing hint: is a target bigger than *your* field of view?

A very common beginner surprise is that a smart telescope's single-frame field is
small, while some favourite targets — M31 (~3°), the Pleiades, the North America
Nebula, the Veil — are *larger than one frame*. A beginner who points at one of
those and shoots a single frame gets a cropped result without realising they
needed **mosaic mode**.

This module answers "will it fit?" from a target's angular size alone: pure,
offline, no dependency. It compares the object's major-axis size (arcmin, from the
bundled catalog) against a single-frame field and returns one of a few friendly,
plain-language verdicts — or ``None`` when the size is unknown (we never guess:
absent a size, no hint).

**Which field, though — that is the whole point of :class:`FrameField`.** The
answer is a property of the owner's telescope, not a constant: an S30's frame is
~128' × 72' and an S50's ~77' × 44', a factor of 1.66 on each edge. Pass the field
derived from the owner's own solved frames (:func:`frame_field_from_solve`)
wherever one is available, exactly as ``AGENTS.md`` §1 "Owner facts" requires —
"where the model matters, derive it from the frame's own ``FOCALLEN``/``XPIXSZ``
rather than assuming either".
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# ⚠️ These are the **ZWO Seestar S50's** single-frame field in arcminutes — a
# ~1.29° × 0.72° rectangle (250 mm over its 1920×1080 2.9 µm sensor). They are the
# *fallback* used only when nothing better is known (an install with no solved
# frame yet), NOT "the Seestar's field": the owner has an **S30**, whose 150 mm
# objective gives ~128' × 72' (AGENTS.md §1 "Owner facts", confirmed 2026-07-24).
# Shipped in v0.130.0 eight days before that confirmation and never revisited, so
# every framing verdict and panel count was an S50's until v0.352.0.
# **Do not flip these to the S30's numbers** — that is the same bug with a
# different wrong answer for the next owner. Derive the field instead:
# :func:`frame_field_from_solve`.
SEESTAR_FOV_LONG_ARCMIN = 77.0
SEESTAR_FOV_SHORT_ARCMIN = 44.0


@dataclass(frozen=True)
class FrameField:
    """One telescope's single-frame field of view, in arcminutes.

    ``long_arcmin``/``short_arcmin`` are the frame's two edges, longest first —
    which edge is which on the sky depends on rotation, and every verdict here
    compares against both, so the pair is all that is needed.
    """

    long_arcmin: float
    short_arcmin: float


#: The field assumed when the owner's own frames can't answer — see the warning on
#: the constants above. Callers that *can* answer must pass their own.
FALLBACK_FIELD = FrameField(SEESTAR_FOV_LONG_ARCMIN, SEESTAR_FOV_SHORT_ARCMIN)


def frame_field_from_solve(
    pixscale_arcsec: float | None,
    width_px: int | float | None,
    height_px: int | float | None,
) -> FrameField | None:
    """The single-frame field a *solved* frame actually had, or ``None``.

    The plate solve already measured the thing that matters — ``pixscale_arcsec``
    — and the frame's own pixel dimensions give the rest, so this needs no header
    read and no assumption about the model. It is also the *honest* number: a
    measured plate scale beats the header's nominal ``FOCALLEN`` when the two
    disagree.

    Returns ``None`` when any input is missing or non-positive, or when the
    result is outside a physically-sensible amateur range (a mis-solved frame
    must not hand the framing advice an absurd field — the caller then falls back
    to :data:`FALLBACK_FIELD`, i.e. exactly today's behaviour). The bounds mirror
    ``fits_loader.fov_deg_from_header``'s 0.05°–20° clamp, in arcminutes.
    """
    if pixscale_arcsec is None or width_px is None or height_px is None:
        return None
    try:
        scale = float(pixscale_arcsec)
        w, h = float(width_px), float(height_px)
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(v) for v in (scale, w, h)):
        return None
    if scale <= 0 or w <= 0 or h <= 0:
        return None
    long_arcmin = scale * max(w, h) / 60.0
    short_arcmin = scale * min(w, h) / 60.0
    if not (3.0 <= long_arcmin <= 1200.0):  # 0.05° … 20°, as arcminutes
        return None
    return FrameField(long_arcmin, short_arcmin)


def _edges(
    field: FrameField | None, fov_long_arcmin: float, fov_short_arcmin: float,
) -> tuple[float, float]:
    """The (long, short) edges to judge against: the measured field when there is
    one, otherwise whatever the caller passed (which defaults to the fallback)."""
    if field is None:
        return fov_long_arcmin, fov_short_arcmin
    return field.long_arcmin, field.short_arcmin


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
    field: FrameField | None = None,
    fov_long_arcmin: float = SEESTAR_FOV_LONG_ARCMIN,
    fov_short_arcmin: float = SEESTAR_FOV_SHORT_ARCMIN,
) -> FramingHint | None:
    """Verdict on whether an object of major-axis ``size_arcmin`` fits one frame.

    ``field`` is the owner's *own* single-frame field
    (:func:`frame_field_from_solve`) and wins when given; without it the
    ``fov_*`` arguments apply, which default to the S50 fallback — see the
    warning on :data:`SEESTAR_FOV_LONG_ARCMIN`.

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
    fov_long_arcmin, fov_short_arcmin = _edges(
        field, fov_long_arcmin, fov_short_arcmin)

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
    field: FrameField | None = None,
    fov_long_arcmin: float = SEESTAR_FOV_LONG_ARCMIN,
    fov_short_arcmin: float = SEESTAR_FOV_SHORT_ARCMIN,
    overlap: float = MOSAIC_PANEL_OVERLAP,
) -> MosaicPlan | None:
    """The panel grid needed to capture an object of this angular size.

    ``field`` is the owner's own single-frame field and wins over the ``fov_*``
    fallbacks — a panel count computed against the wrong telescope is wrong by
    the square of the field ratio, which for an S30 read as an S50 is M 31 in
    **15** panels instead of 6.

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
    fov_long_arcmin, fov_short_arcmin = _edges(
        field, fov_long_arcmin, fov_short_arcmin)
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


# What shape of picture a verdict is judging. Everything this function measures
# is measured against the run's **canvas**, and on a single-field stack that
# canvas *is* one frame of sky — so "your frame", "this picture" and "the canvas"
# are the same thing and "shoot it in mosaic mode" is the right next step.
#
# A **mosaic** canvas is several frames wide, and then the frame-shaped wording
# says two things this function never tested: it calls a multi-panel canvas "your
# frame", and it tells an owner who already shot a mosaic to go and shoot one.
# The owner of this app is a heavy mosaic user (``AGENTS.md`` §1), so that is the
# common case, not the exotic one — hence a canvas kind rather than one voice.
CANVAS_FRAME = "frame"
CANVAS_MOSAIC = "mosaic"


@dataclass(frozen=True)
class FramingResult:
    """A plain-language "did I frame it well?" verdict for a *finished* stack.

    Where :class:`FramingHint` answers "will it fit?" before the shoot, this
    answers "did it actually land well?" from the result itself. ``level`` is a
    stable machine token the UI can style on; ``text`` is the ready-to-render
    beginner sentence, which — like the hint's — is prefixed by the caller with
    the object's name. ``coverage`` is the fraction (0–1) of the object's extent
    that made it into the canvas, and ``off_centre`` how far its centre sits from
    the canvas's, as a fraction of the half-canvas (0 = dead centre, 1 = on the
    edge).

    ``canvas`` is :data:`CANVAS_FRAME` or :data:`CANVAS_MOSAIC` — which shape of
    picture the sentence is talking about, so a UI writing its own heading can
    match the wording instead of contradicting it.
    """

    level: str        # "centred" | "off_centre" | "clipped" | "partial"
    text: str
    coverage: float
    off_centre: float
    canvas: str = CANVAS_FRAME


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
    canvas: str = CANVAS_FRAME,
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

    ``canvas`` says whether the picture being judged is one frame of sky
    (:data:`CANVAS_FRAME`, the default and every caller's behaviour before this
    argument existed) or a multi-panel mosaic (:data:`CANVAS_MOSAIC`). Only the
    **wording** changes: every number here is measured against the canvas either
    way. It matters because the frame-shaped sentences claim things this function
    cannot see — that the canvas is a single frame, and that shooting a mosaic is
    the fix — and on a mosaic both are false, the second of them advice the owner
    has already taken.
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

    mosaic = canvas == CANVAS_MOSAIC
    kind = CANVAS_MOSAIC if mosaic else CANVAS_FRAME

    if coverage < _ALL_IN:
        # Two very different problems share "some of it is missing", and they have
        # opposite fixes: an object that *would* have fitted was simply pointed at
        # badly (re-centre), while one bigger than the canvas can never fit in a
        # picture this size however well aimed (a mosaic, or a bigger one). Say
        # the right one.
        fits_in_canvas = 2.0 * radius_px <= hi_x and 2.0 * radius_px <= hi_y
        if fits_in_canvas:
            if mosaic:
                return FramingResult(
                    "clipped",
                    f"runs off the edge of this mosaic — about {_rounded_pct(coverage)}% "
                    "of it made it in. It would fit whole, so just re-centre the mosaic "
                    "next session.",
                    coverage, off_centre, kind,
                )
            return FramingResult(
                "clipped",
                f"runs off the edge of the frame — about {_rounded_pct(coverage)}% of "
                "it made it in. It would fit whole, so just re-centre it next session.",
                coverage, off_centre, kind,
            )
        if mosaic:
            # They already shot a mosaic; "shoot it in mosaic mode" would be
            # advice they took. The honest next step is a wider one.
            return FramingResult(
                "partial",
                f"is bigger than this mosaic — only about {_rounded_pct(coverage)}% of "
                "it is in this picture. Adding more panels next session would capture "
                "the rest.",
                coverage, off_centre, kind,
            )
        return FramingResult(
            "partial",
            f"is bigger than your frame — only about {_rounded_pct(coverage)}% of it "
            "is in this picture. Shoot it in mosaic mode to capture all of it.",
            coverage, off_centre, kind,
        )
    if off_centre > _OFF_CENTRE_LIMIT:
        return FramingResult(
            "off_centre",
            ("is all in this mosaic" if mosaic else "is all in frame")
            + ", but sits well off to one side. Re-centring it next "
            "session would give it more room and a bit more margin to crop with.",
            coverage, off_centre, kind,
        )
    return FramingResult(
        "centred",
        "is nicely centred and completely inside "
        + ("this mosaic" if mosaic else "the frame")
        + " — well framed.",
        coverage, off_centre, kind,
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
