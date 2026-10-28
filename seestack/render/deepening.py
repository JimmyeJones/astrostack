"""Cross-run "night after night" deepening reel.

When a beginner shoots the same target across several clear nights and re-stacks,
the app already keeps every previous master: each re-stack archives the prior
``master.*`` set as a timestamped sibling and repoints its history row (see
:func:`seestack.stack.output._archive_existing_outputs`), so a target's output
folder holds a chronological series of its stacks, oldest → newest. This module
assembles that series into one short looping animation — the picture visibly
getting **cleaner and deeper** as more subs / more nights pile on.

The one thing that must be right is a *fair comparison*: every frame is
tone-mapped with the **same** stretch, derived once from the deepest (final)
stack, so the only visible change between frames is the noise dropping and faint
detail emerging — never a brightness / black-point jump. (The archived
``_preview.png``s are each autostretched to their *own* data, so a naive reel of
those flickers as the black point moves; re-rendering every frame from its master
FITS with a common stretch is what makes the "getting deeper" story read
honestly. This mirrors the one-sub-vs-stack reveal's fair-comparison fix.)

Purely additive and read-only: it renders from the master FITS the app already
keeps and writes only a cached animation beside the outputs — it touches no
stored pixels, schema, config, or default.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from seestack.render.thumbnail import (
    _highlight_rolloff,
    _midtones_for,
    _mtf,
    _robust_median_sigma,
    load_stack_rgb,
)
from seestack.stack.output import RUN_ARTEFACT_SUFFIXES, pack_unit

log = logging.getLogger(__name__)


@dataclass
class _StfParams:
    """A frozen Screen-Transfer-Function stretch, so it can be applied to every
    frame of the reel identically (not re-solved per frame)."""

    lo: float
    hi: float
    #: (shadows, m) per channel — the black point and midtones coefficient.
    channels: list[tuple[float, float]]


def _solve_stf_params(rgb: np.ndarray, *, target_bg: float = 0.20,
                      sigma_factor: float = -2.0) -> _StfParams | None:
    """Solve the STF stretch for ``rgb`` (an ``(H, W, 3)`` float array) once, so
    the same curve can be replayed on every frame via :func:`_apply_stf_params`.

    This deliberately mirrors :func:`seestack.render.thumbnail.autostretch`'s
    maths exactly — same robust normalization ceiling, same per-channel
    ``median + sigma_factor·σ`` black point, same midtones coefficient — but
    *returns* the coefficients instead of applying them, which is what lets a
    whole series share one stretch. Returns ``None`` for a degenerate (all-NaN
    or flat) reference frame.
    """
    img = rgb.astype(np.float32, copy=False)
    if not np.isfinite(img).any():
        return None
    lo = float(np.nanmin(img))
    hi = float(np.nanpercentile(img, 99.5))
    if not np.isfinite(hi) or hi <= lo:
        hi = float(np.nanmax(img))
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
        return None
    norm = (img - lo) / (hi - lo)
    channels: list[tuple[float, float]] = []
    for c in range(3):
        chan = norm[..., c]
        finite = np.isfinite(chan)
        if not finite.any():
            channels.append((0.0, 0.5))
            continue
        med, sigma = _robust_median_sigma(chan[finite])
        shadows = max(0.0, med + sigma_factor * sigma)
        rng = max(1.0 - shadows, 1e-6)
        norm_med = max((med - shadows) / rng, 1e-6)
        channels.append((shadows, _midtones_for(norm_med, target_bg)))
    return _StfParams(lo=lo, hi=hi, channels=channels)


def _apply_stf_params(rgb: np.ndarray, params: _StfParams) -> np.ndarray:
    """Apply a pre-solved :class:`_StfParams` stretch to ``rgb``, returning a
    ``[0, 1]`` display array. Uncovered (NaN) pixels floor to black, matching
    the app's convention — so a shallower frame with more mosaic gaps still
    renders cleanly rather than smearing NaN across the canvas."""
    img = rgb.astype(np.float32, copy=False)
    norm = (img - params.lo) / (params.hi - params.lo)
    out = np.zeros_like(norm)
    for c in range(3):
        chan = norm[..., c]
        finite = np.isfinite(chan)
        if not finite.any():
            continue
        shadows, m = params.channels[c]
        rng = max(1.0 - shadows, 1e-6)
        xr = (chan[finite] - shadows) / rng
        x = _highlight_rolloff(xr)
        out[..., c][finite] = np.clip(_mtf(x, m), 0.0, 1.0)
    return np.clip(out, 0.0, 1.0)


def deepening_frame_label(date_iso: str | None, n_frames: int | None,
                          end_iso: str | None = None,
                          nights_through: int | None = None) -> str:
    """A compact provenance caption for one reel frame — e.g.
    ``"19 Jul 2026 · 120 subs"``, or ``"11-14 Sep 2024 · 600 subs"`` when the step
    spans several nights — so a *downloaded/shared* clip (which travels without
    the surrounding card) still tells its "night after night" story frame by
    frame. Best-effort: a missing/garbage date or a non-positive sub count is
    simply dropped (degrading to just the date, just the count, or ``""`` when
    neither is known, in which case the label is a clean no-op). Pure, so it's
    unit-tested. Reuses the nameplate's forgiving date parser for one date format
    across the app.

    ``end_iso`` is the *other* end of a capture window (see
    :func:`deepening_series`): a reel frame ordered by when its subs were shot is
    a stack of the nights ``date_iso…end_iso``, and naming only one end of that
    would date a four-night stack by a single night. Omitted, equal, or
    unparseable ⇒ exactly the single-date label this function has always
    produced, so the stack-time series is byte-for-byte unchanged.

    ``nights_through`` is how many observing nights this step has accumulated,
    and it is only ever supplied for a series the caller has *shown* to be
    cumulative (``webapp.capture_nights.cumulative_night_steps``). It prefixes
    the label with ``"Night 1"`` / ``"Nights 1-3"``, which is the owner's own
    wording for what he asked the reel to be — the step's place in the
    progression, where the date says only when the newest subs were shot. Absent
    (the ordinary case, and every series that could not be shown to be nested)
    ⇒ the label is byte-for-byte what it was."""
    from seestack.nameplate import format_acq_date, format_acq_range

    parts: list[str] = []
    if nights_through and nights_through > 0:
        n = int(nights_through)
        # An ASCII hyphen, not an en dash: the reel's label is drawn with
        # Pillow's built-in font, and `render.glyphs.safe_for_default_font`
        # would have to transliterate it anyway.
        parts.append("Night 1" if n == 1 else f"Nights 1-{n}")
    date = (format_acq_range(date_iso, end_iso) if end_iso
            else format_acq_date(date_iso))
    if date:
        parts.append(date)
    if n_frames and n_frames > 0:
        n = int(n_frames)
        parts.append("1 sub" if n == 1 else f"{n} subs")
    return " · ".join(parts)


#: Version tag folded into the reel's cache signature by the caller. Bumped when
#: the *ordering or labelling* of an unchanged set of masters changes, so an
#: install sitting on a cached reel rebuilds it rather than serving one ordered by
#: the old clock. (The caller's own tag covers render-output changes.)
DEEPENING_SERIES_VERSION = "capture-v2"


def _run_display_space(run: Any) -> bool:
    """Whether a run row is an **editor export** — a tone-mapped ``[0, 1]`` image
    rather than a linear master (``options_json``'s ``display_space`` flag, set by
    ``webapp.pipeline``'s edit-export path). Best-effort and pure: unreadable or
    absent JSON reads as "linear", which is what every stacker output is."""
    raw = getattr(run, "options_json", None)
    if not raw:
        return False
    try:
        opts = json.loads(raw)
    except (TypeError, ValueError):
        return False
    return bool(isinstance(opts, dict) and opts.get("display_space"))


def _capture_window(run: Any) -> tuple[str, str] | None:
    """``(start, end)`` of a run's capture window, or ``None`` when it has none.

    One end on its own is honest — it means a run whose frames only yielded a
    single usable ``DATE-OBS`` — and is returned as both ends, exactly as
    :func:`webapp.capture_nights.capture_night_range` treats it."""
    start = (getattr(run, "capture_start_utc", None) or "").strip() or None
    end = (getattr(run, "capture_end_utc", None) or "").strip() or None
    if start is None and end is None:
        return None
    if start is None:
        return end, end  # type: ignore[return-value]
    if end is None:
        return start, start
    return (start, end) if start <= end else (end, start)


@dataclass(frozen=True)
class DeepeningSeries:
    """The reel's steps, oldest → newest, and **which clock** ordered them.

    ``dated_by`` is ``"capture"`` when every candidate run records when its subs
    were *shot* and the series is ordered and labelled by that, or ``"stack"``
    when at least one does not and the whole series falls back to
    ``timestamp_utc`` (when the stack *ran*). Callers must not mix the two: a
    caption that dated some frames by one clock and some by the other would be
    describing two different things with one word.
    """

    runs: list[Any]
    dated_by: str


def deepening_series(runs: Sequence[Any]) -> DeepeningSeries:
    """Order a target's stack runs into the deepening series the reel animates.

    **Why this is not simply "sort by ``timestamp_utc``", which is what it used to
    be.** ``timestamp_utc`` is when the stack *ran*; ``capture_start_utc`` /
    ``capture_end_utc`` (schema 18+) are when its subs were *shot*, and
    :mod:`webapp.capture_nights` already states the rule the rest of the app
    follows — *anything that says "shot on …" has to use the second pair*. A reel
    titled "night after night", labelling each frame with the day somebody pressed
    Stack, was the one surface that didn't: re-stack a back catalogue and the
    series is ordered by the order you happened to reprocess it in, each frame
    dated years off; stack three nights and then re-stack night one alone and the
    reel runs deep → shallow, contradicting its own "cleaner and deeper" story.

    So when **every** candidate run carries a window, the series is ordered by it
    and reported as ``dated_by="capture"``. If even one run lacks one — a
    pre-schema-18 row, a channel combine — the whole series keeps today's
    stack-time order and reports ``dated_by="stack"``. All-or-nothing on purpose:
    a series half-ordered by one clock and half by the other is ordered by
    neither.

    **The window's *end* is the ordering axis, and depth breaks its ties.** A
    cumulative series has growing windows, so the last sub's night normally
    separates every step. When it does not — two stacks whose newest sub is the
    same, which is what "I re-stacked with the frames I'd set aside" and "I
    re-stacked just tonight's subs" both look like — ordering on the *start* of
    the window puts the **wider** window first, and a wider window is the
    *deeper* stack: a pass on the bundled sample ran a reel 6 subs → 3 subs, the
    exact reverse of the card's own "cleaner and deeper" sentence. So ties on the
    end go to the shallower stack, then to the older id. Depth is deliberately
    only the tie-break: the owner asked for the series to be ordered by *when the
    subs were shot*, and a genuinely non-monotone depth (a single late night
    stacked on its own after a deeper earlier run) is then a fact about the
    library rather than something the ordering should hide.

    **One step per distinct set of nights.** A reprocess of subs already in the
    series is not a deepening step — it is the same nights again — so runs sharing
    a capture window collapse to one, preferring the one built from the most
    frames, then a **linear master over an editor export** (the reel tone-maps
    every frame through one shared stretch, and an export arrives already
    denoised/sharpened, so it would show noise dropping for a reason other than
    more subs), then the newest. That is what stops a "Reprocess everything" run
    landing as a final frame identical to the one before it. The collapse never
    takes the series below two steps — the reel self-hides there, and a card that
    exists today must not vanish because its two stacks turn out to be of one
    night — so in that case the un-collapsed capture-ordered list is returned.

    Pure; duck-typed over anything with the row's attributes (``StackRunRow``,
    or a stub in a test), so the engine keeps no webapp import.
    """
    ordered = sorted(runs, key=lambda r: (r.timestamp_utc or "", getattr(r, "id", 0) or 0))
    windows = [_capture_window(r) for r in ordered]
    if not ordered or any(w is None for w in windows):
        return DeepeningSeries(runs=ordered, dated_by="stack")

    by_window: dict[tuple[str, str], list[Any]] = {}
    for run, window in zip(ordered, windows, strict=True):
        by_window.setdefault(window, []).append(run)  # type: ignore[arg-type]

    def _best(group: list[Any]) -> Any:
        return max(group, key=lambda r: ((r.n_frames_used or 0),
                                         0 if _run_display_space(r) else 1,
                                         getattr(r, "id", 0) or 0))

    def _order(pairs: list[tuple[tuple[str, str], Any]]) -> list[Any]:
        return [run for _w, run in
                sorted(pairs, key=lambda p: (p[0][1],
                                             p[1].n_frames_used or 0,
                                             getattr(p[1], "id", 0) or 0))]

    collapsed = _order([(w, _best(g)) for w, g in by_window.items()])
    if len(collapsed) >= 2:
        return DeepeningSeries(runs=collapsed, dated_by="capture")
    # Two stacks of one night: keep both rather than dissolving the card.
    return DeepeningSeries(
        runs=_order(list(zip(windows, ordered, strict=True))),  # type: ignore[arg-type]
        dated_by="capture")


def series_depth_is_monotone(runs: Sequence[Any]) -> bool:
    """Does every step of this series hold at least as many subs as the one before?

    :func:`deepening_series` orders the reel by **when its subs were shot** and
    uses depth only to break a tie, which is the owner's own ask — so a series is
    allowed to step *back* in depth, and on a real library it does: stack three
    nights, then stack just tonight's subs on their own, and that shallow run has
    the newest window and lands **last**. The reel then visibly gets grainier at
    that step.

    The card's lead sentence promised the opposite ("cleaner and deeper … more
    subs each time") while the caption under it printed the counts that
    contradicted it, so the reel needs this one fact to say which story it is
    telling. It is *not* an ordering rule: hiding the shallow step would hide a
    fact about the library, which the ordering deliberately does not do.

    Pure and duck-typed like the rest of this module. A missing or unreadable
    count cannot show a step back, so it reads as "no step back here" — the
    reassuring wording is the one an unmeasurable series should keep.
    """
    prev: int | None = None
    for run in runs:
        n = getattr(run, "n_frames_used", None)
        if not isinstance(n, int) or n <= 0:
            continue
        if prev is not None and n < prev:
            return False
        prev = n
    return True


def _load_label_font(size: int):
    """Pillow's built-in scalable font at ``size`` px — no bundled asset (mirrors
    :func:`seestack.nameplate._load_font`)."""
    from PIL import ImageFont

    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # pragma: no cover — Pillow <10.1 (below our pin)
        return ImageFont.load_default()


def _draw_corner_label(img, text: str):
    """Return ``img`` (a PIL RGB image) with a small translucent provenance label
    in the **bottom-left** corner. Subtle by design — a dark backing strip plus
    white text — so it never competes with the picture. An empty ``text`` is a
    clean no-op (the image is returned unchanged), so a label-less frame is
    byte-for-byte what the reel produced before. The font scales with the frame
    width and shrinks so a long label never runs past ~60% of the frame.

    Also shared by the montage's tile captions and the before/after pair's cell
    labels, both of which carry a **target name** — so the text goes through
    :func:`seestack.render.glyphs.safe_for_default_font` before it is measured
    or drawn."""
    if not text:
        return img
    from PIL import Image, ImageDraw

    from seestack.render.glyphs import safe_for_default_font

    text = safe_for_default_font(text)

    base = img.convert("RGBA")
    width, height = base.size
    font_px = max(9, round(width * 0.028))
    font = _load_label_font(font_px)
    avail = max(1, round(width * 0.6))
    while font_px > 7 and font.getlength(text) > avail:
        font_px -= 1
        font = _load_label_font(font_px)

    ascent, descent = font.getmetrics()
    line_h = ascent + descent
    pad = max(3, round(font_px * 0.4))
    margin = max(3, round(width * 0.015))
    tw = font.getlength(text)
    x0 = margin
    y1 = height - margin
    y0 = y1 - (line_h + 2 * pad)
    x1 = x0 + tw + 2 * pad

    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.rectangle((x0, y0, x1, y1), fill=(0, 0, 0, 130))
    od.text((x0 + pad, y0 + pad), text, font=font, fill=(255, 255, 255, 235))
    return Image.alpha_composite(base, overlay).convert("RGB")


def _fit_onto(img, target_size: tuple[int, int]):
    """Return ``img`` scaled to ``target_size`` **without distorting it**:
    fitted whole inside the target and centred on a black canvas.

    The reel unifies every night onto the deepest frame's size, and each frame
    is loaded with its *own* aspect ratio (``load_stack_rgb`` caps the width, not
    the shape). That is fine while the canvas only grows in one direction, but
    the moment the stack's shape changes — a single portrait panel on night 1
    that has become a 2-wide landscape mosaic by night 5 — a straight
    ``resize(target_size)`` squashes the earlier nights, turning round stars into
    ellipses in exactly the frames the reel is meant to compare. Letterboxing
    keeps every night's geometry true; black padding matches the app's
    NaN = uncovered = black convention, so the pad reads as "no data here yet",
    which is what it is.

    A frame that already matches, or whose aspect ratio matches, comes back
    exactly as a plain resize would have produced it — the common single-field
    case is unchanged."""
    from PIL import Image

    tw, th = target_size
    if img.size == (tw, th):
        return img
    w, h = img.size
    scale = min(tw / w, th / h)
    nw, nh = max(1, round(w * scale)), max(1, round(h * scale))
    fitted = img.resize((nw, nh), Image.BOX)
    if (nw, nh) == (tw, th):
        return fitted
    canvas = Image.new("RGB", (tw, th), (0, 0, 0))
    canvas.paste(fitted, ((tw - nw) // 2, (th - nh) // 2))
    return canvas


#: How far (in reel pixels, at any corner of the frame) a sky placement may sit
#: from "draw it exactly where it is" and still be drawn exactly where it is. Two
#: stacks of one unchanged field differ by a fraction of a pixel of solve jitter;
#: resampling those through a sub-pixel affine would only soften the frame.
_SKY_IDENTITY_TOL_PX = 0.5


def _sky_affine(src_fits: str | Path, src_size: tuple[int, int],
                ref_fits: str | Path, ref_size: tuple[int, int],
                ) -> tuple[float, float, float, float, float, float] | None:
    """The affine that takes a pixel of the **reference** reel frame to the pixel
    of the **source** frame showing the same piece of sky — the coefficient order
    :meth:`PIL.Image.Image.transform` expects for ``Image.AFFINE``.

    Both sizes are the *decimated* reel frames (``load_stack_rgb`` scales every
    master to ``max_width`` by its own factor); the WCS headers describe the
    full-resolution masters, so each end converts between the two. Pillow's
    affine samples pixel ``i`` at continuous coordinate ``i + 0.5``, and a box
    decimation maps continuous ``u`` on the small frame to 0-based full-res
    ``u · W/w − 0.5`` — so that is the conversion used at both ends.

    A 3×3 grid across the reference frame goes pixel → sky → pixel and an affine
    is least-squares fitted through it: two TAN projections a degree or two
    apart differ from an affine by far less than a reel pixel. ``None`` — the
    caller falls back to fit-and-centre — when either master has no usable
    celestial WCS or a point does not project.
    """
    from seestack.io.wcs_io import celestial_wcs_from_fits

    src, sw, sh = celestial_wcs_from_fits(src_fits)
    ref, rw, rh = celestial_wcs_from_fits(ref_fits)
    if src is None or ref is None or min(sw, sh, rw, rh) <= 0:
        return None
    (sdw, sdh), (rdw, rdh) = src_size, ref_size
    t = np.array([0.0, 0.5, 1.0])
    u, v = np.meshgrid(t * rdw, t * rdh)
    u, v = u.ravel(), v.ravel()
    try:
        ra, dec = ref.all_pix2world(u * rw / rdw - 0.5, v * rh / rdh - 0.5, 0)
        sx, sy = src.all_world2pix(ra, dec, 0)
    except Exception as exc:  # noqa: BLE001 — a malformed WCS just means "can't place"
        log.warning("deepening reel: sky placement failed (%s → %s): %s",
                    src_fits, ref_fits, exc)
        return None
    su = (np.asarray(sx, dtype=float) + 0.5) * sdw / sw
    sv = (np.asarray(sy, dtype=float) + 0.5) * sdh / sh
    if not (np.all(np.isfinite(su)) and np.all(np.isfinite(sv))):
        return None
    design = np.column_stack([u, v, np.ones_like(u)])
    (a, b, c), *_ = np.linalg.lstsq(design, su, rcond=None)
    (d, e, f), *_ = np.linalg.lstsq(design, sv, rcond=None)
    coeffs = (float(a), float(b), float(c), float(d), float(e), float(f))
    if not all(np.isfinite(coeffs)) or abs(a * e - b * d) < 1e-9:
        return None
    return coeffs


def _place_on_sky(rgb: np.ndarray,
                  coeffs: tuple[float, float, float, float, float, float],
                  target_size: tuple[int, int]) -> np.ndarray | None:
    """Draw the **linear** ``(H, W, 3)`` frame ``rgb`` on a ``target_size`` canvas
    **where its sky is** on the reference frame (``coeffs`` from
    :func:`_sky_affine`), uncovered pixels NaN — or return ``None`` when none of
    it lands there, and the caller falls back to :func:`_fit_onto` rather than
    showing an all-black frame.

    A frame that already sits exactly on the reference grid (same size, an
    identity mapping to within :data:`_SKY_IDENTITY_TOL_PX`) comes back
    untouched, so the ordinary single-field re-stack is byte-for-byte what the
    reel always drew.

    **Why this runs before the stretch and samples nearest.** It used to resample
    the *stretched u8* frame bilinearly. The stretch has already clipped the sky's
    noise at its black point, so averaging clipped values lifted the sky; and a
    sub-pixel bilinear resample averages neighbours, smoothing the earlier frame's
    noise ~30 % while the newest is never resampled. On a mosaic that grew, the
    shallow first night came out *quieter and brighter* than the deep newest one
    (Scout 2026-10-28) — the reverse of the reel's story. The caller now loads
    each source at the reference's sky scale (:func:`_sky_scale_width`), so the
    mapping is ~1:1 and a nearest pick moves whole pixels without averaging any.
    A source still drawn smaller than it was loaded (one capped by
    :data:`_MAX_PLACED_SOURCE_WIDTH`) is first area-averaged, NaN-aware, in the
    linear domain — what ``load_stack_rgb`` does."""
    from seestack.render.thumbnail import _nan_aware_area_downscale_plane

    a, b, c, d, e, f = coeffs
    tw, th = target_size
    h, w = rgb.shape[:2]
    corners = [(0.0, 0.0), (tw, 0.0), (0.0, th), (tw, th)]
    if (w, h) == (tw, th) and all(
            abs(a * x + b * y + c - x) <= _SKY_IDENTITY_TOL_PX
            and abs(d * x + e * y + f - y) <= _SKY_IDENTITY_TOL_PX
            for x, y in corners):
        return rgb

    # Does any of the source land on the target? Map the source's corners into
    # target coordinates through the inverse and intersect the bounding boxes.
    det = a * e - b * d
    inv = ((e, -b, b * f - c * e), (-d, a, c * d - a * f))
    xs, ys = [], []
    for x, y in [(0.0, 0.0), (w, 0.0), (0.0, h), (w, h)]:
        xs.append((inv[0][0] * x + inv[0][1] * y + inv[0][2]) / det)
        ys.append((inv[1][0] * x + inv[1][1] * y + inv[1][2]) / det)
    if max(xs) <= 0 or min(xs) >= tw or max(ys) <= 0 or min(ys) >= th:
        return None

    # Source pixels per target pixel; above ~1.5 pre-shrink with an area average.
    scale = abs(det) ** 0.5
    if scale > 1.5:
        nw, nh = max(1, round(w / scale)), max(1, round(h / scale))
        sx, sy = nw / w, nh / h
        shrunk = np.empty((nh, nw, rgb.shape[2]), dtype=np.float32)
        for ch in range(rgb.shape[2]):
            shrunk[..., ch] = _nan_aware_area_downscale_plane(rgb[..., ch], nw, nh)
        rgb, w, h = shrunk, nw, nh
        a, b, c, d, e, f = a * sx, b * sx, c * sx, d * sy, e * sy, f * sy

    # The nearest source pixel under each target pixel's centre (Pillow's
    # convention, pixel i is continuous i + 0.5, which `_sky_affine` is fitted in).
    u = np.arange(tw, dtype=np.float64)[None, :] + 0.5
    v = np.arange(th, dtype=np.float64)[:, None] + 0.5
    src_x = np.floor(a * u + b * v + c).astype(np.int64)
    src_y = np.floor(d * u + e * v + f).astype(np.int64)
    inside = (src_x >= 0) & (src_x < w) & (src_y >= 0) & (src_y < h)
    out = np.full((th, tw, rgb.shape[2]), np.nan, dtype=np.float32)
    out[inside] = rgb[src_y[inside], src_x[inside]]
    return out


#: The widest an earlier frame is ever loaded to match the reference's sky scale
#: (a mosaic shown against a newer single panel would otherwise load near full
#: size). Past it the placement area-averages the rest of the way — a little more
#: smoothing on that one shape, but a bounded allocation on the NAS.
_MAX_PLACED_SOURCE_WIDTH = 4096


def _sky_scale_width(src_fits: str | Path, ref_fits: str | Path,
                     ref_size: tuple[int, int], max_width: int) -> int | None:
    """The width to load ``src_fits`` at so one of its pixels covers the same sky
    as one pixel of the reference reel frame — or ``None`` (load it as usual)
    when either master has no usable WCS.

    Every master used to be decimated to ``max_width`` by its *own* factor, so a
    single panel (≈1.05×) and the 2×2 mosaic it grew into (≈2×) had their noise
    averaged down by different amounts before the reel compared them. Loading each
    earlier night at the reference's sky scale averages them alike."""
    from seestack.io.wcs_io import celestial_wcs_from_fits

    src, sw, sh = celestial_wcs_from_fits(src_fits)
    if src is None or sw <= 0 or sh <= 0:
        return None
    full = _sky_affine(src_fits, (sw, sh), ref_fits, ref_size)
    if full is None:
        return None
    a, b, _c, d, e, _f = full
    per_ref_px = abs(a * e - b * d) ** 0.5   # full-res source px per reel px
    if not np.isfinite(per_ref_px) or per_ref_px <= 0:
        return None
    width = int(round(sw / per_ref_px))
    return max(1, min(width, sw, max(max_width, _MAX_PLACED_SOURCE_WIDTH)))


def render_deepening_frames(fits_paths: list[str | Path], *,
                            labels: list[str] | None = None,
                            max_width: int = 1024) -> list:
    """Render each stack FITS in ``fits_paths`` (oldest → newest) to a PIL RGB
    image, all under **one common stretch** taken from the deepest (last) frame.

    A display-space (editor-export) run is already a tone-mapped ``[0, 1]``
    image, so it's shown verbatim (a second stretch would double-process it);
    the common stretch is solved from the deepest **linear** master, which is
    the normal re-stack output. Frames are brought onto the last (deepest)
    frame's canvas so the encoder gets a uniform series even as the canvas grows
    across nights — placed by their WCS where both masters carry one, so the
    object stays put while a mosaic grows around it, else fitted and centred
    (see :func:`_place_on_sky`). Frames that can't be loaded are skipped
    (best-effort).

    ``labels`` (optional, parallel to ``fits_paths``) burns a small provenance
    caption into each frame's bottom-left corner — see
    :func:`_draw_corner_label` — so a shared clip carries its own date/sub-count
    story. A label follows its frame through the skip filter, so a dropped
    (unreadable) frame never shifts the remaining labels off by one. Omitting
    ``labels`` (or an empty string per frame) leaves the frame unlabelled and
    byte-for-byte as before.
    """
    from PIL import Image

    loaded: list[tuple[np.ndarray, bool, str, str | Path]] = []
    for i, fp in enumerate(fits_paths):
        label = labels[i] if (labels is not None and i < len(labels)) else ""
        try:
            rgb, display_space = load_stack_rgb(fp, max_width=max_width)
        except Exception as exc:  # noqa: BLE001 — a bad master just drops out
            log.warning("deepening reel: could not load %s: %s", fp, exc)
            continue
        loaded.append((rgb, display_space, label, fp))
    if len(loaded) < 2:
        return []

    # Solve the shared stretch from the deepest *linear* frame (prefer the last),
    # so the whole reel is tone-mapped identically and only the noise changes.
    params: _StfParams | None = None
    for rgb, display_space, _label, _fp in reversed(loaded):
        if not display_space:
            params = _solve_stf_params(rgb)
            if params is not None:
                break

    def _to_display(rgb: np.ndarray, display_space: bool) -> np.ndarray:
        if display_space or params is None:
            # An export is shown verbatim; with no usable linear reference (every
            # frame display-space-flat) show what we have rather than nothing.
            return np.clip(np.nan_to_num(rgb), 0.0, 1.0)
        return _apply_stf_params(rgb, params)

    # Each earlier night is drawn where its sky sits on the newest frame — a
    # mosaic that grew panel by panel would otherwise have its first panel
    # centred and blown up to fill the frame, the object jumping and zooming
    # between nights. It is loaded at the newest frame's sky scale and placed in
    # the *linear* domain before the shared stretch, so a shallow night is never
    # averaged or lifted into looking cleaner than the deep one (see
    # `_place_on_sky`). No WCS, or no shared sky ⇒ the old fit-and-centre.
    ref_rgb, _ref_ds, _ref_label, ref_fits = loaded[-1]
    target_size = (ref_rgb.shape[1], ref_rgb.shape[0])
    frames: list = []
    for i, (rgb, display_space, label, fp) in enumerate(loaded):
        placed: np.ndarray | None = None
        if i < len(loaded) - 1 and str(fp) != str(ref_fits):
            src = rgb
            width = _sky_scale_width(fp, ref_fits, target_size, max_width)
            if width is not None and width != rgb.shape[1]:
                try:
                    src, _ds = load_stack_rgb(fp, max_width=width)
                except Exception as exc:  # noqa: BLE001 — keep the first load
                    log.warning("deepening reel: could not reload %s: %s", fp, exc)
            coeffs = _sky_affine(fp, (src.shape[1], src.shape[0]), ref_fits, target_size)
            if coeffs is not None:
                placed = _place_on_sky(src, coeffs, target_size)
        if placed is not None:
            img = Image.fromarray(pack_unit(_to_display(placed, display_space)), mode="RGB")
        else:
            img = _fit_onto(Image.fromarray(pack_unit(_to_display(rgb, display_space)),
                                            mode="RGB"), target_size)
        # Size is unified first, so the label is drawn crisp at the final output
        # resolution rather than up/down-scaled with the frame.
        frames.append(_draw_corner_label(img, label))
    return frames


def write_deepening_reel(frames: list, out_dir: Path, out_basename: str) -> Path | None:
    """Write ``frames`` (PIL RGB images, oldest → newest) as one looping
    animation — ``{out_basename}_deepening.webp`` (or ``.png`` APNG fallback) —
    beside the target's outputs. Each night holds ~0.9 s with a longer hold on
    the finished, deepest frame. Returns the written path, or ``None`` if there's
    nothing to write."""
    from PIL import features

    if len(frames) < 2:
        return None
    base = frames[-1]
    norm = [_fit_onto(f, base.size) for f in frames]
    durations = [900] * (len(norm) - 1) + [2200]
    out_dir = Path(out_dir)
    # The suffixes come from `RUN_ARTEFACT_SUFFIXES` rather than being spelled
    # here, because that table is what the delete/archive/merge paths act on — a
    # reel named by hand is a reel nothing cleans up (which is what happened).
    if features.check("webp"):
        path = out_dir / f"{out_basename}{RUN_ARTEFACT_SUFFIXES['deepening_webp']}"
        norm[0].save(path, format="WEBP", save_all=True, append_images=norm[1:],
                     duration=durations, loop=0, minimize_size=True)
    else:
        path = out_dir / f"{out_basename}{RUN_ARTEFACT_SUFFIXES['deepening_apng']}"
        norm[0].save(path, format="PNG", save_all=True, append_images=norm[1:],
                     duration=durations, loop=0)
    log.info("Deepening reel saved (%d stacks) → %s", len(norm), path.name)
    return path


def build_deepening_reel(fits_paths: list[str | Path], out_dir: Path,
                         out_basename: str, *, labels: list[str] | None = None,
                         max_width: int = 1024) -> Path | None:
    """Render ``fits_paths`` (oldest → newest) under a common stretch and write
    the looping "night after night" reel beside the outputs. Convenience wrapper
    over :func:`render_deepening_frames` + :func:`write_deepening_reel`. Returns
    the written path, or ``None`` when fewer than two frames survive.

    ``labels`` (optional, parallel to ``fits_paths``) burns a per-frame
    provenance caption in — see :func:`render_deepening_frames`."""
    frames = render_deepening_frames(fits_paths, labels=labels, max_width=max_width)
    return write_deepening_reel(frames, out_dir, out_basename)
