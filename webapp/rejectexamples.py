"""*Show* me a frame you threw away — a few worked examples per reject cause.

The app already tells a beginner **how many** subs it set aside and **why**, in
plain language: :mod:`webapp.rejection_summary` turns the namespaced
``reject_reason`` tally into a handful of friendly buckets ("Cloud, haze or
moonlight — 18"). What it has never done is let them *see* one. A first-time
Seestar owner has no mental model of what "trailed" or "soft stars" looks like in
their own data, so the count is a verdict they have to take on trust — and the
one worry a beginner actually has is *"did it throw away my best frame?"*. Three
thumbnails answer that in a way no sentence can, and teach the eye at the same
time.

Nothing on the Target page reaches this today: the frames grid previews the
*selected* row, but it cannot be filtered to "the ones you called cloudy", so
getting to an example means scrolling a table of thousands looking for a reason
column. That is why this is a new surface rather than a link.

**Only the buckets whose cause is visible in the frame** (:data:`EXAMPLE_BUCKETS`).
A thumbnail is worth showing when the picture *is* the explanation — a streak
across the field, a thin star field, fat stars. It teaches nothing for "you
removed these" or "not located in the sky yet" (those subs look perfectly
ordinary), and for "couldn't be read" or "their files aren't on your disk" there
is, by construction, nothing to render. Offering a strip there would be a contact
sheet, not a lesson.

**And the example is the worst one, not the first one** — the frame the metric
the bucket is *about* ranks lowest, so what a beginner sees is a clear teaching
case rather than a borderline one. Where the bucket has no such metric (a
satellite streak is not a number this app stores), id order is the honest answer
and is stated as such below.

Pure apart from one injected filesystem question — "is this frame still on
disk?" — which is asked of at most a few dozen candidates, never of every
rejected sub. A frame whose file has gone would render as a broken thumbnail in
a strip whose whole job is to be looked at.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from seestack.io.project import first_existing_frame_path
from webapp.rejection_summary import bucket_for

#: The reject buckets (:mod:`webapp.rejection_summary`'s own keys) whose cause a
#: person can see in the frame. Everything else gets no strip — see the module
#: docstring for why each is left out.
EXAMPLE_BUCKETS: tuple[str, ...] = ("trailed", "clouds", "soft")

#: How many examples one bucket ever offers. Three is a lesson; a walk-away night
#: can reject thousands, and a contact sheet is not what this is for.
MAX_EXAMPLES_PER_BUCKET = 3

#: How many candidates per bucket are ranked before the on-disk check, so a
#: missing file costs an example rather than the strip. Bounded on purpose: this
#: is the only thing the pass retains.
_OVERSAMPLE = 4


def _rank_key(bucket: str, fwhm_px: float | None,
              star_count: int | None) -> tuple[float, float]:
    """Sort key putting the **most instructive** frame of a bucket first.

    The second element is always "did we have a number at all" (0 = yes), so an
    unmeasured frame sorts last within its bucket and is only ever used as a
    filler — it cannot displace a measured example.

    * ``soft`` — the *fattest* stars (largest ``fwhm_px``), which is the bucket's
      own metric (``auto:grade:fwhm`` and friends bucket here via
      :func:`seestack.qc.grading.metric_cause`).
    * ``clouds`` — the *fewest* stars (smallest ``star_count``), likewise.
    * ``trailed`` — no key: a satellite crossing is detected, not scored, and
      there is no stored number that says "this streak is worse than that one".
      Ranking it by a metric it is not about (star size, say) would pick a frame
      for the wrong reason, so id order — the order the rows arrive in — stands.
    """
    if bucket == "soft":
        return (-fwhm_px, 0.0) if fwhm_px is not None else (0.0, 1.0)
    if bucket == "clouds":
        return (float(star_count), 0.0) if star_count is not None else (0.0, 1.0)
    return (0.0, 0.0)


def pick_reject_examples(
    rows: Iterable[tuple],
    *,
    max_per_bucket: int = MAX_EXAMPLES_PER_BUCKET,
    readable: Callable[[str | None, str | None], str | None] = first_existing_frame_path,
) -> dict[str, list[dict[str, Any]]]:
    """``{bucket: [{"frame_id": .., "name": ..}, …]}`` for the visible buckets.

    ``rows`` is ``(id, reject_reason, fwhm_px, star_count, cached_path,
    source_path)`` over this target's **rejected** frames, in id order — i.e.
    ``Project.iter_frame_columns(…, rejected_only=True)``. A bucket with no
    usable example is absent rather than empty, so a caller never has to
    distinguish the two.

    ``readable`` is :func:`seestack.io.project.first_existing_frame_path` — the
    one definition of "which file is this frame?" — injected so the ranking can
    be tested without a filesystem. It is called at most
    ``len(EXAMPLE_BUCKETS) × max_per_bucket × _OVERSAMPLE`` times.
    """
    keep = max(1, int(max_per_bucket))
    cap = keep * _OVERSAMPLE
    # Candidates per bucket, ranked and truncated as they arrive: this pass
    # retains a few dozen tuples whatever the target's depth.
    pool: dict[str, list[tuple[tuple[float, float], int, tuple]]] = {}
    for row in rows:
        frame_id, reason, fwhm_px, star_count = row[0], row[1], row[2], row[3]
        if frame_id is None:
            continue
        # NULL is a hand-reject with no stated reason, exactly as
        # `reject_reason_counts` reads it — and "removed" is not a visible
        # bucket, so this only ever skips work.
        bucket = bucket_for(reason or "user")
        if bucket not in EXAMPLE_BUCKETS:
            continue
        cand = pool.setdefault(bucket, [])
        cand.append((_rank_key(bucket, fwhm_px, star_count), int(frame_id), row))
        if len(cand) > cap * 2:
            cand.sort(key=lambda c: (c[0], c[1]))
            del cand[cap:]

    out: dict[str, list[dict[str, Any]]] = {}
    for bucket, cand in pool.items():
        cand.sort(key=lambda c: (c[0], c[1]))
        picked: list[dict[str, Any]] = []
        for _key, frame_id, row in cand[:cap]:
            if len(picked) >= keep:
                break
            if readable(row[4], row[5]) is None:
                continue
            picked.append({"frame_id": frame_id,
                           "name": Path(row[5] or "").name})
        if picked:
            out[bucket] = picked
    # Presented in the summary's own bucket order, so the strips and the counts
    # above them read down the card in one order.
    return {b: out[b] for b in EXAMPLE_BUCKETS if b in out}
