"""**"Some of your subs came back after this picture was made."**

The app sets subs aside on its own, and it also *puts them back* on its own.
Three reconsiderations do it today: a streak flagged on a tracked extended
object rather than a satellite (:func:`seestack.qc.runner.reconcile_streak_rejections`),
a grade re-run on a now-larger population (:func:`seestack.qc.grading.apply_grade_reaccepts`),
and a missing file that reappeared (:meth:`seestack.io.project.Project.restore_missing_frames`).
All three are pure wins — the sub is good, and the app worked that out by itself.

The gap is what happens *next*. The target's published picture was stacked
before the sub came back, and the owner's live settings have ``auto_stack`` off,
so nothing re-stacks and nothing says anything. They are left looking at a
picture that is quietly thinner than their own data, with no reason on screen to
press Stack again. The "N new subs since your last stack" nudge cannot see this
case at all: it compares each sub's *capture* time against the stack, and a
restored sub was shot long before the picture was made — often on the very night
it is made of.

So this module answers one question, from one fact:

* **The fact is the restoration stamp, not a count comparison.** Deriving it
  from "more subs are ready now than the run combined" would fire forever on any
  target whose run legitimately used fewer frames than were offered (an
  alignment failure, a capped run), which is a permanent nag on an ordinary
  install. ``frames.restored_utc`` records the moment automation put a sub back,
  so "was the picture made before that?" is a comparison of two timestamps that
  are both about the app's own actions, and it is exactly right.
* **It offers; it never acts.** Re-stacking a deep target is hours of CPU on a
  NAS, and ``AGENTS.md`` §9 says new behaviour is opt-in.
* **Silence is the default and the common case.** A healthy install has no
  restorations at all, every frame written before schema 22 carries no stamp,
  and the note self-hides the moment the re-stack lands.

Pure and offline: it reads run rows and a list of stamps, and returns a verdict.
"""

from __future__ import annotations

from dataclasses import dataclass

from seestack.io.project import StackRunRow
from seestack.session_recap import parse_capture_time


@dataclass
class RestoredSubs:
    """Subs that were put back *after* this target's newest picture was stacked.

    ``n_restored`` counts only subs that are ready to stack **now** (accepted and
    plate-solved), so it is what a re-stack would actually fold in rather than
    what was reconsidered.
    """

    run_id: int
    timestamp_utc: str
    n_frames_used: int    # how many subs the picture on screen combined
    n_restored: int       # how many came back after it was made


def restored_since_stack(
    runs: list[StackRunRow], *, restored_stamps: list[str],
) -> RestoredSubs | None:
    """What the newest *genuine* run in ``runs`` (newest first, editor exports and
    combines already filtered out by the caller) missed because subs came back
    after it ran — or ``None`` when there is nothing to say.

    ``restored_stamps`` are the ``restored_utc`` values of the target's
    stack-ready subs (see :meth:`seestack.io.project.Project.restored_frame_stamps`).
    A stamp strictly later than the run's own ``timestamp_utc`` means that sub
    was set aside while the picture was being made, so the picture does not
    contain it.

    ``None`` — meaning *say nothing* — for a target with no runs, and whenever no
    stamp postdates the newest one. Both are the common case: saying nothing is
    the right default for an offer.
    """
    if not runs:
        return None
    run = runs[0]
    if run.id is None:
        return None
    ran = parse_capture_time(run.timestamp_utc)
    if ran is None:
        return None

    n = 0
    for s in restored_stamps:
        when = parse_capture_time(s)
        if when is not None and when > ran:
            n += 1
    if n <= 0:
        return None

    return RestoredSubs(
        run_id=run.id,
        timestamp_utc=run.timestamp_utc,
        n_frames_used=run.n_frames_used,
        n_restored=n,
    )


__all__ = ["RestoredSubs", "restored_since_stack"]
