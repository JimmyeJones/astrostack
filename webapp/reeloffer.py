"""Should the app offer to build a target's night-by-night reel?

The owner asked for a progression video — *"ordered by when the subs were shot,
so I can see how my added frames affect targets"* — and the app can now produce
one two ways. Neither reaches the shape a walk-away install most often has.

* ``StackOptions.save_progress`` makes an ordinary stack emit the cumulative
  by-night snapshots (v0.483.0), which is exactly the ask — but it is an
  *advanced* field on the Stack form and it is off by default, so nobody finds
  it.
* :func:`webapp.capture_nights.cumulative_night_steps` finds the same reel in a
  history that already nests (v0.486.0) — but only for a target the owner
  re-stacked as the nights came in.

*"I stacked this target once, across six nights"* falls between them: the subs
for the reel are all there, the switch that would have caught them was never
found, and the "night after night" card self-hides because there is only one
stack. This module decides when to say so — the offer is the missing affordance,
not a new capability.

Pure and duck-typed over the run row (``id``, ``n_frames_used``,
``options_json``, ``capture_hours_json``, ``duration_s``), so the decision is
unit-testable on its own and cannot drift from the copy that renders it.

**It is deliberately hard to trigger.** The card has never appeared on a
single-stack target, so every gate below exists to keep it from becoming a nag:

* exactly **one** stack with a master on disk (two or more already have the
  cross-run reel);
* that run has **no reel of its own** already — offering to build what is
  sitting beside the master would be nonsense;
* at least :data:`MIN_REEL_NIGHTS` observing nights, counted **both** the
  owner's way and the engine's. :func:`seestack.stack.stacker.plan_capture_nights`
  buckets at UTC noon (the engine has no longitude) while every night surface in
  the webapp buckets at the observer's local noon, so a run sitting on that
  boundary can be three nights to one and two to the other. Requiring both
  keeps the card's promise true whichever way the stack reads it;
* and the run must not have been **re-ordered**: lucky imaging sorts the frame
  list by FWHM, which is the one case ``plan_capture_nights`` names as a lie —
  it snapshots a cumulative accumulator, so "nights 1-2" is only true while no
  night-3 sub has gone in.

Anything unknown answers "no offer". A run from before the app recorded its
capture hours cannot be *shown* to hold three nights, and an offer resting on a
guess is worse than silence.
"""

from __future__ import annotations

import json
from typing import Any

from webapp.capture_nights import capture_night_count

#: Fewest observing nights worth offering a reel for. Mirrors
#: ``seestack.stack.stacker._PROGRESS_MIN_FRAMES`` — the floor
#: ``plan_capture_nights`` itself refuses to go below, because one or two nights
#: is not a progression — so the app never offers a clip the stacker would then
#: decline to label by night.
MIN_REEL_NIGHTS = 3


def _reorders_frames(options_json: str | None) -> bool:
    """Would this run's options hand the stacker its frames out of capture order?

    Only lucky imaging does (``lucky_fraction < 1`` sorts by FWHM), and it is the
    case ``plan_capture_nights`` explicitly refuses. Unreadable options answer
    ``False`` — the permissive direction, whose worst case is the evenly-spaced
    reel this card's copy does not promise, never a wrong picture.
    """
    if not options_json:
        return False
    try:
        opts = json.loads(options_json)
    except (TypeError, ValueError):
        return False
    if not isinstance(opts, dict):
        return False
    try:
        return float(opts.get("lucky_fraction", 1.0)) < 1.0
    except (TypeError, ValueError):
        return False


def night_reel_offer(
    run: Any | None,
    *,
    n_stacks: int,
    lon_deg: float | None = None,
    has_reel: bool = False,
) -> dict[str, Any] | None:
    """The offer payload for this target, or ``None`` to say nothing.

    ``run`` is the target's one stack run (the single step of its deepening
    series); ``n_stacks`` is how many steps that series has; ``has_reel`` says
    whether a ``{stem}_progress`` sibling already sits beside the master.

    The payload carries only what the sentence needs — which run to pre-fill the
    Stack form from, how many nights it holds, how many subs it combined, and how
    long it took last time (``None`` for a run recorded before ``duration_s``, so
    the card drops the clause rather than guessing at a number).
    """
    if run is None or n_stacks != 1 or has_reel:
        return None
    run_id = getattr(run, "id", None)
    if run_id is None:
        return None
    if _reorders_frames(getattr(run, "options_json", None)):
        return None

    hours = getattr(run, "capture_hours_json", None)
    # Both bucketings, for the reason in the module docstring: the count the card
    # prints follows the owner's longitude, and the count the *stacker* will use
    # is UTC-noon. The card may only speak where they agree it is a progression.
    local_nights = capture_night_count(hours, lon_deg)
    utc_nights = capture_night_count(hours, None)
    if local_nights is None or utc_nights is None:
        return None
    if min(local_nights, utc_nights) < MIN_REEL_NIGHTS:
        return None

    duration = getattr(run, "duration_s", None)
    return {
        "run_id": int(run_id),
        # Named the owner's way — the same number the Nights card shows.
        "nights": int(local_nights),
        "subs": int(getattr(run, "n_frames_used", 0) or 0),
        "last_duration_s": (
            float(duration)
            if isinstance(duration, (int, float)) and not isinstance(duration, bool)
            and duration > 0 else None
        ),
    }
