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

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from seestack.render.thumbnail import (
    _highlight_rolloff,
    _midtones_for,
    _mtf,
    _robust_median_sigma,
    load_stack_rgb,
)

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


def deepening_frame_label(date_iso: str | None, n_frames: int | None) -> str:
    """A compact provenance caption for one reel frame — e.g.
    ``"19 Jul 2026 · 120 subs"`` — so a *downloaded/shared* clip (which travels
    without the surrounding card) still tells its "night after night" story frame
    by frame. Best-effort: a missing/garbage date or a non-positive sub count is
    simply dropped (degrading to just the date, just the count, or ``""`` when
    neither is known, in which case the label is a clean no-op). Pure, so it's
    unit-tested. Reuses the nameplate's forgiving date parser for one date format
    across the app."""
    from seestack.nameplate import format_acq_date

    parts: list[str] = []
    date = format_acq_date(date_iso)
    if date:
        parts.append(date)
    if n_frames and n_frames > 0:
        n = int(n_frames)
        parts.append("1 sub" if n == 1 else f"{n} subs")
    return " · ".join(parts)


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
    width and shrinks so a long label never runs past ~60% of the frame."""
    if not text:
        return img
    from PIL import Image, ImageDraw

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


def render_deepening_frames(fits_paths: list[str | Path], *,
                            labels: list[str] | None = None,
                            max_width: int = 1024) -> list:
    """Render each stack FITS in ``fits_paths`` (oldest → newest) to a PIL RGB
    image, all under **one common stretch** taken from the deepest (last) frame.

    A display-space (editor-export) run is already a tone-mapped ``[0, 1]``
    image, so it's shown verbatim (a second stretch would double-process it);
    the common stretch is solved from the deepest **linear** master, which is
    the normal re-stack output. Frames are resized to the last (deepest) frame's
    size so the encoder gets a uniform series even as the canvas grows across
    nights. Frames that can't be loaded are skipped (best-effort).

    ``labels`` (optional, parallel to ``fits_paths``) burns a small provenance
    caption into each frame's bottom-left corner — see
    :func:`_draw_corner_label` — so a shared clip carries its own date/sub-count
    story. A label follows its frame through the skip filter, so a dropped
    (unreadable) frame never shifts the remaining labels off by one. Omitting
    ``labels`` (or an empty string per frame) leaves the frame unlabelled and
    byte-for-byte as before.
    """
    from PIL import Image

    loaded: list[tuple[np.ndarray, bool, str]] = []
    for i, fp in enumerate(fits_paths):
        label = labels[i] if (labels is not None and i < len(labels)) else ""
        try:
            rgb, display_space = load_stack_rgb(fp, max_width=max_width)
        except Exception as exc:  # noqa: BLE001 — a bad master just drops out
            log.warning("deepening reel: could not load %s: %s", fp, exc)
            continue
        loaded.append((rgb, display_space, label))
    if len(loaded) < 2:
        return []

    # Solve the shared stretch from the deepest *linear* frame (prefer the last),
    # so the whole reel is tone-mapped identically and only the noise changes.
    params: _StfParams | None = None
    for rgb, display_space, _label in reversed(loaded):
        if not display_space:
            params = _solve_stf_params(rgb)
            if params is not None:
                break

    images: list = []
    frame_labels: list[str] = []
    for rgb, display_space, label in loaded:
        if display_space:
            disp = np.clip(np.nan_to_num(rgb), 0.0, 1.0)
        elif params is not None:
            disp = _apply_stf_params(rgb, params)
        else:
            # No usable linear reference (every frame display-space-flat); show
            # what we have rather than nothing.
            disp = np.clip(np.nan_to_num(rgb), 0.0, 1.0)
        u8 = (disp * 255).astype(np.uint8)
        images.append(Image.fromarray(u8, mode="RGB"))
        frame_labels.append(label)

    target_size = images[-1].size
    # Unify size first (so the label is drawn crisp at the final output
    # resolution, not up/down-scaled with the frame), then burn each label in.
    resized = [im if im.size == target_size else im.resize(target_size, Image.BOX)
               for im in images]
    return [_draw_corner_label(im, lbl)
            for im, lbl in zip(resized, frame_labels, strict=True)]


def write_deepening_reel(frames: list, out_dir: Path, out_basename: str) -> Path | None:
    """Write ``frames`` (PIL RGB images, oldest → newest) as one looping
    animation — ``{out_basename}_deepening.webp`` (or ``.png`` APNG fallback) —
    beside the target's outputs. Each night holds ~0.9 s with a longer hold on
    the finished, deepest frame. Returns the written path, or ``None`` if there's
    nothing to write."""
    from PIL import Image, features

    if len(frames) < 2:
        return None
    base = frames[-1]
    norm = [f if f.size == base.size else f.resize(base.size, Image.BOX) for f in frames]
    durations = [900] * (len(norm) - 1) + [2200]
    out_dir = Path(out_dir)
    if features.check("webp"):
        path = out_dir / f"{out_basename}_deepening.webp"
        norm[0].save(path, format="WEBP", save_all=True, append_images=norm[1:],
                     duration=durations, loop=0, minimize_size=True)
    else:
        path = out_dir / f"{out_basename}_deepening.png"
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
