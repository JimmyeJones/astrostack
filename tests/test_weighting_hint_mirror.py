"""The frame count the "your weighting won't count" caution quotes must be the
count at which the stacker really stops applying weights.

``frontend/src/weightingHint.ts`` owns one sentence shown in two places — the
per-target Stack form and the global stack defaults in Settings — telling a user
who has ticked both min/max rejection and quality weighting that the two do not
combine. It is right: ``run_stack`` stamps ``weights_applied=False`` into the
run's provenance on exactly that path, because an order statistic ignores
per-frame weights. But the *threshold* in that sentence ("on any stack of 3 or
more subs") is a Python constant the frontend cannot import, so it is mirrored by
hand — the same arrangement as ``rejectionNote.ts`` and ``fullres.ts``, and
unguarded until now, which is the one difference worth removing.

A stale copy would not fail anything. It would quietly tell a beginner their
quality weighting is being ignored on a stack where it is honoured, or — worse —
stay silent on one where it is not, which is the case the caution exists for.

Guarded in both directions, because the constant alone is only half the claim:
the TS literal is checked against :data:`seestack.stack.stacker.MIN_MAX_MIN_FRAMES`,
and that constant is checked against the **dispatcher's own behaviour** rather
than against another copy of itself.
"""

from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path

from seestack.stack.stacker import MIN_MAX_MIN_FRAMES, StackOptions, combine_method

WEIGHTING_HINT_TS = (
    Path(__file__).resolve().parents[1]
    / "frontend" / "src" / "weightingHint.ts"
)


def _ts_number(name: str) -> float:
    """The numeric value of a top-level ``const`` in ``weightingHint.ts``.

    Fails loudly when the declaration can't be found: a renamed or relocated
    constant is itself the drift this guard exists to catch, and a check that
    silently passes when it cannot find its subject enforces nothing."""
    src = WEIGHTING_HINT_TS.read_text(encoding="utf-8")
    m = re.search(rf"^export const {name}\s*=\s*([0-9.]+)\s*;", src, re.M)
    assert m is not None, (
        f"Could not find `export const {name}` in {WEIGHTING_HINT_TS.name}. If it "
        "was renamed or moved, update this guard and check it still agrees with "
        "seestack/stack/stacker.py's MIN_MAX_MIN_FRAMES — otherwise the Stack "
        "form can start quoting a frame count the stacker does not switch at."
    )
    return float(m.group(1))


def test_the_frontend_weighting_floor_matches_the_engine_constant():
    assert _ts_number("WEIGHTING_MIN_MAX_MIN_FRAMES") == float(MIN_MAX_MIN_FRAMES)


def test_the_engine_constant_is_the_count_the_dispatcher_switches_at():
    """…and the constant is not merely a number sitting beside the gate.

    ``weights_applied`` is ``not _min_max_reject_runs(eff, n)``, which is
    ``combine_method(...) == "min-max-reject"`` — so asking ``combine_method``
    across the boundary is asking the same question the provenance flag answers.
    """
    opts = StackOptions(min_max_reject=True, sigma_clip=False, drizzle=False)
    for n in range(0, MIN_MAX_MIN_FRAMES):
        assert combine_method(opts, n) != "min-max-reject", n
    for n in range(MIN_MAX_MIN_FRAMES, MIN_MAX_MIN_FRAMES + 4):
        assert combine_method(opts, n) == "min-max-reject", n

    # Drizzle keeps its own two-pass rejection, so the caution stands down there
    # whatever the count — the other half of the hint's own guard.
    drizzled = replace(opts, drizzle=True)
    for n in range(0, MIN_MAX_MIN_FRAMES + 4):
        assert combine_method(drizzled, n) != "min-max-reject", n
