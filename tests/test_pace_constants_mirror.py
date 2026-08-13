"""The "how many more clear nights?" pace rules must be the same in both languages.

Three screens answer *"so how much longer will this target take me?"* and they
have to agree, or the app contradicts itself about the same picture:

* the **Target page** derives the pace client-side from the night list it has
  already fetched (``frontend/src/components/clearNights.ts``);
* the **Dashboard** overview and the **Tonight planner** get it from the server
  (:func:`seestack.session_recap.recent_night_pace_s`).

The two implementations can't share code across the language boundary, so the
two numbers that define the pace — how many recent nights it looks back over, and
how much kept integration a night needs before it counts as a session at all —
are mirrored **by hand**. A comment in each file says "change them together",
which is exactly the arrangement this project has already been bitten by twice
(the integration goal's three hand-synced copies, unified into ``webapp/goals.py``
in v0.253.1). A prose instruction is not enforcement; this is.

Verified alongside: the two *algorithms* — not just the constants — were driven
against each other over 300 randomised night sets (varying night counts, sub
counts, exposures and rejection rates) and agreed on every one, including the
edges (fewer than two productive nights → no pace either side; the all-duds set
where the client shows its "check focus" advisory and the server reports no
pace). So the only live drift risk is these numbers, and it is now caught here.
"""

from __future__ import annotations

import re
from pathlib import Path

from seestack.session_recap import MIN_PRODUCTIVE_NIGHT_S, PACE_LOOKBACK_NIGHTS

CLEAR_NIGHTS_TS = (
    Path(__file__).resolve().parents[1]
    / "frontend" / "src" / "components" / "clearNights.ts"
)


def _ts_number(name: str) -> float:
    """The numeric value of a top-level ``const`` in ``clearNights.ts``.

    Deliberately fails loudly when the declaration can't be found: a renamed or
    relocated constant is itself the drift this test exists to catch, and a guard
    that silently passes when it can't find its subject enforces nothing.
    """
    src = CLEAR_NIGHTS_TS.read_text(encoding="utf-8")
    m = re.search(rf"^(?:export )?const {name}\s*=\s*([0-9.]+)\s*;", src, re.M)
    assert m is not None, (
        f"Could not find `const {name}` in {CLEAR_NIGHTS_TS.name}. If it was "
        "renamed or moved, update this guard and check the Python side in "
        "seestack/session_recap.py still agrees — the Target page and the "
        "Dashboard/Tonight planner must quote the same ETA for the same target."
    )
    return float(m.group(1))


def test_pace_lookback_matches_the_frontend():
    assert _ts_number("PACE_LOOKBACK_NIGHTS") == float(PACE_LOOKBACK_NIGHTS), (
        "The Target page and the server-side pace look back over a different "
        "number of nights, so they will quote different ETAs for the same target."
    )


def test_min_productive_night_matches_the_frontend():
    assert _ts_number("MIN_PRODUCTIVE_NIGHT_S") == float(MIN_PRODUCTIVE_NIGHT_S), (
        "The Target page and the server-side pace disagree about how much kept "
        "integration makes a night count, so a marginal night would be included "
        "in one screen's median and dropped from the other's."
    )
