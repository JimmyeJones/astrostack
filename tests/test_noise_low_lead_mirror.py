"""The noise-shortfall sentence must read the same in both languages.

Two surfaces say the *same thing* about the same stack, minutes apart:

* the **"How's my stack?"** note — *"100 subs should cut the background noise
  about 10× (√100), and this stack came in nearer 6.2×."*
  (:func:`seestack.stackhealth.noise_low_lead`);
* the History page's **"See the difference"** reveal, which writes that sentence
  again for the run the user is looking at (``noiseLowLead``, in
  ``frontend/src/components/oneFrameVsStack.ts``).

The *number* in it has been pinned since v0.332.1
(``tests/test_factor_label_mirror.py``). The **words around it** were not, and
they had already drifted: the card said *"cut the noise"* where the note said
*"cut the **background** noise"*. Nothing was wrong in either — which is exactly
why nobody caught it. This class does not fail loudly; it drifts, and the failure
mode is a qualifier quietly going missing. The measured quantity is the sky
background's own grain, so the qualifier is the true word and the card moved to
it.

Pinned the way the number already is: one shared table of
``(n_subs, ratio, is_mosaic) → sentence``, driven from both sides.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from seestack.stackhealth import noise_low_lead

CASES_JSON = (
    Path(__file__).resolve().parents[1]
    / "frontend" / "src" / "components" / "noiseLowLead.cases.json"
)


def _cases() -> list[tuple[int, float, bool, str]]:
    """The shared table, or a loud failure — a guard that passes when it can't
    find its subject enforces nothing."""
    assert CASES_JSON.exists(), (
        f"The shared noise-lead case table is missing at {CASES_JSON}. It is "
        "driven from both sides — this file and "
        "frontend/src/components/oneFrameVsStack.test.ts — so if it moved, both "
        "have to follow."
    )
    data = json.loads(CASES_JSON.read_text(encoding="utf-8"))
    cases = [(int(n), float(r), bool(m), str(want))
             for n, r, m, want in data["cases"]]
    assert cases, "The shared case table is empty, so it pins nothing."
    return cases


@pytest.mark.parametrize(("n_subs", "ratio", "is_mosaic", "want"), _cases())
def test_noise_low_lead_matches_the_shared_table(
    n_subs: int, ratio: float, is_mosaic: bool, want: str,
) -> None:
    assert noise_low_lead(n_subs, ratio, is_mosaic) == want, (
        "The health note words the shortfall differently from the shared table "
        "the History reveal's `noiseLowLead` is also driven against. One stack "
        "would be explained two ways on two screens."
    )


def test_the_table_covers_both_shapes_of_the_sentence() -> None:
    """The mosaic and single-field leads are different sentences, not a
    substitution — a table holding only one of them would let the other rot."""
    cases = _cases()
    assert any(m for _, _, m, _ in cases), "no mosaic case"
    assert any(not m for _, _, m, _ in cases), "no single-field case"
    # The qualifier is the thing that went missing, so assert it is still there
    # rather than only that the two sides agree — they would also agree if both
    # dropped it.
    assert all("background noise" in want for _, _, _, want in cases), (
        "a case no longer says 'background noise', which is the exact word that "
        "went missing on one side and the reason this guard exists"
    )
