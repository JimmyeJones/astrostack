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


def render_deepening_frames(fits_paths: list[str | Path], *,
                            max_width: int = 1024) -> list:
    """Render each stack FITS in ``fits_paths`` (oldest → newest) to a PIL RGB
    image, all under **one common stretch** taken from the deepest (last) frame.

    A display-space (editor-export) run is already a tone-mapped ``[0, 1]``
    image, so it's shown verbatim (a second stretch would double-process it);
    the common stretch is solved from the deepest **linear** master, which is
    the normal re-stack output. Frames are resized to the last (deepest) frame's
    size so the encoder gets a uniform series even as the canvas grows across
    nights. Frames that can't be loaded are skipped (best-effort).
    """
    from PIL import Image

    loaded: list[tuple[np.ndarray, bool]] = []
    for fp in fits_paths:
        try:
            rgb, display_space = load_stack_rgb(fp, max_width=max_width)
        except Exception as exc:  # noqa: BLE001 — a bad master just drops out
            log.warning("deepening reel: could not load %s: %s", fp, exc)
            continue
        loaded.append((rgb, display_space))
    if len(loaded) < 2:
        return []

    # Solve the shared stretch from the deepest *linear* frame (prefer the last),
    # so the whole reel is tone-mapped identically and only the noise changes.
    params: _StfParams | None = None
    for rgb, display_space in reversed(loaded):
        if not display_space:
            params = _solve_stf_params(rgb)
            if params is not None:
                break

    images: list = []
    for rgb, display_space in loaded:
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

    target_size = images[-1].size
    return [im if im.size == target_size else im.resize(target_size, Image.BOX)
            for im in images]


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
                         out_basename: str, *, max_width: int = 1024) -> Path | None:
    """Render ``fits_paths`` (oldest → newest) under a common stretch and write
    the looping "night after night" reel beside the outputs. Convenience wrapper
    over :func:`render_deepening_frames` + :func:`write_deepening_reel`. Returns
    the written path, or ``None`` when fewer than two frames survive."""
    frames = render_deepening_frames(fits_paths, max_width=max_width)
    return write_deepening_reel(frames, out_dir, out_basename)
