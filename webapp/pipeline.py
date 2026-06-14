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


def _load_full_rgb_wcs(fits_path: str) -> tuple[Any, Any]:
    """Read a stack FITS to float32 (H,W,3) + an optional celestial WCS."""
    import numpy as np
    from astropy.io import fits as _fits

    with _fits.open(fits_path) as hdul:
        data = np.asarray(hdul[0].data, dtype=np.float32)
        header = hdul[0].header
    if data.ndim == 3:
        rgb = np.transpose(data, (1, 2, 0))
        if rgb.shape[2] == 1:
            rgb = np.repeat(rgb, 3, axis=2)
        elif rgb.shape[2] > 3:
            rgb = rgb[..., :3]
    else:
        rgb = np.stack([data, data, data], axis=-1)
    wcs = None
    try:
        from astropy.wcs import WCS
        w = WCS(header).celestial
        if w.has_celestial:
            wcs = w
    except Exception:  # noqa: BLE001
        wcs = None
    return rgb, wcs


def _apply_editor_to_run(lib: Library, safe: str, run_id: int, recipe_dict: dict,
                         *, output_name: str | None, tiff_mode: str,
                         progress) -> dict[str, Any]:
    """Apply an editor recipe to one run's full-res FITS and record a NEW run.
    Non-destructive: the source run is untouched."""
    import json as _json
    from datetime import datetime, timezone

    import numpy as np

    from seestack.edit.pipeline import apply_recipe
    from seestack.edit.recipe import recipe_from_dict
    from seestack.edit.registry import EditContext
    from seestack.io.project import Project, StackRunRow
    from seestack.stack.output import write_stack_outputs

    entry = lib.find_target(safe)
    if entry is None:
        raise FileNotFoundError(f"no target '{safe}'")
    proj = Project.open(lib.target_dir(entry))
    try:
        run = next((r for r in proj.iter_stack_runs() if r.id == run_id), None)
        if run is None or not run.fits_path or not Path(run.fits_path).exists():
            raise FileNotFoundError(f"run {run_id} has no FITS")
        base = output_name or f"{run.output_basename}_edit"

        rgb, wcs = _load_full_rgb_wcs(run.fits_path)
        recipe = recipe_from_dict(recipe_dict)
        n = len(recipe.ops)
        done = 0

        # Per-op progress: wrap apply by stepping through ops via a callback.
        from seestack.edit.registry import get_op
        ctx = EditContext(wcs=wcs, is_proxy=False, proxy_scale=1.0)
        ctx.stage = "linear"
        out = np.asarray(rgb, dtype=np.float32)
        from seestack.edit.registry import as_rgb
        out = as_rgb(out)
        stretched = False
        for op in [o for o in recipe.ops if o.enabled]:
            spec = get_op(op.id)
            if spec is None:
                continue
            try:
                out = as_rgb(spec.apply(out, op.params, ctx))
                if spec.is_stretch:
                    stretched = True
                    ctx.stage = "nonlinear"
            except Exception as exc:  # noqa: BLE001
                log.warning("editor export op %s failed: %s", op.id, exc)
            done += 1
            progress("export", done, max(n, 1))
        if not stretched:
            from seestack.render.thumbnail import asinh_stretch
            out = asinh_stretch(out)

        coverage = np.ones(out.shape[:2], dtype=np.float32)
        paths = write_stack_outputs(
            project_dir=proj.project_dir, rgb=out, coverage=coverage,
            wcs_text=None, out_basename=base, tiff_mode=tiff_mode,
        )
        new_id = proj.add_stack_run(StackRunRow(
            id=None,
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            output_basename=base,
            fits_path=str(paths["fits"]), tiff_path=str(paths["tiff"]),
            preview_path=str(paths["preview"]),
            n_frames_used=run.n_frames_used,
            canvas_h=out.shape[0], canvas_w=out.shape[1],
            coverage_min=1, coverage_max=1,
            options_json=_json.dumps({"editor_recipe": recipe.to_dict(),
                                      "derived_from": run_id}),
            notes="edited",
        ))
    finally:
        proj.close()
    lib.refresh_target_stats(safe)
    return {"safe": safe, "run_id": new_id, "output_basename": base,
            "output_dir": str(Path(paths["fits"]).parent)}


def submit_editor_export(settings: Settings, jm: JobManager, safe: str, run_id: int,
                         recipe_dict: dict, *, output_name: str | None = None,
                         tiff_mode: str = "linear") -> Job:
    def body(job: Job) -> dict[str, Any]:
        lib = Library.open_or_create(settings.resolved_library_root)
        try:
            return _apply_editor_to_run(
                lib, safe, run_id, recipe_dict,
                output_name=output_name, tiff_mode=tiff_mode,
                progress=_progress(jm, job),
            )
        finally:
            lib.close()

    return jm.submit("editor_export", body, target=safe)


def submit_editor_batch(settings: Settings, jm: JobManager, items: list[dict],
                        recipe_dict: dict, *, output_name: str | None = None,
                        tiff_mode: str = "linear") -> Job:
    def body(job: Job) -> dict[str, Any]:
        lib = Library.open_or_create(settings.resolved_library_root)
        exported: list[dict] = []
        errors: dict[str, str] = {}
        total = len(items)
        try:
            for i, item in enumerate(items, start=1):
                if job.cancel_requested():
                    break
                safe = str(item.get("safe"))
                rid = int(item.get("run_id"))
                job.set_progress("batch", i, total, f"{safe} run {rid}")
                jm.maybe_flush(job)
                try:
                    res = _apply_editor_to_run(
                        lib, safe, rid, recipe_dict,
                        output_name=output_name, tiff_mode=tiff_mode,
                        progress=lambda *a: None,  # per-item detail not surfaced
                    )
                    exported.append(res)
                except Exception as exc:  # noqa: BLE001 — one item shouldn't sink the batch
                    log.warning("batch edit failed for %s/%s: %s", safe, rid, exc)
                    errors[f"{safe}:{rid}"] = str(exc)
        finally:
            lib.close()
        return {"exported": exported, "errors": errors}

    return jm.submit("editor_batch", body)


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
