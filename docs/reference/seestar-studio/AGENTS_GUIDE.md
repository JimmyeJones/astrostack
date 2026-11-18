# Seestar Studio - reference bundle for agents

A local, pure-Python web app that monitors and controls a **ZWO Seestar S30**
smart telescope from a PC browser, replacing the official phone app for
everything functional. Built and verified against a real S30 on **firmware
9.75** in November 2026. Read this file first; `DOCUMENTATION.md` has the full
detail and `README.md` is the end-user guide.

## What is in the bundle

| Path | What it is |
|---|---|
| `seestar_studio.py` | Backend: scope client (JSON-RPC over TCP), state, housekeeping, video hubs, HTTP API, action -> command table (`build_action`) |
| `seestar_studio_ui.py` | The whole single-page UI as one Python string (`STUDIO_HTML`): Live, Camera, Targets, Plan, Focus, Mount, Albums, Stats, Console, Settings |
| `seestar_sim.py` | Simulated scope (control port, image port, HTTP images, MJPEG video, wide camera, fake skyline). Powers `--demo` |
| `seestar_skyline.py` | Skyline (local horizon) scan: astronomy helpers, panorama stitching, horizon detection, cable guard, Sun guard |
| `seestar_monitor.py` | Older read-only dashboard (never sends a control command) |
| `seestar_model.json` + `model_src/` | 3D model used by the Mount tab (not copied into AstroStack's reference; CC BY-SA) |
| `dev/tests/` | Test scripts: simulator suites and the scripts used on the real scope |
| `DOCUMENTATION.md`, `README.md` | Full reference and user guide |
| `LICENSES.md` | Third-party attribution (the 3D model is CC BY-SA) |

## Run it

```
pip install cryptography opencv-python numpy pillow
python seestar_studio.py --demo --web 5599        # simulated scope, safe to click anything
python seestar_studio.py --host <scope-ip> --web 5556 --bind 127.0.0.1
```

- `--demo` needs no telescope and no key.
- A real scope on firmware 7.18+ needs the interop RSA key as `seestar.pem` next to the scripts
  (see "Left out" below). Without it Studio only sees broadcast events.
- Python 3.12, standard library HTTP server, no framework, no build step.
- Run only ONE Studio/Monitor per scope; the scope caps client connections.

## Protocol facts that were verified on the real scope

- JSON-RPC, `\r\n`-delimited, TCP **4700**. Events are broadcast to every client.
- Firmware 7.18+ gate: `get_verify_str` -> sign the string (RSA, PKCS#1 v1.5, SHA-1) ->
  `verify_client {sign, data}` -> `pi_is_verified`.
- HTTP file server on port 80 (stacked images: path from `get_albums`, full-res = thumbnail path
  without `_thn`). Binary image port **4800** (80-byte big-endian header, magic `0x03C3`;
  `begin_streaming` / `stop_streaming`, heartbeat `test_connection`). RTSP `rtsp://ip:4554/stream`
  in video modes; the wide camera is `4555`.
- UDP discovery on 4720 did NOT answer on the test network; Studio falls back to a TCP sweep of
  the /24 for port 4700.
- An idle scope answers `get_view_state` with `{}`; a stopped view lingers as state `cancel` with
  its old stage. Treat both as idle.
- `scope_park {equ_mode}` SETS the mount mode - always pass the current mode.
- `get_setting` contains the scope's hotspot password; do not forward it to a browser.
- `play_sound` numbers 1-15 exist (not 3).
- `scope_get_axle_coord` returns the two real axle angles `[arm elevation, base angle]`
  (parked = `[-90, 0]`). `scope_is_moving` returns the move type or `"none"`.
- The S30 tested reports `can_dual_capture: false`: the wide camera cannot be viewed while the
  telescope camera is stacking. Both cameras stream together only in scenery/Sun/Moon/planet modes.

The full command table with exact parameter shapes is in `DOCUMENTATION.md` and in
`build_action()` / `make_plan()` in `seestar_studio.py`.

## Test status - be precise about this when you reuse the code

| Area | Status |
|---|---|
| Monitoring (state, images, albums, history, alerts, autosave) | Verified on the real scope over a full night |
| Camera/focus/filter/heater/location/clock controls | Verified on the real scope (value read back) |
| Open arm, hold-to-slew, tracking, GoTo + stack, stop/resume, plate solve, sync, polar align start/stop, dark start/stop, park, EQ mode | Verified on the real scope |
| Plan mode (`set_view_plan`, incl. mosaic) | Verified: a 4-target plan ran unattended to completion |
| Live preview (port 4800), scenery video (RTSP), snapshot, record | Verified on the real scope |
| 3D pointing view | Pose checked against the scope's tilt sensor; tripod/head are generic |
| Wide-camera picture-in-picture | Simulator only (the wide RTSP stream itself was seen live once) |
| Live-preview stretch (`_stretch8`) | Synthetic frames only |
| Skyline scan | **Simulator only. Failed on the real scope and is locked there** - see below |
| Delete image, clear plan, reboot, shutdown, Sun/Moon/planet modes | Not exercised on the real scope |

## The skyline-scan incident (read before writing any motion code for this mount)

On 2026-11-18 the first real run sent one `scope_goto` to a point about 15 degrees away. The
firmware accepted it and turned the base almost a full circle the other way (about 355 degrees).
Findings:

1. The firmware chooses its own route for every GoTo inside its own base travel range, and home
   appears to sit at one end of that range. Never assume the short way.
2. A guard that only *detects* excess rotation is not protection: a running goto could not be
   stopped (`iscope_stop_view {stage:"AutoGoto"}` and `scope_speed_move` speed 0 had no visible
   effect; a new `scope_goto` is refused with 203 "equipment is moving").
3. Rotation was being inferred from the pointing direction. The real base angle is available from
   `scope_get_axle_coord` and should be used instead.
4. The simulator moved instantly and by the short route, so it validated the algorithm but not the
   mount's behaviour. A simulator pass is not evidence about firmware routing.

Planned rework (not done): drive the base with `scope_speed_move` in a chosen direction,
closed-loop on `scope_get_axle_coord`; verify a stop command first (`scope_abort_slew` plus
`scope_move ["none"]` per third-party firmware notes, untested); learn the travel range with small
supervised moves. Until then `/api/skyline` start/arm returns 409 unless Studio runs with `--demo`.

Other safety rules the owner set: do not interrupt a running observation; no sweeping the
telescope with the Sun up (the scan starts only with the Sun more than 3 degrees below the
horizon and stops itself at 1.5 below); protect the power cable from winding.

## How the code is organised (for editing)

- `seestar_studio.py`: `State` (one lock, `snapshot()` builds `/api/state` - anything called inside
  it must not take `STATE.lock` again), `ScopeClient` (reader thread + `call()` for request/reply),
  `Housekeeper` (history, last-known state, autosave), `VideoHub` (one per camera), `ScanRig` /
  `SkyArm` (skyline glue), `Handler` (HTTP). POST endpoints require same-origin JSON.
- `seestar_studio_ui.py` is a raw Python string. Avoid triple double-quotes in the JavaScript.
  After editing, restart Studio; the UI is served from memory.
- The simulator returns error 109 for wrong parameter shapes, so `dev/tests/t2.py` catches
  regressions in `build_action()`. Run it against a FRESH `--demo` instance on port 5599.
- Windows note: stopping the launching shell does not always kill python; check for a listener on
  the port before starting another copy. The server refuses to share its port.

## Sources used for the protocol

- seestarpy - https://github.com/astronomyk/seestarpy (docs: https://seestarpy.readthedocs.io)
- seestar_alp - https://github.com/smart-underworld/seestar_alp
- seestar-spec (static analysis of the firmware) - https://github.com/zmerlynn/seestar-spec

## Left out of this bundle on purpose

- `seestar.pem` - the interop private key (a single PKCS#8 PEM block, the same for every device).
  Never commit it. In AstroStack the owner uploads it through the web UI (see the backlog entry).
- The owner's data: captured images, history, last-known state, measured location, serial number,
  and network addresses. Addresses in the code and docs were replaced with examples
  (`192.168.1.100` for the scope).
