"""``GET /api/diagnostics`` — the answers the shipped library diagnostics gave.

Read-only. Lists every stored result of :mod:`seestack.diag` (numbers and
catalogue names only, by that package's contract) and which diagnostics are
still waiting to run. It is on the read-only token's allowlist so the observer
on the owner's NAS can collect new results and report them, which is the whole
point: a question about his real library is answered without anyone typing a
command (see :mod:`webapp.diagnostics`).
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from webapp import deps
from webapp import diagnostics as diag
from webapp.routers._disposition import attachment

router = APIRouter(tags=["diagnostics"])


@router.get("/api/diagnostics")
def get_diagnostics(request: Request) -> dict[str, Any]:
    return diag.all_results(deps.get_settings(request))


@router.post("/api/diagnostics/report")
def start_report(request: Request) -> dict[str, Any]:
    """Start "Create a report for Claude": re-run every diagnostic that can run
    on this library as one background job. Returns that job (a second press
    while one is queued or running returns the same job)."""
    job = diag.submit_report(deps.get_settings(request), deps.get_job_manager(request))
    return {"job_id": job.id, "state": job.state}


@router.get("/api/diagnostics/report")
def download_report(request: Request) -> JSONResponse:
    """The report as one downloadable JSON file — numbers and catalogue names
    only (no paths, location, addresses, serials or keys)."""
    try:
        manager = deps.get_seestar_manager(request)
    except Exception:  # noqa: BLE001 — no Seestar manager in some test apps
        manager = None
    report = diag.build_report(deps.get_settings(request), deps.get_job_manager(request),
                               manager)
    stamp = report["generated_utc"][:10]
    return JSONResponse(report, headers={
        "Content-Disposition": attachment(f"astrostack-report-{stamp}.json")})
