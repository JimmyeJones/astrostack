"""**"This picture was made by an older AstroStack"** — what stacking it again
would *give you*, in facts rather than version numbers.

The app grew columns over time, and a run only ever gets the ones that existed
when it ran. Most of what an old run is missing can be healed from disk later —
its coverage share (:mod:`seestack.coverage_backfill`) and its panel-seam figure
both are — but **when its subs were shot cannot be**, because nothing on disk
records *which frames that run used*. So a picture stacked before the app learned
to record that carries no capture window and no night count, and every surface
that dates it — the caption, the nameplate, the share sheet, the Gallery card,
the History row, the Sky footprint — falls back to saying when the *stack ran*.
On a re-stack of a back catalogue that is years out, and it stays that way
forever: nothing anywhere tells the owner the one thing that would fix it, which
is to press Stack again.

This module is that missing sentence, and it is deliberately narrow:

* **It names a gain, never a version.** "Your version is old" is not a reason a
  beginner can act on, and a table of which release added which column would go
  stale the moment anyone edited it. The only input is the run's own NULLs.
* **It never promises something a re-stack couldn't deliver.** A window is
  missing for two different reasons — the app didn't record windows yet, *or*
  the subs carry no capture time at all — and only the first is fixable. So the
  offer is gated on the target's own accepted frames actually being datable
  *now*, which is checkable, rather than on a version comparison, which is not.
* **It offers; it never acts.** Re-stacking is hours of CPU on a NAS, and §9
  says new behaviour is opt-in.

Pure and offline: it reads run rows and two frame counts, and returns a verdict.
"""

from __future__ import annotations

from dataclasses import dataclass

from seestack.io.project import StackRunRow

# What share of a target's accepted subs must carry a capture time before the app
# will claim that re-stacking would date the picture. A majority, because the
# window is only as honest as the frames behind it: on a target where one sub in
# five hundred happens to be datable, a re-stack *would* record a window — a
# single-night one that misdescribes a picture made of five. Below this the
# offer stays silent rather than promising a date it would get wrong.
MIN_DATABLE_SHARE = 0.5


@dataclass
class RestackGain:
    """What re-stacking this target's newest picture would add, and what it costs.

    Both flags are about the same missing fact at different resolutions — *when*
    the subs were shot, and how many *nights* they came from — because the two
    are recorded separately and an intermediate run can have the first without
    the second. Nothing here is a version comparison.
    """

    run_id: int
    timestamp_utc: str
    n_frames_used: int          # how many subs the old picture combined
    n_frames_ready: int         # how many accepted subs a re-stack would combine
    # The picture can't say which nights it is made from at all — every surface
    # that dates it falls back to when the stack ran.
    missing_capture_window: bool
    # It knows the window but not the count, so a caption can name two dates but
    # never say "over four nights" — the part a person says out loud.
    missing_night_count: bool


def restack_gain(
    runs: list[StackRunRow], *, n_accepted: int, n_accepted_datable: int,
) -> RestackGain | None:
    """What the newest *genuine* run in ``runs`` (newest first, editor exports and
    combines already filtered out by the caller) would gain from a re-stack, or
    ``None`` when there is nothing honest to offer.

    ``None`` — meaning *say nothing* — for a target with no runs, for a picture
    that already records everything this can check, and for one whose subs are
    not datable enough for a re-stack to fix the gap (see
    :data:`MIN_DATABLE_SHARE`). Saying nothing is the common case and the right
    default: this is an offer, and an offer that can't deliver is worse than
    silence.
    """
    if not runs:
        return None
    run = runs[0]
    if run.id is None:
        return None

    missing_window = not run.capture_start_utc
    missing_nights = bool(run.capture_start_utc) and not run.capture_hours_json
    if not missing_window and not missing_nights:
        return None

    # Only offer what a re-stack could actually supply: the frames it would
    # combine have to carry the capture times the old run is missing.
    if n_accepted_datable <= 0:
        return None
    if n_accepted_datable < MIN_DATABLE_SHARE * max(n_accepted, 1):
        return None

    return RestackGain(
        run_id=run.id,
        timestamp_utc=run.timestamp_utc,
        n_frames_used=run.n_frames_used,
        n_frames_ready=n_accepted,
        missing_capture_window=missing_window,
        missing_night_count=missing_nights,
    )


__all__ = ["MIN_DATABLE_SHARE", "RestackGain", "restack_gain"]
