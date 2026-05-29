"""Settings endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from webapp import deps

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
def get_settings(request: Request) -> dict[str, Any]:
    store = deps.get_settings_store(request)
    s = store.get()
    data = s.model_dump()
    # Surface resolved paths so the UI can show where things actually live.
    data["resolved_incoming_dir"] = str(s.resolved_incoming_dir)
    data["resolved_library_root"] = str(s.resolved_library_root)
    return data


@router.put("")
def update_settings(patch: dict[str, Any], request: Request) -> dict[str, Any]:
    store = deps.get_settings_store(request)
    s = store.update(patch)
    data = s.model_dump()
    data["resolved_incoming_dir"] = str(s.resolved_incoming_dir)
    data["resolved_library_root"] = str(s.resolved_library_root)
    return data
