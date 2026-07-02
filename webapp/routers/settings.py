"""Settings endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import ValidationError

from webapp import deps

router = APIRouter(prefix="/api/settings", tags=["settings"])

# Auth credentials are managed only via /api/auth/password. They're never
# exposed in the settings GET nor accepted through the settings PUT — otherwise
# a client could read the hash or set a password to one it already knows.
_AUTH_KEYS = ("auth_password_hash", "auth_salt", "auth_username")

# Read-only fields the GET decorates onto the payload; they're derived, not
# stored, so they must be dropped before an imported config is applied.
_DERIVED_KEYS = ("resolved_incoming_dir", "resolved_library_root")


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
    # Strip auth credentials (managed only via /api/auth/password) and surface a
    # 422 rather than a 500 when a patch fails validation.
    clean = {k: v for k, v in patch.items() if k not in _AUTH_KEYS}
    try:
        s = store.update(clean)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _serialize(s)


@router.get("/export")
def export_settings(request: Request) -> dict[str, Any]:
    """Download the current config as a self-identifying backup envelope.

    Auth credentials and derived paths are excluded, so the file is safe to
    keep and to restore onto another install. Import accepts this envelope (or
    a bare settings object) back via ``POST /api/settings/import``.
    """
    from webapp import __version__

    store = deps.get_settings_store(request)
    data = _serialize(store.get())
    for k in _DERIVED_KEYS:
        data.pop(k, None)
    return {
        "astrostack_settings": True,
        "app_version": __version__,
        "exported_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "settings": data,
    }


@router.post("/import")
def import_settings(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    """Restore settings from an exported backup (or a bare settings object).

    Only known settings fields are applied; auth credentials, derived paths and
    any unknown keys are ignored, and an out-of-range value 422s rather than
    corrupting the live config. This is a merge (like PUT), so fields absent
    from the file keep their current values.
    """
    # Accept both the export envelope ({"settings": {...}}) and a bare dict.
    incoming = payload.get("settings") if isinstance(payload.get("settings"), dict) else payload
    if not isinstance(incoming, dict):
        raise HTTPException(status_code=422, detail="no settings object found in payload")
    clean = {
        k: v for k, v in incoming.items()
        if k not in _AUTH_KEYS and k not in _DERIVED_KEYS
    }
    if not clean:
        raise HTTPException(status_code=422, detail="no importable settings fields found")
    store = deps.get_settings_store(request)
    try:
        s = store.update(clean)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _serialize(s)
