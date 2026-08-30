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
from typing import Sequence, TypeVar

from seestack.io.project import FrameRow, Project

# Any row whose first element is its capture time — see ``_split_sessions``.
_TimedT = TypeVar("_TimedT", bound=Sequence)

# A night's subs land minutes apart; the gap to the previous night is many hours.
# Six hours cleanly separates two nights without splitting a single long session.
DEFAULT_SESSION_GAP_HOURS = 6.0

# Cross-session quality-drift nudge (see ``session_quality_drift``). Auto-grade is
# relative *within* a session, so a whole night shot soft/out-of-focus passes every
# frame; this catches it by comparing the newest session's median FWHM against the
# target's **typical** other night. Deliberately conservative — it must clear BOTH
# a relative and an absolute floor — so it never nags on ordinary night-to-night
# seeing wobble, only a materially worse whole session.
#
# The baseline used to be the *best* (sharpest) other night, and that was a
# statistic whose meaning changed with how many nights you had: a minimum over N
# samples falls without limit as N grows, so on a sky whose seeing never changed
# the same ordinary night got flagged more and more often the longer the owner
# stayed on the target. Measured (200k trials, nightly median FWHM ~ N(3.5, 0.5)
# px, identical every night): **13.7 % of ordinary nights flagged after one prior
# night, 40 % after five, 68 % after twenty, 79 % after forty**. The owner's whole
# workflow is many nights on one target, so the nudge was aimed squarely at its own
# blind spot — and on the Nights card the same comparison drives the "soft" badge
# that sits beside a one-click **Set aside**, i.e. it was nudging toward discarding
# good nights. The median of the *other* nights is stationary in N by construction,
# which is the fix: same floors, same copy shape, a baseline that means one thing
# however long you shoot. Re-measured on the same trials it holds ordinary nights
# at 13.7 % → 4.4 % across the same sweep while still catching 88.8 % of a
# genuinely soft (+1.5 px) night at forty nights.
SESSION_QUALITY_MIN_FRAMES = 4      # need this many measured subs per session to trust its median
FWHM_DRIFT_RATIO = 1.25             # newest ≥ 25% softer than the typical other session, AND
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
    the target's **typical** previous session — a whole-session quality dip (e.g. a
    night shot slightly out of focus or through thin haze) that auto-grade, which
    only compares frames *within* a session, structurally can't see. Purely
    informational: it never rejects anything, it just tells the user to check."""

    kind: str            # which metric drifted — currently always "fwhm"
    latest_fwhm_px: float    # newest session's median FWHM (higher = softer)
    baseline_fwhm_px: float  # median of the prior sessions' median FWHMs
    n_latest: int            # measured subs behind the newest median
    n_baseline: int          # measured subs behind the baseline, across those sessions


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


def parse_capture_time(ts: str | None) -> datetime | None:
    """A frame's stored capture time as a tz-aware UTC ``datetime``, or ``None``
    when it's absent or unparseable.

    Public because every night-shaped screen must read a capture stamp the *same*
    way — the tz-naive coercion below is exactly the kind of detail two
    implementations would disagree about. ``_parse`` remains as the in-module
    shorthand this file has always used."""
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


_parse = parse_capture_time


def _split_sessions(frames: list[_TimedT], gap_hours: float) -> list[list[_TimedT]]:
    """Partition capture-time-tagged rows sorted ascending into sessions,
    starting a new session wherever consecutive captures are more than
    ``gap_hours`` apart. Returns a list of sessions, oldest first.

    Generic in what rides along with the timestamp: callers pass
    ``(datetime, FrameRow)`` pairs, and the lean pace path passes
    ``(datetime, exposure_s, accept)`` triples — only element 0 is read here, and
    keeping one implementation is what makes every screen agree on where a night
    starts and ends."""
    if not frames:
        return []
    gap_s = gap_hours * 3600.0
    sessions: list[list[_TimedT]] = [[frames[0]]]
    for i in range(1, len(frames)):
        prev_dt = frames[i - 1][0]
        this_dt = frames[i][0]
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
    """Compare the newest session's median FWHM against the target's **typical**
    prior session and flag a materially softer newest session. Needs at least two
    sessions each with enough measured subs; returns ``None`` otherwise or when
    the drift doesn't clear both the relative and absolute floors.

    "Typical" is the median of the prior sessions' medians, deliberately, and not
    the sharpest one — see the constants above for the measurement. On two prior
    sessions the two answers differ by construction (a min sits at one end of the
    pair, a median between them), and past that the min keeps falling while the
    median does not, so only the median means the same thing on the owner's
    twentieth night as on their second."""
    if len(sessions) < 2:
        return None
    latest_fwhm, n_latest = _session_median_fwhm(sessions[-1])
    if latest_fwhm is None:
        return None
    priors: list[tuple[float, int]] = []
    for prior in sessions[:-1]:
        med, n = _session_median_fwhm(prior)
        if med is not None:
            priors.append((med, n))
    if not priors:
        return None
    baseline_fwhm = float(median([med for med, _n in priors]))
    # The baseline is built from every judgeable prior night now, not one of them,
    # so the sub count it reports is the whole population behind it.
    n_baseline = sum(n for _med, n in priors)
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

# A mosaic panel needs at least this many of the session's measured subs before
# its own median is a trustworthy yardstick to rescale that panel by — the same
# "≥2 substantial groups or no split at all" gate the engine's per-panel passes
# use (``pointing_groups``), at the same 3-frame floor as the quality weighting.
TRANSPARENCY_TREND_MIN_PANEL_FRAMES = 3


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
    # How many mosaic panels this session's subs split into (0 = one pointing,
    # the ordinary case). Non-zero means the scores below were rescaled panel by
    # panel — see :func:`transparency_trend` — so the card can say why.
    n_pointings: int = 0


def transparency_trend(
    project: Project, *, gap_hours: float = DEFAULT_SESSION_GAP_HOURS
) -> TransparencyTrend | None:
    """Sky-clarity (transparency) trend across the target's most recent capture
    session, or ``None`` when too few of that session's accepted subs carry a
    usable ``transparency_score`` to trend (e.g. an older project predating the
    metric, or a starless field). Read-only aggregation over the ``frames``
    table — mirrors :func:`focus_trend`, but for *higher = better* transparency.

    **On a mosaic the raw scores can't be trended as they stand.**
    ``transparency_score`` is the median flux of a frame's *brightest stars*, so
    it is a property of where the scope pointed as much as of the sky — the same
    thing that made QC grading (v0.270.2), photometric normalization (v0.271.0)
    and quality weighting (v0.272.1) each misread a mosaic. A Seestar working
    through its panels in sequence therefore ends the night on a different patch
    of sky from the one it started on, and comparing the first third against the
    last third reads "we moved to an emptier panel" as "clouds rolled in". So when
    the session's pointings split soundly (``pointing_groups``), each panel's
    scores are **rescaled onto the session's overall median** before anything is
    trended: the panel-to-panel offset goes, the within-night change every panel
    actually saw stays, and the units stay familiar. ``n_pointings`` reports how
    many panels that was, so the card can say so.

    Fail-neutral by construction: a single-pointing target (the ordinary case),
    an unsolved one, and a mosaic too tightly packed to separate all get no split
    and are byte-for-byte unchanged, and a sub in no substantial panel keeps its
    raw score rather than borrowing another patch of sky's yardstick."""
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

    raw = [float(f.transparency_score) for f in measured]  # type: ignore[arg-type]
    factors, n_pointings = _panel_rescale_factors(measured, raw)
    points = [
        TransparencyTrendPoint(t_utc=f.timestamp_utc, transparency=s * k)
        for f, s, k in zip(measured, raw, factors, strict=True)
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
        n_pointings=n_pointings,
    )


def _panel_rescale_factors(
    frames: list[FrameRow], scores: list[float],
) -> tuple[list[float], int]:
    """Per-frame multipliers that put a mosaic's panels on one scale, and how many
    panels there were.

    ``(all 1.0, 0)`` — i.e. "change nothing" — whenever the session's pointings
    don't split soundly, which is every single-field target and every unsolved
    one. Where they do, a panel carrying at least
    ``TRANSPARENCY_TREND_MIN_PANEL_FRAMES`` measured subs is rescaled by
    ``overall median / that panel's median`` so its subs sit on the session's own
    scale; anything else (a sub in no substantial panel, a degenerate median) is
    left alone at 1.0. Pure — see :func:`transparency_trend` for why.
    """
    from seestack.stack.pointings import pointing_groups

    labels = pointing_groups(
        [(f.ra_center_deg, f.dec_center_deg) for f in frames],
        min_members=TRANSPARENCY_TREND_MIN_PANEL_FRAMES,
    )
    if labels is None:
        return [1.0] * len(frames), 0
    overall = float(median(scores))
    per_label: dict[int, list[float]] = {}
    for label, s in zip(labels, scores, strict=True):
        if label >= 0:
            per_label.setdefault(label, []).append(s)
    gains = {
        label: overall / float(median(vals))
        for label, vals in per_label.items()
        if len(vals) >= TRANSPARENCY_TREND_MIN_PANEL_FRAMES and median(vals) > 0
    }
    if not (overall > 0) or len(gains) < 2:
        # Nothing to level, or only one panel could be measured — treating that
        # one as the yardstick would move it against un-rescaled neighbours,
        # which is worse than leaving the night alone.
        return [1.0] * len(frames), 0
    return [gains.get(label, 1.0) for label in labels], len(gains)


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
    # The baseline this night's verdict was judged against — the median of the
    # OTHER nights' medians (see ``_typical_other_fwhm``), or None when there is
    # no other judgeable night. Returned so the UI can say what "soft" means
    # rather than showing a bare yellow word next to a discard button.
    typical_fwhm_px: float | None
    is_best: bool                   # the target's sharpest night (only when ≥2 judgeable)
    reject_buckets: dict[str, int] = field(default_factory=dict)  # plain bucket → count


def _typical_other_fwhm(medians: list[float], skip: int) -> float | None:
    """The median of every judgeable night's median FWHM *except* the one at
    ``skip`` — the baseline a night is judged "soft" against.

    Leave-one-out, so a night is never compared against itself, and a **median**
    rather than the minimum the verdict used to use. The minimum was the same
    grows-with-the-library mistake the drift nudge had (see the constants at the
    top of this module): the sharpest of N nights keeps getting sharper as N
    rises, so on a sky whose seeing never changed the share of a target's own
    nights badged "soft" ran **13.7 % at two nights → 35.9 % at five → 78.6 % at
    forty** (40k trials, nightly median FWHM ~ N(3.5, 0.5) px). That badge sits
    directly beside the one-click "Set aside" button, so it was steering a
    beginner toward discarding perfectly good nights on a long project — the
    owner's exact workflow. Leave-one-out median holds the same sweep at 13.7 %
    → 4.5 %, and on a **two-night** target it is bit-for-bit the old answer (the
    only other night *is* the minimum of the others).

    ``None`` when this is the only judgeable night — nothing to compare against,
    so nothing may be called soft."""
    others = medians[:skip] + medians[skip + 1:]
    return float(median(others)) if others else None


def _night_verdict(
    median_fwhm: float | None, typical_fwhm: float | None, cloud_fraction: float
) -> str:
    """One-word plain verdict for a night, from already-stored metrics only.

    Hazy (a big chunk of the night lost to cloud) takes precedence over any
    sharpness judgement; then a night materially softer than the target's
    *typical other* night is "soft" (same floors, and the same baseline choice,
    as the drift nudge — see ``_typical_other_fwhm``); a night with a usable
    median FWHM that is neither is "sharp"; otherwise "" (not enough measured to
    judge)."""
    if cloud_fraction >= NIGHT_HAZY_CLOUD_FRACTION:
        return "hazy"
    if median_fwhm is None:
        return ""
    if (typical_fwhm is not None
            and median_fwhm >= typical_fwhm * FWHM_DRIFT_RATIO
            and median_fwhm - typical_fwhm >= FWHM_DRIFT_ABS_PX):
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

    # Per-night medians, once, for the two things that need to compare nights.
    # They want *different* statistics and used to share one: the "best" nod
    # genuinely means the sharpest night (a minimum), while the "soft" verdict
    # means "worse than my other nights", which a minimum answers wrongly and
    # more wrongly the longer the project runs (see ``_typical_other_fwhm``).
    night_medians = [_session_median_fwhm(s)[0] for s in sessions]
    medians = [m for m in night_medians if m is not None]
    best_fwhm = min(medians) if medians else None
    n_judgeable = len(medians)
    # Index into ``medians`` for each judgeable session, so a night can be left
    # out of its own baseline by position rather than by value (two nights that
    # measured identically must each still see the other).
    judgeable_at: dict[int, int] = {}
    for s_idx, m in enumerate(night_medians):
        if m is not None:
            judgeable_at[s_idx] = len(judgeable_at)

    out: list[NightSummary] = []
    for s_idx, session_pairs in enumerate(sessions):
        rows = [f for _dt, f in session_pairs]
        kept = [f for f in rows if f.accept]
        set_aside = [f for f in rows if not f.accept]
        buckets: dict[str, int] = {}
        for f in set_aside:
            b = bucket_reject_reason(f.reject_reason)
            buckets[b] = buckets.get(b, 0) + 1
        median_fwhm = night_medians[s_idx]
        cloud_fraction = buckets.get("cloudy", 0) / len(rows) if rows else 0.0
        typical_fwhm = (_typical_other_fwhm(medians, judgeable_at[s_idx])
                        if s_idx in judgeable_at else None)
        verdict = _night_verdict(median_fwhm, typical_fwhm, cloud_fraction)
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
            typical_fwhm_px=typical_fwhm,
            is_best=is_best,
            reject_buckets=buckets,
        ))

    out.reverse()  # newest night first
    return out


# --- recent capture pace ("how much is a clear night worth to me?") ---------
#
# These two numbers are mirrored, deliberately and by hand, in the frontend's
# ``clearNights.ts`` (PACE_LOOKBACK_NIGHTS / MIN_PRODUCTIVE_NIGHT_S). The Target
# page derives the pace client-side from the night list it already fetches; the
# Library-wide overview gets it from the server, computed here. Both must land on
# the same figure for the same target, or the two screens would quote different
# ETAs for the same picture — so change them together.

# How many recent nights the pace is taken over. Long enough that one short night
# doesn't dominate, short enough that a change of habit shows up quickly.
PACE_LOOKBACK_NIGHTS = 5

# Below this much kept integration a "night" is a test frame or two, not a
# session — counting it would drag the median down and inflate every estimate.
MIN_PRODUCTIVE_NIGHT_S = 120.0


def recent_night_pace_s(
    project: Project,
    *,
    gap_hours: float = DEFAULT_SESSION_GAP_HOURS,
    lookback_nights: int = PACE_LOOKBACK_NIGHTS,
) -> float | None:
    """This target's recent productive pace: the **median kept integration per
    clear night**, in seconds, over its most recent nights — or ``None`` when
    there isn't enough history to call it a pace.

    This is what turns an abstract "3.2 h of a 5 h goal" gap into a plan a
    beginner can act on ("about 2 more clear nights"), because only the target's
    own history knows what a clear night is really worth to *this* owner: this
    sky, this framing, this rejection rate.

    Nights are the same 6 h-gap capture sessions :func:`nights_breakdown` shows,
    so the number agrees with the "Nights" card. Only the most recent
    ``lookback_nights`` count, and within those only the *productive* ones (at
    least ``MIN_PRODUCTIVE_NIGHT_S`` of kept subs). Returns ``None`` unless at
    least two of them qualify — one session is not a pace, and projecting a whole
    remaining goal off it would be a confident guess from nothing.

    Read-only and offline; it reads three columns per dated frame and never
    writes anything.
    """
    dated: list[tuple[datetime, float, bool]] = [
        (dt, exposure, accept)
        for ts, exposure, accept in project.iter_frame_capture_rows()
        if (dt := _parse(ts)) is not None
    ]
    if not dated:
        return None
    dated.sort(key=lambda row: row[0])
    sessions = _split_sessions(dated, gap_hours)

    # Newest first, then the same window + productivity filter the Target page's
    # client-side estimate applies.
    recent = sessions[-lookback_nights:] if lookback_nights > 0 else []
    kept_per_night = [
        sum(exposure for _dt, exposure, accept in s if accept) for s in recent
    ]
    productive = [k for k in kept_per_night if k >= MIN_PRODUCTIVE_NIGHT_S]
    if len(productive) < 2:
        return None
    return float(median(productive))


def night_frame_ids(
    project: Project,
    start_utc: str,
    end_utc: str,
    *,
    accepted_only: bool = False,
) -> list[int]:
    """The frame IDs of the capture night bounded by ``[start_utc, end_utc]``.

    ``start_utc``/``end_utc`` are a night's own first/last capture stamps as
    returned by :func:`nights_breakdown` (a ``NightSummary``'s ``start_utc`` /
    ``end_utc``). Because sessions are gap-separated and never overlap in time,
    every frame whose capture time falls in that inclusive window belongs to
    exactly that one night — so a plain time-window match reproduces the same
    night the "Nights" card shows without re-deriving the session split. Pass
    ``accepted_only`` to restrict to the subs currently feeding the stack — the
    set the opt-in "set this night aside" action rejects.

    Returns ``[]`` when either bound is unparseable or nothing falls in-window.
    """
    start = _parse(start_utc)
    end = _parse(end_utc)
    if start is None or end is None:
        return []
    ids: list[int] = []
    for f in project.iter_frames(accepted_only=accepted_only):
        dt = _parse(f.timestamp_utc)
        if dt is not None and start <= dt <= end:
            ids.append(f.id)
    return ids


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
