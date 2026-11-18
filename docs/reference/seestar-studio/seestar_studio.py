#!/usr/bin/env python3
"""
Seestar Studio - a full-featured local web control center for a ZWO Seestar.

A single-file Python app that serves a modern, space-themed web UI (desktop and
phone) for BOTH monitoring and controlling a ZWO Seestar over the LAN - a
lightweight alternative to running the official Android app in an emulator.

Features
--------
* Live stacked image, target, RA/Dec, battery, disk, temperature, stack stats
* Imaging: start / stop view in Star, Sun, Moon, Planet or Scenery mode
* Target GoTo by name + RA/Dec, with a built-in catalogue of popular objects
* Focus: autofocus start/stop and manual focuser steps
* Mount: directional nudge pad, park, and sync
* Albums gallery (browse saved captures from the scope's own file server)
* Settings: gain, exposure, LP filter, dew heater, device info
* Raw RPC console - send any method/params the firmware supports ("and more")

Safety
------
Monitoring is read-only. CONTROL actions (GoTo, start/stop, focus, mount, power)
obviously do change the scope - they are only ever sent when YOU click a control
in the UI (several ask for confirmation first). The app never sends a control
command on its own; idle polling uses getters only.

Control calls use the standard community Seestar JSON-RPC method names (as used by
seestar_alp etc.). If your firmware expects a slightly different shape for some
action, the built-in **Console** tab lets you send the exact method/params.

Usage
-----
    python seestar_studio.py --host 192.168.1.100 --bind tailscale
    then open  http://127.0.0.1:5557   (and the tailnet URL it prints)

Full control needs `seestar.pem` next to this file and the `cryptography` package.
"""

import argparse
import base64
import collections
import datetime
import json
import os
import re
import socket
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import seestar_skyline as skyline

TS_RE = re.compile(r"(\d{8})-(\d{6})")
AUTH_METHODS = {"get_verify_str", "verify_client", "pi_is_verified"}

SCOPE_HTTP_PORT = 80      # the scope's own file server
DATA_DIR = "data"         # last-known state, history, cached live image
CAP_DIR = "captures"      # auto-saved full-resolution stacks
AUTOSAVE_MIN = 10         # 0 disables auto-save
DEMO = False
WIDE_URL = None           # same, for the wide-angle camera
VIDEO_URL = None          # override for the live-video source (demo / testing)
IMG_PORT = 4800           # binary preview-frame port (4804 = wide camera)

# set_setting keys the UI may change (everything else goes through the Console)
ALLOWED_SETTINGS = {
    "stack_lenhance", "stack_dither", "auto_af", "stack_after_goto", "frame_calib",
    "auto_power_off", "auto_3ppa_calib", "expert_mode", "heater_enable", "wide_cam",
    "stack", "mosaic", "beep_volume", "temp_unit", "plan_target_af", "viewplan_gohome",
    "enable_dark_library", "light_brightness", "dark_mode", "manual_exp", "isp_exp_ms",
    "isp_gain", "ae_bri_percent", "exp_ms",
}

# scalar state that survives restarts / scope power-loss ("last known")
PERSIST = ["stack_state", "stacked_frame", "dropped_frame", "exp_state", "exp_ms", "gain",
           "temp", "target_name", "ra", "dec", "mode", "battery", "charging",
           "charger_status", "disk_free_mb", "disk_total_mb", "model", "firmware", "sn",
           "focuser_pos", "lp_filter", "img_label", "img_updated", "last_seen_ts",
           "last_event_wall", "lon", "lat"]


def _ago(sec):
    sec = int(max(0, sec))
    if sec < 90:
        return f"{sec}s"
    if sec < 5400:
        return f"{sec // 60} min"
    if sec < 172800:
        return f"{sec / 3600:.1f} h"
    return f"{sec // 86400} days"


def _safe(name):
    return re.sub(r"[^\w .+-]", "_", str(name or "target")).strip() or "target"


# ----------------------------------------------------------------------------
# Shared state
# ----------------------------------------------------------------------------

class State:
    def __init__(self):
        self.lock = threading.Lock()
        self.connected = False
        self.last_event_ts = 0.0
        self.last_event_wall = None
        self.host = ""
        self.firmware_gated = None
        self.authed = False
        self.have_key = False
        self.connect_count = 0

        self.stack_state = None
        self.stacked_frame = None
        self.dropped_frame = None
        self.stack_lapse_ms = None
        self.exp_state = None
        self.exp_ms = None
        self.gain = None
        self.temp = None

        self.target_name = None
        self.ra = None
        self.dec = None
        self.mode = None
        self.battery = None
        self.charging = None
        self.charger_status = None
        self.disk_free_mb = None
        self.disk_total_mb = None
        self.model = None
        self.firmware = None
        self.sn = None
        self.annotation_count = None
        self.focuser_pos = None
        self.lp_filter = None

        self.img_thumb_path = None
        self.img_full_path = None
        self.img_updated = None
        self.img_label = None

        self.albums = None
        self.log = []
        self.MAXLOG = 500

        self.last_seen_ts = None      # last time we had a live link to the scope
        self.last_stack_ts = None
        self.view_state = None
        self.view_stage = None
        self.heater = None
        self.lon = None
        self.lat = None
        self.history = collections.deque(maxlen=2880)   # 24 h at 30 s
        self.settings = {}            # raw get_setting result
        self.mount = {}               # equ_mode / close / tracking
        self.plan = None              # ViewPlan from iscope_get_app_state
        self.ops = {}                 # last payload of each event type
        self.wheel = None
        self.tracking = None
        self.altaz = None
        self.level = None
        self.compass = None
        self.wifi = None
        self.solve = None
        self.dev_name = None
        self.img_cache = None         # bytes of the latest live thumbnail
        self.img_rev = 0
        self.last_capture = None
        self.capture_count = 0

    # ---- derived ----
    def _battery_estimate(self):
        """(%/hour, hours left) from the recent discharge slope, or (None, None)."""
        now = time.time()
        pts = [(s["t"], s["b"]) for s in self.history
               if s.get("on") and s.get("b") is not None and not s.get("ch")
               and now - s["t"] < 3600]
        if len(pts) < 4 or self.charging:
            return None, None
        (t0, b0), (t1, b1) = pts[0], pts[-1]
        if t1 - t0 < 300 or b0 - b1 < 1:
            return None, None
        rate = (b0 - b1) / ((t1 - t0) / 3600.0)
        return round(rate, 1), round(b1 / rate, 2)

    def _alerts(self, est_h):
        out = []
        now = time.time()
        if not self.connected:
            if self.last_seen_ts:
                when = datetime.datetime.fromtimestamp(self.last_seen_ts).strftime("%a %H:%M")
                txt = f"Last seen {when} ({_ago(now - self.last_seen_ts)} ago)."
                if self.battery is not None and self.battery <= 10 and not self.charging:
                    txt += (f" Battery was at {self.battery}% and discharging - it most "
                            f"likely ran out of power. Plug it in and power it on.")
                else:
                    txt += " Showing the last known data; will reconnect automatically."
                out.append({"id": "offline", "level": "bad", "title": "Scope offline", "text": txt})
            else:
                out.append({"id": "offline", "level": "warn", "title": "Looking for the scope",
                            "text": f"Trying {self.host} - it may be powered off or on another network."})
            return out
        if self.firmware_gated and not self.authed:
            out.append({"id": "auth", "level": "warn", "title": "Monitor only",
                        "text": "Completing authentication..." if self.have_key else
                        "No interop key (seestar.pem) - control is disabled."})
        b = self.battery
        if b is not None and not self.charging:
            left = f" About {est_h * 60:.0f} min left at the current rate." if est_h else ""
            if b <= 5:
                out.append({"id": "batt5", "level": "bad", "title": f"Battery critical: {b}%",
                            "text": "The scope will shut down very soon - connect power now." + left})
            elif b <= 10:
                out.append({"id": "batt10", "level": "bad", "title": f"Battery very low: {b}%",
                            "text": "Connect USB-C power to keep the session alive." + left})
            elif b <= 20:
                out.append({"id": "batt20", "level": "warn", "title": f"Battery low: {b}%",
                            "text": "Consider connecting power." + left})
        if (self.stack_state == "working" and self.last_stack_ts and self.exp_ms
                and self.view_state != "idle"):
            quiet = now - self.last_stack_ts
            if quiet > max(120, 6 * self.exp_ms / 1000.0):
                out.append({"id": "stall", "level": "warn", "title": "Stacking looks stalled",
                            "text": f"No new frame for {_ago(quiet)} (clouds, dew, or the plan ended?)."})
        if self.disk_free_mb is not None and self.disk_free_mb < 2000:
            out.append({"id": "disk", "level": "warn", "title": "Scope storage almost full",
                        "text": f"Only {self.disk_free_mb / 1024:.1f} GB free."})
        return out

    def note(self, kind, text):
        with self.lock:
            self.log.append({"t": datetime.datetime.now().strftime("%H:%M:%S"),
                             "kind": kind, "text": text})
            if len(self.log) > self.MAXLOG:
                self.log = self.log[-self.MAXLOG:]

    def snapshot(self):
        with self.lock:
            age = (time.time() - self.last_event_ts) if self.last_event_ts else None
            integ = None
            if self.stacked_frame is not None and self.exp_ms:
                integ = int(self.stacked_frame * self.exp_ms / 1000)
            rate, est_h = self._battery_estimate()
            return {
                "demo": DEMO,
                "alerts": self._alerts(est_h),
                "last_seen": (datetime.datetime.fromtimestamp(self.last_seen_ts)
                              .strftime("%Y-%m-%d %H:%M:%S") if self.last_seen_ts else None),
                "offline_for_s": (None if self.connected or not self.last_seen_ts
                                  else int(time.time() - self.last_seen_ts)),
                "battery_rate": rate, "battery_hours_left": est_h,
                "view": {"state": self.view_state, "stage": self.view_stage},
                "settings": {k: v for k, v in self.settings.items() if k != "password"}, "mount": self.mount, "plan": self.plan,
                "ops": self.ops, "wheel": self.wheel, "tracking": self.tracking,
                "altaz": self.altaz, "level": self.level, "compass": self.compass,
                "wifi": self.wifi, "solve": self.solve,
                "video": HUB.status() if HUB else {"available": False},
                "video_wide": HUB_W.status() if HUB_W else {"available": False},
                "skyline": skyline_info(),
                "heater": self.heater,
                "location": {"lon": self.lon, "lat": self.lat},
                "autosave": {"minutes": AUTOSAVE_MIN, "last": self.last_capture,
                             "count": self.capture_count, "dir": os.path.abspath(CAP_DIR)},
                "connected": self.connected, "host": self.host,
                "firmware_gated": self.firmware_gated, "authed": self.authed,
                "have_key": self.have_key, "connect_count": self.connect_count,
                "seconds_since_event": round(age, 1) if age is not None else None,
                "last_event_wall": self.last_event_wall,
                "stack": {"state": self.stack_state, "stacked_frame": self.stacked_frame,
                          "dropped_frame": self.dropped_frame, "lapse_ms": self.stack_lapse_ms},
                "exposure": {"state": self.exp_state, "exp_ms": self.exp_ms, "gain": self.gain},
                "temp": self.temp, "integration_s": integ,
                "target": {"name": self.target_name, "ra": self.ra, "dec": self.dec,
                           "mode": self.mode, "annotations": self.annotation_count},
                "power": {"battery": self.battery, "charging": self.charging,
                          "charger_status": self.charger_status},
                "disk": {"free_mb": self.disk_free_mb, "total_mb": self.disk_total_mb},
                "device": {"model": self.model, "firmware": self.firmware, "sn": self.sn},
                "focus": {"position": self.focuser_pos},
                "filter": {"lp": self.lp_filter},
                "image": {"available": self.img_cache is not None or self.img_thumb_path is not None,
                          "label": self.img_label, "updated": self.img_updated,
                          "rev": self.img_rev, "stale": not self.connected},
                "server_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "log": self.log[-250:],
            }


STATE = State()


# ----------------------------------------------------------------------------
# RSA signer (firmware 7.18+)
# ----------------------------------------------------------------------------

def load_signer(key_path):
    if not key_path or not os.path.isfile(key_path):
        return None
    try:
        from cryptography.hazmat.primitives import serialization
    except Exception:
        STATE.note("auth", "seestar.pem found but 'cryptography' not installed "
                           "(pip install cryptography).")
        return None
    try:
        with open(key_path, "rb") as fh:
            pk = serialization.load_pem_private_key(fh.read(), password=None)
    except Exception as e:
        STATE.note("auth", f"Could not load key: {e}")
        return None

    def sign(challenge):
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding
        sig = pk.sign(challenge.encode("utf-8"), padding.PKCS1v15(), hashes.SHA1())
        return base64.b64encode(sig).decode("ascii")

    with STATE.lock:
        STATE.have_key = True
    STATE.note("auth", f"Interop key loaded ({os.path.basename(key_path)}).")
    return sign


# ----------------------------------------------------------------------------
# Discovery + HTTP image fetch
# ----------------------------------------------------------------------------

def _local_ipv4s():
    ips = []
    try:
        for res in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = res[4][0]
            if ip not in ips and not ip.startswith("127."):
                ips.append(ip)
    except Exception:
        pass
    return ips or [""]


def _broadcast_for(ip):
    p = ip.split(".")
    return ".".join(p[:3]) + ".255" if len(p) == 4 else None


def discover_seestar(timeout=3):
    msg = b'{"id":1,"method":"scan_iscope","params":""}'
    for localip in _local_ipv4s():
        try:
            u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            u.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            try:
                u.bind((localip, 0))
            except Exception:
                pass
            u.settimeout(timeout)
            for dst in ("255.255.255.255", _broadcast_for(localip)):
                if dst:
                    try:
                        u.sendto(msg, (dst, 4720))
                    except Exception:
                        pass
            end = time.time() + timeout
            while time.time() < end:
                try:
                    data, addr = u.recvfrom(4096)
                    u.close()
                    return addr[0]
                except socket.timeout:
                    break
            u.close()
        except Exception:
            continue
    return _sweep_for_seestar()


def _is_seestar(ip, port=4700):
    try:
        s = socket.create_connection((ip, port), timeout=0.7)
    except Exception:
        return False
    try:
        s.settimeout(3)
        s.sendall(b'{"id":1,"method":"get_verify_str"}' + bytes([13, 10]))
        return b'"jsonrpc"' in s.recv(2048)
    except Exception:
        return False
    finally:
        s.close()


def _sweep_for_seestar():
    """Look for the control port on each private /24 this PC is on."""
    import concurrent.futures
    for localip in _local_ipv4s():
        p = localip.split(".")
        if len(p) != 4 or not (p[0] in ("10", "192") or p[0] == "172"):
            continue                        # skip tailnet / public ranges
        ips = [".".join(p[:3]) + "." + str(i) for i in range(1, 255)
               if str(i) != p[3]]
        try:
            with concurrent.futures.ThreadPoolExecutor(64) as ex:
                for ip, ok in zip(ips, ex.map(_is_seestar, ips)):
                    if ok:
                        return ip
        except Exception:
            continue
    return None


def scope_http_get(host, path, timeout=8):
    enc = urllib.parse.quote(path)
    try:
        s = socket.create_connection((host, SCOPE_HTTP_PORT), timeout=timeout)
        s.settimeout(timeout)
        s.sendall(f"GET /{enc} HTTP/1.0\r\nHost: seestar\r\n\r\n".encode())
        data = b""
        while True:
            try:
                d = s.recv(65536)
                if not d:
                    break
                data += d
            except socket.timeout:
                break
        s.close()
    except Exception:
        return None
    head, _, body = data.partition(b"\r\n\r\n")
    if b"200" not in head.split(b"\r\n", 1)[0]:
        return None
    return body


# ----------------------------------------------------------------------------
# Scope client - async events + synchronous control calls
# ----------------------------------------------------------------------------

class ScopeClient(threading.Thread):
    daemon = True

    def __init__(self, host, port, signer=None):
        super().__init__(name="scope")
        self.host = host
        self.port = port
        self.signer = signer
        self.sock = None
        self._rid = 1000
        self._idlock = threading.Lock()
        self._sendlock = threading.Lock()
        self._inflight = {}                 # id -> method (polling, fire&forget)
        self._pending = {}                  # id -> {event,reply} (sync calls)
        self._pendlock = threading.Lock()
        self._buf = b""

    def _next_id(self):
        with self._idlock:
            self._rid += 1
            return self._rid

    def _write(self, obj):
        data = (json.dumps(obj) + "\r\n").encode("utf-8")
        with self._sendlock:
            if not self.sock:
                raise ConnectionError("not connected")
            self.sock.sendall(data)

    def _send(self, method, params=None):
        """Fire-and-forget (used by background polling)."""
        rid = self._next_id()
        self._inflight[rid] = method
        msg = {"id": rid, "method": method}
        if params is not None:
            msg["params"] = params
        self._write(msg)
        return rid

    def call(self, method, params=None, timeout=10):
        """Synchronous RPC used by HTTP handler threads. Returns the reply dict
        or raises. Safe because the reader thread sets the reply event."""
        if not self.sock or not STATE.connected:
            raise ConnectionError("scope not connected")
        if STATE.firmware_gated and not STATE.authed and method not in AUTH_METHODS:
            raise PermissionError("not authenticated (no interop key loaded)")
        rid = self._next_id()
        ev = threading.Event()
        slot = {"event": ev, "reply": None}
        with self._pendlock:
            self._pending[rid] = slot
        msg = {"id": rid, "method": method}
        if params is not None:
            msg["params"] = params
        self._write(msg)
        STATE.note("cmd", f"-> {method} {json.dumps(params) if params is not None else ''}".strip())
        if ev.wait(timeout):
            with self._pendlock:
                self._pending.pop(rid, None)
            reply = slot["reply"]
            if reply is None:
                raise ConnectionError("scope disconnected before replying")
            code = reply.get("code") if isinstance(reply, dict) else None
            STATE.note("cmd", f"<- {method} code={code}")
            return reply
        with self._pendlock:
            self._pending.pop(rid, None)
        raise TimeoutError(f"{method} timed out")

    # ---- replies ----
    def _handle_reply(self, method, obj):
        code = obj.get("code")
        result = obj.get("result")
        if method == "get_verify_str":
            if code == 103:
                with STATE.lock:
                    STATE.firmware_gated = False
                return
            with STATE.lock:
                STATE.firmware_gated = True
            ch = (result or {}).get("str") if isinstance(result, dict) else None
            if ch and self.signer and not STATE.authed:
                try:
                    self._send("verify_client", {"sign": self.signer(ch), "data": ch})
                except Exception as e:
                    STATE.note("auth", f"Signing failed: {e}")
        elif method == "verify_client":
            if code == 0:
                self._send("pi_is_verified", "verify")
                with STATE.lock:
                    STATE.authed = True
                STATE.note("auth", "Authenticated - full control enabled.")
            else:
                STATE.note("auth", f"verify_client rejected (code={code}).")
        elif method == "get_device_state" and isinstance(result, dict):
            self._apply_device_state(result)
        elif method == "get_view_state" and isinstance(result, dict):
            self._apply_view_state(result)
        elif method == "get_disk_volume" and isinstance(result, dict):
            with STATE.lock:
                STATE.disk_total_mb = result.get("totalMB")
                STATE.disk_free_mb = result.get("freeMB")
        elif method == "get_focuser_position":
            with STATE.lock:
                STATE.focuser_pos = result if isinstance(result, (int, float)) else \
                    (result or {}).get("position") if isinstance(result, dict) else None
        elif method == "scope_get_equ_coord" and isinstance(result, dict):
            with STATE.lock:
                STATE.ra = result.get("ra"); STATE.dec = result.get("dec")
        elif method == "get_albums" and isinstance(result, dict):
            self._apply_albums(result)
        elif method == "get_setting" and isinstance(result, dict):
            with STATE.lock:
                STATE.settings = result
                if result.get("stack_lenhance") is not None:
                    STATE.lp_filter = result.get("stack_lenhance")
        elif method == "iscope_get_app_state" and isinstance(result, dict):
            with STATE.lock:
                STATE.plan = result.get("ViewPlan")
        elif method == "get_wheel_position":
            with STATE.lock:
                STATE.wheel = result if isinstance(result, int) else None
        elif method == "scope_get_horiz_coord":
            with STATE.lock:
                if isinstance(result, list) and len(result) == 2:
                    STATE.altaz = {"alt": result[0], "az": result[1]}
                elif isinstance(result, dict):
                    STATE.altaz = {"alt": result.get("alt"), "az": result.get("az")}
        elif method in ("get_solve_result", "get_last_solve_result"):
            with STATE.lock:
                STATE.solve = result if code == 0 else {"error": obj.get("error")}

    def _apply_device_state(self, r):
        dev = r.get("device") or {}
        pi = r.get("pi_status") or {}
        sett = r.get("setting") or {}
        with STATE.lock:
            STATE.model = dev.get("user_product_model") or dev.get("product_model")
            STATE.firmware = dev.get("firmware_ver_string")
            STATE.sn = dev.get("sn")
            if "battery_capacity" in pi: STATE.battery = pi["battery_capacity"]
            if "charge_online" in pi: STATE.charging = pi["charge_online"]
            if "charger_status" in pi: STATE.charger_status = pi.get("charger_status")
            if "temp" in pi: STATE.temp = pi["temp"]
            if sett.get("stack_lenhance") is not None: STATE.lp_filter = sett.get("stack_lenhance")
            if sett: STATE.settings = sett
            if isinstance(r.get("mount"), dict):
                STATE.mount = r["mount"]
                if r["mount"].get("tracking") is not None: STATE.tracking = r["mount"]["tracking"]
            foc = r.get("focuser")
            if isinstance(foc, dict) and foc.get("step") is not None: STATE.focuser_pos = foc["step"]
            bs = r.get("balance_sensor")
            if isinstance(bs, dict): STATE.level = bs.get("data") or bs
            cs = r.get("compass_sensor")
            if isinstance(cs, dict): STATE.compass = cs.get("data") or cs
            if isinstance(r.get("station"), dict): STATE.wifi = r["station"]
            STATE.dev_name = dev.get("name")
            if sett.get("heater_enable") is not None: STATE.heater = sett.get("heater_enable")
            ll = r.get("location_lon_lat")
            if isinstance(ll, list) and len(ll) == 2 and (ll[0] or ll[1]):
                STATE.lon, STATE.lat = ll[0], ll[1]
            STATE.last_seen_ts = time.time()

    def _apply_view_state(self, r):
        v = r.get("View") or {}
        stack = v.get("Stack") or {}
        exp = stack.get("Exposure") or {}
        ann = stack.get("Annotate") or {}
        with STATE.lock:
            # real firmware: {} when nothing has run since boot, and a stopped
            # view stays behind as state "cancel" with its old stage
            if not v or v.get("state") in ("cancel", "idle"):
                if v.get("target_name"): STATE.target_name = v.get("target_name")
                STATE.view_state = "idle"
                STATE.view_stage = None
                STATE.stack_state = "idle"
                STATE.exp_state = "idle"
                return
            STATE.view_state = v.get("state")
            STATE.view_stage = v.get("stage")
            if v.get("state") == "idle" or (v.get("state") and not stack):
                STATE.stack_state = "idle"
            if v.get("target_name"): STATE.target_name = v.get("target_name")
            trd = v.get("target_ra_dec")
            if isinstance(trd, list) and len(trd) == 2:
                STATE.ra, STATE.dec = trd[0], trd[1]
            if v.get("mode"): STATE.mode = v.get("mode")
            if v.get("gain") is not None: STATE.gain = v.get("gain")
            if v.get("lp_filter") is not None: STATE.lp_filter = v.get("lp_filter")
            if "stacked_frame" in stack: STATE.stacked_frame = stack["stacked_frame"]
            if "dropped_frame" in stack: STATE.dropped_frame = stack["dropped_frame"]
            if stack.get("state"): STATE.stack_state = stack["state"]
            if exp.get("exp_ms") is not None: STATE.exp_ms = exp["exp_ms"]
            if exp.get("state"): STATE.exp_state = exp["state"]
            ar = (ann.get("result") or {}).get("annotations")
            if isinstance(ar, list): STATE.annotation_count = len(ar)

    def _apply_albums(self, r):
        parent = r.get("path", "MyWorks")
        flat = []
        best = None
        for grp in r.get("list", []) or []:
            gname = grp.get("group_name")
            for f in grp.get("files", []) or []:
                thn = f.get("thn")
                if not thn:
                    continue
                flat.append({"name": f.get("name"), "group": gname,
                             "count": f.get("count"), "thn": f"{parent}/{thn}",
                             "full": f"{parent}/" + thn.replace("_thn.jpg", ".jpg")})
                m = TS_RE.search(thn)
                ts = (m.group(1) + m.group(2)) if m else "0"
                score = ts + ("1" if "Stacked" in thn else "0")
                if best is None or score > best[0]:
                    best = (score, f"{parent}/{thn}",
                            f"{parent}/" + thn.replace("_thn.jpg", ".jpg"), f.get("name"))
        with STATE.lock:
            STATE.albums = flat
            if best:
                STATE.img_thumb_path = best[1]
                STATE.img_full_path = best[2]
                STATE.img_label = best[3]
                STATE.img_updated = datetime.datetime.now().strftime("%H:%M:%S")

    # ---- dispatch ----
    def _handle(self, obj):
        rid = obj.get("id")
        if rid is not None:
            with self._pendlock:
                slot = self._pending.get(rid)
                if slot is not None:
                    slot["reply"] = obj
                    slot["event"].set()
                    self._pending.pop(rid, None)
                    return
            if rid in self._inflight:
                self._handle_reply(self._inflight.pop(rid), obj)
                return
        ev = obj.get("Event")
        if ev is None:
            return
        with STATE.lock:
            STATE.last_event_ts = time.time()
            STATE.last_seen_ts = STATE.last_event_ts
            STATE.last_event_wall = datetime.datetime.now().strftime("%H:%M:%S")
        if ev == "Stack":
            with STATE.lock:
                if "stacked_frame" in obj: STATE.last_stack_ts = time.time()
                if obj.get("state"): STATE.stack_state = obj["state"]
                if "stacked_frame" in obj: STATE.stacked_frame = obj["stacked_frame"]
                if "dropped_frame" in obj: STATE.dropped_frame = obj["dropped_frame"]
                if "lapse_ms" in obj: STATE.stack_lapse_ms = obj["lapse_ms"]
            if obj.get("stacked_frame") is not None:
                STATE.note("stack", f"stacked={obj.get('stacked_frame')} "
                                    f"dropped={obj.get('dropped_frame')} {obj.get('state')}")
        elif ev == "Exposure":
            with STATE.lock:
                if obj.get("state"): STATE.exp_state = obj["state"]
                if "exp_ms" in obj: STATE.exp_ms = obj["exp_ms"]
                if "gain" in obj: STATE.gain = obj["gain"]
            if obj.get("state") in ("start", "complete"):
                STATE.note("expose", f"{obj.get('page','')} {obj.get('state')}")
        elif ev == "PiStatus":
            with STATE.lock:
                if "temp" in obj: STATE.temp = obj["temp"]
                if "battery_capacity" in obj: STATE.battery = obj["battery_capacity"]
                if "charge_online" in obj: STATE.charging = obj["charge_online"]
        else:
            keep = {k: v for k, v in obj.items()
                    if k not in ("Event", "Timestamp") and not isinstance(v, (list, dict))}
            with STATE.lock:
                prev = (STATE.ops.get(ev) or {}).get("state")
                STATE.ops[ev] = dict(keep, t=time.time())
                if len(STATE.ops) > 40:
                    STATE.ops.pop(next(iter(STATE.ops)))
            if keep.get("state") != prev or "state" not in keep:
                STATE.note("event", f"{ev} {keep.get('state', '')}".strip()
                           + (f" ({keep['error']})" if keep.get("error") else ""))

    def _probe_gate(self):
        try:
            s = socket.create_connection((self.host, self.port), timeout=5)
            s.settimeout(3.0)
            s.sendall(b'{"id":1,"method":"get_verify_str","params":"verify"}\r\n')
            buf = b""
            end = time.time() + 3
            while time.time() < end:
                try:
                    d = s.recv(8192)
                    if not d:
                        break
                    buf += d
                    hit = False
                    for line in buf.split(b"\r\n"):
                        if line.strip():
                            try:
                                o = json.loads(line)
                            except Exception:
                                continue
                            if o.get("id") == 1:
                                with STATE.lock:
                                    STATE.firmware_gated = (o.get("code") != 103)
                                hit = True
                                break
                    if hit:
                        break
                except socket.timeout:
                    break
            s.close()
        except Exception:
            pass

    def run(self):
        if not self.signer:
            self._probe_gate()
        backoff = 1.0
        while True:
            try:
                self.sock = socket.create_connection((self.host, self.port), timeout=6)
                self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                self.sock.settimeout(1.0)
                self._buf = b""
                self._inflight = {}
                with STATE.lock:
                    STATE.connected = True
                    STATE.host = self.host
                    STATE.connect_count += 1
                    STATE.authed = False
                STATE.note("net", f"Connected to {self.host}:{self.port}")
                backoff = 1.0
                if self.signer:
                    self._send("get_verify_str", "verify")
                last_hb = time.time()
                last_poll = 0.0
                last_albums = 0.0
                while True:
                    try:
                        chunk = self.sock.recv(65536)
                        if not chunk:
                            raise ConnectionError("socket closed by scope")
                        self._buf += chunk
                        while b"\r\n" in self._buf:
                            line, self._buf = self._buf.split(b"\r\n", 1)
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                obj = json.loads(line)
                            except Exception:
                                continue
                            if isinstance(obj, dict):
                                self._handle(obj)
                    except socket.timeout:
                        pass
                    now = time.time()
                    if self.signer and STATE.authed:
                        if now - last_hb > 10:
                            last_hb = now
                            self._send("scope_get_equ_coord")
                            self._send("get_focuser_position")
                        if now - last_poll > 4:
                            last_poll = now
                            self._send("get_view_state")
                            self._send("get_device_state")
                            self._send("get_disk_volume")
                        if now - last_albums > 10:
                            last_albums = now
                            self._send("get_albums")
                            self._send("get_setting")
                            self._send("iscope_get_app_state")
                            self._send("get_wheel_position")
                            self._send("scope_get_horiz_coord")
                            self._send("get_last_solve_result")
            except Exception as e:
                with STATE.lock:
                    STATE.connected = False
                    STATE.authed = False
                STATE.note("net", f"Disconnected: {e}; retry in {backoff:.0f}s")
                with self._pendlock:
                    for slot in self._pending.values():
                        slot["event"].set()
                    self._pending.clear()
                try:
                    if self.sock:
                        self.sock.close()
                except Exception:
                    pass
                self.sock = None
                time.sleep(backoff)
                backoff = min(backoff * 1.7, 15.0)
                if backoff >= 6 and getattr(self, "discover", True):
                    newip = discover_seestar(3)
                    if newip and newip != self.host:
                        STATE.note("net", f"Discovered Seestar at {newip}")
                        self.host = newip
                        with STATE.lock:
                            STATE.host = newip
                        backoff = 1.0


# ----------------------------------------------------------------------------
# Housekeeper: history, last-known state, live-image cache, auto-save
# (reads only - never sends a control command)
# ----------------------------------------------------------------------------

def load_persisted():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(CAP_DIR, exist_ok=True)
    try:
        with open(os.path.join(DATA_DIR, "last_state.json"), encoding="utf-8") as fh:
            d = json.load(fh)
        with STATE.lock:
            for k in PERSIST:
                if d.get(k) is not None:
                    setattr(STATE, k, d[k])
    except Exception:
        pass
    try:
        with open(os.path.join(DATA_DIR, "last_live.jpg"), "rb") as fh:
            STATE.img_cache = fh.read() or None
    except Exception:
        pass
    try:
        hp = os.path.join(DATA_DIR, "history.jsonl")
        with open(hp, encoding="utf-8") as fh:
            lines = fh.readlines()[-2880:]
        cutoff = time.time() - 86400
        for ln in lines:
            try:
                s = json.loads(ln)
                if s.get("t", 0) >= cutoff:
                    STATE.history.append(s)
            except Exception:
                continue
        if os.path.getsize(hp) > 4_000_000:
            with open(hp, "w", encoding="utf-8") as fh:
                fh.writelines(lines)
    except Exception:
        pass
    STATE.capture_count = sum(len(f) for _, _, f in os.walk(CAP_DIR))


def list_captures():
    out = []
    for root, _, files in os.walk(CAP_DIR):
        for f in files:
            if f.lower().endswith((".jpg", ".jpeg", ".png")):
                full = os.path.join(root, f)
                try:
                    st = os.stat(full)
                except OSError:
                    continue
                out.append({"file": os.path.relpath(full, CAP_DIR).replace("\\", "/"),
                            "target": os.path.basename(root), "name": f, "size": st.st_size,
                            "mtime": int(st.st_mtime),
                            "when": datetime.datetime.fromtimestamp(st.st_mtime).strftime("%b %d %H:%M")})
    out.sort(key=lambda c: -c["mtime"])
    return out


def capture_path(rel):
    """Resolve a capture path safely (no escaping CAP_DIR)."""
    base = os.path.realpath(CAP_DIR)
    full = os.path.realpath(os.path.join(base, rel))
    if full != base and full.startswith(base + os.sep) and os.path.isfile(full):
        return full
    return None


class Housekeeper(threading.Thread):
    daemon = True

    def __init__(self):
        super().__init__(name="housekeeper")
        self.last_sample = 0.0
        self.last_thumb = 0.0
        self.last_thumb_path = None
        self.last_save = 0.0
        self.last_saved_key = None
        self.was_connected = False

    def run(self):
        while True:
            try:
                self.step()
            except Exception as e:
                STATE.note("net", f"housekeeper: {e}")
            time.sleep(3)

    def step(self):
        now = time.time()
        with STATE.lock:
            conn = STATE.connected
            authed = STATE.authed
            host = STATE.host
            thumb, full = STATE.img_thumb_path, STATE.img_full_path
            frames, target = STATE.stacked_frame, STATE.target_name
            working = STATE.stack_state == "working"
        # --- history sample + last-known state ---
        if now - self.last_sample >= 30 or conn != self.was_connected:
            self.last_sample = now
            with STATE.lock:
                s = {"t": int(now), "on": 1 if conn else 0, "b": STATE.battery if conn else None,
                     "c": STATE.temp if conn else None, "f": STATE.stacked_frame if conn else None,
                     "d": STATE.dropped_frame if conn else None, "ch": 1 if STATE.charging else 0}
                STATE.history.append(s)
                persist = {k: getattr(STATE, k) for k in PERSIST}
            if conn or conn != self.was_connected:
                try:
                    with open(os.path.join(DATA_DIR, "history.jsonl"), "a", encoding="utf-8") as fh:
                        fh.write(json.dumps(s) + "\n")
                except Exception:
                    pass
            if conn:
                try:
                    tmp = os.path.join(DATA_DIR, "last_state.json.tmp")
                    with open(tmp, "w", encoding="utf-8") as fh:
                        json.dump(persist, fh)
                    os.replace(tmp, os.path.join(DATA_DIR, "last_state.json"))
                except Exception:
                    pass
            if self.was_connected and not conn:
                with STATE.lock:
                    b, ch = STATE.battery, STATE.charging
                if b is not None and b <= 10 and not ch:
                    STATE.note("net", f"Scope dropped with battery at {b}% - probably out of power.")
            self.was_connected = conn
        if not (conn and authed):
            return
        # --- live thumbnail cache (one fetch shared by every browser) ---
        if thumb and (thumb != self.last_thumb_path or now - self.last_thumb >= 15):
            self.last_thumb = now
            body = scope_http_get(host, thumb, timeout=6)
            if body and len(body) > 500:
                changed = body != STATE.img_cache
                self.last_thumb_path = thumb
                if changed:
                    with STATE.lock:
                        STATE.img_cache = body
                        STATE.img_rev += 1
                    try:
                        with open(os.path.join(DATA_DIR, "last_live.jpg"), "wb") as fh:
                            fh.write(body)
                    except Exception:
                        pass
        # --- auto-save the full-resolution stack to this PC ---
        if (AUTOSAVE_MIN > 0 and full and working and frames
                and now - self.last_save >= AUTOSAVE_MIN * 60
                and (full, frames) != self.last_saved_key):
            self.last_save = now
            body = scope_http_get(host, full, timeout=20)
            if body and len(body) > 2000:
                self.last_saved_key = (full, frames)
                self.save_capture(body, target, frames)

    def save_capture(self, body, target, frames):
        d = os.path.join(CAP_DIR, _safe(target))
        os.makedirs(d, exist_ok=True)
        ext = ".png" if body[:4] == b"\x89PNG" else ".jpg"
        tag = frames if isinstance(frames, str) else f"{frames}f"
        name = f"{_safe(target)}_{datetime.datetime.now():%Y%m%d-%H%M%S}_{tag}{ext}"
        with open(os.path.join(d, name), "wb") as fh:
            fh.write(body)
        # keep the newest 30 per target
        olds = sorted((f for f in os.listdir(d)), reverse=True)[30:]
        for f in olds:
            try:
                os.remove(os.path.join(d, f))
            except OSError:
                pass
        with STATE.lock:
            STATE.last_capture = name
            STATE.capture_count = sum(len(f) for _, _, f in os.walk(CAP_DIR))
        STATE.note("save", f"Saved {name} ({len(body) // 1024} KB)")
        return name


HOUSE = None


def history_points(hours, max_pts=360):
    cutoff = time.time() - hours * 3600
    with STATE.lock:
        pts = [s for s in STATE.history if s["t"] >= cutoff]
    if len(pts) > max_pts:
        step = len(pts) / float(max_pts)
        pts = [pts[int(i * step)] for i in range(max_pts)] + [pts[-1]]
    return pts


# ----------------------------------------------------------------------------
# Control action registry -> (method, params)
# Standard community Seestar JSON-RPC shapes. Tune via the Console if needed.
# ----------------------------------------------------------------------------

def build_action(action, p):
    """Map a UI action to (method, params). Shapes follow the official app's
    protocol as documented by seestarpy (decompiled app + traffic captures)
    and seestar_alp."""
    p = p or {}
    if action == "start_view":                      # open a mode; optional target
        body = {"mode": p.get("mode", "star")}
        if p.get("ra") is not None and p.get("dec") is not None:
            body["target_ra_dec"] = [float(p["ra"]), float(p["dec"])]
            body["target_name"] = p.get("target_name", "Target")
            body["lp_filter"] = bool(p.get("lp", False))
        elif p.get("target_name"):
            body["target_name"] = p["target_name"]
        return ("iscope_start_view", body)
    if action == "goto":                            # slew + plate-solve + (auto) stack
        body = {"mode": "star", "target_ra_dec": [float(p["ra"]), float(p["dec"])],
                "target_name": p.get("target_name", "Target"), "lp_filter": bool(p.get("lp", False))}
        if isinstance(p.get("mosaic"), dict):
            body["mosaic"] = {"scale": float(p["mosaic"].get("scale", 1)),
                              "angle": float(p["mosaic"].get("angle", 0))}
        return ("iscope_start_view", body)
    if action == "stop_view":                       # stop everything
        return ("iscope_stop_view", None)
    if action == "stop_stack":
        return ("iscope_stop_view", {"stage": "Stack"})
    if action == "stop_goto":
        return ("iscope_stop_view", {"stage": "AutoGoto"})
    if action == "start_stack":
        return ("iscope_start_stack", {"restart": bool(p.get("restart", False))})
    if action == "scan_planet":
        return ("start_scan_planet", None)
    if action == "slew":                            # move only, no imaging
        return ("scope_goto", [float(p["ra"]), float(p["dec"])])
    if action == "sync":
        return ("scope_sync", [float(p["ra"]), float(p["dec"])])
    if action == "autofocus_start":
        return ("start_auto_focuse", None)
    if action == "autofocus_stop":
        return ("stop_auto_focuse", None)
    if action in ("focus_move", "focus_to"):        # firmware takes an ABSOLUTE position
        if action == "focus_to":
            pos = int(p["pos"])
        else:
            with STATE.lock:
                cur = STATE.focuser_pos
            if cur is None:
                raise ValueError("focuser position not known yet")
            pos = int(cur) + int(p.get("step", 0))
        if not 1200 <= pos <= 2600:
            raise ValueError("focuser range is 1200-2600")
        return ("move_focuser", {"step": pos, "ret_step": True})
    if action == "mount_move":
        return ("scope_speed_move", {"speed": int(p.get("speed", 500)),
                                     "angle": int(p.get("angle", 0)),
                                     "dur_sec": int(p.get("dur_sec", 1))})
    if action == "park":
        # scope_park also SETS the mount mode - keep whatever it is in now
        with STATE.lock:
            eq = bool((STATE.mount or {}).get("equ_mode"))
        return ("scope_park", {"equ_mode": eq})
    if action == "eq_mode":                         # park into EQ mode
        return ("scope_park", {"equ_mode": bool(p.get("on", True))})
    if action == "open_arm":
        return ("scope_move_to_horizon", None)
    if action == "tracking":
        return ("scope_set_track_state", bool(p.get("on")))
    if action == "set_gain":
        return ("set_control_value", ["gain", int(p["value"])])
    if action == "set_exposure":
        return ("set_setting", {"exp_ms": {"stack_l": int(p["value"])}})
    if action == "set_preview_exposure":
        return ("set_setting", {"exp_ms": {"continuous": int(p["value"])}})
    if action == "lp_filter":                       # moves the filter wheel
        return ("set_setting", {"stack_lenhance": bool(p.get("on"))})
    if action == "wheel":                           # 0 dark, 1 IR-cut, 2 LP
        return ("set_wheel_position", [int(p["pos"])])
    if action == "setting":                         # generic whitelisted set_setting
        key = p.get("key")
        if key not in ALLOWED_SETTINGS:
            raise ValueError(f"setting '{key}' is not allowed here - use the Console")
        return ("set_setting", {key: p.get("value")})
    if action == "dew_heater":
        return ("pi_output_set2", {"heater": {"state": bool(p.get("on")),
                                              "value": int(p.get("value", 90))}})
    if action == "dark_frame":
        return ("start_create_dark", None)
    if action == "dark_stop":
        return ("stop_create_dark", None)
    if action == "solve":
        return ("start_solve", None)
    if action == "polar_align":
        return ("start_polar_align", {"restart": True, "dec_pos_index": 3})
    if action == "polar_align_stop":
        return ("stop_polar_align", None)
    if action == "record_start":
        body = {"raw": bool(p.get("raw", False))}
        if int(p.get("timelapse", 0) or 0) > 0:
            body["timelapse"] = {"enable": True, "delay_sec": int(p["timelapse"])}
        return ("start_record_avi", body)
    if action == "record_stop":
        return ("stop_record_avi", None)
    if action == "set_location":
        lat, lon = float(p["lat"]), float(p["lon"])
        if abs(lat) > 90 or abs(lon) > 180:
            raise ValueError("bad latitude / longitude")
        return ("set_user_location", {"lat": lat, "lon": lon, "force": True})
    if action == "sync_time":
        now = datetime.datetime.now()
        return ("pi_set_time", [{"year": now.year, "mon": now.month, "day": now.day,
                                 "hour": now.hour, "min": now.minute, "sec": now.second,
                                 "time_zone": str(p.get("tz") or "UTC")}])
    if action == "play_sound":
        return ("play_sound", {"num": int(p.get("num", 1))})
    if action == "plan_start":
        return ("set_view_plan", make_plan(p))
    if action == "plan_stop":
        return ("stop_func", {"name": "ViewPlan"})
    if action == "plan_clear":
        return ("clear_view_plan", None)
    if action == "delete_image":
        names = [str(n) for n in (p.get("names") or []) if n and ".." not in str(n)]
        if not names:
            raise ValueError("nothing to delete")
        return ("delete_image", {"name": names})
    if action == "reboot":
        return ("pi_reboot", None)
    if action == "shutdown":
        return ("pi_shutdown", None)
    raise ValueError(f"unknown action '{action}'")


def make_plan(p):
    """Build the app's set_view_plan payload. start_min = minutes since local
    midnight on the scope's clock (values > 1440 mean after midnight)."""
    items = p.get("list") or []
    if not items:
        raise ValueError("the plan has no targets")
    out = []
    for i, it in enumerate(items):
        ra, dec = float(it["ra"]), float(it["dec"])
        start, dur = int(it["start_min"]), int(it["duration_min"])
        if not (0 <= ra < 24 and -90 <= dec <= 90):
            raise ValueError(f"target {i + 1}: bad coordinates")
        if dur < 1 or not 0 <= start < 2880:
            raise ValueError(f"target {i + 1}: bad start time or duration")
        item = {"target_id": 100000000 + (int(time.time()) + i * 7919) % 899999999,
                "target_name": str(it.get("name") or f"Target {i + 1}"),
                "alias_name": str(it.get("alias") or ""),
                "target_ra_dec": [ra, dec], "lp_filter": bool(it.get("lp", False)),
                "start_min": start, "duration_min": dur}
        mo = it.get("mosaic")
        if isinstance(mo, dict) and float(mo.get("scale", 1)) > 1:
            item["mosaic"] = {"scale": min(2.0, float(mo["scale"])),
                              "angle": float(mo.get("angle", 0))}
        out.append(item)
    return {"plan_name": str(p.get("name") or "Studio plan"),
            "update_time_seestar": datetime.datetime.now().strftime("%Y.%m.%d"),
            "list": out}


# ----------------------------------------------------------------------------
# Live video hub: RTSP (sun / moon / planet / scenery) or binary preview frames
# (star-mode live view) -> MJPEG for the browser. Needs OpenCV + numpy.
# ----------------------------------------------------------------------------

os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")
os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")
try:
    import cv2
    import numpy as np
except Exception:                                   # video is optional
    cv2 = None
    np = None


def _stretch8(arr):
    """Auto-stretch a 16-bit frame to 8-bit for display: neutral dark sky,
    stars kept, noise smoothed."""
    a = cv2.GaussianBlur(arr.astype(np.float32), (5, 5), 0)
    sub = a[::4, ::4]
    if a.ndim == 3:                                  # per-channel sky level
        a -= np.median(sub.reshape(-1, a.shape[2]), axis=0)
    else:
        a -= np.median(sub)
    sub = a[::4, ::4]
    sig = float(1.4826 * np.median(np.abs(sub))) or 1.0
    lo = -sig
    hi = min(max(float(np.percentile(sub, 99.9)), 25 * sig), 80 * sig)
    x = np.clip((a - lo) / (hi - lo), 0, 1)
    x = np.arcsinh(x * 6.0) / np.arcsinh(6.0)
    return (x * 255).astype(np.uint8)


def decode_frame(payload, w, h):
    """Decode one image-port payload to a BGR uint8 array (or None)."""
    if payload[:2] == b"\xff\xd8":
        return cv2.imdecode(np.frombuffer(payload, np.uint8), cv2.IMREAD_COLOR)
    if w and h and len(payload) == w * h * 2:       # raw 16-bit Bayer (GRBG)
        bay = np.frombuffer(payload, np.uint16).reshape((h, w))
        return _stretch8(cv2.cvtColor(bay, cv2.COLOR_BAYER_GRBG2BGR))
    if w and h and len(payload) == w * h * 6:       # 16-bit RGB
        rgb = np.frombuffer(payload, np.uint16).reshape((h, w, 3))
        return _stretch8(rgb[:, :, ::-1])
    pk = payload.find(b"PK\x03\x04")
    if pk >= 0:                                     # streaming zip of raw pixels
        import struct
        import zlib
        fl, el = struct.unpack_from("<HH", payload, pk + 26)
        raw = zlib.decompressobj(-15).decompress(payload[pk + 30 + fl + el:])
        return decode_frame(raw, w, h) if len(raw) in (w * h * 2, w * h * 6) else None
    return None


class VideoHub(threading.Thread):
    daemon = True

    def __init__(self, cam="tele"):
        super().__init__(name="video-" + cam)
        self.cam = cam                 # "tele" = the selected main camera, "wide" = the wide-angle one
        self.raw = None                # last full-size frame (BGR), for the skyline scan
        self.raw_ts = 0.0
        self.cond = threading.Condition()
        self.frame = None
        self.seq = 0
        self.last_want = 0.0
        self.source = None
        self.error = None
        self.frame_ts = 0.0

    def status(self):
        return {"available": cv2 is not None, "source": self.source, "error": self.error,
                "live": bool(self.frame is not None and time.time() - self.frame_ts < 5)}

    def want(self):
        self.last_want = time.time()

    def wanted(self):
        return time.time() - self.last_want < 8

    def publish(self, img):
        self.raw, self.raw_ts = img, time.time()
        h, w = img.shape[:2]
        if max(h, w) > 1280:
            k = 1280.0 / max(h, w)
            img = cv2.resize(img, (int(w * k), int(h * k)), interpolation=cv2.INTER_AREA)
        ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if ok:
            with self.cond:
                self.frame = buf.tobytes()
                self.seq += 1
                self.frame_ts = time.time()
                self.cond.notify_all()

    def run(self):
        if cv2 is None:
            return
        while True:
            with STATE.lock:
                conn, stage, host = STATE.connected, STATE.view_stage, STATE.host
                wide = bool((STATE.settings or {}).get("wide_cam"))
            if not (self.wanted() and conn):
                self.source = None
                time.sleep(0.4)
                continue
            try:
                if stage == "RTSP" and self.cam == "wide":
                    # video modes run both cameras: the wide one streams on 4555
                    self.source = "video"
                    self._run_capture(WIDE_URL or f"rtsp://{host}:4555/stream", stage)
                elif stage == "RTSP":
                    url = VIDEO_URL or f"rtsp://{host}:{4555 if wide else 4554}/stream"
                    self.source = "video"
                    self._run_capture(url, stage)
                elif stage == "ContinuousExposure" and self.cam == "tele":
                    self.source = "preview"
                    self._run_preview(host, IMG_PORT + (4 if wide and IMG_PORT == 4800 else 0), stage)
                else:
                    self.source = None
                    self.error = None
                    time.sleep(0.5)
            except Exception as e:
                self.error = str(e)
                time.sleep(2)

    def _same(self, stage):
        return self.wanted() and STATE.connected and STATE.view_stage == stage

    def _run_capture(self, url, stage):
        cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
        try:
            if not cap.isOpened():
                raise ConnectionError("live video stream is not available")
            self.error = None
            bad, last = 0, 0.0
            while self._same(stage):
                ok, img = cap.read()
                if not ok or img is None:
                    bad += 1
                    if bad > 50:
                        raise ConnectionError("live video stream stopped")
                    time.sleep(0.05)
                    continue
                bad = 0
                if time.time() - last >= 0.07:          # cap ~14 fps
                    last = time.time()
                    self.publish(img)
        finally:
            cap.release()

    def _run_preview(self, host, port, stage):
        s = socket.create_connection((host, port), timeout=6)
        try:
            s.settimeout(1.5)
            s.sendall(b'{"id": 21, "method": "begin_streaming"}\r\n')
            self.error = None
            last_hb = time.time()
            while self._same(stage):
                hdr = self._recv(s, 80, idle_ok=True)
                if hdr is None:                         # nothing yet - re-check the mode
                    if time.time() - last_hb > 4:
                        last_hb = time.time()
                        s.sendall(b'{"id": 2, "method": "test_connection"}\r\n')
                    continue
                if hdr[:2] != b"\x03\xc3":              # a JSON reply line, not a frame
                    continue
                import struct
                _, _, hsize, size, _, _, _code, _fid, w, h = struct.unpack(">HHHIHHBBHH", hdr[:20])
                if 80 < hsize <= 4096:
                    self._recv(s, hsize - 80)
                payload = self._recv(s, size) if size else b""
                if size > 1000:
                    img = decode_frame(payload, w, h)
                    if img is not None:
                        self.publish(img)
                if time.time() - last_hb > 4:
                    last_hb = time.time()
                    s.sendall(b'{"id": 2, "method": "test_connection"}\r\n')
            try:
                s.sendall(b'{"id": 22, "method": "stop_streaming"}\r\n')
            except Exception:
                pass
        finally:
            s.close()

    @staticmethod
    def _recv(s, n, idle_ok=False):
        buf, waited = b"", 0
        while len(buf) < n:
            try:
                d = s.recv(min(65536, n - len(buf)))
            except socket.timeout:
                if idle_ok and not buf:
                    return None
                waited += 1
                if waited > 8:
                    raise ConnectionError("image stream stalled")
                continue
            if not d:
                raise ConnectionError("image stream closed")
            buf += d
        return buf


HUB = None
HUB_W = None                     # second hub: the wide-angle camera
SKY = None                       # skyline scan job


class ScanRig:
    """What the skyline scan needs from Studio (see seestar_skyline.SkylineScan)."""

    def call(self, method, params=None):
        return SCOPE.call(method, params, timeout=20)

    def pointing(self):
        r = SCOPE.call("scope_get_horiz_coord", None, timeout=10)
        v = r.get("result") if isinstance(r, dict) else None
        if isinstance(v, dict):
            v = [v.get("alt"), v.get("az")]
        if isinstance(v, list) and len(v) == 2 and v[0] is not None:
            with STATE.lock:
                STATE.altaz = {"alt": v[0], "az": v[1]}
            return float(v[0]), float(v[1])
        return None

    def mount(self):
        r = SCOPE.call("get_device_state", {"keys": ["mount"]}, timeout=10)
        m = (r.get("result") or {}).get("mount") if isinstance(r, dict) else None
        if isinstance(m, dict):
            with STATE.lock:
                STATE.mount = m
            return m
        with STATE.lock:
            return dict(STATE.mount or {})

    def site(self):
        with STATE.lock:
            return (STATE.lat, STATE.lon) if STATE.lat is not None and STATE.lon is not None else None

    def view(self):
        with STATE.lock:
            return STATE.view_state, STATE.view_stage

    def frame(self, newer_than):
        if HUB_W is None:
            return None
        HUB_W.want()
        return HUB_W.raw.copy() if HUB_W.raw is not None and HUB_W.raw_ts > newer_than else None

    def log(self, text):
        STATE.note("scan", text)


class SkyArm(threading.Thread):
    """'Scan at the next twilight': starts the skyline scan by itself, once,
    when the scope has been idle for a while (no view, no plan) and the Sun is
    between 3.5 and 12 degrees below the horizon. Survives a Studio restart."""
    daemon = True
    TWILIGHT = (-12.0, -3.5)

    def __init__(self):
        super().__init__(name="skyarm")
        self.opts = None
        self.idle_since = None
        try:
            with open(os.path.join(DATA_DIR, "skyline_arm.json"), encoding="utf-8") as fh:
                self.opts = json.load(fh)
        except Exception:
            pass

    def arm(self, max_alt):
        self.opts = {"max_alt": float(max_alt), "armed_at": time.strftime("%Y-%m-%d %H:%M:%S")}
        self.idle_since = None
        with open(os.path.join(DATA_DIR, "skyline_arm.json"), "w", encoding="utf-8") as fh:
            json.dump(self.opts, fh)
        STATE.note("scan", "Skyline scan armed for the next twilight.")

    def disarm(self):
        self.opts = None
        try:
            os.remove(os.path.join(DATA_DIR, "skyline_arm.json"))
        except OSError:
            pass

    def run(self):
        while True:
            time.sleep(20)
            try:
                self.tick()
            except Exception as e:
                STATE.note("scan", f"Skyline arming check failed: {e}")

    def tick(self):
        if not self.opts or SKY is None:
            return
        now = time.time()
        with STATE.lock:
            conn = STATE.connected and STATE.authed and bool(STATE.settings)
            busy = STATE.view_state == "working" or (STATE.plan or {}).get("state") == "working"
            lat, lon = STATE.lat, STATE.lon
        if not conn or lat is None or lon is None:
            self.idle_since = None
            return
        sun = skyline.sun_altaz(now, lat, lon)[0]
        if not (self.TWILIGHT[0] <= sun <= self.TWILIGHT[1]) or busy or SKY.status()["state"] == "running":
            self.idle_since = None
            return
        self.idle_since = self.idle_since or now
        if now - self.idle_since < 75:               # let a plan that just ended finish parking
            return
        opts = self.opts
        self.disarm()
        STATE.note("scan", f"Twilight and the scope is idle (Sun {sun:.1f} deg) - starting the armed skyline scan.")
        SKY.start(max_alt=opts.get("max_alt", 40))


ARM = None


def skyline_info():
    doc = skyline.load_horizon(DATA_DIR) or {}
    lat, lon = STATE.lat, STATE.lon          # no lock: this runs inside State.snapshot()
    sun = skyline.sun_altaz(time.time(), lat, lon)[0] if lat is not None and lon is not None else None
    return {"scan": SKY.status() if SKY else {"state": "idle"},
            "updated": doc.get("updated"), "known_deg": doc.get("known_deg"),
            "complete": doc.get("complete"), "ended": doc.get("ended"),
            "armed": ARM.opts if ARM else None,
            "sun_alt": None if sun is None else round(sun, 1), "sun_start": skyline.SUN_START,
            "has_image": os.path.exists(os.path.join(DATA_DIR, "skyline.jpg"))}


# ----------------------------------------------------------------------------
# Web server
# ----------------------------------------------------------------------------

SCOPE = None  # set in main()


class Handler(BaseHTTPRequestHandler):
    scope_host = "192.168.1.100"

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="text/html; charset=utf-8", extra=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        try:
            self.wfile.write(body)
        except Exception:
            pass

    def _json(self, code, obj):
        self._send(code, json.dumps(obj), "application/json")

    def _read_body(self):
        try:
            n = int(self.headers.get("Content-Length", 0))
            return json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return {}

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        if path == "/api/state":
            self._json(200, STATE.snapshot())
        elif path == "/api/albums":
            with STATE.lock:
                self._json(200, {"albums": STATE.albums or []})
        elif path == "/api/image":
            kind = "full" if qs.get("kind", ["thumb"])[0] == "full" else "thumb"
            dl = qs.get("dl", [""])[0] == "1"
            with STATE.lock:
                p = STATE.img_full_path if kind == "full" else STATE.img_thumb_path
                host = STATE.host or self.scope_host
                cache, conn = STATE.img_cache, STATE.connected
                tname = STATE.target_name
            extra = ({"Content-Disposition": f'attachment; filename="{_safe(tname)}.jpg"'}
                     if dl else {})
            body = None
            if kind == "thumb" and cache:
                body = cache
            elif conn and p:
                body = scope_http_get(host, p)
            if not body and kind == "full":      # offline: newest auto-saved capture
                caps = list_captures()
                mine = [c for c in caps if c["target"] == _safe(tname)] or caps
                if mine:
                    try:
                        with open(capture_path(mine[0]["file"]), "rb") as fh:
                            body = fh.read()
                    except Exception:
                        body = None
            body = body or cache
            if not body:
                self._send(204, b"", "text/plain")
            else:
                self._send(200, body, self._ctype(body), extra)
        elif path == "/api/video":
            self._serve_video(HUB_W if qs.get("cam", [""])[0] == "wide" else HUB)
        elif path == "/api/horizon":
            self._json(200, {"horizon": skyline.load_horizon(DATA_DIR), **skyline_info()})
        elif path == "/api/skyline.jpg":
            try:
                with open(os.path.join(DATA_DIR, "skyline.jpg"), "rb") as fh:
                    self._send(200, fh.read(), "image/jpeg")
            except OSError:
                self._send(404, b"", "text/plain")
        elif path == "/api/video_frame":
            hub = HUB_W if qs.get("cam", [""])[0] == "wide" else HUB
            if hub:
                hub.want()
            fr = hub.frame if hub else None
            if fr:
                self._send(200, fr, "image/jpeg")
            else:
                self._send(204, b"", "text/plain")
        elif path == "/api/history":
            try:
                hrs = max(0.25, min(24.0, float(qs.get("h", ["6"])[0])))
            except ValueError:
                hrs = 6.0
            self._json(200, {"hours": hrs, "points": history_points(hrs)})
        elif path == "/api/captures":
            self._json(200, {"captures": list_captures()[:200], "dir": os.path.abspath(CAP_DIR)})
        elif path == "/api/capture":
            full = capture_path(qs.get("f", [""])[0])
            if not full:
                self._send(404, "not found", "text/plain")
            else:
                with open(full, "rb") as fh:
                    body = fh.read()
                extra = ({"Content-Disposition": f'attachment; filename="{os.path.basename(full)}"'}
                         if qs.get("dl", [""])[0] == "1" else {})
                self._send(200, body, self._ctype(body), extra)
        elif path == "/manifest.json":
            self._json(200, {"name": "Seestar Studio", "short_name": "Seestar", "display": "standalone",
                             "start_url": "/", "background_color": "#05070e", "theme_color": "#05070e",
                             "icons": [{"src": "/icon.svg", "sizes": "any", "type": "image/svg+xml"}]})
        elif path == "/icon.svg":
            self._send(200, ICON_SVG, "image/svg+xml")
        elif path == "/api/model":                      # 3D scope model for the Mount tab
            try:
                with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                       "seestar_model.json"), "rb") as fh:
                    self._send(200, fh.read(), "application/json")
            except OSError:
                self._send(404, b"{}", "application/json")
        elif path == "/api/album_image":
            rel = qs.get("path", [""])[0]
            with STATE.lock:
                host = STATE.host or self.scope_host
            if not rel:
                self._send(400, b"", "text/plain")
            else:
                self._serve_scope_image(host, rel)
        elif path == "/" or path.startswith("/index"):
            self._send(200, STUDIO_HTML)
        else:
            self._send(404, "not found", "text/plain")

    def _serve_scope_image(self, host, p):
        if not p:
            self._send(204, b"", "text/plain")
            return
        body = scope_http_get(host, p)
        if not body:
            self._send(502, b"", "text/plain")
            return
        self._send(200, body, self._ctype(body))

    def _serve_video(self, HUB):
        """MJPEG stream of the scope's live view (multipart/x-mixed-replace)."""
        if HUB is None or cv2 is None:
            self._send(503, "live video needs the opencv-python package", "text/plain")
            return
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        seq, idle = -1, 0
        try:
            while idle < 40:                          # give up after ~40 s without frames
                HUB.want()
                with HUB.cond:
                    if HUB.seq == seq:
                        HUB.cond.wait(1.0)
                    fr, cur = HUB.frame, HUB.seq
                if fr is None or cur == seq:
                    idle += 1
                    continue
                idle, seq = 0, cur
                self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                                 + str(len(fr)).encode() + b"\r\n\r\n" + fr + b"\r\n")
        except Exception:
            pass

    @staticmethod
    def _ctype(body):
        return "image/png" if body[:4] == b"\x89PNG" else "image/jpeg"

    def _same_origin(self):
        """Block cross-site requests: a random web page must not be able to make
        the browser POST control commands to this local server."""
        if not (self.headers.get("Content-Type") or "").lower().startswith("application/json"):
            return False
        origin = self.headers.get("Origin")
        if origin and urllib.parse.urlparse(origin).netloc != (self.headers.get("Host") or ""):
            return False
        return True

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if not self._same_origin():
            self._json(403, {"ok": False, "error": "cross-site request blocked"})
            return
        body = self._read_body()
        if SCOPE is None:
            self._json(503, {"ok": False, "error": "scope client not ready"})
            return
        try:
            if path == "/api/save_now":
                with STATE.lock:
                    host, full = STATE.host, STATE.img_full_path
                    conn = STATE.connected
                    tname, frames = STATE.target_name, STATE.stacked_frame or 0
                data = scope_http_get(host, full, timeout=20) if (conn and full) else None
                if not data or len(data) < 2000:
                    self._json(504, {"ok": False, "error": "no image available from the scope"})
                else:
                    self._json(200, {"ok": True, "name": HOUSE.save_capture(data, tname, frames)})
            elif path == "/api/snapshot":
                fr = HUB.frame if HUB else None
                if not fr or time.time() - HUB.frame_ts > 10:
                    self._json(504, {"ok": False, "error": "no live video frame to save"})
                else:
                    with STATE.lock:
                        tname = STATE.target_name if STATE.mode == "star" else (STATE.mode or "live")
                    self._json(200, {"ok": True, "name": HOUSE.save_capture(fr, tname, "snap")})
            elif path == "/api/skyline":
                act = body.get("action")
                if act in ("start", "arm") and not DEMO:
                    # 2026-11-18: on the real S30 the first scope_goto turned the base
                    # almost a full circle (firmware routing) and the guard could not
                    # stop a move in progress. Locked until the scan drives the base
                    # itself and reads the real axle angle (scope_get_axle_coord).
                    self._json(409, {"ok": False, "error":
                                     "The skyline scan is switched off for the real scope until its "
                                     "cable protection has been reworked (see DOCUMENTATION.md). "
                                     "It still runs in demo mode."})
                elif act == "start":
                    with STATE.lock:
                        conn, busy = STATE.connected and STATE.authed, STATE.view_state == "working"
                        plan = (STATE.plan or {}).get("state") == "working"
                        lat, lon = STATE.lat, STATE.lon
                    sun = skyline.sun_altaz(time.time(), lat, lon)[0] if lat is not None and lon is not None else None
                    if sun is not None and sun >= skyline.SUN_START:
                        self._json(409, {"ok": False, "error":
                                         "The Sun is %s. The scan only runs in twilight or at night, so the "
                                         "telescope is never swept past the Sun - use 'Scan at next twilight'."
                                         % ("up" if sun > 0 else "only %.1f degrees below the horizon" % -sun)})
                    elif not conn:
                        self._json(409, {"ok": False, "error": "the scope is not connected"})
                    elif busy or plan:
                        self._json(409, {"ok": False, "error": "the scope is busy - stop the current "
                                                               "view or plan before scanning the skyline"})
                    else:
                        try:
                            SKY.start(max_alt=body.get("max_alt", 40), hfov=body.get("hfov"))
                            self._json(200, {"ok": True})
                        except RuntimeError as e:
                            self._json(409, {"ok": False, "error": str(e)})
                elif act == "abort":
                    SKY.abort()
                    self._json(200, {"ok": True})
                elif act == "arm":
                    ARM.arm(max(15.0, min(60.0, float(body.get("max_alt", 40)))))
                    self._json(200, {"ok": True})
                elif act == "disarm":
                    ARM.disarm()
                    self._json(200, {"ok": True})
                elif act == "clear":
                    for fn in ("horizon.json", "skyline.jpg"):
                        try:
                            os.remove(os.path.join(DATA_DIR, fn))
                        except OSError:
                            pass
                    self._json(200, {"ok": True})
                else:
                    self._json(400, {"ok": False, "error": "unknown skyline action"})
            elif path == "/api/action":
                method, params = build_action(body.get("action"), body.get("params"))
                reply = SCOPE.call(method, params, timeout=float(body.get("timeout", 15)))
                ok = isinstance(reply, dict) and reply.get("code") in (0, None)
                self._json(200, {"ok": ok, "method": method,
                                 "code": reply.get("code") if isinstance(reply, dict) else None,
                                 "reply": reply})
            elif path == "/api/rpc":
                method = body.get("method")
                if not method:
                    self._json(400, {"ok": False, "error": "method required"})
                    return
                params = body.get("params", None)
                reply = SCOPE.call(method, params, timeout=float(body.get("timeout", 15)))
                self._json(200, {"ok": isinstance(reply, dict) and reply.get("code") in (0, None),
                                 "reply": reply})
            else:
                self._json(404, {"ok": False, "error": "no such endpoint"})
        except PermissionError as e:
            self._json(403, {"ok": False, "error": str(e)})
        except (ConnectionError, TimeoutError) as e:
            self._json(504, {"ok": False, "error": str(e)})
        except Exception as e:
            self._json(400, {"ok": False, "error": str(e)})


# The big HTML/CSS/JS SPA lives in a separate module-level string for clarity.
from seestar_studio_ui import STUDIO_HTML  # noqa: E402

ICON_SVG = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><defs><linearGradient id="g" '
            'x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#6ea8ff"/><stop offset="1" '
            'stop-color="#9b7cff"/></linearGradient></defs><rect width="64" height="64" rx="14" '
            'fill="#05070e"/><path d="M32 8l5.5 18.5L56 32l-18.5 5.5L32 56l-5.5-18.5L8 32l18.5-5.5z" '
            'fill="url(#g)"/></svg>')


# ----------------------------------------------------------------------------
# Bind helpers + main
# ----------------------------------------------------------------------------

def tailscale_ip():
    import subprocess
    for exe in ("tailscale", r"C:\Program Files\Tailscale\tailscale.exe",
                r"C:\Program Files (x86)\Tailscale IPN\tailscale.exe"):
        try:
            out = subprocess.run([exe, "ip", "-4"], capture_output=True, text=True, timeout=5)
            for line in (out.stdout or "").splitlines():
                if line.strip().startswith("100."):
                    return line.strip()
        except Exception:
            continue
    for ip in _local_ipv4s():
        try:
            a, b = int(ip.split(".")[0]), int(ip.split(".")[1])
            if a == 100 and 64 <= b <= 127:
                return ip
        except Exception:
            continue
    return None


def resolve_binds(spec):
    out = []
    for part in spec.split(","):
        part = part.strip().lower()
        if part in ("tailscale", "ts", "tailnet"):
            out.append("127.0.0.1")
            tip = tailscale_ip()
            if tip:
                out.append(tip)
        elif part in ("all", "0.0.0.0", "any"):
            out.append("0.0.0.0")
        elif part:
            out.append(part)
    seen, uniq = set(), []
    for a in out:
        if a not in seen:
            seen.add(a); uniq.append(a)
    return uniq or ["127.0.0.1"]


class ExclusiveServer(ThreadingHTTPServer):
    # On Windows the default (SO_REUSEADDR) silently lets a SECOND copy bind the
    # same port, and requests then go to either copy at random. Refuse instead.
    allow_reuse_address = False
    daemon_threads = True


def main():
    global SCOPE
    ap = argparse.ArgumentParser(description="Full web control center for a ZWO Seestar.")
    ap.add_argument("--host", default="192.168.1.100")
    ap.add_argument("--port", type=int, default=4700)
    ap.add_argument("--web", type=int, default=5557)
    ap.add_argument("--key", default=None)
    ap.add_argument("--bind", default="127.0.0.1")
    ap.add_argument("--scope-http", type=int, default=80, help="scope file-server port")
    ap.add_argument("--data", default=None, help="folder for data/ and captures/")
    ap.add_argument("--autosave", type=float, default=10,
                    help="auto-save the full-res stack to this PC every N minutes (0 = off)")
    ap.add_argument("--demo", action="store_true",
                    help="run against a built-in SIMULATED scope (safe to click anything)")
    args = ap.parse_args()

    global SCOPE_HTTP_PORT, DATA_DIR, CAP_DIR, AUTOSAVE_MIN, DEMO, HOUSE, HUB, VIDEO_URL, IMG_PORT
    global HUB_W, SKY, WIDE_URL, ARM
    here_dir = os.path.dirname(os.path.abspath(__file__))
    root = args.data or (os.path.join(here_dir, "demo_data") if args.demo else here_dir)
    DATA_DIR = os.path.join(root, "data")
    CAP_DIR = os.path.join(root, "captures")
    AUTOSAVE_MIN = max(0.0, args.autosave)
    SCOPE_HTTP_PORT = args.scope_http
    demo_signer = None
    if args.demo:
        from seestar_sim import SimScope
        sim = SimScope(port=0, http_port=0, drain=0.5).start()
        DEMO = True
        args.host, args.port, SCOPE_HTTP_PORT = "127.0.0.1", sim.port, sim.http_port
        VIDEO_URL = f"http://127.0.0.1:{sim.http_port}/stream.mjpg"
        WIDE_URL = f"http://127.0.0.1:{sim.http_port}/wide.mjpg"
        IMG_PORT = sim.img_port
        AUTOSAVE_MIN = min(AUTOSAVE_MIN, 1) if AUTOSAVE_MIN else 0
        demo_signer = lambda ch: "demo"          # noqa: E731  (sim accepts any signature)
        with STATE.lock:
            STATE.have_key = True
    load_persisted()

    key_path = args.key
    if not key_path:
        here = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seestar.pem")
        env = os.environ.get("SEESTAR_KEY_PATH")
        if env and os.path.isfile(env):
            key_path = env
        elif os.path.isfile(here):
            key_path = here
    signer = demo_signer or (load_signer(key_path) if key_path else None)

    STATE.host = args.host
    SCOPE = ScopeClient(args.host, args.port, signer=signer)
    SCOPE.discover = not args.demo
    SCOPE.start()
    HOUSE = Housekeeper()
    HOUSE.start()
    HUB = VideoHub()
    HUB.start()
    HUB_W = VideoHub("wide")
    HUB_W.start()
    SKY = skyline.SkylineScan(ScanRig(), DATA_DIR)
    ARM = SkyArm()
    ARM.start()

    Handler.scope_host = args.host
    binds = resolve_binds(args.bind)
    servers = []
    for addr in binds:
        try:
            servers.append((addr, ExclusiveServer((addr, args.web), Handler)))
        except Exception as e:
            print(f"  ! could not bind {addr}:{args.web} - {e}")
            print("    (is another Seestar Studio / Monitor already running on that port?)")
    if not servers:
        print("  No listener could be started."); return

    print("=" * 62)
    print("  Seestar Studio")
    print("=" * 62)
    print(f"  Scope : {args.host}:{args.port}")
    print(f"  Mode  : {'DEMO - simulated scope' if args.demo else 'FULL CONTROL (key loaded)' if signer else 'monitor only (no key)'}")
    print(f"  Saves : {CAP_DIR}  (every {AUTOSAVE_MIN:g} min)" if AUTOSAVE_MIN else "  Saves : auto-save off")
    print(f"  Video : {'live view enabled' if cv2 is not None else 'off (pip install opencv-python numpy)'}")
    print("  Open  :")
    for addr, _ in servers:
        print(f"            http://{'127.0.0.1' if addr=='0.0.0.0' else addr}:{args.web}")
    if any(a.startswith('100.') for a, _ in servers):
        print("          (100.x = reachable from any device on your tailnet)")
    print("  Ctrl+C to stop.")
    print("=" * 62)
    for addr, srv in servers[1:]:
        threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        servers[0][1].serve_forever()
    except KeyboardInterrupt:
        print("\nStopping.")


if __name__ == "__main__":
    main()
