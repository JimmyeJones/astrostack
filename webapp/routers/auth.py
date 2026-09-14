"""Access-control endpoints: set/clear the optional HTTP Basic password."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from webapp import auth, deps

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/status")
def auth_status(request: Request) -> dict[str, Any]:
    s = deps.get_settings(request)
    return {
        "enabled": auth.is_enabled(s),
        "username": s.auth_username,
        # Additive: whether a read-only token exists, never the token itself (it
        # is shown once, at mint time, and only a hash is kept). An older frontend
        # ignores these two; an older backend omitting them reads as "no token",
        # which is the right answer for an install that has never minted one.
        "readonly_enabled": auth.readonly_is_enabled(s),
        "readonly_username": auth.READONLY_USERNAME,
    }


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


@router.post("/readonly-token")
def mint_readonly_token(request: Request) -> dict[str, Any]:
    """Mint (or rotate) the read-only token and return it **once**.

    Only a hash is stored, so this is the only moment the token exists in
    readable form — the caller has to keep it. Calling it again replaces the old
    one, which is how a leaked token is revoked without turning the feature off.

    Like ``set_password``, this sits behind the Basic-auth gate whenever auth is
    enabled, so only someone holding the full credential can mint one. The token
    itself can never reach here: the gate allows it for ``GET`` only.
    """
    store = deps.get_settings_store(request)
    settings = deps.get_settings(request)
    # A token would be theatre on an open install: with no password set every
    # path is already reachable by anyone on the LAN, so refuse rather than hand
    # back a secret that guards nothing.
    if not auth.is_enabled(settings):
        raise HTTPException(
            status_code=400,
            detail="Set an access password first — with no password set the app "
                   "is already open, so a read-only token would guard nothing.",
        )
    token = auth.make_readonly_token()
    h, salt = auth.hash_readonly_token(token)
    s = store.update({"readonly_token_hash": h, "readonly_token_salt": salt})
    return {
        "token": token,
        "username": auth.READONLY_USERNAME,
        "readonly_enabled": auth.readonly_is_enabled(s),
    }


@router.delete("/readonly-token")
def clear_readonly_token(request: Request) -> dict[str, Any]:
    """Revoke the read-only token. Idempotent — no token is already the goal."""
    store = deps.get_settings_store(request)
    s = store.update({"readonly_token_hash": "", "readonly_token_salt": ""})
    return {"readonly_enabled": auth.readonly_is_enabled(s)}
