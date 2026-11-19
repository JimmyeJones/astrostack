"""⭐ Seestar-page upgrade, slice 3 — the read-only monitor.

Shapes follow what Seestar Studio verified on the owner's S30 (firmware 9.75,
``docs/reference/seestar-studio``): storage from ``get_disk_volume``, an idle
view as ``{}`` or a lingering ``cancel``, the newest picture from
``get_albums`` served by the scope's own HTTP server, and a ``setting`` block
that carries the hotspot password and must never reach the browser.
"""

from __future__ import annotations

import http.server
import json
import threading
from types import SimpleNamespace

import pytest

from webapp.seestar import manager as manager_mod
from webapp.seestar import telemetry
from webapp.seestar.client import _DEFAULT_STATE_KEYS, SeestarError
from webapp.seestar.manager import SeestarManager, collect_telemetry, fetch_scope_file

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64 + b"\xff\xd9"

# The sim's get_device_state, with the private blocks real firmware sends.
_DEVICE_STATE = {
    "device": {"product_model": "Seestar S30", "firmware_ver_string": "9.75",
               "sn": "SIM00001", "name": "Seestar-sim"},
    "pi_status": {"battery_capacity": 71, "charge_online": False,
                  "charger_status": "Discharging", "temp": 38.2},
    "setting": {"password": "hotspot-secret", "stack_lenhance": False},
    "station": {"ssid": "HomeWiFi", "ip": "192.0.2.10"},
    "storage": {"is_typec_connected": False},
    "location_lon_lat": [12.5, 55.6],
}
_ALBUMS = {"path": "MyWorks", "list": [{"group_name": "DSO", "files": [
    {"name": "M 31", "count": 40,
     "thn": "M 31/Stacked_40_M 31_10.0s_LP_20261117-220000_thn.jpg"},
    {"name": "M 42", "count": 12,
     "thn": "M 42/M 42_10.0s_LP_20261118-221500_thn.jpg"},
    {"name": "M 42", "count": 12,
     "thn": "M 42/Stacked_12_M 42_10.0s_LP_20261118-221500_thn.jpg"},
    {"name": "evil", "thn": "../../etc/passwd_20991231-235959_thn.jpg"},
]}]}


# ---------------------------------------------------------------------------
# telemetry.normalize — verified field shapes, idle, privacy
# ---------------------------------------------------------------------------


def test_nothing_private_reaches_raw():
    t = telemetry.normalize(_DEVICE_STATE, {}, {})
    blob = json.dumps(t)
    for secret in ("hotspot-secret", "HomeWiFi", "192.0.2.10", "SIM00001", "55.6"):
        assert secret not in blob
    assert t["raw"]["device_state"]["pi_status"]["battery_capacity"] == 71


def test_scrub_drops_password_like_keys_at_any_depth():
    out = telemetry.scrub({"a": [{"wifi_pwd": 1, "ok": 2}], "Password": 3, "b": {"ssid": 4}})
    assert out == {"a": [{"ok": 2}], "b": {}}


def test_device_state_never_asks_for_the_setting_block():
    assert "setting" not in _DEFAULT_STATE_KEYS


def test_storage_comes_from_get_disk_volume_on_9_75():
    t = telemetry.normalize(_DEVICE_STATE, {}, {}, disk={"totalMB": 51854, "freeMB": 35690})
    assert (t["free_storage_mb"], t["total_storage_mb"]) == (35690, 51854)


def test_an_older_storage_volume_list_still_wins():
    ds = {"storage": {"storage_volume": [{"freeMB": 1, "totalMB": 2}]}}
    t = telemetry.normalize(ds, {}, {}, disk={"totalMB": 9, "freeMB": 8})
    assert (t["free_storage_mb"], t["total_storage_mb"]) == (1, 2)


@pytest.mark.parametrize("view_state", [
    {},
    {"View": {}},
    {"View": {"state": "cancel", "mode": "star", "stage": "Stack",
              "target_name": "M 42", "Stack": {"stacked_frame": 30}}},
])
def test_an_idle_or_stopped_view_reads_idle(view_state):
    t = telemetry.normalize({}, view_state, {})
    assert t["state"] == "idle" and t["mode"] is None and t["stage"] is None


def test_a_stopped_view_keeps_its_target_and_count():
    t = telemetry.normalize({}, {"View": {"state": "cancel", "target_name": "M 42",
                                          "Stack": {"stacked_frame": 30}}}, {})
    assert t["target_name"] == "M 42" and t["stacked_frames"] == 30


def test_a_running_stack_reports_exposure_and_integration():
    vs = {"View": {"state": "working", "mode": "star", "stage": "Stack",
                   "Stack": {"stacked_frame": 90, "Exposure": {"exp_ms": 10000.0}}}}
    t = telemetry.normalize({}, vs, {})
    assert t["state"] == "working" and t["mode"] == "star" and t["stage"] == "Stack"
    assert t["exposure_s"] == 10.0 and t["integration_s"] == 900


def test_latest_image_is_the_newest_preferring_the_stacked_one():
    img = telemetry.latest_image(_ALBUMS)
    assert img == {
        "name": "M 42", "count": 12, "stacked": True,
        "thumb": "MyWorks/M 42/Stacked_12_M 42_10.0s_LP_20261118-221500_thn.jpg",
        "full": "MyWorks/M 42/Stacked_12_M 42_10.0s_LP_20261118-221500.jpg",
    }


@pytest.mark.parametrize("albums", [{}, {"list": []}, {"list": [{"files": None}]},
                                    {"list": "x"}, None, {"list": [{"files": [{"thn": 5}]}]}])
def test_latest_image_tolerates_odd_replies(albums):
    assert telemetry.latest_image(albums) is None


# ---------------------------------------------------------------------------
# collect_telemetry and the albums clock
# ---------------------------------------------------------------------------


class _Client:
    def __init__(self, disk_fails: bool = False):
        self.disk_fails = disk_fails
        self.album_calls = 0

    def get_device_state(self, timeout=0):
        return _DEVICE_STATE

    def get_view_state(self, timeout=0):
        return {}

    def get_equ_coord(self, timeout=0):
        return {"ra": 1.0, "dec": 2.0}

    def get_disk_volume(self, timeout=0):
        if self.disk_fails:
            raise SeestarError("method not found")
        return {"totalMB": 100, "freeMB": 40}

    def get_albums(self, timeout=0):
        self.album_calls += 1
        return _ALBUMS


def test_a_firmware_without_get_disk_volume_costs_no_error_line():
    tel, errors = collect_telemetry(_Client(disk_fails=True))
    assert errors == [] and tel["free_storage_mb"] is None


def test_collect_telemetry_carries_storage_and_the_newest_picture():
    tel, errors = collect_telemetry(_Client(), _ALBUMS)
    assert errors == [] and tel["free_storage_mb"] == 40
    assert tel["latest_image"]["name"] == "M 42"


def test_albums_are_asked_for_on_their_own_slower_clock():
    clock = {"t": 1000.0}
    mgr = SeestarManager(get_settings=lambda: None, now_fn=lambda: clock["t"])
    c = _Client()
    for _ in range(5):  # five 2 s poll cycles
        assert mgr._poll_albums("10.0.0.5", c) == _ALBUMS
        clock["t"] += 2.0
    assert c.album_calls == 1
    clock["t"] += manager_mod._ALBUMS_EVERY_S
    mgr._poll_albums("10.0.0.5", c)
    assert c.album_calls == 2


def test_a_failed_albums_call_keeps_the_last_answer():
    clock = {"t": 0.0}
    mgr = SeestarManager(get_settings=lambda: None, now_fn=lambda: clock["t"])
    c = _Client()
    mgr._poll_albums("ip", c)
    c.get_albums = lambda timeout=0: (_ for _ in ()).throw(SeestarError("busy"))
    clock["t"] += 60
    assert mgr._poll_albums("ip", c) == _ALBUMS


# ---------------------------------------------------------------------------
# The scope's HTTP file server (a local stand-in on a free port)
# ---------------------------------------------------------------------------


class _ScopeHttp:
    def __init__(self, files: dict[str, bytes]):
        self.files = files
        self.hits: list[str] = []
        outer = self

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                outer.hits.append(self.path)
                body = outer.files.get(self.path)
                if body is None:
                    self.send_response(404)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()


@pytest.fixture
def scope_http():
    servers = []

    def make(files):
        s = _ScopeHttp(files)
        servers.append(s)
        return s

    yield make
    for s in servers:
        s.close()


def test_fetch_quotes_the_path_and_returns_a_jpeg(scope_http):
    srv = scope_http({"/MyWorks/M%2042/a_thn.jpg": JPEG})
    assert fetch_scope_file("127.0.0.1", "MyWorks/M 42/a_thn.jpg", 1024, port=srv.port) == JPEG


@pytest.mark.parametrize("files,path", [
    ({"/big.jpg": JPEG + b"\x00" * 2048}, "big.jpg"),          # over the ceiling
    ({"/page.jpg": b"<html>not a picture</html>"}, "page.jpg"),  # not an image
    ({}, "missing.jpg"),                                         # 404
])
def test_fetch_refuses_what_is_not_a_bounded_picture(scope_http, files, path):
    srv = scope_http(files)
    assert fetch_scope_file("127.0.0.1", path, 1024, port=srv.port) is None


def test_fetch_from_a_silent_host_is_none_not_an_exception():
    assert fetch_scope_file("127.0.0.1", "x.jpg", 1024, port=1, timeout=0.5) is None


def _manager_with_picture(srv) -> SeestarManager:
    mgr = SeestarManager(get_settings=lambda: None)
    mgr.http_port = srv.port
    mgr._store_telemetry("127.0.0.1", telemetry.normalize({}, {}, {}, albums=_ALBUMS))
    return mgr


def test_manager_fetches_the_reported_picture_and_caches_the_thumbnail(scope_http):
    thumb = "/MyWorks/M%2042/Stacked_12_M%2042_10.0s_LP_20261118-221500_thn.jpg"
    full = "/MyWorks/M%2042/Stacked_12_M%2042_10.0s_LP_20261118-221500.jpg"
    srv = scope_http({thumb: JPEG, full: JPEG + b"full"})
    mgr = _manager_with_picture(srv)
    assert mgr.latest_image("127.0.0.1", "thumb") == JPEG
    assert mgr.latest_image("127.0.0.1", "thumb") == JPEG
    assert srv.hits == [thumb]          # the second ask cost the scope nothing
    assert mgr.latest_image("127.0.0.1", "full") == JPEG + b"full"  # full size is never cached
    assert srv.hits == [thumb, full]


def test_manager_never_contacts_an_unknown_scope_or_an_odd_kind(scope_http):
    srv = scope_http({})
    mgr = _manager_with_picture(srv)
    assert mgr.latest_image("192.0.2.99") is None
    with pytest.raises(ValueError):
        mgr.latest_image("127.0.0.1", "../etc")
    assert srv.hits == []


# ---------------------------------------------------------------------------
# GET /api/seestar/{ip}/image
# ---------------------------------------------------------------------------


def test_image_endpoint_is_gated_validated_and_404s_an_unknown_scope(client):
    assert client.get("/api/seestar/127.0.0.1/image").status_code == 409
    client.put("/api/settings", json={
        "seestar_enabled": True, "seestar_scan_subnet": "203.0.113.0/31"})
    try:
        assert client.get("/api/seestar/127.0.0.1/image?kind=../x").status_code == 422
        assert client.get("/api/seestar/192.0.2.99/image").status_code == 404
    finally:
        client.put("/api/settings", json={"seestar_enabled": False})


def test_image_endpoint_relays_the_scope_picture(client, scope_http):
    thumb = "/MyWorks/M%2042/Stacked_12_M%2042_10.0s_LP_20261118-221500_thn.jpg"
    srv = scope_http({thumb: JPEG})
    client.put("/api/settings", json={
        "seestar_enabled": True, "seestar_scan_subnet": "203.0.113.0/31"})
    try:
        mgr = client.app.state.seestar_manager
        mgr.http_port = srv.port
        mgr._store_telemetry("127.0.0.1", telemetry.normalize({}, {}, {}, albums=_ALBUMS))
        r = client.get("/api/seestar/127.0.0.1/image")
        assert r.status_code == 200
        assert r.headers["content-type"] == "image/jpeg" and r.content == JPEG
        # The devices list carries the picture's label and the private-free raw.
        dev = client.get("/api/seestar/devices").json()["devices"][0]
        assert dev["telemetry"]["latest_image"]["name"] == "M 42"
        # Full size isn't on the stand-in server: no picture, not an error.
        assert client.get("/api/seestar/127.0.0.1/image?kind=full").status_code == 204
    finally:
        client.put("/api/settings", json={"seestar_enabled": False})
