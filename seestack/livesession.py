"""**"Tonight, live"** — how the session happening *right now* is going.

Every session view the app has is either *predictive* (the Tonight planner: what
is up) or *retrospective* (:mod:`seestack.session_recap`: "what did last night
give me?", explicitly written for reading on return). There was no view of the
night in progress — so a beginner standing outside in the cold with the Seestar
had two questions and no answer to either:

* **"Is this actually working?"** — the Seestar's own screen shows a preview, not
  whether the subs it is writing are any good.
* **"Have I got enough to go inside?"** — answerable only in the morning.

The app already knows both, live: the watcher ingests and QCs each sub within a
minute or two of it landing in ``incoming/``, so it holds every sub's FWHM, star
count and accept verdict while the night is still running. This module turns the
frames table into that answer.

Two things it is deliberately **not**. It is not a second definition of "a
session": the trailing cluster is cut with the very same
:func:`seestack.session_recap._split_sessions` gap walk every other night-shaped
screen uses, so no two surfaces can ever disagree about where a night starts. And
it is not a nag — it reports, and says "no session in progress" plainly when the
last sub is hours old, so it self-hides on a quiet night rather than inventing
one.

It also answers a third question the owner can only ask *after* walking away —
**"did it keep going?"** A stalled Seestar (disconnected, card full, parked by a
dew-heater trip) doesn't fail loudly; the subs simply stop, and the owner finds
out in the morning that half a clear night is missing. ``active`` already knew
the newest sub was stale; ``quiet`` is the narrower, mentionable case: this
session was *mid-run* and fell silent, judged against the cadence the target
itself had been keeping. A night the owner deliberately finished never trips it.

Pure, offline and read-only: it aggregates ``frames`` rows and nothing else. The
clock is injected (``now``), so every window it computes is unit-testable without
sleeping or patching.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from statistics import median

from seestack.io.project import FrameRow, Project
from seestack.session_recap import (
    DEFAULT_SESSION_GAP_HOURS,
    bucket_reject_reason,
    last_session_frames,
    parse_capture_time,
)

# How stale the newest sub may be before the night stops counting as "happening
# right now". Generous on purpose: a Seestar re-pointing, a meridian flip, a
# passing cloud the mount waits out, or simply a slow watcher poll can leave a
# real gap mid-session, and flipping to "no session in progress" the moment one
# appears would be exactly the wrong answer for someone standing outside asking
# "is it still working?". Well under the 6 h session gap, so a genuinely finished
# night is never mistaken for a live one.
LIVE_STALE_MINUTES = 45.0

# How many of the session's most recent subs the conditions read looks at. Small
# enough to notice cloud rolling in within a few minutes of subs, large enough
# that one bad frame can't swing the verdict.
CONDITIONS_WINDOW_FRAMES = 20

# Below this many recent subs there is nothing worth grading — the verdict is
# "unknown" and the UI says so rather than calling a night on two frames.
CONDITIONS_MIN_FRAMES = 5

# Where a rolling accept-rate stops being "it's going well" and starts being
# "something is wrong out there". A Seestar on a good night keeps the large
# majority of its subs; losing more than a third of a rolling window is the
# signal a beginner would otherwise only discover in the morning.
CONDITIONS_GOOD_KEEP_RATE = 0.8
CONDITIONS_POOR_KEEP_RATE = 0.5

# --- "capture seems to have gone quiet" -------------------------------------
#
# The failure the owner cannot see happening: they walk away, and part-way
# through an otherwise-clear night the Seestar disconnects, fills its card, or
# parks itself — so subs simply stop arriving and they find out in the morning.
# ``active`` above already knows the newest sub is stale; what it *doesn't* say
# is whether the target was mid-run when it stopped (worth a heads-up) or simply
# finished (worth nothing at all). These constants draw that line.
#
# The cadence is measured, never assumed: "no sub for 45 minutes" means something
# very different for 10 s subs than for a target the owner shoots one 5-minute
# frame at a time, so the wait scales with the gap this target has actually been
# keeping — with a floor and a ceiling either side of it.

# How many of the session's trailing subs the cadence is measured over. Long
# enough that one dither or refocus pause can't move the median, short enough
# that a cadence change part-way through the night is reflected quickly.
QUIET_WINDOW_FRAMES = 30

# Below this many datable subs in the session there is no "run of arrivals" to
# have stopped — a couple of test frames that go quiet is just a couple of test
# frames, so the note stays silent rather than guessing.
QUIET_MIN_FRAMES = 6

# ...and below this much elapsed capture the session never really got going
# (six 10 s subs span a minute). Both floors must clear before anything is said.
QUIET_MIN_SESSION_MINUTES = 20.0

# The wait, in multiples of the target's own typical inter-sub gap. Six is
# deliberately generous: a Seestar's dither, refocus and re-point pauses are a
# small number of sub-lengths, and the cost of crying wolf on a working scope is
# much higher than the cost of noticing a stall a few minutes later.
QUIET_GAP_MULTIPLE = 6.0

# Never say anything sooner than the session stops counting as live (so "still
# going" and "gone quiet" can never both be true), and never wait longer than the
# ceiling however slow the cadence — three hours of silence is worth mentioning
# even to someone shooting half-hour subs.
QUIET_CEILING_MINUTES = 180.0


@dataclass
class LiveConditions:
    """How the last handful of subs have been going — the rolling "is it working
    right now?" read, as distinct from the whole session's totals.

    ``verdict`` is one of ``good`` / ``mixed`` / ``poor`` / ``unknown``; the last
    means "too few recent subs to say", never "bad". The numbers behind it travel
    with it so the UI can say *why* ("4 of your last 20 subs were kept") instead
    of asking the reader to trust a bare adjective.
    """

    verdict: str
    n_recent: int                       # subs in the rolling window
    n_recent_kept: int                  # of those, accepted
    median_fwhm_px: float | None = None  # median star size of the kept ones, if measured
    # The plain buckets behind the *set-aside* subs in the window, so the UI can
    # name the cause ("cloudy", "trailed") rather than only the count.
    recent_buckets: dict[str, int] = field(default_factory=dict)


@dataclass
class LiveSession:
    """The capture session in progress (or the trailing one, if it has gone
    quiet) — counts, integration, and how it has been going lately.

    Every time is an ISO 8601 UTC string, exactly as stored on the frames.
    """

    active: bool                  # newest sub within LIVE_STALE_MINUTES of ``now``
    n_frames: int                 # subs this session (kept + set aside)
    n_kept: int
    n_set_aside: int
    kept_exposure_s: float        # integration so far — the number a goal counts
    session_exposure_s: float     # Σ exposure of every sub this session
    total_kept_exposure_s: float  # Σ exposure of every accepted sub, all sessions
    start_utc: str | None
    latest_utc: str | None
    minutes_since_latest: float | None   # how stale the newest sub is, at ``now``
    conditions: LiveConditions
    reject_buckets: dict[str, int] = field(default_factory=dict)
    # The newest *accepted* sub's id, so the page can show the freshest thumbnail
    # the app actually kept — never a frame it just set aside.
    newest_kept_frame_id: int | None = None
    # "Capture seems to have gone quiet": this session was mid-run and has since
    # fallen silent for longer than ``quiet_after_minutes``. Strictly narrower
    # than ``not active`` — a night the owner deliberately finished, a target
    # that only ever got a handful of subs, and a session that stopped so long
    # ago it is simply history all read ``quiet=False``. The cadence it is judged
    # against travels with it, so a caller can say *why* ("a sub about every
    # 40 s, then nothing") instead of quoting a bare threshold.
    quiet: bool = False
    typical_gap_minutes: float | None = None
    quiet_after_minutes: float | None = None


def _conditions(frames: list[FrameRow]) -> LiveConditions:
    """Grade the trailing ``CONDITIONS_WINDOW_FRAMES`` subs of a session.

    Deliberately blunt: a keep-rate with two floors, plus the kept subs' median
    star size for the UI to quote. It never *combines* sharpness into the verdict
    — a sharp night that is being thrown away by cloud and a soft night that is
    all being kept are different problems, and averaging them into one adjective
    would hide both.
    """
    window = frames[-CONDITIONS_WINDOW_FRAMES:]
    n_recent = len(window)
    kept = [f for f in window if f.accept]
    n_kept = len(kept)
    fwhms = [f.fwhm_px for f in kept if f.fwhm_px is not None and f.fwhm_px > 0]
    med = float(median(fwhms)) if fwhms else None
    buckets: dict[str, int] = {}
    for f in window:
        if not f.accept:
            b = bucket_reject_reason(f.reject_reason)
            buckets[b] = buckets.get(b, 0) + 1

    if n_recent < CONDITIONS_MIN_FRAMES:
        verdict = "unknown"
    else:
        rate = n_kept / n_recent
        if rate >= CONDITIONS_GOOD_KEEP_RATE:
            verdict = "good"
        elif rate >= CONDITIONS_POOR_KEEP_RATE:
            verdict = "mixed"
        else:
            verdict = "poor"
    return LiveConditions(
        verdict=verdict, n_recent=n_recent, n_recent_kept=n_kept,
        median_fwhm_px=med, recent_buckets=buckets,
    )


def typical_gap_minutes(frames: list[FrameRow]) -> float | None:
    """The median minutes between consecutive subs over the session's trailing
    window, or ``None`` when there aren't enough datable arrivals to say.

    The *median*, not the mean, precisely because a real night contains pauses —
    a dither, a refocus, a cloud the mount waits out — and one 20-minute hole
    must not be allowed to redefine what "normal" looks like for this target.
    Non-positive gaps (two subs sharing a stamp, or a clock that stepped
    backwards) are dropped rather than counted as an infinitely fast cadence.
    """
    stamps = [
        dt for f in frames[-QUIET_WINDOW_FRAMES:]
        if (dt := parse_capture_time(f.timestamp_utc)) is not None
    ]
    if len(stamps) < QUIET_MIN_FRAMES:
        return None
    gaps = [
        (b - a).total_seconds() / 60.0
        for a, b in zip(stamps, stamps[1:])
        if (b - a).total_seconds() > 0
    ]
    if len(gaps) < QUIET_MIN_FRAMES - 1:
        return None
    return float(median(gaps))


def quiet_after_minutes(
    typical_gap_min: float, *, stale_minutes: float = LIVE_STALE_MINUTES
) -> float:
    """How long this target's silence has to run before it is worth mentioning,
    given the cadence it has been keeping.

    Clamped by ``stale_minutes`` below — so "still going" and "gone quiet" can
    never both be true of one session — and by :data:`QUIET_CEILING_MINUTES`
    above, so even a very slow cadence gets noticed the same night.
    """
    return min(
        QUIET_CEILING_MINUTES,
        max(stale_minutes, QUIET_GAP_MULTIPLE * typical_gap_min),
    )


def live_session(
    project: Project,
    *,
    now: datetime | None = None,
    gap_hours: float = DEFAULT_SESSION_GAP_HOURS,
    stale_minutes: float = LIVE_STALE_MINUTES,
) -> LiveSession | None:
    """The target's trailing capture session as it stands *at* ``now``, or
    ``None`` when the target has no datable frames at all.

    ``active`` is the whole point: it is ``True`` only while the newest sub is
    within ``stale_minutes``, so the caller can say "tonight, live" for a night in
    progress and fall back to the ordinary recap for one that has finished. The
    session itself is the same trailing gap-separated cluster every other
    night-shaped screen uses, so a session that went quiet an hour ago is still
    reported — with ``active=False`` — rather than vanishing mid-night.

    Read-only aggregation over the ``frames`` table; safe to call while a scan,
    an ingest or a stack is running.
    """
    ref = now or datetime.now(timezone.utc)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)

    all_frames: list[FrameRow] = []
    total_kept_exposure_s = 0.0
    for f in project.iter_frames():
        if f.accept:
            total_kept_exposure_s += f.exposure_s or 0.0
        all_frames.append(f)

    # The same trailing-cluster cut every other night-shaped screen makes — one
    # definition of "a session", so no two surfaces can disagree about where the
    # night starts.
    session = last_session_frames(all_frames, gap_hours=gap_hours)
    if not session:
        return None

    kept = [f for f in session if f.accept]
    set_aside = [f for f in session if not f.accept]
    buckets: dict[str, int] = {}
    for f in set_aside:
        b = bucket_reject_reason(f.reject_reason)
        buckets[b] = buckets.get(b, 0) + 1

    latest_dt = parse_capture_time(session[-1].timestamp_utc)
    # A clock skew (or a frame stamped slightly in the future by a mis-set camera
    # clock) must read as "just now", never as a negative age.
    since = (
        max(0.0, (ref - latest_dt).total_seconds() / 60.0)
        if latest_dt is not None else None
    )
    newest_kept = next((f for f in reversed(session) if f.accept), None)

    # "Gone quiet": the session was mid-run and the subs stopped. Everything here
    # is a narrowing of ``not active``, and each clause exists to keep the note
    # off a night that is simply *over*:
    #   * a measurable cadence (so there was a run of arrivals to stop, and so
    #     the wait is scaled to this target rather than to a fixed clock);
    #   * a session that actually got going, not six subs spanning a minute;
    #   * silence longer than that scaled wait; and
    #   * silence still inside the session gap — past it this is last night, and
    #     the recap is the surface that tells that story, not a live warning.
    start_dt = parse_capture_time(session[0].timestamp_utc)
    span_min = (
        (latest_dt - start_dt).total_seconds() / 60.0
        if latest_dt is not None and start_dt is not None else 0.0
    )
    typical = typical_gap_minutes(session)
    quiet_after = (
        quiet_after_minutes(typical, stale_minutes=stale_minutes)
        if typical is not None else None
    )
    quiet = (
        since is not None
        and quiet_after is not None
        and span_min >= QUIET_MIN_SESSION_MINUTES
        and since >= quiet_after
        and since < gap_hours * 60.0
    )

    return LiveSession(
        active=since is not None and since <= stale_minutes,
        n_frames=len(session),
        n_kept=len(kept),
        n_set_aside=len(set_aside),
        kept_exposure_s=sum(f.exposure_s or 0.0 for f in kept),
        session_exposure_s=sum(f.exposure_s or 0.0 for f in session),
        total_kept_exposure_s=total_kept_exposure_s,
        start_utc=session[0].timestamp_utc,
        latest_utc=session[-1].timestamp_utc,
        minutes_since_latest=since,
        conditions=_conditions(session),
        reject_buckets=buckets,
        newest_kept_frame_id=newest_kept.id if newest_kept is not None else None,
        quiet=quiet,
        typical_gap_minutes=typical,
        quiet_after_minutes=quiet_after,
    )


__all__ = [
    "CONDITIONS_GOOD_KEEP_RATE",
    "CONDITIONS_MIN_FRAMES",
    "CONDITIONS_POOR_KEEP_RATE",
    "CONDITIONS_WINDOW_FRAMES",
    "LIVE_STALE_MINUTES",
    "QUIET_CEILING_MINUTES",
    "QUIET_GAP_MULTIPLE",
    "QUIET_MIN_FRAMES",
    "QUIET_MIN_SESSION_MINUTES",
    "QUIET_WINDOW_FRAMES",
    "LiveConditions",
    "LiveSession",
    "live_session",
    "quiet_after_minutes",
    "typical_gap_minutes",
]
