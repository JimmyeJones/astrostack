"""Rank a user's finished stacks into an auto-curated "best pictures" portfolio.

The webapp's *My best pictures* wall gathers the newest finished stack of every
target across the Library and needs to show the strongest ones first, without any
knobs. :func:`rank_portfolio` is the pure, engine-side scorer behind that: given
one :class:`PortfolioEntry` per target (built from columns already stored on each
``stack_runs`` row), it returns them best-first by a **transparent quality proxy**
— a weighted blend of total integration time, background-noise σ (lower = cleaner),
frame count, and stacking coverage.

Kept engine-pure (no webapp imports) and free of any I/O so the webapp can build
:class:`PortfolioEntry` values however it likes and a unit test can pin the
ordering, tie-breaks, and old-run (missing-metric) fallbacks without a DB.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

__all__ = ["PortfolioEntry", "RankedEntry", "rank_portfolio", "PORTFOLIO_WEIGHTS"]


# How much each quality signal counts toward the score. Integration time is the
# single biggest driver of a good-looking beginner image, so it leads; noise and
# frame count matter next; coverage (how deeply frames overlap) is a light tie
# breaker. The weights need not sum to 1 — the score is always renormalised over
# whichever metrics an entry actually has, so an old run missing σ isn't penalised.
PORTFOLIO_WEIGHTS: dict[str, float] = {
    "exposure": 0.40,
    "frames": 0.25,
    "noise": 0.25,
    "coverage": 0.10,
}


@dataclass(frozen=True)
class PortfolioEntry:
    """One target's representative finished stack, reduced to the numbers the
    ranker needs. ``key`` is an opaque caller-supplied id (e.g. the target's safe
    name + run id) that the caller uses to map a :class:`RankedEntry` back to its
    full image record."""

    key: str
    # Frames combined into this stack (always known; ≥ 0).
    n_frames_used: int
    # Effective integration time in seconds, or None for a pre-schema-4 run.
    total_exposure_s: float | None = None
    # Normalised background-noise σ (lower = cleaner), or None when not measured
    # (pre-schema-6 / editor-export runs).
    noise_sigma: float | None = None
    # Peak stacking coverage (how many frames overlapped at the deepest pixel).
    coverage_max: int = 0


@dataclass(frozen=True)
class RankedEntry:
    """A scored portfolio entry. ``score`` is in [0, 1] (1 = best on every metric
    it carries, relative to the candidate set); ``key`` echoes the input's key."""

    key: str
    score: float


def _valid_positive(value: float | int | None) -> bool:
    """A metric counts only if it's a finite, strictly-positive number."""
    return value is not None and math.isfinite(value) and value > 0


def _subscores(
    entry: PortfolioEntry,
    *,
    max_exposure: float,
    max_frames: float,
    min_noise: float,
    max_coverage: float,
) -> dict[str, float]:
    """Per-metric [0, 1] sub-scores for one entry, relative to the candidate set.
    A metric the entry doesn't carry (or the set never has) is simply absent, so
    the weighted mean is taken over the metrics present."""
    scores: dict[str, float] = {}
    # Higher-is-better metrics: this value ÷ the best value in the set.
    if _valid_positive(entry.total_exposure_s) and max_exposure > 0:
        scores["exposure"] = min(1.0, entry.total_exposure_s / max_exposure)  # type: ignore[operator]
    if _valid_positive(entry.n_frames_used) and max_frames > 0:
        scores["frames"] = min(1.0, entry.n_frames_used / max_frames)
    if _valid_positive(entry.coverage_max) and max_coverage > 0:
        scores["coverage"] = min(1.0, entry.coverage_max / max_coverage)
    # Lower-is-better: the cleanest (smallest σ) scores 1.0, noisier ones less.
    if _valid_positive(entry.noise_sigma) and min_noise > 0:
        scores["noise"] = min(1.0, min_noise / entry.noise_sigma)  # type: ignore[operator]
    return scores


def _score(entry: PortfolioEntry, **maxes: float) -> float:
    """Weighted mean of an entry's available sub-scores, renormalised over just
    the metrics it carries (so a missing metric neither helps nor hurts)."""
    subs = _subscores(entry, **maxes)  # type: ignore[arg-type]
    total_weight = sum(PORTFOLIO_WEIGHTS[m] for m in subs)
    if total_weight <= 0:
        return 0.0
    return sum(PORTFOLIO_WEIGHTS[m] * s for m, s in subs.items()) / total_weight


def rank_portfolio(
    entries: Sequence[PortfolioEntry], *, limit: int | None = None
) -> list[RankedEntry]:
    """Rank finished stacks best-first by the transparent quality blend.

    Each metric is normalised against the best value present in ``entries`` (so
    the ranking is relative to the user's own collection, needing no absolute
    calibration), then blended by :data:`PORTFOLIO_WEIGHTS`. Entries missing a
    metric (e.g. an old run with no recorded σ) are scored over the metrics they
    do have, never penalised for the gap.

    Ordering is deterministic: by score descending, breaking ties by integration
    time, then frame count, then key — so the same collection always ranks the
    same way. ``limit`` (if given and ≥ 0) truncates to the top N; ``limit=0``
    returns an empty list.
    """
    if limit is not None and limit <= 0:
        return []
    if not entries:
        return []

    exposures = [e.total_exposure_s for e in entries if _valid_positive(e.total_exposure_s)]
    frames = [e.n_frames_used for e in entries if _valid_positive(e.n_frames_used)]
    coverages = [e.coverage_max for e in entries if _valid_positive(e.coverage_max)]
    noises = [e.noise_sigma for e in entries if _valid_positive(e.noise_sigma)]
    maxes = {
        "max_exposure": max(exposures) if exposures else 0.0,
        "max_frames": float(max(frames)) if frames else 0.0,
        "max_coverage": float(max(coverages)) if coverages else 0.0,
        "min_noise": min(noises) if noises else 0.0,
    }

    scored = [(e, _score(e, **maxes)) for e in entries]
    # One fully-deterministic pass: highest score first, breaking ties by
    # integration time, then frame count (both descending — negated), then key
    # ascending. Every tie-break is total, so the same collection never reshuffles.
    scored.sort(
        key=lambda es: (
            -es[1],
            -(es[0].total_exposure_s if _valid_positive(es[0].total_exposure_s) else -1.0),
            -es[0].n_frames_used,
            es[0].key,
        )
    )
    ranked = [RankedEntry(key=e.key, score=s) for e, s in scored]
    return ranked if limit is None else ranked[:limit]
