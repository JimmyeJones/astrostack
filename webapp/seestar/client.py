"""Seestar JSON-RPC client (unofficial local API, TCP port 4700).

The Seestar speaks newline-delimited JSON-RPC over a raw TCP socket: we send
``{"id": N, "method": ..., "params": ...}\\r\\n`` and read back newline-framed
JSON. Two kinds of inbound message arrive on the same socket:

* **responses** — carry the ``id`` of the request they answer (plus ``result``
  or ``error``);
* **events** — asynchronous push messages (mode changes, stacking progress)
  that have no matching request id.

A background reader thread demultiplexes the two: responses wake the matching
``_rpc`` caller; events are stashed as "latest event" for telemetry.

This API is reverse-engineered (see github.com/smart-underworld/seestar_alp) and
**firmware-fragile** — every method here is best-effort and tolerant of missing
or renamed fields. Nothing in this module should raise on a malformed reply.
"""

from __future__ import annotations

import json
import logging
import socket
import threading
import time
from typing import Any

log = logging.getLogger(__name__)

DEFAULT_PORT = 4700
_CONNECT_TIMEOUT = 5.0
_RPC_TIMEOUT = 10.0
# Sub-states get_device_state should return. Real firmware expects a "keys"
# param and may not reply at all if it's missing (seen as an RPC timeout), so
# we always send it — matching the seestar_alp reference client.
_DEFAULT_STATE_KEYS = ["device", "setting", "pi_status", "storage"]


class SeestarError(RuntimeError):
    """A Seestar RPC call failed or the device is unreachable."""


class _Pending:
    __slots__ = ("event", "result", "error")

    def __init__(self) -> None:
        self.event = threading.Event()
        self.result: Any = None
        self.error: str | None = None


class SeestarClient:
    """A single TCP connection to one Seestar, with a reader thread."""

    def __init__(self, host: str, port: int = DEFAULT_PORT) -> None:
        self.host = host
        self.port = port
        self._sock: socket.socket | None = None
        self._lock = threading.Lock()       # guards _sock + _next_id + send
        self._next_id = 1
        self._pending: dict[int, _Pending] = {}
        self._reader: threading.Thread | None = None
        self._stop = threading.Event()
        self._connected = False
        self.last_event: dict[str, Any] = {}

    # ---- lifecycle --------------------------------------------------------

    @property
    def is_connected(self) -> bool:
        return self._connected

    def connect(self) -> None:
        with self._lock:
            if self._connected:
                return
            sock = socket.create_connection((self.host, self.port), _CONNECT_TIMEOUT)
            sock.settimeout(None)
            self._sock = sock
            self._connected = True
            self._stop.clear()
            self._reader = threading.Thread(
                target=self._read_loop, name=f"seestar-{self.host}", daemon=True
            )
            self._reader.start()
        log.info("seestar %s: connected", self.host)

    def disconnect(self) -> None:
        self._stop.set()
        with self._lock:
            self._connected = False
            if self._sock is not None:
                try:
                    self._sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                try:
                    self._sock.close()
                except OSError:
                    pass
                self._sock = None
            # Wake anyone waiting on an in-flight reply.
            for p in self._pending.values():
                p.error = "disconnected"
                p.event.set()
            self._pending.clear()

    # ---- low-level RPC ----------------------------------------------------

    def _read_loop(self) -> None:
        buf = b""
        sock = self._sock
        try:
            while not self._stop.is_set() and sock is not None:
                chunk = sock.recv(8192)
                if not chunk:
                    break  # peer closed
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    line = line.strip()
                    if line:
                        self._dispatch(line)
        except OSError as exc:
            if not self._stop.is_set():
                log.info("seestar %s: read loop ended (%s)", self.host, exc)
        finally:
            self._connected = False

    def _dispatch(self, line: bytes) -> None:
        raw = line.decode("utf-8", "replace")
        log.debug("seestar %s recv: %s", self.host, raw[:1000])
        try:
            msg = json.loads(raw)
        except ValueError:
            return
        if not isinstance(msg, dict):
            return
        mid = msg.get("id")
        if mid is not None and mid in self._pending:
            p = self._pending.pop(mid)
            if isinstance(msg.get("error"), dict) or msg.get("error"):
                p.error = str(msg.get("error"))
            else:
                p.result = msg.get("result", msg)
            p.event.set()
        elif mid is not None:
            # A reply we have no waiter for (e.g. the heartbeat id, or an id
            # type mismatch). Log it so protocol surprises are diagnosable.
            log.debug("seestar %s: unmatched response id=%r", self.host, mid)
        else:
            # Asynchronous event push — keep the most recent one for telemetry.
            self.last_event = msg

    def _rpc(self, method: str, params: Any = None, timeout: float = _RPC_TIMEOUT) -> Any:
        if not self._connected or self._sock is None:
            raise SeestarError(f"{self.host}: not connected")
        with self._lock:
            mid = self._next_id
            self._next_id += 1
            payload: dict[str, Any] = {"id": mid, "method": method}
            if params is not None:
                payload["params"] = params
            pending = _Pending()
            self._pending[mid] = pending
            try:
                self._sock.sendall((json.dumps(payload) + "\r\n").encode("utf-8"))
            except OSError as exc:
                self._pending.pop(mid, None)
                self._connected = False
                raise SeestarError(f"{self.host}: send failed: {exc}") from exc
        if not pending.event.wait(timeout):
            self._pending.pop(mid, None)
            raise SeestarError(f"{self.host}: '{method}' timed out")
        if pending.error is not None:
            raise SeestarError(f"{self.host}: '{method}' error: {pending.error}")
        return pending.result

    # ---- telemetry --------------------------------------------------------

    def get_device_state(self, keys: list[str] | None = None,
                         timeout: float = _RPC_TIMEOUT) -> dict:
        res = self._rpc("get_device_state",
                        {"keys": keys or _DEFAULT_STATE_KEYS}, timeout)
        return res if isinstance(res, dict) else {}

    def get_view_state(self, timeout: float = _RPC_TIMEOUT) -> dict:
        res = self._rpc("get_view_state", timeout=timeout)
        return res if isinstance(res, dict) else {}

    def get_equ_coord(self, timeout: float = _RPC_TIMEOUT) -> dict:
        res = self._rpc("scope_get_equ_coord", timeout=timeout)
        return res if isinstance(res, dict) else {}

    # ---- control (only used when the caller has gated it on) --------------

    def goto(self, ra_hours: float, dec_deg: float, target_name: str = "AstroStack") -> Any:
        """Slew to a target and begin a stacking view. ``ra_hours`` is RA in
        hours (the Seestar convention), ``dec_deg`` in degrees."""
        return self._rpc("iscope_start_view", {
            "mode": "star",
            "target_ra_dec": [ra_hours, dec_deg],
            "target_name": target_name,
            "lp_filter": False,
        })

    def start_view(self, mode: str = "star") -> Any:
        return self._rpc("iscope_start_view", {"mode": mode})

    def stop_view(self) -> Any:
        return self._rpc("iscope_stop_view")

    def park(self) -> Any:
        return self._rpc("scope_park")
