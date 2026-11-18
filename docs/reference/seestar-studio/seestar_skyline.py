"""Skyline (local horizon) scan for Seestar Studio.

The scope turns once around the horizon while the wide-angle camera looks at
the skyline. The frames are re-projected into one azimuth/altitude panorama,
the sky/obstruction boundary is found in every azimuth column, and the result
is saved as a horizon profile (altitude of the skyline for each degree of
azimuth) plus the panorama picture itself.

Nothing here talks to the scope directly: the scan gets a small "rig" object
from Studio (send a command, read the pointing, grab a wide-camera frame), so
the same code runs against the real scope and the simulator.
"""
import json
import math
import os
import threading
import time

try:
    import cv2
    import numpy as np
except Exception:                                    # optional, like live video
    cv2 = None
    np = None

D2R = math.pi / 180.0
PANO_STEP = 0.25                 # degrees per panorama pixel
PANO_ALT = (-12.0, 66.0)         # altitude range of the panorama


# ------------------------------------------------------------------ astronomy
def lst_hours(ts, lon):
    jd = ts / 86400.0 + 2440587.5
    t = (jd - 2451545.0) / 36525.0
    g = 280.46061837 + 360.98564736629 * (jd - 2451545.0) + 0.000387933 * t * t
    return ((g + lon) % 360.0) / 15.0


def altaz_to_radec(alt, az, lat, lon, ts):
    a, z, p = alt * D2R, az * D2R, lat * D2R
    sd = math.sin(a) * math.sin(p) + math.cos(a) * math.cos(p) * math.cos(z)
    dec = math.asin(max(-1.0, min(1.0, sd)))
    ha = math.atan2(-math.sin(z) * math.cos(a),
                    math.sin(a) * math.cos(p) - math.cos(a) * math.sin(p) * math.cos(z))
    return (lst_hours(ts, lon) - ha / D2R / 15.0) % 24.0, dec / D2R


def radec_to_altaz(ra, dec, lat, lon, ts):
    ha = (lst_hours(ts, lon) - ra) * 15.0 * D2R
    d, p = dec * D2R, lat * D2R
    alt = math.asin(max(-1.0, min(1.0, math.sin(d) * math.sin(p) + math.cos(d) * math.cos(p) * math.cos(ha))))
    az = math.atan2(-math.cos(d) * math.sin(ha),
                    math.sin(d) * math.cos(p) - math.cos(d) * math.sin(p) * math.cos(ha))
    return alt / D2R, (az / D2R) % 360.0


def sun_altaz(ts, lat, lon):
    """Altitude / azimuth of the Sun in degrees (good to a few tenths of a degree)."""
    n = ts / 86400.0 + 2440587.5 - 2451545.0
    L = (280.460 + 0.9856474 * n) % 360.0
    g = ((357.528 + 0.9856003 * n) % 360.0) * D2R
    lam = (L + 1.915 * math.sin(g) + 0.020 * math.sin(2 * g)) * D2R
    eps = (23.439 - 0.0000004 * n) * D2R
    ra = math.atan2(math.cos(eps) * math.sin(lam), math.cos(lam)) / D2R / 15.0
    dec = math.asin(math.sin(eps) * math.sin(lam)) / D2R
    return radec_to_altaz(ra % 24.0, dec, lat, lon, ts)


# The telescope must never be swept around the sky with the Sun up: the scan
# only starts when the Sun is at least SUN_START degrees below the horizon and
# stops itself (unwinds, parks) if it climbs above SUN_STOP.
SUN_START = -3.0
SUN_STOP = -1.5


def sun_ok_to_start(ts, lat, lon):
    return sun_altaz(ts, lat, lon)[0] < SUN_START


# -------------------------------------------------------------------- geometry
def dirv(alt, az):
    """Unit vector (east, north, up) for an altitude / azimuth in degrees."""
    a, z = alt * D2R, az * D2R
    return (math.cos(a) * math.sin(z), math.cos(a) * math.cos(z), math.sin(a))


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _norm(a):
    n = math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2]) or 1.0
    return (a[0] / n, a[1] / n, a[2] / n)


def tube_basis(alt, az, eq, lat):
    """Where the tube points (p) and the two axes fixed to it: D (the tilt
    axis) and T (perpendicular to both). The camera rides on the tube, so its
    picture is fixed in the (D, T) frame - this is what handles EQ mode, where
    the picture is rolled relative to the horizon."""
    p = dirv(alt, az)
    axis = dirv(abs(lat), 0.0 if lat >= 0 else 180.0) if eq else (0.0, 0.0, 1.0)
    d = _cross(axis, p)
    if math.sqrt(d[0] ** 2 + d[1] ** 2 + d[2] ** 2) < 1e-3:
        d = (1.0, 0.0, 0.0)
    d = _norm(d)
    return p, d, _cross(p, d)


def default_camera(w, h, hfov_deg):
    """Pixel = centre + M . (a, b), where (a, b) are the tangent offsets of a
    direction from the optical axis along D and T. Default: x runs along -D,
    y (down) along -T, i.e. an upright picture in alt-az mode."""
    f = (w / 2.0) / math.tan(hfov_deg * D2R / 2.0)
    return [[-f, 0.0], [0.0, -f]]


# -------------------------------------------------------------------- panorama
class Panorama:
    def __init__(self):
        self.w = int(round(360.0 / PANO_STEP))
        self.h = int(round((PANO_ALT[1] - PANO_ALT[0]) / PANO_STEP))
        self.img = np.zeros((self.h, self.w, 3), np.float32)
        self.wt = np.zeros((self.h, self.w), np.float32)
        az = (np.arange(self.w, dtype=np.float32) + 0.5) * PANO_STEP * D2R
        alt = (PANO_ALT[1] - (np.arange(self.h, dtype=np.float32) + 0.5) * PANO_STEP) * D2R
        ca = np.cos(alt)[:, None]
        self.vx = ca * np.sin(az)[None, :]
        self.vy = ca * np.cos(az)[None, :]
        self.vz = np.repeat(np.sin(alt)[:, None], self.w, axis=1)

    def add(self, frame, basis, cam):
        """Re-project one camera frame onto the azimuth/altitude grid."""
        p, d, t = basis
        fh, fw = frame.shape[:2]
        wp = self.vx * p[0] + self.vy * p[1] + self.vz * p[2]
        ok = wp > 0.2
        wp = np.where(ok, wp, 1.0)
        a = (self.vx * d[0] + self.vy * d[1] + self.vz * d[2]) / wp
        b = (self.vx * t[0] + self.vy * t[1] + self.vz * t[2]) / wp
        mx = (fw / 2.0 + cam[0][0] * a + cam[0][1] * b).astype(np.float32)
        my = (fh / 2.0 + cam[1][0] * a + cam[1][1] * b).astype(np.float32)
        ok &= (mx >= 2) & (mx <= fw - 3) & (my >= 2) & (my <= fh - 3)
        if not ok.any():
            return 0
        warped = cv2.remap(frame, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
        # feather: pixels near the middle of a frame count more than its edges
        ex = 1.0 - np.abs(mx / fw * 2.0 - 1.0)
        ey = 1.0 - np.abs(my / fh * 2.0 - 1.0)
        wgt = np.where(ok, np.clip(np.minimum(ex, ey), 0.02, 1.0), 0.0).astype(np.float32)
        self.img += warped.astype(np.float32) * wgt[:, :, None]
        self.wt += wgt
        return int(ok.sum())

    def result(self):
        w = np.maximum(self.wt, 1e-6)[:, :, None]
        return np.clip(self.img / w, 0, 255).astype(np.uint8), self.wt > 0


def find_skyline(pano, valid):
    """Altitude of the sky/obstruction boundary for each whole degree of
    azimuth (None where it could not be told). Works on brightness contrast
    between the top of each column (sky) and the bottom (ground), whichever is
    the brighter - so it copes with daylight, twilight and a lit-up night."""
    gray = cv2.GaussianBlur(cv2.cvtColor(pano, cv2.COLOR_BGR2GRAY), (0, 0), 2.0).astype(np.float32)
    h, w = gray.shape
    col_alt = [None] * w
    for x in range(w):
        rows = np.flatnonzero(valid[:, x])
        if len(rows) < 40:
            continue
        col = gray[rows, x]
        n = max(6, len(col) // 8)
        sky, gnd = float(np.median(col[:n])), float(np.median(col[-n:]))
        if abs(sky - gnd) < max(7.0, 0.12 * max(sky, gnd)):
            continue                                     # no usable contrast
        thr = (sky + gnd) / 2.0
        is_gnd = (col < thr) if sky > gnd else (col > thr)
        run = np.convolve(is_gnd.astype(np.float32), np.ones(8, np.float32), "valid")
        hit = np.flatnonzero(run >= 7.5)
        if len(hit) == 0:
            continue
        col_alt[x] = PANO_ALT[1] - (rows[hit[0]] + 0.5) * PANO_STEP
    per = int(round(1.0 / PANO_STEP))
    prof = []
    for dg in range(360):
        vals = [v for v in col_alt[dg * per:(dg + 1) * per] if v is not None]
        prof.append(float(np.median(vals)) if vals else None)
    # knock out single-degree spikes, then bridge short gaps
    sm = list(prof)
    for i in range(360):
        win = [prof[(i + k) % 360] for k in (-2, -1, 0, 1, 2) if prof[(i + k) % 360] is not None]
        if prof[i] is not None and len(win) >= 3:
            sm[i] = float(np.median(win))
    known = [i for i in range(360) if sm[i] is not None]
    if known and len(known) < 360:
        for i in range(360):
            if sm[i] is None:
                lo = max((k for k in known if k < i), default=known[-1] - 360)
                hi = min((k for k in known if k > i), default=known[0] + 360)
                if hi - lo <= 12:
                    t = (i - lo) / float(hi - lo)
                    sm[i] = sm[lo % 360] * (1 - t) + sm[hi % 360] * t
    return [None if v is None else round(v, 2) for v in sm]


# ---------------------------------------------------------------- persistence
def load_horizon(data_dir):
    try:
        with open(os.path.join(data_dir, "horizon.json"), encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def save_horizon(data_dir, doc):
    tmp = os.path.join(data_dir, "horizon.json.tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(doc, fh)
    os.replace(tmp, os.path.join(data_dir, "horizon.json"))


# ------------------------------------------------------------------- the scan
class ScanAborted(Exception):
    pass


class CableGuard(Exception):
    """The mount turned further, or another way, than the scan allows."""


class SunGuard(Exception):
    """The Sun is getting close to the horizon: stop sweeping the telescope."""


def _wrap(d):
    return (d + 180.0) % 360.0 - 180.0


class AxisFrame:
    """Rotation of the scope's base about its own axis (azimuth in alt-az
    mode, the polar axis in EQ mode). That is the rotation that winds a power
    cable, so the scan plans and tracks its moves in this angle."""

    def __init__(self, eq, lat):
        self.axis = dirv(abs(lat), 0.0 if lat >= 0 else 180.0) if eq else (0.0, 0.0, 1.0)
        self.e2 = (1.0, 0.0, 0.0)                    # east: always square to the axis
        self.e1 = _cross(self.axis, self.e2)

    def angle(self, alt, az):
        """Base rotation (deg) for a pointing, or None too close to the axis."""
        p = dirv(alt, az)
        k = p[0] * self.axis[0] + p[1] * self.axis[1] + p[2] * self.axis[2]
        f = (p[0] - k * self.axis[0], p[1] - k * self.axis[1], p[2] - k * self.axis[2])
        if math.sqrt(f[0] ** 2 + f[1] ** 2 + f[2] ** 2) < 0.08:
            return None
        return math.atan2(f[0] * self.e2[0] + f[1] * self.e2[1] + f[2] * self.e2[2],
                          f[0] * self.e1[0] + f[1] * self.e1[1] + f[2] * self.e1[2]) / D2R

    def pointing(self, phi, h):
        """(alt, az) for base rotation phi and tube elevation h above the base plane."""
        c, s, sh, ch = math.cos(phi * D2R), math.sin(phi * D2R), math.sin(h * D2R), math.cos(h * D2R)
        p = [ch * (c * self.e1[i] + s * self.e2[i]) + sh * self.axis[i] for i in range(3)]
        return math.asin(max(-1.0, min(1.0, p[2]))) / D2R, (math.atan2(p[0], p[1]) / D2R) % 360.0


class SkylineScan:
    """Background job. `rig` must provide:
        call(method, params) -> reply dict      send one command to the scope
        pointing() -> (alt, az) or None         fresh mount position, degrees
        mount() -> dict                         {'equ_mode':..,'close':..}
        site() -> (lat, lon) or None
        view() -> (state, stage)
        frame(newer_than) -> BGR image or None  a wide-camera frame newer than a timestamp
        log(text)

    Cable protection: the scan never turns the base a full circle. Starting
    from the parked (home) position it sweeps at most HALF_TURN one way, comes
    back through home, sweeps the other way and comes back again. Every mount
    reading updates a running total of how far the base has turned (`wind`);
    the scan stops if that total passes WIND_LIMIT, if the mount jumps further
    than it could have moved between two readings, or if it ends a move
    somewhere other than where it was sent. Moves are made in small steps so
    the firmware has no reason to go the long way round.
    """
    HALF_TURN = 178.0
    WIND_LIMIT = 200.0
    STEP = 32.0                       # largest base rotation per move, degrees

    def __init__(self, rig, data_dir):
        self.rig = rig
        self.data_dir = data_dir
        self.lock = threading.Lock()
        self.state = "idle"            # idle | running | done | error | aborted
        self.msg = ""
        self.step = 0
        self.steps = 0
        self.started = None
        self.wind = 0.0                # net base rotation since home, degrees
        self.wind_max = 0.0
        self._phi = None
        self._abort = False
        self._closing = False
        self._thread = None
        self.max_alt = 40.0
        self.hfov = None
        self.lat = self.lon = None
        self.sun_alt = None

    def status(self):
        with self.lock:
            return {"state": self.state, "msg": self.msg, "step": self.step, "steps": self.steps,
                    "started": self.started, "wind": round(self.wind, 1), "wind_max": round(self.wind_max, 1),
                    "sun_alt": None if self.sun_alt is None else round(self.sun_alt, 1)}

    def start(self, max_alt=40.0, hfov=None):
        with self.lock:
            if self.state == "running":
                raise RuntimeError("a skyline scan is already running")
            self.state, self.msg, self.step, self.steps = "running", "starting", 0, 0
            self.started = time.time()
            self.wind, self.wind_max, self._phi, self._abort = 0.0, 0.0, None, False
            self._closing = False
            self.lat = self.lon = self.sun_alt = None
            self.max_alt = max(15.0, min(60.0, float(max_alt)))
            self.hfov = float(hfov) if hfov else None
        self._thread = threading.Thread(target=self._run, name="skyline", daemon=True)
        self._thread.start()

    def abort(self):
        self._abort = True

    # -- helpers
    def _say(self, msg, step=None):
        with self.lock:
            self.msg = msg
            if step is not None:
                self.step = step
        self.rig.log("Skyline scan: " + msg)

    def _check(self):
        if self._abort:
            raise ScanAborted()
        if self.lat is not None and not self._closing:
            self.sun_alt = sun_altaz(time.time(), self.lat, self.lon)[0]
            if self.sun_alt > SUN_STOP:
                raise SunGuard("the Sun is %.1f degrees below the horizon" % -self.sun_alt)

    def _cmd(self, method, params=None, must=True):
        r = self.rig.call(method, params)
        ok = isinstance(r, dict) and r.get("code") in (0, None)
        if must and not ok:
            raise RuntimeError("%s was refused by the scope (%s)" % (
                method, (r or {}).get("error") or (r or {}).get("code")))
        return ok

    def _wait(self, cond, timeout, what):
        end = time.time() + timeout
        while time.time() < end:
            self._check()
            if cond():
                return True
            time.sleep(0.5)
        raise RuntimeError("timed out waiting for " + what)

    def _read(self):
        """Read the mount and add its movement to the running rotation total."""
        cur = self.rig.pointing()
        if cur is None:
            return None
        phi = self.frame.angle(cur[0], cur[1])
        if phi is not None:
            if self._phi is not None:
                d = _wrap(phi - self._phi)
                if abs(d) > 100.0:
                    raise CableGuard("lost track of the base rotation (it jumped %.0f degrees "
                                     "between two readings)" % abs(d))
                with self.lock:
                    self.wind += d
                    self.wind_max = max(self.wind_max, abs(self.wind))
            self._phi = phi
            if abs(self.wind) > self.WIND_LIMIT:
                raise CableGuard("the base has turned %.0f degrees from home - stopping to "
                                 "protect the cable" % abs(self.wind))
        return cur

    def _settle(self, timeout=70):
        """Wait until the mount has stopped moving; returns (alt, az)."""
        last, still, end = None, 0, time.time() + timeout
        while time.time() < end:
            self._check()
            time.sleep(0.6)
            cur = self._read()
            if cur is None:
                continue
            if last and abs(cur[0] - last[0]) < 0.03 and \
                    abs(_wrap(cur[1] - last[1])) * math.cos(cur[0] * D2R) < 0.03:
                still += 1
                if still >= 2:
                    return cur
            else:
                still = 0
            last = cur
        raise RuntimeError("the mount did not settle")

    def _slew(self, alt, az):
        """One goto, then hold still. Returns the actual (alt, az)."""
        ra, dec = altaz_to_radec(alt, az, self.lat, self.lon, time.time())
        self._cmd("scope_goto", [round(ra, 5), round(dec, 4)])
        time.sleep(0.8)
        self._settle()
        self._cmd("scope_set_track_state", False, must=False)   # hold still on the landscape
        time.sleep(0.5)
        return self._settle(25)

    def _turn_to(self, rel):
        """Walk the base to `rel` degrees from home in small steps, tube held high."""
        h = 55.0 if self.eq else 25.0
        for _ in range(40):
            gap = rel - self.wind
            if abs(gap) <= 6.0:
                return
            nxt = self.wind + max(-self.STEP, min(self.STEP, gap))
            before = self.wind
            al, az = self.frame.pointing(self.phi0 + nxt, h)
            self._slew(al, az)
            if abs(self.wind - nxt) > 20.0:
                raise CableGuard("the mount did not turn the way it was asked to "
                                 "(wanted %.0f, now at %.0f degrees from home)" % (nxt, self.wind))
            if abs(self.wind - before) < 2.0:
                raise RuntimeError("the mount is not turning")
        raise RuntimeError("could not reach the requested rotation")

    def _goto_shot(self, alt, az, rel):
        """Go to one picture position whose base rotation is `rel` from home."""
        if abs(rel - self.wind) > self.STEP:
            self._turn_to(rel - math.copysign(self.STEP * 0.8, rel - self.wind))
        actual = self._slew(alt, az)
        if abs(self.wind - rel) > 25.0:
            raise CableGuard("the mount took an unexpected route to azimuth %.0f "
                             "(%.0f instead of %.0f degrees from home)" % (az, self.wind, rel))
        return actual

    def _grab(self):
        t0 = time.time()
        end = t0 + 25
        while time.time() < end:
            self._check()
            img = self.rig.frame(t0 + 1.0)
            if img is not None:
                return img
            time.sleep(0.2)
        raise RuntimeError("no picture from the wide camera")

    def _calibrate(self, alt0, az0):
        """Work out the camera's scale and orientation from two small moves:
        the landscape shifts in the picture by a known angle."""
        a0 = self._slew(alt0, az0)
        f0 = self._grab()
        h, w = f0.shape[:2]
        g0 = cv2.cvtColor(f0, cv2.COLOR_BGR2GRAY).astype(np.float32)
        win = cv2.createHanningWindow((w, h), cv2.CV_32F)
        p0 = dirv(a0[0], a0[1])
        rows_ab, rows_px = [], []
        for dalt, daz in ((0.0, 3.0), (3.0, 0.0)):
            self._check()
            a1 = self._slew(alt0 + dalt, az0 + daz)
            g1 = cv2.cvtColor(self._grab(), cv2.COLOR_BGR2GRAY).astype(np.float32)
            (sx, sy), resp = cv2.phaseCorrelate(g0, g1, win)
            if resp < 0.03:
                raise RuntimeError("could not follow the landscape between two pictures "
                                   "(too dark or too featureless) - try in twilight or daylight")
            p1, d1, t1 = tube_basis(a1[0], a1[1], self.eq, self.lat)
            wp = p0[0] * p1[0] + p0[1] * p1[1] + p0[2] * p1[2]
            rows_ab.append([(p0[0] * d1[0] + p0[1] * d1[1] + p0[2] * d1[2]) / wp,
                            (p0[0] * t1[0] + p0[1] * t1[1] + p0[2] * t1[2]) / wp])
            rows_px.append([sx, sy])
        ab, px = np.array(rows_ab, np.float64), np.array(rows_px, np.float64)
        if abs(np.linalg.det(ab)) < 1e-7:
            raise RuntimeError("calibration moves were too small")
        m = np.linalg.solve(ab, px).T                 # px = M . ab
        fx, fy = np.linalg.norm(m[:, 0]), np.linalg.norm(m[:, 1])
        f = (fx + fy) / 2.0
        if not (0.6 < fx / fy < 1.6) or f < w * 0.3 or f > w * 14:
            raise RuntimeError("calibration gave an implausible camera scale")
        return m.tolist()

    def _plan_shots(self, hfov, vfov):
        """Picture positions, ordered as two half-turn sweeps out from home."""
        # in alt-az mode the picture is level, so its full width is usable; in EQ
        # mode it is rolled by a different amount everywhere, so use the short side
        small = min(hfov, vfov)
        step_v = (small if self.eq else vfov) * 0.7
        step_h = (small if self.eq else hfov) * 0.62
        alts, top = [], -5.0
        while top < self.max_alt and len(alts) < 8:
            c = max(6.0, top + step_v / 2.0)
            alts.append(c)
            top = c + step_v / 2.0
        shots = []
        for al in alts:
            n = max(6, int(math.ceil(360.0 * math.cos(al * D2R) / step_h)))
            for i in range(n):
                az = (i + 0.5) * 360.0 / n
                phi = self.frame.angle(al, az)
                if phi is None:
                    continue
                rel = _wrap(phi - self.phi0)
                if abs(rel) <= self.HALF_TURN:
                    shots.append((al, az, rel))
        # Lowest rings first, so a scan cut short (sunrise, stop button) still has
        # the whole horizon. Each half-turn shoots one ring on the way out and the
        # next ring on the way back, so no trip is wasted.
        rings = sorted(set(sh[0] for sh in shots))
        legs = []
        for k in range(0, len(rings), 2):
            out = [sh for sh in shots if sh[0] == rings[k]]
            back = [sh for sh in shots if k + 1 < len(rings) and sh[0] == rings[k + 1]]
            legs.append(sorted([sh for sh in out if sh[2] < 0], key=lambda sh: -sh[2]) +
                        sorted([sh for sh in back if sh[2] < 0], key=lambda sh: sh[2]))
            legs.append(sorted([sh for sh in out if sh[2] >= 0], key=lambda sh: sh[2]) +
                        sorted([sh for sh in back if sh[2] >= 0], key=lambda sh: -sh[2]))
        return legs

    def _finish(self, pano, cam, hfov, vfov, total, taken, failed, why):
        """Turn whatever was photographed into a skyline and save it."""
        img, valid = pano.result()
        prof = find_skyline(img, valid)
        known = sum(1 for v in prof if v is not None)
        cv2.imwrite(os.path.join(self.data_dir, "skyline.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 88])
        save_horizon(self.data_dir, {
            "updated": time.strftime("%Y-%m-%d %H:%M:%S"), "source": "scan", "complete": taken + failed >= total,
            "profile": prof, "known_deg": known, "hfov": round(hfov, 2), "vfov": round(vfov, 2),
            "camera": cam, "equ_mode": self.eq, "lat": self.lat, "lon": self.lon,
            "shots": total, "taken": taken, "skipped": failed, "max_turn": round(self.wind_max, 1), "ended": why,
            "pano": {"step": PANO_STEP, "alt_top": PANO_ALT[1], "alt_bottom": PANO_ALT[0]}})
        return known

    def _partial(self, why):
        """Save what was photographed before an early stop; returns a note for the status line."""
        c = getattr(self, "_ctx", None)
        self._ctx = None
        if not c or c["taken"] < 4:
            return ""
        try:
            known = self._finish(c["pano"], c["cam"], c["hfov"], c["vfov"], c["total"], c["taken"], c["failed"], why)
            return " - kept %d pictures: skyline found for %d of 360 degrees" % (c["taken"], known)
        except Exception as e:
            return " - could not save the partial result (%s)" % e

    # -- the job
    def _run(self):
        rig = self.rig
        started_view = False
        tracking_ok = True
        self._ctx = None
        try:
            if cv2 is None:
                raise RuntimeError("OpenCV is not installed on this PC")
            site = rig.site()
            if not site:
                raise RuntimeError("the scope's location is not known yet")
            self.lat, self.lon = site
            sun = sun_altaz(time.time(), self.lat, self.lon)[0]
            if sun >= SUN_START:
                raise RuntimeError("the Sun is %s - the scan only runs in twilight or at night, so the "
                                   "telescope is never swept past the Sun" % (
                                       "up" if sun > 0 else "only %.1f degrees below the horizon" % -sun))
            mt = rig.mount() or {}
            self.eq = bool(mt.get("equ_mode"))
            self.frame = AxisFrame(self.eq, self.lat)
            if rig.view()[0] == "working":
                raise RuntimeError("the scope is busy - stop the current view or plan first")

            # home = the parked position: that is where the cable is taken to be unwound
            if not mt.get("close"):
                self._say("parking first, to start from the home position")
                self._cmd("scope_park", {"equ_mode": self.eq})
                self._wait(lambda: (rig.mount() or {}).get("close") is True, 90, "the scope to park")
                time.sleep(2)
            self._say("switching on the cameras")
            self._cmd("iscope_start_view", {"mode": "scenery"})
            started_view = True
            self._wait(lambda: rig.view()[1] == "RTSP", 45, "the cameras to start")
            self._say("opening the arm")
            self._cmd("scope_move_to_horizon", None, must=False)
            self._wait(lambda: (rig.mount() or {}).get("close") is False, 70, "the arm to open")
            time.sleep(2)
            home = self._settle(40)
            self.phi0 = self.frame.angle(home[0], home[1])
            if self.phi0 is None:
                self.phi0 = 0.0
                self._phi = None
            with self.lock:
                self.wind = 0.0                       # rotation is counted from here
            frame0 = self._grab()
            fh, fw = frame0.shape[:2]

            if self.hfov:
                cam = default_camera(fw, fh, self.hfov)
            else:
                self._say("measuring the wide camera's field of view")
                # look at the horizon (it has the detail to lock on to), at the
                # azimuth that needs the least base rotation from home
                best = None
                for z in range(0, 360, 5):
                    ph = self.frame.angle(12.0, float(z))
                    if ph is not None and (best is None or abs(_wrap(ph - self.phi0)) < best[0]):
                        best = (abs(_wrap(ph - self.phi0)), float(z))
                for attempt in range(3):
                    try:
                        cam = self._calibrate(12.0, best[1] if best else 90.0)
                        break
                    except RuntimeError as e:
                        if "landscape" not in str(e) or attempt == 2:
                            raise
                        self._say("too dark to lock on to the landscape yet - trying again in 3 minutes")
                        for _ in range(180):
                            self._check()
                            time.sleep(1.0)
            f = (math.hypot(cam[0][0], cam[1][0]) + math.hypot(cam[0][1], cam[1][1])) / 2.0
            hfov = 2 * math.atan((fw / 2.0) / f) / D2R
            vfov = 2 * math.atan((fh / 2.0) / f) / D2R
            self._say("wide camera sees %.1f x %.1f degrees" % (hfov, vfov))

            legs = self._plan_shots(hfov, vfov)
            total = sum(len(leg) for leg in legs)
            with self.lock:
                self.steps = total
            pano = Panorama()
            ctx = {"pano": pano, "cam": cam, "hfov": hfov, "vfov": vfov, "total": total, "taken": 0, "failed": 0}
            self._ctx = ctx
            fdir = os.path.join(self.data_dir, "skyline_frames")
            os.makedirs(fdir, exist_ok=True)
            for fn in os.listdir(fdir):
                try:
                    os.remove(os.path.join(fdir, fn))
                except OSError:
                    pass
            meta = open(os.path.join(fdir, "frames.jsonl"), "w", encoding="utf-8")
            meta.write(json.dumps({"camera": cam, "hfov": hfov, "vfov": vfov, "equ_mode": self.eq,
                                   "lat": self.lat, "lon": self.lon, "phi0": self.phi0}) + "\n")
            done = 0
            try:
                for leg in legs:
                    for al, az, rel in leg:
                        self._check()
                        done += 1
                        self._say("picture %d of %d (azimuth %.0f, altitude %.0f)" % (done, total, az, al), done)
                        try:
                            actual = self._goto_shot(al, az, rel)
                        except (ScanAborted, CableGuard, SunGuard):
                            raise
                        except RuntimeError as e:
                            ctx["failed"] += 1
                            rig.log("Skyline scan: skipped azimuth %.0f altitude %.0f - %s" % (az, al, e))
                            if ctx["failed"] > max(6, total // 3):
                                raise RuntimeError("the mount refused too many of the moves")
                            continue
                        frame = self._grab()
                        pano.add(frame, tube_basis(actual[0], actual[1], self.eq, self.lat), cam)
                        ctx["taken"] += 1
                        name = "f%03d.jpg" % done
                        cv2.imwrite(os.path.join(fdir, name), frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
                        meta.write(json.dumps({"file": name, "alt": actual[0], "az": actual[1], "t": time.time(),
                                               "wind": round(self.wind, 2)}) + "\n")
                        meta.flush()
                    self._say("turning back to the home position")
                    self._turn_to(0.0)
            finally:
                meta.close()

            self._say("working out the skyline", total)
            known = self._finish(pano, cam, hfov, vfov, total, ctx["taken"], ctx["failed"], "complete")
            with self.lock:
                self.state = "done"
                self.msg = "finished - skyline found for %d of 360 degrees" % known
            rig.log("Skyline scan: " + self.msg)
        except ScanAborted:
            with self.lock:
                self.state, self.msg = "aborted", "stopped" + self._partial("stopped")
            rig.log("Skyline scan: " + self.msg)
        except SunGuard as e:
            with self.lock:
                self.state, self.msg = "done", "stopped before sunrise (%s)%s" % (e, self._partial("sun"))
            rig.log("Skyline scan: " + self.msg)
        except CableGuard as e:
            tracking_ok = "lost track" not in str(e)
            with self.lock:
                self.state, self.msg = "error", "cable protection: %s%s" % (e, self._partial("cable guard"))
            rig.log("Skyline scan stopped by cable protection: %s" % e)
        except Exception as e:
            with self.lock:
                self.state, self.msg = "error", str(e) + self._partial("error")
            rig.log("Skyline scan failed: %s" % e)
        finally:
            self._abort = False
            self._closing = True              # going home is always allowed
            # unwind before parking, so the cable ends up where it started
            note = ""
            try:
                if started_view and tracking_ok and abs(self.wind) > 8.0:
                    rig.log("Skyline scan: unwinding %.0f degrees back to home" % abs(self.wind))
                    self._turn_to(0.0)
            except Exception as e:
                note = " The base is still turned about %.0f degrees from home - check the cable." % self.wind
                rig.log("Skyline scan: could not unwind (%s).%s" % (e, note))
            if started_view and not tracking_ok:
                note = " The scope was left where it stopped - check the cable before moving it."
            try:
                if started_view:
                    rig.call("iscope_stop_view", None)
                    if not note:
                        time.sleep(1.5)
                        rig.call("scope_park", {"equ_mode": bool((rig.mount() or {}).get("equ_mode"))})
            except Exception:
                pass
            if note:
                with self.lock:
                    self.msg += note
