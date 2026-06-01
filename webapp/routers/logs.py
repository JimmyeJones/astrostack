"""Recent application logs, for in-app diagnostics.

``GET /api/logs`` returns the tail of the in-memory log ring buffer so the user
can see what happened (the canvas size that preceded an OOM, a stack error,
solve warnings) without shelling into the container.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from webapp import logbuffer

router = APIRouter(tags=["logs"])


@router.get("/api/logs")
def get_logs(since: int = 0, level: str | None = None, limit: int = 1000) -> dict[str, Any]:
    """Recent log lines.

    ``since`` — only return records newer than this sequence number (for cheap
    incremental polling). ``level`` — minimum severity (INFO/WARNING/ERROR).
    ``limit`` — cap on returned records (most recent kept).
    """
    buf = logbuffer.get_log_buffer()
    limit = max(1, min(int(limit), 5000))
    logs = buf.records(since=int(since), min_level=logbuffer.level_to_no(level), limit=limit)
    last_seq = logs[-1]["seq"] if logs else int(since)
    return {"logs": logs, "last_seq": last_seq}
