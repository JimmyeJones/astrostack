"""Settings endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from webapp import deps

router = APIRouter(prefix="/api/settings", tags=["settings"])

# Auth credentials are managed only via /api/auth/password. They're never
# exposed in the settings GET nor accepted through the settings PUT — otherwise
# a client could read the hash or set a password to one it already knows.
_AUTH_KEYS = ("auth_password_hash", "auth_salt", "auth_username")


def _serialize(s) -> dict[str, Any]:  # noqa: ANN001
    data = s.model_dump()
    for k in _AUTH_KEYS:
        data.pop(k, None)
    # Surface resolved paths so the UI can show where things actually live.
    data["resolved_incoming_dir"] = str(s.resolved_incoming_dir)
    data["resolved_library_root"] = str(s.resolved_library_root)
    return data


@router.get("")
def get_settings(request: Request) -> dict[str, Any]:
    store = deps.get_settings_store(request)
    return _serialize(store.get())


@router.put("")
def update_settings(patch: dict[str, Any], request: Request) -> dict[str, Any]:
    store = deps.get_settings_store(request)
    clean = {k: v for k, v in patch.items() if k not in _AUTH_KEYS}
    return _serialize(store.update(clean))
