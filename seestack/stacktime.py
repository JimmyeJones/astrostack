"""How long will this stack take? — answered from the target's own past runs.

The app has always been able to say how much longer a **running** stack has to
go (the Jobs page's per-step ETA), but the question a beginner actually has to
answer is the one *before* the button: a night's subs are in, it is late, and
"start it now or in the morning?" needs a number. Nothing could give one. The
Stack form already says how big the picture will be and whether it will fit in
memory; this is the third thing a person wants to know, and the only one the app
was silent about.

Nothing here models the stacker. A run's cost per sub depends on the frame size,
the storage it is read from, the calibration masters applied, the CPU it lands
on and the phase of the moon as far as this module is concerned — so instead of
predicting it, we **measure it**: every finished run records its own wall clock
(``stack_runs.duration_s``, schema 23), and the estimate is the median
seconds-per-sub of that target's own comparable past runs, multiplied by the
number of subs the new run would combine.

"Comparable" is deliberately strict, because a wrong number here costs more
trust than no number at all:

* **the same cost class** — a drizzle run does several times the per-sub work of
  a plain mean, and a two-pass κ-σ run twice that of a single streaming pass, so
  a run of a different shape says nothing about this one (:func:`stack_cost_class`);
* **a similar canvas** — the same subs reprojected onto a mosaic's union canvas
  cost more than onto a single reference frame, so a basis run whose canvas is
  wildly bigger or smaller than the planned one is not evidence for it;
* **enough subs to generalise from** — a three-frame run is mostly start-up cost,
  and dividing it by three says nothing about the per-sub rate of a thousand.

What it deliberately does *not* split on is calibration. A run that applies a
master dark and flat does a little more work per sub than one that does not, but
the sizing endpoint is never told which masters the form holds, and the extra is
a subtract and a divide against a debayer, a background fit and a reprojection —
small enough to sit inside the word "about". Splitting on a fact the caller
cannot supply would only make the estimate silent more often, which is a worse
answer than one that is a few percent out.

When nothing qualifies, :func:`estimate_stack_seconds` returns ``None`` and every
caller shows nothing. That is the honest answer on a fresh install, on a target
that has never been stacked, and on the first run after an upgrade — the column
is new, so nothing is timed yet, and the app says nothing rather than guessing.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from statistics import median
from typing import Any

__all__ = [
    "MAX_BASIS_RUNS",
    "MAX_CANVAS_RATIO",
    "MIN_BASIS_FRAMES",
    "PastStack",
    "StackTimeEstimate",
    "estimate_from_runs",
    "estimate_stack_seconds",
    "past_stack",
    "stack_cost_class",
]

#: A run has to have combined at least this many subs before its
#: seconds-per-sub is worth generalising from: below it the fixed start-up cost
#: (open the project, pick a reference, build the canvas, write the outputs)
#: dominates, so the rate it implies is the *setup's* rate, not the stack's.
MIN_BASIS_FRAMES = 8

#: How far the planned canvas may differ in area from a basis run's before that
#: run stops being evidence. The same subs cost more to reproject onto a big
#: mosaic union canvas than onto one reference frame, so a much larger or
#: smaller canvas is a different job. Generous (a factor of two either way)
#: because a repeat stack of the same target normally lands on nearly the same
#: canvas, and a mosaic's grows only when a new panel appears.
MAX_CANVAS_RATIO = 2.0

#: How many of the most recent comparable runs the median is taken over. A
#: handful smooths out one unlucky run (a night the NAS was busy) without
#: dragging in rates measured on hardware or data the target no longer has.
MAX_BASIS_RUNS = 5


@dataclass(frozen=True)
class PastStack:
    """One timed run, reduced to what predicts the next one."""

    n_frames: int          # subs actually combined
    duration_s: float      # wall clock the stacker measured around itself
    canvas_px: int         # canvas_w × canvas_h of the run's output canvas
    cost_class: str        # see :func:`stack_cost_class`


@dataclass(frozen=True)
class StackTimeEstimate:
    """What :func:`estimate_stack_seconds` found, and what it found it from."""

    seconds: float          # the estimate itself
    per_frame_s: float      # the median rate behind it
    basis_runs: int         # how many past runs the median was taken over
    basis_frames: int       # the largest sub count among them


def stack_cost_class(options: Mapping[str, Any], n_frames: int) -> str:
    """A coarse label for *how much work per sub* a run of these options does.

    Two runs in the same class are comparable; two in different classes are not,
    and no scaling factor between them is offered here on purpose — the ratios
    would be invented rather than measured.

    It is ``stacker.combine_method`` — the app's one answer to "which combine
    actually runs?", gates and silent fall-throughs included — plus the single
    distinction that function has no reason to draw: two-pass drizzle rejection
    re-drizzles every contribution, so it costs multiples of a single-pass
    drizzle and is not evidence for it.

    ``options`` is a plain mapping (a ``StackOptions`` as ``asdict``, or the
    ``options_json`` a run recorded), read for its *concrete* toggles.
    ``auto_reject`` is deliberately not resolved here: a recorded run already
    stores the method it ran with (``_resolve_auto_reject`` writes both flags
    into the options it persists), and a caller sizing a *new* run resolves it
    with that same engine function, which needs a mosaic's panel depth as well
    as the frame count. Re-deriving it from a mapping would be a second, quietly
    different resolution rule — the shape of mistake this project keeps finding.
    """
    from types import SimpleNamespace

    from seestack.stack.stacker import combine_method

    method = combine_method(
        SimpleNamespace(  # type: ignore[arg-type]  # reads three flags only
            drizzle=bool(options.get("drizzle")),
            min_max_reject=bool(options.get("min_max_reject")),
            sigma_clip=bool(options.get("sigma_clip", True)),
        ),
        int(n_frames),
    )
    if method == "drizzle" and options.get("drizzle_reject"):
        return "drizzle+reject"
    return method


def past_stack(run: Any) -> PastStack | None:
    """Reduce a ``stack_runs`` row to a :class:`PastStack`, or ``None``.

    ``None`` means "this row is not evidence": it predates the timing column, it
    was written by something that is not a stack (an editor export, a channel
    combine), it recorded no usable duration or canvas, or its options can't be
    read back. Callers filter rather than judge, so a corrupt row costs the
    estimate a data point and never an exception.
    """
    duration = getattr(run, "duration_s", None)
    if duration is None:
        return None
    try:
        seconds = float(duration)
        n_frames = int(run.n_frames_used)
        canvas_px = int(run.canvas_w) * int(run.canvas_h)
        options = json.loads(run.options_json or "{}")
    except (AttributeError, TypeError, ValueError):
        return None
    if not isinstance(options, dict):
        return None
    if seconds <= 0 or n_frames <= 0 or canvas_px <= 0:
        return None
    return PastStack(n_frames=n_frames, duration_s=seconds, canvas_px=canvas_px,
                     cost_class=stack_cost_class(options, n_frames))


def estimate_stack_seconds(history: Iterable[PastStack], *,
                           n_frames: int,
                           canvas_px: int,
                           cost_class: str) -> StackTimeEstimate | None:
    """How long a stack of ``n_frames`` subs onto a ``canvas_px`` canvas is
    likely to take, from this target's own comparable runs.

    ``history`` is in any order; the most recent runs should come first if the
    caller has that order, since only the first :data:`MAX_BASIS_RUNS` matches
    are used. Returns ``None`` whenever there is no honest answer — no matching
    run, none big enough to generalise from, or a canvas too different to
    compare — and the caller then shows nothing at all.
    """
    if n_frames <= 0 or canvas_px <= 0:
        return None
    basis: list[PastStack] = []
    for run in history:
        if run.cost_class != cost_class or run.n_frames < MIN_BASIS_FRAMES:
            continue
        ratio = run.canvas_px / float(canvas_px)
        if not (1.0 / MAX_CANVAS_RATIO) <= ratio <= MAX_CANVAS_RATIO:
            continue
        basis.append(run)
        if len(basis) >= MAX_BASIS_RUNS:
            break
    if not basis:
        return None
    rate = float(median(r.duration_s / r.n_frames for r in basis))
    return StackTimeEstimate(
        seconds=rate * n_frames,
        per_frame_s=rate,
        basis_runs=len(basis),
        basis_frames=max(r.n_frames for r in basis),
    )


def estimate_from_runs(runs: Sequence[Any], *, n_frames: int, canvas_px: int,
                       cost_class: str) -> StackTimeEstimate | None:
    """:func:`estimate_stack_seconds` over raw ``stack_runs`` rows — the form
    every caller in this app actually holds. Rows that are not evidence are
    dropped (see :func:`past_stack`) rather than rejected."""
    history = [p for p in (past_stack(r) for r in runs) if p is not None]
    return estimate_stack_seconds(history, n_frames=n_frames,
                                  canvas_px=canvas_px, cost_class=cost_class)
