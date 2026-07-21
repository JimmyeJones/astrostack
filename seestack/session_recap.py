"""A friendly, plain-language recap of a target's most recent capture session.

The north-star loop is *drop a night's subs, walk away, come back to a result*.
On return, the first thing a beginner wants to know is **"what did last night
give me?"** — but that answer is scattered across the Jobs summary (transient),
the frame table, and the reject tally. This module gathers it into one small,
persistent summary built entirely from data already on disk: how many subs the
last session added, how much was kept vs. set aside (and *why*, in plain
buckets), and how much total integration the target now has.

Pure, offline, read-only — it just aggregates the project's ``frames`` rows, so
it never guesses and needs no network. A "session" is defined by clustering
frames on their **capture** time (``timestamp_utc``): a night's subs are minutes
apart, and the gap to the previous night is hours, so the trailing run of frames
separated from the rest by more than ``gap_hours`` is "the last session". This
groups a night that spans UTC midnight together and is robust to timezone.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from statistics import median

from seestack.io.project import FrameRow, Project

# A night's subs land minutes apart; the gap to the previous night is many hours.
# Six hours cleanly separates two nights without splitting a single long session.
DEFAULT_SESSION_GAP_HOURS = 6.0

# Cross-session quality-drift nudge (see ``session_quality_drift``). Auto-grade is
# relative *within* a session, so a whole night shot soft/out-of-focus passes every
# frame; this catches it by comparing the newest session's median FWHM against the
# target's best prior session. Deliberately conservative — it must clear BOTH a
# relative and an absolute floor — so it never nags on ordinary night-to-night
# seeing wobble, only a materially worse whole session.
SESSION_QUALITY_MIN_FRAMES = 4      # need this many measured subs per session to trust its median
FWHM_DRIFT_RATIO = 1.25             # newest ≥ 25% softer than the best prior session, AND
FWHM_DRIFT_ABS_PX = 0.6             # ≥ 0.6 px worse in absolute terms — both must hold

# Map a raw ``reject_reason`` to a plain-language bucket a beginner understands.
# Ordered, substring-matched (the raw reasons are ``auto:grade:<metric>``,
# ``auto:streak``, ``bulk:streaked``/``bulk:trailed``, ``qc_error``, ``user`` …).
_REJECT_BUCKETS: list[tuple[tuple[str, ...], str]] = [
    (("streak", "trail"), "trailed"),
    (("sky", "transparency"), "cloudy"),
    (("fwhm", "eccentric", "star_count", "grade"), "soft"),
    (("qc_error", "error", "unreadable"), "unreadable"),
    (("user",), "set aside by you"),
]


def bucket_reject_reason(reason: str | None) -> str:
    """Collapse a raw ``reject_reason`` into a plain bucket (``trailed`` /
    ``cloudy`` / ``soft`` / ``unreadable`` / ``set aside by you`` / ``other``).
    A NULL reason bucketed under ``set aside by you`` — a manual reject with no
    explicit reason is recorded that way elsewhere (``reject_reason_counts``)."""
    if not reason:
        return "set aside by you"
    low = reason.lower()
    for needles, label in _REJECT_BUCKETS:
        if any(n in low for n in needles):
            return label
    return "other"


@dataclass
class SessionQualityDrift:
    """A gentle heads-up that the most recent session is materially *softer* than
    the target's best previous session — a whole-session quality dip (e.g. a night
    shot slightly out of focus or through thin haze) that auto-grade, which only
    compares frames *within* a session, structurally can't see. Purely
    informational: it never rejects anything, it just tells the user to check."""

    kind: str            # which metric drifted — currently always "fwhm"
    latest_fwhm_px: float    # newest session's median FWHM (higher = softer)
    baseline_fwhm_px: float  # best prior session's median FWHM
    n_latest: int            # measured subs behind the newest median
    n_baseline: int          # measured subs behind the baseline median


@dataclass
class SessionRecap:
    """What the most recent capture session brought in, and where the target
    stands now. Times are ISO 8601 UTC strings (as stored on the frames)."""

    n_frames: int                       # subs captured this session (kept + set aside)
    n_kept: int                         # accepted this session
    n_set_aside: int                    # rejected this session
    session_exposure_s: float           # Σ exposure of every sub this session
    kept_exposure_s: float              # Σ exposure of the kept subs this session
    total_kept_exposure_s: float        # Σ exposure of every accepted sub, all sessions
    start_utc: str | None               # earliest capture time this session
    end_utc: str | None                 # latest capture time this session
    reject_buckets: dict[str, int] = field(default_factory=dict)  # plain bucket → count
    quality_drift: SessionQualityDrift | None = None  # cross-session softness nudge, or None


def _parse(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        # Python 3.11+ fromisoformat accepts a trailing 'Z'; be defensive anyway.
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    # Coerce a tz-naive parse to UTC so the session-splitting sort/subtraction is
    # always well-defined. Every writer stores tz-aware UTC today, but the
    # ``fits_loader._parse_timestamp`` fallback can persist an unnormalised header
    # value (e.g. a date-only ``DATE-OBS``), and mixing naive + aware datetimes in
    # one project would otherwise raise "can't compare offset-naive and aware".
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _split_sessions(
    frames: list[tuple[datetime, FrameRow]], gap_hours: float
) -> list[list[tuple[datetime, FrameRow]]]:
    """Partition (capture-time, frame) pairs sorted ascending into sessions,
    starting a new session wherever consecutive captures are more than
    ``gap_hours`` apart. Returns a list of sessions, oldest first."""
    if not frames:
        return []
    gap_s = gap_hours * 3600.0
    sessions: list[list[tuple[datetime, FrameRow]]] = [[frames[0]]]
    for i in range(1, len(frames)):
        prev_dt, _ = frames[i - 1]
        this_dt, _ = frames[i]
        if (this_dt - prev_dt).total_seconds() <= gap_s:
            sessions[-1].append(frames[i])
        else:
            sessions.append([frames[i]])
    return sessions


def _last_session_frames(
    frames: list[tuple[datetime, FrameRow]], gap_hours: float
) -> list[tuple[datetime, FrameRow]]:
    """Given (capture-time, frame) pairs sorted ascending, return the trailing
    run whose consecutive capture times are within ``gap_hours`` of each other —
    i.e. the most recent night's frames."""
    sessions = _split_sessions(frames, gap_hours)
    return sessions[-1] if sessions else []


def last_session_frames(
    frames: list[FrameRow], *, gap_hours: float = DEFAULT_SESSION_GAP_HOURS
) -> list[FrameRow]:
    """The frames of a target's most recent capture session, in capture order.

    A convenience wrapper over the session split: parses each frame's capture
    time, drops undatable frames, and returns the trailing ``gap_hours``-separated
    cluster. Used to trim a target down to just its latest night before combining
    it across the library (see :func:`library_session_recap`) so the caller never
    has to hold every target's full frame list at once."""
    dated = [(dt, f) for f in frames if (dt := _parse(f.timestamp_utc)) is not None]
    if not dated:
        return []
    dated.sort(key=lambda pair: pair[0])
    return [f for _dt, f in _last_session_frames(dated, gap_hours)]


# A generous ceiling on a single capture night's span. The library "last night"
# cut is made *precisely* by the ≤``gap_hours`` trailing-cluster walk over the
# merged cross-target timeline (see :func:`library_session_recap`); this window is
# only a memory bound on how many of each target's frames we carry into that
# merge. It must be wide enough to never sever a night that another target bridges
# — a real dusk-to-dawn run is well under this — yet small enough that we never
# hold a target's whole history. So a frame older than this before the target's
# *own* latest capture cannot belong to the same night and is safely dropped.
LAST_NIGHT_WINDOW_HOURS = 30.0


def recent_session_window_frames(
    frames: list[FrameRow], *, window_hours: float = LAST_NIGHT_WINDOW_HOURS
) -> list[FrameRow]:
    """Trim ``frames`` to those captured within ``window_hours`` of the target's
    *own* latest capture — a memory bound for the cross-target
    :func:`library_session_recap` merge.

    Unlike :func:`last_session_frames`, this does **not** cut at the target's own
    ``gap_hours`` session boundary: a target imaged early in a night and revisited
    near dawn (a >6 h internal gap) keeps *both* batches, so when another target
    shot in between bridges the gap, the early batch isn't wrongly dropped before
    the merge. The precise "last night" cut is left to the merged-timeline gap
    walk; this only ensures every frame that could belong to it survives. Returns
    the datable in-window frames; ``[]`` when none carry a capture timestamp."""
    dated = [(dt, f) for f in frames if (dt := _parse(f.timestamp_utc)) is not None]
    if not dated:
        return []
    latest = max(dt for dt, _ in dated)
    cutoff = latest - timedelta(hours=window_hours)
    return [f for dt, f in dated if dt >= cutoff]


def _session_median_fwhm(
    session_pairs: list[tuple[datetime, FrameRow]]
) -> tuple[float | None, int]:
    """Median FWHM over the session's *accepted*, measured subs (the ones that
    actually feed the stack), or ``(None, 0)`` when too few carry a usable FWHM."""
    vals = [
        f.fwhm_px
        for _dt, f in session_pairs
        if f.accept and f.fwhm_px is not None and f.fwhm_px > 0
    ]
    if len(vals) < SESSION_QUALITY_MIN_FRAMES:
        return None, 0
    return float(median(vals)), len(vals)


def _fwhm_quality_drift(
    sessions: list[list[tuple[datetime, FrameRow]]]
) -> SessionQualityDrift | None:
    """Compare the newest session's median FWHM against the *best* (sharpest)
    prior session and flag a materially softer newest session. Needs at least two
    sessions each with enough measured subs; returns ``None`` otherwise or when
    the drift doesn't clear both the relative and absolute floors."""
    if len(sessions) < 2:
        return None
    latest_fwhm, n_latest = _session_median_fwhm(sessions[-1])
    if latest_fwhm is None:
        return None
    best: tuple[float, int] | None = None
    for prior in sessions[:-1]:
        med, n = _session_median_fwhm(prior)
        if med is None:
            continue
        if best is None or med < best[0]:
            best = (med, n)
    if best is None:
        return None
    baseline_fwhm, n_baseline = best
    softer_enough = (
        latest_fwhm >= baseline_fwhm * FWHM_DRIFT_RATIO
        and latest_fwhm - baseline_fwhm >= FWHM_DRIFT_ABS_PX
    )
    if not softer_enough:
        return None
    return SessionQualityDrift(
        kind="fwhm",
        latest_fwhm_px=latest_fwhm,
        baseline_fwhm_px=baseline_fwhm,
        n_latest=n_latest,
        n_baseline=n_baseline,
    )


def session_recap(
    project: Project, *, gap_hours: float = DEFAULT_SESSION_GAP_HOURS
) -> SessionRecap | None:
    """Summarise the target's most recent capture session, or ``None`` when
    there's nothing datable to report (no frames carry a capture timestamp).

    Read-only aggregation over the ``frames`` table — safe to call any time.
    """
    dated: list[tuple[datetime, FrameRow]] = []
    total_kept_exposure_s = 0.0
    for f in project.iter_frames():
        if f.accept:
            total_kept_exposure_s += f.exposure_s or 0.0
        dt = _parse(f.timestamp_utc)
        if dt is not None:
            dated.append((dt, f))

    if not dated:
        return None

    dated.sort(key=lambda pair: pair[0])
    sessions = _split_sessions(dated, gap_hours)
    session_pairs = sessions[-1] if sessions else []
    if not session_pairs:
        return None

    session = [f for _dt, f in session_pairs]
    kept = [f for f in session if f.accept]
    set_aside = [f for f in session if not f.accept]
    buckets: dict[str, int] = {}
    for f in set_aside:
        b = bucket_reject_reason(f.reject_reason)
        buckets[b] = buckets.get(b, 0) + 1

    # session_pairs is a contiguous trailing slice of ``dated`` (sorted ascending),
    # so the first/last carry the session's span.
    return SessionRecap(
        n_frames=len(session),
        n_kept=len(kept),
        n_set_aside=len(set_aside),
        session_exposure_s=sum(f.exposure_s or 0.0 for f in session),
        kept_exposure_s=sum(f.exposure_s or 0.0 for f in kept),
        total_kept_exposure_s=total_kept_exposure_s,
        start_utc=session_pairs[0][1].timestamp_utc,
        end_utc=session_pairs[-1][1].timestamp_utc,
        reject_buckets=buckets,
        quality_drift=_fwhm_quality_drift(sessions),
    )


# ---------------------------------------------------------------------------
# "Focus & sharpness through the night" — a per-frame FWHM-vs-time trend for the
# target's most recent capture session, so a beginner can see at a glance whether
# their stars stayed sharp all night or drifted soft partway through (dew on the
# lens, temperature/focus drift — a common Seestar failure on a long unattended
# run). Read-only aggregation over the same session split; every number comes from
# the frames table (``fwhm_px`` + ``timestamp_utc``), so it needs no new capture
# step and no pixels. Distinct from the cross-session drift nudge (whole-night vs
# a prior night) — this is the shape of sharpness *within* the latest night.
# ---------------------------------------------------------------------------

# Need at least this many measured, accepted subs in the session to draw a trend
# worth reading — fewer and a "sparkline" is just noise, so the card self-hides.
FOCUS_TREND_MIN_FRAMES = 6

# The night is called "softened"/"improved" only when the change between its first
# and last third clears BOTH a relative and an absolute floor — the same
# belt-and-braces the cross-session drift nudge uses, so we never cry drift over
# ordinary within-night seeing wobble. Otherwise the verdict is a calm "steady".
FOCUS_TREND_DRIFT_RATIO = 1.25   # last third ≥ 25% softer (or sharper) than the first, AND
FOCUS_TREND_DRIFT_ABS_PX = 0.6   # ≥ 0.6 px different in absolute terms — both must hold


@dataclass
class FocusTrendPoint:
    """One accepted, measured sub on the focus-trend sparkline."""

    t_utc: str            # capture time (ISO 8601 UTC, as stored)
    fwhm_px: float        # star size = sharpness (higher = softer)


@dataclass
class FocusTrend:
    """The most recent session's star-sharpness (FWHM) trend over capture time,
    plus a plain-language verdict. Read-only and purely informational — it never
    rejects a frame, it just shows the user how their focus held up.

    ``verdict`` is one of:
      "steady"   — sharpness held roughly flat across the night.
      "softened" — the stars grew materially softer later in the night
                   (dew / temperature / focus drift) — worth a dew heater or a
                   quick refocus next time.
      "improved" — the stars started soft and sharpened up (focus settled in).
    A session with too few measured subs to judge returns ``None`` instead.
    """

    verdict: str
    points: list[FocusTrendPoint]
    n_points: int
    median_fwhm_px: float          # median sharpness over the session
    early_fwhm_px: float           # median of the first third (night's start)
    late_fwhm_px: float            # median of the last third (night's end)
    start_utc: str | None          # first measured sub this session
    end_utc: str | None            # last measured sub this session
    soft_after_utc: str | None     # when it began to soften (only for "softened")


def focus_trend(
    project: Project, *, gap_hours: float = DEFAULT_SESSION_GAP_HOURS
) -> FocusTrend | None:
    """Star-sharpness (FWHM) trend across the target's most recent capture
    session, or ``None`` when too few of that session's accepted subs carry a
    usable FWHM to trend. Read-only aggregation over the ``frames`` table."""
    dated = [
        (dt, f)
        for f in project.iter_frames()
        if (dt := _parse(f.timestamp_utc)) is not None
    ]
    if not dated:
        return None
    dated.sort(key=lambda pair: pair[0])
    session_pairs = _last_session_frames(dated, gap_hours)
    # Only accepted, measured subs — the ones that actually feed the stack — so the
    # trend reflects the sharpness the picture was built from, not rejected outliers.
    measured = [
        f
        for _dt, f in session_pairs
        if f.accept and f.fwhm_px is not None and f.fwhm_px > 0
    ]
    if len(measured) < FOCUS_TREND_MIN_FRAMES:
        return None

    points = [
        FocusTrendPoint(t_utc=f.timestamp_utc, fwhm_px=float(f.fwhm_px))
        for f in measured
    ]
    fwhms = [p.fwhm_px for p in points]
    n = len(fwhms)
    third = n // 3  # ≥ 2 since n ≥ FOCUS_TREND_MIN_FRAMES (6)
    early = float(median(fwhms[:third]))
    late = float(median(fwhms[-third:]))

    soft_after: str | None = None
    if late >= early * FOCUS_TREND_DRIFT_RATIO and late - early >= FOCUS_TREND_DRIFT_ABS_PX:
        verdict = "softened"
        # The last third is where it's clearly soft; name when that stretch began.
        soft_after = points[n - third].t_utc
    elif early >= late * FOCUS_TREND_DRIFT_RATIO and early - late >= FOCUS_TREND_DRIFT_ABS_PX:
        verdict = "improved"
    else:
        verdict = "steady"

    return FocusTrend(
        verdict=verdict,
        points=points,
        n_points=n,
        median_fwhm_px=float(median(fwhms)),
        early_fwhm_px=early,
        late_fwhm_px=late,
        start_utc=points[0].t_utc,
        end_utc=points[-1].t_utc,
        soft_after_utc=soft_after,
    )


# ---------------------------------------------------------------------------
# "Clouds & haze through the night" — the transparency sibling of focus_trend.
# ---------------------------------------------------------------------------

# Same self-hide floor as the focus card — fewer measured subs than this and the
# sparkline is just noise, so the card doesn't appear.
TRANSPARENCY_TREND_MIN_FRAMES = 6

# The night is called "degraded"/"cleared" only when the median star flux between
# its first and last third changes by at least this ratio. Unlike FWHM (a known px
# scale, where the focus card pairs a relative *and* an absolute floor), the
# ``transparency_score`` is median star flux in arbitrary per-target ADU units, so
# an absolute floor would be meaningless across cameras/gains/targets. A *relative*
# ratio is scale-free and the right tool here; 1.4 (a ~40% swing in recorded flux
# between the start and end of a night) is deliberately conservative so ordinary
# transparency wobble reads as a calm "clear", and only a genuine cloud/haze/airmass
# change trips the verdict. (Tuneable against real stored transparency once we have
# a distribution to fit — same real-data caveat the Scout flagged for this metric.)
TRANSPARENCY_TREND_DROP_RATIO = 1.4


@dataclass
class TransparencyTrendPoint:
    """One accepted, measured sub on the transparency-trend sparkline."""

    t_utc: str            # capture time (ISO 8601 UTC, as stored)
    transparency: float   # median star flux (higher = clearer sky)


@dataclass
class TransparencyTrend:
    """The most recent session's sky-clarity (transparency) trend over capture
    time, plus a plain-language verdict. Read-only and purely informational — it
    never rejects a frame; it just shows the user how the sky held up (and, when
    it didn't, that the hazy subs were already auto-down-weighted in the stack).

    ``verdict`` is one of:
      "clear"    — transparency held roughly steady across the night.
      "degraded" — the sky grew materially murkier later in the night
                   (clouds / haze rolling in, or the target sinking into
                   thicker air) — those later subs came through a worse sky.
      "cleared"  — it started hazy and cleared up; the later subs did the
                   heavy lifting.
    A session with too few measured subs to judge returns ``None`` instead.
    """

    verdict: str
    points: list[TransparencyTrendPoint]
    n_points: int
    median_transparency: float      # median clarity over the session
    early_transparency: float       # median of the first third (night's start)
    late_transparency: float        # median of the last third (night's end)
    start_utc: str | None           # first measured sub this session
    end_utc: str | None             # last measured sub this session
    degraded_after_utc: str | None  # when the sky went murky (only for "degraded")


def transparency_trend(
    project: Project, *, gap_hours: float = DEFAULT_SESSION_GAP_HOURS
) -> TransparencyTrend | None:
    """Sky-clarity (transparency) trend across the target's most recent capture
    session, or ``None`` when too few of that session's accepted subs carry a
    usable ``transparency_score`` to trend (e.g. an older project predating the
    metric, or a starless field). Read-only aggregation over the ``frames``
    table — mirrors :func:`focus_trend`, but for *higher = better* transparency."""
    dated = [
        (dt, f)
        for f in project.iter_frames()
        if (dt := _parse(f.timestamp_utc)) is not None
    ]
    if not dated:
        return None
    dated.sort(key=lambda pair: pair[0])
    session_pairs = _last_session_frames(dated, gap_hours)
    # Only accepted, measured subs — the ones that actually feed the stack — so the
    # trend reflects the sky the picture was built from, not rejected outliers.
    measured = [
        f
        for _dt, f in session_pairs
        if f.accept and f.transparency_score is not None and f.transparency_score > 0
    ]
    if len(measured) < TRANSPARENCY_TREND_MIN_FRAMES:
        return None

    points = [
        TransparencyTrendPoint(t_utc=f.timestamp_utc, transparency=float(f.transparency_score))
        for f in measured
    ]
    scores = [p.transparency for p in points]
    n = len(scores)
    third = n // 3  # ≥ 2 since n ≥ TRANSPARENCY_TREND_MIN_FRAMES (6)
    early = float(median(scores[:third]))
    late = float(median(scores[-third:]))

    degraded_after: str | None = None
    # Higher transparency = clearer, so "degraded" is a *drop* (late materially
    # below early) and "cleared" is a *rise* — the direction flip vs the focus card.
    if early > 0 and early >= late * TRANSPARENCY_TREND_DROP_RATIO:
        verdict = "degraded"
        # The last third is where it's clearly murky; name when that stretch began.
        degraded_after = points[n - third].t_utc
    elif late > 0 and late >= early * TRANSPARENCY_TREND_DROP_RATIO:
        verdict = "cleared"
    else:
        verdict = "clear"

    return TransparencyTrend(
        verdict=verdict,
        points=points,
        n_points=n,
        median_transparency=float(median(scores)),
        early_transparency=early,
        late_transparency=late,
        start_utc=points[0].t_utc,
        end_utc=points[-1].t_utc,
        degraded_after_utc=degraded_after,
    )


# ---------------------------------------------------------------------------
# Per-target "Nights" breakdown — every capture night that went into a target,
# so a beginner (who shoots one target across many nights — the Seestar writes a
# new folder per night) can see which nights were good and, later, set a bad one
# aside. Read-only aggregation over the same session split the last-session recap
# uses, so it inherits its timezone-robust, midnight-safe grouping.
# ---------------------------------------------------------------------------

# A night's one-word verdict is advisory — a plain label + a gentle highlight,
# never a gate and never changes data — grounded only in metrics already stored:
#   "hazy"  — a large share of the night's subs were set aside as *cloudy* (the
#             transparency/sky reject bucket): the sky, not focus, was the problem.
#   "soft"  — its median FWHM is materially worse than the target's *sharpest*
#             night, reusing the same relative+absolute floors the cross-session
#             drift nudge already uses, so the two always agree.
#   "sharp" — a usable median FWHM and neither hazy nor soft.
#   ""      — too few measured subs to judge sharpness (and not hazy).
NIGHT_HAZY_CLOUD_FRACTION = 0.4  # ≥ 40% of the night's subs lost to cloud → "hazy"


@dataclass
class NightSummary:
    """One capture night's rollup for the per-target "Nights" breakdown. Times
    are ISO 8601 UTC strings (as stored on the frames)."""

    start_utc: str | None           # earliest capture this night
    end_utc: str | None             # latest capture this night
    n_frames: int                   # subs captured this night (kept + set aside)
    n_kept: int                     # accepted this night
    n_set_aside: int                # rejected this night
    exposure_s: float               # Σ exposure of every sub this night
    kept_exposure_s: float          # Σ exposure of the kept subs this night
    median_fwhm_px: float | None    # median FWHM over accepted, measured subs, or None
    verdict: str                    # "sharp" | "soft" | "hazy" | "" (too few measured)
    is_best: bool                   # the target's sharpest night (only when ≥2 judgeable)
    reject_buckets: dict[str, int] = field(default_factory=dict)  # plain bucket → count


def _night_verdict(
    median_fwhm: float | None, best_fwhm: float | None, cloud_fraction: float
) -> str:
    """One-word plain verdict for a night, from already-stored metrics only.

    Hazy (a big chunk of the night lost to cloud) takes precedence over any
    sharpness judgement; then a night materially softer than the target's best is
    "soft" (same floors as the drift nudge); a night with a usable median FWHM
    that is neither is "sharp"; otherwise "" (not enough measured to judge)."""
    if cloud_fraction >= NIGHT_HAZY_CLOUD_FRACTION:
        return "hazy"
    if median_fwhm is None:
        return ""
    if (best_fwhm is not None
            and median_fwhm >= best_fwhm * FWHM_DRIFT_RATIO
            and median_fwhm - best_fwhm >= FWHM_DRIFT_ABS_PX):
        return "soft"
    return "sharp"


def nights_breakdown(
    project: Project, *, gap_hours: float = DEFAULT_SESSION_GAP_HOURS
) -> list[NightSummary]:
    """Every capture night that went into this target, **newest first**.

    Groups the target's frames into capture-time sessions (the same 6 h-gap split
    the last-session recap uses) and rolls each night up into a small, friendly
    summary: subs kept vs set aside (and why, in plain buckets), integration, the
    night's median FWHM over its accepted subs, and a one-word verdict grounded in
    those metrics. Purely informational and read-only — it never rejects anything;
    a later slice can offer an opt-in "set this night aside" on top of it.

    Returns ``[]`` when nothing is datable (no frame carries a capture time).
    """
    dated: list[tuple[datetime, FrameRow]] = [
        (dt, f) for f in project.iter_frames()
        if (dt := _parse(f.timestamp_utc)) is not None
    ]
    if not dated:
        return []
    dated.sort(key=lambda pair: pair[0])
    sessions = _split_sessions(dated, gap_hours)

    # The target's sharpest night is the baseline both the "soft" verdict and the
    # "best" nod use — computed once over the nights that carry a usable median.
    medians = [m for s in sessions if (m := _session_median_fwhm(s)[0]) is not None]
    best_fwhm = min(medians) if medians else None
    n_judgeable = len(medians)

    out: list[NightSummary] = []
    for session_pairs in sessions:
        rows = [f for _dt, f in session_pairs]
        kept = [f for f in rows if f.accept]
        set_aside = [f for f in rows if not f.accept]
        buckets: dict[str, int] = {}
        for f in set_aside:
            b = bucket_reject_reason(f.reject_reason)
            buckets[b] = buckets.get(b, 0) + 1
        median_fwhm, _n = _session_median_fwhm(session_pairs)
        cloud_fraction = buckets.get("cloudy", 0) / len(rows) if rows else 0.0
        verdict = _night_verdict(median_fwhm, best_fwhm, cloud_fraction)
        # The "best" nod is a positive highlight, so only a genuinely good
        # ("sharp") night earns it — never a clouded ("hazy") night whose few
        # survivors happen to be sharp. ``best_fwhm`` is the min over the
        # judgeable nights, so ``<=`` flags exactly the sharpest; we only nod
        # "best" when there's more than one judgeable night to compare against.
        is_best = (
            n_judgeable >= 2
            and verdict == "sharp"
            and median_fwhm is not None
            and best_fwhm is not None
            and median_fwhm <= best_fwhm
        )
        out.append(NightSummary(
            start_utc=session_pairs[0][1].timestamp_utc,
            end_utc=session_pairs[-1][1].timestamp_utc,
            n_frames=len(rows),
            n_kept=len(kept),
            n_set_aside=len(set_aside),
            exposure_s=sum(f.exposure_s or 0.0 for f in rows),
            kept_exposure_s=sum(f.exposure_s or 0.0 for f in kept),
            median_fwhm_px=median_fwhm,
            verdict=verdict,
            is_best=is_best,
            reject_buckets=buckets,
        ))

    out.reverse()  # newest night first
    return out


@dataclass
class TargetNightContribution:
    """What one target contributed to the library's most recent night."""

    name: str            # the target's display name (e.g. "M 31")
    safe: str            # its URL-safe id, for linking back to the target page
    n_frames: int        # subs captured this night (kept + set aside)
    n_kept: int          # accepted this night
    n_set_aside: int     # rejected this night
    exposure_s: float    # Σ exposure of every sub this night
    kept_exposure_s: float  # Σ exposure of the kept subs this night


@dataclass
class LibrarySessionRecap:
    """The whole library's most recent capture night, combined across targets —
    the Dashboard answer to *what did last night give me?* across everything you
    shot, not just one target. Times are ISO 8601 UTC strings."""

    n_targets: int                      # targets shot this night
    n_frames: int                       # subs captured this night, all targets
    n_kept: int                         # accepted this night, all targets
    n_set_aside: int                    # rejected this night, all targets
    session_exposure_s: float           # Σ exposure this night, all targets
    kept_exposure_s: float              # Σ exposure of the kept subs this night
    start_utc: str | None               # earliest capture this night
    end_utc: str | None                 # latest capture this night
    targets: list[TargetNightContribution] = field(default_factory=list)
    reject_buckets: dict[str, int] = field(default_factory=dict)  # merged buckets


def library_session_recap(
    targets: list[tuple[str, str, list[FrameRow]]],
    *,
    gap_hours: float = DEFAULT_SESSION_GAP_HOURS,
) -> LibrarySessionRecap | None:
    """Combine every target's most-recent capture session into one recap of the
    library's latest night. ``targets`` is ``(name, safe, frames)`` per target.

    Each target's most recent session is found with the same gap rule
    :func:`session_recap` uses; those per-target last sessions are then merged
    onto one timeline and the trailing ``gap_hours``-separated cluster is "last
    night". So two targets shot the same night combine into one recap, while a
    target *not* shot that night (its last session was earlier) drops out. Returns
    ``None`` when no frame across the library carries a capture timestamp.

    Pure, offline, read-only — it just aggregates the frame rows it's handed.
    """
    # (capture-time, name, safe, frame) for every datable frame the caller handed
    # us. We deliberately do **not** pre-trim each target to its own last session
    # here: a target imaged early in a night and revisited near dawn (a >6 h
    # internal gap) would then lose its early batch *before* the merge, even when
    # another target shot in between bridges the two into one continuous night. The
    # trailing-cluster walk below makes the real "last night" cut over the *merged*
    # timeline, so an older isolated session still falls away — while a bridged one
    # is kept. The caller bounds memory with ``recent_session_window_frames``.
    merged: list[tuple[datetime, str, str, FrameRow]] = []
    for name, safe, frames in targets:
        for f in frames:
            dt = _parse(f.timestamp_utc)
            if dt is not None:
                merged.append((dt, name, safe, f))

    if not merged:
        return None

    merged.sort(key=lambda item: item[0])
    # The trailing cluster: walk back from the newest capture while consecutive
    # captures stay within the gap — the same session split, applied to the merged
    # timeline, so same-night targets group and older last-sessions fall away.
    gap_s = gap_hours * 3600.0
    start_idx = len(merged) - 1
    for i in range(len(merged) - 1, 0, -1):
        if (merged[i][0] - merged[i - 1][0]).total_seconds() <= gap_s:
            start_idx = i - 1
        else:
            break
    night = merged[start_idx:]

    # Group the night's frames by target, preserving each target's first-capture
    # order so ties read in the order they were actually shot.
    order: list[tuple[str, str]] = []
    by_target: dict[tuple[str, str], list[FrameRow]] = {}
    for _dt, name, safe, f in night:
        key = (name, safe)
        if key not in by_target:
            by_target[key] = []
            order.append(key)
        by_target[key].append(f)

    contributions: list[TargetNightContribution] = []
    buckets: dict[str, int] = {}
    n_frames = n_kept = n_set_aside = 0
    session_exposure_s = kept_exposure_s = 0.0
    for name, safe in order:
        rows = by_target[(name, safe)]
        kept = [f for f in rows if f.accept]
        set_aside = [f for f in rows if not f.accept]
        exp = sum(f.exposure_s or 0.0 for f in rows)
        kept_exp = sum(f.exposure_s or 0.0 for f in kept)
        for f in set_aside:
            b = bucket_reject_reason(f.reject_reason)
            buckets[b] = buckets.get(b, 0) + 1
        contributions.append(TargetNightContribution(
            name=name, safe=safe,
            n_frames=len(rows), n_kept=len(kept), n_set_aside=len(set_aside),
            exposure_s=exp, kept_exposure_s=kept_exp,
        ))
        n_frames += len(rows)
        n_kept += len(kept)
        n_set_aside += len(set_aside)
        session_exposure_s += exp
        kept_exposure_s += kept_exp

    # Biggest capture leads the card; a stable sort keeps equal counts in shot order.
    contributions.sort(key=lambda c: c.n_frames, reverse=True)

    return LibrarySessionRecap(
        n_targets=len(contributions),
        n_frames=n_frames,
        n_kept=n_kept,
        n_set_aside=n_set_aside,
        session_exposure_s=session_exposure_s,
        kept_exposure_s=kept_exposure_s,
        start_utc=night[0][3].timestamp_utc,
        end_utc=night[-1][3].timestamp_utc,
        targets=contributions,
        reject_buckets=buckets,
    )
