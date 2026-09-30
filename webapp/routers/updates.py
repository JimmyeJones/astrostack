"""Settings → "App updates": the page half of the one-click update.

The app cannot update itself — it runs inside the container an update rebuilds —
so these endpoints only **ask**. ``POST`` writes ``state/updater/request.json``;
``scripts/update_agent.py``, run on the NAS by a cron job the owner sets up once,
picks it up, runs ``scripts/deploy.sh`` (stop, back up, build, health-check) or
``scripts/rollback.sh``, and reports in ``state/updater/status.json``, which
``GET`` reads. That split is the security design, not a convenience: giving the
container the Docker socket instead would make "anyone who can open this page"
root on the NAS, on an app whose password is off by default.

What the page can ask for is deliberately small, and the helper re-checks all of
it (the request is data it validates, never a command): *check*, *update* — which
always installs the ``stable`` branch, the newest ``main`` commit that has had
three days and a green CI run — and *roll back* to the version before the last
update, optionally restoring the backup taken just before it (typed RESTORE).

Nothing here reaches the network. The helper runs ``git fetch`` on the NAS only
when the owner presses Check or Update (owner's answer, 2026-09-30; AGENTS.md §1).

The read-only observer token cannot reach any of this: none of these paths are in
``webapp.main._READONLY_GET_PATHS``.
"""
from __future__ import annotations

import json
import os
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from webapp import deps

router = APIRouter(tags=["updates"])

#: A helper that has not stamped its heartbeat for this long is treated as gone
#: (cron runs it every minute, and a deploy stamps it every 20 s from a thread).
HELPER_STALE_S = 180
#: The helper drops an ask older than an hour; the page stops calling it pending
#: at the same age so the two never disagree about whether something is queued.
REQUEST_MAX_AGE_S = 3600


def _queue(request: Request) -> Path:
    return deps.get_settings(request).state_dir / "updater"


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        obj = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    return obj if isinstance(obj, dict) else None


def _ver(v: Any) -> tuple[int, ...]:
    try:
        return tuple(int(p) for p in str(v).split("."))
    except ValueError:
        return ()


def _running_version() -> str:
    return __import__("webapp").__version__


def update_status(queue: Path, now: float | None = None) -> dict[str, Any]:
    """Everything the App updates card shows, from the helper's status file."""
    now = time.time() if now is None else now
    status = _read_json(queue / "status.json")
    pending = _read_json(queue / "request.json")
    if pending is not None and not (
            isinstance(pending.get("requested_at"), (int, float))
            and now - pending["requested_at"] < REQUEST_MAX_AGE_S):
        pending = None

    running = _running_version()
    if status is None:
        helper, seen = "missing", None
    else:
        seen = status.get("agent_seen_at")
        fresh = isinstance(seen, (int, float)) and now - seen < HELPER_STALE_S
        helper = "ok" if fresh else "stale"
        status = status if fresh or status.get("state") in (None, "idle") else {**status, "state": "idle"}

    status = status or {}
    available = status.get("available") if isinstance(status.get("available"), dict) else None
    newer = bool(available and _ver(available.get("version")) > _ver(running))
    return {
        "running_version": running,
        "helper": helper,
        "helper_seen_at": seen,
        "state": status.get("state") or "idle",
        "job": status.get("job"),
        "pending": {"id": pending.get("id"), "action": pending.get("action")} if pending else None,
        "checked_at": status.get("checked_at"),
        "available": available,
        "update_available": newer,
        "rollback": status.get("rollback") if isinstance(status.get("rollback"), dict) else None,
        "last_result": status.get("last_result") if isinstance(status.get("last_result"), dict) else None,
    }


def _write_request(queue: Path, body: dict[str, Any]) -> dict[str, Any]:
    queue.mkdir(parents=True, exist_ok=True)
    req = {"id": uuid.uuid4().hex[:16], "requested_at": time.time(), **body}
    fd, tmp = tempfile.mkstemp(dir=queue, prefix=".request.")
    with os.fdopen(fd, "w") as f:
        json.dump(req, f)
    os.replace(tmp, queue / "request.json")
    return {"id": req["id"], "action": req["action"]}


def _require_ready(st: dict[str, Any]) -> None:
    if st["helper"] != "ok":
        raise HTTPException(409, "The update helper on your NAS isn't running — see the setup steps on this card.")
    if st["pending"] or st["state"] != "idle":
        raise HTTPException(409, "The helper is already working on a request — wait for it to finish.")


@router.get("/api/updates")
def get_updates(request: Request) -> dict[str, Any]:
    return update_status(_queue(request))


@router.post("/api/updates/check")
def check_updates(request: Request) -> dict[str, Any]:
    q = _queue(request)
    _require_ready(update_status(q))
    return _write_request(q, {"action": "check"})


@router.post("/api/updates/apply")
def apply_update(request: Request) -> dict[str, Any]:
    q = _queue(request)
    st = update_status(q)
    _require_ready(st)
    if not st["update_available"]:
        raise HTTPException(409, "There is no newer tested version to install — press Check for updates first.")
    return _write_request(q, {"action": "update"})


class RollbackIn(BaseModel):
    restore_data: bool = False
    confirm: str | None = None


@router.post("/api/updates/rollback")
def rollback_update(body: RollbackIn, request: Request) -> dict[str, Any]:
    q = _queue(request)
    st = update_status(q)
    _require_ready(st)
    rb = st["rollback"]
    if not rb:
        raise HTTPException(409, "There is no earlier version recorded to go back to.")
    if rb.get("needs_restore_data") and not body.restore_data:
        raise HTTPException(409, f"v{rb.get('to_version')} can't read the newer database format, "
                                 "so going back also restores the backup taken before the update.")
    if body.restore_data and body.confirm != "RESTORE":
        raise HTTPException(400, "Type RESTORE to confirm restoring the backup.")
    req: dict[str, Any] = {"action": "rollback", "restore_data": body.restore_data}
    if body.restore_data:
        req["confirm"] = "RESTORE"
    return _write_request(q, req)
