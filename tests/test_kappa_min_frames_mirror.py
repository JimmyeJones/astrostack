"""The κ-σ lone-outlier depth bound must be spelled the same in both languages.

``seestack.stack.stacker.kappa_min_frames`` is the one definition of "how many
samples must land on **one pixel** before a κ·σ clip can drop a *lone* satellite
trail" — the answer behind the Stack form's pre-run caution, ``stackhealth``'s
``rejection_blind`` note on the finished picture, and the ``REJNEED``/``REJREACH``
cards stamped into the master's own header.

The combine-method chip on History, Gallery and Compare now says the same thing
in its tooltip, and it has to compute the figure from the *run's own* κ rather
than quoting the default's — a stack clipped at κ=1.5 needs 4 samples, not 11.
A TS module cannot import a Python function (the ``formatRejectPct`` /
``test_reject_pct_mirror.py`` arrangement), so the rule is mirrored by hand in
``frontend/src/kappaMinFrames.ts`` and pinned here against **one shared table**
of κ → depth, driven from both sides: change the rule and you have to change the
table.

Only κ > 0 is tabulated. A non-positive or unreadable κ is a frontend-only guard
— the chip answers ``null`` and falls back to a wording that needs no figure —
and is not a case the engine's function is ever asked.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from seestack.stack.stacker import MIN_MAX_MIN_FRAMES, kappa_min_frames

REPO = Path(__file__).resolve().parents[1]
CASES_JSON = REPO / "frontend" / "src" / "kappaMinFrames.cases.json"
TS_SOURCE = REPO / "frontend" / "src" / "kappaMinFrames.ts"


def _cases() -> list[tuple[float, int]]:
    """The shared table, or a loud failure.

    Deliberately explicit when the file can't be found or parsed: a relocated or
    emptied table is itself the drift this guard exists to catch, and a guard
    that passes when it can't find its subject enforces nothing.
    """
    assert CASES_JSON.exists(), (
        f"The shared κ-depth case table is missing at {CASES_JSON}. It is driven "
        "from both sides — this file and frontend/src/kappaMinFrames.test.ts — so "
        "if it moved, both have to follow."
    )
    data = json.loads(CASES_JSON.read_text(encoding="utf-8"))
    cases = [(float(k), int(n)) for k, n in data["cases"]]
    assert cases, "The shared case table is empty, so it pins nothing."
    return cases


def test_every_tabulated_kappa_is_the_engines_own_answer() -> None:
    for kappa, want in _cases():
        assert kappa_min_frames(kappa) == want, (
            f"κ={kappa} is tabulated as {want} but the engine answers "
            f"{kappa_min_frames(kappa)} — the table and the rule have drifted."
        )


def test_the_table_covers_the_default_and_both_sides_of_it() -> None:
    """A table of one row would pass the check above and pin nothing useful."""
    kappas = [k for k, _ in _cases()]
    assert 3.0 in kappas, "κ=3 is the app default and must be pinned."
    assert any(k < 3.0 for k in kappas) and any(k > 3.0 for k in kappas), (
        "The table must straddle the default, or a mirror that ignored κ "
        "entirely would still pass."
    )
    depths = {n for _, n in _cases()}
    assert len(depths) > 1, "Every row answering the same depth pins nothing."


def test_the_mirrored_floor_is_the_engines_floor() -> None:
    """The TS module states its own floor as a literal; it is the engine's."""
    src = TS_SOURCE.read_text(encoding="utf-8")
    m = re.search(r"const\s+ABSOLUTE_MIN_FRAMES\s*=\s*(\d+)\s*;", src)
    assert m, (
        f"Could not find ABSOLUTE_MIN_FRAMES in {TS_SOURCE} — if it was renamed "
        "or removed, this guard has to follow it."
    )
    assert int(m.group(1)) == MIN_MAX_MIN_FRAMES, (
        f"{TS_SOURCE.name} floors the bound at {m.group(1)} where the engine "
        f"floors it at {MIN_MAX_MIN_FRAMES}."
    )
