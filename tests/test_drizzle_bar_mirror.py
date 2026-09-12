"""The drizzle "too thin to pay off" bar must be one number, not two.

Three sentences turn on it: the Stack form's ``drizzleTooFewHint`` ("Consider
turning Drizzle off for this stack"), the same form's print panel (which
withholds "raise Drizzle to ×1.4" below the bar), and — since v0.436.0 — the
editor's print nudge, which names Drizzle as the lever that would print a
picture one size bigger. The first two read the TypeScript copy in
``frontend/src/samplesPerPixel.ts``; the third reads
``seestack.stack.drizzle_path.DRIZZLE_MIN_SAMPLES_PER_PIXEL`` directly, because
it is rendered server-side.

A TS module cannot import a Python constant, so the number is mirrored by hand —
the same arrangement as ``fullres.ts`` and ``rejectionNote.ts``, and guarded here
for the same reason: a stale copy would put back the exact contradiction the fix
removed (one screen recommending the re-stack the other screen withdraws), with
nothing failing.
"""

from __future__ import annotations

import re
from pathlib import Path

from seestack.stack.drizzle_path import DRIZZLE_MIN_SAMPLES_PER_PIXEL

SAMPLES_PER_PIXEL_TS = (
    Path(__file__).resolve().parents[1]
    / "frontend" / "src" / "samplesPerPixel.ts"
)


def _ts_number(name: str) -> float:
    """The numeric value of a top-level ``export const`` in the TS module.

    Fails loudly when the declaration can't be found: a renamed or relocated
    constant is itself the drift this guard exists to catch, and a check that
    silently passes when it can't find its subject enforces nothing."""
    src = SAMPLES_PER_PIXEL_TS.read_text(encoding="utf-8")
    m = re.search(rf"^export const {name}\s*=\s*([0-9.]+)\s*;", src, re.M)
    assert m is not None, (
        f"Could not find `export const {name}` in {SAMPLES_PER_PIXEL_TS.name}. "
        "If it was renamed or moved, update this guard and check it still "
        "agrees with seestack/stack/drizzle_path.py's "
        "DRIZZLE_MIN_SAMPLES_PER_PIXEL — otherwise the Stack form and the "
        "editor's print nudge go back to disagreeing about when Drizzle is "
        "worth recommending."
    )
    return float(m.group(1))


def test_the_frontend_drizzle_bar_matches_the_engine_constant():
    assert (_ts_number("DRIZZLE_MIN_SAMPLES_PER_PIXEL")
            == float(DRIZZLE_MIN_SAMPLES_PER_PIXEL))
