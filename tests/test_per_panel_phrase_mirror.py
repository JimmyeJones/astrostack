"""The planner's per-panel words and the frontend's must not drift apart.

Two surfaces now describe the same quantity about the same target — "what you
already have on it, read per panel" — and they are written in two languages:

* ``frontend/src/closingSeason.haveClause`` builds the "Shoot these before
  they're gone" line in the browser, from
  ``frontend/src/components/target/perPixel`` (``A_TYPICAL_PART``,
  ``fieldsOfSkyLabel``);
* :func:`seestack.nightplan._have_phrase` builds the Tonight / "Worth more time"
  sentence **server-side**, because both cards that show it print ``reason``
  verbatim and so cannot correct a target total themselves.

A TS module cannot import a Python one, so the planner mirrors the two phrases by
hand. This guard is what stops that copy going stale: reword "a typical part" or
the "about N fields of sky" scale on either side and one card starts speaking a
dialect of the other, two clicks apart, about the same picture — which is the
exact failure ``perPixel.ts`` was written to end ("one alert cannot again say 'a
typical part has 3' and 'waiting until each part has 5' two clauses apart").

The *arithmetic* needs no mirror: the planner imports
:func:`seestack.portfolio.per_pixel_total` rather than re-deriving the clamp, and
that function is already pinned against ``perPixel`` where it lives.
"""

from __future__ import annotations

import re
from pathlib import Path

from seestack.nightplan import _A_TYPICAL_PART, _fields_of_sky_phrase

PER_PIXEL_TS = (Path(__file__).resolve().parents[1] / "frontend" / "src"
                / "components" / "target" / "perPixel.ts")


def _ts_source() -> str:
    src = PER_PIXEL_TS.read_text(encoding="utf-8")
    assert "export const A_TYPICAL_PART" in src, (
        f"Could not find the per-panel vocabulary in {PER_PIXEL_TS.name}. If it "
        "moved, update this guard — a check that passes when it cannot find its "
        "subject enforces nothing."
    )
    return src


def test_the_planner_says_a_typical_part_in_the_frontends_exact_words():
    src = _ts_source()
    literal = re.search(r'export const A_TYPICAL_PART = "([^"]+)";', src)
    assert literal is not None, (
        "`A_TYPICAL_PART`'s declaration no longer matches the shape this guard "
        f"reads in {PER_PIXEL_TS.name}."
    )
    assert literal.group(1) == _A_TYPICAL_PART
    # Never "each part": every per-panel figure either side quotes is an average,
    # and a mosaic with one deep panel and eight thin ones has pixels on both
    # sides of it. "Each part has N" promises more than the picture holds.
    assert "each part" not in _A_TYPICAL_PART


def test_the_planner_names_the_scale_in_the_frontends_exact_words():
    """``fieldsOfSkyLabel``: the same template and the same floor of 2."""
    src = _ts_source()
    body = re.search(
        r"export function fieldsOfSkyLabel\([^)]*\): string \{(.*?)^\}",
        src, re.M | re.S,
    )
    assert body is not None, (
        f"Could not find `fieldsOfSkyLabel` in {PER_PIXEL_TS.name}."
    )
    template = re.search(r"return `([^`]+)`;", body.group(1))
    assert template is not None, "…and could not read the phrase it returns."
    # "about ${fields} fields of sky" → the Python phrase for that same count.
    for fields in (2, 4, 96):
        expected = template.group(1).replace("${fields}", str(fields))
        assert _fields_of_sky_phrase(float(fields)) == expected

    # Rounded to a whole field, and floored at 2, on both sides.
    assert "Math.round(" in body.group(1)
    assert "Math.max(2," in body.group(1)
    assert _fields_of_sky_phrase(2.25) == _fields_of_sky_phrase(2.0)
    assert _fields_of_sky_phrase(1.5) == _fields_of_sky_phrase(2.0)


def test_the_two_surfaces_build_the_same_mosaic_clause():
    """Not just the words — the *shape*: depth first, the total in parentheses,
    the scale named. ``closingSeason.haveClause`` is the card this idiom comes
    from, so a reword there has to be a deliberate reword here too."""
    closing = (PER_PIXEL_TS.parents[2] / "closingSeason.ts").read_text(encoding="utf-8")
    clause = re.search(
        r"return `you have about \$\{depth\} on \$\{A_TYPICAL_PART\} of it`\s*"
        r"\+ ` \(\$\{total\} in total, spread over \$\{fieldsOfSkyLabel\("
        r"t\.field_fulls\)\}\)`;",
        closing,
    )
    assert clause is not None, (
        "`closingSeason.haveClause` no longer builds "
        "'<depth> on a typical part of it (<total> in total, spread over "
        "<scale>)'. The planner's sentence mirrors that idiom by hand — if the "
        "card changed on purpose, change seestack.nightplan._have_phrase with it."
    )
