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
from typing import TYPE_CHECKING, Any

from seestack.io.library import Library
from seestack.io.scanner import run_qc_and_solve, scan_and_organize
from webapp import __version__ as APP_VERSION
from webapp.config import Settings
from webapp.jobs import Job, JobManager
from webapp.schemas import STACK_DEFAULTS_META_KEY, coerce_stack_options

if TYPE_CHECKING:
    from seestack.io.project import StackRunRow

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
            graded: dict[str, int] = {}
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
                        use_solve_hints=settings.astap_use_solve_hints,
                        auto_reject_streaks=not settings.keep_streaked_frames,
                        progress=_progress(jm, job),
                        should_stop=job.cancel_requested,
                    )
                    if settings.auto_grade_frames and settings.auto_qc:
                        n = _auto_grade_target(proj, settings)
                        if n:
                            graded[safe] = n
                finally:
                    proj.close()
                lib.refresh_target_stats(safe)
            if graded:
                summary["auto_graded"] = graded

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
            auto_edited = 0
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
                    res = _stack_target(settings, jm, job, lib, safe)
                    stacked.append(safe)
                    # Optionally finish the fresh master into a picture (the same
                    # Auto-recipe chain the one-click Process/Reprocess use), so
                    # the fully-unattended path returns a finished image, not a
                    # flat linear master. Best-effort: never sinks the batch.
                    run_id = res.get("run_id")
                    if (settings.auto_edit_on_autostack and run_id is not None
                            and not job.cancel_requested()):
                        if _auto_edit_process_run(lib, safe, run_id) is not None:
                            auto_edited += 1
                except Exception as exc:  # noqa: BLE001 — one target shouldn't sink the batch
                    log.warning("auto-stack failed for %s: %s", safe, exc)
                    stack_errors[safe] = str(exc)
            summary["auto_stacked"] = stacked
            summary["auto_stack_skipped"] = skipped
            if auto_edited:
                summary["auto_edited"] = auto_edited
            if stack_errors:
                summary["stack_errors"] = stack_errors
        return summary
    finally:
        lib.close()


def submit_build_master(
    settings: Settings, jm: JobManager, *,
    kind: str, source_dir: str, name: str | None = None,
    method: str = "median", sigma: float = 3.0,
) -> Job:
    """Build a master dark/flat/bias from a folder of raw FITS frames and
    register it in the library-level calibration store."""
    def body(job: Job) -> dict[str, Any]:
        from webapp import calibration
        from seestack.calibrate.masters import build_master

        paths = calibration.find_fits_in_dir(source_dir)
        if not paths:
            raise FileNotFoundError(f"No FITS files found in {source_dir}")
        job.set_progress("loading", 0, len(paths), f"{len(paths)} frames")
        array, meta = build_master(
            paths, kind=kind, method=method, sigma=sigma,
            progress=_progress(jm, job),
        )
        entry = calibration.register_master(
            settings.resolved_library_root, name=name or "", array=array, meta=meta,
        )
        return {
            "id": entry["id"], "name": entry["name"], "kind": entry["kind"],
            "n_frames": entry["n_frames"], "width_px": entry["width_px"],
            "height_px": entry["height_px"],
        }

    return jm.submit("build_master", body)


def _auto_grade_target(proj: Any, settings: Settings) -> int:
    """Run auto-grade over a target's accepted frames and apply the rejections
    (the opt-in ``auto_grade_frames`` pipeline hook). Returns frames rejected.
    Best-effort: grading must never sink a QC/ingest pass."""
    from seestack.qc.grading import apply_grade_report, grade_frames

    try:
        frames = list(proj.iter_frames(accepted_only=True))
        report = grade_frames(frames, sensitivity=settings.auto_grade_sensitivity)
        changed = apply_grade_report(proj, report)
        if changed:
            log.info("Auto-grade rejected %d frame(s): %s", len(changed),
                     ", ".join(f"{r.name} ({r.primary_metric})"
                               for r in report.recommendations if r.frame_id in set(changed)))
        return len(changed)
    except Exception as exc:  # noqa: BLE001 — advisory automation, never fatal
        log.warning("Auto-grade failed: %s", exc)
        return 0


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
                    use_solve_hints=settings.astap_use_solve_hints,
                    auto_reject_streaks=not settings.keep_streaked_frames,
                    progress=_progress(jm, job),
                    should_stop=job.cancel_requested,
                )
                summary = dict(summary)
                if settings.auto_grade_frames:
                    n = _auto_grade_target(proj, settings)
                    if n:
                        summary["auto_graded"] = n
            finally:
                proj.close()
            lib.refresh_target_stats(safe)
            return summary
        finally:
            lib.close()

    return jm.submit("qc_solve", body, target=safe)


def submit_process_target(settings: Settings, jm: JobManager, safe: str) -> Job:
    """One-click "process this target": QC + plate-solve every frame, auto-grade
    (when enabled), then stack — the whole ``drop files → good image`` middle in
    one job, so the user reaches a finished stack without configuring the global
    auto toggles or hand-filling the Stack form.

    Reuses the same primitives as the auto pipeline (``run_qc_and_solve`` →
    ``_auto_grade_target`` → ``_stack_target``) but scoped to one target and run
    on demand regardless of the ``auto_*`` settings. The stack uses the target's
    saved defaults (falling back to the global defaults), exactly like auto-stack,
    and is **non-destructive** — a new ``stack_runs`` row alongside any existing
    output. The stack step is skipped (with a reason) when nothing is
    plate-solved yet or the job was cancelled during QC/solve.
    """
    def body(job: Job) -> dict[str, Any]:
        lib = Library.open_or_create(settings.resolved_library_root)
        try:
            proj = lib.open_target(safe)
            try:
                summary = dict(run_qc_and_solve(
                    proj,
                    astap_path=settings.astap_path,
                    max_workers=settings.cpu_workers,
                    run_qc=True,
                    run_solve=True,
                    use_solve_hints=settings.astap_use_solve_hints,
                    auto_reject_streaks=not settings.keep_streaked_frames,
                    progress=_progress(jm, job),
                    should_stop=job.cancel_requested,
                ))
                if settings.auto_grade_frames:
                    n = _auto_grade_target(proj, settings)
                    if n:
                        summary["auto_graded"] = n
                solved_accepted = _solved_accepted_count(proj)
            finally:
                proj.close()
            lib.refresh_target_stats(safe)

            summary["solved_accepted"] = solved_accepted
            if job.cancel_requested():
                summary["stacked"] = False
                summary["stack_skipped_reason"] = "cancelled"
                return summary
            if solved_accepted == 0:
                # Nothing to combine yet (e.g. ASTAP not set up, so no frame has a
                # WCS). Leave a clear reason instead of failing the whole job.
                summary["stacked"] = False
                summary["stack_skipped_reason"] = "no_solved_frames"
                return summary
            summary["stack"] = _stack_target(settings, jm, job, lib, safe)
            summary["stacked"] = True
            run_id = summary["stack"].get("run_id")
            if run_id is not None and not job.cancel_requested():
                # Chain a one-click auto-edit onto the fresh master so the result
                # is a finished *picture*, not a flat linear stack: save the Auto
                # recipe as the run's editor recipe (so it opens edited) and
                # re-render its History/Target thumbnail through that recipe.
                # Best-effort — a failure here never fails the whole Process job;
                # the linear master is already recorded.
                n_ops = _auto_edit_process_run(lib, safe, run_id)
                if n_ops is not None:
                    summary["auto_edited"] = n_ops
            return summary
        finally:
            lib.close()

    return jm.submit("process_target", body, target=safe)


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


def _stack_options_from_run_json(options_json: str | None) -> dict[str, Any] | None:
    """Parse a stack run's ``options_json`` back into a plain ``StackOptions``
    dict, or ``None`` when the run isn't a genuine stack.

    Editor-export and channel-combine runs are also recorded in ``stack_runs``
    but store a different shape (``{"editor_recipe": …}`` / ``{"channel_combine":
    …}``), so they're rejected — we only want to reuse the settings that produced
    an actual integration. Empty/garbage/unknown-only JSON also yields ``None``
    so the caller falls back to the target's saved defaults.
    """
    if not options_json:
        return None
    try:
        data = json.loads(options_json)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    if not isinstance(data, dict) or "editor_recipe" in data or "channel_combine" in data:
        return None
    import dataclasses

    from seestack.stack.stacker import StackOptions

    valid = {f.name for f in dataclasses.fields(StackOptions)}
    clean = {k: v for k, v in data.items() if k in valid}
    return clean or None


def _last_stack_options_for_target(lib: Library, safe: str) -> dict[str, Any] | None:
    """The most recent *genuine* stack run's options for a target, or ``None``.

    Walks the target's runs newest-first and returns the first that parses as a
    real ``StackOptions`` dict (skipping editor/combine runs), so a reprocess
    reuses exactly the settings that made the target's current image.
    """
    proj = lib.open_target(safe)
    try:
        for run in proj.iter_stack_runs():  # newest first
            opts = _stack_options_from_run_json(run.options_json)
            if opts is not None:
                return opts
    finally:
        proj.close()
    return None


def _newest_genuine_stack_run(proj) -> StackRunRow | None:
    """The target's most recent *genuine* stack run (the first, newest-first, whose
    options parse as a real ``StackOptions`` — skipping editor-export/combine runs),
    or ``None`` when it has none. Shared by the reprocess reuse/stale logic and the
    stale-target count so they agree on what "the current image's stack" is.
    """
    for run in proj.iter_stack_runs():  # newest first
        if _stack_options_from_run_json(run.options_json) is not None:
            return run
    return None


def _last_stack_version_for_target(lib: Library, safe: str) -> str | None:
    """The ``engine_version`` of the target's most recent *genuine* stack run
    (skipping editor/combine runs), or ``None`` when it has no genuine stack or
    that run predates version tracking. Used by the "reprocess only stale targets"
    filter to skip targets already stacked on the current build.
    """
    proj = lib.open_target(safe)
    try:
        run = _newest_genuine_stack_run(proj)
        return run.engine_version if run is not None else None
    finally:
        proj.close()


def reprocess_status(lib: Library) -> dict[str, Any]:
    """Count targets whose current image is stale relative to the running build.

    A target is **outdated** when its most recent *genuine* stack was produced by
    a different app version than the one now running (including a run that predates
    version tracking, ``engine_version`` ``None`` — it was made by some older
    build). A target with no genuine stack yet is neither outdated nor up to date:
    there's no existing image to refresh, so it's excluded from both counts (it
    isn't "stale", it just hasn't been stacked). This drives the proactive
    "N targets were made with an older version — reprocess" nudge, so it counts
    only images a reprocess would actually change.

    Returns ``{current_version, outdated, up_to_date, total_targets}``.
    """
    outdated = 0
    up_to_date = 0
    total = 0
    for entry in lib.list_targets():
        total += 1
        proj = lib.open_target(entry.safe_name)
        try:
            run = _newest_genuine_stack_run(proj)
        finally:
            proj.close()
        if run is None:
            continue  # never stacked — not an out-of-date existing image
        if run.engine_version == APP_VERSION:
            up_to_date += 1
        else:
            outdated += 1
    return {
        "current_version": APP_VERSION,
        "outdated": outdated,
        "up_to_date": up_to_date,
        "total_targets": total,
    }


def _refresh_target(settings: Settings, jm: JobManager, job: Job,
                    lib: Library, safe: str) -> None:
    """Deep-rescan one target before it's restacked: re-run QC + plate-solve over
    *all* its existing library frames (not just new ones) and re-apply auto-grade,
    so a "reprocess everything" after an in-place upgrade also picks up QC / solve /
    grading improvements — not only the stacker's.

    ``run_qc_and_solve`` is called with ``only_new_qc=False`` so the metrics are
    re-derived for every frame with the current engine; ``apply_qc_result_to_db``
    still honours a user's manual accept/reject (``user_override``), so re-QC never
    clobbers a hand-made decision. Solving is best-effort — with no ASTAP available
    it simply solves nothing. Auto-grade is applied only when the user has grading
    enabled (``auto_grade_frames``), matching the ordinary ingest pipeline.

    Best-effort and self-contained: a refresh failure is logged and swallowed so it
    can never sink the target's restack (the whole point of reprocess is the new
    stack; a flaky re-QC must not cost the user that)."""
    try:
        proj = lib.open_target(safe)
        try:
            run_qc_and_solve(
                proj,
                astap_path=settings.astap_path,
                max_workers=settings.cpu_workers,
                run_qc=True,
                run_solve=True,
                only_new_qc=False,  # re-derive QC for *every* frame with the new engine
                use_solve_hints=settings.astap_use_solve_hints,
                auto_reject_streaks=not settings.keep_streaked_frames,
                progress=_progress(jm, job),
                should_stop=job.cancel_requested,
            )
            if settings.auto_grade_frames:
                _auto_grade_target(proj, settings)
        finally:
            proj.close()
        lib.refresh_target_stats(safe)
    except Exception as exc:  # noqa: BLE001 — refresh is advisory, never fatal
        log.warning("reprocess-all deep-rescan failed for %s: %s", safe, exc)


def submit_reprocess_all(settings: Settings, jm: JobManager, *,
                         stale_only: bool = False,
                         deep_rescan: bool = False,
                         auto_edit: bool = False) -> Job:
    """Restack *every* target with the current engine — the owner's one-click
    "reprocess everything after an upgrade" maintenance action.

    Each target is restacked reusing the settings that produced its current image
    (its last genuine stack run's ``options_json``; falling back to its saved
    stack defaults / global auto-defaults when it has none). The per-target stacks
    run **serially** inside this single job — the stack hot path is memory-bounded
    on purpose (OOM history), so exactly one runs at a time — and each is recorded
    as a *new* ``stack_runs`` row **alongside** the existing output: nothing is
    ever deleted or overwritten, so a worse restack can't lose a good result.

    Cancellable between targets (and within each target's stack). A target that
    fails to stack is isolated: its error is recorded and the batch carries on.

    ``stale_only`` skips targets whose most recent *genuine* stack was already
    produced by the current app version — so after an upgrade the user reprocesses
    only the images that would actually change, not the whole library. A target
    with no genuine stack (or one that predates version tracking) is treated as
    stale and reprocessed.

    ``deep_rescan`` additionally re-runs QC / plate-solve / auto-grade over each
    target's existing frames *before* its restack (see :func:`_refresh_target`), so
    the reprocess also benefits from QC/solve/grading improvements, not just the
    stacker. Off by default (the plain restack is the common case and a full rescan
    is much slower); the refresh is best-effort per target and honours manual frame
    decisions. It runs only for targets that are going to be restacked, so a
    ``stale_only`` skip skips the rescan too.

    Each reprocessed run is written to a **fresh, version-tagged basename** (see
    :func:`_reprocess_output_basename`) rather than the target's existing
    ``master`` — otherwise the reused ``options_json`` (which carries the old run's
    ``output_name="master"``) would make the stacker *archive* the current
    ``master.fits`` to an orphaned timestamped file and write the new pixels in its
    place, so the old run's DB row would silently start serving the *new* image.
    A distinct basename keeps the old output on disk and reachable, making the
    "nothing is deleted or overwritten — compare them in History" promise true.

    ``auto_edit`` chains the one-click Auto recipe onto every restacked run (see
    :func:`_auto_edit_process_run`), so a reprocess after an upgrade yields finished
    *pictures* across the whole library — not flat linear masters the user must
    hand-edit one by one. Off by default: it seeds an editor recipe on many runs at
    once, so it's an explicit opt-in. It only touches each *new* run's own recipe and
    preview thumbnail (never an existing run's saved edit), is best-effort per run (a
    failure never fails the batch), and is fully reversible in the editor (Reset/undo).
    """
    def body(job: Job) -> dict[str, Any]:
        lib = Library.open_or_create(settings.resolved_library_root)
        try:
            targets = list(lib.list_targets())
            total = len(targets)
            job.set_progress("reprocess", 0, total, f"0/{total} targets")
            jm.maybe_flush(job)
            stacked = 0
            skipped = 0
            rescanned = 0
            auto_edited = 0
            failed: list[dict[str, str]] = []
            cancelled = False
            for i, entry in enumerate(targets):
                if job.cancel_requested():
                    cancelled = True
                    break
                safe = entry.safe_name
                name = entry.name or safe
                if stale_only and _last_stack_version_for_target(lib, safe) == APP_VERSION:
                    # Up to date on the current build — nothing would change, skip it.
                    skipped += 1
                    job.set_progress("reprocess", i + 1, total, f"{i + 1}/{total} targets")
                    jm.maybe_flush(job)
                    continue
                # Persistent label; the inner run_stack progress updates
                # phase/done/total per frame but leaves detail untouched.
                job.detail = f"Target {i + 1}/{total}: {name}"
                jm.maybe_flush(job)
                if deep_rescan and not job.cancel_requested():
                    # Re-derive QC/solve/grade with the current engine first, so the
                    # restack below stacks the freshly-graded frame set.
                    _refresh_target(settings, jm, job, lib, safe)
                    rescanned += 1
                    if job.cancel_requested():
                        cancelled = True
                        break
                reuse = _last_stack_options_for_target(lib, safe)
                # Write to a fresh, version-tagged basename so the reprocessed run
                # lands *alongside* the target's existing output instead of
                # archiving/orphaning its ``master`` (the reused options carry the
                # old run's output_name). This is what makes the batch genuinely
                # non-destructive.
                proj = lib.open_target(safe)
                try:
                    existing = {r.output_basename for r in proj.iter_stack_runs()
                                if r.output_basename}
                finally:
                    proj.close()
                fresh_name = _reprocess_output_basename(existing, APP_VERSION)
                try:
                    res = _stack_target(settings, jm, job, lib, safe,
                                        options=reuse, output_name=fresh_name)
                except Exception as exc:  # noqa: BLE001 — isolate one bad target
                    log.exception("reprocess-all: target %s failed", safe)
                    failed.append({"target": safe, "error": f"{type(exc).__name__}: {exc}"})
                else:
                    if res.get("cancelled"):
                        cancelled = True
                        break
                    stacked += 1
                    run_id = res.get("run_id")
                    if auto_edit and run_id is not None and not job.cancel_requested():
                        # Chain the one-click Auto recipe onto the fresh master so the
                        # reprocess yields a finished *picture*, not a flat linear
                        # stack — same helper the single-target Process action uses.
                        # Best-effort: a failure here never fails the batch.
                        if _auto_edit_process_run(lib, safe, run_id) is not None:
                            auto_edited += 1
                job.set_progress("reprocess", i + 1, total, f"{i + 1}/{total} targets")
                jm.maybe_flush(job)
            return {
                "total": total,
                "stacked": stacked,
                "skipped": skipped,
                "rescanned": rescanned,
                "auto_edited": auto_edited,
                "failed": failed,
                "cancelled": cancelled,
            }
        finally:
            lib.close()

    return jm.submit("reprocess_all", body)


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


def _deconv_psf_meta(recipe) -> dict[str, Any]:  # noqa: ANN001
    """If an editor recipe includes enabled ``detail.deconvolve`` op(s), return a
    ``DECONPSF`` provenance card recording the Gaussian PSF σ (px) actually used,
    so a sharpened export self-documents whether and how hard it was deconvolved.

    Records a single float when one deconvolution ran, or a comma-joined string
    when several ran (in application order). Empty dict when none did.
    """
    sigmas = [round(float(op.params.get("psf_sigma", 1.5)), 3)
              for op in recipe.ops
              if op.enabled and op.id == "detail.deconvolve"]
    if not sigmas:
        return {}
    value: Any = sigmas[0] if len(sigmas) == 1 else ", ".join(str(s) for s in sigmas)
    return {"DECONPSF": (value, "Richardson-Lucy PSF sigma (px)")}


def _recipe_history(recipe) -> list[str]:  # noqa: ANN001
    """Human-readable FITS HISTORY lines, one per enabled editor op (in order),
    e.g. ``AstroStack: detail.denoise(method=wavelet, strength=0.5)``. This is the
    canonical FITS provenance mechanism, so an edited export self-documents its
    full processing chain in Siril/PixInsight/APP — not just the op count."""
    lines: list[str] = []
    for op in recipe.ops:
        if not op.enabled:
            continue
        parts = []
        for k, v in op.params.items():
            if isinstance(v, float):
                v = round(v, 4)
            # skip long/structured params (e.g. curve control points) — keep the
            # line human-readable and within the 72-char FITS card limit.
            text = f"{k}={v}"
            if len(text) <= 24:
                parts.append(text)
        args = ", ".join(parts)
        lines.append(f"AstroStack: {op.id}({args})"[:72])
    return lines


def _carry_provenance(fits_path: str) -> dict[str, Any]:
    """Read provenance cards from a source stack FITS so a derived export can
    keep describing the underlying integration (target, frame count, exposure).

    Best-effort: any header that can't be read simply yields no carry-over cards.
    Only the integration-describing keys are carried; ``STACKER``/``STACKMTD`` are
    intentionally left for the caller to overwrite with the derivation method.
    """
    from astropy.io import fits as _fits

    carry: dict[str, Any] = {}
    try:
        with _fits.open(fits_path) as hdul:
            header = hdul[0].header
            for key in ("OBJECT", "NFRAMES", "EXPOSURE", "EXPTOTAL",
                        "COLORTYP", "DATE-OBS", "DATE-END"):
                if key in header:
                    carry[key] = (header[key], header.comments[key])
    except Exception:  # noqa: BLE001 — provenance is non-critical
        pass
    return carry


def _render_recipe_fullres(fits_path: str, recipe_dict: dict, progress,
                           errors: list[str] | None = None) -> tuple[Any, Any]:
    """Apply an editor recipe to a full-res FITS. Returns ``(out_rgb, recipe)``
    where ``out_rgb`` is the display-stretched 0..1 result. A default asinh
    stretch is applied if the recipe has no stretch op (so the result is never
    raw-linear/black).

    An op that raises on the full-res data is dropped (best-effort, like the live
    preview) but its failure message is appended to ``errors`` (when provided) —
    same format as ``apply_recipe`` — so the caller can surface it instead of the
    export silently changing the look with no notice to the user.

    When ``fits_path`` is itself a tone-mapped display-space export (re-editing an
    edited run), the default fallback stretch is suppressed so an empty/no-stretch
    recipe doesn't double-stretch the already-stretched image — matching the live
    preview's ``ctx.already_display`` behaviour."""
    import numpy as np

    from seestack.edit.recipe import recipe_from_dict
    from seestack.edit.registry import EditContext, as_rgb, get_op

    from seestack.edit.proxy import load_coverage
    from seestack.stack.output import fits_is_display_space

    display_space = fits_is_display_space(fits_path)
    rgb, wcs = _load_full_rgb_wcs(fits_path)
    recipe = recipe_from_dict(recipe_dict)
    n = max(len([o for o in recipe.ops if o.enabled]), 1)
    # Load the run's per-pixel coverage map (if any) so the "Coverage leveling" op
    # can equalise the sky across mosaic panels; None for a single-field image.
    coverage = load_coverage(fits_path)
    ctx = EditContext(wcs=wcs, is_proxy=False, proxy_scale=1.0, coverage=coverage)
    ctx.stage = "linear"
    out = as_rgb(np.asarray(rgb, dtype=np.float32))
    stretched = False
    done = 0
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
            msg = f"{spec.label}: {type(exc).__name__}: {exc}"
            log.warning("editor op %s failed on export: %s", op.id, msg)
            if errors is not None:
                errors.append(msg)
        done += 1
        progress("render", done, n)
    if not stretched and not display_space:
        from seestack.render.thumbnail import asinh_stretch
        out = asinh_stretch(out)
    return out, recipe


def _apply_editor_to_run(lib: Library, safe: str, run_id: int, recipe_dict: dict,
                         *, output_name: str | None, tiff_mode: str,
                         progress) -> dict[str, Any]:
    """Apply an editor recipe to one run's full-res FITS and record a NEW run.
    Non-destructive: the source run is untouched."""
    import json as _json
    from datetime import datetime, timezone

    import numpy as np

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

        op_errors: list[str] = []
        out, recipe = _render_recipe_fullres(run.fits_path, recipe_dict, progress,
                                             errors=op_errors)

        n_ops = len([o for o in recipe.ops if o.enabled])
        edit_meta = _carry_provenance(run.fits_path)
        edit_meta["STACKMTD"] = (f"editor recipe ({n_ops} ops)",
                                 "how this image was produced")
        edit_meta["EDITFROM"] = (int(run_id), "source stack run id")
        edit_meta.update(_deconv_psf_meta(recipe))
        history = _recipe_history(recipe)
        if history:
            edit_meta["HISTORY"] = history

        coverage = np.ones(out.shape[:2], dtype=np.float32)
        # `out` is the recipe's display-space result (a stretch was applied), so
        # the TIFF/preview must be written as-is, not re-stretched/linear-rescaled.
        paths = write_stack_outputs(
            project_dir=proj.project_dir, rgb=out, coverage=coverage,
            wcs_text=None, out_basename=base, tiff_mode=tiff_mode,
            header_meta=edit_meta, already_display=True,
        )
        # Re-exporting under an existing basename archives the prior export's
        # files; repoint its history row at them so it keeps serving its own
        # image rather than this new one (done before adding the new run).
        if paths.get("archived"):
            proj.repoint_stack_runs(paths["archived"])
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
                                      "derived_from": run_id,
                                      # The export is the recipe's tone-mapped
                                      # result, not a linear stack — so re-opening
                                      # it in the editor must not default-stretch
                                      # it again (matches the FITS SSDISPLY card).
                                      "display_space": True}),
            notes="edited",
            engine_version=APP_VERSION,
        ))
    finally:
        proj.close()
    lib.refresh_target_stats(safe)
    return {"safe": safe, "run_id": new_id, "output_basename": base,
            "output_dir": str(Path(paths["fits"]).parent),
            "op_errors": op_errors}


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


def submit_editor_png(settings: Settings, jm: JobManager, safe: str, run_id: int,
                      recipe_dict: dict) -> Job:
    """Render an editor recipe at full resolution and write a downloadable PNG
    (no new stack run created). The PNG path is returned in the job result."""
    def body(job: Job) -> dict[str, Any]:
        from datetime import datetime, timezone

        from seestack.io.project import Project
        from seestack.stack.output import write_full_res_png

        lib = Library.open_or_create(settings.resolved_library_root)
        try:
            entry = lib.find_target(safe)
            if entry is None:
                raise FileNotFoundError(f"no target '{safe}'")
            proj = Project.open(lib.target_dir(entry))
            try:
                run = next((r for r in proj.iter_stack_runs() if r.id == run_id), None)
                if run is None or not run.fits_path or not Path(run.fits_path).exists():
                    raise FileNotFoundError(f"run {run_id} has no FITS")
                op_errors: list[str] = []
                out, _recipe = _render_recipe_fullres(
                    run.fits_path, recipe_dict, _progress(jm, job),
                    errors=op_errors)
                from seestack.stack.output import safe_basename
                ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
                png = (Path(proj.project_dir) / "output"
                       / f"{safe_basename(run.output_basename)}_edit_{ts}.png")
                write_full_res_png(png, out)
            finally:
                proj.close()
            return {"safe": safe, "run_id": run_id,
                    "png_path": str(png), "filename": png.name,
                    "op_errors": op_errors}
        finally:
            lib.close()

    return jm.submit("editor_png", body, target=safe)


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


def _channel_combine(
    lib: Library, target_safe: str, items: list[dict], *,
    output_name: str | None, weights: dict[str, float] | None, progress,
) -> dict[str, Any]:
    """Combine several mono stacks into one LRGB/RGB run, recorded under
    ``target_safe``. Each item: ``{safe, run_id, channel}`` (channel ∈ L/R/G/B)."""
    import json as _json
    from datetime import datetime, timezone

    import numpy as np

    from seestack.io.project import Project, StackRunRow
    from seestack.stack.channel_combine import combine_channels
    from seestack.stack.output import write_stack_outputs

    entry = lib.find_target(target_safe)
    if entry is None:
        raise FileNotFoundError(f"no target '{target_safe}'")

    channels: dict[str, np.ndarray] = {}
    wcs_text: str | None = None
    total = len(items)
    for i, item in enumerate(items, start=1):
        ch = str(item.get("channel", "")).upper()
        if ch not in ("L", "R", "G", "B"):
            raise ValueError(f"bad channel {item.get('channel')!r} (expected L/R/G/B)")
        if ch in channels:
            raise ValueError(f"channel {ch} assigned more than once")
        safe = str(item.get("safe"))
        rid = int(item.get("run_id"))
        progress("loading", i, total, f"{ch} ← {safe} run {rid}")
        src = lib.find_target(safe)
        if src is None:
            raise FileNotFoundError(f"no target '{safe}'")
        proj = Project.open(lib.target_dir(src))
        try:
            run = next((r for r in proj.iter_stack_runs() if r.id == rid), None)
            if run is None or not run.fits_path or not Path(run.fits_path).exists():
                raise FileNotFoundError(f"run {rid} in {safe} has no FITS")
            rgb, wcs = _load_full_rgb_wcs(run.fits_path)
        finally:
            proj.close()
        # Mono stacks have identical channels; luminance == that single channel.
        channels[ch] = (0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2])
        if wcs_text is None and wcs is not None:
            from seestack.io.wcs_io import wcs_to_text
            wcs_text = wcs_to_text(wcs)

    progress("combining", total, total)
    out = combine_channels(channels, weights=weights)

    dst = Project.open(lib.target_dir(entry))
    try:
        base = output_name or "lrgb"
        coverage = np.isfinite(out).all(axis=2).astype(np.float32)
        combo = "".join(c for c in ("L", "R", "G", "B") if c in channels)
        combine_meta = {
            "NCOMBINE": (len(items), "source stacks combined"),
            "STACKMTD": (f"channel-combine ({combo})", "how this image was produced"),
        }
        paths = write_stack_outputs(
            project_dir=dst.project_dir, rgb=out, coverage=coverage,
            wcs_text=wcs_text, out_basename=base, tiff_mode="linear",
            header_meta=combine_meta,
        )
        # Re-combining under an existing basename archives the prior output;
        # repoint its history row so it keeps serving its own image.
        if paths.get("archived"):
            dst.repoint_stack_runs(paths["archived"])
        new_id = dst.add_stack_run(StackRunRow(
            id=None,
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            output_basename=base,
            fits_path=str(paths["fits"]), tiff_path=str(paths["tiff"]),
            preview_path=str(paths["preview"]),
            n_frames_used=len(items),
            canvas_h=out.shape[0], canvas_w=out.shape[1],
            coverage_min=1, coverage_max=1,
            options_json=_json.dumps({"channel_combine": items, "weights": weights or {}}),
            notes="channel combine",
            engine_version=APP_VERSION,
        ))
    finally:
        dst.close()
    lib.refresh_target_stats(target_safe)
    return {"safe": target_safe, "run_id": new_id, "output_basename": base,
            "channels": list(channels.keys())}


def submit_channel_combine(
    settings: Settings, jm: JobManager, target_safe: str, items: list[dict],
    *, output_name: str | None = None, weights: dict[str, float] | None = None,
) -> Job:
    def body(job: Job) -> dict[str, Any]:
        lib = Library.open_or_create(settings.resolved_library_root)
        try:
            return _channel_combine(
                lib, target_safe, items,
                output_name=output_name, weights=weights,
                progress=lambda *a: (job.set_progress(*a), jm.maybe_flush(job))[0],
            )
        finally:
            lib.close()

    return jm.submit("channel_combine", body, target=target_safe)


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


def _reprocess_output_basename(existing: set[str], version: str) -> str:
    """A fresh, non-colliding output basename for a reprocessed run.

    Base is ``master_v<version>`` (self-documenting: the build that produced it),
    sanitised to safe filename chars. If a run already carries that basename (e.g.
    the user reprocessed twice on the same version), a ``_2``/``_3``/… suffix is
    appended so the new run never archives/overwrites the earlier one — the
    reprocess feature's non-destructive guarantee holds even in that edge case.

    ``existing`` is the set of the target's current ``output_basename`` values.
    """
    from seestack.stack.output import _sanitize_basename

    base = _sanitize_basename(f"master_v{version}")
    if base not in existing:
        return base
    n = 2
    while f"{base}_{n}" in existing:
        n += 1
    return f"{base}_{n}"


def _stack_target(
    settings: Settings,
    jm: JobManager,
    job: Job,
    lib: Library,
    safe: str,
    *,
    options: dict[str, Any] | None = None,
    output_name: str | None = None,
) -> dict[str, Any]:
    """Run a stack for one target and record it. Returns a small summary.

    ``output_name``, when given, overrides the output basename *after* the option
    merge — used by reprocess-all to force a fresh, non-colliding name so a
    restack doesn't archive/overwrite the target's existing output.
    """
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
        if output_name is not None:
            opts_dict["output_name"] = output_name
        if opts_dict.get("max_workers") is None and settings.cpu_workers:
            opts_dict["max_workers"] = settings.cpu_workers
        opts = coerce_stack_options(opts_dict)

        result = run_stack(
            proj, opts,
            progress=lambda phase, done, total: (
                job.set_progress(f"stack:{phase}", done, total), jm.maybe_flush(job)
            )[0],
            cancel=job.cancel_requested,
            memory_budget_gb=settings.max_stack_memory_gb,
            app_version=APP_VERSION,
        )
    finally:
        proj.close()
    lib.refresh_target_stats(safe)

    return {
        "output_dir": str(result.output_dir),
        "run_id": result.run_id,
        "n_frames_used": result.n_frames_used,
        "canvas_shape": list(result.canvas_shape),
        "cancelled": result.cancelled,
        "errors": result.errors,
        "excluded_frames": result.excluded_frames,
    }


def _auto_edit_process_run(lib: Library, safe: str, run_id: int) -> int | None:
    """Chain the one-click Auto recipe onto a freshly-produced stack run so the
    "Process target" result is a finished picture: persist the Auto recipe as the
    run's editor recipe (the editor then opens on the edited image) and re-render
    the run's preview thumbnail through it (History/Target show the picture, not a
    flat linear master).

    Additive and reversible — only runs the user explicitly asked to *Process* get
    this; the recipe is a normal saved editor recipe (Reset/undo restores linear)
    and only this run's own preview PNG is rewritten. Returns the number of enabled
    ops applied, or ``None`` when it was skipped (no such run / no FITS) or failed
    (best-effort — never fails the Process job)."""
    from webapp.routers.editor import (
        AUTO_EDIT_NOTE_PREFIX,
        RECIPE_META_PREFIX,
        build_auto_analysis_for_run,
        build_auto_recipe_for_run,
        render_run_display_array,
    )
    from seestack.edit import presets as presets_mod
    from seestack.io.project import Project
    from seestack.stack.output import _write_preview_png

    try:
        entry = lib.find_target(safe)
        if entry is None:
            return None
        proj = Project.open(lib.target_dir(entry))
        try:
            run = next((r for r in proj.iter_stack_runs() if r.id == run_id), None)
            if run is None or not run.fits_path or not Path(run.fits_path).exists():
                return None
            median_fwhm = proj.median_fwhm()
            recipe = build_auto_recipe_for_run(
                proj.project_dir, run, median_fwhm)
            proj.set_meta(f"{RECIPE_META_PREFIX}{run_id}", recipe.to_json())
            # Stamp a plain-language "what Auto did (and why)" note so the History
            # Info panel can explain this silently-applied edit — the same reasoning
            # the interactive editor shows when a user clicks Auto themselves.
            try:
                analysis = build_auto_analysis_for_run(
                    proj.project_dir, run, median_fwhm)
                note = presets_mod.auto_edit_summary(recipe, analysis)
            except Exception:  # noqa: BLE001 — the note is a nicety, never fatal
                note = presets_mod.auto_edit_summary(recipe, None)
            if note:
                proj.set_meta(f"{AUTO_EDIT_NOTE_PREFIX}{run_id}", note)
            if run.preview_path:
                out = render_run_display_array(proj.project_dir, run, recipe)
                _write_preview_png(Path(run.preview_path), out, already_display=True)
        finally:
            proj.close()
        return len([o for o in recipe.ops if o.enabled])
    except Exception as exc:  # noqa: BLE001 — auto-edit is a non-critical nicety
        log.warning("Process-target auto-edit skipped for run %s: %s", run_id, exc)
        return None
