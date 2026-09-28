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
#:
#: **Keyed on the write itself — file, enclosing function, expression source —
#: and deliberately not on a line number.** A line number is wrong in both
#: directions: an edit *anywhere above* the write re-points the key and fails
#: these four tests for a change that has nothing to do with reject reasons (it
#: cost two consecutive runs, 2026-09-27 and 2026-09-28), while a write whose
#: expression is *rewritten in place* keeps its exemption and its stale sentence.
#: Keying on the expression fixes both: it survives every edit that does not touch
#: the write, and any edit that does touch it goes through
#: ``test_the_exempt_list_names_only_sites_that_still_exist``.
_EXEMPT: dict[str, str] = {
    "seestack/qc/runner.py::apply_qc_result_to_db::f{reason}:{result.error or unknown}": (
        "f\"{reason}:…\" — the namespace is a local chosen one line above "
        "(`qc_error` retryable / `qc_error_final` terminal); both are covered by "
        "the `qc_error` entry in HANDLED_PREFIXES, which a vitest case exercises."
    ),
    "seestack/stack/stacker.py::run_stack::reason": (
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


#: ``ast.unparse`` is not stable across CPython **patch** releases in the one thing a
#: site key must not depend on: which quote character it puts *outside* an f-string
#: that contains a quoted literal. 3.12.3 emits ``f'…or 'unknown'…'`` (PEP 701 lets it
#: reuse the same quote); 3.12.14 and 3.11 emit ``f"…or 'unknown'…"``. Keying on the
#: raw unparse therefore made the exemption **environment-dependent** — it passed here
#: and took `main` red on the runner, which is worse than the line number it replaced.
#: Quote characters are exactly the part of the source that does not identify a write,
#: so they are dropped: the identifiers, operators and literal *contents* remain.
_QUOTES = re.compile(r"['\"]")


def _write_source(node: ast.expr) -> str:
    """The write's expression source, normalised so a site key cannot depend on the
    interpreter's choice of quote character (see :data:`_QUOTES`)."""
    return _QUOTES.sub("", ast.unparse(node))


def _enclosing_scopes(tree: ast.AST) -> list[tuple[int, int, str]]:
    """``(first_line, last_line, name)`` for every def in ``tree``, innermost last
    when sorted by span — so :func:`_scope_of` can name a write's own function."""
    out: list[tuple[int, int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.append((node.lineno, node.end_lineno or node.lineno, node.name))
    return out


def _scope_of(scopes: list[tuple[int, int, str]], lineno: int) -> str:
    """The name of the narrowest def containing ``lineno``, or ``"<module>"``.

    The *name*, not the line, is what makes a site key stable: renaming or moving
    the function is a change to the write's own context and should invalidate its
    exemption; editing something else in the file should not.
    """
    inner = [s for s in scopes if s[0] <= lineno <= s[1]]
    if not inner:
        return "<module>"
    return min(inner, key=lambda s: s[1] - s[0])[2]


def _write_sites() -> list[tuple[str, ast.expr]]:
    """Every place the Python side assigns a ``reject_reason``, as (site, value).

    ``site`` is ``<file>::<function>::<expression source>`` — see ``_EXEMPT`` for
    why it is not a line number.
    """
    out: list[tuple[str, ast.expr]] = []
    for directory in _PY_DIRS:
        for path in sorted((_ROOT / directory).rglob("*.py")):
            tree = ast.parse(path.read_text(), filename=str(path))
            rel = path.relative_to(_ROOT).as_posix()
            scopes = _enclosing_scopes(tree)
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
                    scope = _scope_of(scopes, value.lineno)
                    out.append((f"{rel}::{scope}::{_write_source(value)}", value))
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
                f"{site} (line {value.lineno}) stores a reject_reason this test "
                "cannot derive. Either give it a literal, or exempt it in _EXEMPT "
                "with the reason why."
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


def test_a_site_key_does_not_depend_on_the_interpreters_quote_choice():
    """FAIL-BEFORE (v0.484.5): the key must be the *same string* on every CPython.

    ``ast.unparse`` picks a different outer quote for an f-string containing a quoted
    literal depending on the patch release — 3.12.3 reuses the single quote (PEP 701),
    3.11 and 3.12.14 switch to a double one. Keying the exemption on the raw unparse
    made it environment-dependent: v0.484.2 passed locally on 3.12.3 and took `main`
    red on the runner's 3.12.14, which is a worse failure than the line number it
    replaced. Both renderings of the one real f-string write must normalise to one key.
    """
    both = [
        '''x = f"{reason}:{result.error or 'unknown'}"''',
        """x = f'{reason}:{result.error or "unknown"}'""",
    ]
    keys = {_write_source(ast.parse(src).body[0].value) for src in both}
    assert len(keys) == 1, keys
    # And the key the real write produces on *this* interpreter is the one _EXEMPT
    # holds — the assertion CI made and this container did not.
    assert keys.pop() == "f{reason}:{result.error or unknown}"


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
