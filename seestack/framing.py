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
