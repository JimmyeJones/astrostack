"""
Automatic frame-quality grading ("auto-grade").

QC measures five quality metrics per sub (FWHM, star count, sky level,
eccentricity, transparency) but — apart from satellite streaks — nothing acts
on them automatically: the user has to guess which metric to cut on and by how
much. This module turns those measurements into concrete, *explained*
recommendations: "these frames are statistical outliers versus the rest of
this target, and here's why in plain language".

Statistics
----------
Per metric we compute a robust modified z-score (Iglewicz & Hoaglin):

    z = 0.6745 · (x − median) / MAD

falling back to the mean absolute deviation about the median
(``z = (x − median) / (1.2533 · meanAD)``) when MAD is zero (e.g. half the
frames share one value), and skipping the metric entirely when both scales are
zero. Median/MAD are used instead of mean/σ so the bad frames being hunted
can't inflate the yardstick they're measured against.

Two deliberate choices:

- **Direction-aware, one-sided.** Only the *bad* direction flags: high FWHM /
  eccentricity / sky, low star count / transparency. A frame that is unusually
  *sharp* or has an unusually *dark* sky is never recommended for rejection.
- **Log domain for flux-like metrics.** Cloud and haze act multiplicatively
  (they halve star counts, double sky levels), so star count, sky level and
  transparency are graded on ``log(x)``; FWHM and eccentricity stay linear.

Safety rails
------------
- A metric is only graded when at least ``min_frames`` frames carry it —
  robust statistics over a handful of points are noise.
- At most ``max_reject_fraction`` of the considered frames are ever
  recommended (worst offenders kept, by z-score). Auto-grade must never nuke
  half a library, no matter how pathological the distribution.
- Frames the user explicitly graded (``user_override``) are never recommended;
  their metrics still inform the population statistics (they will stack).

This module only *recommends*; ``apply_grade_report`` writes rejections with
reason ``auto:grade:<metric>`` and — like ``auto:streak`` — does **not** set
``user_override``, so a machine decision never masquerades as a human one and
the user can freely re-accept.

Reconsidering old machine decisions
-----------------------------------
A live Seestar target drips subs, so the unattended hook re-grades it on every
scan. A frame rejected **early** — graded against a tiny, noisy population whose
median/MAD are unstable — used to stay rejected forever, even once hundreds of
good subs made it plainly typical. ``grade_frames`` therefore takes an optional
``reconsider`` list: the target's own ``auto:grade`` rejects (never a user
decision). They rejoin the population *and* the considered set exactly as if
accepted, so one deterministic pass over that stable set decides **both**
directions — the frames it flags are the true outliers against the whole night
(reject / stay rejected), and every reconsidered frame it does *not* flag comes
back in ``GradeReport.re_accept``.

Grading over that combined set is what makes the decision a fixed point rather
than a ratchet: the set is invariant under auto-grade's own accept/reject moves
(a frame only ever moves *between* its two halves), so the same recommendations
come out every scan and a frame can't reject → re-accept → reject churn. It also
makes the ``max_reject_fraction`` rail cumulative for free — the cap is measured
against the original considered population, not against a shrinking survivor set.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field, replace
from pathlib import Path

from seestack.io.project import FrameRow

log = logging.getLogger(__name__)

# Modified-z thresholds per sensitivity. 3.5 is the classic Iglewicz–Hoaglin
# recommendation; conservative/aggressive bracket it for cautious users and
# messy skies respectively.
SENSITIVITY_THRESHOLDS: dict[str, float] = {
    "conservative": 5.0,
    "balanced": 3.5,
    "aggressive": 2.5,
}
DEFAULT_SENSITIVITY = "balanced"

# Grade a metric only when this many frames carry it — below that the robust
# scale estimate is unreliable and "reject worst by %" is the honest tool.
MIN_FRAMES_FOR_GRADING = 10

# Never recommend rejecting more than this fraction of the considered frames.
MAX_REJECT_FRACTION = 0.25

# z-scores are capped here so they stay finite (and therefore JSON-safe) even
# for the "star count is zero through solid cloud" case where the log-domain
# deviation is unbounded.
_Z_MAX = 999.0

_HIGH, _LOW = "high", "low"  # which direction of deviation is bad


@dataclass(frozen=True)
class _MetricSpec:
    """How one QC metric is graded.

    ``min_ratio`` / ``min_delta`` are **practical-significance floors**: on a
    very stable night the robust scale (MAD) collapses, and a purely
    statistical cut would flag deviations that are real but cosmetically
    meaningless (FWHM 3.2 px vs 3.0 px). A frame is only recommended when it
    is *both* a statistical outlier *and* worse by at least this much — ratio
    in the bad direction (``worse/typical`` or ``typical/worse``), or an
    absolute delta for eccentricity, whose typical value sits near zero and
    makes ratios unstable.
    """

    attr: str
    bad_dir: str
    log_domain: bool
    label: str
    min_ratio: float | None = None
    min_delta: float | None = None


_METRICS: list[_MetricSpec] = [
    # ≥25% softer than typical: visibly degrades the stack's resolution.
    _MetricSpec("fwhm_px", _HIGH, False, "FWHM", min_ratio=1.25),
    # +0.15 eccentricity: clearly elongated stars, not measurement wobble.
    _MetricSpec("eccentricity_median", _HIGH, False, "eccentricity", min_delta=0.15),
    # ≥1.5× brighter sky: cloud/moon/twilight, not normal sky drift.
    _MetricSpec("sky_adu_median", _HIGH, True, "sky level", min_ratio=1.5),
    # ≥30% of the stars gone: cloud, not detection jitter.
    _MetricSpec("star_count", _LOW, True, "star count", min_ratio=1.0 / 0.7),
    # Bright stars ≥30% dimmer: haze/thin cloud.
    _MetricSpec("transparency_score", _LOW, True, "transparency", min_ratio=1.0 / 0.7),
]

METRIC_LABELS: dict[str, str] = {m.attr: m.label for m in _METRICS}


def _reason_text(metric: str, value: float, typical: float) -> str:
    """Plain-language explanation a beginner can act on."""
    if metric == "fwhm_px":
        return (f"much softer than typical (FWHM {value:.1f} px vs "
                f"{typical:.1f} px) — poor seeing, focus drift or cloud")
    if metric == "eccentricity_median":
        return (f"stars clearly elongated ({value:.2f} vs {typical:.2f}) — "
                f"wind shake or tracking error")
    if metric == "sky_adu_median":
        return (f"sky much brighter than typical ({value:.0f} vs "
                f"{typical:.0f} ADU) — cloud, moonlight or twilight")
    if metric == "star_count":
        return (f"far fewer stars than typical ({value:.0f} vs "
                f"{typical:.0f}) — likely cloud")
    if metric == "transparency_score":
        return ("bright stars much dimmer than typical — haze or thin cloud")
    return f"outlier on {metric} ({value:g} vs {typical:g})"


@dataclass
class GradeReason:
    """Why one frame was flagged on one metric."""

    metric: str
    value: float
    typical: float  # population median, linear domain
    z: float        # modified z-score in the bad direction (≥ threshold)
    label: str


@dataclass
class FrameGrade:
    """One frame recommended for rejection, with every reason that fired."""

    frame_id: int
    name: str
    reasons: list[GradeReason]  # sorted worst-first

    @property
    def worst_z(self) -> float:
        return self.reasons[0].z if self.reasons else 0.0

    @property
    def primary_metric(self) -> str:
        return self.reasons[0].metric if self.reasons else "unknown"


@dataclass
class GradeReport:
    """Everything the UI (and the apply step) needs about one grading pass."""

    sensitivity: str
    threshold: float
    n_accepted: int
    n_considered: int  # accepted frames eligible for a recommendation
    recommendations: list[FrameGrade] = field(default_factory=list)
    metrics_used: list[str] = field(default_factory=list)
    metrics_skipped: dict[str, str] = field(default_factory=dict)
    capped: bool = False  # the MAX_REJECT_FRACTION rail truncated the list
    # Ids from ``reconsider`` this pass did **not** flag: previously
    # auto-rejected frames the now-larger population no longer calls outliers,
    # so ``apply_grade_report`` puts them back. Always empty when no
    # ``reconsider`` list was given (every existing caller).
    re_accept: list[int] = field(default_factory=list)


def _median(values: list[float]) -> float:
    s = sorted(values)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else 0.5 * (s[mid - 1] + s[mid])


def _robust_scale(values: list[float], med: float) -> float | None:
    """MAD-based scale for the modified z-score; meanAD fallback when MAD is
    zero; None when the sample carries no spread at all (skip the metric)."""
    abs_dev = [abs(v - med) for v in values]
    mad = _median(abs_dev)
    if mad > 0:
        return mad / 0.6745
    mean_ad = sum(abs_dev) / len(abs_dev)
    if mean_ad > 0:
        return 1.253314 * mean_ad
    return None


def _practically_worse(spec: _MetricSpec, value: float, typical: float) -> bool:
    """Is ``value`` worse than ``typical`` by at least the spec's floor?

    Statistical significance alone isn't enough: on a rock-stable night the
    MAD collapses and tiny, harmless deviations become huge z-scores. This
    gate keeps auto-grade trustworthy — it only ever names frames that are
    *meaningfully* worse, no matter how tight the distribution is.
    """
    if spec.min_delta is not None:
        if spec.bad_dir == _HIGH:
            return value - typical >= spec.min_delta
        return typical - value >= spec.min_delta
    if spec.min_ratio is not None and typical > 0 and value > 0:
        ratio = (value / typical) if spec.bad_dir == _HIGH else (typical / value)
        return ratio >= spec.min_ratio
    return True  # no floor configured — statistics alone decide


def grade_frames(
    frames: list[FrameRow],
    *,
    sensitivity: str = DEFAULT_SENSITIVITY,
    min_frames: int = MIN_FRAMES_FOR_GRADING,
    max_reject_fraction: float = MAX_REJECT_FRACTION,
    reconsider: list[FrameRow] | None = None,
) -> GradeReport:
    """
    Grade a target's accepted frames and recommend statistical outliers for
    rejection. Pure function over frame rows — no I/O.

    ``frames`` should be the target's **accepted** frames (they define the
    population that would stack). Frames with ``user_override`` set inform the
    statistics but are never recommended — the user's decision stands.

    ``reconsider`` (optional) is the target's own previously ``auto:grade``-
    rejected frames. They are graded exactly as if accepted — they rejoin both
    the population statistics and the considered set — so this one pass decides
    both directions over a stable set (see the module docstring). Any of them the
    pass does *not* flag is reported in :attr:`GradeReport.re_accept`; any it
    does flag simply stays rejected (it is listed in ``recommendations``, and
    ``apply_grade_report`` leaves an already-rejected frame alone). A
    ``user_override`` or id-less entry is ignored — a user decision is never
    reconsidered.
    """
    if sensitivity not in SENSITIVITY_THRESHOLDS:
        raise ValueError(
            f"unknown sensitivity {sensitivity!r} "
            f"(expected one of {sorted(SENSITIVITY_THRESHOLDS)})"
        )
    threshold = SENSITIVITY_THRESHOLDS[sensitivity]

    # Reconsidered frames join the population as accepted candidates. Copy rather
    # than mutate — these rows come straight from the caller's DB read.
    seen_ids = {f.id for f in frames if f.id is not None}
    reconsidered = [
        f if f.accept else replace(f, accept=True)
        for f in (reconsider or [])
        if f.id is not None and not f.user_override and f.id not in seen_ids
    ]
    reconsidered_ids = {f.id for f in reconsidered}
    if reconsidered:
        frames = list(frames) + reconsidered

    accepted = [f for f in frames if f.accept]
    considered = [f for f in accepted if f.id is not None and not f.user_override]
    report = GradeReport(
        sensitivity=sensitivity,
        threshold=threshold,
        n_accepted=len(accepted),
        n_considered=len(considered),
    )

    # Reasons per frame id, accumulated across metrics.
    reasons: dict[int, list[GradeReason]] = {}
    names: dict[int, str] = {}

    for spec in _METRICS:
        metric = spec.attr
        # Population = every accepted frame carrying the metric (log metrics
        # need strictly positive values to transform).
        pop = [
            float(getattr(f, metric))
            for f in accepted
            if getattr(f, metric) is not None
            and math.isfinite(float(getattr(f, metric)))
            and (not spec.log_domain or float(getattr(f, metric)) > 0)
        ]
        if len(pop) < min_frames:
            report.metrics_skipped[metric] = (
                f"only {len(pop)} of {len(accepted)} accepted frames carry "
                f"this metric (need {min_frames})"
            )
            continue
        domain = [math.log(v) for v in pop] if spec.log_domain else pop
        med_d = _median(domain)
        scale = _robust_scale(domain, med_d)
        if scale is None:
            report.metrics_skipped[metric] = "no spread — every frame is identical"
            continue
        med_linear = math.exp(med_d) if spec.log_domain else med_d

        report.metrics_used.append(metric)
        for f in considered:
            raw = getattr(f, metric)
            if raw is None or not math.isfinite(float(raw)):
                continue
            value = float(raw)
            if spec.log_domain and value <= 0:
                # log undefined. A non-positive value on a low-is-bad metric
                # (e.g. star_count == 0 through cloud) is maximally bad; on a
                # high-is-bad metric it's harmless — skip it.
                if spec.bad_dir != _LOW:
                    continue
                z = _Z_MAX
            else:
                x = math.log(value) if spec.log_domain else value
                dev = (x - med_d) if spec.bad_dir == _HIGH else (med_d - x)
                z = min(dev / scale, _Z_MAX)
                if z >= threshold and not _practically_worse(spec, value, med_linear):
                    continue  # statistically odd but cosmetically fine
            if z >= threshold and f.id is not None:
                reasons.setdefault(f.id, []).append(GradeReason(
                    metric=metric,
                    value=value,
                    typical=med_linear,
                    z=z,
                    label=_reason_text(metric, value, med_linear),
                ))
                names[f.id] = Path(f.source_path).name if f.source_path else f"frame {f.id}"

    recs = []
    for fid, rs in reasons.items():
        rs.sort(key=lambda r: r.z, reverse=True)
        recs.append(FrameGrade(frame_id=fid, name=names[fid], reasons=rs))
    # Worst-first, then by frame id so the order — and therefore which frames the
    # cap below keeps — never depends on the order the caller happened to hand
    # the rows in. That determinism is what makes the ``reconsider`` pass a fixed
    # point: a reconsidered frame arrives at the end of ``considered``, so a
    # z-score tie at the cap boundary would otherwise flip a frame in and out
    # between scans.
    recs.sort(key=lambda g: (-g.worst_z, g.frame_id))

    # Safety rail: never recommend more than the cap, keep the worst offenders.
    cap = max(1, int(len(considered) * max_reject_fraction)) if considered else 0
    if len(recs) > cap:
        report.capped = True
        recs = recs[:cap]
        log.info(
            "Auto-grade capped recommendations to %d of %d flagged frames "
            "(%.0f%% rail)", cap, len(reasons), max_reject_fraction * 100,
        )
    report.recommendations = recs
    # Every reconsidered frame the pass didn't end up recommending comes back.
    # Read off the *post-cap* list deliberately: the cap is part of the same
    # deterministic decision over the (invariant) combined set, so a frame the
    # rail keeps out is kept out every scan too — re-accepting it is stable, not
    # a step in a reject↔accept oscillation.
    if reconsidered_ids:
        flagged = {g.frame_id for g in recs}
        report.re_accept = sorted(reconsidered_ids - flagged)
    return report


def best_frame(frames: list[FrameRow]) -> FrameRow | None:
    """Pick the single sharpest accepted sub for an at-a-glance "first look".

    Ranks by sharpness first (**lowest FWHM** — the most direct proxy for a
    well-focused, steady sub), tie-broken by **star count** (more detected stars
    = better focus/transparency), then by frame id for a stable, deterministic
    result. Only *accepted* frames carrying a finite FWHM are eligible, so the
    pick reflects a QC'd sub the stack would actually use; a frame the user set
    aside is never offered as the night's best look.

    Returns ``None`` when no accepted frame carries a usable FWHM yet (nothing is
    QC'd), so the caller can show its pre-QC empty state rather than a bogus pick.
    Pure function over frame rows — no I/O.
    """
    def stars(f: FrameRow) -> float:
        s = f.star_count
        return float(s) if s is not None and math.isfinite(float(s)) else -1.0

    eligible = [
        f for f in frames
        if f.accept and f.id is not None
        and f.fwhm_px is not None and math.isfinite(float(f.fwhm_px))
    ]
    if not eligible:
        return None
    # min() over (FWHM asc, stars desc, id asc): sharpest, then most stars, then
    # the earliest id as a stable deterministic tiebreak.
    return min(eligible, key=lambda f: (float(f.fwhm_px), -stars(f), f.id))


def apply_grade_report(project, report: GradeReport) -> list[int]:
    """
    Reject the recommended frames in ``project``. Returns the ids actually
    changed (so the caller can offer an undo).

    Re-checks each frame's *current* state at apply time: a frame the user
    graded (``user_override``) or already rejected since the report was built
    is left untouched. ``user_override`` stays False — this is a machine
    decision (same convention as ``auto:streak``), so the user can re-accept
    and future automation still respects them.
    """
    changed: list[int] = []
    for rec in report.recommendations:
        f = project.get_frame(rec.frame_id)
        if f is None or not f.accept or f.user_override:
            continue
        project.update_frame(
            rec.frame_id,
            accept=False,
            reject_reason=f"auto:grade:{rec.primary_metric}",
        )
        changed.append(rec.frame_id)
    return changed


def apply_grade_reaccepts(project, report: GradeReport) -> list[int]:
    """
    Put back the frames in ``report.re_accept`` — previously auto-graded rejects
    the now-larger population no longer flags. Returns the ids actually changed.

    Kept separate from :func:`apply_grade_report` so the two directions stay
    independently reportable (and so every existing caller's return shape is
    unchanged). Like the reject step it re-checks each frame's *current* state:
    only a frame that is still rejected, still carries an ``auto:grade`` reason,
    and still has no ``user_override`` is touched — so a rejection the user made
    (or a streak/QC rejection, a different decision entirely) is never undone by
    automation. Empty ``re_accept`` (every caller that passes no ``reconsider``
    list) is a no-op.
    """
    changed: list[int] = []
    for fid in report.re_accept:
        f = project.get_frame(fid)
        if f is None or f.accept or f.user_override:
            continue
        if not (f.reject_reason or "").startswith("auto:grade"):
            continue
        project.update_frame(fid, accept=True, reject_reason=None)
        changed.append(fid)
    return changed
