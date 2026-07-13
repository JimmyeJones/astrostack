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
from datetime import datetime

from seestack.io.project import FrameRow, Project

# A night's subs land minutes apart; the gap to the previous night is many hours.
# Six hours cleanly separates two nights without splitting a single long session.
DEFAULT_SESSION_GAP_HOURS = 6.0

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


def _parse(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        # Python 3.11+ fromisoformat accepts a trailing 'Z'; be defensive anyway.
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _last_session_frames(
    frames: list[tuple[datetime, FrameRow]], gap_hours: float
) -> list[tuple[datetime, FrameRow]]:
    """Given (capture-time, frame) pairs sorted ascending, return the trailing
    run whose consecutive capture times are within ``gap_hours`` of each other —
    i.e. the most recent night's frames."""
    if not frames:
        return []
    gap_s = gap_hours * 3600.0
    start_i = len(frames) - 1
    for i in range(len(frames) - 2, -1, -1):
        newer_dt, _ = frames[i + 1]
        older_dt, _ = frames[i]
        if (newer_dt - older_dt).total_seconds() <= gap_s:
            start_i = i
        else:
            break
    return frames[start_i:]


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
    session_pairs = _last_session_frames(dated, gap_hours)
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
    )
