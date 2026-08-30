"""Pipeline triggers: scan the incoming folder, or QC+solve one target."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from webapp import deps, pipeline
from webapp.config import Settings
from webapp.schemas import ScanRequest

router = APIRouter(tags=["pipeline"])


def _confined_scan_root(settings: Settings, root: str) -> str:
    """Confirm a client-supplied scan root is the incoming folder, or inside it.

    Every other ingest/target endpoint resolves through a database ``safe_name``
    and is traversal-safe by construction; ``root`` is the one place a caller
    names a directory directly, and an unconfined one lets anything that can
    reach the API register (and, with ``copy_to_cache``, copy) FITS from any
    server-readable directory. Auth is off by default, so "anything that can
    reach the API" is everything on the owner's network.

    The check is **lexical** — ``normpath`` on the absolute paths, no symlink
    resolution — because a library or an incoming folder that *is* a symlinked
    NAS share is normal on the box this runs on, and the scan already follows
    such links when it walks the default root. What it rejects is naming a
    directory outside the tree, by absolute path or by ``..``. A caller who
    passes the fully-resolved form of a symlinked incoming folder is accepted
    too, so neither spelling of the same folder is refused.

    Strictly read-only either way: this only decides *where a scan may look*.
    ``incoming/`` remains read-and-create-new only (AGENTS.md §10).
    """
    incoming = settings.resolved_incoming_dir

    def contains(parent: Path, child: Path) -> bool:
        p = os.path.normpath(os.path.abspath(str(parent)))
        c = os.path.normpath(os.path.abspath(str(child)))
        return c == p or c.startswith(p + os.sep)

    asked = Path(root).expanduser()
    if contains(incoming, asked):
        return str(asked)
    try:
        if contains(incoming.resolve(), asked.resolve()):
            return str(asked)
    except (OSError, RuntimeError):  # unresolvable path (loop, permission)
        pass
    raise HTTPException(
        status_code=400,
        detail=(
            "A scan can only look inside your incoming folder "
            f"({incoming}). Leave the folder out to scan all of it."
        ),
    )


@router.post("/api/scan")
def trigger_scan(request: Request, body: ScanRequest | None = None) -> dict[str, str]:
    settings = deps.get_settings(request)
    jm = deps.get_job_manager(request)
    root = body.root if body else None
    # An empty/absent root means "the whole incoming folder" and always has.
    if root:
        root = _confined_scan_root(settings, root)
    job = pipeline.submit_pipeline(settings, jm, root=root)
    return {"job_id": job.id}


@router.post("/api/targets/{safe}/qc-solve")
def trigger_qc_solve(safe: str, request: Request) -> dict[str, str]:
    settings = deps.get_settings(request)
    jm = deps.get_job_manager(request)
    # Ensure target exists.
    lib, proj = deps.open_target_project(request, safe)
    proj.close()
    lib.close()
    job = pipeline.submit_qc_solve(settings, jm, safe)
    return {"job_id": job.id}


@router.post("/api/targets/{safe}/process")
def trigger_process_target(safe: str, request: Request) -> dict[str, str]:
    """One-click "process this target": QC + solve, auto-grade (when enabled),
    then stack, chained in a single job — the whole middle of the workflow with
    no form to fill. Non-destructive (a new stack run alongside any existing)."""
    settings = deps.get_settings(request)
    jm = deps.get_job_manager(request)
    # Ensure target exists.
    lib, proj = deps.open_target_project(request, safe)
    proj.close()
    lib.close()
    job = pipeline.submit_process_target(settings, jm, safe)
    return {"job_id": job.id}
