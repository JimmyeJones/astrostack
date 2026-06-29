"""Jobs: list, get, cancel, and an SSE progress stream."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from webapp import deps
from webapp.jobs import Job
from webapp.schemas import JobOut

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

_TERMINAL = {"done", "error", "cancelled", "interrupted"}


def _to_out(job: Job) -> JobOut:
    return JobOut(**job.to_dict())


@router.get("", response_model=list[JobOut])
def list_jobs(request: Request, limit: int = 100) -> list[JobOut]:
    jm = deps.get_job_manager(request)
    return [_to_out(j) for j in jm.list(limit=limit)]


@router.post("/clear")
def clear_history(request: Request) -> dict:
    """Delete all finished jobs (keeps running/queued ones)."""
    jm = deps.get_job_manager(request)
    return {"removed": jm.clear_history()}


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: str, request: Request) -> JobOut:
    jm = deps.get_job_manager(request)
    job = jm.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="No such job")
    return _to_out(job)


@router.post("/{job_id}/cancel")
def cancel_job(job_id: str, request: Request) -> dict:
    jm = deps.get_job_manager(request)
    ok = jm.cancel(job_id)
    if not ok:
        raise HTTPException(status_code=409, detail="Job not cancellable")
    return {"cancelled": job_id}


@router.get("/{job_id}/events")
async def job_events(job_id: str, request: Request) -> EventSourceResponse:
    jm = deps.get_job_manager(request)
    if jm.get(job_id) is None:
        raise HTTPException(status_code=404, detail="No such job")

    async def gen():
        last = None
        while True:
            if await request.is_disconnected():
                break
            job = jm.get(job_id)
            if job is None:
                break
            payload = json.dumps(job.to_dict())
            if payload != last:
                last = payload
                yield {"event": "progress", "data": payload}
            if job.state in _TERMINAL:
                yield {"event": "done", "data": payload}
                break
            await asyncio.sleep(0.25)

    return EventSourceResponse(gen())
