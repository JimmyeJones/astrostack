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

**On a mosaic the three flux-like medians are taken per panel, not per target.**
Star count, sky level and transparency all measure *what the frame recorded*, so
on a mosaic they differ between panels for reasons that have nothing to do with
frame quality: a panel pointed at an emptier patch of sky genuinely has fewer,
fainter stars. Compared against the whole target that reads as cloud, and every
sub of that panel is demoted together — which does nothing where the panel is the
only data (a common scale factor cancels in a weighted mean) but does tilt the
*overlaps* it shares with its neighbours toward the neighbouring panel, thinning
and discolouring the joins. FWHM and eccentricity stay target-wide: seeing and
tracking are properties of the night, not of where you pointed. The split is
taken from :func:`~seestack.stack.pointings.panel_labels`, so a single-pointing
target — every ordinary stack — is byte-for-byte unchanged.
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
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from seestack.io.project import FrameRow
from seestack.stack.pointings import panel_labels

log = logging.getLogger(__name__)

# Fewest usable measurements a mosaic panel must carry before its *own* median is
# used as that metric's yardstick. Below it the panel falls back to the
# target-wide median — a median of one or two subs is noise, and being wrong in
# that direction is simply today's behaviour.
MIN_PANEL_MEASUREMENTS = 3


def panel_reference_medians(
    values: list[float | None],
    labels: list[int] | None,
    *,
    min_panel_measurements: int = MIN_PANEL_MEASUREMENTS,
) -> list[float | None]:
    """Per-frame median yardstick for one flux-like metric.

    Returns one reference value per input index: the median of the frame's own
    mosaic panel when that panel carries enough usable measurements, else the
    target-wide median. ``labels`` is ``None`` on any target that doesn't split
    into panels (see :func:`~seestack.stack.pointings.panel_labels`), which
    hands back the target-wide median for every frame — exactly what this has
    always done. Non-positive and missing values are ignored on both sides,
    matching the per-factor guards in :func:`compute_frame_weights`.
    """
    usable = [float(v) for v in values if v is not None and v > 0]
    overall = float(np.median(usable)) if usable else None
    if labels is None:
        return [overall] * len(values)

    buckets: dict[int, list[float]] = {}
    for value, label in zip(values, labels, strict=True):
        if label >= 0 and value is not None and value > 0:
            buckets.setdefault(label, []).append(float(value))
    per_panel = {
        label: float(np.median(vals))
        for label, vals in buckets.items()
        if len(vals) >= min_panel_measurements
    }
    return [
        per_panel.get(label, overall) if label >= 0 else overall
        for label in labels
    ]


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
    # Mosaic panels the flux-like metrics were compared *within* (0 = one
    # population, i.e. every ordinary single-pointing stack).
    n_panels: int = 0


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
    # Eccentricity 0 (perfectly round) is a valid, best-case measurement, so the
    # median includes it; the factor guards a 0 divisor per-frame instead.
    eccs = [f.eccentricity_median for f in frames
            if f.eccentricity_median is not None and f.eccentricity_median >= 0]

    best_fwhm = float(np.percentile(fwhms, 10)) if fwhms else None
    median_ecc = float(np.median(eccs)) if eccs else None

    # The three flux-like metrics get a per-panel yardstick on a mosaic (and the
    # target-wide one everywhere else) — see the module docstring.
    labels = panel_labels([(f.ra_center_deg, f.dec_center_deg) for f in frames])
    median_stars = panel_reference_medians([f.star_count for f in frames], labels)
    median_sky = panel_reference_medians([f.sky_adu_median for f in frames], labels)
    median_transp = panel_reference_medians(
        [f.transparency_score for f in frames], labels)
    n_panels = len({lab for lab in labels if lab >= 0}) if labels else 0

    weights: dict[int, float] = {}
    weighted_list: list[float] = []
    n_neutral = 0
    for i, f in enumerate(frames):
        if f.id is None:
            continue
        factors: list[float] = []
        ref_stars, ref_sky, ref_transp = (
            median_stars[i], median_sky[i], median_transp[i])

        if f.fwhm_px is not None and f.fwhm_px > 0 and best_fwhm is not None:
            factors.append(float(np.clip((best_fwhm / f.fwhm_px) ** 2, min_weight, 1.0)))
        if f.star_count is not None and ref_stars is not None and ref_stars > 0:
            factors.append(float(np.clip(f.star_count / ref_stars, min_weight, 1.0)))
        if (f.sky_adu_median is not None and f.sky_adu_median > 0
                and ref_sky is not None and ref_sky > 0):
            factors.append(float(np.clip((ref_sky / f.sky_adu_median) ** 0.5, min_weight, 1.0)))
        if (f.transparency_score is not None and f.transparency_score > 0
                and ref_transp is not None and ref_transp > 0):
            factors.append(float(np.clip(f.transparency_score / ref_transp, min_weight, 1.0)))
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
            n_panels=n_panels,
        )
    else:
        stats = WeightingStats(0, n_neutral, 1.0, 1.0, 1.0, n_panels=n_panels)
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
