"""\"My deep-sky wall\" — every finished picture as one shareable montage.

A Seestar owner accumulates dozens of finished targets over a season, but the
app can only ever show them **one at a time**: the gallery is a list, the
deepening reel is one target across nights, the recap poster is *numbers* over
one hero image. There is no single picture that says *"look at everything I've
captured"* — which is exactly the thing a beginner wants to post to friends at
the end of a good run of clear nights.

This module builds it: the library's best pictures, letterboxed onto a tidy
grid, each with a small caption naming the target and its integration, under an
optional title strip.

Pure and offline, like :mod:`seestack.recap`: no network, no bundled asset
(Pillow's built-in scalable font), no ``webapp`` imports, and nothing written
anywhere — the webapp layer loads the previews it already keeps, hands them
here, and serves the result as a display-time render. Every tile is optional:
a preview that can't be read is simply left out by the caller, and fewer than
:data:`MIN_TILES` pictures yields ``None`` rather than a "wall" of one.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

# One picture is not a wall — and two is the smallest set where the montage says
# something the single picture didn't. Below this the caller renders nothing.
MIN_TILES = 2

# A sane default cap. Past roughly nine tiles each picture is too small to enjoy
# at social-media sizes, and the point of the wall is the *pictures*, not the
# count. Callers may ask for fewer; more than this is refused rather than
# silently producing a contact sheet of thumbnails.
DEFAULT_MAX_TILES = 9
MAX_TILES = 16

# Montage width in pixels. 1600 keeps a 3-wide grid's tiles at ~530 px — big
# enough to see the object, small enough to post without re-compression.
DEFAULT_WIDTH = 1600

_BG = (10, 12, 20)          # the app's deep-space background
_TITLE_FG = (236, 238, 248)
_SUBTITLE_FG = (158, 164, 184)


@dataclass
class MontageTile:
    """One picture on the wall: a loaded ``PIL`` image plus its caption."""

    image: Any          # PIL.Image.Image — typed loosely to keep Pillow lazy
    caption: str = ""


def montage_grid(n: int, columns: int | None = None) -> tuple[int, int]:
    """``(cols, rows)`` for ``n`` tiles — as close to square as fills up.

    Up to three pictures read best as a single row (three squares stacked into a
    2×2 with a hole in it looks like something failed). Above that, the grid is
    ``ceil(sqrt(n))`` wide, which gives 4→2×2, 6→3×2, 9→3×3 and never leaves
    more than one short row. ``columns`` overrides the choice, clamped to
    ``1..n`` so a caller can't ask for an empty or impossible grid.
    """
    n = max(0, int(n))
    if n <= 0:
        return (0, 0)
    if columns is not None:
        cols = max(1, min(int(columns), n))
    elif n <= 3:
        cols = n
    else:
        cols = math.ceil(math.sqrt(n))
    return cols, math.ceil(n / cols)


def montage_caption(name: str | None, exposure_s: float | None) -> str:
    """``"M 42 · 3h 12m"`` — the tile's own label, or just the name when the
    integration is unknown, or ``""`` when even the name is missing (which the
    label drawer treats as "no label", not as an empty box)."""
    from seestack.sharecard import format_duration

    clean = (name or "").strip()
    if not clean:
        return ""
    dur = format_duration(exposure_s)
    return f"{clean} · {dur}" if dur else clean


def montage_title(n_targets: int, total_integration_s: float | None) -> str:
    """The strip across the top: ``"My deep-sky wall — 14 targets, 38h of light"``.

    Falls back to the target count alone when there's no integration to report,
    so the strip is never a sentence with a hole in it.
    """
    from seestack.sharecard import format_duration

    n = max(0, int(n_targets))
    # ``·`` rather than an em dash: the strip is drawn with Pillow's built-in
    # font, which has no glyph for ``—`` and renders it as a tofu box — the same
    # reason the recap poster's rendered strings stay off it.
    head = f"My deep-sky wall · {n} target{'' if n == 1 else 's'}"
    dur = format_duration(total_integration_s)
    return f"{head}, {dur} of light" if dur else head


def _median_aspect(tiles: list[MontageTile]) -> float:
    """The median width/height of the tiles, clamped to a sane range.

    The cell shape is taken from the pictures themselves rather than fixed, so a
    library of ordinary landscape single-field stacks letterboxes hardly at all,
    and one that is mostly tall mosaics doesn't sit in a sea of black bars. The
    clamp keeps one freak panorama from squeezing every other tile into a strip.
    """
    ratios = []
    for t in tiles:
        try:
            w, h = t.image.size
        except Exception:  # noqa: BLE001 — a tile that can't describe itself
            continue
        if w > 0 and h > 0:
            ratios.append(w / h)
    if not ratios:
        return 4 / 3
    ratios.sort()
    mid = ratios[len(ratios) // 2]
    return min(2.2, max(0.6, mid))


def build_montage(
    tiles: list[MontageTile],
    *,
    columns: int | None = None,
    title: str | None = None,
    width: int = DEFAULT_WIDTH,
    max_tiles: int = DEFAULT_MAX_TILES,
):
    """Compose ``tiles`` into one montage image, or ``None`` when there's no wall.

    Returns ``None`` for fewer than :data:`MIN_TILES` tiles — the caller renders
    nothing rather than offering a one-picture "wall". Tiles past ``max_tiles``
    are dropped (the caller ranks them, so the best ones are first).

    Each picture is fitted *whole* into its cell and centred on the background
    (:func:`seestack.render.deepening._fit_onto`), so a portrait single-field and
    a landscape mosaic sit side by side without either being squashed — the same
    letterboxing, and the same "black = no data" convention, the deepening reel
    already uses. Captions are burned on with the reel's own corner label, so the
    two shareables speak in one visual voice.
    """
    from PIL import Image, ImageDraw

    from seestack.render.deepening import _draw_corner_label, _fit_onto

    kept = [t for t in tiles if t is not None and t.image is not None]
    kept = kept[: max(MIN_TILES, min(int(max_tiles), MAX_TILES))]
    if len(kept) < MIN_TILES:
        return None

    cols, rows = montage_grid(len(kept), columns)
    width = max(320, int(width))
    gap = max(2, round(width * 0.006))
    pad = gap
    cell_w = max(1, (width - pad * 2 - gap * (cols - 1)) // cols)
    cell_h = max(1, round(cell_w / _median_aspect(kept)))

    title_h = 0
    if title:
        title_h = max(28, round(width * 0.055))
    height = title_h + pad * 2 + rows * cell_h + gap * (rows - 1)
    canvas = Image.new("RGB", (width, height), _BG)

    if title:
        draw = ImageDraw.Draw(canvas)
        from seestack.recap import _fit_font

        font = _fit_font(draw, title, round(title_h * 0.46), width - pad * 2)
        draw.text((pad, round(title_h * 0.28)), title, font=font, fill=_TITLE_FG)

    for i, tile in enumerate(kept):
        try:
            img = tile.image.convert("RGB")
        except Exception:  # noqa: BLE001 — one bad tile must not sink the wall
            continue
        cell = _fit_onto(img, (cell_w, cell_h))
        cell = _draw_corner_label(cell, tile.caption or "")
        row = i // cols
        col = i % cols
        # A short last row is centred rather than left-aligned: seven pictures
        # in a 3-wide grid otherwise leave a conspicuous hole in the bottom-right
        # corner, which reads as "something failed to load" on the one image the
        # user is about to post.
        in_row = min(cols, len(kept) - row * cols)
        row_w = in_row * cell_w + (in_row - 1) * gap
        x0 = pad + (width - pad * 2 - row_w) // 2
        x = x0 + col * (cell_w + gap)
        y = title_h + pad + row * (cell_h + gap)
        canvas.paste(cell, (x, y))
    return canvas
