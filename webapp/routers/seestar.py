"""Seestar telescope endpoints: discovery, telemetry, and gated control.

Monitoring (list devices, read telemetry, SSE stream) is always available when
``seestar_enabled`` is on. Control commands (goto / start / stop / park, and
slice 4's stop-stack / resume / autofocus / focus / solve) are
additionally gated behind ``seestar_control_enabled`` so that simply watching a
scope can never disturb an in-progress session; a disabled control returns 409.
"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from webapp import deps
from webapp.seestar import keyfile
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


# ---- the interop key (⭐ Seestar-page upgrade, slice 1) ---------------------
#
# Firmware 7.18+ answers commands only from a client that signs its challenge
# with this key. These three endpoints say only "installed / not installed":
# the key is never served back (`webapp.seestar.keyfile` holds the rules). None
# is gated on `seestar_enabled` — the owner may add the key before switching the
# integration on — and none is on the read-only token's allowlist. The upload is
# a JSON body, which is also this app's CSRF guard (see `routers/updates.py`).


class KeyUpload(BaseModel):
    pem: str = Field(max_length=4 * keyfile.MAX_KEY_BYTES)


@router.get("/key")
def key_status(request: Request) -> dict:
    return keyfile.key_status(deps.get_settings(request).state_dir)


@router.post("/key")
def upload_key(body: KeyUpload, request: Request) -> dict:
    state_dir = deps.get_settings(request).state_dir
    try:
        keyfile.install_key(state_dir, body.pem)
    except keyfile.KeyFileError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    except OSError:
        raise HTTPException(
            status_code=500,
            detail="AstroStack couldn't save the key file. Check that its data folder is writable.",
        ) from None
    return keyfile.key_status(state_dir)


@router.delete("/key")
def remove_key(request: Request) -> dict:
    state_dir = deps.get_settings(request).state_dir
    removed = keyfile.remove_key(state_dir)
    return {**keyfile.key_status(state_dir), "removed": removed}


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


@router.get("/{ip}/image")
def device_image(ip: str, request: Request,
                 kind: str = Query("thumb", pattern="^(thumb|full)$")) -> Response:
    """The newest picture the scope holds, relayed from its own HTTP server
    (⭐ Seestar-page upgrade, slice 3). Read-only; only a scope the manager
    already knows, at the path the scope reported. 204 when it holds none."""
    _require_enabled(request)
    mgr = deps.get_seestar_manager(request)
    if not any(d["id"] == ip for d in mgr.snapshot()):
        raise HTTPException(status_code=404, detail=f"No device {ip}")
    body = mgr.latest_image(ip, kind)
    if body is None:
        return Response(status_code=204)
    media = "image/png" if body.startswith(b"\x89PNG") else "image/jpeg"
    return Response(content=body, media_type=media,
                    headers={"Cache-Control": "private, max-age=60"})


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
    ra_hours: float = Field(ge=0, lt=24)
    dec_deg: float = Field(ge=-90, le=90)
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


# ---- the controls Seestar Studio verified on the real scope (⭐ slice 4) ----
#
# Only what Studio's test table marks "verified on the real scope": stop and
# resume stacking, focus, plate solve (GoTo + stack and park are above; park
# now passes the scope's current ``equ_mode``). Nothing simulator-only, and no
# skyline scan or free slewing — the firmware picks its own GoTo route.


class FocusNudge(BaseModel):
    #: Focuser steps from where it is now; Studio's buttons are ±1/±10/±50.
    steps: int = Field(ge=-200, le=200)


@router.post("/{ip}/stop-stack")
def stop_stack(ip: str, request: Request) -> dict:
    _require_control(request)
    return _run_control(request, ip, "stop_stack", {})


@router.post("/{ip}/resume")
def resume(ip: str, request: Request) -> dict:
    _require_control(request)
    return _run_control(request, ip, "resume", {})


@router.post("/{ip}/autofocus")
def autofocus(ip: str, request: Request) -> dict:
    _require_control(request)
    return _run_control(request, ip, "autofocus", {})


@router.post("/{ip}/focus")
def focus(ip: str, body: FocusNudge, request: Request) -> dict:
    _require_control(request)
    if body.steps == 0:
        raise HTTPException(status_code=422, detail="steps must not be 0")
    return _run_control(request, ip, "focus", body.model_dump())


@router.post("/{ip}/solve")
def solve(ip: str, request: Request) -> dict:
    _require_control(request)
    return _run_control(request, ip, "solve", {})


def _run_control(request: Request, ip: str, action: str, params: dict) -> dict:
    mgr = deps.get_seestar_manager(request)
    try:
        result = mgr.control(ip, action, params)
    except SeestarError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"ok": True, "action": action, "result": result}
