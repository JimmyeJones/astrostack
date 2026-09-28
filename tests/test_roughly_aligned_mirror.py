"""The "your stars may look a little soft" gate must be one rule in both languages.

Sub-pixel refine leaves a sub *only roughly aligned* when its measured shift
exceeds the cap: the frame stacks unshifted, so its stars land soft or doubled
with nothing else on screen pointing at alignment. Two surfaces say so about the
same run — :func:`seestack.stackhealth.stack_health_notes`' ``roughly_aligned``
note on the Target page, and ``roughlyAlignedNote`` on History's Info panel — and
``stackhealth``'s own comment has always claimed they share one gate "so the two
surfaces never disagree".

They did not, and a shared *threshold* was what hid it: both spelled the same
≥20 %-of-≥10 bar and then read it against **different populations**. The engine
divides by ``n_frames_used`` (a roughly-aligned sub is by definition one that
contributed); the card divided by ``n_offered``. On any run with align failures
that is a larger denominator and so a smaller share, which on the owner's data
meant the card quoted a different number *and* withheld the fix the health note
was already prescribing. (The same shape as v0.484.6's ``REJREACH``: agreement on
a bound is not agreement on the measurement.)

So the rule is now one function here, mirrored by hand in
``frontend/src/routes/History.tsx`` (a TS module cannot import a Python one — the
``kappaMinFrames`` / ``test_kappa_min_frames_mirror.py`` arrangement) and pinned
against **one shared table** driven from both sides: change the rule and you have
to change the table.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from seestack.stackhealth import (
    _ROUGHLY_ALIGNED_MIN_USED,
    _ROUGHLY_ALIGNED_NOTE_FRACTION,
    roughly_aligned_is_material,
)

REPO = Path(__file__).resolve().parents[1]
CASES_JSON = REPO / "frontend" / "src" / "roughlyAligned.cases.json"
TS_SOURCE = REPO / "frontend" / "src" / "routes" / "History.tsx"


def _cases() -> list[tuple[int, int, bool]]:
    """The shared table, or a loud failure.

    Deliberately explicit when the file can't be found or parsed: a relocated or
    emptied table is itself the drift this guard exists to catch, and a guard
    that passes when it can't find its subject enforces nothing.
    """
    assert CASES_JSON.exists(), (
        f"The shared roughly-aligned case table is missing at {CASES_JSON}. It is "
        "driven from both sides — this file and "
        "frontend/src/routes/History.test.tsx — so if it moved, both have to "
        "follow."
    )
    data = json.loads(CASES_JSON.read_text(encoding="utf-8"))
    cases = [(int(used), int(rough), bool(want)) for used, rough, want in data["cases"]]
    assert cases, "The shared case table is empty, so it pins nothing."
    return cases


def test_every_tabulated_case_is_the_engines_own_answer() -> None:
    for used, rough, want in _cases():
        assert roughly_aligned_is_material(rough, used) is want, (
            f"{rough} rough of {used} stacked subs is tabulated as {want} but the "
            f"engine answers {roughly_aligned_is_material(rough, used)} — the "
            "table and the rule have drifted."
        )


def test_the_table_straddles_both_halves_of_the_gate() -> None:
    """A table that only varied the share would pass a mirror that ignored the
    stack-size floor, and vice versa — so pin that both are exercised both ways."""
    cases = _cases()
    floor = _ROUGHLY_ALIGNED_MIN_USED
    frac = _ROUGHLY_ALIGNED_NOTE_FRACTION
    # A big share on a stack below the floor, and the same big share above it.
    assert any(used < floor and rough >= frac * used for used, rough, _w in cases), (
        "No row has a material share on a stack under the size floor, so a "
        "mirror missing the floor would still pass."
    )
    assert any(used >= floor and rough >= frac * used for used, rough, _w in cases)
    # And both sides of the share, on stacks that clear the floor.
    assert any(used >= floor and rough < frac * used for used, rough, _w in cases), (
        "No row is a small share on a big stack, so a mirror that always said "
        "yes would still pass."
    )
    assert {w for _u, _r, w in cases} == {True, False}, (
        "Every row answering the same way pins nothing."
    )
    # Exactly at the bar — the case an inequality typo moves.
    assert any(used == floor and rough == round(frac * used) for used, rough, _w in cases)


def test_the_card_reads_the_share_against_the_subs_that_were_combined() -> None:
    """The mirror's *denominator*, which the shared table cannot see.

    The table pins the rule for a given pair of numbers; it cannot pin which
    number the card feeds in, and that is precisely what drifted. So assert in
    the source that ``roughlyAlignedNote`` derives its population from
    ``contributingSubs`` and never divides by ``n_offered``.
    """
    src = TS_SOURCE.read_text(encoding="utf-8")
    m = re.search(r"export function roughlyAlignedNote\((.*?)\n}\n", src, re.S)
    assert m, (
        f"Could not find roughlyAlignedNote in {TS_SOURCE} — if it was renamed or "
        "moved, this guard has to follow it."
    )
    body = m.group(1)
    assert "contributingSubs(fa)" in body, (
        "roughlyAlignedNote no longer takes its denominator from "
        "contributingSubs, which is the one thing that keeps it reading the same "
        "population as the engine's note."
    )
    assert "n_offered" not in body, (
        "roughlyAlignedNote mentions n_offered again. A roughly-aligned sub is "
        "one that contributed, so offered is a population its count never came "
        "from — that is the bug this guard exists for."
    )


def test_the_mirrored_gate_numbers_are_the_engines_numbers() -> None:
    """The card states the bar as literals; they are the engine's."""
    src = TS_SOURCE.read_text(encoding="utf-8")
    m = re.search(r"export function roughlyAlignedNote\((.*?)\n}\n", src, re.S)
    assert m
    body = m.group(1)
    floor = re.search(r"used\s*>=\s*(\d+)", body)
    share = re.search(r"fraction\s*>=\s*([0-9.]+)", body)
    assert floor and share, (
        "Could not read the ≥N-subs floor and the ≥share bar out of "
        "roughlyAlignedNote — if they are now spelled some other way, this guard "
        "has to follow them."
    )
    assert int(floor.group(1)) == _ROUGHLY_ALIGNED_MIN_USED, (
        f"The card floors the note at {floor.group(1)} stacked subs where the "
        f"engine floors it at {_ROUGHLY_ALIGNED_MIN_USED}."
    )
    assert float(share.group(1)) == _ROUGHLY_ALIGNED_NOTE_FRACTION, (
        f"The card guides a fix above {share.group(1)} where the engine's bar is "
        f"{_ROUGHLY_ALIGNED_NOTE_FRACTION}."
    )
