"""A ratchet on how many separate notices each page can put on screen.

Owner, 2026-11-17: "the app is starting to get pretty cluttered again —
remember simplicity is sometimes best — or at least recursive organization."
The prose rule in AGENTS.md §1 ("prefer a consolidation over a new card") was
there; the pages grew anyway, one well-meant card at a time. So the count is
now mechanical, like the docs budget.

For every route file this counts the distinct card/note/banner-style
components it renders, plus its ``<Alert`` sites. Each route has a ceiling
(:data:`BUDGET`, measured 2026-11-17). A change that **raises** a page's count
fails: put the new thing inside an existing group, a collapsed section, the
page's notice board or a nested route instead. A change that **lowers** one
should lower its ceiling in the same commit, so the ratchet only turns one way.
Raising a ceiling needs the owner's sign-off, recorded in the commit.

Counting by name is crude on purpose: it is cheap, it cannot miss a new
``…Card`` dropped onto a page, and gaming it by renaming a card to dodge the
pattern is exactly the clutter it exists to stop — don't.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROUTES = Path(__file__).resolve().parents[1] / "frontend" / "src" / "routes"

_SURFACE = re.compile(
    r"<([A-Z][A-Za-z0-9]*(?:Card|Note|Banner|Nudge|Hint|Offer|Callout|Notice|Strip|Prompt|Tip|Warning))\b")
_ALERT = re.compile(r"<Alert\b")

#: Ceiling per route file: (distinct surface components, <Alert> sites).
#: Lower these as pages are consolidated; never raise one without owner sign-off.
BUDGET: dict[str, tuple[int, int]] = {
    "Target.tsx": (30, 13),
    "Dashboard.tsx": (23, 2),
    "Editor.tsx": (6, 16),
    "History.tsx": (6, 1),
    "SkySoFar.tsx": (6, 0),
    "Tonight.tsx": (5, 3),
    "Library.tsx": (5, 0),
    "MoonSun.tsx": (3, 5),
    "Gallery.tsx": (3, 3),
    "YourYear.tsx": (3, 0),
    "Settings.tsx": (2, 5),
    "Stack.tsx": (2, 40),
    "Jobs.tsx": (2, 10),
    "Compare.tsx": (1, 4),
    "Seestar.tsx": (1, 3),
}
#: A route not listed above may hold at most this many of each.
DEFAULT_BUDGET = (3, 3)


def _count(path: Path) -> tuple[int, int]:
    src = path.read_text(encoding="utf-8")
    return len(set(_SURFACE.findall(src))), len(_ALERT.findall(src))


def _route_files() -> list[Path]:
    return sorted(p for p in ROUTES.glob("*.tsx") if not p.name.endswith(".test.tsx"))


@pytest.mark.parametrize("path", _route_files(), ids=lambda p: p.name)
def test_no_page_grows_more_notices(path: Path) -> None:
    surfaces, alerts = _count(path)
    cap_s, cap_a = BUDGET.get(path.name, DEFAULT_BUDGET)
    assert surfaces <= cap_s and alerts <= cap_a, (
        f"{path.name} now renders {surfaces} card/note/banner kinds (ceiling {cap_s}) and "
        f"{alerts} <Alert> sites (ceiling {cap_a}). The owner finds the app cluttered: put the "
        "new thing inside an existing group, a collapsed section, the notice board or a nested "
        "route instead of adding a surface (AGENTS.md §1, the UI rule)."
    )


def test_budget_lists_only_real_routes() -> None:
    names = {p.name for p in _route_files()}
    assert set(BUDGET) <= names, sorted(set(BUDGET) - names)


def test_the_counter_sees_what_it_claims() -> None:
    sample = '<FooCard /> <FooCard/> <BarNote x={1}> <Alert color="red"> <Alerts> <Card>'
    assert set(_SURFACE.findall(sample)) == {"FooCard", "BarNote"}
    assert len(_ALERT.findall(sample)) == 1
