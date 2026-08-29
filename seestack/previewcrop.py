"""What a run's *stored preview PNG* shows of its stack canvas.

The preview is normally a plain uniform downscale of the master FITS canvas, and
every surface that lines up with it — the Sky map's tile placement and coverage
overlay, History's object pins and scale bar, the shared picture's scale bar, the
wallpaper crop — assumes exactly that. One path breaks the assumption: the
one-click **Process target** auto-edit rewrites the preview through the Auto
recipe, and Auto ends with a ``geometry.crop`` that trims a mosaic's ragged
border (``auto_crop_border``, on by default). The stored picture is then a *crop*
of the canvas, and nothing recorded that — so the consumers place their geometry
on the full canvas and land off by the crop's offset and scale.

This module is the vocabulary for recording it, mirroring what
``stack_runs.preview_north_up_deg`` does for the other way a preview can stop
being a plain downscale. A run carries one of three states:

* **NULL / absent** — a plain full-canvas downscale. Every run that predates this
  column, every stack-time preview, and every un-cropped auto-edit. Consumers
  behave exactly as they always have.
* **bounds** — the fractional ``(x0, y0, x1, y1)`` of the canvas the preview
  shows. Consumers compose it.
* **unknown** — the preview came out of a recipe whose geometry can't be reduced
  to a plain crop (a rotate, say). Consumers must *decline* to place geometry
  rather than guess: a confidently-misplaced overlay is worse than none.

Pure and dependency-free (JSON + arithmetic) so the engine, the webapp and the
tests all speak the same shape.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

# The stored marker for "this preview's geometry can't be reconciled with the
# canvas" — see the module docstring. Consumers decline placement on it.
UNKNOWN = "unknown"


@dataclass(frozen=True)
class PreviewCrop:
    """Fractional bounds of the canvas a stored preview shows (0..1, x0 < x1)."""

    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def w_frac(self) -> float:
        return self.x1 - self.x0

    @property
    def h_frac(self) -> float:
        return self.y1 - self.y0

    @property
    def is_full(self) -> bool:
        """True when this crop shows the whole canvas (i.e. means nothing)."""
        return (abs(self.x0) < 1e-6 and abs(self.y0) < 1e-6
                and abs(self.x1 - 1.0) < 1e-6 and abs(self.y1 - 1.0) < 1e-6)

    def as_tuple(self) -> tuple[float, float, float, float]:
        return (self.x0, self.y0, self.x1, self.y1)

    def compose(self, other: PreviewCrop) -> PreviewCrop:
        """This crop followed by ``other`` (whose bounds are fractions of *this*
        crop's output), as one crop of the original canvas."""
        return PreviewCrop(
            self.x0 + other.x0 * self.w_frac,
            self.y0 + other.y0 * self.h_frac,
            self.x0 + other.x1 * self.w_frac,
            self.y0 + other.y1 * self.h_frac,
        )

    def to_json(self) -> str:
        return json.dumps({"x0": self.x0, "y0": self.y0, "x1": self.x1, "y1": self.y1})


FULL = PreviewCrop(0.0, 0.0, 1.0, 1.0)


def _clamp01(v: float) -> float:
    return min(1.0, max(0.0, float(v)))


def make_crop(x0: float, y0: float, x1: float, y1: float) -> PreviewCrop | None:
    """A clamped, ordered :class:`PreviewCrop`, or ``None`` when the bounds are
    non-finite or degenerate (zero width/height) — mirroring ``geometry.crop``'s
    own "ignore a degenerate crop" behaviour rather than recording a nonsense
    rectangle."""
    try:
        raw = [float(v) for v in (x0, y0, x1, y1)]
    except (TypeError, ValueError):
        return None
    # Reject NaN *before* clamping: `max(0.0, nan)` quietly returns 0.0, which
    # would turn a nonsense bound into a confident full-width crop.
    if not all(v == v for v in raw):
        return None
    xs = sorted((_clamp01(raw[0]), _clamp01(raw[2])))
    ys = sorted((_clamp01(raw[1]), _clamp01(raw[3])))
    if xs[1] - xs[0] <= 0.0 or ys[1] - ys[0] <= 0.0:
        return None
    return PreviewCrop(xs[0], ys[0], xs[1], ys[1])


def parse_preview_crop(text: str | None) -> PreviewCrop | str | None:
    """Read a stored ``stack_runs.preview_crop_json`` value.

    Returns ``None`` for NULL/blank/unparseable (the plain-downscale default —
    an unreadable value must never be *more* alarming than an absent one),
    :data:`UNKNOWN` for the "can't be reconciled" marker, and a
    :class:`PreviewCrop` otherwise. A recorded full-canvas crop reads back as
    ``None`` so callers only ever have to check one thing for "no crop"."""
    if not text:
        return None
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    if data.get(UNKNOWN):
        return UNKNOWN
    try:
        crop = make_crop(data["x0"], data["y0"], data["x1"], data["y1"])
    except (KeyError, TypeError, ValueError):
        return None
    if crop is None or crop.is_full:
        return None
    return crop


def preview_crop_json(crop: PreviewCrop | str | None) -> str | None:
    """The value to store for a crop, :data:`UNKNOWN`, or "no crop" (``None``).

    A full-canvas crop stores as ``None`` (nothing to compose), so a re-render
    that stops cropping clears the column rather than leaving a stale rectangle
    behind — the same "always written, never left alone" rule the North-up angle
    follows."""
    if crop is None:
        return None
    if crop == UNKNOWN:
        return json.dumps({UNKNOWN: True})
    if not isinstance(crop, PreviewCrop) or crop.is_full:
        return None
    return crop.to_json()


def crop_pixel_box(crop: PreviewCrop | None, width: int, height: int
                   ) -> tuple[int, int, int, int]:
    """The crop as integer pixel bounds ``(x0, y0, x1, y1)`` on a ``width ×
    height`` grid, clamped to at least 1 px per axis. ``None`` gives the whole
    grid, so callers can use this unconditionally."""
    if crop is None:
        return (0, 0, int(width), int(height))
    x0 = min(max(int(round(crop.x0 * width)), 0), max(int(width) - 1, 0))
    y0 = min(max(int(round(crop.y0 * height)), 0), max(int(height) - 1, 0))
    x1 = max(min(int(round(crop.x1 * width)), int(width)), x0 + 1)
    y1 = max(min(int(round(crop.y1 * height)), int(height)), y0 + 1)
    return (x0, y0, x1, y1)
