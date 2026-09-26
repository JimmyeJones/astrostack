"""Every ``reject_reason`` the engine writes has a plain-language label of its own.

A rejected sub's badge on the Target page is the one place a beginner reads *why*
a frame was left out, and the mapping that writes it —
``frontend/src/rejectReason.ts`` — is a **hand mirror** of a vocabulary owned by
the Python that stores those reasons. Mirroring a list by hand is how a list goes
stale: two reasons the app writes had no label of their own and fell through the
generic ``auto:`` branch, so the owner's frames table showed him
``Auto: seestar_output`` and ``Auto: file_missing`` — the internal identifiers,
verbatim, on the friendliness surface (AGENTS.md §1 priority 3).

This file is the version of that hole that cannot come back. It derives the
vocabulary from the **code that writes it** (every ``reject_reason=`` keyword,
``fields["reject_reason"] =`` and ``row.reject_reason =`` in ``seestack/`` and
``webapp/``, read with :mod:`ast` so a docstring's ``solve_failed:…`` is not
mistaken for a write) and asserts the frontend names each one. A reason
*swallowed* by a broader prefix is the failure this catches: being covered by
``auto:`` is not the same as having a label.

**A new reason is not a bug; having no label is.** Give it one in
``EXACT_LABELS``; or, if its suffix is genuinely data (a metric, a solver
message, an exception), add its namespace to ``HANDLED_PREFIXES`` there.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from seestack.io import project as project_mod
from seestack.qc import grading
from webapp import rejection_summary

_ROOT = Path(__file__).resolve().parents[1]
_LABELS_TS = _ROOT / "frontend" / "src" / "rejectReason.ts"
_PY_DIRS = ("seestack", "webapp")

#: Write sites whose stored string cannot be derived from the source, with the
#: reason. Keep this tiny, and say what the reason *is* — that sentence is what
#: the next reader needs.
_EXEMPT: dict[str, str] = {
    "seestack/qc/runner.py:113": (
        "f\"{reason}:…\" — the namespace is a local chosen one line above "
        "(`qc_error` retryable / `qc_error_final` terminal); both are covered by "
        "the `qc_error` entry in HANDLED_PREFIXES, which a vitest case exercises."
    ),
    "seestack/stack/stacker.py:2754": (
        "a plain-English sentence composed at stack time (\"bad plate-solve "
        "(footprint far from the group)\") — deliberately shown verbatim, which is "
        "what rejectReasonLabel's fall-through is for."
    ),
}


def _literals(node: ast.expr) -> tuple[set[str], set[str], bool]:
    """Split one assigned value into (exact reasons, namespace prefixes, opaque?).

    Recurses through the conditionals and ``or`` fallbacks the writers use
    (``None if accept else "user"``, ``body.reject_reason or "user"``). Reading
    another row's reason (an attribute or subscript) stores no new vocabulary, so
    it contributes nothing and is not opaque.
    """
    exact: set[str] = set()
    prefixes: set[str] = set()
    opaque = False
    if isinstance(node, ast.Constant):
        if isinstance(node.value, str):
            exact.add(node.value)
    elif isinstance(node, ast.JoinedStr):
        head = node.values[0] if node.values else None
        if isinstance(head, ast.Constant) and isinstance(head.value, str):
            prefixes.add(head.value)
        else:
            opaque = True
    elif isinstance(node, ast.Name):
        value = getattr(project_mod, node.id, None)
        if isinstance(value, str) and node.id.startswith("REJECT_REASON_"):
            exact.add(value)
        else:
            opaque = True
    elif isinstance(node, ast.IfExp):
        for branch in (node.body, node.orelse):
            e, p, o = _literals(branch)
            exact |= e
            prefixes |= p
            opaque = opaque or o
    elif isinstance(node, ast.BoolOp):
        for branch in node.values:
            e, p, o = _literals(branch)
            exact |= e
            prefixes |= p
            opaque = opaque or o
    elif isinstance(node, (ast.Attribute, ast.Subscript)):
        pass  # copies an existing row's reason — no new vocabulary
    else:
        opaque = True
    return exact, prefixes, opaque


def _write_sites() -> list[tuple[str, ast.expr]]:
    """Every place the Python side assigns a ``reject_reason``, as (site, value)."""
    out: list[tuple[str, ast.expr]] = []
    for directory in _PY_DIRS:
        for path in sorted((_ROOT / directory).rglob("*.py")):
            tree = ast.parse(path.read_text(), filename=str(path))
            rel = path.relative_to(_ROOT).as_posix()
            for node in ast.walk(tree):
                values: list[ast.expr] = []
                if isinstance(node, ast.keyword) and node.arg == "reject_reason":
                    values.append(node.value)
                elif isinstance(node, ast.Assign):
                    for target in node.targets:
                        if (isinstance(target, ast.Subscript)
                                and isinstance(target.slice, ast.Constant)
                                and target.slice.value == "reject_reason"):
                            values.append(node.value)
                        elif (isinstance(target, ast.Attribute)
                                and target.attr == "reject_reason"):
                            values.append(node.value)
                for value in values:
                    out.append((f"{rel}:{value.lineno}", value))
    return out


def _ts_record(name: str) -> dict[str, str]:
    """Parse one ``export const <name>: Record<string, string> = { … }`` table."""
    src = _LABELS_TS.read_text()
    start = src.index(f"export const {name}")
    body = src[src.index("{", start) + 1: src.index("};", start)]
    body = re.sub(r"//[^\n]*", "", body)  # drop the comments between entries
    return {
        (m.group(1) or m.group(2)): m.group(3)
        for m in re.finditer(r"""(?:"([^"]+)"|([A-Za-z_][\w]*))\s*:\s*"([^"]*)"\s*,""",
                             body)
    }


def _ts_prefixes() -> list[str]:
    src = _LABELS_TS.read_text()
    start = src.index("export const HANDLED_PREFIXES")
    body = src[src.index("[", start): src.index("];", start)]
    return re.findall(r'"([^"]+)"', body)


def _vocabulary() -> tuple[set[str], set[str]]:
    """The exact reasons and namespace prefixes the code can store."""
    exact: set[str] = set()
    prefixes: set[str] = set()
    for site, value in _write_sites():
        e, p, opaque = _literals(value)
        exact |= e
        prefixes |= p
        if opaque:
            assert site in _EXEMPT, (
                f"{site} stores a reject_reason this test cannot derive. Either "
                "give it a literal, or exempt it here with the reason why."
            )
    return exact, prefixes


def test_every_reason_the_code_writes_has_a_label_of_its_own():
    exact, _ = _vocabulary()
    labelled = _ts_record("EXACT_LABELS")
    missing = sorted(r for r in exact if r not in labelled)
    assert not missing, (
        "these reject_reasons are written by the app but have no label of their "
        f"own in {_LABELS_TS.name}, so the owner is shown the raw code: {missing}"
    )


def test_every_namespace_the_code_writes_is_one_the_frontend_slices():
    _, prefixes = _vocabulary()
    handled = _ts_prefixes()
    missing = sorted(p for p in prefixes
                     if not any(p.startswith(h) for h in handled))
    assert not missing, (
        f"these reject_reason namespaces are written by the app but {_LABELS_TS.name} "
        f"does not recognise them: {missing}"
    )


def test_the_exempt_list_names_only_sites_that_still_exist():
    """An exemption for a write site that has gone is a comment pretending to be
    a rule — and the next real opaque write would be silently excused by it."""
    sites = {site for site, _ in _write_sites()}
    stale = sorted(s for s in _EXEMPT if s not in sites)
    assert not stale, f"these exempted write sites no longer exist: {stale}"


def test_the_metric_labels_say_what_the_engine_says():
    """`seestack.qc.grading` owns what a metric is *called*; the frontend's copy
    must agree word for word, or one frame is described two ways depending on
    which surface is describing it."""
    assert _ts_record("METRIC_LABEL") == dict(grading.METRIC_LABELS)


def test_every_reason_the_code_writes_groups_into_a_named_bucket():
    """The badge says it in three words; the breakdown above it says it in a
    sentence. Both are hand mirrors of the same vocabulary, so both are checked:
    an exact reason the app writes about a *file* falling into "Left out for
    other reasons" is the same failure as showing its raw code."""
    exact, _ = _vocabulary()
    vague = sorted(r for r in exact
                   if rejection_summary._bucket_for(r) == "other")
    assert not vague, (
        "these reject_reasons are written by the app but webapp/rejection_summary.py "
        f"has no bucket for them, so the breakdown says only \"other\": {vague}"
    )
