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
from datetime import datetime, timezone
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
