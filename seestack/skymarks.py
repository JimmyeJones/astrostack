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

An optional third mark, off unless asked for, is the **"Moon for scale" disc**:
a faint circle drawn at the true angular size of the full Moon, tucked under the
scale bar. It is the visual twin of the bar's own
:attr:`~seestack.scalebar.ScaleBar.moon_comparison` sentence — "about 2.5 full
Moons wide" is a fact a beginner has to do arithmetic on, while a circle beside
the nebula is a fact they simply *see*.

Two deliberate choices worth knowing:

* **The marks live along the *top* edge** (bar top-left, disc under it, rose
  top-right). The
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

#: The "Moon for scale" disc is drawn only while its diameter stays within this
#: share of the picture's **short** side. Past it the Moon is no longer a *mark*
#: on the picture — it is most of the picture — and a circle that big reads as
#: damage rather than as a size cue. A field that tight is exactly where
#: :attr:`seestack.scalebar.ScaleBar.moon_comparison` already says the honest
#: thing in words ("about 80% the width of the full Moon"), so the sentence
#: carries it and the disc stands aside. Mirrored in ``frontend/src/moonDisc.ts``
#: (pinned by ``tests/test_moon_disc_mirror.py``) so screen and file agree on
#: when it appears.
MOON_DISC_MAX_SHORT_FRACTION = 0.5

#: The disc's label. Kept next to the constant above because the two together are
#: the whole of what a reader sees, and because it must stay drawable with the
#: bundled face (plain ASCII — see :func:`_text`).
MOON_DISC_LABEL = "Full Moon"


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

    ``moon_px`` is the full Moon's **diameter** in those same pixels — the
    "Moon for scale" disc, off unless asked for. It comes off the very same
    :class:`~seestack.scalebar.ScaleBar` as ``bar_px`` (``moon_fraction`` is
    derived from ``fraction``), so the disc and the bar cannot disagree about
    how much sky one pixel is.

    Any part may be absent: ``bar_px``/``bar_label`` for a run with no usable
    pixel scale, ``directions`` for one with no usable orientation, ``moon_px``
    whenever the disc wasn't asked for.
    """

    bar_px: float | None = None
    bar_label: str = ""
    directions: SkyDirections | None = None
    moon_px: float | None = None

    @property
    def has_scale(self) -> bool:
        return bool(self.bar_px and self.bar_px > 0 and self.bar_label)

    @property
    def has_compass(self) -> bool:
        return self.directions is not None

    @property
    def has_moon(self) -> bool:
        """Whether a Moon disc was asked for *and* is a sensible size to draw.

        The size test is here rather than at the drawing site so ``mark_zones``
        and :func:`draw_sky_marks` can never disagree about whether the disc
        exists — one of them keeping a zone clear for a circle the other decided
        not to draw is exactly the drift the shared-derivation rule exists to
        prevent. It needs the picture's size, so the property answers the half it
        can (asked for at all) and :func:`_moon_diameter` answers the rest."""
        return bool(self.moon_px and self.moon_px > 0)

    def __bool__(self) -> bool:
        """False when there is nothing to draw, so a caller can gate on the
        marks themselves rather than testing both halves."""
        return self.has_scale or self.has_compass or self.has_moon


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
    """Mark text with the same dark halo, via Pillow's stroke.

    Sanitised on the way in: ``ScaleBar.ascii_label`` already keeps the primes
    off this face by hand, but the compass letters and any future mark text go
    through the shared net so a missing glyph can't bake a box into a share."""
    from seestack.render.glyphs import safe_for_default_font

    draw.text(xy, safe_for_default_font(text), font=font, fill=MARK_RGB,
              anchor=anchor, stroke_width=2, stroke_fill=HALO_RGB)


def _moon_disc_box(width: int, height: int, marks: SkyMarks):  # noqa: ANN202
    """Where the "Moon for scale" disc goes on a ``width`` × ``height`` picture.

    ``(x0, y0, x1, y1)`` for the circle itself, or ``None`` when there is no
    disc to draw — not asked for, or too big to be a mark
    (:data:`MOON_DISC_MAX_SHORT_FRACTION`), or a picture with no room for it.

    It sits **directly under the scale bar**, top-left, because the two answer
    the same question ("how big is this piece of sky?") and a reader should meet
    them together — put them in opposite corners and they read as two unrelated
    decorations. That also keeps it clear of the rose (top-right) and of the
    bottom edge, which is the caption zone the module docstring describes.

    One function so :func:`mark_zones` and :func:`draw_sky_marks` share the
    arithmetic instead of mirroring it."""
    if not marks.has_moon or width <= 0 or height <= 0:
        return None
    short = max(1, min(width, height))
    diameter = float(marks.moon_px or 0.0)
    if not (diameter > 0) or diameter > short * MOON_DISC_MAX_SHORT_FRACTION:
        return None
    margin = max(_MIN_MARGIN_PX, round(short * _MARGIN_FRACTION))
    line_w = max(_MIN_LINE_PX, round(short * _LINE_FRACTION))
    label_px = max(_MIN_LABEL_PX, round(short * _LABEL_FRACTION))
    gap = max(6, round(short * 0.018))
    # Clear the bar's own zone when there is a bar; otherwise start at the margin.
    top = float(margin)
    if marks.has_scale:
        serif = max(line_w * 2, round(short * 0.010))
        top = margin + serif + line_w + label_px * 1.4 + gap
    x0, y0 = float(margin), top
    x1, y1 = x0 + diameter, y0 + diameter
    # The label is set below the circle, so the *label* is what has to fit.
    if x1 > width or y1 + label_px * 1.4 > height:
        return None
    return (x0, y0, x1, y1)


def mark_zones(width: int, height: int, marks: SkyMarks):  # noqa: ANN201
    """The pixel boxes :func:`draw_sky_marks` will ink on a ``width`` × ``height``
    picture, as ``(x0, y0, x1, y1)`` rectangles.

    So another overlay drawn on the same picture can keep out of them. The marks
    go on **last** (a caption or matte is added after, never over them), which
    means a collision doesn't mislead — it just buries whatever was underneath —
    but a name half-hidden by the compass rose is still a name the beginner
    can't read, and this is the cheap way to avoid it.

    Derived from the same constants the drawing uses rather than re-measured, so
    the two can't drift; a mark that isn't drawn contributes no box, and a
    :class:`SkyMarks` with nothing to draw returns ``()``.
    """
    if not marks or width <= 0 or height <= 0:
        return ()
    short = max(1, min(width, height))
    margin = max(_MIN_MARGIN_PX, round(short * _MARGIN_FRACTION))
    line_w = max(_MIN_LINE_PX, round(short * _LINE_FRACTION))
    label_px = max(_MIN_LABEL_PX, round(short * _LABEL_FRACTION))
    zones: list[tuple[float, float, float, float]] = []
    if marks.has_scale:
        bar = min(float(marks.bar_px), max(1.0, width - 2.0 * margin))
        serif = max(line_w * 2, round(short * 0.010))
        # The bar sits at (margin, margin); its serifs stand off it vertically
        # and its label is set below them, ~1.4 line-heights tall with the halo.
        zones.append((margin - serif, margin - serif - line_w,
                      margin + bar + serif,
                      margin + serif + line_w + label_px * 1.4))
    if marks.directions is not None:
        rose = max(_MIN_ROSE_PX, round(short * _ROSE_FRACTION))
        gap = max(6, round(short * 0.018))
        pad = rose + gap + margin
        cx, cy = float(width - pad), float(pad)
        # The arms point wherever the sky says, so the rose's box is the full
        # circle its longest reach (arm + gap + letter) sweeps out.
        reach = rose + gap + label_px
        zones.append((cx - reach, cy - reach, cx + reach, cy + reach))
    disc = _moon_disc_box(width, height, marks)
    if disc is not None:
        # The circle, its stroke (which the rasteriser rounds outward off a
        # fractional box), and the label set beneath it. Every allowance here is
        # deliberately generous — the box exists to be *avoided*, so
        # over-claiming costs a catalog name a few pixels of room while
        # under-claiming buries it, and the exact extent of a stroked line
        # depends on face metrics this module stays free of PIL to avoid asking
        # for. The half-width allowance matters because the label is centred on
        # the circle and can be wider than a small disc.
        x0, y0, x1, y1 = disc
        half = max((x1 - x0) / 2.0, len(MOON_DISC_LABEL) * label_px * 0.6 / 2.0)
        mid = (x0 + x1) / 2.0
        zones.append((mid - half - line_w, y0 - line_w, mid + half + line_w,
                      y1 + line_w + label_px * 2.0))
    return tuple(zones)


def draw_sky_marks(img, marks: SkyMarks):  # noqa: ANN001, ANN201
    """Return a new RGB ``PIL.Image``: ``img`` with the scale bar drawn at the
    top-left, the optional Moon-for-scale disc beneath it, and the North/East
    rose at the top-right.

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

    disc = _moon_disc_box(width, height, marks)
    if disc is not None:
        # "Moon for scale": a faint circle exactly as wide as the full Moon would
        # look in this field. An outline, never a fill — the picture underneath
        # is the whole point, and a filled disc would hide the very thing being
        # measured. Haloed like every other mark so it survives a bright core.
        x0, y0, x1, y1 = disc
        draw.ellipse([x0, y0, x1, y1], outline=HALO_RGB, width=line_w + 2)
        draw.ellipse([x0, y0, x1, y1], outline=MARK_RGB, width=line_w)
        _text(draw, ((x0 + x1) / 2.0, y1 + line_w), MOON_DISC_LABEL, font, "ma")

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
