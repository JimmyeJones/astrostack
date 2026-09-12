"""The Moon-for-scale disc on screen and the one baked into the file must be the
same circle.

"Moon for scale" is drawn twice: once as a browser overlay over the preview
(``frontend/src/moonDisc.ts``) and once into the pixels of the shared JPEG
(``seestack/skymarks.py``, sized off ``seestack.scalebar.ScaleBar``). Two numbers
decide what a reader sees — the Moon's angular diameter, and the size past which
the disc stops being a mark and self-hides — and a TypeScript module cannot
import a Python constant. Left to prose, a change to either side would make the
screen and the download disagree about how big the Moon is, which is precisely
the claim the feature exists to make. Same arrangement, and same reason, as
``test_fullres_cap_mirror.py`` and ``test_pace_constants_mirror.py``.

The formula itself needs no guard: ``moon_fraction`` is derived from the bar's
own ``fraction`` on both sides, so the crop and North-up re-basings are carried
for free — see ``seestack.scalebar.ScaleBar.moon_fraction``.
"""

from __future__ import annotations

import re
from pathlib import Path

from seestack.scalebar import MOON_DIAMETER_ARCSEC
from seestack.skymarks import MOON_DISC_MAX_SHORT_FRACTION

MOON_TS = Path(__file__).resolve().parents[1] / "frontend" / "src" / "moonDisc.ts"


def _ts_number(name: str) -> float:
    """The numeric value of a top-level ``const`` in ``moonDisc.ts``.

    Fails loudly when the declaration can't be found: a renamed or relocated
    constant is itself the drift this guard exists to catch, and a check that
    silently passes when it can't find its subject enforces nothing."""
    src = MOON_TS.read_text(encoding="utf-8")
    m = re.search(rf"^export const {name}\s*=\s*([0-9.*\s]+);", src, re.M)
    assert m is not None, (
        f"Could not find `export const {name}` in {MOON_TS.name}. If it was "
        "renamed or moved, update this guard and check it still agrees with "
        "seestack/scalebar.py and seestack/skymarks.py — otherwise the disc on "
        "screen and the disc in the downloaded picture stop being the same "
        "circle."
    )
    return float(eval(m.group(1), {"__builtins__": {}}, {}))  # noqa: S307


def test_the_frontend_draws_the_same_moon_the_engine_does():
    assert _ts_number("MOON_DIAMETER_ARCSEC") == float(MOON_DIAMETER_ARCSEC), (
        "The browser overlay and the baked share picture disagree about how big "
        "the full Moon is, so the same picture would show two different discs."
    )


def test_the_frontend_hides_the_disc_at_the_same_size_the_engine_does():
    assert _ts_number("MOON_DISC_MAX_SHORT_FRACTION") == float(
        MOON_DISC_MAX_SHORT_FRACTION), (
        "The overlay and the bake disagree about when the Moon is too big to be "
        "a mark, so a field could offer a disc on screen that the download "
        "declines to draw (or the reverse)."
    )
