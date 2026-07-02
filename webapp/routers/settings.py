"""Settings endpoints."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import ValidationError

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
    # Strip auth credentials (managed only via /api/auth/password) and surface a
    # 422 rather than a 500 when a patch fails validation.
    clean = {k: v for k, v in patch.items() if k not in _AUTH_KEYS}
    try:
        s = store.update(clean)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _serialize(s)


# Settings that only make sense for the machine they were written on — they're
# env/host-specific and would point a restored config at the wrong place. Kept
# out of export/import so a backup taken on one install restores cleanly on
# another (and never repoints the data root out from under a running app).
_HOST_KEYS = ("data_root", "incoming_dir", "library_root", "astap_path")


def _export_payload(s) -> dict[str, Any]:  # noqa: ANN001
    """The persistable settings suitable for backup — no secrets, no host paths."""
    data = s.model_dump()
    for k in (*_AUTH_KEYS, *_HOST_KEYS):
        data.pop(k, None)
    return data


@router.get("/export")
def export_settings(request: Request) -> Response:
    """Download the current config as a portable JSON backup.

    Excludes auth credentials and host-specific paths (see ``_HOST_KEYS``) so the
    file can be restored on any install without leaking the password hash or
    repointing the data root.
    """
    store = deps.get_settings_store(request)
    payload = json.dumps(_export_payload(store.get()), indent=2)
    return Response(
        content=payload,
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=astrostack-settings.json"},
    )


@router.post("/import")
def import_settings(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    """Restore settings from an exported backup.

    Additive and safe: only known, non-secret, non-host fields are applied — any
    auth credentials, host paths, or unknown keys in the uploaded file are
    ignored (the existing values are kept). Validation failures surface as 422.
    """
    store = deps.get_settings_store(request)
    skip = (*_AUTH_KEYS, *_HOST_KEYS)
    clean = {k: v for k, v in payload.items() if k not in skip}
    try:
        s = store.update(clean)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _serialize(s)
