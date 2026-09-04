"""Object names baked into a shared picture.

The app already answers *"what is that other fuzzy blob?"* on screen: v0.293.0
draws a pin and a name over the Target page's picture for every bundled-catalog
object that falls inside the solved field (:mod:`seestack.annotate`). But the
overlay is drawn in the browser, so the moment the beginner shares the picture
the answer is gone — and "here's the Running Man Nebula, just above Orion" is a
far better thing to post than an unlabelled smudge. This module bakes the names
into the pixels, exactly as :mod:`seestack.skymarks` bakes the scale bar and
compass and :mod:`seestack.nameplate` bakes the acquisition caption.

Two halves, split so the interesting one needs no image at all:

* :func:`place_labels` is **pure geometry** — it turns the field objects (whose
  pixel coordinates live on the run's own FITS grid) into label anchors
  expressed as *fractions* of the picture, optionally re-based onto the
  rectangle a cropped preview actually shows and carried through any North-up
  turn the shared picture takes. Fractions rather than pixels
  because the shared JPEG is re-rendered at share resolution, so its pixel grid
  is not the FITS one; the same reasoning makes ``SkyMarks.bar_px`` a scaled
  fraction.
* :func:`draw_object_labels` does the pixel work: it decides how many labels
  this particular picture can carry, finds each a spot that nothing else wants,
  and drops the ones a crowded field has no room for.

The deconfliction is deliberately *at draw time*, not in the pure half: how many
chips fit and whether two of them collide depends on the rendered size, and the
same field has to stay readable whether it is baked onto a 900 px share JPEG or
a 2048 px one.

Pure and offline like its siblings: Pillow's built-in scalable font, no bundled
asset, no network, no ``webapp`` imports. Nothing here touches the stored
preview, the FITS, or the linear science data — it draws on a copy at
display/share time only.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# The mark colour and halo are shared with the sky marks on purpose: a picture
# saved with both carries one visual set, and the in-app overlay uses the same
# pale blue-white. Public constants, so this is one definition rather than a
# second copy of the palette.
from seestack.skymarks import HALO_RGB, MARK_RGB

#: Marker dot + chip metrics, as a fraction of the picture's short edge, so a
#: labelled 900 px share JPEG and a 2048 px one read the same. The label size
#: matches :mod:`seestack.skymarks`' own so the two overlays look like one set.
_LABEL_FRACTION = 0.026
_MIN_LABEL_PX = 11
_DOT_FRACTION = 0.005
_MIN_DOT_PX = 3
_MARGIN_FRACTION = 0.02
_MIN_MARGIN_PX = 8

#: One more label per this many pixels of the picture's *geometric-mean edge*
#: (``√(w·h)``). Deliberately sub-linear in area rather than the on-screen
#: overlay's own "one per 22,000 CSS px² of box": that rule is written for a
#: card that varies from 180 px to full screen, while every share JPEG is
#: already large enough to saturate it, so measuring the edge is what actually
#: separates a small export from a big one. Both clamp to the same band below,
#: so a shared picture carries about as many names as the card it came from.
_PX_PER_LABEL_EDGE = 26.0
_MIN_LABELS = 3
_MAX_LABELS = 10


@dataclass(frozen=True)
class ObjectLabel:
    """One name to draw, anchored in *fractions* of the picture it goes on.

    ``x``/``y`` are 0 at the left/top edge and 1 at the right/bottom, so the
    anchor survives whatever resolution the picture is finally rendered at.
    ``notability`` is the object's normalised distance from the picture's centre
    (0 dead centre, ~1.41 in a corner) — the same quantity the on-screen
    read-out sorts on, so "which objects matter most here?" is answered the same
    way on the card and on the shared file.
    """

    text: str
    x: float
    y: float
    notability: float


@dataclass(frozen=True)
class ObjectLabels:
    """The names to bake onto one picture, most notable first.

    Falsey when there is nothing to draw, so a caller can gate on the labels
    themselves — a run with no WCS, no catalog object in frame, or a geometry
    that can't be reconciled all arrive here as an empty set and draw nothing,
    exactly as an empty :class:`~seestack.skymarks.SkyMarks` does.
    """

    labels: tuple[ObjectLabel, ...] = field(default_factory=tuple)

    def __bool__(self) -> bool:
        return bool(self.labels)


def _load_font(size: int):
    """Pillow's built-in scalable font at ``size`` px — no bundled asset.

    Mirrors :func:`seestack.skymarks._load_font` (same Pillow pin, same graceful
    fall-back) rather than reaching across for another module's private helper,
    which is the convention its siblings already follow."""
    from PIL import ImageFont

    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # pragma: no cover — Pillow <10.1 (below our pin)
        return ImageFont.load_default()


def label_text(catalog_id: str, name: str) -> str:
    """The chip's wording: the friendly name when the catalog has one, else the
    designation — the Python mirror of the overlay's ``objectLabel``, so the
    baked label and the on-screen chip say the same thing."""
    friendly = (name or "").strip()
    return friendly if friendly else (catalog_id or "").strip()


def place_labels(
    objects,  # noqa: ANN001 — iterable of annotate.FieldObject (or anything with the same fields)
    width_px: int,
    height_px: int,
    *,
    crop_box: tuple[int, int, int, int] | None = None,
    north_up_turns=(),  # noqa: ANN001 — sequence of float
) -> ObjectLabels:
    """Turn field objects into label anchors on the picture that will be shown.

    ``width_px``/``height_px`` are the **FITS grid** the objects' ``x_px``/
    ``y_px`` were measured on. ``crop_box`` is the pixel rectangle of that grid
    the picture actually shows (``x0, y0, x1, y1``) when the stored preview is a
    trimmed one — an auto-edit border trim on a mosaic — so an object is placed
    relative to what is on screen rather than to the canvas behind it, and one
    that fell outside the trim is dropped rather than drawn off the edge.

    ``north_up_turns`` are the North-up rotations the picture took *after* that
    crop, in the order they were applied — so a turned picture can carry its
    names instead of being shared bare. The turn moves every pixel and grows the
    canvas, and the anchors follow it through the renderer's own geometry
    (:func:`seestack.render.orient.follow_north_up_turns`) rather than being
    abandoned. The rotation is done on the crop rectangle's own grid; the
    rendered picture is a uniform scaling of it, and a rotate is scale-invariant
    up to the bounding box's sub-pixel rounding, which is far inside a marker
    dot.

    Objects are returned most-notable-first (closest to the picture's centre),
    which is the order :func:`draw_object_labels` hands out its limited room in.
    Notability is measured on the **un-turned** picture, so a turn re-places the
    names without reshuffling which of them a crowded field keeps.
    An unusable frame, an empty catalog match, or a degenerate crop all return
    an empty (falsey) :class:`ObjectLabels`.
    """
    if width_px <= 0 or height_px <= 0:
        return ObjectLabels()
    x0, y0, x1, y1 = crop_box if crop_box is not None else (0, 0, width_px, height_px)
    vis_w = float(x1 - x0)
    vis_h = float(y1 - y0)
    if vis_w <= 0 or vis_h <= 0:
        return ObjectLabels()

    kept: list[tuple[str, float, tuple[float, float]]] = []
    for o in objects:
        text = label_text(getattr(o, "catalog_id", ""), getattr(o, "name", ""))
        if not text:
            continue
        fx = (float(o.x_px) - x0) / vis_w
        fy = (float(o.y_px) - y0) / vis_h
        # Outside what the picture shows — either off the canvas or trimmed away.
        # Checked before any turn: a rotate only ever moves a point that is inside
        # the frame to somewhere else inside the (grown) frame.
        if not (0.0 <= fx <= 1.0 and 0.0 <= fy <= 1.0):
            continue
        nx = (fx - 0.5) * 2.0
        ny = (fy - 0.5) * 2.0
        kept.append((text, float((nx * nx + ny * ny) ** 0.5),
                     (fx * vis_w, fy * vis_h)))

    from seestack.render.orient import follow_north_up_turns

    turned = follow_north_up_turns(
        [pt for _t, _n, pt in kept], int(vis_w), int(vis_h), north_up_turns)
    if turned is None:
        return ObjectLabels()
    points, out_w, out_h = turned
    if out_w <= 0 or out_h <= 0:
        return ObjectLabels()

    placed = [
        ObjectLabel(text=text, x=px / out_w, y=py / out_h, notability=notability)
        for (text, notability, _src), (px, py) in zip(kept, points, strict=True)
    ]
    placed.sort(key=lambda lab: (lab.notability, lab.text))
    return ObjectLabels(labels=tuple(placed))


def label_budget(width: int, height: int) -> int:
    """How many names a ``width`` × ``height`` picture can carry and stay
    readable. Scale-free (a share of the area), clamped to a sensible band so a
    tiny thumbnail still gets a few and a huge mosaic doesn't turn into a
    catalogue page."""
    if width <= 0 or height <= 0:
        return 0
    n = int((width * height) ** 0.5 / _PX_PER_LABEL_EDGE)
    return max(_MIN_LABELS, min(_MAX_LABELS, n))


def _fits(rect, others, width, height, margin) -> bool:  # noqa: ANN001
    """Is ``rect`` inside the picture and clear of everything already placed?"""
    rx0, ry0, rx1, ry1 = rect
    if rx0 < margin or ry0 < margin or rx1 > width - margin or ry1 > height - margin:
        return False
    for ox0, oy0, ox1, oy1 in others:
        if rx0 < ox1 and ox0 < rx1 and ry0 < oy1 and oy0 < ry1:
            return False
    return True


def draw_object_labels(img, labels: ObjectLabels, *, avoid=()):  # noqa: ANN001, ANN201
    """Return a new RGB ``PIL.Image``: ``img`` with a dot and a name on each
    object that fits.

    ``avoid`` is a sequence of ``(x0, y0, x1, y1)`` pixel rectangles no chip may
    land in — the caller passes the boxes any *other* overlay on the same picture
    will occupy (:func:`seestack.skymarks.mark_zones`). A name half-hidden under
    the compass rose is a name the beginner can't read, and the marks are drawn
    after these, so without it the collision is silent.

    The canvas size is unchanged — these are marks *on* the picture, like the
    sky marks, not a frame around it. When there is nothing to draw the image
    comes back unchanged (converted to RGB if it wasn't), so a run with no
    catalog object in frame is byte-for-byte the plain share.

    Room is handed out most-notable-first, and a chip is tried below its dot,
    then above, then to either side; a label with nowhere clear to go is simply
    not drawn. **The dot never moves** — nudging it would make the label point
    at empty sky, which is worse than no label at all.
    """
    from PIL import ImageDraw

    picture = img.convert("RGB") if img.mode != "RGB" else img
    if not labels:
        return picture

    picture = picture.copy()
    width, height = picture.size
    short = max(1, min(width, height))
    font = _load_font(max(_MIN_LABEL_PX, round(short * _LABEL_FRACTION)))
    dot_r = max(_MIN_DOT_PX, round(short * _DOT_FRACTION))
    margin = max(_MIN_MARGIN_PX, round(short * _MARGIN_FRACTION))
    gap = max(2, dot_r)
    draw = ImageDraw.Draw(picture)

    budget = label_budget(width, height)
    # Seeded with whatever else is going on this picture, so the placement below
    # treats another overlay's furniture exactly as it treats an earlier chip.
    taken: list[tuple[float, float, float, float]] = [
        (float(a), float(b), float(c), float(d)) for a, b, c, d in avoid]
    drawn = 0
    for lab in labels.labels:
        if drawn >= budget:
            break
        cx = lab.x * width
        cy = lab.y * height
        if not (margin <= cx <= width - margin and margin <= cy <= height - margin):
            # The dot itself would sit in (or past) the picture's own margin;
            # a name pinned there reads as pointing off the edge.
            continue
        box = draw.textbbox((0, 0), lab.text, font=font, stroke_width=2)
        tw = float(box[2] - box[0])
        th = float(box[3] - box[1])
        step = dot_r + gap
        spot = None
        for dx, dy, anchor in (
            (0.0, step + th / 2.0, "mm"),      # below the dot
            (0.0, -(step + th / 2.0), "mm"),   # above it
            (step + tw / 2.0, 0.0, "mm"),      # right
            (-(step + tw / 2.0), 0.0, "mm"),   # left
        ):
            rect = (cx + dx - tw / 2.0, cy + dy - th / 2.0,
                    cx + dx + tw / 2.0, cy + dy + th / 2.0)
            if _fits(rect, taken, width, height, margin):
                spot = (cx + dx, cy + dy, anchor, rect)
                break
        if spot is None:
            continue
        tx, ty, anchor, rect = spot
        # The dot, over its own dark halo, so it survives a bright nebula core
        # as well as empty sky — the same treatment every sky mark gets.
        draw.ellipse([cx - dot_r - 1, cy - dot_r - 1, cx + dot_r + 1, cy + dot_r + 1],
                     outline=HALO_RGB, width=2)
        draw.ellipse([cx - dot_r, cy - dot_r, cx + dot_r, cy + dot_r],
                     outline=MARK_RGB, width=max(1, dot_r // 2))
        draw.text((tx, ty), lab.text, font=font, fill=MARK_RGB, anchor=anchor,
                  stroke_width=2, stroke_fill=HALO_RGB)
        # Reserve the chip *and* the dot, so the next label can't be laid over
        # either of them.
        taken.append(rect)
        taken.append((cx - dot_r, cy - dot_r, cx + dot_r, cy + dot_r))
        drawn += 1
    return picture
