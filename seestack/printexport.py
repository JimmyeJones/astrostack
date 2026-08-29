"""Print it — turn a finished picture into a file a photo lab will print well.

A beginner who finally gets an image they love wants it **on the wall**. Every
export the app offers today (PNG, full-res PNG, JPEG, TIFF) is native-resolution
with no print sizing and no DPI metadata, so it lands in a photo-print service at
whatever size the pixel count implies — often soft, often tiny, always without
warning. Nothing bridges "great picture on screen" → "nice print in my hands".

This module is that bridge, and it is deliberately a *decision*, not a knob: it
looks at the picture's own resolution and says which standard sizes it can print
**sharply**, with the largest one recommended. The user picks a size by its name
("A4"), never a DPI.

The maths, in one paragraph. Printed sharpness is pixels per printed inch, so a
paper size is only honest if the picture has enough pixels to cover it without
being **upscaled** — enlarging a 1000 px picture to 3000 px doesn't add detail,
it just makes the softness bigger. So for each paper size (oriented to match the
picture, portrait or landscape) the achievable DPI is
``min(width_px / paper_width_in, height_px / paper_height_in)``: the point at
which the fitted picture exactly fills the shorter dimension. A size qualifies
when that clears ``min_dpi``; the render then uses that DPI, capped at
:data:`MAX_DPI` because no consumer lab resolves more.

Pure and offline: sizing is plain arithmetic on integers, and the render needs
only Pillow. No ``webapp`` imports, no network, nothing written here — the caller
owns the file.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

# Below this, a print looks visibly soft at arm's length. 300 is the darkroom
# ideal and 150 is the floor most consumer labs quote; we take the floor as the
# *qualifying* bar (so a modest stack still gets an honest small print) and let
# the render use every pixel the picture actually has, up to MAX_DPI.
DEFAULT_MIN_DPI = 150

# Rendering past this wastes bytes: no consumer photo lab resolves beyond it, and
# a 600 DPI A3 canvas is ~50 MP of mostly-invisible detail.
MAX_DPI = 300


@dataclass(frozen=True)
class PaperSize:
    """One standard print size, in inches, longest edge second."""

    name: str
    short_in: float
    long_in: float


# The sizes a beginner actually orders, smallest first. Kept deliberately short —
# this is a menu, not a catalogue — and spanning "everyone can print this" to
# "you have a wall-worthy stack". Inch sizes are the common photo-lab set; A4/A3
# are the ISO paper sizes converted from millimetres (210×297, 297×420).
PAPER_SIZES: tuple[PaperSize, ...] = (
    PaperSize("6×4 in", 4.0, 6.0),
    PaperSize("7×5 in", 5.0, 7.0),
    PaperSize("10×8 in", 8.0, 10.0),
    PaperSize("A4", 8.27, 11.69),
    PaperSize("A3", 11.69, 16.54),
)


@dataclass(frozen=True)
class PrintOption:
    """One print size this picture can fill sharply, ready to render or offer."""

    name: str            # the paper size, e.g. "A4"
    dpi: int             # dots per inch this picture will actually be printed at
    width_px: int        # canvas the render produces…
    height_px: int       # …oriented to match the picture
    width_in: float      # printed size, oriented the same way
    height_in: float

    @property
    def label(self) -> str:
        """"A4 · 240 DPI" — the size first, because that is what a user picks."""
        return f"{self.name} · {self.dpi} DPI"


def print_options(width_px: int, height_px: int, *,
                  min_dpi: int = DEFAULT_MIN_DPI) -> list[PrintOption]:
    """Every standard size this picture can print sharply, **largest first**.

    A size is included only when the picture can cover it without being upscaled
    past ``min_dpi`` — so the list is honest by construction and the first entry
    is the sane default ("the biggest print you can make from this"). Returns an
    empty list for a picture too small for even the smallest size (the caller
    then offers nothing rather than a print that would look bad), and for a
    degenerate/absent size.
    """
    if width_px < 1 or height_px < 1 or min_dpi < 1:
        return []
    options: list[PrintOption] = []
    for paper in PAPER_SIZES:
        # Orient the paper the same way as the picture, so the letterbox bars are
        # as small as the aspect mismatch allows rather than as large as turning
        # a landscape stack onto portrait paper would make them.
        if width_px >= height_px:
            paper_w, paper_h = paper.long_in, paper.short_in
        else:
            paper_w, paper_h = paper.short_in, paper.long_in
        achievable = min(width_px / paper_w, height_px / paper_h)
        if achievable < min_dpi:
            continue
        dpi = int(min(MAX_DPI, achievable))
        options.append(PrintOption(
            name=paper.name, dpi=dpi,
            width_px=max(1, round(paper_w * dpi)),
            height_px=max(1, round(paper_h * dpi)),
            width_in=paper_w, height_in=paper_h,
        ))
    options.reverse()   # largest paper first — the recommended one leads
    return options


def print_advice(options: list[PrintOption]) -> str:
    """One plain-language line about what this picture can print at, or ``""``.

    Says the *recommendation*, not the arithmetic: a beginner should never have
    to reason about DPI to order a print.

    The too-small line deliberately does **not** promise that more subs fix it —
    they don't. What a print needs is *pixels*, and another night of the same
    pointing adds none (it makes the picture cleaner, not bigger). The lever is
    named by :func:`bigger_print`, which the caller shows alongside this.
    """
    if not options:
        return ("This picture doesn't have enough detail for a sharp print yet — "
                "it needs more pixels, not more exposure.")
    best = options[0]
    return (f"Best print size for this picture: up to {best.name} "
            f"at {best.dpi} DPI.")


# What super-resolution realistically buys. The Stack form offers a drizzle scale
# of ×1.0–×4.0 with ×2.0 as "full super-res", so a picture within 2× of the next
# paper size can get there by re-stacking with Drizzle on; past that the honest
# lever is a mosaic.
DRIZZLE_MAX_USEFUL_SCALE = 2.0

# Past this, the next print size is too far away to be a motivating nudge — a
# beginner told they need 5× more detail learns nothing they can act on — so we
# say nothing at all rather than set an unreachable goal.
BIGGER_PRINT_MAX_SCALE = 3.0


@dataclass(frozen=True)
class BiggerPrint:
    """The next print size up from what a picture can already fill, and what it
    would take to get there."""

    name: str            # the next paper size up, e.g. "A3"
    scale: float         # times more pixels *per side* than the picture has now
    width_px: int        # the picture would need to be at least this wide…
    height_px: int       # …and this tall, oriented to match it
    text: str            # the finished plain-language sentence


def bigger_print(width_px: int, height_px: int, *,
                 min_dpi: int = DEFAULT_MIN_DPI) -> BiggerPrint | None:
    """What it would take to print this picture one size *bigger*, or ``None``.

    :func:`print_options` answers "what can I print today?" and hides itself when
    the answer is *nothing*, which drops the more motivating fact on the floor:
    how close the picture is to the next size up, and — the part that has to be
    right — **which lever actually gets it there**.

    More integration does not add pixels. Another night of the same pointing
    makes the picture *cleaner*, not *bigger*, so it can never unlock a larger
    print; what adds resolution is drizzle (super-resolution) or shooting the
    object as a mosaic. The sentence says exactly that, and names drizzle only
    while the gap is within :data:`DRIZZLE_MAX_USEFUL_SCALE`.

    Returns ``None`` when the picture already fills the largest size offered
    (nothing left to reach for), when the gap is beyond
    :data:`BIGGER_PRINT_MAX_SCALE`, and for degenerate sizes. The pixel counts
    are the *minimum* that would qualify, and ``scale`` is rounded **up** to a
    tenth so the nudge never promises a size the picture would just miss.
    """
    if width_px < 1 or height_px < 1 or min_dpi < 1:
        return None
    printable = {o.name for o in print_options(width_px, height_px, min_dpi=min_dpi)}
    # The largest paper the picture already fills. Papers differ slightly in
    # aspect (10×8 is 1.25, A4 is 1.41), so a very wide picture can qualify for
    # A4 while missing the *smaller* 10×8 — skipping anything no larger than
    # what it already prints keeps the nudge pointing upward.
    best_long = max((p.long_in for p in PAPER_SIZES if p.name in printable),
                    default=0.0)
    for paper in PAPER_SIZES:            # smallest first
        if paper.name in printable or paper.long_in <= best_long:
            continue
        if width_px >= height_px:
            paper_w, paper_h = paper.long_in, paper.short_in
        else:
            paper_w, paper_h = paper.short_in, paper.long_in
        need_w, need_h = paper_w * min_dpi, paper_h * min_dpi
        # Both axes have to clear the floor, so the binding one sets the gap.
        scale = math.ceil(max(need_w / width_px, need_h / height_px) * 10) / 10
        if scale > BIGGER_PRINT_MAX_SCALE:
            return None
        return BiggerPrint(
            name=paper.name, scale=scale,
            width_px=max(1, math.ceil(need_w)), height_px=max(1, math.ceil(need_h)),
            text=_bigger_print_text(paper.name, scale, bool(printable)),
        )
    return None


def _bigger_print_text(name: str, scale: float, prints_already: bool) -> str:
    """The nudge, in the app's plain voice — the gap first, then the one lever
    that closes it, then the thing it is *not* (more subs)."""
    gap = f"{scale:g}×"        # "1.5×"
    lead = (f"About {gap} more detail would print this at {name}."
            if prints_already else
            f"About {gap} more detail would make it printable at {name}, the "
            "smallest size that comes out sharp.")
    if scale <= DRIZZLE_MAX_USEFUL_SCALE:
        lever = ("More subs won't do it — they make the picture cleaner, not "
                 "bigger. What adds detail is re-stacking with Drizzle "
                 "(super-resolution) switched on, which pays off when you have "
                 "plenty of subs.")
    else:
        lever = ("That's more than super-resolution alone adds, so this one "
                 "wants a mosaic — the same object shot as several overlapping "
                 "panels. More subs make the picture cleaner, not bigger.")
    return f"{lead} {lever}"


def render_print(rgb: np.ndarray, option: PrintOption):
    """Fit an already display-stretched image (0..1, NaN = uncovered) onto
    ``option``'s pixel canvas and return the Pillow image, ready to save with
    ``img.save(path, dpi=(option.dpi, option.dpi))``.

    The picture is scaled **whole** and centred, never stretched: a lab that
    prints a squashed M 31 has printed the wrong picture. The letterbox ground is
    black, which is both the app's NaN = uncovered convention everywhere else and
    the right ground for a night-sky print. LANCZOS resampling, matching the share
    JPEG's reasoning — BOX (used for thumbnails) softens star cores, and softness
    is precisely what a print exposes.
    """
    from PIL import Image

    arr = np.nan_to_num(np.asarray(rgb, dtype=np.float32), nan=0.0)
    u8 = (np.clip(arr, 0.0, 1.0) * 255.0).astype(np.uint8)
    if u8.ndim == 2:
        u8 = np.stack([u8, u8, u8], axis=-1)
    img = Image.fromarray(u8, mode="RGB")

    tw, th = option.width_px, option.height_px
    w, h = img.size
    scale = min(tw / w, th / h)
    nw, nh = max(1, round(w * scale)), max(1, round(h * scale))
    fitted = img.resize((nw, nh), Image.LANCZOS) if (nw, nh) != (w, h) else img
    if (nw, nh) == (tw, th):
        return fitted
    canvas = Image.new("RGB", (tw, th), (0, 0, 0))
    canvas.paste(fitted, ((tw - nw) // 2, (th - nh) // 2))
    return canvas
