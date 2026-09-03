"""Every webapp caller of the night pace must say which nights it means.

``recent_night_pace_s`` splits a target's history into "nights" two different
ways, and the difference is a factor of about two on exactly the shape a Seestar
owner shoots most: a night done in two goes (an evening run, bed, a pre-dawn
run). Passed a ``night_of``, those halves are **one** night carrying their whole
integration; without one, the split is session-by-session and each half enters
the median on its own — which biases the pace low and tells a beginner they need
*more* clear nights than they really do. That was a real, shipped bug (v0.329.4).

The fix made the parameter **optional**, defaulting to the old session split, and
that default is right: a caller with no longitude to hand must not have its
number silently change. It is also a trap — a fourth surface that wants a pace
gets the halved figure by simply not knowing to pass it, which is precisely the
bug that was just fixed. Prose in the docstring is not enforcement; this is.

**The exception is stated, never silent.** A caller that genuinely wants
*sessions* rather than observing nights (a last-session recap legitimately does)
opts out with a marker comment naming its reason, on the call or the line above:

    pace = recent_night_pace_s(proj)  # night-pace: sessions — this is one session

so the guard is a prompt to decide, not a rule that has to be worked around.
"""

from __future__ import annotations

import ast
from pathlib import Path

WEBAPP = Path(__file__).resolve().parents[2] / "webapp"

#: How a caller declares it means sessions, not observing nights, on purpose.
OPT_OUT = "night-pace: sessions"


def _called_name(func: ast.expr) -> str | None:
    """The bare name a call site uses — ``f(...)`` or ``mod.f(...)``."""
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _pace_calls() -> list[tuple[Path, int, ast.Call]]:
    found: list[tuple[Path, int, ast.Call]] = []
    for path in sorted(WEBAPP.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and _called_name(node.func) == "recent_night_pace_s"):
                found.append((path, node.lineno, node))
    return found


def _opted_out(path: Path, lineno: int) -> bool:
    """Whether the call at ``lineno`` carries the opt-out marker on its own line
    or the line above (where a long call's comment naturally lands)."""
    lines = path.read_text(encoding="utf-8").split("\n")
    window = lines[max(0, lineno - 2):lineno + 1]
    return any(OPT_OUT in line for line in window)


def test_the_guard_is_actually_looking_at_something():
    """A guard that silently stops finding call sites — a rename, a move out of
    ``webapp/`` — would sit permanently green while checking nothing."""
    calls = _pace_calls()
    assert calls, "no recent_night_pace_s call found in webapp/ — has it moved?"
    files = {p.name for p, _, _ in calls}
    assert {"stats.py", "plan.py"} <= files, files


def test_every_webapp_caller_says_which_nights_it_means():
    for path, lineno, node in _pace_calls():
        if _opted_out(path, lineno):
            continue
        kwargs = {kw.arg for kw in node.keywords}
        assert "night_of" in kwargs, (
            f"{path.relative_to(WEBAPP.parent)}:{lineno} calls "
            "recent_night_pace_s without night_of, so it will quote the "
            "session-split pace — roughly half a night's integration on a night "
            "shot in two goes. Pass the same night_of the Nights card uses, or "
            f"mark the call `# {OPT_OUT} — <why>` if sessions really are what "
            "you mean."
        )


def test_a_starred_call_is_not_mistaken_for_a_keyword():
    """``f(proj, **opts)`` hides whether ``night_of`` is there, so it must not
    read as if it were — the guard would then pass on the very shape that can
    smuggle the default through."""
    node = ast.parse("recent_night_pace_s(proj, **opts)").body[0].value
    assert {kw.arg for kw in node.keywords} == {None}
    assert "night_of" not in {kw.arg for kw in node.keywords}
