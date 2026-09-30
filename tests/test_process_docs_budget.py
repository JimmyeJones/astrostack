"""The docs-growth rule (AGENTS.md §2, "the three-file rule"), enforced.

The rule has been written down since 2026-09-04 and unenforced since then, and
the 2026-09-30 audit (D1/D2) found what that costs: "Bugs (fix these first)" —
which must hold *open bugs and nothing else* — carried struck-through shipped
entries, ``✅ SHIPPED`` paragraphs and an "OWNER ANSWERS" notes block, and
``docs/IMPROVEMENTS.md`` grows by roughly a hundred lines per merged PR, so no
agent can read it in a run and every agent is necessarily skimming. Skimming is
the common cause behind stale entries surviving, ideas being re-derived and
items being built twice.

Three checks, each with its fix path in the failure message:

(a) the Bugs section holds open bugs only — no strike-throughs, no shipped
    markers, no notes blocks;
(b) a change may not grow ``docs/IMPROVEMENTS.md`` by more than
    :data:`GROWTH_BUDGET_LINES` unless it files a Bugs entry marked
    *reproduced* or *measured* (which is the one thing §2 lets a run add);
(c) ``docs/PROCESS-NOTES.md`` and ``docs/SHIPPED.md`` stay under generous
    absolute ceilings, set just above their 2026-09-30 sizes.

(b) needs a base to diff against and reads it from ``DOCS_BUDGET_BASE`` (a git
ref); ``.github/workflows/docs-budget.yml`` sets it to the PR's base commit.
Without it the check is skipped, so a plain local ``pytest`` run is unaffected.
The check compares *line counts* and reads the diff only for the exemption, so a
union merge of two docs changes cannot trip it by itself; and a Scout run that
files verified bugs is exempt by construction, which is what keeps this from
failing legitimate docs-only work.

Standalone on purpose: no ``seestack``/``webapp`` import, so the workflow runs it
with nothing but ``pytest`` installed.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
IMPROVEMENTS = ROOT / "docs" / "IMPROVEMENTS.md"
PROCESS_NOTES = ROOT / "docs" / "PROCESS-NOTES.md"
SHIPPED = ROOT / "docs" / "SHIPPED.md"

BUGS_HEADING = "## Bugs (fix these first)"

#: How many lines a single change may add to ``docs/IMPROVEMENTS.md`` without
#: filing a verified bug. §2: "a run must leave it no longer than it found it
#: unless it is filing a verified bug"; forty lines is room for a claim line, a
#: Shipped one-liner or two and a lead, not for a spec.
GROWTH_BUDGET_LINES = 40

#: Absolute ceilings, set just above the 2026-09-30 sizes (15,786 and 58,971
#: lines) with a few months' headroom. When one is hit: **archive**, never
#: delete — move the oldest entries (whole, in order) to a dated file under
#: ``docs/archive/`` and leave a one-line pointer where they were.
PROCESS_NOTES_CEILING = 18_000
SHIPPED_CEILING = 64_000

#: What marks an entry as shipped or as a note rather than an open bug. Strike-
#: through (``~~``), the shipped tick, a version-stamped SHIPPED/FIXED/CLOSED
#: marker, and the clipboard the owner-answers notes block is headed with.
_NOT_OPEN = re.compile(
    r"~~|✅|\b(?:SHIPPED|FIXED|CLOSED)\b\s+(?:as\s+|with\s+)?(?:\*\*)?v0\.\d|📋"
)

#: What makes a Bugs entry a *verified* one: the entry says it was reproduced
#: or measured. Case-insensitive, whole words, so "unreproduced" does not count.
_VERIFIED = re.compile(r"\b(?:reproduced|measured)\b", re.IGNORECASE)


def _bugs_section(text: str) -> tuple[int, list[str]]:
    """``(first line number, lines)`` of the Bugs section, heading excluded,
    ending at the next ``## `` heading."""
    lines = text.splitlines()
    try:
        start = next(i for i, ln in enumerate(lines) if ln.strip() == BUGS_HEADING)
    except StopIteration:  # pragma: no cover — the heading is load-bearing
        pytest.fail(f"{IMPROVEMENTS.name} has no '{BUGS_HEADING}' heading")
    end = next((i for i in range(start + 1, len(lines))
                if lines[i].startswith("## ")), len(lines))
    return start + 2, lines[start + 1:end]


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True,
    ).stdout


# --- (a) open bugs only ---------------------------------------------------


def test_the_bugs_section_holds_open_bugs_only():
    first, lines = _bugs_section(IMPROVEMENTS.read_text(encoding="utf-8"))
    offenders = [f"  line {first + i}: {ln.strip()[:100]}"
                 for i, ln in enumerate(lines) if _NOT_OPEN.search(ln)]
    assert not offenders, (
        f"'{BUGS_HEADING}' in docs/IMPROVEMENTS.md must hold open bugs and nothing "
        f"else (AGENTS.md §2), but {len(offenders)} line(s) carry a shipped marker "
        "(~~ / ✅ / SHIPPED|FIXED|CLOSED vN) or a notes block (📋):\n"
        + "\n".join(offenders[:20])
        + ("\n  …" if len(offenders) > 20 else "")
        + "\nFix: cut a shipped entry *whole* to docs/SHIPPED.md (newest first, "
        "headed by version + date) and leave a one-line '✅ vX.Y.Z …' under "
        "'## Shipped'; move a note or an owner answer to docs/PROCESS-NOTES.md "
        "(or the gate it answers under 'Needs owner sign-off'); an open entry "
        "with a shipped *part* keeps the open part and points at SHIPPED.md for "
        "the rest. Nothing is deleted outright."
    )


# --- (b) growth per change ------------------------------------------------


def _base_ref() -> str | None:
    ref = os.environ.get("DOCS_BUDGET_BASE", "").strip()
    if not ref:
        return None
    try:
        _git("rev-parse", "--verify", f"{ref}^{{commit}}")
    except subprocess.CalledProcessError:
        pytest.skip(f"DOCS_BUDGET_BASE={ref!r} is not a commit this checkout has "
                    "(fetch it, or unset the variable to skip the growth check)")
    return ref


def test_a_change_does_not_grow_the_backlog_past_its_budget():
    base = _base_ref()
    if base is None:
        pytest.skip("DOCS_BUDGET_BASE unset: the per-change growth check runs in "
                    ".github/workflows/docs-budget.yml against the PR's base")
    try:
        before = _git("show", f"{base}:docs/IMPROVEMENTS.md")
    except subprocess.CalledProcessError:
        pytest.skip("docs/IMPROVEMENTS.md does not exist at the base")
    after = IMPROVEMENTS.read_text(encoding="utf-8")
    growth = len(after.splitlines()) - len(before.splitlines())
    if growth <= GROWTH_BUDGET_LINES:
        return
    # The one exemption: the change files a verified bug. Read as "an added line
    # inside today's Bugs section says reproduced/measured".
    diff = _git("diff", base, "--", "docs/IMPROVEMENTS.md")
    added = {ln[1:].strip() for ln in diff.splitlines()
             if ln.startswith("+") and not ln.startswith("+++")}
    _, bugs = _bugs_section(after)
    filed = [ln for ln in bugs if ln.strip() in added and _VERIFIED.search(ln)]
    assert filed, (
        f"docs/IMPROVEMENTS.md grew by {growth} lines against {base} "
        f"(budget {GROWTH_BUDGET_LINES}) and the change files no Bugs entry marked "
        "'reproduced' or 'measured'. AGENTS.md §2: a run must leave the working "
        "list no longer than it found it unless it is filing a verified bug. "
        "Fix: cut what shipped to docs/SHIPPED.md, move notes and sweep records to "
        "docs/PROCESS-NOTES.md, keep an idea to a few lines with a why, a pillar "
        "and a size — or, if this really is a verified bug, say 'reproduced' or "
        "'measured' in its entry."
    )


# --- (c) absolute ceilings --------------------------------------------------


@pytest.mark.parametrize("path, ceiling", [
    (PROCESS_NOTES, PROCESS_NOTES_CEILING),
    (SHIPPED, SHIPPED_CEILING),
])
def test_the_record_files_stay_under_their_ceilings(path: Path, ceiling: int):
    n = len(path.read_text(encoding="utf-8").splitlines())
    assert n <= ceiling, (
        f"docs/{path.name} is {n:,} lines, over its {ceiling:,}-line ceiling. "
        "Fix: archive, never delete — move the *oldest* entries, whole and in "
        f"order, to docs/archive/{path.stem}-<YYYY-MM>.md (create the folder if it "
        "is missing), leave one line where they were saying what moved and where, "
        "and raise the ceiling here only if the archive step itself is what is "
        "being avoided."
    )


def test_the_ceilings_are_generous_not_tight():
    """A ceiling set at today's size would fail the next honest PR."""
    for path, ceiling in ((PROCESS_NOTES, PROCESS_NOTES_CEILING),
                          (SHIPPED, SHIPPED_CEILING)):
        n = len(path.read_text(encoding="utf-8").splitlines())
        assert ceiling - n >= 500, (
            f"docs/{path.name} is within 500 lines of its ceiling ({n:,}/{ceiling:,}); "
            "archive the oldest entries now rather than on the PR that trips it.")
