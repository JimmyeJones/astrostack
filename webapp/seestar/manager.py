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

import logging
import threading
import time
from typing import Any, Callable

from webapp.config import Settings
from webapp.seestar import discovery, telemetry
from webapp.seestar.client import SeestarClient, SeestarError

log = logging.getLogger(__name__)

_IDLE_SLEEP = 5.0   # how often the loops re-check settings while disabled
_POLL_TIMEOUT = 6.0  # per-call RPC timeout while polling (keeps the loop snappy)
_RECONNECT_CAP_S = 300.0  # ceiling on the per-scope reconnect backoff


def _reconnect_delay_s(fails: int, base: float, cap: float) -> float:
    """Capped exponential backoff for reconnect attempts: ``base·2^(fails-1)``,
    clamped to ``[base, cap]``. ``fails`` is the count of *consecutive* failed
    reconnects (≥1); 0 or fewer means no wait. Keeps a genuinely-gone scope from
    being hammered every poll cycle while a briefly-dropped one recovers fast."""
    if fails <= 0:
        return 0.0
    delay = base * (2 ** (fails - 1))
    return min(max(delay, base), cap)


def collect_telemetry(client: SeestarClient) -> tuple[dict[str, Any] | None, list[str]]:
    """Best-effort telemetry: query each endpoint independently so an
    unsupported/slow method on one firmware doesn't blank the whole dashboard.
    Returns ``(telemetry | None, errors)`` — None only if *every* call failed."""
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
    return telemetry.normalize(ds or {}, vs or {}, eq or {}), errors


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
        self._scan_now.set()
        with self._lock:
            for client in self._clients.values():
                client.disconnect()
            self._clients.clear()

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
            self._clear_backoff_locked(ip)
            dev = self._devices.get(ip)
            if dev is not None:
                dev["connected"] = False
                dev["reconnecting"] = False
        if client is not None:
            client.disconnect()

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
                return client.park()
        except (KeyError, ValueError) as exc:
            raise SeestarError(f"bad parameters for '{action}': {exc}") from exc
        raise SeestarError(f"unknown action '{action}'")

    # ---- internals --------------------------------------------------------

    def _ensure_client(self, ip: str) -> SeestarClient:
        with self._lock:
            client = self._clients.get(ip)
            if client is not None and client.is_connected:
                return client
            client = SeestarClient(ip)
            self._clients[ip] = client
            self._last_ok.pop(ip, None)  # re-log telemetry state after a fresh connect
        client.connect()  # may raise SeestarError → surfaced to caller
        with self._lock:
            dev = self._devices.setdefault(ip, _new_device(ip))
            dev["connected"] = True
            dev["reconnecting"] = False
            dev["error"] = None
            self._clear_backoff_locked(ip)
        return client

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
                time.sleep(_IDLE_SLEEP)
                continue
            with self._lock:
                items = list(self._clients.items())
            base = float(max(2, int(settings.seestar_poll_interval_s)))
            for ip, client in items:
                if not self._poll_reconnect(ip, client, base):
                    continue
                tel, errors = collect_telemetry(client)
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
                    detail = "device not serving telemetry (port 4700 returned no data)"
                    if self._last_ok.get(ip) is not False:
                        log.info("seestar %s: connected but %s", ip, detail)
                    self._last_ok[ip] = False
                    self._mark_error(ip, detail)
            time.sleep(max(2, int(settings.seestar_poll_interval_s)))

    def _teardown_all(self) -> None:
        with self._lock:
            clients = list(self._clients.values())
            self._clients.clear()
            self._reconnect_fails.clear()
            self._reconnect_at.clear()
            for dev in self._devices.values():
                dev["connected"] = False
                dev["reconnecting"] = False
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
    }


def _utc_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
