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

# Per-target meta marker recording the solved+accepted frame count of the last
# *auto*-stack attempt. Used to break a crash loop: if a stack repeatedly kills
# the process (e.g. OOM), the container restarts, the watcher re-scans, and
# without this we'd auto-stack the same data forever. We attempt a given frame
# count once; the user can still trigger a manual stack to retry.
AUTO_STACK_ATTEMPT_META_KEY = "web_auto_stack_attempt"


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
                        only_new_qc=True,  # don't re-QC frames already done on re-scans
                        progress=_progress(jm, job),
                        should_stop=job.cancel_requested,
                    )
                finally:
                    proj.close()
                lib.refresh_target_stats(safe)

        # Auto-stack runs as its own pass (not gated on QC/solve being on) and is
        # non-fatal per target. It considers *all* targets — not just the ones
        # touched by this batch — so enabling auto-stack and running a scan picks
        # up existing data too. A target is (re)stacked only when it has new
        # plate-solved accepted frames since its last stack, so repeated scans
        # don't redundantly re-stack unchanged targets.
        if settings.auto_stack:
            stacked: list[str] = []
            skipped: list[str] = []
            stack_errors: dict[str, str] = {}
            for entry in lib.list_targets():
                if job.cancel_requested():
                    break
                safe = entry.safe_name
                attempt_n = _auto_stack_frame_count(lib, safe)
                if attempt_n is None:
                    skipped.append(safe)
                    continue
                # Record the attempt *before* stacking so that if this stack
                # crashes the whole process, the watcher won't re-trigger the
                # identical stack on restart (crash-loop guard).
                _mark_auto_stack_attempt(lib, safe, attempt_n)
                try:
                    _stack_target(settings, jm, job, lib, safe)
                    stacked.append(safe)
                except Exception as exc:  # noqa: BLE001 — one target shouldn't sink the batch
                    log.warning("auto-stack failed for %s: %s", safe, exc)
                    stack_errors[safe] = str(exc)
            summary["auto_stacked"] = stacked
            summary["auto_stack_skipped"] = skipped
            if stack_errors:
                summary["stack_errors"] = stack_errors
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


def _solved_accepted_count(proj: Any) -> int:
    return sum(1 for f in proj.iter_frames(accepted_only=True) if f.wcs_json)


def _auto_stack_frame_count(lib: Library, safe: str) -> int | None:
    """Solved+accepted frame count to stack now, or ``None`` to skip the target.

    Stacks the first time a target has solvable data, and again only when more
    accepted+solved frames exist than the last stack used — so repeated scans
    don't redundantly re-stack unchanged targets. Also skips a target whose
    auto-stack was already attempted at this exact frame count but produced no
    run (crash-loop guard); a manual stack bypasses this.
    """
    proj = lib.open_target(safe)
    try:
        solved_accepted = _solved_accepted_count(proj)
        if solved_accepted == 0:
            return None
        latest = next(iter(proj.iter_stack_runs()), None)  # newest first
        if latest is not None and solved_accepted <= latest.n_frames_used:
            return None
        attempted = proj.get_meta(AUTO_STACK_ATTEMPT_META_KEY)
        if attempted is not None:
            with contextlib.suppress(TypeError, ValueError):
                if int(attempted) >= solved_accepted:
                    return None  # already tried this data; don't loop
        return solved_accepted
    finally:
        proj.close()


def _mark_auto_stack_attempt(lib: Library, safe: str, frame_count: int) -> None:
    proj = lib.open_target(safe)
    try:
        proj.set_meta(AUTO_STACK_ATTEMPT_META_KEY, str(frame_count))
    finally:
        proj.close()


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
        "excluded_frames": result.excluded_frames,
    }
