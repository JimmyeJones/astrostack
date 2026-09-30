"""The probe's ``KNOWN_VIEW_SWITCHES`` must still name pages that have one.

``scripts/dogfood_probe.mjs`` no longer carries a list of the views a page keeps
behind a click — it reads them off the rendered page (``viewSwitches``), so a
filter added tomorrow is swept without anyone remembering. That is strictly more
durable than the two-string ``COMPARE_MODES`` it replaces, and it buys one new
way to fail silently: discovery keys off **Mantine's own class names**, so a
Mantine rename would find nothing, on every route, and a sweep that suddenly
covers only landing views would report CLEAN exactly as it did before.

``KNOWN_VIEW_SWITCHES`` is the answer to that — the probe prints a finding when
a route it names yields nothing to click. Which makes the list itself the thing
that rots: delete a SegmentedControl from one of those pages and the probe
starts crying wolf on every pass until someone reads the source. This test is
the other half, in the same shape as ``test_dogfood_probe_anchors.py``: every
route named must be one whose component really does render a
``<SegmentedControl``.

Deliberately one-directional. A page can *have* a SegmentedControl that this
sweep's library never renders — Gallery's and History's are behind a modal and
on data the sample does not have — so "every file with a SegmentedControl is on
the list" would be false for honest reasons, and asserting it would push the
probe into warning about pages whose landing state legitimately has no switch.
"""

from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_PROBE = _ROOT / "scripts" / "dogfood_probe.mjs"
_ROUTES_DIR = _ROOT / "frontend" / "src" / "routes"

#: Which route component answers each route the probe names. Written out rather
#: than parsed from `main.tsx`: five entries, and an explicit table is the thing
#: a reader can check against the app in one glance.
_ROUTE_COMPONENT = {
    "/compare": "Compare.tsx",
    "/logs": "Logs.tsx",
    "/life-list": "LifeList.tsx",
    "/tonight": "Tonight.tsx",
    "/sky": "Sky.tsx",
}

_KNOWN_RE = re.compile(r"const KNOWN_VIEW_SWITCHES\s*=\s*\[(.*?)\]\s*;", re.DOTALL)
_QUOTED_RE = re.compile(r'"(/[^"\n]*)"')


def _known_view_switches() -> list[str]:
    body = _KNOWN_RE.search(_PROBE.read_text(encoding="utf-8"))
    assert body, "dogfood_probe.mjs no longer declares KNOWN_VIEW_SWITCHES"
    return _QUOTED_RE.findall(body.group(1))


def test_every_named_route_really_has_a_view_switch() -> None:
    named = _known_view_switches()
    assert named, "KNOWN_VIEW_SWITCHES is empty — nothing would catch a silent stop"

    unmapped = sorted(set(named) - set(_ROUTE_COMPONENT))
    assert not unmapped, (
        f"KNOWN_VIEW_SWITCHES names routes this test cannot check: {unmapped}. "
        "Add each to _ROUTE_COMPONENT above with the route component that "
        "renders its switch."
    )

    without = []
    for route in named:
        src = (_ROUTES_DIR / _ROUTE_COMPONENT[route]).read_text(encoding="utf-8")
        if "<SegmentedControl" not in src:
            without.append(f"{route} ({_ROUTE_COMPONENT[route]})")
    assert not without, (
        "these routes are named in KNOWN_VIEW_SWITCHES but their component no "
        f"longer renders a <SegmentedControl: {without}. The probe will report "
        "a missing view switch on every pass until this list is corrected — "
        "drop the route from KNOWN_VIEW_SWITCHES in scripts/dogfood_probe.mjs."
    )


def test_the_probe_discovers_switches_rather_than_listing_them() -> None:
    """The list that used to rot is gone, and must not come back.

    ``COMPARE_MODES = ["Split", "Blink"]`` covered one page for six weeks while
    `/life-list`, `/tonight`, `/logs`, `/sky` and the Stack form's advanced
    panel went unswept — not because anyone decided they did not matter, but
    because a hand-written list only ever holds what its author was looking at.
    """
    text = _PROBE.read_text(encoding="utf-8")
    assert "function viewSwitches" in text, (
        "scripts/dogfood_probe.mjs no longer discovers view switches off the "
        "page. Whatever replaced it, a hand-written list of labels is the one "
        "shape this test exists to keep out."
    )
    assert not re.search(r"\bconst\s+COMPARE_MODES\b", text), (
        "COMPARE_MODES is declared again. It listed two labels on one route; "
        "viewSwitches finds every switch on every route with no list to keep in "
        "step. (The name may still appear in a comment explaining the history.)"
    )
