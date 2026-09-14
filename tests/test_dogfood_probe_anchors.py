"""The dogfood probe's ``PRESCRIPTIVE`` list must still point at real cards.

``scripts/dogfood_probe.mjs`` collects the Target page's *prescriptive* sentences
— the ones that tell the owner what to do next — off the rendered page, by
``data-testid``. It is what makes a dogfood pass print those sentences together
instead of leaving them to be cropped out of a screenshot afterwards, which is
how four of the five findings before it were actually found.

The link between the two files is a **string**, and a string is exactly the kind
of link that rots silently: rename a ``data-testid`` in the frontend and the
probe keeps running, keeps reporting CLEAN, and simply stops printing that
sentence. Nothing fails, and the next run reads a *shorter* paragraph without
knowing a claim went missing. This test is the enforcement the arrangement
otherwise lacks — the same shape as the ``*_mirror`` guards in this directory.

It deliberately checks both directions:

* every id the probe asks for is rendered by some non-test source file, so a
  renamed card is caught at the source;
* the cards that *only* the browser can read — the four frontend-computed ones
  the server-side block in ``agent-dogfood.sh`` structurally cannot print — are
  still on the list, so a future edit can't quietly narrow the probe back to the
  half that was already covered.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PROBE = REPO / "scripts" / "dogfood_probe.mjs"
FRONTEND_SRC = REPO / "frontend" / "src"

# The ids whose sentences have no server-side equivalent: `readiness.ts`,
# `grainProjection.ts`, `nextBestMove.ts` and `integrationTrend.ts` all run in
# the browser, so `agent-dogfood.sh`'s "what the app SAYS about this mosaic"
# block (the panel map + the health notes, both read straight off the API)
# cannot carry them however it is extended.
BROWSER_ONLY = {"readiness-card", "next-best-move", "integration-trend"}


def _prescriptive_ids() -> list[str]:
    """The ids in the probe's ``PRESCRIPTIVE`` array.

    Fails loudly rather than returning an empty list when the declaration can't
    be found: a renamed or restructured list is itself the drift being guarded
    against, and a guard that passes when it can't find its subject enforces
    nothing.
    """
    src = PROBE.read_text(encoding="utf-8")
    m = re.search(r"^const PRESCRIPTIVE = \[(.*?)\];", src, re.S | re.M)
    assert m, "could not find `const PRESCRIPTIVE = [...]` in dogfood_probe.mjs"
    ids = re.findall(r'"([a-z0-9-]+)"', m.group(1))
    assert ids, "PRESCRIPTIVE is empty — the probe would print nothing"
    return ids


def _rendered_testids() -> set[str]:
    """Every ``data-testid`` literal rendered by non-test frontend source."""
    found: set[str] = set()
    for path in FRONTEND_SRC.rglob("*.tsx"):
        if ".test." in path.name:
            continue
        found.update(
            re.findall(r'data-testid="([a-z0-9-]+)"', path.read_text(encoding="utf-8"))
        )
    return found


def test_every_id_the_probe_reads_is_rendered_by_a_real_card() -> None:
    rendered = _rendered_testids()
    missing = [i for i in _prescriptive_ids() if i not in rendered]
    assert not missing, (
        "dogfood_probe.mjs collects data-testid(s) nothing renders: "
        f"{missing}. A probe that asks for an id that no longer exists reports "
        "CLEAN and silently drops that sentence from the paragraph."
    )


def test_the_browser_only_cards_stay_on_the_list() -> None:
    ids = set(_prescriptive_ids())
    assert BROWSER_ONLY <= ids, (
        "these cards are computed in the frontend, so the browser probe is the "
        f"only thing that can print them: {sorted(BROWSER_ONLY - ids)}"
    )


# --- the Tonight page's prescribing column ----------------------------------
#
# `/tonight` is the *other* page that tells the owner what to do, and it does it
# from four independent self-hiding cards in one column, none of which knows what
# the others said — which is the shape every finding of the last six runs has
# had. The list has the same string-rot problem as `PRESCRIPTIVE` above, plus one
# of its own: these cards are siblings in a plain `<Stack>` rather than children
# of a `NoticeBoard`, so the probe cannot walk them structurally the way
# `noticeBoardClaims` walks the Dashboard's. A name is all there is.

#: The cards whose *whole purpose* is to name a target for tonight. Losing one of
#: these from the list would take the paragraph back to the half that never
#: disagreed, which is the drift v0.445.0 was found in the gap between.
TONIGHT_PRESCRIBERS = {"closing-season", "plan-week"}


def _tonight_ids() -> list[str]:
    """The ids in the probe's ``TONIGHT_PRESCRIPTIVE`` array.

    Fails loudly when the declaration can't be found, for the same reason
    :func:`_prescriptive_ids` does.
    """
    src = PROBE.read_text(encoding="utf-8")
    m = re.search(r"^const TONIGHT_PRESCRIPTIVE = \[(.*?)\];", src, re.S | re.M)
    assert m, (
        "could not find `const TONIGHT_PRESCRIPTIVE = [...]` in dogfood_probe.mjs"
    )
    ids = re.findall(r'"([a-z0-9-]+)"', m.group(1))
    assert ids, "TONIGHT_PRESCRIPTIVE is empty — the probe would print nothing"
    return ids


def test_every_tonight_id_the_probe_reads_is_rendered_by_a_real_card() -> None:
    rendered = _rendered_testids()
    missing = [i for i in _tonight_ids() if i not in rendered]
    assert not missing, (
        "dogfood_probe.mjs collects Tonight data-testid(s) nothing renders: "
        f"{missing}. The pass still reports CLEAN and simply prints a shorter "
        "paragraph, which is the failure this guard exists for."
    )


def test_the_cards_that_name_a_target_for_tonight_stay_on_the_list() -> None:
    ids = set(_tonight_ids())
    assert TONIGHT_PRESCRIBERS <= ids, (
        "these are the cards that prescribe a target for tonight; reading the "
        "column without them is reading it without the disagreement: "
        f"{sorted(TONIGHT_PRESCRIBERS - ids)}"
    )


def test_the_probe_actually_reads_the_tonight_route() -> None:
    """A list nothing calls is decoration. The probe must collect it on
    ``/tonight`` and print it, or the ids above are guarded for nothing."""
    src = PROBE.read_text(encoding="utf-8")
    assert 'route === "/tonight"' in src, (
        "TONIGHT_PRESCRIPTIVE is never collected — no route reads it"
    )
    assert "prescriptiveClaims, TONIGHT_PRESCRIPTIVE" in src, (
        "the Tonight ids are not passed to the extractor that reads them"
    )
    assert "what the TONIGHT page SAYS" in src, (
        "nothing prints the paragraph, so a run would never see it"
    )
