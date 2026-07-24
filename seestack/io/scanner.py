"""
Folder scanner: turn a folder of Seestar sub-folders into organised targets.

The Seestar app already does the hard part of organising — every time you
image something it drops the frames into their own sub-folder. The scanner
leans on that, and on the Seestar's **folder-naming convention** (see
``_apply_seestar_convention``):

  * ``<Target>_sub/`` holds the raw sub-frames (the lights to stack) and is
    the authoritative frame source; it becomes the target ``<Target>``.
    A mosaic's raw subs live in ``<Target>_mosaic_sub/`` and become the
    **separate** target ``<Target> (mosaic)`` — kept distinct from the
    single-field target because their fields of view / canvases differ.
  * ``<Target>/`` (no suffix) is the Seestar's *own on-device stacked
    output* — a single, often lower-resolution image, **not** raw subs. When
    a ``<Target>_sub/`` sibling exists we skip this output folder so we never
    build a bogus 1-frame "stack" from it. A bare folder with no ``_sub``
    sibling still ingests as a target (older / non-Seestar layouts).
  * ``*_video/`` folders are video captures, not stackable deep-sky subs, and
    are skipped entirely.
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
from collections.abc import Callable, Sequence
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

# Seestar folder-naming convention (see the module docstring). The Seestar
# writes raw subs into "<Target>_sub/" ("<Target>_mosaic_sub/" for a mosaic)
# and its own on-device stacked OUTPUT into the bare "<Target>/". "*_video/"
# folders are video captures. Suffixes are matched case-insensitively because
# the folder casing is not guaranteed across firmware/app versions.
_SUB_SUFFIX = "_sub"
_MOSAIC_SUB_SUFFIX = "_mosaic_sub"
_VIDEO_SUFFIX = "_video"


def _apply_seestar_convention(
    subdirs_with_fits: list[tuple[str, list[Path]]],
) -> list[tuple[str, list[Path]]]:
    """
    Map raw scan folders to ``(target_name, files)`` units, honouring the
    Seestar folder convention so we never ingest the Seestar's own output or
    video folders as if they were raw sub-frames.

    Rules, applied per folder:

    * ``*_video`` → skipped (video capture, not stackable subs).
    * ``<T>_mosaic_sub`` → target ``"<T> (mosaic)"`` (a mosaic's raw subs, kept
      distinct from the single-field target so their differing footprints are
      never co-stacked or auto-merged).
    * ``<T>_sub`` → target ``"<T>"`` (a single field's raw subs).
    * a bare ``<T>`` whose ``<T>_sub`` sibling is also present → skipped (it's
      the Seestar's on-device stacked output, not raw subs).
    * any other bare folder → ingested unchanged (older / non-Seestar layouts
      whose subs live directly in a plainly-named folder).

    Order is preserved. Folder names are compared case-insensitively for the
    suffix tests, but the target name keeps the folder's original casing.
    """
    names_lower = {name.lower() for name, _ in subdirs_with_fits}
    units: list[tuple[str, list[Path]]] = []
    for name, files in subdirs_with_fits:
        low = name.lower()
        if low.endswith(_VIDEO_SUFFIX):
            continue
        if low.endswith(_MOSAIC_SUB_SUFFIX):
            base = name[: -len(_MOSAIC_SUB_SUFFIX)].rstrip()
            units.append((f"{base} (mosaic)" if base else name, files))
            continue
        if low.endswith(_SUB_SUFFIX):
            base = name[: -len(_SUB_SUFFIX)].rstrip()
            units.append((base if base else name, files))
            continue
        # A bare folder: skip it only when its raw-sub sibling is present (then
        # it's the Seestar's own output). Otherwise ingest it as today.
        if (low + _SUB_SUFFIX) in names_lower:
            continue
        units.append((name, files))
    return units


def _looks_like_seestar_container(d: Path) -> bool:
    """True when ``d`` is a *container* level of a Seestar layout — a folder that
    holds no FITS of its own but wraps the real per-target folders one level
    deeper — recognised by at least one child folder named ``*_sub`` (the
    authoritative raw-subs marker, which also covers ``*_mosaic_sub``).

    This is the "I copied the whole Seestar share/SD card into incoming" shape
    (``incoming/MyWorks/{M 31_sub, M 31, …}``). A plainly-nested non-Seestar
    folder — whose children share no convention names (e.g. ``Andromeda/sub/``,
    ``MyProject/night1/``) — returns False so it still ingests as a single
    target, exactly as before.
    """
    try:
        children = [c for c in d.iterdir() if c.is_dir()]
    except OSError:
        return False
    return any(c.name.lower().endswith(_SUB_SUFFIX) for c in children)


def _seestar_output_bases(
    subdirs_with_fits: list[tuple[str, list[Path]]],
) -> dict[str, str]:
    """Map each single-field ``<T>_sub`` target name to the bare ``<T>`` folder
    basename whose already-registered frames (the Seestar's on-device stacked
    output) must be additively rejected from that target on a re-scan.

    This is the *upgrade-path* companion to ``_apply_seestar_convention``: the
    convention stops us ingesting a bare ``<T>/`` output folder going forward,
    but a library first scanned before v0.184.9 already merged that output frame
    into the ``<T>`` target (both fold to the same safe name). See
    ``Project.reject_seestar_output_frames``. Mosaics are skipped here — their
    on-device output naming is device-specific and tracked as a separate bug.
    """
    bases: dict[str, str] = {}
    for name, _ in subdirs_with_fits:
        low = name.lower()
        if low.endswith(_MOSAIC_SUB_SUFFIX):
            continue
        if low.endswith(_SUB_SUFFIX):
            base = name[: -len(_SUB_SUFFIX)].rstrip()
            if base:
                bases[base] = base
    return bases


# A Seestar's own on-device stacked OUTPUT folder holds a single image, so a
# target the pre-``_apply_seestar_convention`` scanner built from one is a
# 1-frame "stack". Allow a tiny margin above 1 (an occasional two-file output)
# while never flagging a real light-frame stack (dozens–thousands of subs).
_MAX_JUNK_OUTPUT_FRAMES = 2


@dataclass(frozen=True)
class JunkTargetVerdict:
    """Why a target looks like Seestar output/video junk, not raw subs."""

    reason: str   # "video" | "on_device_output"
    detail: str   # plain-language, beginner-facing explanation


def classify_seestar_junk_target(
    target_name: str,
    source_paths: Sequence[str | Path],
    n_frames: int,
) -> JunkTargetVerdict | None:
    """
    Decide whether a library target was built from a Seestar *output* or *video*
    folder rather than raw sub-frames — the leftover "junk" targets an old,
    pre-``_apply_seestar_convention`` scan produced before the scanner learned the
    Seestar folder convention (v0.184.9).

    Pure and side-effect-free apart from a **read-only** ``<T>_sub`` sibling check
    on disk — the same signal ``_apply_seestar_convention`` uses to skip an
    on-device output. Returns ``None`` for a normal target. It never deletes
    anything: the caller surfaces the verdict for the user to confirm.

    * ``video`` — the target name (or every frame's source folder) ends with
      ``_video``: a video capture, not stackable deep-sky subs.
    * ``on_device_output`` — a small (≤ ``_MAX_JUNK_OUTPUT_FRAMES``) target whose
      frames all sit in a single **bare** ``<T>/`` folder that has a raw-subs
      ``<T>_sub/`` sibling on disk: the Seestar's own single stacked output, which
      "stacks" to one lower-resolution frame (colour speckle).

    Conservative by design — it only flags a target with positive evidence
    (a ``_video`` name/folder, or a bare output folder whose ``_sub`` sibling is
    actually present), so a real target is never mistaken for junk.
    """
    _VIDEO_DETAIL = (
        "Built from a Seestar “_video” capture folder, not raw sub-frames — "
        "it can't be stacked into a deep image."
    )
    if target_name.strip().lower().endswith(_VIDEO_SUFFIX):
        return JunkTargetVerdict("video", _VIDEO_DETAIL)

    folders = {Path(p).parent for p in source_paths}
    if not folders:
        return None
    folder_names = {f.name.lower() for f in folders}
    if all(n.endswith(_VIDEO_SUFFIX) for n in folder_names):
        return JunkTargetVerdict("video", _VIDEO_DETAIL)

    if n_frames <= _MAX_JUNK_OUTPUT_FRAMES and len(folders) == 1:
        folder = next(iter(folders))
        low = folder.name.lower()
        # A raw-subs folder ("_sub"/"_mosaic_sub") is never junk — only a *bare*
        # output folder is. "_mosaic_sub" ends with "_sub", so one test covers both.
        if not (low.endswith(_SUB_SUFFIX) or low.endswith(_VIDEO_SUFFIX)):
            sibling = folder.parent / f"{folder.name}{_SUB_SUFFIX}"
            try:
                is_output = sibling.is_dir()
            except OSError:
                is_output = False
            if is_output:
                return JunkTargetVerdict(
                    "on_device_output",
                    "Looks like the Seestar's own single stacked image (its "
                    f"“{folder.name}_sub” raw-subs folder is right beside it), not "
                    "raw subs — stacking it just reproduces that one "
                    "lower-resolution frame.",
                )
    return None


def duplicate_sub_target_base_name(
    target_name: str,
    source_paths: Sequence[str | Path],
) -> str | None:
    """Return the base target name (``<T>``) if this target looks like a leftover
    ``<T>_sub``-named **duplicate** that a pre-v0.184.9 scan built, else ``None``.

    Before the scanner learned the Seestar convention it mapped a raw-subs folder
    ``<T>_sub/`` to a target literally named ``<T>_sub``. The convention (v0.184.9)
    now maps that same folder to target ``<T>``, so on an upgraded install a
    re-scan registers those subs under ``<T>`` while the old ``<T>_sub``-named
    target lingers holding the *same* frames — a harmless-but-cluttering duplicate
    (two library tiles for one object, double auto-stack compute). The frames are
    correct raw subs, so this is **not** the ``on_device_output`` junk case; it is
    a de-duplication hint.

    Pure and side-effect-free: it only recognises the *shape* (name ends ``_sub``
    and every frame sits under a single ``*_sub/`` folder). The caller must confirm
    the base target ``<T>`` actually exists and already owns these subs before
    offering removal, so a legitimately-named standalone ``…_sub`` target (or one
    whose subs the base doesn't yet own) is never flagged. Single-field only —
    ``_mosaic_sub`` naming is device-specific and deliberately left to its own bug.
    """
    name = target_name.strip()
    low = name.lower()
    if not low.endswith(_SUB_SUFFIX) or low.endswith(_MOSAIC_SUB_SUFFIX):
        return None
    base = name[: -len(_SUB_SUFFIX)].rstrip()
    if not base:
        return None
    folders = {Path(p).parent for p in source_paths}
    if len(folders) != 1:
        return None
    folder = next(iter(folders))
    if not folder.name.lower().endswith(_SUB_SUFFIX):
        return None
    return base


@dataclass
class TargetScanResult:
    """What the organise phase did for one target."""

    target_name: str
    safe_name: str
    n_frames_found: int = 0
    n_frames_added: int = 0
    n_skipped_existing: int = 0
    n_errors: int = 0
    # Dedup-skipped frames whose content was refreshed (a mid-copy sub whose
    # source later completed, or a reused path overwritten with a different
    # capture) — their QC was reset, so the target needs re-QC even though no
    # *new* frame was added.
    n_frames_refreshed: int = 0
    # DB ids of those refreshed frames, so the caller can invalidate their cached
    # previews (which key on id alone and would keep showing the old image).
    refreshed_frame_ids: list[int] = field(default_factory=list)
    # Frames additively rejected because they are the Seestar's on-device output
    # (a pre-v0.184.9 library merged that output into this target as a fake sub).
    n_output_frames_rejected: int = 0


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

    subdirs_with_fits: list[tuple[str, list[Path]]] = []
    for d in subdirs:
        # Whole-device drop: the Seestar share/SD card copied wholesale keeps a
        # container level (e.g. "MyWorks/") intact, so a subdir may hold no FITS
        # directly but wrap the real "<T>_sub"/"<T>" folders one level deeper.
        # Expand such a container into its children so each real target is kept
        # separate, instead of lumping every object + output + video into ONE
        # giant target named after the container.
        if not find_fits_files(d, recursive=False) and _looks_like_seestar_container(d):
            for child in sorted(c for c in d.iterdir() if c.is_dir()):
                child_fits = find_fits_files(child, recursive=True)
                if child_fits:
                    subdirs_with_fits.append((child.name, child_fits))
            continue
        fits = find_fits_files(d, recursive=True)
        if fits:
            subdirs_with_fits.append((d.name, fits))
    # Fold the Seestar folder convention in (raw "_sub" folders → targets;
    # skip on-device outputs and videos) before turning folders into targets.
    units = _apply_seestar_convention(subdirs_with_fits)
    # Upgrade path: a library first scanned before v0.184.9 may already hold the
    # Seestar's on-device output inside a "<T>" target the raw "<T>_sub" subs now
    # map to — additively reject those output frames so they leave the stack pool.
    output_bases = _seestar_output_bases(subdirs_with_fits)
    if loose:
        units.append((UNSORTED_TARGET_NAME, loose))

    total = len(units)
    for i, (target_name, files) in enumerate(units):
        if progress is not None:
            progress("Organizing", i, total)
        tsr = _ingest_into_target(library, target_name, files,
                                  copy_to_cache=copy_to_cache,
                                  reject_output_base=output_bases.get(target_name))
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
    reject_output_base: str | None = None,
) -> TargetScanResult:
    """Open (or create) the target and ingest ``files`` into its project.

    ``reject_output_base``, when given, is the bare ``<T>/`` output-folder
    basename for a Seestar single-field target: after ingest, any already-
    registered frame that lives in that folder (the Seestar's own on-device
    output, mis-ingested by a pre-v0.184.9 scan) is additively rejected so it
    leaves the stack/reference pool.
    """
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
                    if res.refreshed_frame_id is not None:
                        tsr.refreshed_frame_ids.append(res.refreshed_frame_id)
            elif res.error is not None:
                tsr.n_errors += 1
            else:
                tsr.n_frames_added += 1
        if reject_output_base:
            rejected = proj.reject_seestar_output_frames(reject_output_base)
            tsr.n_output_frames_rejected = len(rejected)
            if rejected:
                log.info(
                    "Rejected %d Seestar on-device output frame(s) from target "
                    "%r (source folder %r) — they are excluded from stacking; "
                    "re-accept them if you really want them stacked.",
                    len(rejected), entry.name, reject_output_base,
                )
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
