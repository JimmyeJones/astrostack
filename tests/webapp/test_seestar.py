"""Seestar integration: telemetry parsing, JSON-RPC client, discovery, gating."""

from __future__ import annotations

import json
import socket
import threading

import pytest

from webapp.seestar import discovery, telemetry
from webapp.seestar.client import SeestarClient, SeestarError
from webapp.seestar.manager import collect_telemetry


# --------------------------------------------------------------------------- #
# telemetry.normalize
# --------------------------------------------------------------------------- #

def test_normalize_full_payload():
    device_state = {
        "device": {"name": "Seestar S50", "firmware_ver_string": "4.02"},
        "pi_status": {"temp": 41.5, "battery_capacity": 88, "charger_status": "Charging"},
        "storage": {"storage_volume": [{"freeMB": 12000, "totalMB": 30000}]},
    }
    view_state = {"View": {"state": "working", "mode": "star", "target_name": "M 42",
                           "stage": "Stack", "Stack": {"stacked_frame": 42, "dropped_frame": 3}}}
    equ = {"ra": 5.6, "dec": -5.4}

    t = telemetry.normalize(device_state, view_state, equ)
    assert t["model"] == "Seestar S50"
    assert t["firmware"] == "4.02"
    assert t["temp_c"] == 41.5
    assert t["battery_pct"] == 88
    assert t["charging"] is True
    assert t["free_storage_mb"] == 12000
    assert t["target_name"] == "M 42"
    assert t["stacked_frames"] == 42
    assert t["dropped_frames"] == 3
    assert t["ra_hours"] == 5.6 and t["dec_deg"] == -5.4
    assert t["raw"]["view_state"] == view_state


def test_normalize_tolerates_empty_and_partial():
    t = telemetry.normalize({}, {}, {})
    assert t["battery_pct"] is None
    assert t["target_name"] is None
    assert t["stacked_frames"] is None
    # Discharging → not charging.
    t2 = telemetry.normalize({"pi_status": {"charger_status": "Discharging"}}, {}, {})
    assert t2["charging"] is False


# --------------------------------------------------------------------------- #
# SeestarClient against a fake TCP server
# --------------------------------------------------------------------------- #

class _FakeSeestar:
    """Minimal newline-delimited JSON-RPC server speaking the Seestar dialect."""

    def __init__(self, responses: dict):
        self.responses = responses
        self.received: list[dict] = []
        self._srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._srv.bind(("127.0.0.1", 0))
        self._srv.listen(1)
        self.port = self._srv.getsockname()[1]
        self._stop = False
        self._thread = threading.Thread(target=self._serve, daemon=True)

    def start(self):
        self._thread.start()

    def _serve(self):
        try:
            conn, _ = self._srv.accept()
        except OSError:
            return
        with conn:
            # Unsolicited event push (no id) before any request.
            conn.sendall((json.dumps({"Event": "PiStatus", "battery": 50}) + "\r\n").encode())
            buf = b""
            while not self._stop:
                try:
                    data = conn.recv(4096)
                except OSError:
                    break
                if not data:
                    break
                buf += data
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    msg = json.loads(line)
                    self.received.append(msg)
                    result = self.responses.get(msg["method"], {})
                    conn.sendall((json.dumps({"id": msg["id"], "result": result}) + "\r\n").encode())

    def stop(self):
        self._stop = True
        try:
            self._srv.close()
        except OSError:
            pass


@pytest.fixture
def fake_seestar():
    server = _FakeSeestar(responses={
        "get_device_state": {"device": {"name": "S50"}},
        "get_view_state": {"View": {"mode": "star"}},
        "scope_get_equ_coord": {"ra": 1.0, "dec": 2.0},
        "iscope_start_view": {"code": 0},
    })
    server.start()
    yield server
    server.stop()


def test_client_rpc_roundtrip_and_event(fake_seestar):
    c = SeestarClient("127.0.0.1", fake_seestar.port)
    c.connect()
    try:
        assert c.is_connected
        assert c.get_device_state()["device"]["name"] == "S50"
        assert c.get_view_state()["View"]["mode"] == "star"
        assert c.get_equ_coord()["ra"] == 1.0
        # The unsolicited event was captured.
        assert c.last_event.get("Event") == "PiStatus"
    finally:
        c.disconnect()
    assert not c.is_connected


def test_connect_sends_udp_intro(fake_seestar, monkeypatch):
    # The scope expects a UDP intro on :4720 before it serves the TCP channel.
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp.bind(("127.0.0.1", 0))
    udp.settimeout(2.0)
    monkeypatch.setattr("webapp.seestar.client._UDP_INTRO_PORT", udp.getsockname()[1])

    c = SeestarClient("127.0.0.1", fake_seestar.port)
    c.connect()
    try:
        data, _ = udp.recvfrom(1024)
        assert json.loads(data)["method"] == "scan_iscope"
    finally:
        c.disconnect()
        udp.close()


def test_client_goto_sends_expected_payload(fake_seestar):
    c = SeestarClient("127.0.0.1", fake_seestar.port)
    c.connect()
    try:
        c.goto(5.5, -10.0, "M 1")
    finally:
        c.disconnect()
    goto = next(m for m in fake_seestar.received if m["method"] == "iscope_start_view")
    assert goto["params"]["target_ra_dec"] == [5.5, -10.0]
    assert goto["params"]["target_name"] == "M 1"
    assert goto["params"]["mode"] == "star"


def test_get_device_state_sends_keys_param(fake_seestar):
    # Real firmware may not reply to get_device_state without a "keys" param.
    c = SeestarClient("127.0.0.1", fake_seestar.port)
    c.connect()
    try:
        c.get_device_state()
    finally:
        c.disconnect()
    req = next(m for m in fake_seestar.received if m["method"] == "get_device_state")
    assert isinstance(req["params"]["keys"], list) and req["params"]["keys"]


def test_rpc_before_connect_raises():
    c = SeestarClient("127.0.0.1", 4700)
    with pytest.raises(SeestarError):
        c.get_device_state()


def test_timeout_on_silent_device_explains_single_controller():
    """A device that accepts the TCP connection but never replies (e.g. the app
    is already connected) should produce an actionable error, not a bare timeout."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    accepted = []
    t = threading.Thread(target=lambda: accepted.append(srv.accept()), daemon=True)
    t.start()
    try:
        c = SeestarClient("127.0.0.1", port)
        c.connect()
        try:
            with pytest.raises(SeestarError) as exc:
                c.get_device_state(timeout=0.5)
            assert c.bytes_received == 0
            assert "no data" in str(exc.value)
            assert "power-cycle" in str(exc.value)
        finally:
            c.disconnect()
    finally:
        srv.close()


# --------------------------------------------------------------------------- #
# collect_telemetry — best-effort, degrades gracefully
# --------------------------------------------------------------------------- #

class _FakeClient:
    def __init__(self, fail: set[str]):
        self.fail = fail

    def get_device_state(self, timeout: float = 0):
        if "ds" in self.fail:
            raise SeestarError("device_state timed out")
        return {"pi_status": {"battery_capacity": 80}}

    def get_view_state(self, timeout: float = 0):
        if "vs" in self.fail:
            raise SeestarError("view_state timed out")
        return {"View": {"mode": "star", "target_name": "M 31"}}

    def get_equ_coord(self, timeout: float = 0):
        if "eq" in self.fail:
            raise SeestarError("equ timed out")
        return {"ra": 1.0, "dec": 2.0}


def test_collect_telemetry_all_ok():
    tel, errors = collect_telemetry(_FakeClient(set()))
    assert errors == []
    assert tel["battery_pct"] == 80 and tel["target_name"] == "M 31"


def test_collect_telemetry_partial_failure_still_returns_data():
    # device_state times out (the reported symptom) but the rest still populate.
    tel, errors = collect_telemetry(_FakeClient({"ds"}))
    assert tel is not None
    assert tel["target_name"] == "M 31"
    assert tel["ra_hours"] == 1.0
    assert tel["battery_pct"] is None
    assert any("device_state" in e for e in errors)


def test_collect_telemetry_total_failure_returns_none():
    tel, errors = collect_telemetry(_FakeClient({"ds", "vs", "eq"}))
    assert tel is None
    assert len(errors) == 3


# --------------------------------------------------------------------------- #
# discovery
# --------------------------------------------------------------------------- #

def test_scan_finds_listening_extra_ip():
    # A listening socket on localhost stands in for a reachable scope.
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    try:
        # Probe that specific port via the private helper.
        assert discovery._probe("127.0.0.1", port) is True
        assert discovery._probe("127.0.0.1", port + 1) in (False, True)  # may or may not be open
    finally:
        srv.close()


def test_scan_empty_when_no_hosts():
    # TEST-NET-3 /31 → at most two TCP probes, none answer; no UDP replies.
    assert discovery.scan("203.0.113.0/31", udp_timeout=0.2) == []


def test_discover_udp_finds_responder(monkeypatch):
    # A fake UDP server that answers scan_iscope stands in for a real scope.
    resp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    resp.bind(("127.0.0.1", 0))
    port = resp.getsockname()[1]

    def serve():
        try:
            data, addr = resp.recvfrom(4096)
            assert json.loads(data)["method"] == "scan_iscope"
            resp.sendto(json.dumps({"name": "Seestar S50"}).encode(), addr)
        except OSError:
            pass

    threading.Thread(target=serve, daemon=True).start()
    monkeypatch.setattr("webapp.seestar.discovery._UDP_PORT", port)
    monkeypatch.setattr("webapp.seestar.discovery._broadcast_addrs", lambda subnet: ["127.0.0.1"])
    try:
        found = discovery.discover_udp(timeout=1.0)
        assert "127.0.0.1" in found
        assert found["127.0.0.1"].get("name") == "Seestar S50"
    finally:
        resp.close()


# --------------------------------------------------------------------------- #
# router gating (manager idles because seestar_enabled defaults False)
# --------------------------------------------------------------------------- #

def test_devices_endpoint_disabled_by_default(client):
    r = client.get("/api/seestar/devices")
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is False
    assert body["control_enabled"] is False
    assert body["devices"] == []


def test_scan_and_control_blocked_when_disabled(client):
    assert client.post("/api/seestar/scan").status_code == 409
    assert client.post("/api/seestar/1.2.3.4/goto",
                       json={"ra_hours": 1, "dec_deg": 2}).status_code == 409


def test_control_blocked_when_only_monitoring_enabled(client):
    # Enable monitoring with a tiny no-host subnet so the background scan is a no-op.
    client.put("/api/settings", json={
        "seestar_enabled": True, "seestar_scan_subnet": "203.0.113.0/31",
    })
    assert client.post("/api/seestar/scan").status_code == 200
    # Control still gated.
    r = client.post("/api/seestar/1.2.3.4/park")
    assert r.status_code == 409
    client.put("/api/settings", json={"seestar_enabled": False})


@pytest.mark.parametrize("ra_hours,dec_deg", [
    (-0.01, 0),      # ra below 0
    (24, 0),         # ra at/above 24 is out of range (hours are [0, 24))
    (24.5, 0),
    (0, 90.01),      # dec above 90
    (0, -90.01),     # dec below -90
])
def test_goto_rejects_out_of_range_coordinates(client, ra_hours, dec_deg):
    # Malformed coordinates must be rejected before they'd ever reach the
    # telescope's RPC, regardless of whether control is enabled.
    r = client.post("/api/seestar/1.2.3.4/goto",
                     json={"ra_hours": ra_hours, "dec_deg": dec_deg})
    assert r.status_code == 422


def test_goto_accepts_boundary_coordinates(client):
    # 0 <= ra_hours < 24 and -90 <= dec_deg <= 90 are valid; with control
    # disabled the request still gets past validation and is gated at 409.
    r = client.post("/api/seestar/1.2.3.4/goto",
                     json={"ra_hours": 0, "dec_deg": 90})
    assert r.status_code == 409
    r = client.post("/api/seestar/1.2.3.4/goto",
                     json={"ra_hours": 23.999, "dec_deg": -90})
    assert r.status_code == 409
