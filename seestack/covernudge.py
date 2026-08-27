"""Which of a target's stacks should be on show — the two halves of one question.

A target's **cover** is the picture the Library tile, "My best pictures", the
montage wall and the gallery's "best" endpoint all show. It defaults to the
newest stack, but the owner can *pin* a run as the cover ("Set as cover" in
History) — and once pinned it stays pinned forever.

Both of those states can quietly show the wrong picture, in opposite ways, so
this module holds one function for each. They are **mutually exclusive by
construction** — the first needs a pin, the second needs none — so the app can
call both and never say two things at once.

:func:`cleanest_shot` — **something is pinned.** Staying pinned is the right
default (they may have pinned a favourite framing, or a hand-edited version), but
a beginner who keeps adding subs gets steadily *cleaner* stacks night after
night, while every showcase surface keeps showing the older, noisier picture they
pinned once. Nothing in the app ever mentions the gap.

:func:`grainier_default` — **nothing is pinned**, which is the state a beginner
is actually in, and the one where the *default* can go backwards. With no pin the
cover means "newest", so a restack through haze — or one where auto-reject set a
lot of subs aside — produces a legitimately newer stack with a materially
**higher** σ than one the target already has, and every showcase surface switches
to it with nothing said. That is a silent quality regression on the owner's exact
walk-away workflow, and the whole point of the app is that it can be trusted not
to do that quietly.

Both only ever **suggest**; changing the cover stays the user's one-tap decision,
through the same ``set-cover`` path they already have (AGENTS.md §9/§10: new
behaviour is opt-in, never an auto-swap of something the user chose).

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


@dataclass(frozen=True)
class GrainierDefault:
    """Nothing is pinned, and the newest stack — which is therefore what every
    showcase surface shows — is materially grainier than one this target already
    has."""

    #: The earlier, cleaner run worth putting on show (the suggestion).
    run_id: int
    #: The newest genuine run: what the unpinned cover is showing right now.
    newest_run_id: int
    #: Both runs' normalized background-noise σ (lower = cleaner).
    noise_sigma: float          # the newest (grainier) one
    best_noise_sigma: float     # the earlier, cleaner one
    #: How much *more* background grain the newest has, as a whole percent of the
    #: better run's σ (e.g. 30 for "about 30 % more grain"). Always ≥ 1.
    percent_grainier: int
    #: How many frames each combined, so the UI can hint at *why*.
    n_frames_used: int
    best_n_frames_used: int
    #: When each was stacked (ISO UTC), so the note can date the better picture.
    timestamp_utc: str
    best_timestamp_utc: str


def grainier_default(
    genuine_runs: Sequence[StackRunRow],
    cover_run_id: int | None,
    *,
    ratio: float = CLEANER_RATIO,
) -> GrainierDefault | None:
    """Should we offer to pin an earlier, cleaner stack instead of the newest?

    The mirror of :func:`cleanest_shot`, for the case that one deliberately
    leaves out: with **nothing pinned** there is no cover to compare against, so
    that function stays silent by design — but that is exactly the state where
    the default itself can regress, because "no pin" means "show the newest".

    ``genuine_runs`` is the target's *genuine* stack runs, newest first — same
    contract as :func:`cleanest_shot`, and for the same reason: an editor-export
    or channel-combine run's σ isn't measured on the same kind of image, so it
    can't be compared like with like.

    The comparison is deliberately against the target's **best** earlier stack,
    not its previous one: what the owner loses when the cover moves is the best
    picture they had, and a beginner asked to compare against "the one before"
    would rightly wonder why the app is not pointing at the good one.

    Returns ``None`` — say nothing — whenever any of these hold:

    * something *is* pinned (``cover_run_id`` is not ``None``): the cover isn't
      following the newest stack, so it cannot have moved on its own. This is
      also what makes this function and :func:`cleanest_shot` mutually exclusive;
    * there are fewer than two genuine runs, or the newest has no id;
    * either side has no usable σ (pre-schema-6 runs, or a degenerate measure);
    * no earlier run is materially cleaner — i.e. the best earlier σ is not below
      ``ratio`` × the newest's. That includes the ordinary, happy case where the
      newest stack is the cleanest one the target has.
    """
    if cover_run_id is not None or len(genuine_runs) < 2:
        return None
    newest = genuine_runs[0]
    if newest.id is None:
        return None
    new_sigma = _usable_sigma(newest)
    if new_sigma is None:
        return None
    best: StackRunRow | None = None
    best_sigma: float | None = None
    for run in genuine_runs[1:]:
        if run.id is None:
            continue
        sigma = _usable_sigma(run)
        if sigma is None:
            continue
        if best_sigma is None or sigma < best_sigma:
            best, best_sigma = run, sigma
    if best is None or best_sigma is None:
        return None
    # Same bar as the other direction, read the other way round: the good one
    # must be at least (1 − ratio) cleaner than what's on show.
    if best_sigma > new_sigma * ratio:
        return None
    # Round *down* so the headline never overstates the regression, and floor at
    # 1 % so a nudge that fired can't claim "0 % grainier" through rounding.
    percent = max(1, int((new_sigma / best_sigma - 1.0) * 100.0))
    return GrainierDefault(
        run_id=best.id,
        newest_run_id=newest.id,
        noise_sigma=new_sigma,
        best_noise_sigma=best_sigma,
        percent_grainier=percent,
        n_frames_used=newest.n_frames_used,
        best_n_frames_used=best.n_frames_used,
        timestamp_utc=newest.timestamp_utc,
        best_timestamp_utc=best.timestamp_utc,
    )
