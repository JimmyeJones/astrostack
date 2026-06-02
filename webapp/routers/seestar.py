"""Seestar telescope endpoints: discovery, telemetry, and gated control.

Monitoring (list devices, read telemetry, SSE stream) is always available when
``seestar_enabled`` is on. Control commands (goto / start / stop / park) are
additionally gated behind ``seestar_control_enabled`` so that simply watching a
scope can never disturb an in-progress session; a disabled control returns 409.
"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from webapp import deps
from webapp.seestar.client import SeestarError

router = APIRouter(prefix="/api/seestar", tags=["seestar"])


def _require_enabled(request: Request) -> None:
    if not deps.get_settings(request).seestar_enabled:
        raise HTTPException(status_code=409, detail="Seestar integration is disabled")


def _require_control(request: Request) -> None:
    settings = deps.get_settings(request)
    if not settings.seestar_enabled:
        raise HTTPException(status_code=409, detail="Seestar integration is disabled")
    if not settings.seestar_control_enabled:
        raise HTTPException(
            status_code=409,
            detail="Seestar control is disabled. Enable it in Settings to send commands.",
        )


@router.get("/devices")
def list_devices(request: Request) -> dict:
    settings = deps.get_settings(request)
    mgr = deps.get_seestar_manager(request)
    return {
        "enabled": settings.seestar_enabled,
        "control_enabled": settings.seestar_control_enabled,
        "devices": mgr.snapshot(),
    }


@router.post("/scan")
def scan(request: Request) -> dict:
    _require_enabled(request)
    deps.get_seestar_manager(request).request_scan()
    return {"scanning": True}


@router.post("/{ip}/connect")
def connect(ip: str, request: Request) -> dict:
    _require_enabled(request)
    try:
        deps.get_seestar_manager(request).connect(ip)
    except SeestarError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"connected": ip}


@router.post("/{ip}/disconnect")
def disconnect(ip: str, request: Request) -> dict:
    deps.get_seestar_manager(request).disconnect(ip)
    return {"disconnected": ip}


@router.get("/{ip}/state")
def device_state(ip: str, request: Request) -> dict:
    mgr = deps.get_seestar_manager(request)
    dev = next((d for d in mgr.snapshot() if d["id"] == ip), None)
    if dev is None:
        raise HTTPException(status_code=404, detail=f"No device {ip}")
    return dev


@router.get("/{ip}/events")
async def device_events(ip: str, request: Request) -> EventSourceResponse:
    mgr = deps.get_seestar_manager(request)

    async def gen():
        last = None
        while True:
            if await request.is_disconnected():
                break
            dev = next((d for d in mgr.snapshot() if d["id"] == ip), None)
            payload = json.dumps(dev) if dev is not None else json.dumps({"id": ip, "error": "gone"})
            if payload != last:
                last = payload
                yield {"event": "telemetry", "data": payload}
            await asyncio.sleep(1.0)

    return EventSourceResponse(gen())


class GotoRequest(BaseModel):
    ra_hours: float
    dec_deg: float
    target_name: str = "AstroStack"


@router.post("/{ip}/goto")
def goto(ip: str, body: GotoRequest, request: Request) -> dict:
    _require_control(request)
    return _run_control(request, ip, "goto", body.model_dump())


@router.post("/{ip}/start")
def start(ip: str, request: Request) -> dict:
    _require_control(request)
    return _run_control(request, ip, "start", {})


@router.post("/{ip}/stop")
def stop(ip: str, request: Request) -> dict:
    _require_control(request)
    return _run_control(request, ip, "stop", {})


@router.post("/{ip}/park")
def park(ip: str, request: Request) -> dict:
    _require_control(request)
    return _run_control(request, ip, "park", {})


def _run_control(request: Request, ip: str, action: str, params: dict) -> dict:
    mgr = deps.get_seestar_manager(request)
    try:
        result = mgr.control(ip, action, params)
    except SeestarError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"ok": True, "action": action, "result": result}
