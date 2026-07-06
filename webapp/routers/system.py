"""System info + health check."""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from webapp import deps, pipeline

router = APIRouter(tags=["system"])


def _first_solvable_frame(lib) -> tuple[str, str] | None:
    """Return (target_safe, fits_path) of the first frame we could solve, or None."""
    from seestack.io.project import Project

    for t in lib.list_targets():
        proj = None
        try:
            proj = Project.open(lib.target_dir(t))
            for f in proj.iter_frames():
                path = f.cached_path or f.source_path
                if path and Path(path).exists():
                    return t.safe_name, str(path)
        except Exception:  # noqa: BLE001 — skip broken projects
            pass
        finally:
            if proj is not None:
                proj.close()
    return None


@router.post("/api/system/astap-test")
async def astap_test(request: Request) -> dict:
    """Actually run ASTAP on a real frame from the library — the only test that
    confirms the binary + star database + a solve all work end-to-end."""
    settings = deps.get_settings(request)

    def work() -> dict:
        from seestack.solve.runner import solve_one

        lib = deps.open_library(request)
        try:
            found = _first_solvable_frame(lib)
        finally:
            lib.close()
        if found is None:
            return {"ok": False, "detail": "No ingested frames to test on. Scan some data first."}
        safe, path = found
        t0 = time.monotonic()
        res = solve_one(0, path, astap_path=settings.astap_path,
                        fov_deg=settings.astap_fov_deg, timeout_s=min(settings.astap_timeout_s, 45.0))
        elapsed = time.monotonic() - t0
        return {
            "ok": res.solved,
            "target": safe,
            "frame": Path(path).name,
            "solved": res.solved,
            "ra_deg": res.ra_center_deg,
            "dec_deg": res.dec_center_deg,
            "elapsed_s": round(elapsed, 1),
            "detail": None if res.solved else (res.error or "solve failed"),
        }

    return await run_in_threadpool(work)


def _astap_info(settings) -> dict:  # noqa: ANN001
    """Report ASTAP availability *and* whether it can actually solve.

    A common failure mode is "binary found but no star database" — every solve
    then fails. We surface the database directory + ``.290`` count and a short
    self-test so the cause is obvious from the Settings page.
    """
    try:
        import subprocess

        from seestack.solve.astap import find_astap, find_star_db_dir

        path = find_astap(settings.astap_path)
        if path is None:
            return {
                "found": False, "path": None, "star_db_found": False,
                "star_db_dir": None, "star_db_count": 0,
                "hint": "ASTAP binary not found. Set astap_path or SEESTACK_ASTAP_PATH.",
            }

        db_dir = find_star_db_dir(path)
        db_count = (
            len(list(db_dir.glob("*.290"))) + len(list(db_dir.glob("*.1476")))
            if db_dir else 0
        )
        info = {
            "found": True,
            "path": str(path),
            "star_db_found": db_count > 0,
            "star_db_dir": str(db_dir) if db_dir else None,
            "star_db_count": db_count,
        }
        # Quick "does it even run" probe (does not solve a frame).
        try:
            proc = subprocess.run(  # noqa: S603
                [str(path), "-h"], capture_output=True, text=True, timeout=15, check=False,
            )
            out = (proc.stdout + proc.stderr)
            ver = next((ln for ln in out.splitlines() if "version" in ln.lower()), "")
            info["runs"] = True
            info["version"] = ver.strip()[:120] or None
        except Exception as exc:  # noqa: BLE001
            info["runs"] = False
            info["error"] = f"ASTAP failed to run: {exc}"
        if db_count == 0:
            info["hint"] = (
                "ASTAP is installed but no star database (*.290) was found next "
                "to it — every solve will fail. Add one (e.g. d05) to "
                f"{path.parent} or set SEESTACK_ASTAP_DATA."
            )
        return info
    except Exception as exc:  # noqa: BLE001
        return {"found": False, "path": None, "error": str(exc)}


def _memory_info() -> dict:
    """Total + currently-available RAM in GB (Linux /proc/meminfo), so the UI can
    warn when the stack memory budget is set higher than the box can back. Empty
    dict when meminfo can't be read (non-Linux / restricted container)."""
    fields: dict[str, int] = {}
    try:
        with open("/proc/meminfo") as fh:
            for line in fh:
                key, _, rest = line.partition(":")
                if key in ("MemTotal", "MemAvailable"):
                    fields[key] = int(rest.split()[0]) * 1024  # kB → bytes
                    if len(fields) == 2:
                        break
    except (OSError, ValueError):
        return {}
    out: dict = {}
    if "MemTotal" in fields:
        out["total_gb"] = round(fields["MemTotal"] / 1e9, 1)
    if "MemAvailable" in fields:
        out["available_gb"] = round(fields["MemAvailable"] / 1e9, 1)
    return out


def _gpu_available() -> bool:
    try:
        from seestack.core.xp import GPU_AVAILABLE

        return bool(GPU_AVAILABLE)
    except Exception:  # noqa: BLE001
        return False


class ReprocessAllBody(BaseModel):
    # When True, skip targets whose most recent genuine stack was already produced
    # by the current app version — reprocess only what an upgrade would change,
    # not the whole library. Defaults False so the endpoint's existing behaviour
    # (restack everything) is unchanged for any caller that omits it.
    stale_only: bool = False
    # When True, re-run QC / plate-solve / auto-grade over each target's existing
    # frames *before* restacking it, so the reprocess also picks up QC/solve/grading
    # improvements — not just the stacker's. Much slower (a full rescan), so it's an
    # explicit opt-in; defaults False (plain restack) to keep existing callers'
    # behaviour unchanged.
    deep_rescan: bool = False
    # When True, chain the one-click Auto recipe onto each restacked run so the
    # reprocess yields finished *pictures* (a saved editor recipe + re-rendered
    # thumbnail), not flat linear masters. Only touches the new runs' own recipe;
    # off by default (it seeds an editor recipe on many runs at once).
    auto_edit: bool = False


@router.post("/api/reprocess-all")
def reprocess_all(request: Request, body: ReprocessAllBody | None = None) -> dict[str, Any]:
    """Restack every target with the current engine (owner-requested maintenance
    action). Non-destructive: each restack is a new run alongside the old one,
    run serially so the memory-bounded stack hot path is never oversubscribed.

    With ``stale_only`` set, targets already stacked on the current version are
    skipped, so an upgrade reprocesses only the images that would actually change.
    With ``deep_rescan`` set, each target's frames are re-QC'd / re-solved /
    re-graded before its restack (slower; picks up QC/solve/grading improvements
    too, not just the stacker's). With ``auto_edit`` set, the one-click Auto recipe
    is chained onto each restacked run so the batch produces finished pictures, not
    flat linear masters.

    Idempotent-ish: if a reprocess-all batch is already queued/running, return
    that job instead of enqueuing a duplicate.
    """
    settings = deps.get_settings(request)
    jm = deps.get_job_manager(request)
    existing = jm.active_of_kind("reprocess_all")
    if existing is not None:
        return {"job_id": existing.id, "already_running": True}
    stale_only = bool(body.stale_only) if body is not None else False
    deep_rescan = bool(body.deep_rescan) if body is not None else False
    auto_edit = bool(body.auto_edit) if body is not None else False
    job = pipeline.submit_reprocess_all(settings, jm, stale_only=stale_only,
                                        deep_rescan=deep_rescan, auto_edit=auto_edit)
    return {"job_id": job.id, "already_running": False}


@router.get("/api/reprocess-status")
def reprocess_status(request: Request) -> dict[str, Any]:
    """How many targets' current images were made by an older engine version than
    the running build — so the UI can *proactively* nudge the user to reprocess
    after an in-place upgrade instead of hoping they remember to. Read-only.

    Returns ``{current_version, outdated, up_to_date, total_targets}``; ``outdated``
    counts only targets that already have a genuine stack on a different version
    (a never-stacked target is neither), i.e. exactly the images a reprocess would
    change. FastAPI runs this sync endpoint in a threadpool, so the per-target
    SQLite reads don't block the event loop.
    """
    from seestack.io.library import Library

    settings = deps.get_settings(request)
    lib = Library.open_or_create(settings.resolved_library_root)
    try:
        return pipeline.reprocess_status(lib)
    finally:
        lib.close()


@router.get("/api/health")
async def health() -> dict:
    """Liveness probe. Deliberately trivial — no subprocess, no disk, no locks.

    This is what Docker's HEALTHCHECK hits. It must answer *instantly* even when
    the job worker is pinning every core on a long stack; anything heavier here
    (e.g. shelling out to ASTAP, which is slow under load) can blow the probe's
    timeout, get the container restarted mid-stack, and leave jobs "interrupted".
    Rich status (ASTAP, disk, GPU) lives on ``/api/system`` instead.
    """
    return {"ok": True}


@router.get("/api/system")
def system(request: Request) -> dict:
    settings = deps.get_settings(request)
    astap = _astap_info(settings)
    disk = {}
    try:
        usage = shutil.disk_usage(settings.data_root)
        disk = {
            "total_gb": round(usage.total / 1e9, 1),
            "used_gb": round(usage.used / 1e9, 1),
            "free_gb": round(usage.free / 1e9, 1),
        }
    except OSError:
        pass
    return {
        "version": __import__("webapp").__version__,
        "data_root": settings.data_root,
        "cpu_count": os.cpu_count(),
        "cpu_workers": settings.cpu_workers,
        "gpu_available": _gpu_available(),
        "astap": astap,
        "disk": disk,
        "memory": _memory_info(),
        "watcher_enabled": settings.watcher_enabled,
    }
