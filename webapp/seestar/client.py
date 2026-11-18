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

import contextlib
import json
import logging
import socket
import threading
import time
from typing import Any

from webapp.seestar.keyfile import KeyFileError, RsaPrivateKey, sign_challenge

log = logging.getLogger(__name__)

DEFAULT_PORT = 4700
_CONNECT_TIMEOUT = 5.0
_RPC_TIMEOUT = 10.0
# Before the TCP control channel will answer, the Seestar expects a UDP "intro"
# broadcast on port 4720 (this is what the seestar_alp client sends on connect).
# Without it some firmware accepts the TCP socket but never replies to anything.
_UDP_INTRO_PORT = 4720
_UDP_INTRO_MSG = {"id": 1, "method": "scan_iscope", "params": ""}
# Sub-states get_device_state should return. Real firmware expects a "keys"
# param and may not reply at all if it's missing (seen as an RPC timeout), so
# we always send it — matching the seestar_alp reference client.
_DEFAULT_STATE_KEYS = ["device", "setting", "pi_status", "storage"]

# The firmware 7.18+ handshake (``SeestarClient.handshake``) ends in one of
# these. They are what ``/api/seestar/devices`` reports as a device's ``auth``.
AUTH_VERIFIED = "verified"        # the scope accepted our signature
AUTH_NOT_NEEDED = "not_needed"    # firmware older than 7.18: no handshake exists
AUTH_KEY_NEEDED = "key_needed"    # the scope asks for one and no key is installed
AUTH_REJECTED = "rejected"        # the scope refused the signature (wrong key)
AUTH_FAILED = "failed"            # no usable answer (timeout, dropped link, odd reply)
#: ``get_verify_str`` on firmware without the gate: "method not found".
_CODE_METHOD_NOT_FOUND = 103


class SeestarError(RuntimeError):
    """A Seestar RPC call failed or the device is unreachable."""


def _send_udp_intro(host: str) -> None:
    """Fire-and-forget UDP intro that prompts the scope to start serving its
    TCP control channel. Best-effort: failures (no route, no listener) are
    swallowed — they don't stop the TCP attempt that follows."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.sendto(json.dumps(_UDP_INTRO_MSG).encode("utf-8"),
                        (host, _UDP_INTRO_PORT))
        log.debug("seestar %s: sent UDP intro on :%d", host, _UDP_INTRO_PORT)
    except OSError as exc:
        log.debug("seestar %s: UDP intro failed: %s", host, exc)


class _Pending:
    __slots__ = ("event", "result", "error", "reply")

    def __init__(self) -> None:
        self.event = threading.Event()
        self.result: Any = None
        self.error: str | None = None
        self.reply: dict[str, Any] = {}  # the whole message, ``code`` and all


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
        self._rx_bytes = 0  # total bytes received since connect (silence detector)

    # ---- lifecycle --------------------------------------------------------

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def bytes_received(self) -> int:
        return self._rx_bytes

    def connect(self) -> None:
        with self._lock:
            if self._connected:
                return
            # Reconnect hygiene: a prior connection may have dropped — the read
            # loop sets ``_connected = False`` on its way out but leaves the dead
            # socket and any in-flight replies behind. Tear those down before we
            # open a fresh socket, so a flaky Wi-Fi link (the manager's poll loop
            # re-``connect()``s a disconnected client every cycle) doesn't leak a
            # file descriptor and a stale pending reply on every reconnect.
            self._teardown_locked()
            _send_udp_intro(self.host)
            sock = socket.create_connection((self.host, self.port), _CONNECT_TIMEOUT)
            sock.settimeout(None)
            self._sock = sock
            self._connected = True
            self._rx_bytes = 0
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
            self._teardown_locked()

    def _teardown_locked(self) -> None:
        """Close the current socket and fail any in-flight replies. The caller
        must hold ``self._lock``. Idempotent — safe to call when already torn
        down (e.g. from ``connect()`` after a dropped link). Does not touch
        ``self._connected``/``self._stop``; the caller owns that transition."""
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
                self._rx_bytes += len(chunk)
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
            p.reply = msg
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
        pending = self._call(method, params, timeout)
        if pending.error is not None:
            raise SeestarError(f"{self.host}: '{method}' error: {pending.error}")
        return pending.result

    def _rpc_reply(self, method: str, params: Any = None,
                   timeout: float = _RPC_TIMEOUT) -> dict[str, Any]:
        """The whole reply, error or not — for the handshake, which branches on
        the firmware's ``code`` (103 = method not found). Raises only when no
        reply arrives."""
        pending = self._call(method, params, timeout)
        if pending.error == "disconnected" and not pending.reply:
            raise SeestarError(f"{self.host}: '{method}' error: disconnected")
        return pending.reply

    def _call(self, method: str, params: Any, timeout: float) -> _Pending:
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
            raise SeestarError(f"{self.host}: '{method}' timed out{self._timeout_hint()}")
        return pending

    def _timeout_hint(self) -> str:
        """Turn a bare timeout into a diagnosis based on what (if anything) the
        device has sent us since connecting."""
        if self._rx_bytes == 0:
            return (" — connected but the device sent no data at all. Either another "
                    "controller holds the session (close the Seestar phone app), or "
                    "the scope is in standby / mid firmware-update / has the local API "
                    "disabled by firmware. Try: close the app, fully power-cycle the "
                    "scope (let any update finish), and confirm this IP is the Seestar.")
        if self.last_event:
            return (" — the device is sending data (events) but did not answer this "
                    "command. It may be busy or this method isn't supported on its "
                    "firmware.")
        return ""

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

    # ---- the firmware 7.18+ handshake (⭐ Seestar-page upgrade, slice 2) ----

    def handshake(self, key: RsaPrivateKey | None,
                  timeout: float = _RPC_TIMEOUT) -> str:
        """Prove to the scope that we hold the interop key, so it answers our
        commands: ``get_verify_str`` → sign the challenge (RSA PKCS#1 v1.5,
        SHA-1) → ``verify_client {sign, data}`` → ``pi_is_verified``, exactly
        the sequence Seestar Studio verified on the owner's S30. Code 103 on the
        first call means firmware too old to have the gate. With no key the
        first call is still made — it is how we learn whether one is needed —
        and nothing more is sent. Never raises; returns one of the ``AUTH_*``
        values. Nothing about the key or the signature is logged."""
        try:
            reply = self._rpc_reply("get_verify_str", "verify", timeout)
        except SeestarError as exc:
            log.info("seestar %s: handshake got no answer (%s)", self.host, exc)
            return AUTH_FAILED
        code = reply.get("code")
        if code == _CODE_METHOD_NOT_FOUND:
            return AUTH_NOT_NEEDED
        result = reply.get("result")
        challenge = result.get("str") if isinstance(result, dict) else None
        if code not in (0, None) or reply.get("error") or not isinstance(challenge, str) \
                or not challenge:
            log.info("seestar %s: handshake challenge unusable (code=%s)", self.host, code)
            return AUTH_FAILED
        if key is None:
            return AUTH_KEY_NEEDED
        try:
            signature = sign_challenge(key, challenge)
        except KeyFileError:
            return AUTH_REJECTED  # a key too short to sign with can never pass
        try:
            verdict = self._rpc_reply(
                "verify_client", {"sign": signature, "data": challenge}, timeout)
        except SeestarError as exc:
            log.info("seestar %s: verify_client got no answer (%s)", self.host, exc)
            return AUTH_FAILED
        if verdict.get("code") not in (0, None) or verdict.get("error"):
            log.info("seestar %s: the scope refused the key (code=%s)",
                     self.host, verdict.get("code"))
            return AUTH_REJECTED
        # Studio sends it and does not wait on the answer; neither do we.
        with contextlib.suppress(SeestarError):
            self._rpc_reply("pi_is_verified", "verify", timeout)
        log.info("seestar %s: key accepted — the scope will answer commands", self.host)
        return AUTH_VERIFIED
