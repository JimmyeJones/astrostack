"""Every job kind the backend submits has a plain-language name on the Jobs page.

The Jobs page (``frontend/src/routes/Jobs.tsx``'s ``KIND_LABEL``) translates the
engine's snake_case job kinds — ``qc_solve``, ``editor_png`` — into words a
Seestar beginner reads, and the "Notify me when done" ping reuses the same name.
An unknown kind falls back to the raw identifier, so a new job type that nobody
added to the map ships *working* but speaking jargon: the editor's Share and Print
jobs read ``editor_share`` / ``editor_print`` on the Jobs page and in the desktop
notification for that reason until v0.505.29.

The two lists live on opposite sides of the language boundary, so this pins them:
every kind passed to ``JobManager.submit`` anywhere under ``webapp/`` — as a
string literal, or through a module-level ``JOB_KIND*`` constant — must be a key
of ``KIND_LABEL``.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JOBS_TSX = ROOT / "frontend" / "src" / "routes" / "Jobs.tsx"


def _module_str_constants(tree: ast.Module) -> dict[str, str]:
    out: dict[str, str] = {}
    for node in tree.body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)):
            out[node.targets[0].id] = node.value.value
    return out


def _submitted_kinds() -> dict[str, str]:
    """``{kind: "file:line"}`` for every ``<x>.submit(<kind>, …)`` under webapp/."""
    found: dict[str, str] = {}
    unresolved: list[str] = []
    for path in sorted((ROOT / "webapp").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        consts = _module_str_constants(tree)
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "submit" and node.args):
                continue
            arg = node.args[0]
            where = f"{path.relative_to(ROOT)}:{node.lineno}"
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                found.setdefault(arg.value, where)
            elif isinstance(arg, ast.Name) and arg.id in consts:
                found.setdefault(consts[arg.id], where)
            else:
                unresolved.append(where)
    # A kind built at run time can't be checked here; make that a loud choice.
    assert not unresolved, f"job kind not a literal or module constant: {unresolved}"
    return found


def _kind_label_keys() -> set[str]:
    src = JOBS_TSX.read_text(encoding="utf-8")
    m = re.search(r"const KIND_LABEL: Record<string, string> = \{(.*?)\n\};", src, re.S)
    assert m, "KIND_LABEL map not found in Jobs.tsx"
    return set(re.findall(r"^\s*([a-z_]+):", m.group(1), re.M))


def test_the_scan_finds_the_job_kinds() -> None:
    # Guard the guard: a scan that silently finds nothing would pass below.
    kinds = _submitted_kinds()
    for kind in ("pipeline", "stack", "editor_png", "video_stack", "editor_share"):
        assert kind in kinds


def test_every_submitted_job_kind_has_a_plain_language_label() -> None:
    labels = _kind_label_keys()
    missing = {k: w for k, w in _submitted_kinds().items() if k not in labels}
    assert not missing, (
        "job kinds with no KIND_LABEL entry in frontend/src/routes/Jobs.tsx "
        f"(the Jobs page and job notifications would show the raw id): {missing}")
