"""Pipeline triggers: scan the incoming folder, or QC+solve one target."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from webapp import deps, pipeline
from webapp.config import Settings
from webapp.schemas import ScanRequest

router = APIRouter(tags=["pipeline"])


def confined_scan_root(settings: Settings, root: str) -> str:
    """Resolve a client-supplied scan ``root``, confirming it stays inside the
    configured incoming folder.

    Every other ingest path in the app resolves server-side — the upload router
    re-confirms each destination with :func:`webapp.routers.upload.confined_dest`,
    and every target endpoint goes through a DB ``safe_name`` lookup — so this was
    the one place a client could name an arbitrary server-readable directory and
    have its FITS registered into the Library (and copied into the cache when
    ``copy_to_cache`` is on). Defence in depth rather than a live exploit: this is
    a local single-user app and the scan only *reads* its source. Confining it
    keeps the posture uniform.

    A relative root is taken as relative to the incoming folder (the only tree it
    could legally name anyway), so ``{"root": "M42"}`` means what a caller would
    expect instead of resolving against the server's working directory. Raises
    ``400`` when the resolved path escapes; ``incoming/`` itself is allowed and is
    what an omitted root already means.
    """
    incoming = settings.resolved_incoming_dir.resolve()
    candidate = Path(root).expanduser()
    if not candidate.is_absolute():
        candidate = incoming / candidate
    candidate = candidate.resolve()
    if candidate != incoming and incoming not in candidate.parents:
        raise HTTPException(
            status_code=400,
            detail=(
                "A scan can only look inside your incoming folder "
                f"({incoming}). Leave the folder blank to scan all of it."
            ),
        )
    return str(candidate)


@router.post("/api/scan")
def trigger_scan(request: Request, body: ScanRequest | None = None) -> dict[str, str]:
    settings = deps.get_settings(request)
    jm = deps.get_job_manager(request)
    root = body.root if body else None
    if root:
        root = confined_scan_root(settings, root)
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
