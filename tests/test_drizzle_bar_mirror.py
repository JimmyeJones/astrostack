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

import pytest

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


# --- and the *unit* the bar is quoted in ------------------------------------
#
# The number agreeing across two files is only half of it. `drizzle_path.py`
# states the other half as a rule — "It is a per-**pixel** count, not a target's
# frame total … Every surface that quotes this bar must feed it the depth, not
# the total" — because on a mosaic the two differ by the panel count, and the
# direction of the error is the flattering one: a 3x3 raster 900 subs deep in
# total has ~100 on any pixel, so a recommendation counted in *frames* says yes
# on exactly the canvas drizzle handles worst. The Stack form's own cautions
# were moved onto the per-pixel depth in v0.436.0; the sentences beside the
# control — the field help under the checkbox, and the glossary entry the
# control has linked to since v0.461.0 — were not, and still read "200+ dithered
# frames". This guard is that rule, checked.

_BAR_TEXT = "200+"


def _sentence_with_the_bar(text: str) -> str:
    """The sentence quoting the recommendation, for the unit check below."""
    flat = " ".join(text.split())
    assert _BAR_TEXT in flat, (
        f"the bar {_BAR_TEXT!r} is not quoted here any more — if the wording "
        "moved, move this guard with it rather than deleting it"
    )
    start = flat.rfind(".", 0, flat.index(_BAR_TEXT)) + 1
    end = flat.find(".", flat.index(_BAR_TEXT))
    return flat[start:end if end != -1 else len(flat)]


@pytest.mark.parametrize("name", ["drizzle", "drizzle_reject"])
def test_the_drizzle_controls_say_which_count_the_bar_is_against(name):
    """The sentence a user reads with their hand on the toggle has to name the
    unit, because it is the one that decides whether they turn it on."""
    from webapp.schemas import stack_option_fields

    field = next(f for f in stack_option_fields() if f.key == name)
    help_text = " ".join((field.help or "").split())
    if _BAR_TEXT not in help_text:          # only `drizzle` quotes the bar today
        return
    assert "pixel" in _sentence_with_the_bar(help_text), (
        f"the {name!r} help quotes {_BAR_TEXT!r} without saying it is counted "
        "per output pixel — on a mosaic that reads an order of magnitude high"
    )


def test_the_glossary_entry_the_drizzle_control_links_to_says_it_too():
    """The control offers the glossary in the same row as the help, so the two
    have to agree about what is being counted — a beginner who does not trust
    the tooltip clicks the book."""
    from seestack.glossary import load_glossary

    _intro, terms = load_glossary()
    entry = next(t for t in terms if t.slug == "drizzle")
    assert "pixel" in _sentence_with_the_bar(entry.body), (
        "the glossary's Drizzle entry quotes the bar in frames, which is the "
        "unit the Stack form's own cautions were moved off in v0.436.0"
    )


def test_the_engine_s_own_recommendation_names_the_unit():
    """The sentence every surface above is quoting. It is the source, so if it
    says "frames" the copy that cites it will keep saying "frames"."""
    import seestack.stack.drizzle_path as dp

    assert "pixel" in _sentence_with_the_bar(dp.__doc__ or "")
