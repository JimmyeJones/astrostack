"""The noise-reduction factor must be spelled the same in both languages.

Two surfaces put a number on the *same* stack, minutes apart:

* the **"One frame vs your stack"** card writes "Stacking your 505 subs cut the
  background noise about 22×" (``factorLabel``, in
  ``frontend/src/components/oneFrameVsStack.ts``);
* the **"How's my stack?"** note writes "…and this stack came in nearer 22×"
  about that same measured ratio (``seestack.stackhealth._factor_label``).

They can't share code across the language boundary, so the rule — whole numbers
at or above 10, one decimal below, a trailing ``.0`` dropped — is mirrored by
hand. A comment saying "keep these identical" is not enforcement; this is, and it
is the same idiom ``tests/test_pace_constants_mirror.py`` already uses for a pair
of hand-synced constants. Because this one is a *formatter* rather than a
constant, the two are pinned against **one shared table** of value → string
cases, driven from both sides: change the rule and you have to change the table.

**It caught a live divergence the day it was written (v0.332.1).** Python's
``round()`` is half-to-**even**; JavaScript's ``Math.round()`` is half-**up**. So a
measured ratio of 10.5 read "10" on the health note and "11" on the card, and 2.45
read "2.4" against "2.5" — six of the eleven half-cases first tried disagreed. The
Python side moved to ``floor(x + 0.5)``, which is what ``Math.round`` is.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from seestack.stackhealth import _factor_label

CASES_JSON = (
    Path(__file__).resolve().parents[1]
    / "frontend" / "src" / "components" / "factorLabel.cases.json"
)


def _cases() -> list[tuple[float, str]]:
    """The shared table, or a loud failure.

    Deliberately explicit when the file can't be found or parsed: a relocated or
    emptied table is itself the drift this guard exists to catch, and a guard that
    passes when it can't find its subject enforces nothing.
    """
    assert CASES_JSON.exists(), (
        f"The shared factor-label case table is missing at {CASES_JSON}. It is "
        "driven from both sides — this file and "
        "frontend/src/components/oneFrameVsStack.test.ts — so if it moved, both "
        "have to follow."
    )
    data = json.loads(CASES_JSON.read_text(encoding="utf-8"))
    cases = [(float(v), str(want)) for v, want in data["cases"]]
    assert cases, "The shared case table is empty, so it pins nothing."
    return cases


@pytest.mark.parametrize(("value", "want"), _cases())
def test_factor_label_matches_the_shared_table(value: float, want: str) -> None:
    assert _factor_label(value) == want, (
        f"`_factor_label({value})` spells the factor differently from the shared "
        f"table the card's `factorLabel` is also driven against. The same stack "
        f"would be described two ways on two screens."
    )


def test_the_table_covers_the_rule_it_exists_to_pin() -> None:
    """A table that only held easy values would pass whatever either side did.

    So assert it still spans the three things the rule actually decides: the
    10× switch between whole numbers and one decimal, at least one value on each
    side of it, and the half-cases where Python and JavaScript round differently —
    which is the divergence this guard was written after finding.
    """
    cases = _cases()
    values = [v for v, _ in cases]
    assert any(v < 10 for v in values), "nothing below the one-decimal boundary"
    assert any(v >= 10 for v in values), "nothing above it"
    assert any(want.endswith(("0", "1", "2", "3", "4", "5", "6", "7", "8", "9"))
               and "." in want for _, want in cases), "no one-decimal answer"
    assert any("." not in want for _, want in cases), "no whole-number answer"
    # The rounding-mode cases: a value whose ×10 (or whose self, above 10) lands
    # exactly on .5, where half-to-even and half-up part company.
    halves = [v for v in values
              if (v >= 10 and abs(v - int(v) - 0.5) < 1e-12)
              or (v < 10 and abs(v * 10 - int(v * 10) - 0.5) < 1e-9)]
    assert len(halves) >= 3, (
        "The table no longer covers the exact-half cases, which is the only place "
        "Python's round() and JavaScript's Math.round() disagree — and the "
        f"divergence this guard was written after finding. Got: {halves}"
    )
