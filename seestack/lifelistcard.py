"""\"My Messier grid\" — the whole life list as one shareable picture.

The life-list page answers *"how many of the 110 have I got?"*, but it answers
it as a **web page**: a scrolling grid of cards you can look at and nobody else
can. The single most shareable thing this app could produce for a beginner is
that same grid as one image — the classic checklist with your own pictures in
the squares you have filled and the rest still waiting — because it says both
halves of the story at once: what you have captured, and how far there is to go.

This module is the pure, offline half. It takes one :class:`GridCell` per
catalog object (a label, whether it is captured, and optionally the owner's own
picture of it) and composes the poster. Like :mod:`seestack.montage` and
:mod:`seestack.recap` it is engine-pure: no network, no bundled asset (Pillow's
built-in scalable font), no ``webapp`` imports, and nothing written anywhere —
the webapp layer loads the previews it already keeps, hands them here, and
serves the result as a display-time render.

Unlike the deep-sky wall, which shows only the pictures you *have*, the grid
draws every object on the list. A tile you haven't captured is a dim square with
its id in it, which is the point: the empty squares are what makes it a life
list rather than a gallery.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

#: How many captured objects the grid needs before it is worth sharing.
#:
#: A grid with nothing in it is a picture of the Messier catalogue, not of the
#: owner's sky — so the caller renders nothing (and the endpoint 404s) rather
#: than handing someone a wall of grey squares to post. One is enough: "here's
#: my first" is a real thing to share, and the empty squares beside it are the
#: whole story.
MIN_CAPTURED = 1

#: The widest the grid ever gets, in columns.
#:
#: 110 Messier objects land on 11 x 10, which is both the natural square-ish
#: choice and a tidy rectangle. The cap matters only for a caller that hands in
#: a larger set (the bundled catalog is ~157 objects if the popular NGC/IC are
#: included): past 11 columns each tile is too small to recognise a galaxy in at
#: the poster width below.
MAX_COLUMNS = 11

#: Poster width in pixels. At 11 columns this puts each tile at ~114 px — big
#: enough that M42 and M31 are recognisable, small enough to post without
#: re-compression, and the finished poster comes out roughly square.
DEFAULT_WIDTH = 1320

#: The largest source picture a caller need hand in per tile.
#:
#: A tile is ~114 px, so anything past a couple of hundred pixels is thrown away
#: by the cover-crop. The caller is loading up to 110 previews for one poster, on
#: a RAM-capped NAS — downscaling each on the way in keeps the whole set at tens
#: of megabytes instead of hundreds. Exported so the webapp and the tests agree
#: on one number rather than each picking their own.
TILE_SOURCE_MAX_PX = 256

_BG = (10, 12, 20)              # the app's deep-space background
_TITLE_FG = (236, 238, 248)
_SUBTITLE_FG = (158, 164, 184)
_TODO_TILE = (26, 29, 40)       # a square still to fill
_TODO_FG = (108, 114, 134)
_LIT_TILE = (17, 48, 47)        # captured, but no picture to show yet
_LIT_FG = (110, 200, 190)


@dataclass
class GridCell:
    """One object on the list: its label, whether it's captured, its picture."""

    #: The catalog id ("M31") — the stable label a beginner counts in. Popular
    #: names are far too long for a 114 px tile, so they are deliberately not
    #: drawn here.
    label: str
    captured: bool = False
    #: A PIL image of the owner's capture, when there is one. ``None`` both for
    #: an object never captured *and* for one captured but not yet stacked — the
    #: tile still lights up in the second case, it just shows no picture.
    image: Any = field(default=None)


def grid_columns(n: int) -> int:
    """How many columns ``n`` tiles read best in — square-ish, capped.

    ``ceil(sqrt(n))`` gives 110 -> 11 (a clean 11 x 10), 42 -> 7, 12 -> 4, and
    never leaves more than one short row. Clamped to :data:`MAX_COLUMNS` so a
    bigger catalog grows downward rather than shrinking every tile.
    """
    n = max(0, int(n))
    if n <= 0:
        return 0
    return max(1, min(MAX_COLUMNS, math.ceil(math.sqrt(n))))


def grid_title(captured: int, total: int) -> str:
    """The strip across the top: ``"My Messier list · 42 of 110 captured"``.

    ``·`` rather than an em dash: the strip is drawn with Pillow's built-in font,
    which has no glyph for ``—`` and renders it as a tofu box — the same reason
    the recap poster's rendered strings stay off it.
    """
    return f"My Messier list · {max(0, int(captured))} of {max(0, int(total))} captured"


def grid_subtitle(captured: int, total: int) -> str:
    """The quieter second line — what the grey squares mean, or that there are none.

    Says the thing a stranger looking at the poster would otherwise have to
    guess, and changes with how far along the owner is, because the motivating
    fact does: finishing the list deserves a different sentence from starting it.
    """
    captured = max(0, int(captured))
    total = max(0, int(total))
    left = max(0, total - captured)
    if total <= 0:
        return ""
    if left == 0:
        # A colon, not the em dash this sentence wants: the poster is drawn
        # with Pillow's bundled face, which has no ``—`` glyph and baked a
        # hollow box into the one card that says "you finished the list".
        return "The whole list: every one of them."
    if captured == 0:
        return "All still to shoot."
    return f"The dim squares are the {left} still to shoot."


def _tile_placeholder(size: int, cell: GridCell):
    """The square drawn for an object with no picture — dim for a to-shoot tile,
    faintly lit for one captured but not yet stacked, with its id in the middle."""
    from PIL import Image, ImageDraw

    from seestack.recap import _fit_font
    from seestack.render.glyphs import safe_for_default_font

    bg, fg = (_LIT_TILE, _LIT_FG) if cell.captured else (_TODO_TILE, _TODO_FG)
    img = Image.new("RGB", (size, size), bg)
    text = safe_for_default_font((cell.label or "").strip())
    if not text:
        return img
    draw = ImageDraw.Draw(img)
    font = _fit_font(draw, text, max(10, round(size * 0.26)), size * 0.8)
    box = draw.textbbox((0, 0), text, font=font)
    draw.text(
        ((size - (box[2] - box[0])) / 2 - box[0], (size - (box[3] - box[1])) / 2 - box[1]),
        text, font=font, fill=fg,
    )
    return img


def _draw_tile_label(img, text: str, size: int):
    """Burn the object's id into the bottom-left of a captured tile.

    The same look as the deepening reel's corner label — a dark backing chip
    under white text — but sized for a *tile* rather than a frame, which is why
    it isn't :func:`seestack.render.deepening._draw_corner_label`: that one is
    ``width * 0.028``, which on a 114 px square clamps to its 9 px floor and
    leaves the captured squares' ids visibly smaller than the to-shoot squares'.
    On a checklist the two must read at the same weight, or the empty half of the
    poster shouts over the half the owner is proud of.
    """
    from PIL import Image, ImageDraw

    from seestack.recap import _fit_font
    from seestack.render.glyphs import safe_for_default_font

    text = safe_for_default_font((text or "").strip())
    if not text:
        return img
    base = img.convert("RGBA")
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font = _fit_font(draw, text, max(10, round(size * 0.17)), size * 0.72)
    box = draw.textbbox((0, 0), text, font=font)
    pad = max(2, round(size * 0.035))
    margin = max(2, round(size * 0.04))
    x0, y1 = margin, size - margin
    y0 = y1 - ((box[3] - box[1]) + 2 * pad)
    draw.rectangle((x0, y0, x0 + (box[2] - box[0]) + 2 * pad, y1), fill=(0, 0, 0, 150))
    draw.text((x0 + pad - box[0], y0 + pad - box[1]), text,
              font=font, fill=(255, 255, 255, 238))
    return Image.alpha_composite(base, overlay).convert("RGB")


def _tile(size: int, cell: GridCell):
    """One finished tile: the owner's picture cover-cropped square and labelled,
    or the placeholder above when there is no picture to show.

    **Cover, not letterbox** — the opposite choice from :mod:`seestack.montage`,
    and deliberately: on the wall the picture *is* the subject and must be whole,
    while here the tile is a checkbox 114 px wide and the grid only reads as
    progress if the squares are filled. The centre crop keeps the framed object,
    which is what a plate-solved Seestar capture is centred on. A picture that
    can't be decoded falls back to the placeholder rather than sinking the
    poster.
    """
    from seestack.recap import _cover_crop

    if cell.image is None:
        return _tile_placeholder(size, cell)
    try:
        cropped = _cover_crop(cell.image.convert("RGB"), size)
    except Exception:  # noqa: BLE001 — one bad picture must not sink the grid
        return _tile_placeholder(size, cell)
    return _draw_tile_label(cropped, cell.label, size)


def build_life_list_grid(
    cells: list[GridCell],
    *,
    title: str | None = None,
    subtitle: str | None = None,
    width: int = DEFAULT_WIDTH,
    columns: int | None = None,
    min_captured: int = MIN_CAPTURED,
):
    """Compose ``cells`` into one poster, or ``None`` when there's nothing to share.

    Returns ``None`` when fewer than ``min_captured`` of the cells are captured —
    see :data:`MIN_CAPTURED`. Every cell is drawn, captured or not: the empty
    squares are the point.

    The grid is filled left-to-right in the order given, so the caller's own
    display order (the life list's Messier-numeric one) is what the poster
    shows — a beginner reads the squares as M1, M2, M3… and a re-ordering by
    "captured first" would break the counting.
    """
    from PIL import Image, ImageDraw

    kept = [c for c in cells if c is not None]
    n_captured = sum(1 for c in kept if c.captured)
    if not kept or n_captured < max(0, int(min_captured)):
        return None

    cols = max(1, min(int(columns), len(kept))) if columns else grid_columns(len(kept))
    rows = math.ceil(len(kept) / cols)
    width = max(320, int(width))
    gap = max(2, round(width * 0.004))
    pad = max(gap, round(width * 0.012))
    cell_px = max(1, (width - pad * 2 - gap * (cols - 1)) // cols)

    head_h = 0
    if title:
        head_h = max(30, round(width * 0.05))
        if subtitle:
            head_h += max(18, round(width * 0.028))
    height = head_h + pad * 2 + rows * cell_px + gap * (rows - 1)
    canvas = Image.new("RGB", (width, height), _BG)

    if title:
        from seestack.recap import _fit_font
        from seestack.render.glyphs import safe_for_default_font

        draw = ImageDraw.Draw(canvas)
        inner = width - pad * 2
        # The heading counts the owner's own list; the subtitle used to write
        # an em dash, which this face has no glyph for and drew as a hollow
        # box (fixed in ``grid_subtitle``, netted here).
        title = safe_for_default_font(title)
        subtitle = safe_for_default_font(subtitle)
        font = _fit_font(draw, title, round(width * 0.032), inner)
        draw.text((pad, pad), title, font=font, fill=_TITLE_FG)
        if subtitle:
            sub_font = _fit_font(draw, subtitle, round(width * 0.019), inner)
            draw.text((pad, pad + round(width * 0.038)), subtitle,
                      font=sub_font, fill=_SUBTITLE_FG)

    for i, cell in enumerate(kept):
        row, col = divmod(i, cols)
        tile = _tile(cell_px, cell)
        x = pad + col * (cell_px + gap)
        y = head_h + pad + row * (cell_px + gap)
        canvas.paste(tile, (x, y))
    return canvas
