#!/usr/bin/env python3
"""
Seestar Monitor - a lightweight, local web dashboard for a ZWO Seestar telescope.

A tiny, fast replacement for the official Seestar app when all you want is to
*watch* a running observation from your PC's browser - without running a heavy
Android emulator. Runs in a terminal, serves a dashboard on
http://127.0.0.1:5556 .

Two modes
---------
* monitor mode (no key): listens passively to the scope's unauthenticated event
  broadcast (stacking progress, exposure state, temperature). Zero risk to the
  observation.
* full mode (key present): newer firmware (7.18+) gates device state, the live
  image and everything else behind an RSA challenge-response. If `seestar.pem`
  (the interop key) sits next to this file, the tool completes the handshake and
  additionally shows: target name, RA/Dec, battery, disk, full stack stats, and
  the LIVE STACKED IMAGE, refreshed as stacking progresses.

Safety
------
Strictly READ-ONLY. It only ever calls getters (get_device_state,
get_view_state, get_disk_volume, get_albums, scope_get_equ_coord) and fetches
already-saved images over the scope's HTTP file server. It NEVER sends a command
that could move, stop, or reconfigure the scope, so a running plan is never
disturbed.

Usage
-----
    python seestar_monitor.py --host 192.168.1.100
    then open  http://127.0.0.1:5556

Options:
    --host  Seestar IP on your LAN   (default 192.168.1.100)
    --port  control port             (default 4700)
    --web   local web UI port        (default 5556)
    --key   path to interop PEM      (default ./seestar.pem if present)

Monitor mode needs only the Python standard library. Full mode also needs the
`cryptography` package (pip install cryptography).
"""

import argparse
import base64
import datetime
import json
import os
import re
import socket
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TS_RE = re.compile(r"(\d{8})-(\d{6})")   # 20261117-000001 inside image filenames


# ----------------------------------------------------------------------------
# Shared, thread-safe state
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

        # From the broadcast event stream (always available)
        self.stack_state = None
        self.stacked_frame = None
        self.dropped_frame = None
        self.can_annotate = None
        self.stack_lapse_ms = None
        self.exp_state = None
        self.exp_ms = None
        self.gain = None
        self.exp_page = None
        self.temp = None

        # From authenticated polling (full mode only)
        self.target_name = None
        self.ra = None
        self.dec = None
        self.mode = None
        self.view_state = None
        self.battery = None
        self.charging = None
        self.charger_status = None
        self.disk_free_mb = None
        self.disk_total_mb = None
        self.model = None
        self.firmware = None
        self.sn = None
        self.annotation_count = None

        # Live image (full mode): current best path on the scope HTTP server
        self.img_thumb_path = None    # e.g. MyWorks/.../..._thn.jpg
        self.img_full_path = None
        self.img_updated = None       # wall time we last refreshed the path
        self.img_label = None

        self.log = []
        self.MAXLOG = 400

    def note(self, kind, text):
        with self.lock:
            self.log.append({
                "t": datetime.datetime.now().strftime("%H:%M:%S"),
                "kind": kind, "text": text,
            })
            if len(self.log) > self.MAXLOG:
                self.log = self.log[-self.MAXLOG:]

    def snapshot(self):
        with self.lock:
            age = (time.time() - self.last_event_ts) if self.last_event_ts else None
            integ = None
            if self.stacked_frame is not None and self.exp_ms:
                integ = int(self.stacked_frame * self.exp_ms / 1000)
            return {
                "connected": self.connected,
                "host": self.host,
                "firmware_gated": self.firmware_gated,
                "authed": self.authed,
                "have_key": self.have_key,
                "connect_count": self.connect_count,
                "seconds_since_event": round(age, 1) if age is not None else None,
                "last_event_wall": self.last_event_wall,
                "stack": {
                    "state": self.stack_state,
                    "stacked_frame": self.stacked_frame,
                    "dropped_frame": self.dropped_frame,
                    "can_annotate": self.can_annotate,
                    "lapse_ms": self.stack_lapse_ms,
                },
                "exposure": {
                    "state": self.exp_state, "exp_ms": self.exp_ms,
                    "gain": self.gain, "page": self.exp_page,
                },
                "temp": self.temp,
                "integration_s": integ,
                "target": {
                    "name": self.target_name, "ra": self.ra, "dec": self.dec,
                    "mode": self.mode, "annotations": self.annotation_count,
                },
                "power": {
                    "battery": self.battery, "charging": self.charging,
                    "charger_status": self.charger_status,
                },
                "disk": {"free_mb": self.disk_free_mb, "total_mb": self.disk_total_mb},
                "device": {"model": self.model, "firmware": self.firmware, "sn": self.sn},
                "image": {
                    "available": self.img_thumb_path is not None,
                    "label": self.img_label, "updated": self.img_updated,
                },
                "server_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "log": self.log[-200:],
            }


STATE = State()


# ----------------------------------------------------------------------------
# Optional RSA signer (firmware 7.18+)
# ----------------------------------------------------------------------------

def load_signer(key_path):
    if not key_path or not os.path.isfile(key_path):
        return None
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
    except Exception:
        STATE.note("auth", "seestar.pem found but 'cryptography' is not installed; "
                           "run: pip install cryptography")
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
    STATE.note("auth", f"Interop key loaded ({os.path.basename(key_path)}); full features enabled.")
    return sign


# ----------------------------------------------------------------------------
# HTTP file fetch from the scope (port 80) - read-only, used only for images
# ----------------------------------------------------------------------------

def discover_seestar(timeout=3):
    """Broadcast the Seestar discovery ping (UDP 4720) and return the first IP
    that answers, or None. Lets the tool keep working if DHCP changes the IP."""
    msg = b'{"id":1,"method":"scan_iscope","params":""}'
    found = None
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
                    if b"result" in data or b"ip" in data or addr:
                        found = addr[0]
                        break
                except socket.timeout:
                    break
            u.close()
            if found:
                return found
        except Exception:
            continue
    return found


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
    try:
        parts = ip.split(".")
        if len(parts) == 4:
            return ".".join(parts[:3]) + ".255"
    except Exception:
        pass
    return None


def scope_http_get(host, path, timeout=6):
    """GET a file from the Seestar's built-in HTTP server. Returns body bytes or None."""
    enc = urllib.parse.quote(path)
    try:
        s = socket.create_connection((host, 80), timeout=timeout)
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
    status = head.split(b"\r\n", 1)[0] if head else b""
    if b"200" not in status:
        return None
    return body


# ----------------------------------------------------------------------------
# Scope client: single-threaded async JSON-RPC
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
        self._inflight = {}
        self._buf = b""

    def _send(self, method, params=None):
        self._rid += 1
        rid = self._rid
        self._inflight[rid] = method
        msg = {"id": rid, "method": method}
        if params is not None:
            msg["params"] = params
        self.sock.sendall((json.dumps(msg) + "\r\n").encode("utf-8"))
        return rid

    # ---- replies to our own requests ----
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
            challenge = (result or {}).get("str") if isinstance(result, dict) else None
            if challenge and self.signer and not STATE.authed:
                try:
                    self._send("verify_client",
                               {"sign": self.signer(challenge), "data": challenge})
                except Exception as e:
                    STATE.note("auth", f"Signing failed: {e}")
        elif method == "verify_client":
            if code == 0:
                self._send("pi_is_verified", "verify")
                with STATE.lock:
                    STATE.authed = True
                STATE.note("auth", "Authenticated - full features enabled.")
            else:
                STATE.note("auth", f"verify_client rejected (code={code}); key not accepted.")
        elif method == "get_device_state":
            if isinstance(result, dict):
                self._apply_device_state(result)
        elif method == "get_view_state":
            if isinstance(result, dict):
                self._apply_view_state(result)
        elif method == "get_disk_volume":
            if isinstance(result, dict):
                with STATE.lock:
                    STATE.disk_total_mb = result.get("totalMB")
                    STATE.disk_free_mb = result.get("freeMB")
        elif method == "scope_get_equ_coord":
            if isinstance(result, dict):
                with STATE.lock:
                    STATE.ra = result.get("ra")
                    STATE.dec = result.get("dec")
        elif method == "get_albums":
            if isinstance(result, dict):
                self._apply_albums(result)

    def _apply_device_state(self, r):
        dev = r.get("device") or {}
        pi = r.get("pi_status") or {}
        with STATE.lock:
            STATE.model = dev.get("user_product_model") or dev.get("product_model")
            STATE.firmware = dev.get("firmware_ver_string")
            STATE.sn = dev.get("sn")
            if "battery_capacity" in pi: STATE.battery = pi["battery_capacity"]
            if "charge_online" in pi: STATE.charging = pi["charge_online"]
            if "charger_status" in pi: STATE.charger_status = pi.get("charger_status")
            if "temp" in pi: STATE.temp = pi["temp"]

    def _apply_view_state(self, r):
        v = r.get("View") or {}
        stack = v.get("Stack") or {}
        exp = stack.get("Exposure") or {}
        ann = stack.get("Annotate") or {}
        with STATE.lock:
            if v.get("target_name"): STATE.target_name = v.get("target_name")
            trd = v.get("target_ra_dec")
            if isinstance(trd, list) and len(trd) == 2:
                STATE.ra, STATE.dec = trd[0], trd[1]
            if v.get("mode"): STATE.mode = v.get("mode")
            if v.get("gain") is not None: STATE.gain = v.get("gain")
            if "stacked_frame" in stack: STATE.stacked_frame = stack["stacked_frame"]
            if "dropped_frame" in stack: STATE.dropped_frame = stack["dropped_frame"]
            if stack.get("state"): STATE.stack_state = stack["state"]
            if exp.get("exp_ms") is not None: STATE.exp_ms = exp["exp_ms"]
            if exp.get("state"): STATE.exp_state = exp["state"]
            ar = (ann.get("result") or {}).get("annotations")
            if isinstance(ar, list): STATE.annotation_count = len(ar)
            STATE.view_state = r

    def _apply_albums(self, r):
        parent = r.get("path", "MyWorks")
        best = None  # (ts_str, thn, name)
        for grp in r.get("list", []) or []:
            for f in grp.get("files", []) or []:
                thn = f.get("thn")
                if not thn or not thn.lower().endswith(".jpg"):
                    continue
                m = TS_RE.search(thn)
                ts = (m.group(1) + m.group(2)) if m else "0"
                # prefer stacked frames (live result) over raw subs
                score = ts + ("1" if "Stacked" in thn else "0")
                if best is None or score > best[0]:
                    best = (score, thn, f.get("name"))
        if best:
            thn = best[1]
            full = thn.replace("_thn.jpg", ".jpg")
            with STATE.lock:
                STATE.img_thumb_path = f"{parent}/{thn}"
                STATE.img_full_path = f"{parent}/{full}"
                STATE.img_label = best[2]
                STATE.img_updated = datetime.datetime.now().strftime("%H:%M:%S")

    # ---- broadcast events ----
    def _handle(self, obj):
        rid = obj.get("id")
        if rid is not None and rid in self._inflight:
            self._handle_reply(self._inflight.pop(rid), obj)
            return
        ev = obj.get("Event")
        if ev is None:
            return
        with STATE.lock:
            STATE.last_event_ts = time.time()
            STATE.last_event_wall = datetime.datetime.now().strftime("%H:%M:%S")
        if ev == "Stack":
            with STATE.lock:
                if obj.get("state"): STATE.stack_state = obj["state"]
                if "stacked_frame" in obj: STATE.stacked_frame = obj["stacked_frame"]
                if "dropped_frame" in obj: STATE.dropped_frame = obj["dropped_frame"]
                if "can_annotate" in obj: STATE.can_annotate = obj["can_annotate"]
                if "lapse_ms" in obj: STATE.stack_lapse_ms = obj["lapse_ms"]
            if obj.get("stacked_frame") is not None:
                STATE.note("stack", f"stacked={obj.get('stacked_frame')} "
                                    f"dropped={obj.get('dropped_frame')} {obj.get('state')}")
        elif ev == "Exposure":
            with STATE.lock:
                if obj.get("state"): STATE.exp_state = obj["state"]
                if "exp_ms" in obj: STATE.exp_ms = obj["exp_ms"]
                if "gain" in obj: STATE.gain = obj["gain"]
                if "page" in obj: STATE.exp_page = obj["page"]
            if obj.get("state") in ("start", "complete"):
                STATE.note("expose", f"{obj.get('page','')} {obj.get('state')}")
        elif ev == "PiStatus":
            with STATE.lock:
                if "temp" in obj: STATE.temp = obj["temp"]
                if "battery_capacity" in obj: STATE.battery = obj["battery_capacity"]
                if "charge_online" in obj: STATE.charging = obj["charge_online"]
        else:
            STATE.note("event", ev)

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
                        if not line.strip():
                            continue
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

                # Monitor mode: stay passive (sending an unanswered verify makes
                # the scope drop us). Full mode: start the handshake.
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
                        if now - last_poll > 4:
                            last_poll = now
                            self._send("get_view_state")
                            self._send("get_device_state")
                            self._send("get_disk_volume")
                        if now - last_albums > 10:
                            last_albums = now
                            self._send("get_albums")
            except Exception as e:
                with STATE.lock:
                    STATE.connected = False
                    STATE.authed = False
                STATE.note("net", f"Disconnected: {e}; retry in {backoff:.0f}s")
                try:
                    if self.sock:
                        self.sock.close()
                except Exception:
                    pass
                time.sleep(backoff)
                backoff = min(backoff * 1.7, 15.0)
                # If we keep failing, the scope's IP may have changed - rediscover.
                if backoff >= 6:
                    newip = discover_seestar(3)
                    if newip and newip != self.host:
                        STATE.note("net", f"Discovered Seestar at {newip} (was {self.host})")
                        self.host = newip
                        with STATE.lock:
                            STATE.host = newip
                        backoff = 1.0


# ----------------------------------------------------------------------------
# Web UI
# ----------------------------------------------------------------------------

DASHBOARD_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Seestar Monitor</title>
<style>
  :root{--bg:#0a0e14;--panel:#121825;--panel2:#0e1420;--line:#1f2a3a;--txt:#e6edf6;
    --muted:#8aa0bd;--accent:#e5484d;--ok:#2ecc71;--warn:#f2c94c;--blue:#4a9eff;--purple:#c07cff}
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--txt);
    font:15px/1.45 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif}
  header{display:flex;align-items:center;gap:12px;padding:14px 20px;flex-wrap:wrap;
    border-bottom:1px solid var(--line);position:sticky;top:0;background:var(--bg);z-index:5}
  header h1{font-size:18px;margin:0;font-weight:650;letter-spacing:.2px}
  .star{color:var(--accent);font-size:22px}
  .pill{font-size:12px;padding:3px 10px;border-radius:999px;border:1px solid var(--line);
    color:var(--muted);white-space:nowrap}
  .pill.live{color:#031;background:var(--ok);border-color:var(--ok);font-weight:650}
  .pill.dead{color:#fff;background:var(--accent);border-color:var(--accent);font-weight:650}
  .pill.mode{color:var(--blue);border-color:#24405f}
  main{max-width:1080px;margin:0 auto;padding:18px 16px 60px}
  .layout{display:grid;grid-template-columns:1.1fr .9fr;gap:16px}
  @media(max-width:820px){.layout{grid-template-columns:1fr}}
  .imgwrap{background:#000;border:1px solid var(--line);border-radius:14px;overflow:hidden;
    position:relative;min-height:240px;display:flex;align-items:center;justify-content:center}
  .imgwrap img{width:100%;display:block}
  .imgwrap .noimg{color:var(--muted);font-size:13px;padding:40px;text-align:center}
  .imgcap{position:absolute;left:0;right:0;bottom:0;padding:8px 12px;font-size:12px;
    background:linear-gradient(transparent,rgba(0,0,0,.75));color:#cfe;display:flex;
    justify-content:space-between;gap:8px}
  .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}
  .card{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:14px 16px}
  .card h3{margin:0 0 6px;font-size:11px;font-weight:600;text-transform:uppercase;
    letter-spacing:.8px;color:var(--muted)}
  .big{font-size:30px;font-weight:700;line-height:1.1;font-variant-numeric:tabular-nums}
  .big.lg{font-size:38px}
  .sub{color:var(--muted);font-size:12.5px;margin-top:3px}
  .row{display:flex;justify-content:space-between;gap:10px;padding:3px 0;
    border-bottom:1px dashed #16202e;font-variant-numeric:tabular-nums}
  .row:last-child{border-bottom:0}.row .k{color:var(--muted)}
  .section-title{margin:22px 4px 10px;font-size:12px;text-transform:uppercase;
    letter-spacing:.8px;color:var(--muted)}
  #log{background:var(--panel2);border:1px solid var(--line);border-radius:14px;
    padding:10px 12px;height:240px;overflow:auto;font:12.5px/1.5 ui-monospace,Consolas,monospace}
  #log .l{display:flex;gap:10px}.l .t{color:#51607a;flex:0 0 62px}
  .kind{flex:0 0 56px;text-transform:uppercase;font-size:10.5px}
  .k-stack{color:var(--ok)}.k-expose{color:var(--blue)}.k-net{color:var(--warn)}
  .k-auth{color:var(--purple)}.k-event{color:var(--muted)}
  .foot{color:#51607a;font-size:12px;margin-top:18px;text-align:center}
  a{color:var(--blue)}
  .bar{height:6px;border-radius:4px;background:#1d2736;margin-top:8px;overflow:hidden}
  .bar>i{display:block;height:100%;background:var(--ok)}
  .banner{background:#10151f;border:1px solid var(--line);color:var(--muted);border-radius:12px;
    padding:10px 14px;margin-bottom:14px;font-size:13px;display:none}
</style>
</head>
<body>
<header>
  <span class="star">&#10022;</span>
  <h1>Seestar Monitor</h1>
  <span id="conn" class="pill">connecting&hellip;</span>
  <span id="mode" class="pill mode">&mdash;</span>
  <span style="flex:1"></span>
  <span id="target" class="pill"></span>
  <span id="host" class="pill"></span>
</header>
<main>
  <div id="banner" class="banner"></div>
  <div class="layout">
    <div>
      <div class="imgwrap">
        <img id="live" alt="" style="display:none">
        <div id="noimg" class="noimg">Live image appears here in full mode.</div>
        <div class="imgcap"><span id="imglabel"></span><span id="imgupdated"></span></div>
      </div>
      <div style="text-align:right;margin-top:6px">
        <a id="full" href="#" target="_blank" style="font-size:12px;display:none">open full-resolution &#8599;</a>
      </div>
    </div>
    <div>
      <div class="grid">
        <div class="card"><h3>Frames stacked</h3><div id="stacked" class="big lg">&mdash;</div>
          <div id="dropped" class="sub">dropped &mdash;</div></div>
        <div class="card"><h3>Integration</h3><div id="integ" class="big">&mdash;</div>
          <div id="integsub" class="sub">&mdash;</div></div>
        <div class="card"><h3>Battery</h3><div id="batt" class="big">&mdash;</div>
          <div class="bar"><i id="battbar" style="width:0%"></i></div>
          <div id="battsub" class="sub">&mdash;</div></div>
        <div class="card"><h3>Sensor temp</h3><div id="temp" class="big">&mdash;</div>
          <div class="sub">CMOS</div></div>
        <div class="card"><h3>Exposure</h3><div id="exp" class="big">&mdash;</div>
          <div id="expsub" class="sub">&mdash;</div></div>
        <div class="card"><h3>Free disk</h3><div id="disk" class="big">&mdash;</div>
          <div id="disksub" class="sub">&mdash;</div></div>
      </div>
    </div>
  </div>

  <div class="section-title">Detail</div>
  <div class="grid">
    <div class="card" style="grid-column:1/-1">
      <div class="row"><span class="k">Target</span><span id="d-target">&mdash;</span></div>
      <div class="row"><span class="k">Coordinates (RA / Dec)</span><span id="d-coord">&mdash;</span></div>
      <div class="row"><span class="k">Mode / gain</span><span id="d-mode">&mdash;</span></div>
      <div class="row"><span class="k">Stars annotated</span><span id="d-annot">&mdash;</span></div>
      <div class="row"><span class="k">Stacking state</span><span id="d-stackstate">&mdash;</span></div>
      <div class="row"><span class="k">Device</span><span id="d-device">&mdash;</span></div>
      <div class="row"><span class="k">Last event</span><span id="d-last">&mdash;</span></div>
      <div class="row"><span class="k">Reconnects</span><span id="d-recon">&mdash;</span></div>
    </div>
  </div>

  <div class="section-title">Event log</div>
  <div id="log"></div>
  <div class="foot">Read-only monitor &middot; your observation is never touched &middot;
    <span id="stime"></span></div>
</main>
<script>
function fmtHMS(s){if(s==null)return "—";s=Math.max(0,Math.floor(s));
  const h=Math.floor(s/3600),m=Math.floor((s%3600)/60),ss=s%60;
  return (h?h+"h ":"")+((h||m)?((m<10&&h?"0":"")+m+"m "):"")+(ss<10?"0":"")+ss+"s";}
function gb(mb){return mb==null?"—":(mb/1024).toFixed(1)+" GB";}
let lastImgTick=0;
async function tick(){
  let d;
  try{ d=await (await fetch("/api/state",{cache:"no-store"})).json(); }
  catch(e){ const c=document.getElementById("conn");c.className="pill dead";c.textContent="server offline";return;}
  const conn=document.getElementById("conn");
  if(d.connected){conn.className="pill live";conn.textContent="LIVE";}
  else{conn.className="pill dead";conn.textContent="scope offline";}
  document.getElementById("host").textContent=d.host||"";
  document.getElementById("mode").textContent=d.authed?"full mode":"monitor mode";
  const tgt=d.target&&d.target.name;
  document.getElementById("target").textContent=tgt?("◉ "+tgt):"";

  const banner=document.getElementById("banner");
  if(d.firmware_gated && !d.authed){banner.style.display="block";
    banner.innerHTML=d.have_key?"Key loaded; completing handshake&hellip;"
      :"Firmware requires a key for full features. Showing the live event stream "+
       "(stacking progress, temperature) only. See README to enable full mode.";
  }else{banner.style.display="none";}

  const st=d.stack||{},ex=d.exposure||{},p=d.power||{},tg=d.target||{},dk=d.disk||{},dv=d.device||{};
  document.getElementById("stacked").textContent=st.stacked_frame!=null?st.stacked_frame:"—";
  document.getElementById("dropped").textContent="dropped "+(st.dropped_frame!=null?st.dropped_frame:"—");
  document.getElementById("integ").textContent=fmtHMS(d.integration_s);
  document.getElementById("integsub").textContent=(st.stacked_frame!=null&&ex.exp_ms)?
    (st.stacked_frame+" × "+(ex.exp_ms/1000)+"s"):"—";
  const b=p.battery;
  document.getElementById("batt").textContent=b!=null?(b+"%"):"—";
  document.getElementById("battbar").style.width=(b!=null?b:0)+"%";
  document.getElementById("battbar").style.background=b!=null&&b<20?"#e5484d":(b!=null&&b<50?"#f2c94c":"#2ecc71");
  document.getElementById("battsub").textContent=p.charging?("charging ("+(p.charger_status||"")+")"):(b!=null?"on battery":"—");
  document.getElementById("temp").textContent=d.temp!=null?d.temp.toFixed(1)+"°":"—";
  document.getElementById("exp").textContent=ex.state||"—";
  document.getElementById("expsub").textContent=((ex.exp_ms?(ex.exp_ms/1000)+"s":"")+(ex.gain!=null?"  gain "+ex.gain:""))||"—";
  document.getElementById("disk").textContent=gb(dk.free_mb);
  document.getElementById("disksub").textContent=dk.total_mb?("of "+gb(dk.total_mb)):"—";

  document.getElementById("d-target").textContent=tg.name||"—";
  document.getElementById("d-coord").textContent=(tg.ra!=null&&tg.dec!=null)?
    (tg.ra.toFixed(4)+"h  /  "+tg.dec.toFixed(4)+"°"):"—";
  document.getElementById("d-mode").textContent=(tg.mode||"—")+(ex.gain!=null?"  /  gain "+ex.gain:"");
  document.getElementById("d-annot").textContent=tg.annotations!=null?tg.annotations:"—";
  document.getElementById("d-stackstate").textContent=st.state||"—";
  document.getElementById("d-device").textContent=dv.model?(dv.model+"  fw "+(dv.firmware||"?")+"  SN "+(dv.sn||"?")):"—";
  document.getElementById("d-last").textContent=(d.last_event_wall||"—")+
    (d.seconds_since_event!=null?("  ("+d.seconds_since_event+"s ago)"):"");
  document.getElementById("d-recon").textContent=d.connect_count!=null?d.connect_count:"—";

  // live image (refresh roughly every 6s to stay light)
  const img=d.image||{};
  if(img.available){
    const now=Date.now();
    if(now-lastImgTick>6000){
      lastImgTick=now;
      const el=document.getElementById("live");
      el.onload=function(){el.style.display="block";document.getElementById("noimg").style.display="none";};
      el.src="/api/image?kind=thumb&v="+now;
      const full=document.getElementById("full");
      full.style.display="inline";full.href="/api/image?kind=full&v="+now;
    }
    document.getElementById("imglabel").textContent=img.label||"";
    document.getElementById("imgupdated").textContent=img.updated?("updated "+img.updated):"";
  }

  const logEl=document.getElementById("log");
  const atBottom=logEl.scrollTop+logEl.clientHeight>=logEl.scrollHeight-20;
  logEl.innerHTML=(d.log||[]).map(e=>'<div class="l"><span class="t">'+e.t+'</span>'+
    '<span class="kind k-'+e.kind+'">'+e.kind+'</span><span>'+esc(e.text)+'</span></div>').join("");
  if(atBottom)logEl.scrollTop=logEl.scrollHeight;
  document.getElementById("stime").textContent=d.server_time||"";
}
function esc(s){return String(s).replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));}
tick();setInterval(tick,2000);
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    scope_host = "192.168.1.100"

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="text/html; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except Exception:
            pass

    def do_GET(self):
        if self.path.startswith("/api/state"):
            self._send(200, json.dumps(STATE.snapshot()), "application/json")
        elif self.path.startswith("/api/image"):
            kind = "full" if "kind=full" in self.path else "thumb"
            with STATE.lock:
                path = STATE.img_full_path if kind == "full" else STATE.img_thumb_path
            if not path:
                self._send(204, b"", "text/plain")
                return
            with STATE.lock:
                host = STATE.host or self.scope_host
            body = scope_http_get(host, path)
            if not body:
                self._send(502, b"", "text/plain")
                return
            self._send(200, body, "image/jpeg")
        elif self.path == "/" or self.path.startswith("/index"):
            self._send(200, DASHBOARD_HTML)
        else:
            self._send(404, "not found", "text/plain")


def tailscale_ip():
    """Return this machine's Tailscale IPv4 (100.64.0.0/10), or None."""
    import subprocess
    for exe in ("tailscale", r"C:\Program Files\Tailscale\tailscale.exe",
                r"C:\Program Files (x86)\Tailscale IPN\tailscale.exe"):
        try:
            out = subprocess.run([exe, "ip", "-4"], capture_output=True,
                                 text=True, timeout=5)
            for line in (out.stdout or "").splitlines():
                ip = line.strip()
                if ip.startswith("100."):
                    return ip
        except Exception:
            continue
    # Fallback: scan local interfaces for a CGNAT (Tailscale) address
    for ip in _local_ipv4s():
        try:
            first, second = int(ip.split(".")[0]), int(ip.split(".")[1])
            if first == 100 and 64 <= second <= 127:
                return ip
        except Exception:
            continue
    return None


def resolve_binds(spec):
    """Turn a --bind spec into a list of concrete addresses to listen on.
    Special tokens: 'tailscale' (localhost + this host's tailnet IP),
    'all'/'0.0.0.0' (everything). Otherwise a comma-separated list of IPs."""
    out = []
    for part in spec.split(","):
        part = part.strip().lower()
        if part in ("tailscale", "ts", "tailnet"):
            out.append("127.0.0.1")
            tip = tailscale_ip()
            if tip:
                out.append(tip)
            else:
                STATE.note("net", "Tailscale IP not found; binding localhost only.")
        elif part in ("all", "0.0.0.0", "any"):
            out.append("0.0.0.0")
        elif part:
            out.append(part)
    # de-dup, preserve order
    seen, uniq = set(), []
    for a in out:
        if a not in seen:
            seen.add(a); uniq.append(a)
    return uniq or ["127.0.0.1"]


def main():
    ap = argparse.ArgumentParser(description="Local web monitor for a ZWO Seestar.")
    ap.add_argument("--host", default="192.168.1.100")
    ap.add_argument("--port", type=int, default=4700)
    ap.add_argument("--web", type=int, default=5556)
    ap.add_argument("--key", default=None)
    ap.add_argument("--bind", default="127.0.0.1",
                    help="addresses to serve on: '127.0.0.1' (default, this PC "
                         "only), 'tailscale' (localhost + tailnet), '0.0.0.0' "
                         "(all networks), or a comma-separated list of IPs")
    args = ap.parse_args()

    key_path = args.key
    if not key_path:
        here = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seestar.pem")
        env = os.environ.get("SEESTAR_KEY_PATH")
        if env and os.path.isfile(env):
            key_path = env
        elif os.path.isfile(here):
            key_path = here
    signer = load_signer(key_path) if key_path else None

    STATE.host = args.host
    ScopeClient(args.host, args.port, signer=signer).start()

    Handler.scope_host = args.host
    binds = resolve_binds(args.bind)

    servers = []
    for addr in binds:
        try:
            srv = ThreadingHTTPServer((addr, args.web), Handler)
            servers.append((addr, srv))
        except Exception as e:
            print(f"  ! could not bind {addr}:{args.web} - {e}")
    if not servers:
        print("  No listener could be started. Exiting.")
        return

    print("=" * 60)
    print("  Seestar Monitor")
    print("=" * 60)
    print(f"  Scope : {args.host}:{args.port}")
    print(f"  Mode  : {'FULL (key loaded)' if signer else 'monitor (read-only, no key)'}")
    print("  Open  :")
    for addr, _ in servers:
        shown = "127.0.0.1" if addr in ("0.0.0.0",) else addr
        print(f"            http://{shown}:{args.web}")
    if any(a.startswith("100.") for a, _ in servers):
        print("          (the 100.x address works from any device on your tailnet)")
    print("  Read-only - your observation is never touched. Ctrl+C to stop.")
    print("=" * 60)

    # Serve every bound address; run all but the first in daemon threads.
    for addr, srv in servers[1:]:
        threading.Thread(target=srv.serve_forever, daemon=True,
                         name=f"http-{addr}").start()
    try:
        servers[0][1].serve_forever()
    except KeyboardInterrupt:
        print("\nStopping.")


if __name__ == "__main__":
    main()
