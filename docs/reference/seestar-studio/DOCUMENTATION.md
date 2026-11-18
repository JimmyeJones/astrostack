# Seestar PC Monitoring — Full Documentation

Everything set up on this PC to monitor a **ZWO Seestar S30** smart telescope,
why it works the way it does, and how to run, extend, or troubleshoot it.

Last updated: 2026-11-17.

---

## Table of contents

1. [Summary](#1-summary)
2. [What's installed on this PC](#2-whats-installed-on-this-pc)
3. [The Seestar Monitor (the lightweight dashboard)](#3-the-seestar-monitor-the-lightweight-dashboard)
4. [Accessing it from your phone (Tailscale)](#4-accessing-it-from-your-phone-tailscale)
5. [BlueStacks (the full official app, as a fallback)](#5-bluestacks-the-full-official-app-as-a-fallback)
6. [How the Seestar protocol works](#6-how-the-seestar-protocol-works)
7. [The authentication key](#7-the-authentication-key)
8. [Network, ports & firewall](#8-network-ports--firewall)
9. [File inventory](#9-file-inventory)
10. [Troubleshooting](#10-troubleshooting)
11. [Ideas / possible extensions](#11-ideas--possible-extensions)

---

## 1. Summary

The official Seestar app is Android-only, so viewing the scope from a PC normally
means running it inside an Android emulator (BlueStacks), which is heavy on CPU
and RAM. To replace that for **monitoring**, this project adds a tiny Python web
dashboard — **Seestar Monitor** — that talks to the telescope directly over the
LAN and shows the live observation in any browser, including your phone over
Tailscale.

Two ways to reach the scope now exist on this PC:

| Tool | Use it for | Weight |
|------|-----------|--------|
| **Seestar Studio** (this project) | Full control **and** monitoring from a browser: live image, imaging, GoTo, focus, mount, albums, raw-RPC console, settings | Tiny (a Python script) |
| **Seestar Monitor** (this project) | Strictly read-only watching of a running plan | Tiny (a Python script) |
| **BlueStacks + Seestar app** | The official app, as a fallback | Heavy (Android emulator) |

The monitor is **strictly read-only** — it never sends a command that could move
or stop the scope — so it can never disturb a running observation.

- **Scope:** ZWO Seestar S30, firmware 9.75, LAN IP `192.168.1.100`
  (auto-discovered if it changes).
- **Dashboard:** `http://127.0.0.1:5556` on this PC, and on the tailnet at
  `http://100.64.0.10:5556`.

---

## 2. What's installed on this PC

- **Seestar Monitor** — `<PROJECT>\` (this folder). Pure-Python, uses
  the standard library plus the `cryptography` package (already installed).
- **BlueStacks 5** — installed via winget (`BlueStack.BlueStacks`), with an
  Android 11 instance named *"BlueStacks App Player 1"* running the real Seestar
  app, signed in to Google Play. Kept as a full-control fallback.
- **Python 3.12** (Windows Store) and **Python 3.11/3.13** — the monitor runs on
  3.12 here. `cryptography` 47.0.0 is installed.
- **Tailscale** — this PC is `your-pc` at tailnet IP `100.64.0.10`.

---

## 3. The Seestar Monitor (the lightweight dashboard)

### Run it

Double-click **`Start Seestar Monitor.bat`**, or in a terminal:

```
python seestar_monitor.py --host 192.168.1.100 --bind tailscale
```

Then open **http://127.0.0.1:5556** on this PC.

### What it shows

- **Live stacked image**, refreshed as the stack grows (click for full-res)
- **Target** name and coordinates (RA / Dec)
- **Frames stacked** / dropped and total **integration time**
- **Exposure** state, sub-length and gain
- **Battery** % + charging, **sensor temperature**, **free disk**
- Device info (model, firmware, serial) and detected **star annotations**
- A live **event log** of the observation

### Command-line options

| Option | Default | Meaning |
|--------|---------|---------|
| `--host` | `192.168.1.100` | Seestar IP on the LAN |
| `--port` | `4700` | Scope control port |
| `--web`  | `5556` | Local web UI port |
| `--key`  | `./seestar.pem` | Interop key for full mode |
| `--bind` | `127.0.0.1` | Where to listen: `127.0.0.1` (this PC only), `tailscale` (localhost + tailnet), `0.0.0.0` (all networks), or a comma-separated list of IPs |

### Monitor mode vs full mode

- **Full mode** (active here): the file `seestar.pem` is present, so the tool
  completes the firmware's authentication handshake and shows *everything* above,
  including the live image.
- **Monitor mode** (if `seestar.pem` is missing): the tool still shows the
  unauthenticated broadcast stream — stacking progress, exposure state and
  temperature — which is enough to confirm a plan is running. Target, battery,
  disk and the live image are not available without the key.

### HTTP endpoints (for reference / scripting)

The local server exposes:

- `GET /` — the dashboard page
- `GET /api/state` — a JSON snapshot of all current status
- `GET /api/image?kind=thumb|full` — the current stacked image (proxied from the
  scope's own HTTP server)

### Reliability features

- **Auto-reconnect** with backoff if the socket drops.
- **Auto-discovery**: if the scope stops responding (e.g. DHCP changed its IP),
  the tool broadcasts the Seestar discovery ping (UDP 4720) and switches to the
  new IP automatically.
- **Passive in monitor mode**: it sends nothing, because the scope drops a client
  that requests verification but never completes it. In full mode it completes
  the handshake and then polls, which keeps the session stable.
- **One copy only**: the scope caps simultaneous connections. Running several
  monitors (or many stale copies) causes reconnect churn. Run just one.

---

## 3b. Seestar Studio (full control UI)

**Seestar Studio** (`seestar_studio.py` + `seestar_studio_ui.py`) is the
full-featured sibling of the monitor: a modern, space-themed single-page web app
that both monitors **and controls** the scope. Launch it with
**`Start Seestar Studio.bat`** (port 5556, tailnet-enabled) and open the same
URLs as the monitor.

> Run **one** Seestar app at a time — Studio and Monitor share port 5556, and the
> scope limits simultaneous connections.

### Panels

- **Live** — big live stacked image, frames/integration/exposure, and
  Start/Stop view with a mode selector (Stargazing / Solar / Lunar / Planetary /
  Scenery).
- **Camera** — gain, sub-exposure, LP filter on/off, save frame, dark-frame
  library.
- **Target** — manual GoTo (name + RA/Dec, optional LP), plus a one-tap
  catalogue of popular objects (Messier favourites, NGC 7000, …). Sun/Moon/planets
  use the matching mode on the Live tab.
- **Focus** — autofocus start/stop and manual focuser steps; live position.
- **Mount** — a directional nudge pad with adjustable speed, live RA/Dec, and
  Park.
- **Albums** — a gallery of captures pulled from the scope's file server; click a
  thumbnail for the full image.
- **Console** — a raw JSON-RPC sender: type any `method` + `params` and see the
  reply. This is the "**and more**" escape hatch for anything the firmware
  supports that isn't a dedicated button, and a live event log.
- **Settings** — device info, dew-heater power, and reboot/shutdown (confirmed).

### Safety model

- **Monitoring is read-only** (same getters as the monitor).
- **Control actions change the scope** and are only sent when *you* click a
  control. Disruptive ones (GoTo, Stop, Park, dark frames, reboot, shutdown)
  **ask for confirmation** first. The app never sends a control command on its
  own; idle polling uses getters only. So nothing moves unless you tell it to.
- Full control needs the interop key (`seestar.pem`) and the `cryptography`
  package. Without the key, Studio still runs but control is disabled (monitor
  only) and the UI says so.

### How control is implemented

Each control maps to a standard community Seestar JSON-RPC method (the same ones
`seestar_alp` uses), sent synchronously so the UI can show success/failure:

| Action | Method |
|--------|--------|
| Start / stop view | `iscope_start_view` / `iscope_stop_view` |
| GoTo target | `goto_target` (RA hours, Dec deg, J2000) |
| Stop slew | `stop_goto` |
| Autofocus | `start_auto_focuse` / `stop_auto_focuse` |
| Focuser step | `move_focuser` |
| Mount nudge | `scope_speed_move` |
| Park / sync | `scope_park` / `scope_sync` |
| Gain / exposure | `set_control_value` |
| LP filter | `set_setting` |
| Dew heater | `pi_output_set2` |
| Reboot / shutdown | `pi_reboot` / `pi_shutdown` |

If your firmware expects a slightly different shape for any action, send the exact
method and params from the **Console** tab — that always works. The backend also
exposes `POST /api/action` (named actions) and `POST /api/rpc` (arbitrary method)
for scripting.

---

## 4. Accessing it from your phone (Tailscale)

The launcher binds the dashboard to the **tailnet** as well as this PC. From any
device signed in to your Tailscale account:

- **http://100.64.0.10:5556** — this PC's Tailscale IP
- **http://your-pc.your-tailnet.ts.net:5556** — MagicDNS name (if enabled)

Both the phone and this PC must be connected to Tailscale. Only your tailnet can
reach it — nothing else on your home Wi-Fi — and **no Windows Firewall change was
required** (see §8).

> Tip: add the phone URL to your home screen for one-tap access while imaging.

**Privacy note:** the dashboard has no login. Anyone on *your* tailnet can view it
(read-only, telescope status only). To restrict to this PC, launch with
`--bind 127.0.0.1`. To expose on all networks including plain Wi-Fi (less
private), use `--bind 0.0.0.0`.

---

## 5. BlueStacks (the full official app, as a fallback)

BlueStacks 5 is installed with an **Android 11 (64-bit)** instance, *"BlueStacks
App Player 1"*, running the genuine Seestar app signed in to Google Play. Use it
when you need full control (starting/stopping plans, slewing, changing settings) —
things the read-only monitor deliberately does not do.

Setup notes / changes made:

- The default *"BlueStacks App Player"* instance is **Android 7** and too old for
  the current Seestar app; it is stopped and can be deleted in the BlueStacks
  **Multi-Instance Manager**.
- Local Android debugging (**ADB**) was enabled in BlueStacks settings
  (`bst.enable_adb_access="1"`) to allow automated setup. It is **local-only**,
  not remote. The original settings file is backed up at
  `C:\ProgramData\BlueStacks_nxt\bluestacks.conf.bak-claude`.
- To silence BlueStacks ads: Settings → Preferences, turn off the ad and
  featured-banner options.

Since the monitor now covers watching a plan, you can **close BlueStacks to free
CPU/RAM** when you don't need full control.

---

## 6. How the Seestar protocol works

The Seestar exposes a local API on the LAN. No cloud is involved.

### Control channel — TCP port 4700

- **Newline-delimited JSON-RPC.** Each message is one JSON object terminated by
  `\r\n`. Requests look like `{"id": 10, "method": "get_device_state"}`; replies
  echo the `id` and carry a `result` and a `code` (0 = success).
- The scope also **broadcasts status events** to every connected client, e.g.
  `{"Event":"Stack","stacked_frame":376,"dropped_frame":0,...}`,
  `{"Event":"Exposure","state":"complete","exp_ms":20000,"gain":200}`,
  `{"Event":"PiStatus","temp":32.7,"battery_capacity":26}`. These require **no
  authentication** — that's what monitor mode reads.

### Useful read-only methods (used by the monitor)

| Method | Returns |
|--------|---------|
| `get_device_state` | device info, `setting`, `storage`, `pi_status` (battery/temp), camera, focuser, mount |
| `get_view_state` | current `View`: target name, `target_ra_dec`, mode, gain, `Stack` (stacked/dropped frames), `Exposure`, star `Annotate` results |
| `get_disk_volume` | `{"totalMB":…, "freeMB":…}` |
| `get_albums` | list of saved works with thumbnail paths (used to locate the live image) |
| `scope_get_equ_coord` | current RA/Dec |

### The authentication gate (firmware 7.18+)

Newer firmware (this scope is **9.75**) refuses every method except the handshake
until the client proves itself with an RSA challenge-response:

1. Client calls `get_verify_str` → scope returns `{"result":{"str":"<random>"}}`.
2. Client **signs** that string with **RSA PKCS#1 v1.5 over SHA-1** using a
   private key, base64-encodes it, and calls
   `verify_client` with `{"sign":"<b64>","data":"<the str>"}`.
3. Scope replies `code: 0` on success (on firmware 9.75 the result also contains
   a `key_envelope`; plaintext reads still work afterward).
4. Client calls `pi_is_verified` to confirm.

If the signature is wrong the scope returns **code 207** ("rejected"). If the
method is unknown (old firmware) it returns **code 103**, and no auth is needed.

Exact wire shapes:

```
--> {"id":1,"method":"get_verify_str","params":"verify"}
<-- {"result":{"str":"2WrFAU3axJOYI5ENGbbEehgSrPPj1JkC"},"code":0,"id":1}
--> {"id":2,"method":"verify_client","params":{"sign":"<base64 RSA/SHA1 sig>","data":"2WrF...JkC"}}
<-- {"result":{"key_envelope":{...}},"code":0,"id":2}
--> {"id":3,"method":"pi_is_verified","params":"verify"}
<-- {"code":0,"id":3}
```

### The live image — HTTP port 80

The scope runs a plain **HTTP file server on port 80**. `get_albums` returns the
current work's thumbnail path, e.g.
`MyWorks/M 45_mosaic/Stacked_381_mosaic_M 45_20.0s_IRCUT_20261117-000001_thn.jpg`.
Fetching that path over HTTP returns the JPEG thumbnail; dropping the `_thn`
suffix gives the full-resolution image. The monitor polls `get_albums`, picks the
newest `Stacked_*` file, and proxies it at `/api/image`. This is read-only and
does not disturb imaging.

### Discovery — UDP port 4720

Broadcasting `{"id":1,"method":"scan_iscope","params":""}` to UDP 4720 makes the
scope reply with its address — used for auto-discovery if the IP changes.

### Ports summary

| Port | Protocol | Purpose |
|------|----------|---------|
| 4700 | TCP | JSON-RPC control + event broadcast |
| 80 | TCP/HTTP | file server (images, thumbnails) |
| 4720 | UDP | discovery (`scan_iscope`) |
| 4800 / 4801 / 4500 | TCP | imaging / internal (binary) |
| 4554 | TCP/RTSP | live video stream — only active in certain preview modes, **not** during stacking |

---

## 7. The authentication key

Full mode needs the RSA private key the app uses to sign the challenge.

- **What it is:** a PKCS#8 RSA private key, stored here as **`seestar.pem`**.
- **Where it comes from:** the owner supplies it; it is **not** in this repository and
  must never be committed. It is the **same key for all Seestar devices** (not tied to
  a scope's serial, network, or account).
- **Will it change?**
  - It does **not** change because of your device, a reboot, or your network.
  - It **can** change only if **ZWO rotates it in a future firmware + app
    update** (shipping a new key in the app and a matching public key in
    firmware). They've kept it stable across many versions, but they are actively
    evolving this auth (9.75 already added the `key_envelope` step), so it is not
    guaranteed permanent.
  - **If it ever stops working:** the live image and battery/target go blank and
    the event log shows `verify_client rejected (code=207)`. The dashboard then
    falls back to **monitor mode** automatically (stacking progress, exposure,
    temperature — no key needed). To restore full mode, the owner supplies the
    updated key.

---

## 8. Network, ports & firewall

- **Scope:** `192.168.1.100` on the home LAN (DHCP; auto-rediscovered).
- **This PC tailnet:** IP `100.64.0.10`, name
  `your-pc.your-tailnet.ts.net`.
- **Dashboard ports:** TCP `5556` on `127.0.0.1` and on the tailnet IP.

**Windows Firewall:** default inbound is *Block* on all profiles, but **no change
was made and none is needed**:

- The Tailscale network adapter is on the **Private** profile.
- Tailscale's own `Tailscale-In` rule already **allows all inbound on the
  Domain/Private profiles**, so tailnet traffic to the dashboard is permitted.
- There is additionally an inbound allow-rule for the exact Python interpreter in
  use.

Because the server binds only to `127.0.0.1` and the `100.x` tailnet IP, other
devices on the home Wi-Fi cannot reach it — only your tailnet.

---

## 9. File inventory

Everything lives in **`<PROJECT>\`**:

| File | What it is |
|------|-----------|
| `seestar_studio.py` | **Studio** — full control app (server + control backend) |
| `seestar_studio_ui.py` | Studio's web UI (HTML/CSS/JS) |
| `Start Seestar Studio.bat` | Launcher for Studio (binds tailnet) |
| `seestar_monitor.py` | The read-only monitor program |
| `Start Seestar Monitor.bat` | Launcher for the monitor (binds tailnet) |
| `seestar.pem` | The interop RSA key (enables full control) — keep private |
| `README.md` | Short user quick-start |
| `DOCUMENTATION.md` | This full reference |


---

## 10. Troubleshooting

**Dashboard says "scope offline" / keeps reconnecting**
- Make sure only **one** copy of the monitor is running (the scope limits
  simultaneous connections; several clients cause churn). The official app also
  holds a connection — one app + one monitor is fine.
- Check the scope is powered and on the network: `ping 192.168.1.100`.

**Live image or fields are blank**
- You may be in monitor mode — confirm `seestar.pem` sits next to the script.
- The scope may be idle (not currently viewing/stacking), so there's no image yet.
- The event log will show `verify_client rejected (code=207)` if the key is no
  longer accepted (see §7).

**Phone can't open the dashboard**
- Confirm Tailscale is connected on both the phone and this PC.
- Confirm the PC is serving the tailnet: it should be listening on
  `100.64.0.10:5556` (the launcher uses `--bind tailscale`).
- Try the IP URL rather than the MagicDNS name if MagicDNS isn't enabled.

**Port 5556 already in use**
- A previous copy is still running. Close it, or start with `--web 5557` and open
  that port instead.

**Scope got a new IP**
- The monitor rediscovers it automatically. You can also pass `--host <new-ip>`.

---

## 11. Ideas / possible extensions

- **Tune control shapes**: the Studio control actions use standard community RPC
  shapes; once tested against the scope, any that need a different param layout
  can be adjusted in `build_action()` (the Console tab confirms the right shape).
- **History/graphs**: log temperature, battery and frame rate over the night.
- **Alerts**: notify when the plan finishes, battery drops, or dropped frames
  spike.
- **Run as a service / auto-start**: launch the monitor on boot so the tailnet
  dashboard is always available.

All of these are optional — the current setup already delivers reliable,
low-overhead monitoring from this PC and your phone.

---

## Studio v2 additions (2026-11-17)

Added after the scope ran out of battery mid-session (last contact 04:07, 1 %).

### New features
| Feature | Where | Notes |
|---|---|---|
| Auto-save full-res stack to PC | `Housekeeper.step()` | Every `--autosave N` min (default 10) while stacking; `captures\<target>\<target>_<time>_<frames>f.jpg`, newest 30 per target kept. HTTP GET only. |
| Last-known state | `data\last_state.json`, `data\last_live.jpg` | Survives scope power loss and Studio restarts; UI marks data as "last known". |
| History | `data\history.jsonl`, `GET /api/history?h=6` | 30 s samples of battery / temp / frames; 24 h in memory. |
| Alerts | `State._alerts()` -> `alerts[]` in `/api/state` | offline (with battery diagnosis), batt 20/10/5 %, stalled stack, low disk. Browser beeps / notifies when the bell is on. |
| Battery estimate | `State._battery_estimate()` | %/h and hours left from the last hour's discharge slope. |
| Shared thumbnail cache | `Housekeeper` | One fetch from the scope every 15 s serves every browser. |
| Target planner | UI | 77 objects, altitude/peak time computed in the browser from the location stored on the scope (`location_lon_lat`) or entered in Settings. |
| Simulator / demo | `seestar_sim.py`, `--demo` | Fake scope: same JSON-RPC + verify handshake, events, albums, images. Test-only method `sim_set {"battery": 8}`. |

### New endpoints
`GET /api/history`, `GET /api/captures`, `GET /api/capture?f=<rel>[&dl=1]`,
`POST /api/save_now`, `GET /manifest.json`, `GET /icon.svg`; `/api/image` gained `&dl=1`
and falls back to the cached / auto-saved image when the scope is offline.

### New options
`--demo`, `--autosave MIN`, `--scope-http PORT`, `--data DIR`.

### Fixes
- **Reply race in `ScopeClient.call()`**: the reader thread removed the pending
  slot before the caller read it, so every control reported "failed" even though
  the scope had executed it. Found with the simulator; fixed.
- **Cross-site POST protection**: `/api/*` POSTs must be `application/json` and
  same-origin, so a web page in your browser cannot drive the telescope.
- **Single instance**: a second copy on the same port now fails to start (Windows
  used to allow both and split requests between them at random).

### Test status
All 13 control actions, the confirm dialogs, hold-to-slew, offline/reconnect and
alerts pass end-to-end **against the simulator**. The simulator encodes the same
community RPC shapes as `build_action()`, so this proves the plumbing, not that
firmware 9.75 accepts each shape - that still needs a run on the real scope.

---

## Studio v3 - full app feature set (2026-11-17)

Goal: every functional feature of the official app (not the social / challenge
filler). Command shapes were re-derived from two open-source projects that
document the official app's protocol - **seestarpy** (decompiled app v3.4.1 +
traffic captures) and **seestar_alp** - and several v1/v2 guesses turned out to
be wrong and were corrected.

### Corrected commands (v1/v2 had these wrong)
| Action | Was | Now (as the app sends it) |
|---|---|---|
| GoTo | `goto_target {...}` (not a firmware method) | `iscope_start_view {mode:"star", target_ra_dec:[ra_h,dec], target_name, lp_filter[, mosaic]}` |
| Stop slew | `stop_goto` | `iscope_stop_view {stage:"AutoGoto"}` |
| Stop stacking | - | `iscope_stop_view {stage:"Stack"}`; stop everything = `iscope_stop_view` |
| Sub-exposure | `set_control_value ["exposure",ms]` | `set_setting {exp_ms:{stack_l: ms}}` |
| LP filter | `set_setting {lp_filter}` | `set_setting {stack_lenhance: bool}` or `set_wheel_position [0 dark / 1 IR-cut / 2 LP]` |
| Focuser | `move_focuser {step: delta}` | `move_focuser {step: ABSOLUTE 1200-2600, ret_step:true}` (Studio adds the delta itself) |
| Park | `scope_park` | `scope_park {equ_mode:false}`; EQ mode = `scope_park {equ_mode:true}` |
| Sync | list or dict guess | `scope_sync [ra_h, dec]` |

### Added features
| Area | What | Method(s) |
|---|---|---|
| Live view | Live video for Sun / Moon / planets / scenery and star-mode preview, snapshot to PC | RTSP `rtsp://<ip>:4554/stream` (4555 wide) and binary frames on port 4800 (`begin_streaming`), re-served as MJPEG at `/api/video` (needs `opencv-python`, `numpy`) |
| Stacking | Start / stop stacking separately from the view | `iscope_start_stack {restart}` |
| Video | Record / time-lapse on the scope | `start_record_avi {raw, timelapse:{enable,delay_sec}}`, `stop_record_avi` |
| Targets | Sun, Moon, 7 planets (positions computed in the browser), auto-find, sky map, favourites, recents, framing/mosaic, slew-only | `iscope_start_view {mode:sun/moon/planet,...}`, `start_scan_planet`, `scope_goto [ra,dec]` |
| Plan | Build a night's schedule and run it **on the scope** | `set_view_plan {plan_name, update_time_seestar, list:[{target_id,target_name,alias_name,target_ra_dec,lp_filter,start_min,duration_min}]}`, `stop_func {name:"ViewPlan"}`, `clear_view_plan`; status from `iscope_get_app_state().ViewPlan` |
| Camera | Dithering, save sub-frames, DBE, star correction, trail removal, 4K drizzle, dark library, expert mode, wide camera, auto-AF, stack-after-GoTo, live-view exposure | `set_setting {...}` (whitelist `ALLOWED_SETTINGS`) |
| Mount | Tracking, open arm, EQ / Alt-Az, polar alignment + error, plate solve + result, sync, level bubble, compass, alt/az | `scope_set_track_state bool`, `scope_move_to_horizon`, `start_polar_align {restart,dec_pos_index}`, `start_solve`, `get_last_solve_result`, `get_device_state` |
| Device | Set location, sync clock, sound volume, beep, auto power-off, Wi-Fi info, delete images | `set_user_location {lat,lon,force}`, `pi_set_time [{year..sec,time_zone}]`, `play_sound {num}`, `delete_image {name:[...]}` |

`start_min` in a plan is minutes since local midnight on the scope's clock
(> 1440 = after midnight); Studio syncs the clock before sending.

### Deliberately not included
Firmware update, Wi-Fi / station setup, storage format, and the app's community
/ challenge / cloud features. Use the official app (BlueStacks fallback) for those.

### Test status
40+ actions, a full two-target plan run, both live-video paths, and every screen
pass against the simulator, which now models the real protocol (and rejects
wrong parameter shapes). **Nothing has been run against the real scope** - it has
been offline since 04:07 on 2026-11-17. First real session: watch the Console
tab's event log for any `code` other than 0.


## Real-scope verification (2026-11-17, firmware 9.75)

Every reversible control was exercised against the real Seestar S30 and
confirmed by reading the value back or watching the scope's events:
exposure, preview exposure, gain, LP filter, filter wheel, dither, DBE,
auto-focus toggle, dew heater, focuser, location, clock sync, beep, open arm,
hold-to-slew, tracking, GoTo (slew + auto-focus + plate solve + stack),
stop / resume stacking, stop view, live preview (binary port), scenery live
video (RTSP), snapshot, video record start/stop, plate solve, sync, slew-only,
dark frame start/stop, polar alignment start/stop, plan start/stop (incl.
mosaic items), park, EQ mode.

Not exercised (irreversible or disruptive): delete image, clear plan, reboot,
shutdown, Sun/Moon/planet modes.

Firmware facts learned:
- UDP discovery (4720) gets no reply on this network; Studio falls back to a
  TCP sweep of the /24 for port 4700.
- `get_view_state` returns `{}` after boot, and a stopped view lingers as
  state `cancel` with its old stage - both are treated as idle.
- `play_sound` numbers 1-15 exist (not 3); 80 does not.
- `scope_park {equ_mode}` SETS the mount mode. Park now keeps the current mode.
- `get_setting` contains the scope's hotspot password; it is stripped from
  `/api/state`.


## 3D pointing view (Mount tab)

The Mount tab shows a live 3D view of the scope: tripod, the scope itself, a
sky dome with compass points, Polaris / the polar axis, and the line of sight
to the current target. It is posed from `scope_get_horiz_coord` (alt/az),
`mount.equ_mode` (base tilted to the pole in EQ mode), `mount.close` (parked)
and the site latitude. Drag to rotate, scroll to zoom, double-click to reset.

The scope is a real CAD model rendered with WebGL, with the optical tube
articulated separately from the body. If WebGL or the model file is missing it
falls back to a simple block model.

- Model: "Seestar S30 Pro - Telescope" by WistowTbone,
  https://www.thingiverse.com/thing:7342818 - licensed CC BY-SA 4.0. It is the
  S30 Pro body (very close to the S30), measured by its author, not by ZWO.
- `model_src/Seestar_S30_Pro.obj` - the original file;
  `model_src/convert_model.py` turns it into `seestar_model.json`, which Studio
  serves at `/api/model`. Keep the attribution if you share these files.


## Later additions (2026-11-17, evening)

- **Plan tab**: "Copy this plan into the builder" pulls the plan that is on
  the scope (targets, times, filters, mosaic) into the builder so last night's
  plan can be re-sent or tweaked. Each target has a **Mosaic x** field (1-2);
  values above 1 are sent as `mosaic:{scale,angle:0}`. The "On the scope" list
  shows mosaic, filter, time stacked and why a target stopped (e.g. the
  firmware's `error: "shut down"`).
- **3D view**: generic tripod + tilt head drawn as solid geometry; the Sun,
  Moon, planets and the other targets of the running plan are marked on the
  dome (green = done, purple = still to come).
- **Live preview stretch** (`_stretch8`): per-channel sky subtraction, noise
  smoothing and an asinh stretch, so the star-mode preview has a neutral dark
  background instead of grey colour noise. Tested on synthetic frames only.
- Regression suite: scratchpad `t2.py` against `--demo` passes; note that Park
  now keeps the mount mode, so run it on a fresh demo instance.


## Wide-angle camera and skyline scan

### Wide camera
- The S30 runs its wide camera as a second imager process (control 4702,
  images 4804, RTSP 4555); clients talk to 4700 only and the main process
  relays. In **video modes** (scenery, Sun, Moon, planets) both cameras stream
  at once (`SecondView working`, RTSP 4554 = tele, 4555 = wide). Studio shows
  the wide camera as a picture-in-picture on the Live tab; click it to swap
  which camera is large. Endpoints: `/api/video?cam=wide`,
  `/api/video_frame?cam=wide`; state key `video_wide`.
- **Not possible on this scope:** watching the wide camera while the telescope
  camera is stacking deep-sky. The firmware only allows that through "dual"
  plans, gated by `can_dual_capture` / `can_star_mode_sel_cam`, and this S30
  reports both as `false`. (Source: zmerlynn/seestar-spec, a static analysis
  of the firmware - not tested here.)

### Skyline scan (`seestar_skyline.py`)
Measures the local horizon - trees, roofs, hills - with the wide camera:
1. parks (home = cable unwound), starts scenery mode, opens the arm;
2. measures the wide camera's scale and orientation from two 3-degree moves
   (phase correlation), so no field of view has to be assumed;
3. photographs rings of positions around the horizon, re-projects every frame
   into one azimuth/altitude panorama (0.25 deg/pixel) using the tube's real
   orientation, so it also works in EQ mode where the picture is rolled;
4. finds the sky/obstruction boundary in every azimuth column and saves
   `data/horizon.json` (altitude per degree of azimuth) + `data/skyline.jpg`.

The result is drawn on the Mount tab (panorama with the detected line, and a
band on the 3D dome) and the Plan tab warns when a target is behind it.
API: `POST /api/skyline {action:"start"|"abort"|"clear", max_alt}`,
`GET /api/horizon`, `GET /api/skyline.jpg`; state key `skyline`.

**Cable protection.** The scan never turns the base a full circle. Counting
from the parked position it sweeps at most 178 degrees one way, returns through
home, sweeps the other way and returns again. Every mount reading updates a
running total of base rotation (azimuth in alt-az mode, rotation about the
polar axis in EQ mode). The scan stops if the total passes 200 degrees, if the
mount jumps more than it could have moved between readings, or if a move ends
somewhere other than where it was sent. Moves are at most 32 degrees of base
rotation each, so the firmware has no reason to go the long way round. On
stop, error or abort it unwinds back to home before parking; if it cannot, it
leaves the scope where it is and says how far it is turned.

**Status:** verified on the simulator only (fake site with a house and a tree:
skyline recovered to ~0.3 deg median error, rotation peaked at 174 deg and
returned to 0). **Not yet run on the real scope.** Open questions there:
whether `scope_goto` is accepted in scenery mode, the real wide field of view
(retailers say ~23 deg, unverified), and how well sky/ground separation works
at night - twilight or daylight is the safe choice.


## First real skyline attempt - 2026-11-18 06:35 (FAILED, scan now locked on the real scope)

What happened (EQ mode, scope parked at home, Sun 5.5 deg below the horizon):
- `iscope_start_view {mode:"scenery"}` worked; the wide RTSP stream (4555) came up; the arm opened
  to alt 2.6 / az 86.5.
- The first `scope_goto` (calibration target alt 12 / az 75 - about 15 degrees away on the sky) was
  ACCEPTED in scenery mode, but the firmware drove the base (RA axis) almost a full turn the other
  way: the pointing went north below the horizon, round by the west, over the top and back to the
  east - about 355 degrees of base rotation in ~60 s.
- The cable guard saw it and tripped at 208 degrees, but raising the alarm does not stop a goto
  that is already running. The follow-up `scope_goto` to unwind was refused with 203
  "equipment is moving". `iscope_stop_view {stage:"AutoGoto"}` and `scope_speed_move speed 0` did
  not visibly stop it either; the move ran to its target.
- The scope was then parked with `scope_park {equ_mode:true}`; ScopeHome took ~66 s (a normal park
  takes ~25 s), consistent with the base turning back the way it came. Cable state could not be
  verified remotely. No pictures were taken.

Lessons / facts:
- The firmware routes gotos within its own base travel range; home appears to sit at one end of
  that range, so a target slightly "past" home is reached by going nearly all the way round.
  Normal GoTos can therefore already turn the base by up to about a full turn.
- `scope_get_axle_coord` works on port 4700 and returns the two real axle angles; parked it reads
  `[-90.0, 0.0]` (arm elevation, base angle). THIS is what cable tracking must use, not an angle
  inferred from the pointing.
- `scope_is_moving` returns "none" / the move type; `can_goto` returns a boolean.
- Stopping: firmware notes say `scope_abort_slew` plus `scope_move ["none"]`; untested here.

Rework needed before the scan may run on the real scope again:
1. drive the base with `scope_speed_move` in a chosen direction (never `scope_goto`), closed-loop
   on `scope_get_axle_coord`, so the direction and amount of rotation are ours to decide;
2. a stop that is verified to halt motion;
3. learn the real travel range and speed-move axis mapping with small supervised moves first.
Until then `/api/skyline` start/arm is refused unless Studio runs in demo mode.
