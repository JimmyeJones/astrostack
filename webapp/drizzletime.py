"""What an automatic drizzle will cost — the numbers behind the sentence.

The owner's pictures were coming out at the sensor's own resolution, so v0.494.0
let an unattended run drizzle itself when the subs can pay for it ("Auto, when
worth it"). v0.494.2 then measured what saying yes costs: about **×7 the per-sub
time of a plain stack**, which on his 5,477-sub target turns about an hour of
stacking into most of a day's. Asked whether a hands-off run should decline a
long one, he chose **(c): tell me the estimate before it starts and let it run**
— explicitly not a refusal and not a threshold (sign-off item 19, answered
2026-10-13).

This module is the "tell me" half. It is pure arithmetic over two things the app
already measures, so nothing here models the stacker:

* his own **seconds-per-sub**, the median of this target's comparable finished
  runs (:func:`seestack.stacktime.estimate_from_runs`), and
* the measured **drizzle ratio** for the cost class the run will actually be
  recorded as (``seestack.stack.autodrizzle.DRIZZLE_COST_RATIO``).

Which of the two the drizzle figure stands on matters, and the preference is
deliberate: when the target has comparable *drizzled* runs, the estimate is read
straight off them and the ratio is not used at all — a measurement of the job
in hand beats a measurement of a different job times a constant. The ratio is
the fallback for the ordinary case, which is a target that has only ever been
stacked plain, and it is also what turns a drizzled rate back into the "a plain
stack would take about …" comparison the owner's sentence makes.

When neither is available — a fresh install, a target stacked for the first time
— there is no number, and the caller says *"this will take several times longer
than a normal stack"* rather than inventing one. That sentence is true from the
measurement alone and needs no history, which is why the "no estimate" case is a
different wording rather than silence: the whole point of the owner's answer is
that an automatic drizzle never starts a long run without saying so.

Nothing here refuses, thresholds or gates: the run proceeds either way. The two
one-click actions the note carries (cancel, and *don't auto-drizzle this
target*) live with the surfaces that draw them.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from seestack.stack.autodrizzle import DRIZZLE_COST_RATIO

__all__ = ["AutoDrizzleCost", "price_auto_drizzle"]


@dataclass(frozen=True)
class AutoDrizzleCost:
    """What a running automatic drizzle costs, as numbers for one sentence.

    Both second counts are ``None`` together or present together: the comparison
    is the point of the sentence, and half of it would read as a promise about
    the other half. ``measured`` says whether they came from *this target's own*
    timed runs rather than from the ratio alone — which is never true with no
    history at all, since the ratio multiplies a rate that does not exist.
    """

    #: Super-resolution scale the run chose (1.2–1.5).
    scale: float
    #: Estimated wall clock of the drizzled run, or ``None`` with no history.
    drizzle_seconds: float | None
    #: …and of the plain stack it is replacing, for the comparison.
    plain_seconds: float | None
    #: How many of the target's past runs the rate was taken over (0 for none).
    basis_runs: int
    #: ``False`` when every basis run was timed by a different build, so the
    #: surface can say the real time may differ — the same caveat the Stack
    #: form's own estimate carries (observer issue #933).
    same_engine: bool

    @property
    def measured(self) -> bool:
        """Did this come from the owner's own runs?"""
        return self.drizzle_seconds is not None

    def as_dict(self) -> dict[str, Any]:
        """The JSON a job row carries. Flat, and every key always present, so a
        surface reading it never has to tell "absent" from "unknown"."""
        return {
            "scale": round(float(self.scale), 4),
            "drizzle_seconds": (None if self.drizzle_seconds is None
                                else round(float(self.drizzle_seconds), 1)),
            "plain_seconds": (None if self.plain_seconds is None
                              else round(float(self.plain_seconds), 1)),
            "basis_runs": int(self.basis_runs),
            "same_engine": bool(self.same_engine),
        }


def price_auto_drizzle(
    runs: Sequence[Any],
    *,
    scale: float,
    n_frames: int,
    canvas_px: int,
    cost_class: str,
    plain_cost_class: str,
    engine_version: str | None = None,
) -> AutoDrizzleCost:
    """Price the drizzle an unattended run has just chosen.

    ``runs`` is this target's newest ``stack_runs`` rows, newest first — the same
    sequence ``/stack-estimate`` reads, and rows that are not evidence are
    dropped by :func:`seestack.stacktime.past_stack` rather than rejected.
    ``cost_class`` and ``plain_cost_class`` come from the engine
    (``AutoDrizzleRun``), which is the only place that knows both without
    re-resolving ``auto_reject`` and the ``drizzle_reject`` affordability check.

    Always returns a cost: with no usable history both second counts are
    ``None`` and the caller falls back to the wording that needs no number.
    """
    from seestack.stacktime import estimate_from_runs

    def _estimate(klass: str) -> Any:
        return estimate_from_runs(runs, n_frames=int(n_frames),
                                  canvas_px=int(canvas_px), cost_class=klass,
                                  engine_version=engine_version)

    drizzled = _estimate(cost_class)
    plain = _estimate(plain_cost_class)
    # The ratio between the two classes, used only to fill in whichever side has
    # no runs of its own. ``None`` for a class the measurement does not cover (a
    # class that is not a drizzle at all, which the engine cannot hand us, or a
    # future one) — and then the side with no runs simply has no number, which
    # is the honest answer rather than a guess at a ratio.
    ratio = DRIZZLE_COST_RATIO.get(cost_class)
    basis = drizzled or plain
    if basis is None or ratio is None or ratio <= 0:
        # No comparable run at all (or nothing to convert with): say so.
        return AutoDrizzleCost(scale=float(scale), drizzle_seconds=None,
                               plain_seconds=None,
                               basis_runs=0 if basis is None else basis.basis_runs,
                               same_engine=True if basis is None else basis.same_engine)
    drizzle_seconds = (drizzled.seconds if drizzled is not None
                       else plain.seconds * ratio)
    plain_seconds = (plain.seconds if plain is not None
                     else drizzled.seconds / ratio)
    return AutoDrizzleCost(
        scale=float(scale),
        drizzle_seconds=float(drizzle_seconds),
        plain_seconds=float(plain_seconds),
        basis_runs=int(basis.basis_runs),
        same_engine=bool(basis.same_engine),
    )
