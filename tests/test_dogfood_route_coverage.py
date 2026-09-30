"""Every registered frontend route is one the dogfood probe actually opens.

``scripts/dogfood_probe.mjs`` carries a ``ROUTES`` table whose own comment says
it is "the real route table (frontend/src/main.tsx)" — and mirroring a list by
hand is how a list goes stale. Three registered routes had **never been
photographed by any dogfood pass**: ``/show`` ("Show and tell"), ``/live``
("Tonight, live" — the only nav entry that was missing, and the page whose own
docstring says it is *meant to be left open on a phone for hours*) and
``/sky-so-far/:year``. Nothing had measured their height, their overflow, their
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
#:
#: Empty on purpose. ``settings/*`` used to sit here, on the reasoning that it
#: "renders the same component as ``/settings``, scrolled to one panel, so
#: sweeping every section would re-photograph one page N times for no new
#: layout". That was wrong in both halves: ``SectionTabs`` is a **tab strip**,
#: not a scroll target, so ``/settings`` shows its *first* section and nothing
#: else, and the other six panels — mounted, because the sections share one edit
#: buffer, but hidden — have zero-size bounding rects that every one of the
#: probe's three DOM checks skips by construction. Six sections of the app's
#: tallest-by-content page were therefore never drawn, never measured and never
#: watched for a console error. The probe now opens each one, and
#: :func:`test_the_probe_opens_every_settings_section` keeps it that way.
_EXEMPT: dict[str, str] = {}

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


#: ``"folders",`` … inside ``export const SETTINGS_SECTIONS = [ … ] as const;``.
_SECTIONS_RE = re.compile(
    r"export const SETTINGS_SECTIONS\s*=\s*\[(.*?)\]\s*as const", re.DOTALL
)
#: ``"folders", "automation", …`` inside ``const SETTINGS_SECTIONS = [ … ];``.
_PROBE_SECTIONS_RE = re.compile(
    r"const SETTINGS_SECTIONS\s*=\s*\[(.*?)\]\s*;", re.DOTALL
)
_QUOTED_RE = re.compile(r"\"([a-z0-9-]+)\"")


def _app_settings_sections() -> set[str]:
    src = (_ROOT / "frontend" / "src" / "settingsSections.ts").read_text("utf-8")
    body = _SECTIONS_RE.search(src)
    assert body, "settingsSections.ts no longer declares SETTINGS_SECTIONS"
    return set(_QUOTED_RE.findall(body.group(1)))


def _probe_settings_sections() -> set[str]:
    body = _PROBE_SECTIONS_RE.search(_PROBE.read_text(encoding="utf-8"))
    if body is None:
        return set()
    return set(_QUOTED_RE.findall(body.group(1)))


def test_the_probe_opens_every_settings_section() -> None:
    """Settings is seven pages behind one route, and only one of them was swept.

    ``settings/*`` satisfies the route test above with a single template
    literal, which is exactly the kind of "covered" that covers nothing — so the
    sections get their own check, against the app's own list. A section added to
    :data:`SETTINGS_SECTIONS` and not to the probe goes red here.
    """
    app = _app_settings_sections()
    assert len(app) >= 5 and "maintenance" in app, app
    missing = sorted(app - _probe_settings_sections())
    assert not missing, (
        "these Settings sections are registered in "
        "frontend/src/settingsSections.ts but no dogfood pass ever opens them: "
        f"{missing}. Add each to SETTINGS_SECTIONS in scripts/dogfood_probe.mjs "
        "— an inactive Tabs.Panel is hidden, so a /settings shot measures the "
        "first section and is blind to every other one."
    )
    stale = sorted(_probe_settings_sections() - app)
    assert not stale, (
        f"the probe sweeps Settings sections the app no longer has: {stale}. "
        "Each is a 404-shaped shot that reads as a bug in the app."
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
