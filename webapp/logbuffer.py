"""In-memory ring buffer of recent log records, surfaced at ``GET /api/logs``.

So the original cause of a problem (e.g. "Output canvas: 11194×14127 … mosaic"
right before an OOM, or a stack ValueError) is visible in the app instead of
only in ``docker logs`` / ``dmesg``. A single bounded handler is attached to the
root logger at startup; it keeps the last N records in memory (nothing is
written to disk — history beyond the buffer lives in the container's stdout).
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from datetime import UTC, datetime
from typing import Any

DEFAULT_CAPACITY = 3000

_LEVELS = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}


class RingBufferLogHandler(logging.Handler):
    """A logging handler that keeps the most recent records in a deque."""

    def __init__(self, capacity: int = DEFAULT_CAPACITY) -> None:
        super().__init__()
        self._buf: deque[dict[str, Any]] = deque(maxlen=capacity)
        self._lock = threading.Lock()
        self._seq = 0

    def emit(self, record: logging.LogRecord) -> None:  # noqa: D102
        try:
            message = record.getMessage()
            if record.exc_info:
                message += "\n" + self.formatException(record.exc_info)
            entry = {
                "ts": datetime.fromtimestamp(record.created, UTC)
                .strftime("%Y-%m-%dT%H:%M:%SZ"),
                "level": record.levelname,
                "levelno": record.levelno,
                "logger": record.name,
                "message": message,
            }
            with self._lock:
                self._seq += 1
                entry["seq"] = self._seq
                self._buf.append(entry)
        except Exception:  # noqa: BLE001 — logging must never raise
            self.handleError(record)

    def records(
        self, *, since: int = 0, min_level: int = 0, limit: int = 1000,
    ) -> list[dict[str, Any]]:
        with self._lock:
            items = list(self._buf)
        out = [
            e for e in items
            if e["seq"] > since and e["levelno"] >= min_level
        ]
        return out[-limit:]


_buffer: RingBufferLogHandler | None = None


def get_log_buffer() -> RingBufferLogHandler:
    global _buffer
    if _buffer is None:
        _buffer = RingBufferLogHandler()
    return _buffer


def install(min_level: int = logging.INFO) -> RingBufferLogHandler:
    """Attach the ring buffer to the root logger (idempotent)."""
    buf = get_log_buffer()
    buf.setLevel(min_level)
    root = logging.getLogger()
    if buf not in root.handlers:
        root.addHandler(buf)
    return buf


def level_to_no(level: str | None) -> int:
    if not level:
        return 0
    return _LEVELS.get(level.upper(), 0)
