"""Job bodies: thin adapters that drive the seestack engine and report progress
into a :class:`~webapp.jobs.Job`.

These run on the single job-worker thread. Each opens the Library / Project,
calls the existing engine functions (``scan_and_organize``,
``run_qc_and_solve``, ``run_stack``), and maps their progress callbacks onto the
job record so the SSE stream and the jobs DB stay current.
"""

from __future__ import annotations

import contextlib
import json
import logging
from pathlib import Path
from typing import Any

from seestack.io.library import Library
from seestack.io.scanner import run_qc_and_solve, scan_and_organize
from webapp.config import Settings
from webapp.jobs import Job, JobManager
from webapp.schemas import STACK_DEFAULTS_META_KEY, coerce_stack_options

log = logging.getLogger(__name__)


def _progress(jm: JobManager, job: Job):
    """Engine ``(phase, done, total)`` callback bound to a job."""
    def cb(phase: str, done: int, total: int) -> None:
        job.set_progress(phase, done, total)
        jm.maybe_flush(job)
    return cb


def submit_pipeline(settings: Settings, jm: JobManager, *, root: str | None = None) -> Job:
    def body(job: Job) -> dict[str, Any]:
        return _pipeline_body(settings, jm, job, root=root)
    return jm.submit("pipeline", body)


def _pipeline_body(
    settings: Settings, jm: JobManager, job: Job, *, root: str | None
) -> dict[str, Any]:
    lib = Library.open_or_create(settings.resolved_library_root)
    scan_root = Path(root) if root else settings.resolved_incoming_dir
    summary: dict[str, Any] = {"root": str(scan_root), "targets": []}
    try:
        if settings.auto_ingest:
            job.set_progress("scan", 0, 0, f"Scanning {scan_root}")
            scan = scan_and_organize(
                lib, scan_root,
                copy_to_cache=settings.copy_to_cache,
                progress=_progress(jm, job),
            )
            touched_names = [t.safe_name for t in scan.targets if t.n_frames_added > 0]
            summary["scanned"] = scan.total_added
        else:
            touched_names = [t.safe_name for t in lib.list_targets()]
        summary["targets"] = touched_names

        if settings.auto_qc or settings.auto_solve:
            for safe in touched_names:
                if job.cancel_requested():
                    break
                proj = lib.open_target(safe)
                try:
                    run_qc_and_solve(
                        proj,
                        astap_path=settings.astap_path,
                        max_workers=settings.cpu_workers,
                        run_qc=settings.auto_qc,
                        run_solve=settings.auto_solve,
                        progress=_progress(jm, job),
                        should_stop=job.cancel_requested,
                    )
                finally:
                    proj.close()
                lib.refresh_target_stats(safe)
                if settings.auto_stack and not job.cancel_requested():
                    _stack_target(settings, jm, job, lib, safe)
        return summary
    finally:
        lib.close()


def submit_qc_solve(settings: Settings, jm: JobManager, safe: str) -> Job:
    def body(job: Job) -> dict[str, Any]:
        lib = Library.open_or_create(settings.resolved_library_root)
        try:
            proj = lib.open_target(safe)
            try:
                summary = run_qc_and_solve(
                    proj,
                    astap_path=settings.astap_path,
                    max_workers=settings.cpu_workers,
                    run_qc=settings.auto_qc or True,
                    run_solve=settings.auto_solve or True,
                    progress=_progress(jm, job),
                    should_stop=job.cancel_requested,
                )
            finally:
                proj.close()
            lib.refresh_target_stats(safe)
            return dict(summary)
        finally:
            lib.close()

    return jm.submit("qc_solve", body, target=safe)


def submit_stack(
    settings: Settings, jm: JobManager, safe: str, options: dict[str, Any]
) -> Job:
    def body(job: Job) -> dict[str, Any]:
        lib = Library.open_or_create(settings.resolved_library_root)
        try:
            return _stack_target(settings, jm, job, lib, safe, options=options)
        finally:
            lib.close()

    return jm.submit("stack", body, target=safe)


def _stack_target(
    settings: Settings,
    jm: JobManager,
    job: Job,
    lib: Library,
    safe: str,
    *,
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run a stack for one target and record it. Returns a small summary."""
    from seestack.stack.stacker import run_stack

    # Option precedence:
    #   global settings.default_stack_options
    #     → per-target "Save as defaults" (used by auto-stack)
    #       → explicit options passed for this run (manual stack from the form)
    opts_dict = dict(settings.default_stack_options)
    proj = lib.open_target(safe)
    try:
        if options is None:
            raw = proj.get_meta(STACK_DEFAULTS_META_KEY)
            if raw:
                with contextlib.suppress(json.JSONDecodeError):
                    opts_dict.update(json.loads(raw))
        else:
            opts_dict.update(options)
        if opts_dict.get("max_workers") is None and settings.cpu_workers:
            opts_dict["max_workers"] = settings.cpu_workers
        opts = coerce_stack_options(opts_dict)

        result = run_stack(
            proj, opts,
            progress=lambda phase, done, total: (
                job.set_progress(f"stack:{phase}", done, total), jm.maybe_flush(job)
            )[0],
            cancel=job.cancel_requested,
        )
    finally:
        proj.close()
    lib.refresh_target_stats(safe)

    return {
        "output_dir": str(result.output_dir),
        "n_frames_used": result.n_frames_used,
        "canvas_shape": list(result.canvas_shape),
        "cancelled": result.cancelled,
        "errors": result.errors,
    }
