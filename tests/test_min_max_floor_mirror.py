"""The min/max floor the copy quotes must be the one the accumulator trims at.

Three sentences in the app now turn on "three samples on a pixel": the engine's
``rejection_blind`` note (``seestack.stackhealth``), History's 0 %-drop
qualifier, and the Jobs card's min/max guarantee
(``frontend/src/components/target/rejectionNote.ts``). The first two read
``seestack.stack.stacker.MIN_MAX_MIN_FRAMES`` directly; the third cannot import a
Python constant, so it mirrors the number by hand — the same arrangement as
``fullres.ts`` and ``clearNights.ts``, and guarded here for the same reason.

A stale copy would put the false guarantee straight back on the one surface a
walk-away user actually reads, with nothing failing. The bound itself is checked
against the **accumulator's behaviour** (not merely against the constant) in
``tests/test_rejection_reach.py::
test_the_min_max_floor_is_the_depth_the_accumulator_actually_trims_at``.
"""

from __future__ import annotations

import re
from pathlib import Path

from seestack.stack.stacker import MIN_MAX_MIN_FRAMES

REJECTION_NOTE_TS = (
    Path(__file__).resolve().parents[1]
    / "frontend" / "src" / "components" / "target" / "rejectionNote.ts"
)


def _ts_number(name: str) -> float:
    """The numeric value of a top-level ``const`` in ``rejectionNote.ts``.

    Fails loudly when the declaration can't be found: a renamed or relocated
    constant is itself the drift this guard exists to catch, and a check that
    silently passes when it can't find its subject enforces nothing."""
    src = REJECTION_NOTE_TS.read_text(encoding="utf-8")
    m = re.search(rf"^export const {name}\s*=\s*([0-9.]+)\s*;", src, re.M)
    assert m is not None, (
        f"Could not find `export const {name}` in {REJECTION_NOTE_TS.name}. If it "
        "was renamed or moved, update this guard and check it still agrees with "
        "seestack/stack/stacker.py's MIN_MAX_MIN_FRAMES — otherwise the Jobs "
        "card goes back to promising a per-pixel extreme drop on a picture too "
        "thin for one to have happened."
    )
    return float(m.group(1))


def test_the_frontend_min_max_floor_matches_the_engine_constant():
    assert _ts_number("MIN_MAX_MIN_SAMPLES") == float(MIN_MAX_MIN_FRAMES)
