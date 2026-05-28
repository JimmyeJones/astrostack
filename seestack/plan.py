"""
Batch plan: pre-configure ingest → QC → plate solve → stack and run as one
unattended job.

A plan is a JSON file (``*.seestackplan``) that describes:

  - the **project** to operate on (existing dir, or create if missing)
  - whether to **ingest** a folder of raws (optional)
  - whether to run **QC**, **plate solve**, **stack** (each optional)
  - all the per-step options

Typical use: set up a plan during the day, hit "Run now" before bed; come
back to a finished stack. Or save the plan and reuse it for similar nights.

Two entry points:

  ``run_plan(plan, progress=..., cancel=...)``
      Synchronous runner. The GUI invokes this from a worker thread; the
      headless CLI invokes it directly.

  ``Plan.load(path) / Plan.save(path)``
      JSON round-trip. The format is human-readable on purpose so users can
      diff plans and tweak by hand.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

from seestack.stack.stacker import StackOptions

log = logging.getLogger(__name__)


@dataclass
class IngestStep:
    enabled: bool = True
    source_dir: str = ""
    copy_to_cache: bool = True


@dataclass
class QCStep:
    enabled: bool = True
    auto_reject_streaks: bool = True


@dataclass
class SolveStep:
    enabled: bool = True
    astap_path: str | None = None  # if not set, project meta / auto-find is used


@dataclass
class StackStep:
    enabled: bool = True
    options: StackOptions = field(default_factory=StackOptions)


@dataclass
class Plan:
    """A complete batch description. Save/load via JSON."""

    project_dir: str
    project_name: str = ""        # used only if creating a new project
    ingest: IngestStep = field(default_factory=IngestStep)
    qc: QCStep = field(default_factory=QCStep)
    solve: SolveStep = field(default_factory=SolveStep)
    stack: StackStep = field(default_factory=StackStep)
    schema_version: int = 1

    # ---- I/O ---------------------------------------------------------------

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(asdict(self), indent=2))

    @classmethod
    def load(cls, path: str | Path) -> "Plan":
        raw = json.loads(Path(path).read_text())
        return cls._from_dict(raw)

    @classmethod
    def _from_dict(cls, data: dict[str, Any]) -> "Plan":
        # Be lenient about unknown keys (forward compatibility).
        def filt(target_cls, d):
            keys = {f.name for f in fields(target_cls)}
            return {k: v for k, v in d.items() if k in keys}

        ingest = IngestStep(**filt(IngestStep, data.get("ingest", {})))
        qc = QCStep(**filt(QCStep, data.get("qc", {})))
        solve = SolveStep(**filt(SolveStep, data.get("solve", {})))
        stack_raw = data.get("stack", {})
        stack_opts_raw = stack_raw.get("options", {}) if isinstance(stack_raw, dict) else {}
        stack_opts = StackOptions(**filt(StackOptions, stack_opts_raw))
        stack = StackStep(
            enabled=stack_raw.get("enabled", True) if isinstance(stack_raw, dict) else True,
            options=stack_opts,
        )
        return cls(
            project_dir=data["project_dir"],
            project_name=data.get("project_name", ""),
            ingest=ingest,
            qc=qc,
            solve=solve,
            stack=stack,
            schema_version=int(data.get("schema_version", 1)),
        )


# ---- Runner -----------------------------------------------------------------


@dataclass
class PlanProgress:
    """Snapshot pushed to the progress callback."""

    step: str          # 'ingest' | 'qc' | 'solve' | 'stack' | 'done'
    step_index: int
    n_steps: int
    detail: str = ""
    sub_done: int = 0
    sub_total: int = 0


@dataclass
class PlanResult:
    """Summary returned at the end."""

    steps_run: list[str]
    stack_result: Any = None        # StackResult if a stack happened
    errors: list[str] = field(default_factory=list)
    cancelled: bool = False


ProgressFn = Callable[[PlanProgress], None]
CancelFn = Callable[[], bool]


def run_plan(
    plan: Plan,
    *,
    progress: ProgressFn | None = None,
    cancel: CancelFn | None = None,
) -> PlanResult:
    """
    Execute the steps in a plan. Synchronous. Returns a summary.

    Each enabled step runs in order. If a step fails, we record the error
    and continue (later steps may still succeed; e.g. QC failures don't
    block a stack).
    """
    progress = progress or (lambda *a: None)
    cancel = cancel or (lambda: False)

    project_dir = Path(plan.project_dir)
    enabled_steps = [s for s in ("ingest", "qc", "solve", "stack")
                     if getattr(plan, s).enabled]
    result = PlanResult(steps_run=[])
    n_steps = len(enabled_steps)

    # Step 0: open / create project.
    project = _open_or_create_project(project_dir, plan.project_name)
    try:
        for i, step_name in enumerate(enabled_steps):
            if cancel():
                result.cancelled = True
                break
            progress(PlanProgress(step=step_name, step_index=i, n_steps=n_steps))
            try:
                if step_name == "ingest":
                    _run_ingest(project, plan.ingest, progress, i, n_steps, cancel)
                elif step_name == "qc":
                    _run_qc(project, plan.qc, progress, i, n_steps, cancel)
                elif step_name == "solve":
                    _run_solve(project, plan.solve, progress, i, n_steps, cancel)
                elif step_name == "stack":
                    result.stack_result = _run_stack_step(
                        project, plan.stack, progress, i, n_steps, cancel,
                    )
                result.steps_run.append(step_name)
            except Exception as exc:  # noqa: BLE001
                log.exception("Plan step %s failed", step_name)
                result.errors.append(f"{step_name}: {type(exc).__name__}: {exc}")
        progress(PlanProgress(step="done", step_index=n_steps, n_steps=n_steps))
    finally:
        project.close()
    return result


def _open_or_create_project(project_dir: Path, project_name: str):
    from seestack.io.project import Project

    if (project_dir / "project.sqlite").exists():
        return Project.open(project_dir)
    name = project_name or project_dir.name
    return Project.create(project_dir, name=name)


def _run_ingest(project, step: IngestStep, progress: ProgressFn,
                step_index: int, n_steps: int, cancel: CancelFn) -> None:
    from seestack.core.cache import CacheManager
    from seestack.io.ingest import find_fits_files, ingest_files

    if not step.source_dir:
        return
    src = Path(step.source_dir)
    files = find_fits_files(src)
    total = len(files)
    if total == 0:
        return
    cache = CacheManager(project.project_dir)
    cache.ensure_dirs()
    for i, r in enumerate(ingest_files(project, cache, files, copy_to_cache=step.copy_to_cache)):
        if cancel():
            return
        progress(PlanProgress(
            step="ingest", step_index=step_index, n_steps=n_steps,
            detail=str(r.source_path.name), sub_done=i + 1, sub_total=total,
        ))


def _run_qc(project, step: QCStep, progress: ProgressFn,
            step_index: int, n_steps: int, cancel: CancelFn) -> None:
    from seestack.core.jobs import run_serial
    from seestack.qc.runner import (
        apply_qc_result_to_db, build_qc_arglist, compute_for_db_row,
    )
    from concurrent.futures import ProcessPoolExecutor, as_completed

    args = build_qc_arglist(project)
    total = len(args)
    if total == 0:
        return
    progress(PlanProgress(step="qc", step_index=step_index, n_steps=n_steps,
                          sub_done=0, sub_total=total))
    # Use ProcessPoolExecutor directly (same as JobRunner internals).
    done = 0
    with ProcessPoolExecutor() as ex:
        futures = {ex.submit(compute_for_db_row, *a): a for a in args}
        for fut in as_completed(futures):
            if cancel():
                for other in futures:
                    other.cancel()
                return
            try:
                qc_result = fut.result()
                apply_qc_result_to_db(project, qc_result, auto_reject=step.auto_reject_streaks)
            except Exception as exc:  # noqa: BLE001
                log.warning("QC error: %s", exc)
            done += 1
            progress(PlanProgress(
                step="qc", step_index=step_index, n_steps=n_steps,
                sub_done=done, sub_total=total,
            ))


def _run_solve(project, step: SolveStep, progress: ProgressFn,
               step_index: int, n_steps: int, cancel: CancelFn) -> None:
    from concurrent.futures import ProcessPoolExecutor, as_completed

    from seestack.solve.runner import apply_solve_result_to_db, build_solve_arglist, solve_one

    if step.astap_path:
        project.set_meta("astap_path", step.astap_path)
    args = build_solve_arglist(project)
    total = len(args)
    if total == 0:
        return
    progress(PlanProgress(step="solve", step_index=step_index, n_steps=n_steps,
                          sub_done=0, sub_total=total))
    done = 0
    with ProcessPoolExecutor() as ex:
        futures = {ex.submit(solve_one, *a): a for a in args}
        for fut in as_completed(futures):
            if cancel():
                for other in futures:
                    other.cancel()
                return
            try:
                solve_result = fut.result()
                apply_solve_result_to_db(project, solve_result)
            except Exception as exc:  # noqa: BLE001
                log.warning("Solve error: %s", exc)
            done += 1
            progress(PlanProgress(
                step="solve", step_index=step_index, n_steps=n_steps,
                sub_done=done, sub_total=total,
            ))


def _run_stack_step(project, step: StackStep, progress: ProgressFn,
                    step_index: int, n_steps: int, cancel: CancelFn):
    from seestack.stack.stacker import run_stack

    def inner_progress(phase: str, done: int, total: int) -> None:
        progress(PlanProgress(
            step="stack", step_index=step_index, n_steps=n_steps,
            detail=phase, sub_done=done, sub_total=total,
        ))

    return run_stack(project, step.options, progress=inner_progress, cancel=cancel)
