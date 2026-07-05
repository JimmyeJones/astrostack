"""
Photometric (multiplicative) frame normalization for the stack.

Frames are already *additively* sky-zeroed per frame (the per-frame background
subtraction in ``align.py``), but nothing gain-matches their **signal**. Haze,
airmass and thin cloud scale the recorded flux of stars and nebulosity frame to
frame by tens of percent across a multi-night session. Left uncorrected this:

  * inflates the per-pixel spread the κ-σ / min-max rejection clips against, so
    real outliers on bright structure survive (weaker rejection where it matters
    most), and
  * lets hazy nights quietly dim the combined result.

This module estimates a per-frame **multiplicative scale** from the frame's own
``transparency_score`` (the median flux of its brightest stars, already measured
by QC) relative to the *median* transparency of the frames being stacked, and
the stacker divides it out of the pixels **before** accumulation. Normalising to
the median (not the reference frame or the brightest) keeps the combined image's
overall brightness stable — half the frames scale gently up, half gently down.

Design choices (all in service of "never make a live stack worse"):

  * **Neutral fallback everywhere.** A frame with no / non-positive transparency
    keeps scale 1.0 (it isn't penalised for something we couldn't measure). If
    fewer than ``min_frames`` frames carry a usable score the whole run is
    neutral (a median from one or two frames isn't a trustworthy reference).
  * **Bounded.** Each scale is clipped to ``[1/max_ratio, max_ratio]`` so a
    single wild transparency estimate can't blow a frame up or crush it.
  * **Independent of quality weighting.** Scaling gain-matches the *values*;
    quality weighting down-weights the *contribution*. Both can be on together
    (a hazy frame is scaled up to match *and* trusted less), and either can be
    off. The two are orthogonal and compose correctly.

The scale is comparable only *within one target* (same camera/gain/exposure) —
exactly the assumption the quality-weighting ``transparency_factor`` already
makes — which is fine because a stack is always one target.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from seestack.io.project import FrameRow

log = logging.getLogger(__name__)

# Below this many frames with a usable transparency score, the median reference
# isn't trustworthy — stay fully neutral rather than normalise against noise.
_MIN_MEASURED_FRAMES = 3


@dataclass
class PhotometricStats:
    """Summary diagnostics for the stack log / FITS provenance."""

    n_scaled: int          # frames that got a measured (data-derived) scale
    n_neutral: int         # frames left at 1.0 (no usable transparency)
    n_adjusted: int        # frames whose scale actually moved off 1.0
    min_scale: float
    max_scale: float
    median_scale: float


def compute_photometric_scales(
    frames: list[FrameRow],
    *,
    max_ratio: float = 2.0,
    min_frames: int = _MIN_MEASURED_FRAMES,
) -> tuple[dict[int, float], PhotometricStats]:
    """
    Build a ``{frame_id: scale}`` map that gain-matches every frame's signal to
    the median transparency of the run.

    ``max_ratio`` bounds each scale to ``[1/max_ratio, max_ratio]``. A frame with
    no usable ``transparency_score`` (or when too few frames carry one) gets the
    neutral scale ``1.0``.
    """
    max_ratio = max(1.0, float(max_ratio))
    measured = [
        f.transparency_score for f in frames
        if f.transparency_score is not None and f.transparency_score > 0
    ]
    # Not enough signal to establish a robust reference → everything neutral.
    if len(measured) < max(1, int(min_frames)):
        scales = {f.id: 1.0 for f in frames if f.id is not None}
        n = len(scales)
        return scales, PhotometricStats(0, n, 0, 1.0, 1.0, 1.0)

    ref = float(np.median(measured))
    lo, hi = 1.0 / max_ratio, max_ratio

    scales: dict[int, float] = {}
    measured_scales: list[float] = []
    n_neutral = 0
    n_adjusted = 0
    for f in frames:
        if f.id is None:
            continue
        if f.transparency_score is not None and f.transparency_score > 0 and ref > 0:
            s = float(np.clip(ref / f.transparency_score, lo, hi))
            scales[f.id] = s
            measured_scales.append(s)
            if abs(s - 1.0) > 1e-3:
                n_adjusted += 1
        else:
            scales[f.id] = 1.0
            n_neutral += 1

    if measured_scales:
        stats = PhotometricStats(
            n_scaled=len(measured_scales),
            n_neutral=n_neutral,
            n_adjusted=n_adjusted,
            min_scale=float(min(measured_scales)),
            max_scale=float(max(measured_scales)),
            median_scale=float(np.median(measured_scales)),
        )
    else:
        stats = PhotometricStats(0, n_neutral, 0, 1.0, 1.0, 1.0)
    return scales, stats
