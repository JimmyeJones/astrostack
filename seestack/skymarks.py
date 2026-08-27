"""Scale bar and sky compass baked into a shared picture.

Every published astrophoto carries two small marks a beginner never thinks to
add: a **scale bar** ("this much of the picture is 30 arcminutes") and a
**North/East rose** ("this is which way up the sky is"). They are what makes a
picture read as a real astrophoto rather than a pretty smudge, and they quietly
teach the beginner the two facts they most often ask about their own result —
*how big is it?* and *which way is up?*

The app already knows both numbers exactly: a finished stack stores its solved
output WCS, which carries the pixel scale (:mod:`seestack.scalebar` turns that
into a round bar) and the field orientation. But the in-app overlay is drawn in
the browser, so it **doesn't travel with the file** — the moment a beginner
downloads or shares the picture, both marks are gone. This module bakes them
into the pixels, the same way :mod:`seestack.nameplate` bakes the acquisition
caption.

Two deliberate choices worth knowing:

* **The marks live along the *top* edge** (bar top-left, rose top-right). The
  bottom of a shared picture is already the app's caption zone — the nameplate
  draws its footer bar there and the keepsake sets its caption beneath — so
  putting the sky marks anywhere along the bottom would mean one covering the
  other. Along the top they compose with both.
* **The directions are derived numerically from the WCS**, by asking it where
  Dec-increasing and RA-increasing go in pixel space, exactly as
  :func:`seestack.render.orient.north_up_rotation_deg` does. Nothing here
  hand-rolls a ``CROTA``/``CD`` sign (the sign hazard the sky-atlas overlay is
  still gated on), so an East/West mirror can't creep in from a convention
  mismatch — and a mirrored field (negative parity) is drawn mirrored because
  that is what the WCS says.

Pure and offline, like its siblings: it draws onto a PIL image with Pillow's
built-in scalable font, so there is no bundled asset, no network, and no
``webapp`` imports. The render is display-time only — it never touches the
stored FITS/preview or the linear science data — and every half is best-effort:
a run with a scale but no usable orientation gets a bar and no rose, and a run
with neither is a clean no-op that returns the picture unchanged.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

#: Mark colour — the same pale blue-white the in-app overlay uses, so a picture
#: downloaded with marks looks like the one on screen.
MARK_RGB = (223, 241, 255)
#: Every mark is drawn over its own dark halo so it stays readable against a
#: bright nebula core as well as against empty sky.
HALO_RGB = (8, 12, 22)

#: Largest RA offset :func:`sky_directions` will step to find East. Past this the
#: step swings far enough round a nearby pole that its chord stops pointing the
#: way the tangent does, so we shrink the on-sky step instead of widening the RA.
_MAX_RA_STEP_DEG = 1.0


@dataclass(frozen=True)
class SkyDirections:
    """Where North and East point on screen, in degrees.

    Angles are measured counter-clockwise from screen-right (+x) with screen-up
    positive — the same convention :func:`seestack.render.orient.
    north_up_rotation_deg` measures in, so "North is up" is ``north_deg == 90``.
    """

    north_deg: float
    east_deg: float


@dataclass(frozen=True)
class SkyMarks:
    """The concrete marks to draw on one specific image, in *its* pixels.

    ``bar_px`` is the scale bar's length in pixels **of the image it will be
    drawn on** — the caller scales :attr:`seestack.scalebar.ScaleBar.fraction`
    by that image's width, so a preview, a full-res render and a north-up
    rotated frame each get a bar of the right length. ``bar_label`` must be
    drawable with the bundled font (see :func:`seestack.scalebar.ScaleBar.
    ascii_label` — the ′/″ prime characters have no glyph and would bake a
    hollow box into the picture).

    Either half may be absent: ``bar_px``/``bar_label`` for a run with no usable
    pixel scale, ``directions`` for one with no usable orientation.
    """

    bar_px: float | None = None
    bar_label: str = ""
    directions: SkyDirections | None = None

    @property
    def has_scale(self) -> bool:
        return bool(self.bar_px and self.bar_px > 0 and self.bar_label)

    @property
    def has_compass(self) -> bool:
        return self.directions is not None

    def __bool__(self) -> bool:
        """False when there is nothing to draw, so a caller can gate on the
        marks themselves rather than testing both halves."""
        return self.has_scale or self.has_compass


def _norm180(deg: float) -> float:
    """Normalise an angle to ``(-180, 180]``."""
    out = (deg + 180.0) % 360.0 - 180.0
    return 180.0 if out == -180.0 else out


def sky_directions(wcs, width: int, height: int) -> SkyDirections | None:  # noqa: ANN001
    """Where North and East point on an image described by ``wcs``.

    Asks the WCS itself: step a small amount North (increasing Dec) and East
    (increasing RA) from the image centre and see which way the pixel position
    moves. Near the North pole the Dec step is taken southward and the vector
    flipped, and the RA step is divided by ``cos(dec)`` so it stays a small
    *angular* step at high declination.

    Returns ``None`` when there is no usable WCS or the geometry is degenerate
    (a non-finite projection, or a step that doesn't move) — the caller then
    simply omits the rose rather than drawing a made-up direction.
    """
    if wcs is None or width <= 0 or height <= 0:
        return None
    try:
        cx = (width - 1) / 2.0
        cy = (height - 1) / 2.0
        ra0, dec0 = (float(v) for v in wcs.all_pix2world(cx, cy, 0))
        if not (math.isfinite(ra0) and math.isfinite(dec0)):
            return None

        step_deg = 0.05
        # North: step in Dec, flipping the vector if the pole is in the way.
        dec1 = dec0 + step_deg
        north_flip = 1.0
        if dec1 >= 90.0:
            dec1 = dec0 - step_deg
            north_flip = -1.0
        nx, ny = (float(v) for v in wcs.all_world2pix(ra0, dec1, 0))

        # East: step in RA. Dividing by cos(dec) keeps the *on-sky* step the same
        # size at any declination, but close to a pole that asks for a huge RA
        # offset, and a step that swings a long way round the pole stops being a
        # local direction. So the RA offset is capped (shrinking the on-sky step
        # instead), and a truly degenerate pole gives no rose at all.
        cosd = math.cos(math.radians(dec0))
        if abs(cosd) < 1e-9:
            return None
        dra = min(step_deg / abs(cosd), _MAX_RA_STEP_DEG)
        ra1 = ra0 + dra
        ex, ey = (float(v) for v in wcs.all_world2pix(ra1, dec0, 0))

        north = _screen_angle((nx - cx) * north_flip, (ny - cy) * north_flip)
        east = _screen_angle(ex - cx, ey - cy)
    except Exception:  # noqa: BLE001 — a degenerate WCS just means "no rose"
        return None
    if north is None or east is None:
        return None
    return SkyDirections(north_deg=north, east_deg=east)


def _screen_angle(dcol: float, drow: float) -> float | None:
    """The on-screen angle (deg CCW from +x, up positive) of a pixel-space step.

    Rows increase downward, so screen-up is ``-drow``. ``None`` for a
    non-finite or zero-length step."""
    if not (math.isfinite(dcol) and math.isfinite(drow)):
        return None
    if abs(dcol) < 1e-9 and abs(drow) < 1e-9:
        return None
    return _norm180(math.degrees(math.atan2(-drow, dcol)))


def rotated(directions: SkyDirections | None, ccw_deg: float) -> SkyDirections | None:
    """The same directions as seen after the image is rotated ``ccw_deg``
    counter-clockwise (PIL's ``Image.rotate`` sense).

    The share path can rotate a picture North-up *after* the WCS was read, so
    the rose has to follow the pixels. Rotating the image CCW by β moves every
    on-screen direction to ``angle + β``. ``None`` in, ``None`` out."""
    if directions is None:
        return None
    return SkyDirections(
        north_deg=_norm180(directions.north_deg + ccw_deg),
        east_deg=_norm180(directions.east_deg + ccw_deg),
    )


# Geometry, all as a fraction of the picture's **short** side so a wide mosaic
# and a square crop get proportionally the same marks.
_MARGIN_FRACTION = 0.030
_MIN_MARGIN_PX = 8
_LABEL_FRACTION = 0.026
_MIN_LABEL_PX = 10
_ROSE_FRACTION = 0.055
_MIN_ROSE_PX = 16
_LINE_FRACTION = 0.0035
_MIN_LINE_PX = 2


def _load_font(size: int):
    """Pillow's built-in scalable font at ``size`` px — no bundled asset.

    Mirrors :func:`seestack.keepsake._load_font` (same Pillow>=10.2 pin, same
    graceful fall-back) rather than reaching across for another module's
    private helper."""
    from PIL import ImageFont

    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # pragma: no cover — Pillow <10.1 (below our pin)
        return ImageFont.load_default()


def _line(draw, xy0, xy1, width: int) -> None:  # noqa: ANN001
    """A mark line drawn over its own dark halo, so it survives a bright
    background as well as empty sky."""
    draw.line([xy0, xy1], fill=HALO_RGB, width=width + 2)
    draw.line([xy0, xy1], fill=MARK_RGB, width=width)


def _text(draw, xy, text: str, font, anchor: str) -> None:  # noqa: ANN001
    """Mark text with the same dark halo, via Pillow's stroke."""
    draw.text(xy, text, font=font, fill=MARK_RGB, anchor=anchor,
              stroke_width=2, stroke_fill=HALO_RGB)


def draw_sky_marks(img, marks: SkyMarks):  # noqa: ANN001, ANN201
    """Return a new RGB ``PIL.Image``: ``img`` with the scale bar drawn at the
    top-left and the North/East rose at the top-right.

    The canvas size is unchanged — these are marks *on* the picture, not a frame
    around it, so a wallpaper stays wallpaper-shaped. When ``marks`` has nothing
    to draw the image is returned unchanged (converted to RGB if it wasn't), so
    a run with no usable WCS is a clean no-op exactly as an empty nameplate is.
    """
    from PIL import ImageDraw

    picture = img.convert("RGB") if img.mode != "RGB" else img
    if not marks:
        return picture

    picture = picture.copy()
    width, height = picture.size
    short = max(1, min(width, height))
    margin = max(_MIN_MARGIN_PX, round(short * _MARGIN_FRACTION))
    line_w = max(_MIN_LINE_PX, round(short * _LINE_FRACTION))
    font = _load_font(max(_MIN_LABEL_PX, round(short * _LABEL_FRACTION)))
    draw = ImageDraw.Draw(picture)

    if marks.has_scale:
        # Never let the bar run past the picture: a tiny share of a wide field
        # can ask for a bar longer than the canvas, and a bar that leaves the
        # frame is worse than a slightly cramped one.
        bar = min(float(marks.bar_px), max(1.0, width - 2.0 * margin))
        x0, y = float(margin), float(margin)
        x1 = x0 + bar
        _line(draw, (x0, y), (x1, y), line_w)
        # End serifs, so the bar reads as a measured span rather than a stray
        # line — the same tick-ended shape the in-app overlay draws.
        serif = max(line_w * 2, round(short * 0.010))
        _line(draw, (x0, y - serif), (x0, y + serif), line_w)
        _line(draw, (x1, y - serif), (x1, y + serif), line_w)
        _text(draw, ((x0 + x1) / 2.0, y + serif + line_w), marks.bar_label,
              font, "ma")

    if marks.directions is not None:
        rose = max(_MIN_ROSE_PX, round(short * _ROSE_FRACTION))
        # The letter sits just beyond its arm's tip, so the rose's *centre* has
        # to stand an arm + a letter + the margin in from the corner — whichever
        # way the arms happen to point.
        gap = max(6, round(short * 0.018))
        pad = rose + gap + margin
        cx = float(width - pad)
        cy = float(pad)
        for angle, label in ((marks.directions.north_deg, "N"),
                             (marks.directions.east_deg, "E")):
            rad = math.radians(angle)
            dx, dy = math.cos(rad), -math.sin(rad)  # rows increase downward
            tip = (cx + dx * rose, cy + dy * rose)
            _line(draw, (cx, cy), tip, line_w)
            _text(draw, (cx + dx * (rose + gap), cy + dy * (rose + gap)),
                  label, font, "mm")
    return picture
