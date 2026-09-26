"""Every registered frontend route is one the dogfood probe actually opens.

``scripts/dogfood_probe.mjs`` carries a ``ROUTES`` table whose own comment says
it is "the real route table (frontend/src/main.tsx)" — and mirroring a list by
hand is how a list goes stale. It had: ``/show`` ("Show & tell"), ``/live``
("Tonight, live" — the page whose docstring says it is *meant to be left open on
a phone for hours*, and the only nav entry that was missing) and
``/sky-so-far/:year`` were registered routes that **no dogfood pass had ever
photographed**, so nothing had measured their height, their overflow, their
squeezed text or their clipped badges at 420 px.

That is the same hole as the missing observing site, the empty ``incoming/``,
the click-only Compare comparators and the 1:1 editor preview — a surface the
tooling is structurally unable to see — and this file is the version of it that
cannot come back: a route added to ``main.tsx`` and not to the probe goes red
here, in the suite every run has to pass, rather than being noticed by whoever
next reads both files side by side.

**A new route is not a bug; being un-probed is.** Adding it to the probe is the
fix; adding it to :data:`_EXEMPT` is also a fix when the route genuinely cannot
be swept, but write down *why*, because that sentence is what the next reader
needs.
"""

from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_MAIN = _ROOT / "frontend" / "src" / "main.tsx"
_PROBE = _ROOT / "scripts" / "dogfood_probe.mjs"

#: Routes the probe deliberately does not open, with the reason. Keep this tiny.
_EXEMPT: dict[str, str] = {
    # `/settings/:section` renders the *same* component as `/settings`, scrolled
    # to one panel (`settingsSections.ts`), so sweeping every section would
    # re-photograph one page N times for no new layout. The page itself is swept.
    "settings/*": "same component as /settings, deep-linked to a panel",
}

#: `{ path: "x", … }` in the router config. `main.tsx` holds exactly one route
#: table, so a file-wide scan is the whole of it.
_MAIN_PATH_RE = re.compile(r"\bpath:\s*\"([^\"]*)\"")

#: Every route-shaped literal in the probe — plain strings and template literals
#: alike, because the two routes it cannot write as constants (`/compare`, whose
#: query string carries two picture refs, and the year drill-down) are built in
#: helper functions rather than listed in `ROUTES`.
_PROBE_LITERAL_RE = re.compile(r"""(?:"(/[^"\n]*)"|'(/[^'\n]*)'|`(/[^`\n]*)`)""")


def _shape(route: str) -> str:
    """A route reduced to what makes two references to it the same page.

    Strips the query/hash (``/compare?a=…`` is the Compare page), drops the
    surrounding slashes, and replaces every parameter — React Router's
    ``:safe`` and JavaScript's ``${SAFE}`` alike — with ``*``, so the two sides
    of this test can be compared as sets.
    """
    route = re.split(r"[?#]", route, maxsplit=1)[0]
    route = re.sub(r"\$\{[^}]*\}", "*", route)
    route = re.sub(r":[A-Za-z_][A-Za-z0-9_]*", "*", route)
    return route.strip("/")


def _registered_routes() -> set[str]:
    return {
        shape
        for raw in _MAIN_PATH_RE.findall(_MAIN.read_text(encoding="utf-8"))
        if (shape := _shape(raw))          # the layout route itself is "/"
    }


def _probed_routes() -> set[str]:
    text = _PROBE.read_text(encoding="utf-8")
    out: set[str] = set()
    for groups in _PROBE_LITERAL_RE.findall(text):
        raw = next(g for g in groups if g)
        out.add(_shape(raw))
    return out


def test_the_probe_opens_every_route_the_app_registers() -> None:
    registered = _registered_routes()
    # Sanity: the scan found a real route table, not zero matches from a regex
    # that stopped matching after a refactor.
    assert len(registered) >= 20, registered
    assert "library" in registered and "targets/*" in registered, registered

    probed = _probed_routes()
    assert "library" in probed and "targets/*" in probed, sorted(probed)

    missing = sorted(registered - probed - set(_EXEMPT))
    assert not missing, (
        "these routes are registered in frontend/src/main.tsx but no dogfood "
        f"pass ever opens them: {missing}. Add each to ROUTES in "
        "scripts/dogfood_probe.mjs (a page nothing photographs is a page whose "
        "phone layout nobody has checked), or to _EXEMPT above with the reason."
    )


def test_every_exemption_is_still_a_real_route() -> None:
    """An exemption that no longer names a route is dead weight that hides the
    next one — the failure mode a stale allow-list always has."""
    registered = _registered_routes()
    stale = sorted(set(_EXEMPT) - registered)
    assert not stale, (
        f"_EXEMPT names routes that main.tsx no longer registers: {stale}. "
        "Delete them, so the list stays a statement about today's app."
    )
