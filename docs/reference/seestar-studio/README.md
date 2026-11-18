# Seestar on your PC

Local, lightweight web apps for your **ZWO Seestar** telescope — no Android
emulator needed. Two programs are included:

| App | Launch | What it does |
|-----|--------|--------------|
| **Seestar Studio** (recommended) | `Start Seestar Studio.bat` | Full **control + monitor**: live image, imaging, GoTo, focus, mount, albums, a raw-RPC console, and settings — a complete replacement for the app. |
| **Seestar Monitor** | `Start Seestar Monitor.bat` | **Read-only** watch-only dashboard. Can never disturb a running plan. |

Both serve on **http://127.0.0.1:5556** and on your Tailscale tailnet. Run only
**one** at a time (they share the port; a second copy now refuses to start).

### Studio highlights

- **Live** view with zoomable full-res viewer, **Save to PC**, and a Power card
  with a battery time-remaining estimate.
- **Auto-save**: every 10 minutes while stacking, the full-resolution stack is
  copied to `captures\<target>\` on this PC — so the result survives even if the
  scope runs out of battery mid-session. (`--autosave 0` turns it off.)
- **Alerts** (banner + optional beep / desktop notification — click the bell):
  scope offline, battery 20 / 10 / 5 %, stalled stacking, storage nearly full.
- **Last-known data**: if the scope drops, Studio keeps showing the last image
  and readings, says when it was last seen, and reconnects by itself.
- **Target planner**: 77 deep-sky objects with live altitude, peak time, search,
  type filter; GoTo accepts decimal or `hh:mm:ss` coordinates.
- **Stats**: battery, temperature and frames-stacked charts (1 h / 6 h / 24 h).
- **Mount**: hold-to-slew pad (also arrow keys); **Console**: raw RPC + history.
- Phone layout with bottom tab bar; "Add to Home screen" gives an app icon.

- **Live video** for Sun / Moon / planets / scenery, plus snapshot and on-scope
  video recording.
- **Plan** tab: schedule a night of targets and send it to the scope - it then
  runs on the scope by itself, exactly like the app's Plan mode.
- **Targets**: Sun, Moon and planets, a tap-to-pick sky map, favourites,
  framing / mosaic, slew-only.
- **Camera**: filter wheel, dithering, sub-frame saving, DBE, 4K drizzle,
  live-view exposure. **Mount**: tracking, EQ mode, polar alignment, plate
  solve, sync, level bubble. **Settings**: location, clock sync, sound.
- **Mount** tab: live 3D view of the scope on its tripod showing how it is
  tilted and where it points, with the Sun, Moon, planets and plan targets on
  the sky dome (scope model by WistowTbone, CC BY-SA - see DOCUMENTATION.md).
- **Plan** tab: copy the plan on the scope back into the builder, mosaic per
  target, and the reason a target stopped.
- Not included on purpose: firmware updates, Wi-Fi setup, storage formatting.

### Try it safely: demo mode

Double-click **`Try Seestar Studio (demo).bat`** (or
`python seestar_studio.py --demo --web 5599`). It runs against a built-in
**simulated telescope** (`seestar_sim.py`), so you can click every control and
see what it does without touching the real scope.

The rest of this file documents the Monitor; see `DOCUMENTATION.md` for the full
Studio reference.

---

## Seestar Monitor

A lightweight, local web dashboard for watching (and reading the full status of)
your **ZWO Seestar** telescope from your PC's browser — without running the heavy
Android app in an emulator.

It runs as a tiny Python program in a terminal and serves a dashboard at
**http://127.0.0.1:5556**.

![what it shows](what-it-shows)

## What it shows

- **Live stacked image**, refreshed as the stack grows (click for full resolution)
- **Target** name and coordinates (RA / Dec)
- **Frames stacked** / dropped, and total **integration time**
- **Exposure** state, sub-length and gain
- **Battery** %, charging status; **sensor temperature**; **free disk**
- Device info (model, firmware, serial) and detected **star annotations**
- A live **event log** of the observation

## Quick start

1. Make sure Python 3 is installed (it is, on this PC).
2. Double-click **`Start Seestar Monitor.bat`**
   — or run in a terminal:
   ```
   python seestar_monitor.py --host 192.168.1.100 --bind tailscale
   ```
3. On this PC your browser opens **http://127.0.0.1:5556**.

If the Seestar's IP ever changes (DHCP), the monitor automatically re-discovers
it on the network, so you normally never need to change anything. You can still
pass a specific address with `--host <ip>`.

## View it on your phone (Tailscale)

The launcher starts the dashboard on your **tailnet** as well as this PC, so any
device signed in to your Tailscale account can open it:

- **http://100.64.0.10:5556**  (this PC's Tailscale IP)
- or, if MagicDNS is on:
  **http://your-pc.your-tailnet.ts.net:5556**

Both your phone and this PC must be signed in to Tailscale and connected. Nothing
else on your home Wi-Fi can see it — only your tailnet — and no Windows Firewall
change is needed (Tailscale already permits it).

Tip: add the phone URL to your home screen for one-tap access while imaging.

To serve on this PC only (no tailnet), use `--bind 127.0.0.1`. To serve on every
network including plain Wi-Fi, use `--bind 0.0.0.0` (less private).

## It is read-only and safe

The monitor **only reads** from the scope. It never sends a command that could
move, stop, or reconfigure it, so **a running plan is never disturbed**. You can
leave it open all night while an observation runs.

It is a *monitor*, not a controller — by design, so it can never interrupt your
imaging. (Control could be added later, but that is what carries risk to a plan.)

## Modes

The Seestar firmware (7.18+) locks most data behind an RSA handshake.

- **Full mode** (this is set up for you): the file **`seestar.pem`** sits next to
  the script and holds the interop key, so the dashboard shows everything above,
  including the live image.
- **Monitor mode** (if `seestar.pem` is missing): the dashboard still shows the
  live broadcast stream — stacking progress, exposure state and temperature —
  which is all you need to confirm a plan is running. Target, battery, disk and
  the live image are not available without the key.

Full mode also needs the `cryptography` Python package (already installed here:
`pip install cryptography` if you ever move this to another PC).

## Options

| Option | Default | Meaning |
|--------|---------|---------|
| `--host` | `192.168.1.100` | Seestar IP on your LAN |
| `--port` | `4700` | Scope control port |
| `--web`  | `5556` | Local web UI port (open in your browser) |
| `--key`  | `./seestar.pem` | Path to the interop key |

## How it works (brief)

The Seestar speaks newline-delimited JSON-RPC on TCP port **4700** and broadcasts
status events to any connected client. Device state, view state and the album
list are fetched with read-only calls (`get_device_state`, `get_view_state`,
`get_disk_volume`, `get_albums`). The live stacked image is pulled from the
scope's own HTTP file server on port **80** using the path from `get_albums`. The
dashboard polls the local server (`/api/state`, `/api/image`) a couple of times a
second.

## Troubleshooting

- **"scope offline" / keeps reconnecting**: make sure nothing else is hammering
  the scope. The official app holds a connection too; one app plus this monitor
  is fine, but several copies at once can exceed the scope's connection limit.
  (Only run one copy of the monitor.)
- **Port 5556 already in use**: another copy is still running. Close it, or start
  with `--web 5557` and open that port instead.
- **No live image / fields blank**: you're in monitor mode (no `seestar.pem`), or
  the scope is idle (not currently viewing/stacking).

## Files in this folder

- `seestar_studio.py` + `seestar_studio_ui.py` — the full control app (**Studio**)
- `Start Seestar Studio.bat` — launcher for Studio
- `Try Seestar Studio (demo).bat` + `seestar_sim.py` — demo mode / simulated scope
- `captures\` — full-res stacks auto-saved by Studio; `data\` — history, last-known state
- `seestar_monitor.py` — the read-only monitor
- `Start Seestar Monitor.bat` — launcher for the monitor
- `seestar.pem` — the interop key (enables full control / full mode)
- `README.md` — this file
- `DOCUMENTATION.md` — full technical reference (protocol, Studio, key, network)
