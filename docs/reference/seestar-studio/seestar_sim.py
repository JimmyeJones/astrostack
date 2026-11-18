#!/usr/bin/env python3
"""
Seestar simulator - a fake ZWO Seestar for testing Seestar Studio safely.

Speaks the same newline-delimited JSON-RPC on a TCP control port (incl. the
firmware 7.18+ verify handshake, which it always accepts), broadcasts Stack /
Exposure / PiStatus events, serves synthetic album images over HTTP, a live
"video" feed, and the binary preview-frame protocol - so every Studio feature,
including CONTROL actions, can be exercised without a real telescope.

Command shapes follow the official app's protocol as documented by the
seestarpy / seestar_alp projects.

    python seestar_sim.py                 # control :4700, http :8080
    python seestar_studio.py --demo       # Studio + built-in simulator

Extra test-only method:  sim_set {"battery": 8, "temp": 40, "drain": 1.0}
"""

import argparse
import datetime
import io
import json
import math
import random
import socket
import struct
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def _render(frames, w, h, seed=7):
    """Synthetic 'stacked' deep-sky image: gets cleaner as frames grow."""
    try:
        from PIL import Image, ImageDraw, ImageFilter
    except Exception:
        return None
    rnd = random.Random(seed)
    img = Image.new("RGB", (w, h), (3, 4, 9))
    neb = Image.new("RGB", (w, h), (0, 0, 0))
    d = ImageDraw.Draw(neb)
    depth = min(1.0, 0.25 + frames / 160.0)
    for i in range(46):
        cx = w * (0.5 + 0.26 * math.cos(i * 0.61) * rnd.uniform(0.3, 1))
        cy = h * (0.5 + 0.2 * math.sin(i * 0.47) * rnd.uniform(0.3, 1))
        r = rnd.uniform(0.05, 0.16) * w
        col = (int(rnd.uniform(110, 190) * depth), int(rnd.uniform(25, 60) * depth),
               int(rnd.uniform(50, 120) * depth))
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=col)
    neb = neb.filter(ImageFilter.GaussianBlur(w / 16))
    img = Image.blend(img, neb, 0.85)
    d = ImageDraw.Draw(img)
    for i in range(int(w * h / 900)):
        x, y = rnd.uniform(0, w), rnd.uniform(0, h)
        b = int(rnd.uniform(90, 255))
        r = 0.6 if b < 215 else rnd.uniform(1.0, 2.2) * w / 500
        d.ellipse((x - r, y - r, x + r, y + r), fill=(b, b, min(255, b + 20)))
    noise = max(0, 26 - frames // 4)
    if noise:
        n = Image.effect_noise((w, h), noise).convert("RGB")
        img = Image.blend(img, n, 0.16)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=86)
    return buf.getvalue()


def sim_horizon(az):
    """The fake site's true skyline (altitude in degrees for an azimuth)."""
    az = az % 360.0
    h = 9.0 + 5.0 * math.sin(az * math.pi / 90.0) + 2.5 * math.sin(az * math.pi / 22.0)
    if 195.0 <= az <= 235.0:                         # a tall tree
        h = max(h, 30.0 - abs(az - 215.0) * 0.9)
    if 40.0 <= az <= 75.0:                           # a house
        h = max(h, 17.0)
    return h


SIM_WIDE = {"w": 640, "h": 360, "hfov": 34.0}


def _wide_frame(alt, az, eq, lat):
    """What the simulated wide camera sees at a pointing: sky above the fake
    skyline, textured ground below. Uses the same tube geometry as Studio."""
    import cv2
    import numpy as np
    from seestar_skyline import tube_basis
    w, h = SIM_WIDE["w"], SIM_WIDE["h"]
    f = (w / 2.0) / math.tan(math.radians(SIM_WIDE["hfov"]) / 2.0)
    p, d, t = tube_basis(alt, az, eq, lat)
    xs, ys = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    a, b = -(xs - w / 2.0) / f, -(ys - h / 2.0) / f
    vx, vy, vz = p[0] + a * d[0] + b * t[0], p[1] + a * d[1] + b * t[1], p[2] + a * d[2] + b * t[2]
    n = np.sqrt(vx * vx + vy * vy + vz * vz)
    al = np.degrees(np.arcsin(vz / n))
    zz = np.degrees(np.arctan2(vx, vy)) % 360.0
    hz = 9.0 + 5.0 * np.sin(zz * np.pi / 90.0) + 2.5 * np.sin(zz * np.pi / 22.0)
    hz = np.where((zz >= 195) & (zz <= 235), np.maximum(hz, 30.0 - np.abs(zz - 215.0) * 0.9), hz)
    hz = np.where((zz >= 40) & (zz <= 75), np.maximum(hz, 17.0), hz)
    sky = al > hz
    img = np.zeros((h, w, 3), np.float32)
    cloud = 18.0 * np.sin(zz * 0.9) * np.sin(al * 1.3) + 10.0 * np.sin(zz * 0.23 + al * 0.5)
    img[..., 0] = np.where(sky, 200 - al * 0.8 + cloud, 38 + 14 * np.sin(zz * 2.1) + 8 * np.sin(al * 3.0))
    img[..., 1] = np.where(sky, 165 - al * 0.6 + cloud, 58 + 18 * np.sin(zz * 2.1) + 8 * np.sin(al * 3.0))
    img[..., 2] = np.where(sky, 130 - al * 0.5 + cloud, 44 + 14 * np.sin(zz * 2.1))
    ok, buf = cv2.imencode(".jpg", np.clip(img, 0, 255).astype(np.uint8), [cv2.IMWRITE_JPEG_QUALITY, 85])
    return buf.tobytes()


def _video_frame(mode, t, w=360, h=640):
    """One frame of the fake live-video feed (a drifting disc)."""
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (w, h), (2, 3, 8) if mode != "scenery" else (60, 90, 140))
    d = ImageDraw.Draw(img)
    cx = w / 2 + 40 * math.sin(t / 3.0)
    cy = h / 2 + 30 * math.cos(t / 4.0)
    r, col = {"sun": (110, (255, 190, 60)), "moon": (120, (215, 215, 205)),
              "planet": (26, (230, 200, 160))}.get(mode, (70, (90, 140, 70)))
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=col)
    if mode == "moon":
        for i in range(9):
            a = i * 0.7
            x, y, cr = cx + 70 * math.cos(a) * (i % 3) / 2, cy + 70 * math.sin(a) * (i % 4) / 3, 8 + i % 4 * 4
            d.ellipse((x - cr, y - cr, x + cr, y + cr), fill=(180, 180, 172))
    d.text((10, h - 22), f"SIM {mode} {datetime.datetime.now():%H:%M:%S}", fill=(200, 200, 200))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=80)
    return buf.getvalue()


class SimScope:
    def __init__(self, port=4700, http_port=8080, bind="127.0.0.1", drain=0.25, img_port=0):
        self.bind = bind
        self.lock = threading.RLock()
        self.clients = []           # (sock, state-dict)
        self.offline_until = 0
        self.drain = drain          # battery % per minute
        self.battery = 64.0
        self.charging = False
        self.temp = 31.5
        self.focus = 1560
        self.heater = False
        self.gain = 80
        self.mode = None            # None = idle
        self.stage = None
        self.target = "IC 443"
        self.ra, self.dec = 6.3037, 22.505
        self.stacked = 0
        self.dropped = 0
        self.slewing_until = 0
        self.af_until = 0
        self.solve_until = 0
        self.dark_until = 0
        self.pa_until = 0
        self.tracking = True
        self.equ_mode = False
        self.alt, self.az = 52.3, 141.8
        self.closed = False
        self.wheel = 2
        self.plan = None
        self.plan_state = None
        self.recording = False
        self.deleted = []
        self.location = [-104.99, 39.74]
        self.settings = {
            "temp_unit": "C", "beep_volume": "backyard", "lang": "en", "stack_lenhance": True,
            "heater_enable": False, "expert_mode": False, "focal_pos": 1560,
            "exp_ms": {"stack_l": 10000, "continuous": 500}, "auto_power_off": True,
            "stack_dither": {"pix": 50, "interval": 5, "enable": True}, "auto_3ppa_calib": True,
            "auto_af": False, "frame_calib": True, "stack_after_goto": True, "wide_cam": False,
            "stack": {"dbe": False, "star_correction": True, "cont_capt": False, "drizzle2x": False,
                      "airplane_line_removal": True, "save_discrete_frame": False,
                      "save_discrete_ok_frame": True, "light_duration_min": -1},
            "mosaic": {"scale": 1.0, "angle": 0.0, "estimated_hours": 0.26},
            "manual_exp": False, "isp_exp_ms": 30.0, "isp_gain": 0.0, "ae_bri_percent": 50.0,
            "plan_target_af": False, "viewplan_gohome": True, "enable_dark_library": True,
            "light_brightness": 50, "dark_mode": False, "usb_en_eth": False, "typec_mode": "file",
        }
        self.session = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        self.saved = [("M 42", 144, "20261115-221004"), ("M 31", 96, "20261114-203310")]
        self.rpc_log = []
        self._img_cache = {}
        self._start_view("star", stack=True)

        self.srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.srv.bind((bind, port))
        self.srv.listen(8)
        self.port = self.srv.getsockname()[1]

        self.imgsrv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.imgsrv.bind((bind, img_port))
        self.imgsrv.listen(4)
        self.img_port = self.imgsrv.getsockname()[1]

        sim = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                if time.time() < sim.offline_until:
                    self.send_error(503); return
                path = urllib.parse.unquote(urllib.parse.urlparse(self.path).path)
                if path.endswith("wide.mjpg"):
                    return sim.serve_wide(self)
                if path.endswith("stream.mjpg"):
                    return sim.serve_mjpeg(self)
                body = sim.image_for(path)
                if not body:
                    self.send_error(404); return
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.http = ThreadingHTTPServer((bind, http_port), H)
        self.http.daemon_threads = True
        self.http_port = self.http.server_address[1]

    @property
    def exp_ms(self):
        return self.settings["exp_ms"]["stack_l"]

    @property
    def lp(self):
        return self.settings["stack_lenhance"]

    # ---- lifecycle ----
    def start(self):
        threading.Thread(target=self.http.serve_forever, daemon=True).start()
        threading.Thread(target=self._accept, daemon=True).start()
        threading.Thread(target=self._accept_img, daemon=True).start()
        threading.Thread(target=self._tick, daemon=True).start()
        return self

    def _accept(self):
        while True:
            try:
                s, _ = self.srv.accept()
            except Exception:
                return
            if time.time() < self.offline_until:
                s.close(); continue
            st = {"verified": False}
            with self.lock:
                self.clients.append((s, st))
            threading.Thread(target=self._serve, args=(s, st), daemon=True).start()

    def _drop_all(self):
        with self.lock:
            for s, _ in self.clients:
                try:
                    s.close()
                except Exception:
                    pass
            self.clients = []

    def _serve(self, s, st):
        buf = b""
        try:
            while True:
                d = s.recv(65536)
                if not d:
                    break
                buf += d
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        req = json.loads(line)
                    except Exception:
                        continue
                    rep = self._rpc(req, st)
                    s.sendall((json.dumps(rep) + "\r\n").encode())
        except Exception:
            pass
        finally:
            with self.lock:
                self.clients = [(c, x) for c, x in self.clients if c is not s]
            try:
                s.close()
            except Exception:
                pass

    def _broadcast(self, ev):
        ev["Timestamp"] = f"{time.monotonic():.6f}"
        data = (json.dumps(ev) + "\r\n").encode()
        with self.lock:
            for s, _ in list(self.clients):
                try:
                    s.sendall(data)
                except Exception:
                    pass

    # ---- binary preview-frame port (like 4800) ----
    def _accept_img(self):
        while True:
            try:
                s, _ = self.imgsrv.accept()
            except Exception:
                return
            threading.Thread(target=self._serve_img, args=(s,), daemon=True).start()

    def _serve_img(self, s):
        """After begin_streaming: 80-byte header + raw 16-bit Bayer frames."""
        import numpy as np
        s.settimeout(0.5)
        streaming, n = False, 0
        w, h = 270, 480
        try:
            while True:
                try:
                    d = s.recv(4096)
                    if not d:
                        break
                    if b"begin_streaming" in d:
                        streaming = True
                    if b"stop_streaming" in d:
                        streaming = False
                except socket.timeout:
                    pass
                if streaming and self.stage == "ContinuousExposure":
                    n += 1
                    rng = np.random.default_rng(5)
                    img = rng.integers(180, 420, (h, w)).astype(np.uint16)
                    for _ in range(60):
                        x, y = int(rng.integers(2, w - 2)), int(rng.integers(2, h - 2))
                        img[y - 1:y + 2, x - 1:x + 2] = int(rng.integers(3000, 40000))
                    img = np.roll(img, n % w, axis=1)
                    payload = img.tobytes()
                    hdr = struct.pack(">HHHIHHBBHH", 0x03C3, 1, 80, len(payload), 0, 0, 1, 21, w, h)
                    s.sendall(hdr + b"\x00" * (80 - len(hdr)) + payload)
        except Exception:
            pass
        finally:
            s.close()

    def serve_mjpeg(self, handler):
        handler.send_response(200)
        handler.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        handler.end_headers()
        try:
            while self.stage == "RTSP" and time.time() > self.offline_until:
                f = _video_frame(self.mode or "moon", time.time())
                handler.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                                    + str(len(f)).encode() + b"\r\n\r\n" + f + b"\r\n")
                time.sleep(0.15)
        except Exception:
            pass

    def serve_wide(self, handler):
        """MJPEG of the simulated wide camera (follows the mount)."""
        handler.send_response(200)
        handler.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        handler.end_headers()
        try:
            while self.stage == "RTSP" and time.time() > self.offline_until:
                f = _wide_frame(self.alt, self.az, self.equ_mode, self.location[1])
                handler.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                                    + str(len(f)).encode() + b"\r\n\r\n" + f + b"\r\n")
                time.sleep(0.2)
        except Exception:
            pass

    def _set_altaz_from_radec(self):
        from seestar_skyline import radec_to_altaz
        self.alt, self.az = radec_to_altaz(self.ra, self.dec, self.location[1], self.location[0], time.time())

    # ---- simulation clock ----
    def _tick(self):
        last_exp = time.time()
        n = 0
        while True:
            time.sleep(1)
            n += 1
            now = time.time()
            if now < self.offline_until:
                continue
            with self.lock:
                if not self.charging:
                    self.battery = max(0.0, self.battery - self.drain / 60.0)
                self.temp += random.uniform(-0.05, 0.05)
                if self.mode == "star" and self.stage == "AutoGoto" and now > self.slewing_until:
                    self.stage = "Stack" if self.settings["stack_after_goto"] else "ContinuousExposure"
                    self._broadcast({"Event": "AutoGoto", "state": "complete"})
                self._plan_tick(now)
                stacking = self.mode == "star" and self.stage == "Stack"
                exp_s = max(2.0, self.exp_ms / 1000.0 / 5.0)   # 5x faster than real
                if self.battery <= 0:
                    self.offline_until = now + 3600 * 24
                    self._drop_all()
                    continue
            if stacking and now - last_exp >= exp_s:
                last_exp = now
                with self.lock:
                    if random.random() < 0.07:
                        self.dropped += 1
                    else:
                        self.stacked += 1
                    ev = {"Event": "Stack", "state": "working", "stacked_frame": self.stacked,
                          "dropped_frame": self.dropped, "lapse_ms": int(exp_s * 1000)}
                self._broadcast({"Event": "Exposure", "state": "complete", "page": "stack",
                                 "exp_ms": float(self.exp_ms), "gain": self.gain})
                self._broadcast(ev)
                self._broadcast({"Event": "Exposure", "state": "start", "page": "stack",
                                 "exp_ms": float(self.exp_ms), "gain": self.gain})
            if n % 5 == 0:
                self._broadcast({"Event": "PiStatus", "temp": round(self.temp, 1),
                                 "battery_capacity": int(self.battery),
                                 "charge_online": self.charging})

    def _plan_tick(self, now):
        """Run a stored view plan: each target for (duration_min) seconds here (60x fast)."""
        if self.plan_state != "working" or not self.plan:
            return
        items = self.plan["list"]
        cur = next((it for it in items if it.get("state") == "working"), None)
        if cur and now >= cur["_end"]:
            cur["state"] = "complete"
            cur = None
        if cur is None:
            nxt = next((it for it in items if it.get("state") == "idle"), None)
            if nxt is None:
                self.plan_state = "complete"
                if self.settings.get("viewplan_gohome"):
                    self._park()
                self._broadcast({"Event": "ViewPlan", "state": "complete"})
                return
            nxt["state"] = "working"
            nxt["_end"] = now + max(8, nxt["duration_min"])
            self._goto(nxt["target_name"], nxt["target_ra_dec"], nxt.get("lp_filter"), now)
        for it in items:
            if it.get("state") == "working":
                it["lapse_ms"] = int((now - (it["_end"] - max(8, it["duration_min"]))) * 1000)

    def _start_view(self, mode, stack=False):
        self.mode = mode
        self.closed = False
        self.stage = ("Stack" if stack else "ContinuousExposure") if mode == "star" else "RTSP"
        self.stacked = 0
        self.dropped = 0
        self.session = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")

    def _goto(self, name, radec, lp, now):
        self.target = name or "Target"
        self.ra, self.dec = float(radec[0]), float(radec[1])
        if lp is not None:
            self.settings["stack_lenhance"] = bool(lp)
        self._start_view("star")
        self.stage = "AutoGoto"
        self.slewing_until = now + 5

    def _park(self):
        if self.stacked:
            self.saved.insert(0, (self.target, self.stacked, self.session))
        self.mode = None
        self.stage = None
        self.closed = True
        self.ra, self.dec = 0.0, 90.0

    # ---- images / albums ----
    def _thn(self):
        return (f"{self.target}_sub/Stacked_{self.stacked}_{self.target}_"
                f"{self.exp_ms / 1000:.1f}s_LP_{self.session}_thn.jpg")

    def image_for(self, path):
        thumb = "_thn" in path
        with self.lock:
            live = self.session in path
            frames = self.stacked if live else 150
            seed = sum(map(ord, path.split("/")[-2] if "/" in path else path)) % 97
        key = (seed, frames // 3, thumb)
        if key not in self._img_cache:
            if len(self._img_cache) > 40:
                self._img_cache.clear()
            w, h = (270, 480) if thumb else (1080, 1920)
            self._img_cache[key] = _render(frames, w, h, seed)
        return self._img_cache[key]

    def _albums(self):
        files = []
        if self.stacked and self.mode == "star":
            files.append({"name": f"{self.target}_sub", "thn": self._thn(), "count": self.stacked})
        for name, cnt, ts in self.saved:
            thn = f"{name}/Stacked_{cnt}_{name}_10.0s_LP_{ts}_thn.jpg"
            if not any(name in d for d in self.deleted):
                files.append({"name": name, "count": cnt, "thn": thn})
        return {"path": "MyWorks", "list": [{"group_name": "DSO", "files": files}]}

    def _view(self, now):
        view = {"state": "working" if self.mode else "idle", "mode": self.mode,
                "target_name": self.target, "target_ra_dec": [self.ra, self.dec],
                "gain": self.gain, "lp_filter": self.lp}
        if self.mode:
            view["stage"] = self.stage
            if self.mode == "star":
                view["Stack"] = {"state": "working" if self.stage == "Stack" else "idle",
                                 "stacked_frame": self.stacked, "dropped_frame": self.dropped,
                                 "Exposure": {"exp_ms": float(self.exp_ms), "state": "working"},
                                 "Annotate": {"result": {"annotations": [{}, {}, {}]}}}
        if now < self.af_until:
            view["AutoFocus"] = {"state": "working"}
        return view

    def _plan_public(self):
        if not self.plan:
            return None
        p = dict(self.plan)
        p["list"] = [{k: v for k, v in it.items() if not k.startswith("_")} for it in self.plan["list"]]
        return {"state": self.plan_state, "plan": p}

    # ---- RPC ----
    def _rpc(self, req, st):
        m = req.get("method")
        p = req.get("params")
        rid = req.get("id")
        code, result = 0, 0
        with self.lock:
            self.rpc_log.append((m, p))
            self.rpc_log = self.rpc_log[-300:]
            now = time.time()
            try:
                code, result = self._do(m, p, st, now)
            except Exception as e:                      # wrong param shape -> like firmware
                code, result = 109, f"invalid parameter: {e}"
        rep = {"jsonrpc": "2.0", "Timestamp": f"{time.monotonic():.6f}", "method": m,
               "code": code, "id": rid}
        if code:
            rep["error"] = result
        else:
            rep["result"] = result
        return rep

    def _do(self, m, p, st, now):
        if m == "get_verify_str":
            return 0, {"str": "sim-%08x" % random.getrandbits(32)}
        if m == "verify_client":
            st["verified"] = True
            return 0, {"key_envelope": "simulated"}
        if m == "pi_is_verified":
            return 0, st["verified"]
        if m == "test_connection":
            return 0, "server connected!"
        if not st["verified"]:
            return 207, "fail to operate"
        S = self.settings
        if m == "get_device_state":
            full = {"device": {"product_model": "Seestar S30", "user_product_model": "Seestar S30 (simulated)",
                               "firmware_ver_string": "9.75", "firmware_ver_int": 2775, "sn": "SIM00001",
                               "name": "Seestar-sim"},
                    "pi_status": {"battery_capacity": int(self.battery), "charge_online": self.charging,
                                  "charger_status": "Charging" if self.charging else "Discharging",
                                  "temp": round(self.temp, 1), "battery_temp": 24},
                    "setting": S,
                    "mount": {"equ_mode": self.equ_mode, "close": self.closed, "tracking": self.tracking,
                              "move_type": "none"},
                    "focuser": {"state": "idle", "step": self.focus, "max_step": 2600},
                    "balance_sensor": {"code": 0, "data": {"x": 0.012, "y": -0.004, "z": 0.99, "angle": 0.74}},
                    "compass_sensor": {"code": 0, "data": {"direction": 187.5, "cali": 1}},
                    "station": {"ssid": "HomeWiFi", "sig_lev": -52, "ip": "192.168.1.100", "freq": 5180},
                    "storage": {"is_typec_connected": False},
                    "location_lon_lat": self.location}
            keys = (p or {}).get("keys") if isinstance(p, dict) else None
            return 0, ({k: full[k] for k in keys if k in full} if keys else full)
        if m == "get_view_state":
            return 0, {"View": self._view(now)}
        if m == "iscope_get_app_state":
            r = {"View": self._view(now)}
            if self.plan:
                r["ViewPlan"] = self._plan_public()
            return 0, r
        if m == "get_setting":
            return 0, S
        if m == "get_disk_volume":
            return 0, {"totalMB": 51854, "freeMB": 35690 - self.stacked * 4}
        if m == "get_focuser_position":
            return 0, self.focus
        if m == "scope_get_equ_coord":
            return 0, {"ra": self.ra, "dec": self.dec}
        if m == "scope_get_horiz_coord":
            return 0, [round(self.alt, 4), round(self.az, 4)]
        if m == "scope_get_track_state":
            return 0, self.tracking
        if m == "get_wheel_position":
            return 0, self.wheel
        if m == "get_user_location":
            return 0, self.location
        if m == "get_albums":
            return 0, self._albums()
        if m in ("get_solve_result", "get_last_solve_result"):
            if now < self.solve_until:
                return 0, {"state": "working"}
            return 0, {"ra_dec": [self.ra, self.dec], "fov": [0.73, 1.29], "focal_len": 160.2,
                       "angle": 178.3, "star_number": 412, "state": "complete"}
        if m == "iscope_start_view":
            mode = p.get("mode", "star")
            trd = p.get("target_ra_dec")
            if isinstance(trd, list) and len(trd) == 2 and trd[0] is not None:
                self._goto(p.get("target_name"), trd, p.get("lp_filter"), now)
                self.mode = mode
                if "mosaic" in p:
                    S["mosaic"].update(p["mosaic"])
            else:
                self._start_view(mode)
                if p.get("target_name"):
                    self.target = p["target_name"]
            return 0, 0
        if m == "iscope_start_stack":
            if self.mode != "star":
                return 207, "fail to operate"
            if (p or {}).get("restart"):
                self.stacked = self.dropped = 0
                self.session = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
            self.stage = "Stack"
            return 0, 0
        if m == "iscope_stop_view":
            stage = (p or {}).get("stage") if isinstance(p, dict) else None
            if stage == "Stack":
                if self.stacked:
                    self.saved.insert(0, (self.target, self.stacked, self.session))
                if self.mode == "star":
                    self.stage = "ContinuousExposure"
            elif stage == "AutoGoto":
                self.slewing_until = 0
                if self.stage == "AutoGoto":
                    self.stage = "ContinuousExposure"
            else:
                if self.stacked and self.stage == "Stack":
                    self.saved.insert(0, (self.target, self.stacked, self.session))
                self.mode = None
                self.stage = None
            return 0, 0
        if m == "scope_goto":
            self.ra, self.dec = float(p[0]), float(p[1])
            self._set_altaz_from_radec()
            if self.alt < -2.0 and getattr(self, "limit_horizon", False):
                return 207, None
            return 0, 0
        if m == "scope_sync":
            self.ra, self.dec = float(p[0]), float(p[1])
            return 0, 0
        if m == "scope_park":
            self._park()
            self.equ_mode = bool((p or {}).get("equ_mode", False))
            return 0, 0
        if m == "scope_move_to_horizon":
            self.closed = False
            self.alt, self.az = (0.0, 110.0) if self.equ_mode else (0.0, 0.0)
            self.ra, self.dec = 6.0, 0.0
            return 0, 0
        if m == "scope_set_track_state":
            if not isinstance(p, bool):
                raise ValueError("expected bool")
            self.tracking = p
            return 0, 0
        if m == "scope_speed_move":
            sp, ang = p["speed"], math.radians(p["angle"])
            k = sp / 1000.0 * 0.05
            self.ra = (self.ra + k * math.cos(ang) / 15.0) % 24
            self.dec = max(-90, min(90, self.dec + k * math.sin(ang)))
            return 0, 0
        if m == "start_auto_focuse":
            self.af_until = now + 8
            self.focus = 1560 + random.randint(-15, 15)
            return 0, 0
        if m == "stop_auto_focuse":
            self.af_until = 0
            return 0, 0
        if m == "move_focuser":
            pos = int(p["step"])
            if not 1200 <= pos <= 2600:
                return 109, "step out of range"
            self.focus = pos
            return 0, {"step": pos}
        if m == "set_control_value":
            if p[0] != "gain":
                return 104, "unknown control"
            self.gain = int(p[1])
            return 0, 0
        if m == "set_setting":
            for k, v in p.items():
                if k not in S and k not in ("master_cli", "preview", "annotation", "motion_monitor"):
                    return 109, f"unknown setting {k}"
                if isinstance(v, dict) and isinstance(S.get(k), dict):
                    S[k].update(v)
                else:
                    S[k] = v
            if "stack_lenhance" in p:
                self.wheel = 2 if p["stack_lenhance"] else 1
            return 0, 0
        if m == "set_wheel_position":
            self.wheel = int(p[0])
            S["stack_lenhance"] = self.wheel == 2
            return 0, 0
        if m == "pi_output_set2":
            self.heater = bool(p["heater"]["state"])
            S["heater_enable"] = self.heater
            return 0, 0
        if m == "set_user_location":
            self.location = [float(p["lon"]), float(p["lat"])]
            return 0, 0
        if m == "pi_set_time":
            _ = p[0]["year"], p[0]["time_zone"]
            return 0, 0
        if m == "start_solve":
            self.solve_until = now + 4
            return 0, 0
        if m == "start_create_dark":
            self.dark_until = now + 10
            return 0, 0
        if m == "start_polar_align":
            if not self.equ_mode:
                return 207, "fail to operate"
            self.pa_until = now + 10
            threading.Timer(3, lambda: self._broadcast(
                {"Event": "EqModePA", "state": "complete", "total": 0.42, "x": 0.31, "y": -0.28})).start()
            return 0, 0
        if m == "start_record_avi":
            self.recording = True
            return 0, 0
        if m == "stop_record_avi":
            self.recording = False
            return 0, 0
        if m == "set_view_plan":
            if not isinstance(p.get("list"), list) or not p["list"]:
                return 109, "empty plan"
            for it in p["list"]:
                _ = it["target_name"], it["target_ra_dec"][1], it["start_min"], it["duration_min"]
            self.plan = json.loads(json.dumps(p))
            for it in self.plan["list"]:
                it.update({"state": "idle", "lapse_ms": 0, "skip": False})
            self.plan_state = "working"
            return 0, 0
        if m == "stop_func":
            if (p or {}).get("name") == "ViewPlan" and self.plan:
                self.plan_state = "cancel"
                for it in self.plan["list"]:
                    if it.get("state") == "working":
                        it["state"] = "cancel"
            return 0, 0
        if m == "clear_view_plan":
            self.plan = None
            self.plan_state = None
            return 0, 0
        if m == "delete_image":
            self.deleted += list(p["name"])
            return 0, 0
        if m in ("stop_solve", "stop_create_dark", "stop_polar_align", "start_scan_planet",
                 "play_sound", "set_sequence_setting"):
            return 0, 0
        if m == "pi_reboot":
            self.offline_until = now + 12
            threading.Timer(0.3, self._drop_all).start()
            return 0, 0
        if m == "pi_shutdown":
            self.offline_until = now + 30
            threading.Timer(0.3, self._drop_all).start()
            return 0, 0
        if m == "sim_set":
            for k in ("battery", "temp", "drain", "charging"):
                if k in (p or {}):
                    setattr(self, k, p[k])
            return 0, 0
        return 103, "method not found"


def main():
    ap = argparse.ArgumentParser(description="Fake Seestar for testing Seestar Studio.")
    ap.add_argument("--port", type=int, default=4700)
    ap.add_argument("--http", type=int, default=8080)
    ap.add_argument("--bind", default="127.0.0.1")
    ap.add_argument("--drain", type=float, default=0.25, help="battery %% per minute")
    a = ap.parse_args()
    sim = SimScope(a.port, a.http, a.bind, a.drain).start()
    print(f"Simulated Seestar: control {a.bind}:{sim.port}, images http://{a.bind}:{sim.http_port}/")
    print("Easiest way to use it:  python seestar_studio.py --demo")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
