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

And one route on the list renders its switch only on data a pass may not have,
which this file now covers too. `/tonight`'s switch is the object-type filter
inside "Start something new", and `Tonight.tsx` returns an alert in place of
that whole planning body without an observing site or a dark window — so on
`--empty` and `--no-site` the guard reported a Mantine rename about a control
that could not exist. `VIEW_SWITCH_PRECONDITIONS` in the probe exempts such a
route by asking the **running app** the same two questions the page's own early
returns ask; the tests below pin that it only ever exempts a route the guard
actually watches, and that the questions it asks are still the ones the page
is gated on.
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
_PRECOND_RE = re.compile(
    r"const VIEW_SWITCH_PRECONDITIONS\s*=\s*\{(.*?)\n\};", re.DOTALL)

#: The two fields `Tonight.tsx`'s early returns gate its planning body on — and
#: so the two the probe's `/tonight` precondition has to ask about. Named here
#: rather than inferred so a page that stops gating on one of them goes red
#: where somebody will read it.
_TONIGHT_GATE_FIELDS = ("location_source", "dark_window")


def _known_view_switches() -> list[str]:
    body = _KNOWN_RE.search(_PROBE.read_text(encoding="utf-8"))
    assert body, "dogfood_probe.mjs no longer declares KNOWN_VIEW_SWITCHES"
    return _QUOTED_RE.findall(body.group(1))


def _precondition_block() -> str:
    body = _PRECOND_RE.search(_PROBE.read_text(encoding="utf-8"))
    assert body, (
        "dogfood_probe.mjs no longer declares VIEW_SWITCH_PRECONDITIONS. "
        "Without it the view-switch guard reports a Mantine rename on every "
        "--empty / --no-site pass, because /tonight's switch is inside a "
        "planning body the page does not render without a site."
    )
    return body.group(1)


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


def test_a_data_gated_switch_only_ever_exempts_a_route_the_guard_watches() -> None:
    """A precondition is an exemption from a finding, so it must not invent one.

    A route named here but not in ``KNOWN_VIEW_SWITCHES`` exempts nothing and
    reads as cover for a page nobody checks; one not in ``_ROUTE_COMPONENT``
    cannot be checked by the test above either.
    """
    gated = _QUOTED_RE.findall(_precondition_block())
    assert gated, (
        "VIEW_SWITCH_PRECONDITIONS names no route. /tonight needs one: its "
        "switch lives inside a planning body Tonight.tsx replaces with an "
        "alert when there is no observing site."
    )
    known = set(_known_view_switches())
    stray = sorted(r for r in gated if r not in known)
    assert not stray, (
        f"these routes carry a view-switch precondition but are not in "
        f"KNOWN_VIEW_SWITCHES, so they exempt nothing: {stray}"
    )
    unmapped = sorted(r for r in gated if r not in _ROUTE_COMPONENT)
    assert not unmapped, (
        f"these gated routes have no entry in _ROUTE_COMPONENT: {unmapped}"
    )


def test_tonights_precondition_asks_what_its_page_is_actually_gated_on() -> None:
    """The exemption must track the page, not a snapshot of it.

    The precondition asks the running app rather than re-deriving the rule, and
    the fields it asks about are the ones ``Tonight.tsx``'s own early returns
    read. If the page stops gating on one of them, the probe is exempting
    `/tonight` for a reason that no longer holds — which is the same silent
    shrink in coverage the guard exists to prevent, arrived at from the other
    side.
    """
    block = _precondition_block()
    src = (_ROUTES_DIR / _ROUTE_COMPONENT["/tonight"]).read_text(encoding="utf-8")
    for field in _TONIGHT_GATE_FIELDS:
        assert field in block, (
            f"/tonight's precondition no longer asks about {field!r}, which "
            "Tonight.tsx returns an alert on."
        )
        assert field in src, (
            f"Tonight.tsx no longer reads {field!r}, so the probe's /tonight "
            "precondition is asking the wrong question. Re-read the page's "
            "early returns and update VIEW_SWITCH_PRECONDITIONS."
        )


def test_the_guard_consults_the_preconditions_before_reporting() -> None:
    """Declaring the map is not using it.

    Source-level like the rest of this file (the probe needs a browser and a
    running app to execute), and it pins the one line that turns the map into
    behaviour: the guard has to read it before it counts a finding.
    """
    text = _PROBE.read_text(encoding="utf-8")
    assert "VIEW_SWITCH_SKIPPED[switchPath]" in text, (
        "the view-switch guard no longer consults VIEW_SWITCH_SKIPPED, so a "
        "route whose switch this pass cannot render is reported as a finding "
        "again."
    )
