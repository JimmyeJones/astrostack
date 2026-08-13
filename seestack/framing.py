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
