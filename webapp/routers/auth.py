"""Access-control endpoints: set/clear the optional HTTP Basic password."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from webapp import auth, deps

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/status")
def auth_status(request: Request) -> dict[str, Any]:
    s = deps.get_settings(request)
    return {"enabled": auth.is_enabled(s), "username": s.auth_username}


@router.post("/password")
def set_password(body: dict[str, Any], request: Request) -> dict[str, Any]:
    """Set (or clear) the access password.

    An empty/omitted ``password`` disables auth. While auth is already enabled
    this endpoint is itself behind the Basic-auth gate, so only an
    authenticated user can change or remove the password.
    """
    store = deps.get_settings_store(request)
    password = str(body.get("password", "") or "")
    username = str(body.get("username", "") or "").strip()

    patch: dict[str, Any] = {}
    if username:
        patch["auth_username"] = username
    if password:
        if len(password) < 4:
            raise HTTPException(status_code=400, detail="Password must be at least 4 characters")
        h, salt = auth.hash_password(password)
        patch["auth_password_hash"] = h
        patch["auth_salt"] = salt
    else:
        # Clear → disable auth.
        patch["auth_password_hash"] = ""
        patch["auth_salt"] = ""

    s = store.update(patch)
    return {"enabled": auth.is_enabled(s), "username": s.auth_username}
