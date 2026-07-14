"""
Folder scanner: turn a folder of Seestar sub-folders into organised targets.

The Seestar app already does the hard part of organising — every time you
image something it drops the frames into their own sub-folder. The scanner
leans on that:

  * Each immediate sub-folder of the scanned root becomes **one target**.
    All FITS files anywhere inside that sub-folder belong to it. A mosaic,
    whose panels all live in a single Seestar folder, therefore comes in as
    one target — exactly what you want, since the stacker stitches the
    panels onto one canvas.
  * Loose FITS files sitting directly in the root (exports, one-offs, files
    that escaped a folder) are collected into a single ``Unsorted`` target
    you can sort out by hand later.

Two phases, kept separate so they're independently testable:

  1. ``scan_and_organize`` — pure file/DB bookkeeping. Walk the tree, create
     (or re-open) one target Project per sub-folder, register every frame.
     Re-running it is idempotent: already-known frames are skipped.
  2. ``run_qc_and_solve`` — the heavy compute. Runs the existing QC metrics
     and ASTAP plate-solving across a target's frames, in a process pool.

Stacking is deliberately *not* part of the scan — the design is "organise +
QC + solve, then stop", so you can review quality and reject bad frames
before committing CPU time to a stack.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

from seestack.core.cache import CacheManager
from seestack.io.ingest import FITS_SUFFIXES, find_fits_files, ingest_files
from seestack.io.library import UNSORTED_TARGET_NAME, Library
from seestack.io.project import Project

log = logging.getLogger(__name__)

# phase, done, total  — emitted by the progress callback throughout a scan.
ProgressFn = Callable[[str, int, int], None]
ShouldStopFn = Callable[[], bool]


@dataclass
class TargetScanResult:
    """What the organise phase did for one target."""

    target_name: str
    safe_name: str
    n_frames_found: int = 0
    n_frames_added: int = 0
    n_skipped_existing: int = 0
    n_errors: int = 0
    # Dedup-skipped frames whose Stage-1 cache was refreshed (a mid-copy sub whose
    # source later completed) — their QC was reset, so the target needs re-QC even
    # though no *new* frame was added.
    n_frames_refreshed: int = 0


@dataclass
class ScanResult:
    """Outcome of a whole ``scan_and_organize`` pass."""

    root: str
    targets: list[TargetScanResult] = field(default_factory=list)

    @property
    def n_targets(self) -> int:
        return len(self.targets)

    @property
    def total_found(self) -> int:
        return sum(t.n_frames_found for t in self.targets)

    @property
    def total_added(self) -> int:
        return sum(t.n_frames_added for t in self.targets)


def scan_and_organize(
    library: Library,
    root: str | Path,
    *,
    copy_to_cache: bool = False,
    progress: ProgressFn | None = None,
) -> ScanResult:
    """
    Walk ``root`` and organise every FITS file into a library target.

    Parameters
    ----------
    library
        The library to populate. Targets are created/re-opened inside it.
    root
        The folder to scan. Its immediate sub-folders each become a target;
        loose FITS files in the root go to the ``Unsorted`` target.
    copy_to_cache
        When True, every frame is copied into its target's Stage-1 cache
        (useful if the source folder is on a NAS). The default is False:
        the scanned folder is normally already on local disk, so we just
        reference the originals in place and skip the (potentially huge)
        duplication.
    progress
        Optional ``progress(phase, done, total)`` callback.

    Re-running a scan is safe — frames already registered (matched by their
    absolute source path) are skipped, so you can scan again after adding
    more nights to the same folders.
    """
    root = Path(root)
    if not root.exists() or not root.is_dir():
        raise NotADirectoryError(f"scan root is not a directory: {root}")

    result = ScanResult(root=str(root))

    # Each immediate sub-directory containing FITS files = one target.
    subdirs = sorted(d for d in root.iterdir() if d.is_dir())
    # Loose FITS directly in the root → the Unsorted catch-all.
    loose = sorted(
        p for p in root.iterdir()
        if p.is_file() and p.suffix.lower() in FITS_SUFFIXES
    )

    units: list[tuple[str, list[Path]]] = []
    for d in subdirs:
        fits = find_fits_files(d, recursive=True)
        if fits:
            units.append((d.name, fits))
    if loose:
        units.append((UNSORTED_TARGET_NAME, loose))

    total = len(units)
    for i, (target_name, files) in enumerate(units):
        if progress is not None:
            progress("Organizing", i, total)
        tsr = _ingest_into_target(library, target_name, files,
                                  copy_to_cache=copy_to_cache)
        result.targets.append(tsr)
    if progress is not None:
        progress("Organizing", total, total)

    return result


def _ingest_into_target(
    library: Library,
    target_name: str,
    files: list[Path],
    *,
    copy_to_cache: bool,
) -> TargetScanResult:
    """Open (or create) the target and ingest ``files`` into its project."""
    entry, proj = library.open_or_create_target(target_name)
    tsr = TargetScanResult(
        target_name=entry.name,
        safe_name=entry.safe_name,
        n_frames_found=len(files),
    )
    try:
        cache = CacheManager(library.target_dir(entry))
        for res in ingest_files(proj, cache, files, copy_to_cache=copy_to_cache):
            # Check ``skipped`` first: a benign skip (e.g. a still-copying sub) is
            # never a failure even if it carries a note, so it can't inflate n_errors.
            if res.skipped:
                tsr.n_skipped_existing += 1
                if res.refreshed:
                    tsr.n_frames_refreshed += 1
            elif res.error is not None:
                tsr.n_errors += 1
            else:
                tsr.n_frames_added += 1
    finally:
        proj.close()
    # Keep the registry's cached counts in step with the project DB.
    library.refresh_target_stats(entry.safe_name)
    return tsr


def run_qc_and_solve(
    project: Project,
    *,
    astap_path: str | Path | None = None,
    max_workers: int | None = None,
    run_qc: bool = True,
    run_solve: bool = True,
    serial: bool = False,
    only_new_qc: bool = False,
    use_solve_hints: bool = True,
    auto_reject_streaks: bool = True,
    progress: ProgressFn | None = None,
    should_stop: ShouldStopFn | None = None,
) -> dict:
    """
    Run QC metrics and ASTAP plate-solving across one target's frames.

    Both phases fan their work out to a ``ProcessPoolExecutor`` (heavy
    numeric / subprocess work needs real parallelism). Pass ``serial=True``
    to run in-process instead — used by tests and tiny projects where the
    pool spin-up isn't worth it.

    DB writes happen on the calling thread (the one that opened ``project``),
    which keeps SQLite access single-threaded per project.

    Returns a small summary dict: ``{'qc_done', 'qc_total', 'solve_done',
    'solve_total'}``.
    """
    from seestack.qc.runner import (
        apply_qc_result_to_db,
        build_qc_arglist,
        compute_for_db_row,
        reconcile_streak_rejections,
    )
    from seestack.solve.runner import (
        apply_solve_result_to_db,
        build_solve_arglist,
        solve_one,
    )

    summary = {"qc_done": 0, "qc_total": 0, "solve_done": 0, "solve_total": 0}

    if run_qc and not _stopped(should_stop):
        qc_args = build_qc_arglist(project, only_new=only_new_qc)
        summary["qc_total"] = len(qc_args)
        for done, result in _map_jobs(
            compute_for_db_row, qc_args,
            serial=serial, max_workers=max_workers,
            phase="QC", progress=progress, should_stop=should_stop,
        ):
            if result is not None:
                try:
                    apply_qc_result_to_db(
                        project, result, auto_reject=auto_reject_streaks)
                except Exception as exc:  # noqa: BLE001
                    log.warning("QC DB write failed: %s", exc)
            summary["qc_done"] = done
        # A stationary bright extended object (edge-on galaxy, elongated nebula)
        # trips the shape-only streak detector on most/all subs, so an unguarded
        # auto-reject would silently discard the whole target. Re-accept the
        # streak rejections when they cover a majority of the target (they can't
        # be transient trails); stacking's per-pixel rejection still cleans any
        # genuine trail. No-op in the normal case (a few real satellite subs).
        if auto_reject_streaks:
            restored = reconcile_streak_rejections(project)
            if restored:
                summary["streak_reaccepted"] = len(restored)

    if run_solve and not _stopped(should_stop):
        solve_args = build_solve_arglist(project, use_hint=use_solve_hints)
        # build_solve_arglist reads astap_path from project meta (usually
        # unset for freshly-scanned targets) — override it if the caller
        # supplied one so the whole scan uses a known-good ASTAP.
        if astap_path is not None:
            solve_args = [
                (fid, path, str(astap_path), *rest)
                for (fid, path, _ap, *rest) in solve_args
            ]
        summary["solve_total"] = len(solve_args)
        for done, result in _map_jobs(
            solve_one, solve_args,
            serial=serial, max_workers=max_workers,
            phase="Solving", progress=progress, should_stop=should_stop,
        ):
            if result is not None:
                try:
                    apply_solve_result_to_db(project, result)
                except Exception as exc:  # noqa: BLE001
                    log.warning("solve DB write failed: %s", exc)
            summary["solve_done"] = done

    return summary


def _stopped(should_stop: ShouldStopFn | None) -> bool:
    return should_stop is not None and should_stop()


def _map_jobs(
    func,
    arg_tuples: list[tuple],
    *,
    serial: bool,
    max_workers: int | None,
    phase: str,
    progress: ProgressFn | None,
    should_stop: ShouldStopFn | None,
):
    """
    Yield ``(done_count, result)`` for each completed job.

    ``result`` is whatever ``func`` returned, or None if that job raised.
    Honours cancellation via ``should_stop`` between completions.
    """
    total = len(arg_tuples)
    if total == 0:
        return

    if serial:
        for i, args in enumerate(arg_tuples, start=1):
            if _stopped(should_stop):
                return
            try:
                value = func(*args)
            except Exception as exc:  # noqa: BLE001
                log.warning("%s job failed: %s", phase, exc)
                value = None
            if progress is not None:
                progress(phase, i, total)
            yield i, value
        return

    with ProcessPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(func, *args): args for args in arg_tuples}
        done = 0
        for fut in as_completed(futures):
            if _stopped(should_stop):
                # Drop everything still queued and bail out promptly.
                ex.shutdown(wait=False, cancel_futures=True)
                return
            try:
                value = fut.result()
            except Exception as exc:  # noqa: BLE001
                log.warning("%s job failed: %s", phase, exc)
                value = None
            done += 1
            if progress is not None:
                progress(phase, done, total)
            yield done, value
