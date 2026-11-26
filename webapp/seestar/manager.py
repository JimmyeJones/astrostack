"""Background manager for Seestar devices.

Owns the live picture of every scope on the LAN: it periodically re-scans for
devices, keeps a connected :class:`SeestarClient` per reachable scope, and polls
each one for telemetry on a short interval so the dashboard always has a fresh
snapshot to serve. Runs on its own daemon threads (a scan loop + a poll loop) so
it never blocks the single job worker — the same pattern as :class:`Watcher`.

Everything reads the *current* settings each cycle (via the ``get_settings``
callback), so toggling Seestar on/off or changing the subnet at runtime takes
effect without a restart. When disabled it tears down all connections and idles.
"""

from __future__ import annotations

import http.client
import logging
import threading
import time
import urllib.parse
from typing import Any, Callable

from webapp.config import Settings
from webapp.seestar import discovery, keyfile, telemetry
from webapp.seestar.client import (
    AUTH_FAILED,
    AUTH_KEY_NEEDED,
    AUTH_REJECTED,
    FOCUSER_RANGE,
    SeestarClient,
    SeestarError,
)

log = logging.getLogger(__name__)

_IDLE_SLEEP = 5.0   # how often the loops re-check settings while disabled
_POLL_TIMEOUT = 6.0  # per-call RPC timeout while polling (keeps the loop snappy)
_RECONNECT_CAP_S = 300.0  # ceiling on the per-scope reconnect backoff
#: Ceiling on how long :meth:`SeestarManager.stop` may block waiting for each
#: loop thread to return. Both loops wait on the stop event rather than sleeping,
#: so an *idle* manager joins in microseconds; this budget only bites when a loop
#: is mid-RPC (:data:`_POLL_TIMEOUT` per telemetry call, three per scope) or
#: mid-subnet-scan, where app shutdown must not block indefinitely either. It is
#: deliberately a ceiling and not a guarantee — a loop polling several silent
#: scopes can outlast any fixed number — so a thread still alive at the deadline
#: is logged and left alone; both are daemons and do exit.
_STOP_JOIN_TIMEOUT_S = 10.0
#: How soon a handshake that got no usable answer is tried again on the same
#: connection. Every other outcome stands until the link or the key changes.
_AUTH_RETRY_S = 60.0
#: The scope's own picture list (``get_albums``) changes at most once a stacked
#: frame, so it is asked for no more often than this — Seestar Studio's pace.
_ALBUMS_EVERY_S = 10.0
#: The scope's HTTP file server, which serves its stacked pictures.
SCOPE_HTTP_PORT = 80
_IMAGE_TIMEOUT_S = 8.0
#: Ceilings on one picture fetched from the scope. A Seestar thumbnail is tens
#: of KB and a full stacked JPEG a few MB; anything bigger is not one.
_IMAGE_MAX_BYTES = {"thumb": 2 * 1024 * 1024, "full": 32 * 1024 * 1024}


#: Why a connected scope serves nothing, in plain words, when the handshake
#: already says why (firmware 7.18+ answers commands only after it).
_NO_TELEMETRY = {
    AUTH_KEY_NEEDED: ("this Seestar's firmware answers only after AstroStack proves it holds "
                      "the Seestar key — add the key file in Settings → This device"),
    AUTH_REJECTED: ("this Seestar refused the key file in Settings — it isn't the key this "
                    "scope's firmware expects; upload the right one in Settings → This device"),
}


def _reconnect_delay_s(fails: int, base: float, cap: float) -> float:
    """Capped exponential backoff for reconnect attempts: ``base·2^(fails-1)``,
    clamped to ``[base, cap]``. ``fails`` is the count of *consecutive* failed
    reconnects (≥1); 0 or fewer means no wait. Keeps a genuinely-gone scope from
    being hammered every poll cycle while a briefly-dropped one recovers fast."""
    if fails <= 0:
        return 0.0
    delay = base * (2 ** (fails - 1))
    return min(max(delay, base), cap)


def collect_telemetry(client: SeestarClient, albums: dict | None = None,
                      ) -> tuple[dict[str, Any] | None, list[str]]:
    """Best-effort telemetry: query each endpoint independently so an
    unsupported/slow method on one firmware doesn't blank the whole dashboard.
    Returns ``(telemetry | None, errors)`` — None only if *every* core call
    failed. ``albums`` is the caller's latest ``get_albums`` reply (it is
    polled on its own, slower clock). ``get_disk_volume`` is an extra: a
    firmware without it costs the storage figure, never an error line."""
    errors: list[str] = []

    def safe(label: str, fn):  # noqa: ANN001
        try:
            return fn()
        except SeestarError as exc:
            errors.append(f"{label}: {exc}")
            log.debug("seestar telemetry %s failed: %s", label, exc)
            return None

    ds = safe("device_state", lambda: client.get_device_state(timeout=_POLL_TIMEOUT))
    vs = safe("view_state", lambda: client.get_view_state(timeout=_POLL_TIMEOUT))
    eq = safe("equ_coord", lambda: client.get_equ_coord(timeout=_POLL_TIMEOUT))
    if ds is None and vs is None and eq is None:
        return None, errors
    try:
        disk = client.get_disk_volume(timeout=_POLL_TIMEOUT)
    except SeestarError as exc:
        log.debug("seestar telemetry disk_volume failed: %s", exc)
        disk = {}
    return telemetry.normalize(ds or {}, vs or {}, eq or {}, disk, albums), errors


def fetch_scope_file(host: str, path: str, max_bytes: int, port: int = SCOPE_HTTP_PORT,
                     timeout: float = _IMAGE_TIMEOUT_S) -> bytes | None:
    """GET one picture from the scope's HTTP file server. Read-only and
    bounded: a timeout, a byte ceiling (a longer body is refused, not cut), and
    only a JPEG or PNG is returned. Never raises; None on any failure."""
    conn = http.client.HTTPConnection(host, port, timeout=timeout)
    try:
        conn.request("GET", "/" + urllib.parse.quote(path), headers={"Host": "seestar"})
        resp = conn.getresponse()
        if resp.status != 200:
            return None
        length = resp.getheader("Content-Length")
        if length is not None and length.isdigit() and int(length) > max_bytes:
            return None
        body = resp.read(max_bytes + 1)
    except (OSError, http.client.HTTPException) as exc:
        log.debug("seestar %s: picture fetch failed: %s", host, exc)
        return None
    finally:
        conn.close()
    if len(body) > max_bytes:
        return None
    if not (body.startswith(b"\xff\xd8") or body.startswith(b"\x89PNG")):
        return None
    return body


class SeestarManager:
    def __init__(
        self,
        get_settings: Callable[[], Settings],
        now_fn: Callable[[], float] | None = None,
    ) -> None:
        self._get_settings = get_settings
        self._now = now_fn or time.monotonic
        self._lock = threading.Lock()
        self._devices: dict[str, dict[str, Any]] = {}
        self._clients: dict[str, SeestarClient] = {}
        self._last_ok: dict[str, bool] = {}  # per-ip telemetry state, for transition logs
        # Per-ip reconnect backoff: consecutive failure count and the earliest
        # monotonic time to try again, so a dropped scope isn't re-dialled every
        # poll cycle (see ``_reconnect_delay_s``).
        self._reconnect_fails: dict[str, int] = {}
        self._reconnect_at: dict[str, float] = {}
        # Per-ip handshake record: (the client it ran on, outcome, the key's
        # modulus or None, when). A new connection, a changed key or a stale
        # failure makes it due again (``_auth_due``). One lock serialises the
        # handshakes, so the scan and poll loops never sign two challenges on
        # one socket at once.
        self._auth: dict[str, tuple[SeestarClient, str, int | None, float]] = {}
        self._handshake_lock = threading.Lock()
        # Per-ip (monotonic time, last get_albums reply), on its own slower clock.
        self._albums: dict[str, tuple[float, dict]] = {}
        # Per-ip (scope path, bytes) of the last thumbnail served, so a page that
        # re-asks for an unchanged picture costs the scope nothing. One per scope.
        self._thumbs: dict[str, tuple[str, bytes]] = {}
        self.http_port = SCOPE_HTTP_PORT
        self._stop = threading.Event()
        self._scan_now = threading.Event()
        self._scan_thread: threading.Thread | None = None
        self._poll_thread: threading.Thread | None = None

    # ---- lifecycle --------------------------------------------------------

    def start(self) -> None:
        self._stop.clear()
        self._scan_thread = threading.Thread(
            target=self._scan_loop, name="seestar-scan", daemon=True)
        self._poll_thread = threading.Thread(
            target=self._poll_loop, name="seestar-poll", daemon=True)
        self._scan_thread.start()
        self._poll_thread.start()
        log.info("seestar manager started")

    def stop(self) -> None:
        self._stop.set()
        self._scan_now.set()  # wakes the scan loop out of its interval wait
        with self._lock:
            for client in self._clients.values():
                client.disconnect()
            self._clients.clear()
        # Then *wait* for the loops, so a returned ``stop()`` means stopped.
        # Setting the flag alone was a false contract: nothing joined, and the
        # poll loop only read the flag at the top of its next iteration, so a
        # torn-down manager kept polling for up to ``_IDLE_SLEEP`` seconds. In
        # the test suite — a fresh app, and a fresh manager, per test — that
        # left two or three ``seestar-poll`` threads from already-closed apps
        # running underneath every webapp test.
        current = threading.current_thread()
        for thread in (self._poll_thread, self._scan_thread):
            if thread is None or thread is current or not thread.is_alive():
                continue
            thread.join(_STOP_JOIN_TIMEOUT_S)
            if thread.is_alive():
                log.warning("seestar %s thread still running %.0fs after stop; "
                            "it is a daemon and will exit on its own",
                            thread.name, _STOP_JOIN_TIMEOUT_S)

    # ---- public API (used by the router) ---------------------------------

    def snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(d) for d in self._devices.values()]

    def request_scan(self) -> None:
        self._scan_now.set()

    def connect(self, ip: str) -> None:
        self._ensure_client(ip)

    def disconnect(self, ip: str) -> None:
        with self._lock:
            client = self._clients.pop(ip, None)
            self._last_ok.pop(ip, None)
            self._auth.pop(ip, None)
            self._albums.pop(ip, None)
            self._thumbs.pop(ip, None)
            self._clear_backoff_locked(ip)
            dev = self._devices.get(ip)
            if dev is not None:
                dev["connected"] = False
                dev["reconnecting"] = False
                dev["auth"] = None
        if client is not None:
            client.disconnect()

    def latest_image(self, ip: str, kind: str = "thumb") -> bytes | None:
        """The newest picture the scope holds (``kind`` "thumb" or "full"),
        fetched from its own HTTP server, or None. Only a scope this manager
        already knows is ever contacted, and only at the path the scope itself
        reported — never one from the caller."""
        if kind not in _IMAGE_MAX_BYTES:
            raise ValueError(f"unknown picture kind {kind!r}")
        with self._lock:
            dev = self._devices.get(ip)
            tel = dev.get("telemetry") if dev is not None else None
            info = tel.get("latest_image") if isinstance(tel, dict) else None
            cached = self._thumbs.get(ip)
        if not isinstance(info, dict) or not isinstance(info.get(kind), str):
            return None
        path = info[kind]
        if kind == "thumb" and cached is not None and cached[0] == path:
            return cached[1]
        body = fetch_scope_file(ip, path, _IMAGE_MAX_BYTES[kind], port=self.http_port)
        if body is not None and kind == "thumb":
            with self._lock:
                self._thumbs[ip] = (path, body)
        return body

    def control(self, ip: str, action: str, params: dict[str, Any] | None = None) -> Any:
        """Run a control command on a device. Caller is responsible for having
        checked ``seestar_control_enabled`` first."""
        client = self._ensure_client(ip)
        params = params or {}
        try:
            if action == "goto":
                return client.goto(
                    float(params["ra_hours"]), float(params["dec_deg"]),
                    str(params.get("target_name", "AstroStack")),
                )
            if action == "start":
                return client.start_view(str(params.get("mode", "star")))
            if action == "stop":
                return client.stop_view()
            if action == "park":
                return client.park(self._current_equ_mode(client))
            if action == "stop_stack":
                return client.stop_stack()
            if action == "resume":
                return client.resume_stack()
            if action == "autofocus":
                return client.autofocus()
            if action == "focus":
                return self._nudge_focus(client, int(params["steps"]))
            if action == "solve":
                return client.plate_solve()
        except (KeyError, ValueError, TypeError) as exc:
            raise SeestarError(f"bad parameters for '{action}': {exc}") from exc
        raise SeestarError(f"unknown action '{action}'")

    @staticmethod
    def _current_equ_mode(client: SeestarClient) -> bool | None:
        """The mount mode the scope is in *now*, read fresh — ``scope_park``
        sets the mode it is given, so parking with a stale or guessed value
        would quietly switch an EQ-mode scope to alt-az (or back). ``None``
        when the firmware does not say, and the bare park is sent instead."""
        mode = client.get_mount(timeout=_POLL_TIMEOUT).get("equ_mode")
        return mode if isinstance(mode, bool) else None

    @staticmethod
    def _nudge_focus(client: SeestarClient, steps: int) -> dict[str, int]:
        """Move the focuser ``steps`` from where it is now. The firmware only
        takes an absolute position, so the current one is read first, fresh;
        an unknown position refuses rather than guessing."""
        current = client.get_focuser_position(timeout=_POLL_TIMEOUT)
        if current is None:
            raise SeestarError("the scope didn't say where its focuser is — try again")
        target = current + steps
        lo, hi = FOCUSER_RANGE
        if not lo <= target <= hi:
            raise SeestarError(
                f"the focuser is at {current}; moving {steps:+d} would leave its {lo}–{hi} range")
        client.move_focuser(target)
        return {"from": current, "to": target}

    # ---- internals --------------------------------------------------------

    def _ensure_client(self, ip: str) -> SeestarClient:
        with self._lock:
            client = self._clients.get(ip)
            live = client is not None and client.is_connected
            if not live:
                client = SeestarClient(ip)
                self._clients[ip] = client
                self._last_ok.pop(ip, None)  # re-log telemetry state after a fresh connect
        if live:
            self._ensure_auth(ip, client)
            return client
        client.connect()  # may raise SeestarError → surfaced to caller
        with self._lock:
            dev = self._devices.setdefault(ip, _new_device(ip))
            dev["connected"] = True
            dev["reconnecting"] = False
            dev["error"] = None
            self._clear_backoff_locked(ip)
        self._ensure_auth(ip, client)
        return client

    # ---- the firmware 7.18+ handshake (⭐ Seestar-page upgrade, slice 2) ----

    def _current_key(self) -> keyfile.RsaPrivateKey | None:
        state_dir = getattr(self._get_settings(), "state_dir", None)
        return keyfile.load_key(state_dir) if state_dir is not None else None

    def _auth_due(self, ip: str, client: SeestarClient,
                  key: keyfile.RsaPrivateKey | None) -> bool:
        record = self._auth.get(ip)
        if record is None or record[0] is not client:
            return True  # never run on this connection
        _, status, key_n, at = record
        if key_n != (key.n if key is not None else None):
            return True  # the key was added, replaced or removed since
        return status == AUTH_FAILED and self._now() - at >= _AUTH_RETRY_S

    def _auth_status(self, ip: str) -> str | None:
        with self._lock:
            record = self._auth.get(ip)
        return record[1] if record is not None else None

    def _ensure_auth(self, ip: str, client: SeestarClient) -> None:
        """Run the handshake on ``client`` when it is due. Best-effort: the
        outcome is recorded on the device (``auth``) and never raised — a scope
        that refuses still serves its broadcast events."""
        key = self._current_key()
        with self._handshake_lock:
            if not client.is_connected or not self._auth_due(ip, client, key):
                return
            status = client.handshake(key, timeout=_POLL_TIMEOUT)
            with self._lock:
                self._auth[ip] = (client, status, key.n if key is not None else None,
                                  self._now())
                if self._clients.get(ip) is client:
                    self._devices.setdefault(ip, _new_device(ip))["auth"] = status

    def _poll_albums(self, ip: str, client: SeestarClient) -> dict:
        """The scope's picture list, asked for at most every
        :data:`_ALBUMS_EVERY_S`; between asks (or when it fails) the last
        answer stands, so the newest-picture line doesn't flicker."""
        now = self._now()
        last = self._albums.get(ip)
        if last is not None and now - last[0] < _ALBUMS_EVERY_S:
            return last[1]
        try:
            albums = client.get_albums(timeout=_POLL_TIMEOUT)
        except SeestarError as exc:
            log.debug("seestar %s: get_albums failed: %s", ip, exc)
            albums = last[1] if last is not None else {}
        self._albums[ip] = (now, albums)
        return albums

    def _poll_reconnect(self, ip: str, client: SeestarClient, base_s: float) -> bool:
        """Reconnect a dropped client with capped exponential backoff. Returns
        True when the client is live and telemetry should be collected this cycle;
        False while backing off, or when the reconnect attempt just failed.

        A live client clears any pending backoff; a fresh failure lengthens it
        (up to :data:`_RECONNECT_CAP_S`) and surfaces a ``reconnecting…`` state so
        a genuinely-gone scope isn't re-dialled every poll cycle."""
        if client.is_connected:
            with self._lock:
                self._clear_backoff_locked(ip)
            return True
        now = self._now()
        if now < self._reconnect_at.get(ip, 0.0):
            return False  # still backing off — leave the scope alone this cycle
        try:
            client.connect()
        except SeestarError as exc:
            fails = self._reconnect_fails.get(ip, 0) + 1
            self._reconnect_fails[ip] = fails
            delay = _reconnect_delay_s(fails, base_s, _RECONNECT_CAP_S)
            self._reconnect_at[ip] = now + delay
            self._mark_reconnecting(ip, str(exc), delay)
            return False
        with self._lock:
            self._clear_backoff_locked(ip)
        return True

    def _clear_backoff_locked(self, ip: str) -> None:
        self._reconnect_fails.pop(ip, None)
        self._reconnect_at.pop(ip, None)

    def _scan_loop(self) -> None:
        while not self._stop.is_set():
            settings = self._get_settings()
            if not settings.seestar_enabled:
                self._teardown_all()
                self._scan_now.wait(_IDLE_SLEEP)
                self._scan_now.clear()
                continue
            try:
                ips = discovery.scan(
                    settings.seestar_scan_subnet,
                    extra_ips=list(settings.seestar_known_ips),
                )
                self._merge_discovered(ips)
                for ip in ips:
                    try:
                        self._ensure_client(ip)  # auto-connect for monitoring
                    except SeestarError as exc:
                        self._mark_error(ip, str(exc))
            except Exception as exc:  # noqa: BLE001 — a scan failure must not kill the loop
                log.warning("seestar scan failed: %s", exc)
            interval = max(30, int(settings.seestar_scan_interval_s))
            self._scan_now.wait(interval)
            self._scan_now.clear()

    def _poll_loop(self) -> None:
        while not self._stop.is_set():
            settings = self._get_settings()
            if not settings.seestar_enabled:
                # ``_stop.wait`` rather than ``time.sleep``: the wait returns the
                # moment ``stop()`` sets the event, so the loop ends when it is
                # asked to instead of at the end of the current nap.
                self._stop.wait(_IDLE_SLEEP)
                continue
            with self._lock:
                items = list(self._clients.items())
            base = float(max(2, int(settings.seestar_poll_interval_s)))
            for ip, client in items:
                try:
                    self._poll_one(ip, client, base)
                except Exception as exc:  # noqa: BLE001 — one scope's failure must not kill the loop
                    # An uncaught error here used to end the thread silently,
                    # leaving every scope's card frozen on its last telemetry
                    # as "connected" until the container restarted.
                    log.warning("seestar %s: poll failed: %s", ip, exc)
                    self._mark_error(ip, f"poll failed: {exc}")
            self._stop.wait(max(2, int(settings.seestar_poll_interval_s)))

    def _poll_one(self, ip: str, client: SeestarClient, base: float) -> None:
        """One poll cycle for one scope: reconnect (with backoff), auth, telemetry."""
        if not self._poll_reconnect(ip, client, base):
            return
        self._ensure_auth(ip, client)
        tel, errors = collect_telemetry(client, self._poll_albums(ip, client))
        if tel is not None:
            self._store_telemetry(ip, tel, error="; ".join(errors) or None)
            if not self._last_ok.get(ip):
                log.info("seestar %s: telemetry OK (model=%s battery=%s%% target=%s)",
                         ip, tel.get("model"), tel.get("battery_pct"),
                         tel.get("target_name"))
            self._last_ok[ip] = True
        else:
            # Connected but the device serves nothing. Expected when the
            # scope's local API is unavailable; an environmental state,
            # not an app error — so log it once, concisely, at INFO.
            detail = _NO_TELEMETRY.get(
                self._auth_status(ip),
                "device not serving telemetry (port 4700 returned no data)")
            if self._last_ok.get(ip) is not False:
                log.info("seestar %s: connected but %s", ip, detail)
            self._last_ok[ip] = False
            self._mark_error(ip, detail)

    def _teardown_all(self) -> None:
        with self._lock:
            clients = list(self._clients.values())
            self._clients.clear()
            self._reconnect_fails.clear()
            self._reconnect_at.clear()
            self._auth.clear()
            self._albums.clear()
            self._thumbs.clear()
            for dev in self._devices.values():
                dev["connected"] = False
                dev["reconnecting"] = False
                dev["auth"] = None
        for client in clients:
            client.disconnect()

    def _merge_discovered(self, ips: list[str]) -> None:
        now = _utc_iso()
        seen = set(ips)
        with self._lock:
            for ip in ips:
                dev = self._devices.setdefault(ip, _new_device(ip))
                dev["reachable"] = True
                dev["last_seen_utc"] = now
            for ip, dev in self._devices.items():
                if ip not in seen:
                    dev["reachable"] = False

    def _store_telemetry(self, ip: str, tel: dict[str, Any], error: str | None = None) -> None:
        with self._lock:
            dev = self._devices.setdefault(ip, _new_device(ip))
            dev["telemetry"] = tel
            dev["connected"] = True
            dev["reconnecting"] = False
            dev["error"] = error
            dev["last_seen_utc"] = _utc_iso()
            for key in ("device_name", "model", "firmware"):
                if tel.get(key):
                    dev[key] = tel[key]

    def _mark_error(self, ip: str, message: str) -> None:
        with self._lock:
            dev = self._devices.setdefault(ip, _new_device(ip))
            dev["error"] = message
            dev["connected"] = False

    def _mark_reconnecting(self, ip: str, message: str, delay_s: float) -> None:
        with self._lock:
            dev = self._devices.setdefault(ip, _new_device(ip))
            dev["connected"] = False
            dev["reconnecting"] = True
            dev["error"] = f"reconnecting… ({message}); next attempt in {int(delay_s)}s"


def _new_device(ip: str) -> dict[str, Any]:
    return {
        "id": ip, "ip": ip, "device_name": None, "model": None, "firmware": None,
        "reachable": False, "connected": False, "reconnecting": False,
        "last_seen_utc": None, "telemetry": None, "error": None,
        # The firmware 7.18+ handshake's outcome — a client.AUTH_* value, or
        # None while not connected / not yet tried.
        "auth": None,
    }


def _utc_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
