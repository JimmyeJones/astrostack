"""\"Share your glow-up\" — one raw sub beside the finished stack, as one picture.

The app already *shows* a beginner what stacking bought them: the Target page's
"One frame vs your stack" reveal puts a single noisy sub under a draggable
divider against the finished picture, tone-matched so the only difference is
noise and detail. It is the most delightful thing the app does — and it cannot
leave the app. The one picture a non-astro friend actually understands is
*"this grainy single frame → this clean deep-sky photo, from the same little
telescope"*, and until now there was no way to send it: only a screenshot.

This module composes that artefact: the two halves side by side at a common
height, each labelled with what it is, under one plain-language caption line.

Pure and offline, exactly like :mod:`seestack.montage` and
:mod:`seestack.keepsake`: no network, no bundled asset (Pillow's built-in
scalable font), no ``webapp`` imports, and nothing written anywhere — the webapp
layer renders the two halves it already knows how to make, hands them here, and
serves the result as a display-time download. Every caption field is
best-effort: a fact we don't have is left out rather than printed blank.

Honesty is the whole point, so the composer deliberately does **not** stretch,
brighten, or otherwise touch either half's pixels — matching the two tone curves
is the *caller's* job (the reveal's ``reference-sub`` render already applies the
stack preview's own autostretch to the sub). All this does is lay them out.
"""

from __future__ import annotations

#: Composed width in pixels. 1600 leaves each half ~790 px — big enough to see
#: the grain in the "before" at social-media sizes, small enough to post
#: without re-compression. Mirrors :data:`seestack.montage.DEFAULT_WIDTH`.
DEFAULT_WIDTH = 1600

#: Sane bounds so a caller (or a query parameter) can't ask for a strip of
#: thumbnails or a canvas that costs a gigabyte to compose.
MIN_WIDTH = 480
MAX_WIDTH = 3200

_BG = (10, 12, 20)          # the app's deep-space background (as the montage)
_DIVIDER = (58, 60, 68)     # the keepsake's hairline, so the two agree
_CAPTION_FG = (200, 205, 220)

#: Cell aspect clamp. The two halves are the same field, so their shapes agree
#: in the ordinary case; the clamp only stops one freak panorama (a wide mosaic
#: master beside a single portrait panel) squeezing both into a strip.
_MIN_ASPECT = 0.6
_MAX_ASPECT = 2.2


def sub_exposure_label(seconds: float | None) -> str:
    """``"30-second"`` for a sub exposure, or ``""`` when there isn't one.

    Mirrors the reveal card's own ``subExposureLabel`` (frontend
    ``oneFrameVsStack.ts``) so the downloadable picture and the in-app card can
    never describe the same sub differently. A whole number of seconds reads as
    ``"30-second"``; a fractional exposure keeps one decimal.
    """
    try:
        value = float(seconds)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return ""
    if value <= 0 or value != value or value in (float("inf"), float("-inf")):
        return ""
    rounded = round(value * 10) / 10
    text = str(int(rounded)) if rounded == int(rounded) else f"{rounded:.1f}"
    return f"{text}-second"


def panel_labels(n_frames: int | None, sub_exposure_s: float | None) -> tuple[str, str]:
    """``("One 30-second frame", "505 frames stacked")`` — the two burned-on
    labels, so each half of the shared picture says what it is without the
    caption line having to be read.

    Each degrades on its own: no exposure gives ``"One frame"``, no frame count
    gives ``"Stacked"`` (never ``"None frames stacked"``).
    """
    exp = sub_exposure_label(sub_exposure_s)
    before = f"One {exp} frame" if exp else "One frame"
    count = _frame_count(n_frames)
    if not count:
        return before, "Stacked"
    return before, f"{count:,} frame{'' if count == 1 else 's'} stacked"


def before_after_caption(
    target: str | None,
    n_frames: int | None,
    sub_exposure_s: float | None,
    integration_s: float | None,
) -> str:
    """The one-line caption under the pair — e.g.
    ``"M 42 · one 30-second frame vs 505 frames stacked · 4h 12m of light"``.

    Every clause is optional and drops out cleanly when its datum is missing, so
    an older run with thin provenance gets a shorter sentence rather than one
    with a hole in it; with nothing at all to say the caption is ``""`` and
    :func:`build_before_after` simply omits the bar.

    Separated with ``·`` rather than an em dash or an arrow: the built-in font
    has no glyph for ``—``/``→`` and renders both as a tofu box on the one image
    the user is about to post (the same reason :func:`seestack.montage.montage_title`
    avoids them).
    """
    parts: list[str] = []
    name = (target or "").strip()
    if name:
        parts.append(name)
    before, after = panel_labels(n_frames, sub_exposure_s)
    if _frame_count(n_frames):
        parts.append(f"{before[0].lower()}{before[1:]} vs {after}")
    dur = _duration(integration_s)
    if dur:
        parts.append(f"{dur} of light")
    return " · ".join(parts)


def _frame_count(n_frames: int | None) -> int:
    """``n_frames`` as a positive int, or ``0`` when it isn't usable."""
    try:
        count = int(n_frames)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0
    return count if count > 0 else 0


def _duration(seconds: float | None) -> str:
    """``format_duration`` with the non-finite guard the caption path needs — a
    ``NaN`` integration reaches ``int(round(...))`` there and raises, and one
    unreadable header must not cost the user the whole picture."""
    from seestack.sharecard import format_duration

    try:
        value = float(seconds)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return ""
    if not value > 0 or value == float("inf"):
        return ""
    return format_duration(value)


def build_before_after(
    before,  # noqa: ANN001 — PIL.Image.Image, typed loosely to keep Pillow lazy
    after,  # noqa: ANN001
    *,
    caption: str = "",
    labels: tuple[str, str] = ("One frame", "Stacked"),
    width: int = DEFAULT_WIDTH,
):
    """Compose ``before`` and ``after`` into one labelled picture, or ``None``
    when either half is missing.

    Both images are fitted *whole* into equal half-cells and centred on the
    background (:func:`seestack.render.deepening._fit_onto`), so a single
    portrait sub beside a wider mosaic master keeps both geometries true rather
    than squashing either — the same letterboxing, and the same
    "black = no data" convention, the reel and the montage wall already use.
    Labels are burned on with the reel's own corner label so all three
    shareables speak in one visual voice.

    Returns a PIL RGB image; the caller encodes it (JPEG, as the montage does).
    """
    from PIL import Image, ImageDraw

    from seestack.render.deepening import _draw_corner_label, _fit_onto

    if before is None or after is None:
        return None
    try:
        left_img = before.convert("RGB")
        right_img = after.convert("RGB")
    except Exception:  # noqa: BLE001 — an unreadable half means no before/after
        return None

    width = max(MIN_WIDTH, min(int(width), MAX_WIDTH))
    gap = max(2, round(width * 0.006))
    pad = gap
    cell_w = max(1, (width - pad * 2 - gap) // 2)
    cell_h = max(1, round(cell_w / _pair_aspect(left_img, right_img)))

    caption_h = max(26, round(width * 0.034)) if caption else 0
    height = pad * 2 + cell_h + caption_h
    canvas = Image.new("RGB", (width, height), _BG)

    label_before, label_after = labels
    for i, (img, label) in enumerate(
            ((left_img, label_before), (right_img, label_after))):
        cell = _draw_corner_label(_fit_onto(img, (cell_w, cell_h)), label or "")
        canvas.paste(cell, (pad + i * (cell_w + gap), pad))

    # A hairline down the seam, so the pair reads as two photographs rather than
    # one picture with a dark band in the middle — the keepsake's frame edge, in
    # the one place this layout needs one.
    draw = ImageDraw.Draw(canvas)
    seam = pad + cell_w + gap // 2
    draw.line((seam, pad, seam, pad + cell_h - 1), fill=_DIVIDER, width=1)

    if caption:
        from seestack.recap import _fit_font

        font = _fit_font(draw, caption, round(caption_h * 0.52), width - pad * 2)
        draw.text((width / 2, pad + cell_h + round(caption_h * 0.30)), caption,
                  font=font, fill=_CAPTION_FG, anchor="ma")
    return canvas


def _pair_aspect(left, right) -> float:  # noqa: ANN001 — PIL images
    """The cell's width/height, taken from the two pictures themselves.

    Uses the *narrower* (taller) of the two aspect ratios so the shorter picture
    is the one that letterboxes: fitting a tall sub into a cell shaped like a
    wide master would put big black bars either side of the half the user is
    supposed to be looking at. Clamped to a sane range, and falling back to 4:3
    when neither image can describe itself.
    """
    ratios = []
    for img in (left, right):
        try:
            w, h = img.size
        except Exception:  # noqa: BLE001 — an image that can't describe itself
            continue
        if w > 0 and h > 0:
            ratios.append(w / h)
    if not ratios:
        return 4 / 3
    return min(_MAX_ASPECT, max(_MIN_ASPECT, min(ratios)))
