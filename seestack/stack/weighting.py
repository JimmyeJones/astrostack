"""
Frame quality weighting for the stack.

Each frame contributes to the final stack with a weight derived from its QC
metrics. Better frames (sharper, more stars, darker sky) get pulled more
heavily into the average; worse frames still contribute but less.

Formula (geometric mean of three sub-weights, each in [0.1, 1.0]):

  - ``fwhm_factor    = (best_fwhm / frame_fwhm)^2`` — favours sharp seeing.
  - ``stars_factor   = frame_stars / median_stars`` — penalises cloud-affected
    frames whose star count dropped.
  - ``sky_factor     = (median_sky / frame_sky)^0.5`` — mild penalty for
    very bright skies (moonlight, thin cloud).

Frames missing any metric get the neutral weight 1.0 for that factor (they
aren't penalised for things we couldn't measure). Frames with all three
metrics missing get weight 1.0 (i.e. behave like the unweighted stack).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from seestack.io.project import FrameRow

log = logging.getLogger(__name__)


@dataclass
class WeightingStats:
    """Summary diagnostics for the stack log."""

    n_weighted: int
    n_neutral: int
    min_weight: float
    max_weight: float
    median_weight: float


def compute_frame_weights(
    frames: list[FrameRow],
    *,
    min_weight: float = 0.1,
) -> tuple[dict[int, float], WeightingStats]:
    """
    Build a ``{frame_id: weight}`` map.

    ``min_weight`` is the floor — even very bad frames keep at least this much
    influence so a single bad metric doesn't completely zero out a frame.
    """
    fwhms = [f.fwhm_px for f in frames if f.fwhm_px is not None and f.fwhm_px > 0]
    stars = [f.star_count for f in frames if f.star_count is not None and f.star_count > 0]
    skies = [f.sky_adu_median for f in frames if f.sky_adu_median is not None and f.sky_adu_median > 0]

    best_fwhm = float(np.percentile(fwhms, 10)) if fwhms else None
    median_stars = float(np.median(stars)) if stars else None
    median_sky = float(np.median(skies)) if skies else None

    weights: dict[int, float] = {}
    weighted_list: list[float] = []
    n_neutral = 0
    for f in frames:
        if f.id is None:
            continue
        factors: list[float] = []

        if f.fwhm_px is not None and f.fwhm_px > 0 and best_fwhm is not None:
            factors.append(float(np.clip((best_fwhm / f.fwhm_px) ** 2, min_weight, 1.0)))
        if f.star_count is not None and median_stars is not None and median_stars > 0:
            factors.append(float(np.clip(f.star_count / median_stars, min_weight, 1.0)))
        if f.sky_adu_median is not None and median_sky is not None and median_sky > 0:
            factors.append(float(np.clip((median_sky / f.sky_adu_median) ** 0.5, min_weight, 1.0)))

        if not factors:
            weights[f.id] = 1.0
            n_neutral += 1
            continue

        # Geometric mean keeps the weight in [min_weight, 1.0] and is gentler
        # than a product when multiple factors are well below 1.
        w = float(np.exp(np.mean(np.log(factors))))
        weights[f.id] = w
        weighted_list.append(w)

    if weighted_list:
        stats = WeightingStats(
            n_weighted=len(weighted_list),
            n_neutral=n_neutral,
            min_weight=float(min(weighted_list)),
            max_weight=float(max(weighted_list)),
            median_weight=float(np.median(weighted_list)),
        )
    else:
        stats = WeightingStats(0, n_neutral, 1.0, 1.0, 1.0)
    return weights, stats


def unit_weights(frames: list[FrameRow]) -> dict[int, float]:
    """All frames get weight 1.0 — used when quality weighting is off."""
    return {f.id: 1.0 for f in frames if f.id is not None}
