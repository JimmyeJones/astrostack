"""Your cleanest shot so far — offer to promote a newer, cleaner stack to cover.

A target's **cover** is the picture the Library tile, "My best pictures", the
montage wall and the gallery's "best" endpoint all show. It defaults to the
newest stack, but the owner can *pin* a run as the cover ("Set as cover" in
History) — and once pinned it stays pinned forever.

That is the right default (they may have pinned a favourite framing, or a
hand-edited version), but it has a quiet cost: a beginner who keeps adding subs
gets steadily *cleaner* stacks night after night, while every showcase surface
keeps showing the older, noisier picture they pinned once. Nothing in the app
ever mentions the gap.

This module is the pure, offline half of the nudge: given a target's genuine
stack runs (newest first) and its pinned cover id, decide whether the newest
stack is *materially* cleaner than the cover — and by how much. It only ever
**suggests**; promoting the cover stays the user's one-tap decision, through the
same ``set-cover`` path they already have (AGENTS.md §9/§10: new behaviour is
opt-in, never an auto-swap of something the user chose).

Read-only and side-effect free, so it is safe to call on every page load.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from seestack.io.project import StackRunRow

#: How much cleaner the newest stack must be before we say anything, as a ratio
#: of its background-noise σ to the cover's.
#:
#: 0.85 = "at least 15 % less background grain". Two stacks of the same target on
#: the same night differ by a few percent for reasons nobody can see (which subs
#: made the cut, where the σ patch landed), so a tighter threshold would fire on
#: noise about noise and train the owner to ignore the nudge. 15 % is roughly
#: what going from ~40 to ~55 subs buys you (σ falls as 1/√N), i.e. a genuine
#: extra session's worth of data — visible in the picture, and worth a mention.
CLEANER_RATIO = 0.85


@dataclass(frozen=True)
class CleanestShot:
    """The newest stack is materially cleaner than the pinned cover."""

    #: The newest genuine stack (the candidate).
    run_id: int
    #: The run currently pinned as the target's cover.
    cover_run_id: int
    #: Both runs' normalized background-noise σ (lower = cleaner).
    noise_sigma: float
    cover_noise_sigma: float
    #: How much less background grain the candidate has, as a whole percent of
    #: the cover's σ (e.g. 20 for "about 20 % less grain"). Always ≥ 1.
    percent_cleaner: int
    #: How many frames each combined, so the UI can say *why* it got cleaner.
    n_frames_used: int
    cover_n_frames_used: int
    #: When the candidate was stacked (ISO UTC), for "this stack from last night".
    timestamp_utc: str


def _usable_sigma(run: StackRunRow) -> float | None:
    """A run's noise σ when it is a finite, positive number, else ``None``.

    Runs stacked before schema 6 carry ``None``, and a σ of 0 (or a NaN that
    slipped through a degenerate measurement) can't be compared as a ratio — in
    every one of those cases the honest answer is to say nothing at all.
    """
    sigma = run.noise_sigma
    if sigma is None:
        return None
    try:
        value = float(sigma)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value) or value <= 0.0:
        return None
    return value


def cleanest_shot(
    genuine_runs: Sequence[StackRunRow],
    cover_run_id: int | None,
    *,
    ratio: float = CLEANER_RATIO,
) -> CleanestShot | None:
    """Should we offer to make the newest stack this target's cover?

    ``genuine_runs`` is the target's *genuine* stack runs, newest first — the
    caller filters out editor-export / channel-combine runs, whose σ isn't
    measured on the same kind of image and so can't be compared like with like.

    Returns ``None`` — say nothing — whenever any of these hold:

    * nothing is pinned (``cover_run_id`` is ``None``): the cover already *is*
      the newest stack, so there is no gap to close;
    * the pinned run is the newest one, or isn't among the genuine runs at all
      (pruned, or an editor export pinned by hand — not comparable);
    * either run has no usable σ (pre-schema-6 runs, or a degenerate measure);
    * the newest stack isn't materially cleaner (σ above ``ratio`` × the
      cover's) — including the common case where it is *noisier*.
    """
    if cover_run_id is None or not genuine_runs:
        return None
    newest = genuine_runs[0]
    if newest.id is None or newest.id == cover_run_id:
        return None
    cover = next((r for r in genuine_runs if r.id == cover_run_id), None)
    if cover is None:
        return None
    new_sigma = _usable_sigma(newest)
    cover_sigma = _usable_sigma(cover)
    if new_sigma is None or cover_sigma is None:
        return None
    if new_sigma > cover_sigma * ratio:
        return None
    # Round *down* so the headline never overstates the improvement, and floor at
    # 1 % so a nudge that fired can't claim "0 % cleaner" through rounding.
    percent = max(1, int((1.0 - new_sigma / cover_sigma) * 100.0))
    return CleanestShot(
        run_id=newest.id,
        cover_run_id=cover_run_id,
        noise_sigma=new_sigma,
        cover_noise_sigma=cover_sigma,
        percent_cleaner=percent,
        n_frames_used=newest.n_frames_used,
        cover_n_frames_used=cover.n_frames_used,
        timestamp_utc=newest.timestamp_utc,
    )
