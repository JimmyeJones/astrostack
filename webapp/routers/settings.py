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


def _sanitize_patch(clean: dict[str, Any]) -> dict[str, Any]:
    """Sanitise *and validate* a persisted default_stack_options in a settings patch.

    Two guards, both mirroring the per-target stack-defaults endpoint
    (``put_stack_defaults``) so the global default is held to the same contract:

    * **Drop calibration master paths.** ``NON_FORM_KEYS`` (``dark_path`` etc.) are
      resolved server-side from master ids and must never be set from raw client
      input (a settings PUT body or an imported backup) — otherwise a raw path
      would leak into every default-based stack.
    * **Reject an out-of-range / bad-enum value with a 422.** ``store.update``
      persists ``default_stack_options`` as an opaque ``dict[str, Any]``, so
      without this a client could PUT e.g. ``{"mosaic_canvas": "garbage"}`` or an
      out-of-range ``sigma_kappa`` and get a 200. That poisoned default is then
      served into *every* target's Stack form (``get_stack_defaults``) and 400s
      every subsequent stack — and the unattended auto-stack chain feeds it
      straight to the engine, the exact cryptic-deep-failure ``validate_stack_options``
      exists to prevent. The per-target ``PUT .../stack-defaults`` already validates;
      this closes the same gap on the global path.

    Mutates and returns *clean*. Raises ``HTTPException(422)`` on a bad value."""
    dso = clean.get("default_stack_options")
    if isinstance(dso, dict):
        from webapp.schemas import strip_non_form_keys, validate_stack_options
        stripped = strip_non_form_keys(dso)
        try:
            validate_stack_options(stripped)
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail=f"invalid default stack option: {exc}") from exc
        clean["default_stack_options"] = stripped
    return clean


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
    clean = _sanitize_patch({k: v for k, v in patch.items() if k not in _AUTH_KEYS})
    try:
        s = store.update(clean)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    # Apply the (possibly changed) history cap to the running JobManager so it
    # takes effect without a restart. Best-effort: never fail the settings save
    # if the manager isn't wired up (e.g. in a lightweight test app).
    try:
        deps.get_job_manager(request).max_history = s.job_history_limit
    except Exception:  # noqa: BLE001 — a missing manager must not 500 the save
        pass
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
    clean = _sanitize_patch({k: v for k, v in payload.items() if k not in skip})
    try:
        s = store.update(clean)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _serialize(s)
