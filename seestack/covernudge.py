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

:func:`grainier_newest` is the **mirror case**, for the state a beginner is
actually in: with *nothing* pinned the cover simply follows the newest stack, so
a hazy night's restack silently replaces a better picture with a grainier one on
every showcase surface, with nothing said. Same shape, same one-tap ``set-cover``
— it just offers the *earlier*, cleaner run instead. The two are mutually
exclusive by construction (one needs a pin, the other needs none), so they can
never both speak.

Both halves compare **one number** — each run's stored ``noise_sigma`` — so both
can only compare two pictures of the same sky. The module already refuses a
comparison across run *kinds* for that reason (an editor export's σ is not
measured on the same kind of image); :data:`MIN_SKY_SHARE` refuses one that
would put a materially *smaller* picture on show, which is the same refusal
across canvases.

Read-only and side-effect free, so it is safe to call on every page load.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
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

#: How much of the sky the picture *on show* covers that an offered replacement
#: must cover too, before either nudge will call it the better picture.
#:
#: ``noise_sigma`` is normalized to **its own image's** robust range
#: (:func:`seestack.edit.noise.estimate_noise_sigma`), measured over the whole
#: canvas, so it answers "how grainy is this picture?" and not "how deep is this
#: target?". Across two canvases of *different* sky that is no longer a like-for
#: -like comparison, and a growing mosaic is where it bites: the owner opens a new
#: panel, it holds one sub for a night, the whole canvas measures grainier for it
#: — and the nudge offered to put the earlier, **half-size** picture back on the
#: Library tile, "My best pictures" and the montage wall, where a pin stays
#: forever and the mosaic being built would never show again. "Grainier" was true
#: and "the better picture" was not. What that state actually needs is "keep
#: shooting the new panel", which the Target page's own thin-stack and
#: next-best-move lines already say (``frontend/src/components/target/
#: thinStack.ts``, ``nextBestMove.ts``) — so the honest answer here is silence,
#: not a second sentence.
#:
#: Measured by stacking real subsets of the bundled 2×2 mosaic sample through
#: ``run_stack`` (``webapp.sample_data``, ``shape="mosaic"``): a restack of the
#: **same** sky moves the canvas by 0.3–0.6 % (21 subs → 11 subs is 3.63 → 3.62
#: field-fulls, and still fires at 31 % grainier, which is this nudge's whole
#: point), while one added panel is **+83 % to +263 %**. The pair that fired on
#: growth alone: one panel six subs deep (σ 0.00074) → two panels with a single
#: sub on the new one (σ 0.00089) — "20 % more grain", and half the sky. 0.9
#: therefore sits an order of magnitude above the same-sky wobble and far below
#: the smallest real loss of sky there is: it separates the two cases rather than
#: tuning between them.
MIN_SKY_SHARE = 0.9


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


def _usable_fields(value: float | None) -> float | None:
    """A canvas's sky extent in field-fulls when it is a finite positive number,
    else ``None`` — the same "say nothing rather than guess" rule
    :func:`_usable_sigma` applies to σ, and the one
    :func:`webapp.field_fulls.field_fulls_of_sky` already answers ``None`` with.
    """
    if value is None:
        return None
    try:
        fields = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(fields) or fields <= 0.0:
        return None
    return fields


def _offer_loses_sky(
    candidate_id: int,
    shown_id: int,
    sky_fields: Mapping[int, float | None] | None,
    *,
    min_share: float,
) -> bool:
    """Would showing ``candidate_id`` instead of ``shown_id`` put a materially
    smaller piece of sky on every showcase surface? (See :data:`MIN_SKY_SHARE`.)

    ``sky_fields`` maps a run id to how many single-frame field-fulls of sky its
    canvas covers (:func:`webapp.field_fulls.field_fulls_of_sky`, which the
    History listing and the wall's ranking already read). A map that is absent,
    or that cannot answer for *both* runs, answers ``False`` — "no opinion" —
    which is byte for byte what every caller did before this existed: a single
    field, an older install, a canvas whose native frame shape cannot be read.
    So this can only ever **silence** a nudge, never raise one.
    """
    if not sky_fields:
        return False
    candidate = _usable_fields(sky_fields.get(candidate_id))
    shown = _usable_fields(sky_fields.get(shown_id))
    if candidate is None or shown is None:
        return False
    return candidate < shown * min_share


def cleanest_shot(
    genuine_runs: Sequence[StackRunRow],
    cover_run_id: int | None,
    *,
    ratio: float = CLEANER_RATIO,
    sky_fields: Mapping[int, float | None] | None = None,
    min_sky_share: float = MIN_SKY_SHARE,
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
      cover's) — including the common case where it is *noisier*;
    * promoting it would put a materially **smaller** piece of sky on show than
      the pinned cover does (``sky_fields``, :data:`MIN_SKY_SHARE`) — a stack of
      fewer panels than the pinned mosaic measures cleaner for its own depth, and
      "cleaner" is not a reason to hide sky the owner has already shot.
      ``sky_fields`` is optional and omitting it is exactly today's behaviour.
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
    if _offer_loses_sky(newest.id, cover_run_id, sky_fields,
                        min_share=min_sky_share):
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
class GrainierNewest:
    """The newest stack — which, unpinned, *is* the cover — came out materially
    grainier than an earlier one the target already has."""

    #: The earlier, cleaner run we're offering to pin (the better picture).
    run_id: int
    #: The newest run, i.e. what every showcase surface is showing right now.
    newest_run_id: int
    #: Both runs' normalized background-noise σ (lower = cleaner).
    noise_sigma: float
    newest_noise_sigma: float
    #: How much *more* background grain the newest one has, as a whole percent of
    #: the better run's σ (e.g. 30 for "about 30 % more grain"). Always ≥ 1.
    percent_grainier: int
    #: How many frames each combined, so the UI can say *why* without guessing.
    n_frames_used: int
    newest_n_frames_used: int
    #: When the better run was stacked (ISO UTC), for "your 14 May one".
    timestamp_utc: str


def grainier_newest(
    genuine_runs: Sequence[StackRunRow],
    cover_run_id: int | None,
    *,
    ratio: float = CLEANER_RATIO,
    sky_fields: Mapping[int, float | None] | None = None,
    min_sky_share: float = MIN_SKY_SHARE,
) -> GrainierNewest | None:
    """Should we offer to pin an earlier, cleaner stack as the cover?

    The mirror of :func:`cleanest_shot`. With **nothing pinned** the cover follows
    the newest stack, so a restack through haze — or one where auto-reject set a
    lot of subs aside — quietly demotes a better picture on the Library tile, "My
    best pictures" and the montage wall, and the app never mentions it. This spots
    exactly that, and offers the same one-tap ``set-cover`` in the other
    direction. It never pins anything by itself.

    ``genuine_runs`` is the target's *genuine* stack runs, newest first (the
    caller filters out editor-export / channel-combine runs, whose σ isn't
    measured on the same kind of image). The run offered is the **cleanest**
    earlier one, not merely the previous one.

    Returns ``None`` — say nothing — whenever any of these hold:

    * something *is* pinned (``cover_run_id`` is not ``None``): the cover is the
      user's own choice and can't drift, which is :func:`cleanest_shot`'s case,
      not this one;
    * there is no earlier genuine run to fall back to;
    * either run has no usable σ (pre-schema-6 runs, or a degenerate measure);
    * the newest stack isn't materially grainier (the best earlier σ is above
      ``ratio`` × the newest's) — including the common, happy case where the
      newest is the cleanest the target has;
    * every earlier run that *is* cleaner covers materially less sky than the
      newest one does (``sky_fields``, :data:`MIN_SKY_SHARE`) — a growing mosaic
      measures grainier for the panel it has just opened, and offering the
      half-size picture instead would hide the sky being added. An earlier run of
      the **same** sky is still offered, which is this nudge's actual case (haze,
      or a night most of whose subs were set aside), so the filter sits on the
      candidate rather than on the verdict. ``sky_fields`` is optional and
      omitting it is exactly today's behaviour.
    """
    if cover_run_id is not None or not genuine_runs:
        return None
    newest = genuine_runs[0]
    if newest.id is None:
        return None
    new_sigma = _usable_sigma(newest)
    if new_sigma is None:
        return None
    # The best earlier run wins ties by recency: `min` keeps the first of equal
    # sigmas and the list is newest-first, so a beginner is offered the most
    # recent of two equally-clean pictures rather than the oldest.
    best: StackRunRow | None = None
    best_sigma: float | None = None
    for run in genuine_runs[1:]:
        if run.id is None or run.id == newest.id:
            continue
        sigma = _usable_sigma(run)
        if sigma is None:
            continue
        if _offer_loses_sky(run.id, newest.id, sky_fields,
                            min_share=min_sky_share):
            continue
        if best_sigma is None or sigma < best_sigma:
            best, best_sigma = run, sigma
    if best is None or best_sigma is None or best.id is None:
        return None
    if best_sigma > new_sigma * ratio:
        return None
    # Round *down* so the headline never overstates how much worse it got, and
    # floor at 1 % so a nudge that fired can't claim "0 % grainier".
    percent = max(1, int((new_sigma / best_sigma - 1.0) * 100.0))
    return GrainierNewest(
        run_id=best.id,
        newest_run_id=newest.id,
        noise_sigma=best_sigma,
        newest_noise_sigma=new_sigma,
        percent_grainier=percent,
        n_frames_used=best.n_frames_used,
        newest_n_frames_used=newest.n_frames_used,
        timestamp_utc=best.timestamp_utc,
    )
