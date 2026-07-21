"""A tasteful acquisition nameplate baked into a shared image.

Astrophotographers traditionally caption a finished picture with its
*acquisition data* — target, total integration, sub count, date, gear — and
beginners love the look but have no easy way to make one; they post a bare JPEG
with no context. The app already records every field on the stack (``stacker.py``
stamps ``OBJECT`` / ``NFRAMES`` / ``EXPTOTAL`` / ``EXPOSURE`` / ``DATE-OBS`` into
the master FITS header), so this module turns those facts into one clean footer
bar drawn onto the share-export pixels — no typing, no fonts/positions to pick.

Pure and offline: it draws onto a PIL image with Pillow's built-in *scalable*
font (``ImageFont.load_default(size=…)``, available since Pillow 10.1 — the
project pins ``Pillow>=10.2``), so there is no bundled asset, no network, and no
``webapp`` imports. The webapp layer reads the run's provenance, builds a
:class:`NameplateFields`, and hands it to ``write_share_jpeg``; the render is a
display-time overlay only — it never touches the stored FITS/preview or the
linear science data.

Every field is best-effort: a line whose data is missing is simply omitted
(never a dangling separator or a blank), so an older/edited run without full
provenance still exports a tidy nameplate — or none at all, in which case the
image is returned unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass

from seestack.sharecard import format_duration

_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


@dataclass(frozen=True)
class NameplateFields:
    """The acquisition facts a nameplate can show, all optional.

    ``date_iso`` is a FITS ``DATE-OBS``-style timestamp (``"2026-07-19T21:03:00"``
    or just ``"2026-07-19"``); it's formatted to ``"19 Jul 2026"`` for display.
    ``camera`` is passed by the caller (the app targets the ZWO Seestar) rather
    than asserted here, so the pure helper stays gear-agnostic and testable.
    """

    target: str | None = None
    integration_s: float | None = None
    n_frames: int | None = None
    sub_exposure_s: float | None = None
    date_iso: str | None = None
    camera: str | None = None


def _fmt_sub_exposure(seconds: float | None) -> str:
    """A single sub's exposure for the ``"(505×30s)"`` detail — ``"30s"`` /
    ``"2.5s"``, trimming a trailing ``.0`` — or ``""`` when unknown."""
    if not seconds or seconds <= 0:
        return ""
    return f"{seconds:g}s"


def format_acq_date(date_iso: str | None) -> str:
    """``"2026-07-19T21:03:00"`` → ``"19 Jul 2026"``. Best-effort: returns ``""``
    for anything it can't confidently parse (missing, wrong shape, out-of-range),
    so a caption never shows a half-parsed or garbage date."""
    if not date_iso:
        return ""
    date_part = str(date_iso).strip().replace("T", " ").split(" ", 1)[0]
    bits = date_part.split("-")
    if len(bits) < 3:
        return ""
    try:
        year, month, day = int(bits[0]), int(bits[1]), int(bits[2])
    except (TypeError, ValueError):
        return ""
    if not (1 <= month <= 12) or not (1 <= day <= 31) or year <= 0:
        return ""
    return f"{day} {_MONTHS[month - 1]} {year}"


def nameplate_line(fields: NameplateFields) -> str:
    """The single ``·``-joined caption baked onto the image, e.g.
    ``"M 31 · 4h 12m (505×30s) · 19 Jul 2026 · ZWO Seestar S50"``.

    Each part is included only when it carries real information — the integration
    part folds in the ``(N×exp)`` detail when both are known, degrading to just
    the duration, just the sub count, or nothing — so a run missing any field
    still yields a tidy line (never a dangling separator or a ``"0 subs"``)."""
    parts: list[str] = []

    name = (fields.target or "").strip()
    if name:
        parts.append(name)

    integ = format_duration(fields.integration_s)
    sub_exp = _fmt_sub_exposure(fields.sub_exposure_s)
    n = fields.n_frames if (fields.n_frames and fields.n_frames > 0) else None
    if n and sub_exp:
        detail = f"({n}×{sub_exp})"
    elif n:
        detail = "(1 sub)" if n == 1 else f"({n} subs)"
    else:
        detail = ""
    if integ and detail:
        parts.append(f"{integ} {detail}")
    elif integ:
        parts.append(integ)
    elif detail:
        parts.append(detail)

    date = format_acq_date(fields.date_iso)
    if date:
        parts.append(date)

    camera = (fields.camera or "").strip()
    if camera:
        parts.append(camera)

    return " · ".join(parts)


def _load_font(size: int):
    """Pillow's built-in scalable font at ``size`` px — no bundled asset."""
    from PIL import ImageFont

    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # pragma: no cover — Pillow <10.1 (below our pin)
        return ImageFont.load_default()


def draw_nameplate(img, fields: NameplateFields):
    """Return a copy of ``img`` (an RGB ``PIL.Image``) with a translucent footer
    caption bar. When there's nothing to say (:func:`nameplate_line` is empty),
    the image is returned unchanged — so an off-switch or a provenance-less run
    is a clean no-op.

    The bar is drawn on the *final* (already-downscaled) share image, so the text
    is crisp at the output resolution. The font size scales with the image width
    and shrinks to fit so a long caption never overflows a narrow share."""
    from PIL import Image, ImageDraw

    text = nameplate_line(fields)
    if not text:
        return img.convert("RGB") if img.mode != "RGB" else img

    base = img.convert("RGBA")
    width, height = base.size

    # Font scales with the image (floored so it stays legible on a small share),
    # then shrinks until the caption fits within the side padding.
    side_pad = max(6, round(width * 0.012))
    avail = max(1, width - 2 * side_pad)
    font_px = max(11, round(width * 0.021))
    font = _load_font(font_px)
    while font_px > 8 and font.getlength(text) > avail:
        font_px -= 1
        font = _load_font(font_px)

    ascent, descent = font.getmetrics()
    line_h = ascent + descent
    v_pad = max(4, round(line_h * 0.4))
    bar_h = min(height, line_h + 2 * v_pad)

    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    # Semi-transparent dark strip so the caption reads over any sky/star field.
    od.rectangle((0, height - bar_h, width, height), fill=(0, 0, 0, 140))
    od.text((side_pad, height - bar_h + v_pad), text, font=font,
            fill=(255, 255, 255, 235))

    return Image.alpha_composite(base, overlay).convert("RGB")
