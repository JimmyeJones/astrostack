"""The "Full-res PNG" copy and the render's own ceiling must not drift apart.

Four screens offer the full-res PNG download, and every one of them describes
what it hands over: the Target page's and the Dashboard strip's menu item say
"(native size)", History's prints the canvas dimensions outright. That render
decimates anything whose long edge exceeds
``webapp.routers.stack._FULL_RES_PNG_MAX_LONG_EDGE`` — a deliberate ceiling that
bounds memory and response size on a RAM-capped NAS — so on a big union mosaic
the download is *not* native size, and History was quoting a number the file
demonstrably misses.

The wording now comes from one place (``frontend/src/fullres.ts``), which has to
know that ceiling to decide which sentence is true. It can't import a Python
constant, so the number is mirrored by hand with a "change them together"
comment — the same arrangement as ``clearNights.ts`` and, for the same reason,
guarded here rather than left to prose. A stale copy would put the untruth
straight back on all four screens with nothing failing.
"""

from __future__ import annotations

import re
from pathlib import Path

from webapp.routers.stack import _FULL_RES_PNG_MAX_LONG_EDGE

FULLRES_TS = Path(__file__).resolve().parents[1] / "frontend" / "src" / "fullres.ts"


def _ts_number(name: str) -> float:
    """The numeric value of a top-level ``const`` in ``fullres.ts``.

    Fails loudly when the declaration can't be found: a renamed or relocated
    constant is itself the drift this guard exists to catch, and a check that
    silently passes when it can't find its subject enforces nothing."""
    src = FULLRES_TS.read_text(encoding="utf-8")
    m = re.search(rf"^export const {name}\s*=\s*([0-9.]+)\s*;", src, re.M)
    assert m is not None, (
        f"Could not find `export const {name}` in {FULLRES_TS.name}. If it was "
        "renamed or moved, update this guard and check it still agrees with "
        "webapp/routers/stack.py's _FULL_RES_PNG_MAX_LONG_EDGE — otherwise the "
        "download menus go back to promising native size on a picture the "
        "render caps."
    )
    return float(m.group(1))


def test_the_frontends_cap_matches_the_render():
    assert _ts_number("FULL_RES_PNG_MAX_LONG_EDGE") == float(
        _FULL_RES_PNG_MAX_LONG_EDGE), (
        "The full-res PNG render and the copy describing it disagree about how "
        "big the file can be, so a download menu is either claiming native size "
        "on a capped picture or warning about a cap that isn't there."
    )
