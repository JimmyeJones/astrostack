"""Storage accounting + housekeeping.

The library can grow to hundreds of GB: per-target the bulk is the two-stage
cache (``cache/stage1_raw`` + ``cache/stage2_aligned``) plus thumbnails, all of
which are *regenerable* from the source frames, and the ``output/`` stacks. This
router reports where the space went and lets the user reclaim it safely:

* ``GET  /api/storage`` — per-target breakdown + totals + free disk.
* ``POST /api/targets/{safe}/cache/clear`` — drop a regenerable cache stage.
* ``POST /api/targets/{safe}/stack-runs/prune`` — delete old stack runs
  (keep the N newest, or an explicit list), removing their output files too.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Collection
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from seestack.core.cache import CacheManager
from seestack.edit.proxy import proxy_dir
from seestack.io.project import StackRunRow
from seestack.render.thumbnail import thumbs_dir
from webapp import deps, picturesarchive
from webapp.storage_estimate import estimate_nightly_bytes

router = APIRouter(tags=["storage"])

# Cache stages the user can clear. "stage1"/"stage2" map to CacheManager;
# "thumbs" is the per-frame thumbnail cache; "proxies" is the editor's
# downsampled preview cache (rebuilt from the stack FITS on the next open);
# "all" clears every regenerable bit.
_CLEARABLE = ("stage1", "stage2", "thumbs", "proxies", "all")


def _dir_bytes(path: Path) -> int:
    """Total size of files under ``path`` (recursive). 0 if missing.

    Best-effort: a file that vanished/permission-denied is skipped, and an
    unreadable *subdirectory* encountered mid-walk (e.g. a NAS mount that went
    permission-denied) returns the partial total rather than raising — the
    storage page must never 500 on one flaky mount.
    """
    if not path.exists():
        return 0
    total = 0
    try:
        for p in path.rglob("*"):
            try:
                if p.is_file():
                    total += p.stat().st_size
            except OSError:
                continue
    except OSError:
        pass
    return total


def run_artifact_paths(fits_path: str | None,
                       tiff_path: str | None = None,
                       preview_path: str | None = None) -> list[Path]:
    """Every file one run's output set occupies on disk.

    The three paths a ``stack_runs`` row records, plus every sibling resolved
    from the FITS *basename* rather than from a column (see
    :data:`seestack.stack.output.RUN_ARTEFACT_SUFFIXES`): the two coverage maps,
    the preview, the progress and deepening reels, the share PNG.

    One definition, because two callers need exactly this answer from opposite
    directions — :func:`delete_run_artifacts` to know what to unlink, and
    :func:`purge_stack_run` to know what another row still serves. Built with
    plain :class:`~pathlib.Path` and no ``resolve()``: these are the strings the
    DB holds, two rows naming one file hold the *same* string, and a delete must
    not start following symlinks.
    """
    from seestack.stack.output import RUN_ARTEFACT_SUFFIXES

    paths: list[Path] = [Path(p) for p in (fits_path, tiff_path, preview_path)
                         if p]
    if fits_path:
        fp = Path(fits_path)
        stem = fp.name[:-len(fp.suffix)] if fp.suffix else fp.name
        paths.extend(fp.with_name(f"{stem}{sfx}")
                     for sfx in RUN_ARTEFACT_SUFFIXES.values())
    return paths


def delete_run_artifacts(run: StackRunRow, *,
                         keep_paths: Collection[Path] = ()) -> None:
    """Unlink a stack run's output files. Best-effort.

    Not only the three paths recorded on the ``stack_runs`` row
    (FITS/TIFF/preview): a finished stack also writes a per-pixel
    ``_coverage.fits`` and, when asked for, a ``_progress`` reel, both resolved
    from the FITS *basename* rather than a column (see
    :data:`seestack.stack.output.RUN_ARTEFACT_SUFFIXES`). Unlinking only the
    recorded three left those behind for good — the coverage map alone is ~8 MB
    on a 1080×1920 stack and far more on a mosaic, and reclaiming space is the
    entire point of deleting a run.

    ``keep_paths`` is every file a **surviving** row still names, and nothing in
    it is unlinked. A row does not always own the files it points at: before the
    v0.81.7–0.81.8 overwrite guard a re-stack wrote the canonical ``master.*``
    straight over the previous run's output, and
    :meth:`seestack.io.project.Project.repoint_stack_runs` only runs at re-stack
    time, so the rows written before the guard still name a file a *newer* run
    wrote (observer issue #1069 counts 56 of them, on 15 shared paths). Deleting
    one of those rows unlinked the live run's whole set — master, TIFF, preview,
    both coverage maps and the reels — losing a picture the owner never asked to
    lose, on the button whose whole purpose is routine housekeeping.

    Go through :func:`purge_stack_run`, which supplies this set from the DB; the
    empty default exists only for a caller that has no project to ask, and there
    is none.
    """
    skip = set(keep_paths)
    for p in run_artifact_paths(getattr(run, "fits_path", None),
                                getattr(run, "tiff_path", None),
                                getattr(run, "preview_path", None)):
        if p in skip:
            continue
        try:
            p.unlink(missing_ok=True)
        except OSError:
            pass


def purge_stack_run(proj: Any, run: StackRunRow) -> None:
    """Delete a stack run and everything the app hung off its id.

    One definition, because a run is more than its history row: its output file
    set, the editor's cached preview proxy (up to ~27 MB of ``.npy``), and up to
    six ``project_meta`` annotations (:mod:`webapp.run_meta`). The single-run
    delete endpoint used to clear some of that and the "Prune old stacks" path
    none of it, so pruning — the *disk-space* feature — left the proxy behind for
    every run it removed.
    """
    from seestack.edit.proxy import clear_proxy
    from webapp.run_meta import delete_run_meta

    # Which files do the *other* rows still name? A row does not always own what
    # it points at (see :func:`delete_run_artifacts`), so this is asked before a
    # byte is unlinked. A three-column read rather than ``iter_stack_runs``'
    # ``SELECT *``, because "Prune old stacks" walks every run it removes through
    # here. The run's own paths are excluded, or nothing would ever be deleted —
    # and because the set is re-read per run, deleting the *last* row of a shared
    # group still frees the whole file set, which is what keeps the guard from
    # leaking disk on the one button that exists to reclaim it.
    keep: set[Path] = set()
    for paths in proj.iter_stack_run_output_paths(exclude_run_id=run.id):
        keep.update(run_artifact_paths(*paths))
    delete_run_artifacts(run, keep_paths=keep)
    if run.id is None:
        return
    proj.delete_stack_run(run.id)
    clear_proxy(Path(proj.project_dir), run.id)
    delete_run_meta(proj, run.id)


class TargetStorage(BaseModel):
    safe: str
    name: str
    total_bytes: int
    output_bytes: int
    cache_bytes: int        # stage1 + stage2 + thumbs (all regenerable)
    stage1_bytes: int
    stage2_bytes: int
    thumbs_bytes: int
    # The editor's downsampled preview proxies. Additive with a default so an
    # older frontend (which doesn't read it) and an older backend (which doesn't
    # send it) both keep working.
    proxies_bytes: int = 0
    n_stack_runs: int


class StorageResponse(BaseModel):
    targets: list[TargetStorage]
    total_bytes: int
    output_bytes: int
    cache_bytes: int
    #: The prepared full-size picture archive ("Full-size versions" on the
    #: Gallery), which is a season of pictures at print size and easily
    #: gigabytes. It lives outside the library, so without this line it is disk
    #: the page cannot account for — the one question this page exists to
    #: answer. ``0`` when none has been built, which is the default and every
    #: install that never presses the button.
    exports_bytes: int = 0
    #: The owner's raw subs in ``incoming/``, which on this install are the only
    #: copy that exists (Owner Facts; AGENTS.md §10) — counted from the ``frames``
    #: rows, never by walking or stat-ing the folder itself. ``incoming_bytes`` is
    #: the sum of the sizes we know; ``incoming_unsized_frames`` counts rows
    #: ingested before ``source_size_bytes`` existed, which is why the page says
    #: "at least". All additive and 0 on a fresh install.
    incoming_frames: int = 0
    incoming_bytes: int = 0
    incoming_unsized_frames: int = 0
    #: Whether ``copy_to_cache`` is on. Off (the owner's setting) means the app
    #: holds no copy of a sub at all; on means the copies are working files that
    #: "Clear caches" deletes — a distinction the page has to draw, because
    #: neither is a backup.
    incoming_copied: bool = False
    disk: dict


@router.get("/api/storage", response_model=StorageResponse)
def get_storage(request: Request) -> StorageResponse:
    from seestack.io.project import Project

    settings = deps.get_settings(request)
    lib = deps.open_library(request)
    rows: list[TargetStorage] = []
    # Capture cadence across the whole library, for the "nights left" estimate.
    night_counts: dict[str, int] = {}
    total_frames = 0
    # …and how much raw data sits in incoming/, summed from the frame rows. The
    # trailing separator matters: without it a sibling like `incoming2/` matches.
    incoming_prefix = os.path.join(str(settings.resolved_incoming_dir), "")
    incoming_frames = incoming_bytes = incoming_unsized = 0
    try:
        for t in lib.list_targets():
            tdir = lib.target_dir(t)
            try:
                cm = CacheManager(tdir)
                stage1 = cm.stats("stage1").bytes_total
                stage2 = cm.stats("stage2").bytes_total
            except OSError:
                # An unreadable/vanished target cache dir (a NAS mount that went
                # permission-denied, a dataset unmounted mid-scan) must not 500
                # the whole storage page — the same per-target resilience
                # gallery.py / sky.py / stats.py already apply for a broken
                # project DB. Report 0 for the parts we can't read and keep
                # listing every other target. (_dir_bytes below is already
                # best-effort and never raises.)
                stage1 = stage2 = 0
            thumbs = _dir_bytes(thumbs_dir(tdir))
            proxies = _dir_bytes(proxy_dir(tdir))
            output = _dir_bytes(tdir / "output")
            total = _dir_bytes(tdir)
            n_runs = 0
            proj = None
            try:
                proj = Project.open(tdir)
                n_runs = sum(1 for _ in proj.iter_stack_runs())
                for night, n in proj.frame_night_counts().items():
                    night_counts[night] = night_counts.get(night, 0) + n
                    total_frames += n
                n_inc, b_inc, u_inc = proj.source_frames_under(incoming_prefix)
                incoming_frames += n_inc
                incoming_bytes += b_inc
                incoming_unsized += u_inc
            except Exception:  # noqa: BLE001
                pass
            finally:
                if proj is not None:
                    proj.close()
            rows.append(TargetStorage(
                safe=t.safe_name, name=t.name,
                total_bytes=total, output_bytes=output,
                cache_bytes=stage1 + stage2 + thumbs + proxies,
                stage1_bytes=stage1, stage2_bytes=stage2, thumbs_bytes=thumbs,
                proxies_bytes=proxies,
                n_stack_runs=n_runs,
            ))
    finally:
        lib.close()

    rows.sort(key=lambda r: r.total_bytes, reverse=True)

    library_bytes = sum(r.total_bytes for r in rows)
    disk: dict = {}
    try:
        usage = shutil.disk_usage(deps.get_settings(request).data_root)
        disk = {
            "total_gb": round(usage.total / 1e9, 1),
            "used_gb": round(usage.used / 1e9, 1),
            "free_gb": round(usage.free / 1e9, 1),
            "free_bytes": int(usage.free),
        }
    except OSError:
        pass

    # Additive, best-effort growth estimate — null when there isn't enough
    # capture history to project from (see estimate_nightly_bytes). The frontend
    # turns this into a plain-language "about N more nights" headroom line.
    nightly = estimate_nightly_bytes(night_counts, library_bytes, total_frames)
    disk["nightly_bytes"] = int(nightly) if nightly is not None else None

    return StorageResponse(
        targets=rows,
        total_bytes=library_bytes,
        output_bytes=sum(r.output_bytes for r in rows),
        cache_bytes=sum(r.cache_bytes for r in rows),
        # Best-effort like every other figure here: a missing directory is 0.
        exports_bytes=_dir_bytes(picturesarchive.archive_dir(settings)),
        incoming_frames=incoming_frames,
        incoming_bytes=incoming_bytes,
        incoming_unsized_frames=incoming_unsized,
        incoming_copied=bool(settings.copy_to_cache),
        disk=disk,
    )


@router.post("/api/targets/{safe}/cache/clear")
def clear_cache(safe: str, request: Request, stage: str = "all") -> dict:
    """Delete a regenerable cache stage for one target. The project DB and the
    stacked outputs are never touched — only re-creatable intermediates."""
    if stage not in _CLEARABLE:
        raise HTTPException(status_code=400, detail=f"stage must be one of {_CLEARABLE}")
    lib = deps.open_library(request)
    try:
        entry = lib.find_target(safe)
        if entry is None:
            raise HTTPException(status_code=404, detail=f"No target '{safe}'")
        tdir = lib.target_dir(entry)
    finally:
        lib.close()

    cm = CacheManager(tdir)
    cleared: list[str] = []
    if stage in ("stage1", "all"):
        cm.clear("stage1")
        cleared.append("stage1")
    if stage in ("stage2", "all"):
        cm.clear("stage2")
        cleared.append("stage2")
    if stage in ("thumbs", "all"):
        td = thumbs_dir(tdir)
        if td.exists():
            shutil.rmtree(td, ignore_errors=True)
        cleared.append("thumbs")
    if stage in ("proxies", "all"):
        # The editor's live-preview proxies: pure derived data, rebuilt from the
        # stack FITS the next time a run is opened. Clearing them is also the
        # only way an install that pruned runs before v0.264.0 gets back the
        # proxies those deletions used to orphan.
        pd = proxy_dir(tdir)
        if pd.exists():
            shutil.rmtree(pd, ignore_errors=True)
        cleared.append("proxies")
    return {"safe": safe, "cleared": cleared}


class PruneRequest(BaseModel):
    # Keep the N newest runs (delete the rest), or delete an explicit id list.
    keep: int | None = None
    ids: list[int] | None = None


@router.post("/api/targets/{safe}/stack-runs/prune")
def prune_stack_runs(safe: str, body: PruneRequest, request: Request) -> dict:
    """Delete old stack runs and their output files. Either keep the N newest
    (``keep``) or delete a specific ``ids`` list."""
    if body.keep is None and not body.ids:
        raise HTTPException(status_code=400, detail="Provide 'keep' or 'ids'")
    if body.keep is not None and body.keep < 0:
        raise HTTPException(status_code=400, detail="'keep' must be >= 0")

    lib, proj = deps.open_target_project(request, safe)
    # Nested, not two statements in one ``finally`` — if ``proj.close()`` ever
    # raised, the flat form would skip ``lib.close()`` and leak the Library
    # handle. Matches ``get_storage`` above and ``gallery.py``; the trigger is
    # essentially unreachable, so this is consistency, not a live leak.
    try:
        try:
            runs = list(proj.iter_stack_runs())  # newest first
            if body.ids is not None:
                to_delete = [r for r in runs if r.id in set(body.ids)]
            else:
                to_delete = runs[body.keep:]
            for run in to_delete:
                purge_stack_run(proj, run)
        finally:
            proj.close()
    finally:
        lib.close()
    return {"safe": safe, "deleted": [r.id for r in to_delete]}
