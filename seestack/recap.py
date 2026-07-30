"""A shareable "your sky, so far" recap poster.

The app already tallies everything a hobbyist is quietly proud of — nights out,
total integration, targets imaged, subs kept, the biggest project — but those
numbers live on a web page nobody else can see. A beginner who wants to show a
friend (or post) what a season of imaging added up to has nothing to hand them.

This module turns those already-computed facts into two things:

  * :func:`recap_caption` — a copy-paste blurb for the post itself.
  * :func:`draw_recap_poster` — one square image with the headline numbers and,
    when there is one, the user's own best picture as the backdrop.

Pure and offline: no network, no bundled asset (Pillow's built-in *scalable*
font, exactly like :mod:`seestack.nameplate`), and no ``webapp`` imports. The
webapp layer collects the facts from the library summary + activity calendar it
already serves and hands them here; nothing is written to the library and no
stored pixels are touched — the poster is a display-time render.

Every field is optional and best-effort: a missing figure is simply left out
rather than shown as a zero, so a two-night-old library still produces a tidy
poster instead of a wall of "0".
"""

from __future__ import annotations

from dataclasses import dataclass

from seestack.nameplate import format_acq_date
from seestack.sharecard import format_duration

# The poster is a square so it fits every social surface without cropping, and
# 1080 px is the usual upload ceiling before re-compression.
POSTER_SIZE = 1080


@dataclass(frozen=True)
class RecapFacts:
    """The facts a recap poster can show — all optional.

    ``window_months`` is how far back the ``n_nights`` count reaches (the
    activity calendar's trailing window), so the poster can say "this year"
    honestly rather than implying an all-time figure it doesn't have.
    """

    total_integration_s: float | None = None
    n_targets: int | None = None
    n_subs_kept: int | None = None
    n_nights: int | None = None
    window_months: int = 12
    first_light_utc: str | None = None
    top_target_name: str | None = None
    top_target_integration_s: float | None = None


def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one}" if n == 1 else f"{n:,} {many}"


def recap_stats(facts: RecapFacts) -> list[tuple[str, str]]:
    """The headline ``(value, label)`` pairs for the poster, biggest first.

    Only figures that carry real information are included — a zero or a missing
    count is dropped rather than printed, because "0 nights" reads as a bug
    rather than a beginning. Returns an empty list when there is nothing worth
    celebrating yet, which is the caller's cue not to offer a poster at all.
    """
    out: list[tuple[str, str]] = []
    dur = format_duration(facts.total_integration_s)
    if dur:
        out.append((dur, "of light collected"))
    if facts.n_nights and facts.n_nights > 0:
        out.append((f"{facts.n_nights:,}", "night" if facts.n_nights == 1 else "nights out"))
    if facts.n_targets and facts.n_targets > 0:
        out.append((f"{facts.n_targets:,}",
                    "target imaged" if facts.n_targets == 1 else "targets imaged"))
    if facts.n_subs_kept and facts.n_subs_kept > 0:
        out.append((f"{facts.n_subs_kept:,}",
                    "sub kept" if facts.n_subs_kept == 1 else "subs kept"))
    return out


def recap_caption(facts: RecapFacts) -> str:
    """The copy-paste blurb to post beside the poster, e.g.

    ``"12 nights under the sky · 8h 20m of light · 4 targets · biggest project:
    M 31 (4h 12m)"``

    Built from whatever is known, in the order a person would say it, with each
    part omitted when its figure is missing — so it never shows a dangling
    separator or a zero. Returns ``""`` when nothing has been captured yet.
    """
    parts: list[str] = []
    if facts.n_nights and facts.n_nights > 0:
        parts.append(_plural(facts.n_nights, "night", "nights") + " under the sky")
    dur = format_duration(facts.total_integration_s)
    if dur:
        parts.append(f"{dur} of light")
    if facts.n_targets and facts.n_targets > 0:
        parts.append(_plural(facts.n_targets, "target", "targets"))
    name = (facts.top_target_name or "").strip()
    if name:
        top_dur = format_duration(facts.top_target_integration_s)
        parts.append(f"biggest project: {name} ({top_dur})" if top_dur
                     else f"biggest project: {name}")
    return " · ".join(parts)


def recap_top_project_line(facts: RecapFacts) -> str:
    """The poster's "biggest project" line, or ``""`` when no target is known.

    Uses a **middle dot** rather than an em dash: Pillow's built-in font has no
    glyph for U+2014, so an em dash renders as a tofu box on the finished poster
    — the one character the user is about to post publicly.
    """
    name = (facts.top_target_name or "").strip()
    if not name:
        return ""
    dur = format_duration(facts.top_target_integration_s)
    return f"Biggest project: {name} · {dur}" if dur else f"Biggest project: {name}"


def recap_since_line(facts: RecapFacts) -> str:
    """The small "since <date>" footnote, or ``""`` when first light is unknown
    or unparseable (the poster then simply omits the line)."""
    when = format_acq_date(facts.first_light_utc)
    return f"Since {when}" if when else ""


def _load_font(size: int):
    """Pillow's built-in scalable font at ``size`` px — no bundled asset.

    Mirrors :func:`seestack.nameplate._load_font` (same Pillow>=10.2 pin, same
    graceful fall-back) rather than importing it, so neither module has to be a
    dependency of the other."""
    from PIL import ImageFont

    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # pragma: no cover — Pillow <10.1 (below our pin)
        return ImageFont.load_default()


def _text_width(draw, text: str, font) -> float:  # noqa: ANN001 — PIL types
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0]


def _fit_font(draw, text: str, size: int, max_width: float):  # noqa: ANN001
    """The largest built-in font ≤ ``size`` whose ``text`` fits ``max_width``.

    A long target name or a five-figure sub count must never run off the edge of
    a poster the user is about to post, so every line shrinks to fit rather than
    overflowing. Bottoms out at 10 px (below that it's unreadable anyway and the
    caller's layout guarantees room)."""
    font = _load_font(size)
    while size > 10 and _text_width(draw, text, font) > max_width:
        size -= 2
        font = _load_font(size)
    return font


def _cover_crop(img, size: int):  # noqa: ANN001 — PIL Image
    """Scale ``img`` to fill a ``size``×``size`` square and centre-crop it.

    Cover (not fit) so the backdrop has no letterbox bars; the centre crop keeps
    the framed object, which is what a Seestar sub is centred on."""
    from PIL import Image

    w, h = img.size
    if w <= 0 or h <= 0:
        return Image.new("RGB", (size, size), (10, 12, 20))
    scale = max(size / w, size / h)
    new = (max(1, round(w * scale)), max(1, round(h * scale)))
    resized = img.convert("RGB").resize(new, Image.LANCZOS)
    left = (new[0] - size) // 2
    top = (new[1] - size) // 2
    return resized.crop((left, top, left + size, top + size))


def draw_recap_poster(facts: RecapFacts, hero=None, *, size: int = POSTER_SIZE):  # noqa: ANN001
    """Render the recap as one square RGB ``PIL.Image``.

    ``hero`` is the user's own finished picture (any PIL image) used as the
    backdrop, darkened so the text stays readable; without one the poster falls
    back to a plain deep-space background, so a library with no stack yet still
    renders rather than failing.

    Layout, top to bottom: a title, up to four big stat blocks in a 2×2 grid,
    the "biggest project" line, and the "since <date>" footnote. Anything with
    no data is skipped and the rest closes up, so the poster is never sparse in
    an obviously-broken way.
    """
    from PIL import Image, ImageDraw

    canvas = (_cover_crop(hero, size) if hero is not None
              else Image.new("RGB", (size, size), (10, 12, 20)))
    # Darken the backdrop so white text stays legible over a bright galaxy core,
    # while the picture still reads as the user's own.
    veil = Image.new("RGB", (size, size), (6, 8, 16))
    canvas = Image.blend(canvas, veil, 0.55)
    draw = ImageDraw.Draw(canvas)

    margin = round(size * 0.075)
    inner = size - 2 * margin

    title = "My sky, so far"
    font = _fit_font(draw, title, round(size * 0.072), inner)
    draw.text((margin, margin), title, font=font, fill=(255, 255, 255))

    # The stat grid sits in the middle of the square and the provenance lines
    # anchor to the bottom, so the poster stays balanced whether it carries one
    # stat or four (a top-down flow left a big empty foot on a thin library).
    stats = recap_stats(facts)[:4]
    if stats:
        col_w = inner // 2
        row_h = round(size * 0.165)
        n_rows = (len(stats) + 1) // 2
        top = round(size * 0.5) - (n_rows * row_h) // 2
        for i, (value, label) in enumerate(stats):
            cx = margin + (i % 2) * col_w
            cy = top + (i // 2) * row_h
            vfont = _fit_font(draw, value, round(size * 0.085), col_w - margin // 2)
            draw.text((cx, cy), value, font=vfont, fill=(198, 176, 255))
            lfont = _fit_font(draw, label, round(size * 0.030), col_w - margin // 2)
            draw.text((cx, cy + round(size * 0.092)), label, font=lfont,
                      fill=(196, 200, 216))

    # Bottom-anchored, laid out upwards: footer, then "since", then the biggest
    # project — each line skipped (and its space reclaimed) when it has no data.
    y = size - margin - round(size * 0.030)
    footer = "Made with AstroStack"
    draw.text((margin, y), footer, font=_load_font(round(size * 0.026)),
              fill=(132, 138, 160))

    since = recap_since_line(facts)
    if since:
        y -= round(size * 0.048)
        sfont = _fit_font(draw, since, round(size * 0.030), inner)
        draw.text((margin, y), since, font=sfont, fill=(158, 164, 184))

    line = recap_top_project_line(facts)
    if line:
        y -= round(size * 0.058)
        lfont = _fit_font(draw, line, round(size * 0.036), inner)
        draw.text((margin, y), line, font=lfont, fill=(232, 234, 244))
    return canvas
