"""The "what Auto did" note must read the same in both languages.

The same recipe gets described twice, about the same picture:

* the **editor** writes it when a user clicks Auto (``autoSummaryPhrases`` /
  ``autoCauseSentence`` / ``fmt``, in
  ``frontend/src/components/editor/autoSummary.ts``);
* an **unattended** job (Process-target, reprocess-everything, the watcher's
  auto-stack) stamps it on the History Info panel, so a walk-away user gets the
  same reasoning without having opened the editor
  (``seestack.edit.presets._AUTO_OP_PHRASES`` / ``_auto_cause_clause`` /
  ``_auto_num``).

Two of those three were mirrored by hand and by comment only, and the numeric one
had drifted: Python's ``round()`` is half-to-**even** and JavaScript's
``Math.round()`` is half-**up**, so a measured 0.125 sky read *"a ~0.12 sky"* on
the History panel and *"a ~0.13 sky"* in the editor — the same defect
``_factor_label`` was fixed for in v0.332.1, in a function whose docstring
already claimed to mirror this one. The Python side moved to ``floor(x + 0.5)``,
which is what ``Math.round`` is.

Both are now pinned against **shared tables** driven from each side, the idiom
``tests/test_factor_label_mirror.py`` established: change the rule (or a phrase)
and you have to change the table, which reddens both suites at once.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from seestack.edit.presets import _AUTO_OP_PHRASES, _auto_cause_clause, _auto_num

_FE = Path(__file__).resolve().parents[1] / "frontend" / "src" / "components" / "editor"
NUM_CASES_JSON = _FE / "autoNum.cases.json"
PHRASE_CASES_JSON = _FE / "autoOpPhrases.cases.json"


def _load(path: Path, what: str):
    """A shared table, or a loud failure — a table that can't be found enforces
    nothing, and a relocated one is itself the drift this guards against."""
    assert path.exists(), (
        f"The shared {what} table is missing at {path}. It is driven from both "
        "sides — this file and frontend/src/components/editor/autoSummary.test.ts "
        "— so if it moved, both have to follow."
    )
    data = json.loads(path.read_text(encoding="utf-8"))
    cases = data["cases"]
    assert cases, f"The shared {what} table is empty, so it pins nothing."
    return cases


def _num_cases() -> list[tuple[float, str]]:
    return [(float(v), str(want))
            for v, want in _load(NUM_CASES_JSON, "auto-number")]


# --- the numbers ------------------------------------------------------------

@pytest.mark.parametrize(("value", "want"), _num_cases())
def test_auto_num_matches_the_shared_table(value: float, want: str) -> None:
    assert _auto_num(value) == want, (
        f"`_auto_num({value})` writes the measurement differently from the shared "
        "table the editor's `fmt` is also driven against. One picture would be "
        "described as measuring two different things on two screens."
    )


def test_the_number_table_covers_the_rounding_mode_it_exists_to_pin() -> None:
    """The exact-half hundredths are the only place the two languages disagree,
    so a table that lost them would pin nothing that matters."""
    values = [v for v, _ in _num_cases()]
    assert any(v != int(v) for v in values), "no fractional case"
    assert any(v == int(v) for v in values), "no whole-number case"
    # A "half" here is a value whose *hundredths* boundary lands on .5 — the
    # rule rounds at 2 decimals, so that is where the two languages part.
    halves = [v for v in values if abs(v * 100 - int(v * 100) - 0.5) < 1e-9]
    assert len(halves) >= 3, (
        "The table no longer covers the exact-half hundredths, which is where "
        f"Python's round() and JavaScript's Math.round() part company. Got: {halves}"
    )


# --- the phrases ------------------------------------------------------------

def test_op_phrases_match_the_shared_table() -> None:
    """Every op the Auto recipe can emit is named identically on both screens.

    Asserted as a whole mapping rather than case by case: a phrase table drifts
    by *gaining* or *losing* a key as much as by re-wording one, and neither
    shows up in a per-key loop over one side's own keys.
    """
    want = {str(k): str(v) for k, v in _load(PHRASE_CASES_JSON, "op-phrase").items()}
    assert want == _AUTO_OP_PHRASES, (
        "`_AUTO_OP_PHRASES` no longer matches the shared table the editor's "
        "`OP_PHRASES` is driven against, so an auto-edit applied by an unattended "
        "job would be described in different words from the identical one applied "
        "in the editor."
    )


def test_the_phrase_table_covers_every_op_auto_actually_emits() -> None:
    """A phrase table is only a guard while it is complete.

    So pin it against the recipe builder itself rather than against a list: an op
    added to Auto with no phrase on either side would leave *both* surfaces
    printing a raw op id at a user, and a table-only test would still pass. Built
    over a noisy mosaic scene with a trim, which is the shape that turns on the
    most optional ops (panel levelling, denoise, chroma denoise, the crop).
    """
    import numpy as np

    from seestack.edit.presets import auto_recipe

    rng = np.random.default_rng(7)
    rgb = np.clip(
        0.05 + rng.normal(0.0, 0.02, size=(96, 128, 3)).astype(np.float32),
        0.0, 1.0)
    recipes = [
        auto_recipe(rgb),
        auto_recipe(rgb, median_fwhm=3.5, is_mosaic=True,
                    trim_crop=(0.02, 0.02, 0.98, 0.98)),
    ]
    emitted = {op.id for r in recipes for op in r.ops}
    assert emitted, "the Auto builder produced no ops, so this pins nothing"
    missing = sorted(emitted - set(_AUTO_OP_PHRASES))
    assert not missing, (
        f"Auto emits {missing}, which has no plain-language phrase — the note "
        "would print a raw op id at a user. Add it to _AUTO_OP_PHRASES and to "
        f"{PHRASE_CASES_JSON.name}."
    )


# --- the clause the numbers land in -----------------------------------------

def test_cause_clause_rounds_the_trim_percentage_like_the_editor_does() -> None:
    """The trim figure is the clause's second hand-mirrored number.

    It sits in its own `round(trim * 100)` rather than going through
    :func:`_auto_num`, so it carried the same half-to-even divergence
    independently: 0.125 read "12%" here against the editor's "13%".
    """
    assert _auto_cause_clause({"trim_fraction": 0.125}) == (
        "13% of ragged mosaic edge to trim")
    assert _auto_cause_clause({"trim_fraction": 0.115}) == (
        "12% of ragged mosaic edge to trim")


def test_cause_clause_reads_as_the_editor_writes_it() -> None:
    """The clause body — the part both sides build identically — for the shape
    the module docstring's own example uses."""
    assert _auto_cause_clause({
        "sky": 0.125, "median_fwhm": 4.7, "noise_fraction": 0.8,
        "trim_fraction": 0.125,
    }) == (
        "a ~0.13 sky, 4.7 px stars, a noisy background, "
        "13% of ragged mosaic edge to trim"
    )


def test_a_linear_stacks_dark_sky_is_not_reported_as_no_sky() -> None:
    """The bundled sample, in a real running app, said *"measured a ~0 sky"*.

    Its measured sky is 0.001 — a perfectly ordinary number for a **linear**
    stack, which is what the editor opens — and two decimals rounded it away. The
    same panel says "sky level 0.24" one line below (the stretch's *target*
    background, a display-space number), so the pair read as the app measuring
    the same picture twice and getting nothing the first time.
    """
    assert _auto_cause_clause({"sky": 0.001, "median_fwhm": 2.07}) == (
        "a ~0.001 sky, 2.07 px stars")
    # Three decimals is exactly what `analyze_auto_inputs` carries, so a sky it
    # rounded to zero still reads "0" rather than inventing precision.
    assert _auto_cause_clause({"sky": 0.0}) == "a ~0 sky"
    # …and nothing about the ordinary range moves.
    assert _auto_num(0.24) == "0.24"
    assert _auto_num(2.07) == "2.07"
