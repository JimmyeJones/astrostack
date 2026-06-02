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

import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from seestack.core.cache import CacheManager
from seestack.io.project import StackRunRow
from seestack.render.thumbnail import thumbs_dir
from webapp import deps

router = APIRouter(tags=["storage"])

# Cache stages the user can clear. "stage1"/"stage2" map to CacheManager;
# "thumbs" is the per-frame thumbnail cache; "all" clears every regenerable bit.
_CLEARABLE = ("stage1", "stage2", "thumbs", "all")


def _dir_bytes(path: Path) -> int:
    """Total size of files under ``path`` (recursive). 0 if missing."""
    if not path.exists():
        return 0
    total = 0
    for p in path.rglob("*"):
        try:
            if p.is_file():
                total += p.stat().st_size
        except OSError:
            continue
    return total


def delete_run_artifacts(run: StackRunRow) -> None:
    """Unlink a stack run's output files (FITS/TIFF/preview). Best-effort."""
    for attr in ("fits_path", "tiff_path", "preview_path"):
        p = getattr(run, attr, None)
        if p:
            try:
                Path(p).unlink(missing_ok=True)
            except OSError:
                pass


class TargetStorage(BaseModel):
    safe: str
    name: str
    total_bytes: int
    output_bytes: int
    cache_bytes: int        # stage1 + stage2 + thumbs (all regenerable)
    stage1_bytes: int
    stage2_bytes: int
    thumbs_bytes: int
    n_stack_runs: int


class StorageResponse(BaseModel):
    targets: list[TargetStorage]
    total_bytes: int
    output_bytes: int
    cache_bytes: int
    disk: dict


@router.get("/api/storage", response_model=StorageResponse)
def get_storage(request: Request) -> StorageResponse:
    from seestack.io.project import Project

    lib = deps.open_library(request)
    rows: list[TargetStorage] = []
    try:
        for t in lib.list_targets():
            tdir = lib.target_dir(t)
            cm = CacheManager(tdir)
            stage1 = cm.stats("stage1").bytes_total
            stage2 = cm.stats("stage2").bytes_total
            thumbs = _dir_bytes(thumbs_dir(tdir))
            output = _dir_bytes(tdir / "output")
            total = _dir_bytes(tdir)
            n_runs = 0
            proj = None
            try:
                proj = Project.open(tdir)
                n_runs = sum(1 for _ in proj.iter_stack_runs())
            except Exception:  # noqa: BLE001
                pass
            finally:
                if proj is not None:
                    proj.close()
            rows.append(TargetStorage(
                safe=t.safe_name, name=t.name,
                total_bytes=total, output_bytes=output,
                cache_bytes=stage1 + stage2 + thumbs,
                stage1_bytes=stage1, stage2_bytes=stage2, thumbs_bytes=thumbs,
                n_stack_runs=n_runs,
            ))
    finally:
        lib.close()

    rows.sort(key=lambda r: r.total_bytes, reverse=True)

    disk: dict = {}
    try:
        usage = shutil.disk_usage(deps.get_settings(request).data_root)
        disk = {
            "total_gb": round(usage.total / 1e9, 1),
            "used_gb": round(usage.used / 1e9, 1),
            "free_gb": round(usage.free / 1e9, 1),
        }
    except OSError:
        pass

    return StorageResponse(
        targets=rows,
        total_bytes=sum(r.total_bytes for r in rows),
        output_bytes=sum(r.output_bytes for r in rows),
        cache_bytes=sum(r.cache_bytes for r in rows),
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
    try:
        runs = list(proj.iter_stack_runs())  # newest first
        if body.ids is not None:
            to_delete = [r for r in runs if r.id in set(body.ids)]
        else:
            to_delete = runs[body.keep:]
        for run in to_delete:
            delete_run_artifacts(run)
            if run.id is not None:
                proj.delete_stack_run(run.id)
    finally:
        proj.close()
        lib.close()
    return {"safe": safe, "deleted": [r.id for r in to_delete]}
