"""The rejection percentage must be spelled the same in both languages.

Two surfaces put a number on the *same* stack's clean-up, and the sentence around
it is word-identical:

* the **"How's my stack?"** note — *"Cleaned ~0.5% of pixels — passing
  satellites, planes and cosmic-ray hits were rejected, so they're not in your
  final image."* (``seestack.stackhealth._format_reject_pct``);
* the one-click **"Process target"** result on the Jobs page, which says the same
  thing where the finished picture lands, for a walk-away user who may never open
  the card (``formatRejectPct``, in
  ``frontend/src/components/target/rejectionNote.ts``).

They can't share code across the language boundary, so the rule — ``<0.1%`` for a
sliver, one decimal below 10%, whole percent above — was mirrored by hand and by
comment. **It had already drifted.** Below 1% the frontend printed two decimals
where the engine printed one (*"0.50%"* against *"0.5%"*), and at the bottom of
the cue's own band it printed *"0.07%"* where the engine printed *"<0.1%"* — two
decimals of false precision on a figure the sentence already prefixes with "~".
The frontend moved to the engine's rule, and the pair is now pinned against
**one shared table** of fraction → string cases, driven from both sides: change
the rule and you have to change the table.

Same idiom as ``tests/test_factor_label_mirror.py``, and written after the survey
that entry asked for found this as the first of its siblings.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from seestack.stackhealth import _format_reject_pct

CASES_JSON = (
    Path(__file__).resolve().parents[1]
    / "frontend" / "src" / "components" / "rejectPct.cases.json"
)


def _cases() -> list[tuple[float, str]]:
    """The shared table, or a loud failure.

    Deliberately explicit when the file can't be found or parsed: a relocated or
    emptied table is itself the drift this guard exists to catch, and a guard
    that passes when it can't find its subject enforces nothing.
    """
    assert CASES_JSON.exists(), (
        f"The shared reject-percentage case table is missing at {CASES_JSON}. It "
        "is driven from both sides — this file and "
        "frontend/src/components/target/rejectionNote.test.ts — so if it moved, "
        "both have to follow."
    )
    data = json.loads(CASES_JSON.read_text(encoding="utf-8"))
    cases = [(float(v), str(want)) for v, want in data["cases"]]
    assert cases, "The shared case table is empty, so it pins nothing."
    return cases


@pytest.mark.parametrize(("fraction", "want"), _cases())
def test_format_reject_pct_matches_the_shared_table(
    fraction: float, want: str,
) -> None:
    assert _format_reject_pct(fraction) == want, (
        f"`_format_reject_pct({fraction})` spells the clean-up differently from "
        "the shared table the Process-target note's `formatRejectPct` is also "
        "driven against. The same stack would be quoted two percentages on two "
        "screens."
    )


def test_the_table_covers_the_rule_it_exists_to_pin() -> None:
    """A table that only held easy values would pass whatever either side did.

    So assert it still spans the three things the rule actually decides: the
    sliver floor, the one-decimal band, the whole-percent band above 10%, and the
    exact-half cases where Python and JavaScript round differently.
    """
    cases = _cases()
    assert any(want == "<0.1%" for _, want in cases), "no sliver case"
    assert any("." in want and want != "<0.1%" for _, want in cases), (
        "no one-decimal answer")
    assert any("." not in want for _, want in cases), "no whole-percent answer"
    # A fraction inside the band the cheerful note actually uses, so the table
    # can never drift into testing only values a user will never see.
    assert any(0.0005 <= v < 0.08 for v, _ in cases), (
        "nothing inside the note's own honest band (0.05% – 8%)")
    halves = [
        v for v, _ in cases
        if abs(v * 1000 - int(v * 1000) - 0.5) < 1e-9
        or abs(v * 100 - int(v * 100) - 0.5) < 1e-9
    ]
    assert len(halves) >= 3, (
        "The table no longer covers the exact-half cases, which is where "
        "Python's round() and JavaScript's Math.round() part company. "
        f"Got: {halves}"
    )
