"""Pick a "nice" angular scale bar for a finished stack, from its pixel scale.

A beginner has no intuition for angular scale — they don't know whether their
M31 frame is 1° or 3° across, or how the Ring Nebula's tiny apparent size
compares to what they can see. A small scale bar ("30′") plus a plain-language
full-Moon comparison ("the whole frame is about 2.5 full Moons wide") turns the
picture into something they *understand* and can caption when sharing.

This is a pure, offline helper: given the local pixel scale (arcsec/px) and the
image dimensions it chooses a round bar length that spans a comfortable fraction
of the frame and returns its label, its length as a fraction of the image width
(so the frontend can draw it over any scaled preview), and a Moon comparison.
No WCS object, no astropy, no I/O — trivially unit-tested.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

# The full Moon's mean apparent diameter, in arcseconds (~31′). Used for the
# plain-language "how big is this compared to the Moon?" comparison.
MOON_DIAMETER_ARCSEC = 31.0 * 60.0  # 1860″

# A ladder of "nice" bar lengths in arcseconds: 1″…5°, the round numbers an
# astronomer would actually label a scale bar with (seconds → minutes → degrees).
_LADDER_ARCSEC: tuple[float, ...] = (
    1, 2, 5, 10, 15, 30,           # arcseconds
    60, 120, 300, 600, 900, 1800,  # 1′, 2′, 5′, 10′, 15′, 30′
    3600, 7200, 18000,             # 1°, 2°, 5°
)

# The bar should span at most this fraction of the frame width (so it never
# dominates the picture); we pick the largest ladder rung that fits under it.
_MAX_BAR_FRACTION = 0.25


@dataclass(frozen=True)
class ScaleBar:
    """A chosen scale bar for one image."""

    # The bar length in arcseconds (a rung of the nice-number ladder).
    arcsec: float
    # A friendly label for that length ("30″" / "15′" / "2°").
    label: str
    # The bar length as a fraction of the image width (0–1), so the frontend can
    # draw it at ``fraction · rendered_width`` over any scaled preview.
    fraction: float
    # The whole frame's width in arcminutes (handy context / captions).
    frame_arcmin: float
    # One plain-language sentence comparing the frame to the full Moon.
    moon_comparison: str

    def to_dict(self) -> dict:
        return asdict(self)


def _format_length(arcsec: float) -> str:
    """A friendly label for a ladder length: seconds, arcminutes, or degrees.

    The ladder rungs are chosen so each maps to a clean whole number in its unit
    (e.g. 1800″ = 30′, 3600″ = 1°), so no fractional labels appear."""
    if arcsec < 60:
        return f"{int(round(arcsec))}″"          # arcseconds ″
    if arcsec < 3600:
        return f"{int(round(arcsec / 60))}′"      # arcminutes ′
    return f"{int(round(arcsec / 3600))}°"        # degrees °


def _moon_comparison(frame_arcsec: float) -> str:
    """Plain-language "how big is the whole frame vs the full Moon?"."""
    moons = frame_arcsec / MOON_DIAMETER_ARCSEC
    if moons < 0.5:
        # Smaller than half a Moon — compare as a fraction of the Moon's width.
        frac = frame_arcsec / MOON_DIAMETER_ARCSEC
        pct = int(round(frac * 100))
        return f"the whole frame is about {pct}% the width of the full Moon"
    if moons < 1.5:
        return "the whole frame is about as wide as the full Moon"
    # A tidy one-decimal count of Moons for anything bigger.
    return f"the whole frame is about {moons:.1f} full Moons wide"


def scale_bar_for(
    arcsec_per_px: float, width_px: int, height_px: int = 0,
) -> ScaleBar | None:
    """Choose a scale bar for an image with the given pixel scale and width.

    ``arcsec_per_px`` is the local plate scale (arcsec per pixel) and ``width_px``
    the image width in pixels. ``height_px`` is accepted for symmetry but the bar
    is sized against the width. Returns ``None`` when the inputs can't yield a
    sensible bar (non-finite / non-positive scale or width) — the caller then
    simply omits the scale bar (older/edited runs, no WCS).

    The chosen bar is the *largest* nice-number rung whose length stays within
    :data:`_MAX_BAR_FRACTION` of the frame width; if the frame is so tiny that
    even 1″ overflows that, we fall back to the smallest rung (still labelled
    honestly, just wider than the target) so a bar is always offered when there
    is a real scale to show."""
    if not (arcsec_per_px > 0) or width_px <= 0:
        return None
    # math.isfinite guard without importing math for one call.
    if arcsec_per_px != arcsec_per_px or arcsec_per_px in (float("inf"), float("-inf")):
        return None

    frame_arcsec = arcsec_per_px * width_px
    if not (frame_arcsec > 0):
        return None
    limit = frame_arcsec * _MAX_BAR_FRACTION

    # Largest ladder rung within the width limit; else the smallest rung.
    chosen = None
    for rung in _LADDER_ARCSEC:
        if rung <= limit:
            chosen = rung
    if chosen is None:
        chosen = _LADDER_ARCSEC[0]

    return ScaleBar(
        arcsec=float(chosen),
        label=_format_length(chosen),
        fraction=float(chosen) / frame_arcsec,
        frame_arcmin=frame_arcsec / 60.0,
        moon_comparison=_moon_comparison(frame_arcsec),
    )
