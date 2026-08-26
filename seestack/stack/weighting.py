"""
Frame quality weighting for the stack.

Each frame contributes to the final stack with a weight derived from its QC
metrics. Better frames (sharper, more stars, darker sky) get pulled more
heavily into the average; worse frames still contribute but less.

Formula (geometric mean of up to five sub-weights, each in [0.1, 1.0]):

  - ``fwhm_factor         = (best_fwhm / frame_fwhm)^2`` — favours sharp seeing.
  - ``stars_factor        = frame_stars / median_stars`` — penalises
    cloud-affected frames whose star count dropped.
  - ``sky_factor          = (median_sky / frame_sky)^0.5`` — mild penalty for
    very bright skies (moonlight, thin cloud). Guards ``frame_sky <= 0`` (a
    black / corrupt sub, or a non-Seestar frame with no ADU pedestal) as
    neutral rather than dividing by it, symmetrically with the other factors.
  - ``transparency_factor = frame_transp / median_transp`` — penalises hazy /
    thin-cloud frames whose bright stars dimmed (the ``transparency_score`` is
    the median flux of a frame's brightest stars). Normalised against the
    *median of the frames being stacked*, i.e. within this one target, because
    the raw score isn't comparable across gain/exposure.
  - ``ecc_factor          = median_ecc / frame_ecc`` — penalises frames whose
    stars are more *elongated* than the run's median (tracking error, wind,
    a mount bump), symmetrically with the others: a frame with rounder-than-
    median stars caps at the neutral 1.0. Guards ``frame_ecc == 0`` (perfectly
    round — the best case) as neutral, and only applies when the run's median
    eccentricity is itself measurable (> 0). Captures star *shape*, where
    ``fwhm_factor`` captures star *size*, so the two aren't redundant.

Frames missing any metric get the neutral weight 1.0 for that factor (they
aren't penalised for things we couldn't measure). Frames with all metrics
missing get weight 1.0 (i.e. behave like the unweighted stack).

**Mosaics compare a panel against itself.** Three of those medians — stars,
sky and transparency — are over *position-dependent* metrics: a mosaic panel
aimed at an emptier patch of sky genuinely has fewer, fainter stars, and one
low over a light dome genuinely has a brighter sky. Taken target-wide across a
mosaic, ``stars_factor``/``transparency_factor`` clip at 1.0 and so can only
*penalise* that panel — measured at a **0.73× systematic weight** on a panel
whose only difference from its neighbour was its star field, which quietly
makes that panel a quarter shallower than the data it was given. So on a mosaic
those three medians are taken **per panel** (``group_by_pointing``, gated by
:func:`~seestack.stack.pointings.pointing_groups`), while FWHM and eccentricity
stay target-wide — seeing and tracking are properties of the *night*, not of
where you pointed. Exactly the split QC grading makes (``per_pointing``).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from seestack.io.project import FrameRow
from seestack.stack.pointings import pointing_groups

log = logging.getLogger(__name__)


@dataclass
class WeightingStats:
    """Summary diagnostics for the stack log."""

    n_weighted: int
    n_neutral: int
    min_weight: float
    max_weight: float
    median_weight: float
    # Frames actually pulled below full weight (weight < ~1.0) — the honest
    # "how many subs did weighting demote" figure surfaced in the run Info panel.
    n_downweighted: int = 0


# A panel needs at least this many subs carrying a metric before its own median
# is a trustworthy yardstick; below that the panel falls back to the target-wide
# one, the same shape the photometric pass uses.
_MIN_PANEL_FRAMES = 3

# Per-frame (stars, sky, transparency) medians — the position-dependent trio.
_PositionalMedians = dict[int, tuple[float | None, float | None, float | None]]


def _median_of(values: list[float]) -> float | None:
    return float(np.median(values)) if values else None


def _positional_medians(
    frames: list[FrameRow], *, group_by_pointing: bool,
) -> _PositionalMedians:
    """Each frame's yardstick for star count / sky level / transparency.

    Target-wide for a single-field target (and for a mosaic whose pointings
    don't split soundly) — identical to the medians this function replaced. Per
    **panel** on a mosaic that does split, because those three metrics are
    properties of where the scope pointed as much as of the sky; see the module
    docstring. A panel too thin to carry ``_MIN_PANEL_FRAMES`` of a metric falls
    back to the target-wide median for *that metric only*, so a sparse panel is
    still weighted rather than left unjudged.
    """
    wide = (
        _median_of([f.star_count for f in frames
                    if f.star_count is not None and f.star_count > 0]),
        _median_of([f.sky_adu_median for f in frames
                    if f.sky_adu_median is not None and f.sky_adu_median > 0]),
        _median_of([f.transparency_score for f in frames
                    if f.transparency_score is not None and f.transparency_score > 0]),
    )
    labels = pointing_groups(
        [(f.ra_center_deg, f.dec_center_deg) for f in frames],
        min_members=_MIN_PANEL_FRAMES,
    ) if group_by_pointing else None
    if labels is None:
        return {f.id: wide for f in frames if f.id is not None}

    buckets: dict[int, tuple[list[float], list[float], list[float]]] = {}
    for f, label in zip(frames, labels, strict=True):
        if label < 0:
            continue
        stars, skies, transps = buckets.setdefault(label, ([], [], []))
        if f.star_count is not None and f.star_count > 0:
            stars.append(float(f.star_count))
        if f.sky_adu_median is not None and f.sky_adu_median > 0:
            skies.append(float(f.sky_adu_median))
        if f.transparency_score is not None and f.transparency_score > 0:
            transps.append(float(f.transparency_score))
    per_label = {
        label: tuple(
            _median_of(vals) if len(vals) >= _MIN_PANEL_FRAMES else fallback
            for vals, fallback in zip(cols, wide, strict=True)
        )
        for label, cols in buckets.items()
    }
    return {
        f.id: per_label.get(label, wide)  # type: ignore[misc]
        for f, label in zip(frames, labels, strict=True)
        if f.id is not None
    }


def compute_frame_weights(
    frames: list[FrameRow],
    *,
    min_weight: float = 0.1,
    group_by_pointing: bool = False,
) -> tuple[dict[int, float], WeightingStats]:
    """
    Build a ``{frame_id: weight}`` map.

    ``min_weight`` is the floor — even very bad frames keep at least this much
    influence so a single bad metric doesn't completely zero out a frame.

    ``group_by_pointing`` (set by the stacker on a **mosaic** canvas) takes the
    star-count / sky / transparency medians per panel rather than target-wide —
    see the module docstring. It self-disables when the pointings don't split
    soundly, so a single-field target is unaffected either way.
    """
    fwhms = [f.fwhm_px for f in frames if f.fwhm_px is not None and f.fwhm_px > 0]
    # Eccentricity 0 (perfectly round) is a valid, best-case measurement, so the
    # median includes it; the factor guards a 0 divisor per-frame instead.
    eccs = [f.eccentricity_median for f in frames
            if f.eccentricity_median is not None and f.eccentricity_median >= 0]

    best_fwhm = float(np.percentile(fwhms, 10)) if fwhms else None
    median_ecc = float(np.median(eccs)) if eccs else None
    # The three position-dependent medians, per mosaic panel where the pointings
    # split soundly and target-wide otherwise (which is every single-field
    # target, and therefore byte-for-byte today's behaviour there).
    panel_medians = _positional_medians(frames, group_by_pointing=group_by_pointing)

    weights: dict[int, float] = {}
    weighted_list: list[float] = []
    n_neutral = 0
    for f in frames:
        if f.id is None:
            continue
        factors: list[float] = []

        if f.fwhm_px is not None and f.fwhm_px > 0 and best_fwhm is not None:
            factors.append(float(np.clip((best_fwhm / f.fwhm_px) ** 2, min_weight, 1.0)))
        median_stars, median_sky, median_transp = panel_medians[f.id]
        if f.star_count is not None and median_stars is not None and median_stars > 0:
            factors.append(float(np.clip(f.star_count / median_stars, min_weight, 1.0)))
        if (f.sky_adu_median is not None and f.sky_adu_median > 0
                and median_sky is not None and median_sky > 0):
            factors.append(float(np.clip((median_sky / f.sky_adu_median) ** 0.5, min_weight, 1.0)))
        if (f.transparency_score is not None and f.transparency_score > 0
                and median_transp is not None and median_transp > 0):
            factors.append(float(np.clip(f.transparency_score / median_transp, min_weight, 1.0)))
        if (f.eccentricity_median is not None and f.eccentricity_median > 0
                and median_ecc is not None and median_ecc > 0):
            factors.append(float(np.clip(median_ecc / f.eccentricity_median, min_weight, 1.0)))

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
            n_downweighted=sum(1 for w in weighted_list if w < 0.999),
        )
    else:
        stats = WeightingStats(0, n_neutral, 1.0, 1.0, 1.0)
    return weights, stats


def unit_weights(frames: list[FrameRow]) -> dict[int, float]:
    """All frames get weight 1.0 — used when quality weighting is off."""
    return {f.id: 1.0 for f in frames if f.id is not None}


def combine_weights_with_photometric(
    weights: dict[int, float],
    photometric_scales: dict[int, float] | None,
) -> dict[int, float]:
    """Fold photometric gain-matching into the *weighted-sum* combine weight.

    Photometric normalization multiplies a hazy frame's pixels by ``s`` (> 1) to
    gain-match its signal to the run's median — which multiplies that frame's
    per-pixel noise σ by the same ``s`` (scaling an image scales its noise).
    A minimum-variance (inverse-variance) combine weights a frame with noise
    ``s·σ`` by ``∝ 1/(s·σ)²``, so a photometrically-scaled frame carries an extra
    ``1/s²`` relative to an unscaled one. Without it a scaled-up hazy sub enters
    the mean trusting its *amplified* noise at close to full quality weight,
    raising the stacked background RMS more than an inverse-variance combine
    would; a scaled-*down* transparent sub (``s`` < 1, less noise) is
    symmetrically under-trusted.

    Returns ``weights`` **unchanged** (same object) when no photometric scaling is
    active, so a run with ``photometric_normalize`` off is byte-for-byte
    identical. Only the weighted-sum / κ-σ-pass-2 combine and the drizzle final
    weight-map should use these; the unweighted κ-σ pass-1 mean/σ, the min/max
    order statistic, and the drizzle *statistics* (clip-reference) pass keep the
    plain quality ``weights`` by design — they mirror the standard path, where the
    rejection reference is computed before the inverse-variance combine.
    """
    if not photometric_scales:
        return weights
    combined = dict(weights)
    for fid, s in photometric_scales.items():
        # A neutral (1.0) or unmeasurable scale leaves the frame's weight as-is;
        # only a genuinely applied scale carries the variance correction.
        if s and s > 0 and abs(s - 1.0) > 1e-9:
            combined[fid] = weights.get(fid, 1.0) / (s * s)
    return combined
