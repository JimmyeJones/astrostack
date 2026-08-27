"""A framed, print-and-share-ready keepsake of a finished picture.

Every "proper" astrophoto a beginner admires online is *framed and titled*: the
image sits on a dark matte with the object's name under it and a line of
acquisition data — how long it took, how many subs, which night. What our app
hands them is a bare rectangle. The caption they type into Instagram doesn't
travel with the file, so a month later the picture on their phone is an
unlabelled smudge and the six hours behind it are gone.

This module turns a finished picture into that keepsake: the same pixels, matted
on a near-black card, with the object's name set as a title and the acquisition
facts as a subtitle beneath it. One self-contained JPEG they can post or print.

It is the *sibling* of :mod:`seestack.nameplate`, not a replacement:

* a **nameplate** draws a translucent footer bar **over** the picture — nothing
  is added to the frame, so it stays a wallpaper-shaped image;
* a **keepsake** adds a matte **around** the picture and sets the caption below
  it — nothing covers the sky, at the cost of a slightly larger canvas.

Both read the same :class:`~seestack.nameplate.NameplateFields` and share
:func:`~seestack.nameplate.acquisition_parts`, so they can never disagree about
the wording or about which fields count as missing.

Pure and offline, exactly like the nameplate: it draws onto a PIL image with
Pillow's built-in *scalable* font (``ImageFont.load_default(size=…)``, Pillow
≥10.1 — the project pins ``Pillow>=10.2``), so there is no bundled asset, no
network, and no ``webapp`` imports. The render is display-time only — it never
touches the stored FITS/preview or the linear science data — and every field is
best-effort: a fact we don't have is simply left out.
"""

from __future__ import annotations

from seestack.nameplate import NameplateFields, acquisition_parts

#: The matte colour. Not pure black: a picture's own uncovered/NaN corners are
#: black, and on a pure-black card they'd bleed into the mount and leave the
#: frame looking torn. A few levels up reads as "dark card" while keeping the
#: sky the darkest thing in the image.
MATTE_RGB = (16, 17, 21)

#: The hairline that separates picture from matte, so a dark sky still reads as
#: a framed photograph rather than a hole in the card.
EDGE_RGB = (58, 60, 68)

TITLE_RGB = (242, 243, 246)
DETAIL_RGB = (168, 172, 182)

#: Matte width as a fraction of the picture's short side. ~4.5 % is the
#: proportion a physical photo mount uses — enough to read as deliberate,
#: little enough that the picture still dominates.
_MATTE_FRACTION = 0.045
_MIN_MATTE_PX = 12

#: Title / detail type sizes, also as a fraction of the short side, each with a
#: floor so a small share stays legible.
_TITLE_FRACTION = 0.052
_MIN_TITLE_PX = 15
_DETAIL_FRACTION = 0.030
_MIN_DETAIL_PX = 11


def keepsake_caption(fields: NameplateFields) -> tuple[str, str]:
    """``(title, details)`` for a keepsake — e.g.
    ``("M 31", "4h 12m (505×30s) · 19 Jul 2026 · ZWO Seestar S50")``.

    Either half may be empty: an un-named target has no title, and a run with no
    usable provenance has no details. Both empty means there is nothing to say,
    which :func:`draw_keepsake` treats as "don't frame it at all"."""
    title = (fields.target or "").strip()
    details = " · ".join(acquisition_parts(fields, include_target=False))
    return title, details


def _load_font(size: int):
    """Pillow's built-in scalable font at ``size`` px — no bundled asset.

    Mirrors :func:`seestack.nameplate._load_font` (same Pillow>=10.2 pin, same
    graceful fall-back), as :mod:`seestack.recap` already does, rather than
    reaching across for another module's private helper."""
    from PIL import ImageFont

    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # pragma: no cover — Pillow <10.1 (below our pin)
        return ImageFont.load_default()


def _fit_font(text: str, avail: int, start_px: int, floor_px: int):
    """The largest built-in font at or below ``start_px`` whose ``text`` fits in
    ``avail`` pixels, never going below ``floor_px`` (a caption that simply
    cannot fit is centred and allowed to be tight rather than made unreadable)."""
    size = max(floor_px, start_px)
    font = _load_font(size)
    while size > floor_px and font.getlength(text) > avail:
        size -= 1
        font = _load_font(size)
    return font


def draw_keepsake(img, fields: NameplateFields):
    """Return a new RGB ``PIL.Image``: ``img`` matted on a dark card with its
    name and acquisition data set beneath it.

    When there is nothing to caption (:func:`keepsake_caption` gives two empty
    strings), the image is returned unchanged rather than framed — an empty
    mount is worse than no mount, and it keeps a provenance-less run a clean
    no-op, exactly as ``draw_nameplate`` does.

    The matte and type sizes scale with the picture's **short** side, so a wide
    mosaic and a square crop get proportionally the same frame; the caption
    shrinks to fit rather than overflowing the card.
    """
    from PIL import Image, ImageDraw

    title, details = keepsake_caption(fields)
    if not title and not details:
        return img.convert("RGB") if img.mode != "RGB" else img

    picture = img.convert("RGB")
    width, height = picture.size
    short = max(1, min(width, height))

    matte = max(_MIN_MATTE_PX, round(short * _MATTE_FRACTION))
    avail = max(1, width)

    title_font = (_fit_font(title, avail, round(short * _TITLE_FRACTION),
                            _MIN_TITLE_PX) if title else None)
    detail_font = (_fit_font(details, avail, round(short * _DETAIL_FRACTION),
                             _MIN_DETAIL_PX) if details else None)

    def _line_height(font) -> int:
        ascent, descent = font.getmetrics()
        return ascent + descent

    title_h = _line_height(title_font) if title_font is not None else 0
    detail_h = _line_height(detail_font) if detail_font is not None else 0
    # Breathing room between the two caption lines, only when both are present.
    gap = round(matte * 0.35) if (title_h and detail_h) else 0
    caption_h = title_h + gap + detail_h

    # Even matte on three sides; the foot carries the caption plus its own
    # margin, so the type sits *in* the mount rather than crowding its edge.
    top = left = right = matte
    bottom = matte + caption_h + matte

    card = Image.new("RGB", (width + left + right, height + top + bottom),
                     MATTE_RGB)
    card.paste(picture, (left, top))

    draw = ImageDraw.Draw(card)
    # Hairline just outside the picture, so a dark sky still reads as a framed
    # photograph. Drawn outside the pasted pixels — the picture is untouched.
    draw.rectangle((left - 1, top - 1, left + width, top + height),
                   outline=EDGE_RGB, width=1)

    y = top + height + matte
    centre = left + width / 2
    if title_font is not None:
        draw.text((centre, y), title, font=title_font, fill=TITLE_RGB,
                  anchor="ma")
        y += title_h + gap
    if detail_font is not None:
        draw.text((centre, y), details, font=detail_font, fill=DETAIL_RGB,
                  anchor="ma")
    return card
