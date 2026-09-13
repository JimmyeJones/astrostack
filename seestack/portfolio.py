"""Rank a user's finished stacks into an auto-curated "best pictures" portfolio.

The webapp's *My best pictures* wall gathers the newest finished stack of every
target across the Library and needs to show the strongest ones first, without any
knobs. :func:`rank_portfolio` is the pure, engine-side scorer behind that: given
one :class:`PortfolioEntry` per target (built from columns already stored on each
``stack_runs`` row), it returns them best-first by a **transparent quality proxy**
— a weighted blend of integration time, background-noise σ (lower = cleaner),
frame count, and stacking coverage.

**Every one of those is read per pixel, because that is what a picture is.** A
run's integration time, frame count and peak coverage are all facts about the
*target*: on a mosaic the subs are spread across the raster, so the totals
describe the sum of the picture while the wall is ranking a *part* of it. The one
axis measured on the pixels themselves — σ — reads the per-pixel truth, so before
this the blend's two halves disagreed about the same picture: a 3×3 raster nine
subs deep in total scored as "nine frames" here while the Gallery card of the very
same run turned its frame badge orange for being one sub deep everywhere. The
scale is the run's own ``field_fulls`` (:mod:`webapp.field_fulls`) — the same
figure the Gallery card, the History integration trend and the readiness verdict
already read — so this wall cannot invent a second definition of "depth".
Identity on a single field, where the totals *are* the depth.

Kept engine-pure (no webapp imports) and free of any I/O so the webapp can build
:class:`PortfolioEntry` values however it likes and a unit test can pin the
ordering, tie-breaks, and old-run (missing-metric) fallbacks without a DB.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

__all__ = [
    "PortfolioEntry",
    "RankedEntry",
    "rank_portfolio",
    "per_pixel_total",
    "PORTFOLIO_WEIGHTS",
]


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
    # How many single-frame field-fulls of sky this picture's canvas covers
    # (``webapp.field_fulls.field_fulls_of_sky`` — canvas area ÷ one native
    # frame's area, drizzle divided out). It is the scale that turns this run's
    # *totals* into what one pixel of it actually received, and the same figure
    # the Gallery card, the History trend and the readiness verdict already read
    # per run, so this wall cannot invent a second definition of "depth".
    #
    # ``None`` / ≤ 1.0 means "no scaling" — a single field, a run whose frame
    # shape can't be read, and every caller that predates the field — which is,
    # byte for byte, what this ranker did before it existed.
    field_fulls: float | None = None
    # The user explicitly pinned this picture (it is its target's chosen "cover").
    # A pin is a *preference*, not a quality signal, so it never touches the
    # score — it only floats the entry ahead of the ranked tail so the automatic
    # ranking can't hide the one picture the user said was their favourite.
    pinned: bool = False


@dataclass(frozen=True)
class RankedEntry:
    """A scored portfolio entry. ``score`` is in [0, 1] (1 = best on every metric
    it carries, relative to the candidate set); ``key`` echoes the input's key.
    ``pinned`` echoes the input's pin so the caller can mark *why* an entry is
    where it is (the score alone wouldn't explain a floated favourite)."""

    key: str
    score: float
    pinned: bool = False


def _valid_positive(value: float | int | None) -> bool:
    """A metric counts only if it's a finite, strictly-positive number."""
    return value is not None and math.isfinite(value) and value > 0


def per_pixel_total(total: float, field_fulls: float | None) -> float:
    """A run *total* — frames combined, or seconds of integration — as the share
    one pixel of its canvas actually received.

    The Python twin of ``frontend/src/components/target/perPixel.perPixel``, and
    the same clamp: anything missing, non-finite or at or below 1.0 reads as
    **no scaling**, which is both the single-field answer and exactly what every
    caller did before the figure existed. A scale below one would *inflate* the
    apparent depth, which is the direction that hides the bug, so it is clamped
    rather than honoured — identically to ``field_fulls_of_sky`` itself.
    """
    if field_fulls is None or not math.isfinite(field_fulls) or field_fulls <= 1.0:
        return float(total)
    return float(total) / float(field_fulls)


def _entry_exposure(entry: PortfolioEntry) -> float | None:
    """This picture's integration time **per pixel**, or ``None`` when unmeasured."""
    if not _valid_positive(entry.total_exposure_s):
        return None
    return per_pixel_total(float(entry.total_exposure_s), entry.field_fulls)  # type: ignore[arg-type]


def _entry_frames(entry: PortfolioEntry) -> float | None:
    """How many subs landed on **one pixel** of this picture, or ``None``."""
    if not _valid_positive(entry.n_frames_used):
        return None
    return per_pixel_total(float(entry.n_frames_used), entry.field_fulls)


def _entry_coverage(entry: PortfolioEntry) -> float | None:
    """How deeply frames overlap on this picture, or ``None`` when unrecorded.

    ``coverage_max`` is the depth of the **deepest single pixel**, which on a
    single field is every pixel — the frame count — and on a mosaic is the
    corner where the panels happen to meet. On the bundled 2×2 sample that
    corner is covered by all 21 subs the target has while half the picture sits
    at 6, so the peak alone would score a thinly-shot raster as the deepest
    picture in the collection *and* set the yardstick every other entry is
    normalised against.

    So the peak is capped at what a typical pixel got (:func:`per_pixel_total`
    of the frame count — the same one scale the other two axes use, rather than
    a second source of "depth"). On a single field the two are the same number
    already, so this restores the identity a mosaic breaks instead of inventing
    a rule for it; and the cap can only ever lower a figure, never raise one.
    """
    if not _valid_positive(entry.coverage_max):
        return None
    peak = float(entry.coverage_max)
    depth = _entry_frames(entry)
    return peak if depth is None else min(peak, depth)


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
    # Higher-is-better metrics: this value ÷ the best value in the set. Every one
    # of the three is read **per pixel** (see :func:`per_pixel_total`), because
    # each is otherwise a claim about the whole target rather than about the
    # picture on the wall — identity on a single field.
    exposure = _entry_exposure(entry)
    frames = _entry_frames(entry)
    coverage = _entry_coverage(entry)
    if exposure is not None and max_exposure > 0:
        scores["exposure"] = min(1.0, exposure / max_exposure)
    if frames is not None and max_frames > 0:
        scores["frames"] = min(1.0, frames / max_frames)
    if coverage is not None and max_coverage > 0:
        scores["coverage"] = min(1.0, coverage / max_coverage)
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


def _sort_key(scored: tuple[PortfolioEntry, float]) -> tuple:
    """One fully-deterministic ordering: pinned favourites first (``not pinned``
    sorts False < True), then highest score, breaking ties by integration time,
    then frame count (both descending — negated), then key ascending. Both
    tie-breaks read the same **per-pixel** figures the score does, so a tie is
    broken by the picture rather than by the target."""
    entry, score = scored
    exposure = _entry_exposure(entry)
    return (
        not entry.pinned,
        -score,
        -(exposure if exposure is not None else -1.0),
        -(_entry_frames(entry) or 0.0),
        entry.key,
    )


def rank_portfolio(
    entries: Sequence[PortfolioEntry], *, limit: int | None = None
) -> list[RankedEntry]:
    """Rank finished stacks best-first by the transparent quality blend.

    Each metric is normalised against the best value present in ``entries`` (so
    the ranking is relative to the user's own collection, needing no absolute
    calibration), then blended by :data:`PORTFOLIO_WEIGHTS`. Entries missing a
    metric (e.g. an old run with no recorded σ) are scored over the metrics they
    do have, never penalised for the gap.

    Entries the user **pinned** (``PortfolioEntry.pinned`` — their target's chosen
    cover picture) sort ahead of every unpinned entry, ranked among themselves by
    the same blend. A pin is a stated preference, not a quality claim, so it never
    changes an entry's ``score``; it only guarantees the favourite survives
    ``limit`` instead of being cut by a wall of deeper stacks. With nothing pinned
    (the default) the ordering is byte-for-byte what it always was.

    Ordering is otherwise deterministic: by score descending, breaking ties by
    integration time, then frame count, then key — so the same collection always
    ranks the same way. ``limit`` (if given and ≥ 0) truncates to the top N;
    ``limit=0`` returns an empty list.
    """
    if limit is not None and limit <= 0:
        return []
    if not entries:
        return []

    # The yardsticks come off the *same* per-pixel readings the sub-scores do —
    # a peak that no picture is really at would otherwise normalise every other
    # entry against a depth nobody has.
    exposures = [v for v in (_entry_exposure(e) for e in entries) if v is not None]
    frames = [v for v in (_entry_frames(e) for e in entries) if v is not None]
    coverages = [v for v in (_entry_coverage(e) for e in entries) if v is not None]
    noises = [e.noise_sigma for e in entries if _valid_positive(e.noise_sigma)]
    maxes = {
        "max_exposure": max(exposures) if exposures else 0.0,
        "max_frames": max(frames) if frames else 0.0,
        "max_coverage": max(coverages) if coverages else 0.0,
        "min_noise": min(noises) if noises else 0.0,
    }

    scored = [(e, _score(e, **maxes)) for e in entries]
    # One fully-deterministic pass — see :func:`_sort_key`. Every tie-break is
    # total, so the same collection never reshuffles.
    scored.sort(key=_sort_key)
    ranked = [RankedEntry(key=e.key, score=s, pinned=e.pinned) for e, s in scored]
    return ranked if limit is None else ranked[:limit]
