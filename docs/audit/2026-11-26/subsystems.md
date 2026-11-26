# Audit — recently built subsystems (AstroStack v0.511.5, `main`)

Scope: Seestar integration, library diagnostics, Moon/Sun video stacker, update button, planning.
Repo was read-only; every experiment script is in
`/tmp/claude-0/-home-user-astrostack/898c11c2-2328-5559-a5d0-f0f505498eb1/scratchpad/audit/subsystems/`
(`t_key.py`, `t_sim.py`, `t_off2.py`, `t_diag.py`, `t_video.py`, `t_grid2.py`, `t_plan.py`). Bulky data
(videos, synthetic library, stacks) was deleted after use; no process was left running.

Confidence words: **CONFIRMED** = reproduced by running the code; **READ** = traced in the source;
**SUSPECTED** = inferred. Status: every finding was grepped in `docs/IMPROVEMENTS.md` / `docs/SHIPPED.md`;
all ranked defects below are **NEW** unless marked.

---

## 1. Seestar telescope integration

**Verdict.** The protocol work is right: handshake, signature, wire shapes and every control match the owner's
reference, and it all runs against his simulator. But it will not work for him out of the box (default discovery
cannot find his scope from a Docker bridge), and after the first time the scope is switched off the telemetry
thread dies and never comes back until the container restarts. So tomorrow: he pins the IP, it works for one
session, then the page shows a frozen picture of last night.

### What I ran

- `t_key.py` — throwaway keys from `openssl genrsa` (PKCS#8 2048-bit, PKCS#1 1024-bit). `keyfile.parse_private_key`
  accepts both, plus CRLF line endings, a UTF-8 BOM and trailing text; an `ENCRYPTED PRIVATE KEY` is refused in
  plain words. `sign_pkcs1v15_sha1` output **verifies with `openssl dgst -sha1 -verify` and is byte-identical to
  `openssl dgst -sha1 -sign`** for three challenges. Stored file mode 0600, folder 0700. `repr` shows only the bit size.
- `t_sim.py` — the reference `seestar_sim.py` on 127.0.0.1:4700, driven by AstroStack's `SeestarClient` and
  `SeestarManager`:
  - no key → `key_needed`; unauthenticated `get_device_state` → error 207 handled; with key → `verified`
    (the sim replies `{"key_envelope": …}` as firmware 9.75 does; AstroStack ignores the envelope, as the reference does).
  - wire log, exactly as `build_action()`: `iscope_start_view {mode:"star", target_ra_dec:[h,deg], target_name, lp_filter:false}`,
    `iscope_stop_view {stage:"Stack"}`, `iscope_start_stack {restart:false}`, `start_auto_focuse`,
    `move_focuser {step:<absolute>, ret_step:true}`, `start_solve`, `scope_park {equ_mode:<read fresh>}`, bare `iscope_stop_view`.
    The simulator rejects wrong shapes with code 109; none was rejected.
  - Park with the sim in EQ mode: manager read `get_device_state {keys:["mount"]}` then sent `scope_park {equ_mode:true}` — mode preserved.
  - Manager end-to-end: telemetry, storage from `get_disk_volume`, idle/`cancel` view read as idle, `get_albums` →
    thumbnail 11 KB and full image 186 KB fetched from the scope's HTTP server (`_thn` dropped for full size).
    `raw` telemetry carried none of `setting` / `station` / `location_lon_lat` / `sn`. One TCP client per scope.
- `t_off2.py` — the simulator as a subprocess, killed to imitate the scope being switched off.

Line-by-line against the reference: framing `\r\n` out and newline-split in — same. `get_verify_str` / `pi_is_verified`
sent with `params:"verify"` — same. Challenge signed as its UTF-8 bytes, signature base64 — same. 103 → no gate,
non-zero on `verify_client` → rejected — same. Focuser range 1200–2600 and absolute moves — same.
Safety: AstroStack exposes no `scope_goto`, no `scope_speed_move`, no skyline scan; the only motion is the app-style
GoTo (confirm dialog) and Park (confirm dialog). The key is never returned by the API, never logged, not in the
tar backup of `deploy.sh` (that archives only `*.sqlite*` and `config.json`), not on the read-only token's allowlist,
not in `/api/diagnostics`. A global same-origin guard (`webapp/main.py:310-352`) covers the bodiless control POSTs.

### Defects, ranked

1. **The telemetry thread dies for good the first time the scope goes offline.** — **critical** (for this feature) — **CONFIRMED**.
   `webapp/seestar/client.py:137` (`socket.create_connection` raises `OSError`, not `SeestarError`);
   `webapp/seestar/manager.py:409-416` (`_poll_reconnect` catches only `SeestarError`); `_poll_loop` (`manager.py:449-483`) has no outer guard.
   Evidence (`t_off2.py`): after killing the simulator, `Exception in thread seestar-poll … ConnectionRefusedError`,
   then `poll thread alive: False | scan thread alive: True`. A powered-off scope gives a timeout or "no route", also `OSError`.
   What he sees: the scope's battery dies or he packs it away; next night the scan thread reconnects and the card says
   "connected / Key accepted", but battery, target, frame count and picture are last night's and never move. Only a container restart fixes it.
   The same uncaught `OSError` makes `POST /api/seestar/{ip}/connect` and every control return a 500 instead of a readable 502, and makes the scan loop
   abandon the rest of its list ("seestar scan failed").
   Fix (S): in `SeestarClient.connect` wrap the socket open and raise `SeestarError`; put a `try/except Exception` around each device in `_poll_loop`.
   Regression test: a real listener in a subprocess, killed. The existing tests fake the failure with `SeestarError`, which is why this passed.

2. **Default discovery can never find his scope.** — **high** — **READ** (plus the reference's own measured fact).
   `webapp/seestar/discovery.py:118-141`: with `seestar_scan_subnet` blank the scan is UDP 4720 only. The reference records
   that UDP 4720 got no reply on his network, and AstroStack runs in a bridged Docker container (`docker/docker-compose.yml:26`, `ports:` only),
   where a broadcast never leaves the bridge and `_primary_ipv4()` is a 172.x address. The settings hint
   (`frontend/src/routes/Settings.tsx:80`, "Blank = auto-detect from the container's network") says the opposite of what happens.
   What he sees: "No Seestars found yet", however often he presses Scan network. It works only if he types the scope's IP
   (which changes with DHCP) or his LAN's CIDR.
   Fix (S–M): when UDP finds nothing and nothing is pinned, say so in plain words on the empty state and ask for the scope's address or the
   network range in one field; identify a Seestar on a sweep the way the reference does (`get_verify_str` answered with `"jsonrpc"`), so the
   "unrelated box with 4700 open" worry that disabled the sweep goes away; on a lost pinned scope, re-sweep its /24 and follow it to its new address.

3. **`{ip}` is not validated anywhere.** — **medium** — **CONFIRMED**. `webapp/routers/seestar.py:103-111` and every `/{ip}/…` route;
   `manager._ensure_client`. Evidence: `m.connect("not a host; rm -rf")` raised `gaierror` and left that string in `_clients`
   (the poll loop then retries it forever — and, by defect 1, dies on it). Any host name or address is dialled on TCP 4700 and sent a UDP datagram on 4720
   by the NAS (a small request-forgery surface, auth being off by default). Fix (S): accept only a literal private IPv4 address
   (`ipaddress.ip_address(...).is_private`), and only create a client for an address that is pinned or was discovered.

4. **Without the key, the app keeps asking for a challenge it cannot answer.** — **medium** — **READ**. `client.py:383-399`, `manager.py:459-466`.
   The reference deliberately sends nothing on the main connection without a key, "because the scope drops a client that requests verification but
   never completes it", and probes the gate on a separate short-lived socket. AstroStack sends `get_verify_str` on its one connection and then polls
   four gated methods every 5 s. On the real scope that is most likely a drop/reconnect cycle every few seconds (each successful reconnect clears the
   backoff), competing for the scope's limited client slots with his phone app and his own Seestar Studio. Fix (S): probe the gate on a throwaway socket;
   with no key, hold the connection silently and show the broadcast events (`Stack`, `PiStatus`, `Exposure`), which need no key — AstroStack currently
   discards them (`client.py:230`).

5. **Controls do not look at what the scope is doing.** — **medium** — **READ**. `routers/seestar.py:176-232`, `Seestar.tsx:289-305`.
   The owner's stated rule is "do not interrupt a running observation". "Stop" (ends the whole session) and "Pause stacking" have no confirmation, and
   GoTo/Park confirm with the same sentence whether the scope is idle or two hours into a stack or a running plan. `POST /{ip}/start` sends
   `iscope_start_view {mode:"star"}` with no target; it has no button but is live. Fix (S): when telemetry says a stack or plan is running, name it in the
   confirmation ("M 31 has 412 frames stacked — stop it?"); confirm Stop; drop or hide `/start`.

6. Low: every scan (300 s) opens and closes an extra TCP connection to a scope that is already connected (`discovery.py:135-139`); request ids start
   at 1 (the reference starts at 1000); `get_device_state` is always sent with a `keys` list whereas the verified reference sends none — fine on the
   simulator, unverified on firmware 9.75 (**SUSPECTED**); log lines carry the scope's LAN address and are served on `/api/logs`, which the public-issue-filing
   observer reads.

**Biggest meaningful improvement.** Fix 1 and 2 together (one small change each) and add an "is this what the real scope does?" smoke test that runs the
bundled simulator in a subprocess through connect → handshake → telemetry → power-off → power-on. That one test would have caught defect 1.

---

## 2. Library diagnostics

**Verdict.** The mechanism works: at boot every pending diagnostic is queued as one job, runs, and its numbers-only result is served. It costs the
single worker a few minutes, not hours. But there is no way for the owner to see or copy a result in the app, so at least five backlog entries
(including the top ⭐ one) wait on a courier — the NAS observer — that has delivered nothing; and the headline diagnostic cannot tell a blotch from
ordinary lens vignetting.

### What I ran

`t_diag.py`: a synthetic library of 6 targets × 12 full-size S30 raws (1080×1920, RGGB), scanned in place, then the real app booted through
`TestClient(create_app())`.

- Boot → `/api/diagnostics` listed 5 pending; a `diagnostics` job ran; all five stored `status: done`.
- Timings on full-size subs, one thread: `sensor_pattern_by_temperature` 79.6 s for 140 subs (**0.57 s a sub**), `sky_falloff` 2.6 s for 24 (0.11 s a sub),
  the other three under 0.1 s (record or header only).
- Cost on a 100-target / 100k-sub library, by counting reads: sensor pattern ≤ 560 raw loads + debayer (≈ 5 min), sky falloff ≤ 300 raw loads (≈ 0.5 min),
  filter card ≤ 800 header reads, plus each diagnostic opening every target's database once and reading 3–6 columns of every row. **Roughly 6–10 minutes
  holding the single job worker**, once per new diagnostic version; imports and stacks queue behind it. It is cancellable between files. Memory is small
  (four columns per sub). That is acceptable.
- Privacy: results held only counts, ratios, catalogue families and anonymous lists; a failure is recorded by exception class only;
  `check_result_is_safe` refuses path-like and location-like strings. I found no leak.

### Defects, ranked

1. **Results have no way out except the observer.** — **high** (it is a cause of the stall he feels) — **CONFIRMED** by search.
   The frontend never calls `/api/diagnostics` (only `Jobs.tsx` mentions the job kind). Backlog entries held on a result: the ⭐ colour-blotch entry
   (`docs/IMPROVEMENTS.md:96-130`), the dark-ring entry (:159-184), the un-located mosaic panel entry (:201-208), the Dashboard overcount lead (:252), the LP-filter idea (:2494).
   Fix — the simplest robust design (S–M):
   - one section inside the existing Settings → Maintenance group (no new top-level card): "Questions the app answered about your library", one line per result
     with its question, date and status, and what is still waiting and why (today a diagnostic whose `ready` check fails is listed as pending with no reason);
   - two buttons: **Copy all results** (clipboard, as one Markdown block ready to paste into a GitHub issue — the results are already privacy-checked) and
     **Download** (`GET /api/diagnostics/export`, one JSON file);
   - a **Run again** button per diagnostic, so a result does not need an update and a reboot;
   - a one-line dashboard notice the first time new results exist ("3 new measurements are ready — copy them to the developers"), folded into the existing notice board.
   The observer keeps working unchanged; the loop simply no longer depends on it.

2. **`sensor_pattern_by_temperature` v2 reads plain colour vignetting as "a colour pattern fixed to the camera".** — **medium-high** — **CONFIRMED**.
   `seestack/diag/sensor_pattern.py:72-76, 205-216`. My library had smooth, colour-dependent vignetting (R −14 %, G −10 %, B −7 % at the corner), no blotches,
   different sky levels per sub. Result: `ratio 213.5, repeat_r 1.0` overall and `204 / 1.0` in the one populated temperature range. Each map has only its mean
   removed, so any smooth camera-fixed colour gradient (vignetting, amp glow, the LP filter's angle dependence) scores as the pattern. The ⭐ entry's gate
   ("apply only when repeat r ≥ 0.5 and ratio ≥ 2") is therefore met by every real OSC camera, and the temperature comparison will mostly compare vignetting
   with itself (r ≈ 1 between ranges → "one pattern that changes strength"), which answers nothing about "only when it is cold".
   Fix (S, bump to v3): fit and remove a low-order radial/quadratic surface from each chroma map before measuring, and report the smooth part and the
   residual (blotch-scale) part as separate numbers.

3. Low: `sky_falloff` and `sensor_pattern` both read whole raws to answer related questions (~860 loads; could share a sample). A job interrupted by a
   redeploy re-runs from the start at the next boot (correct, just slow). Results reach developers only after `stable` catches up (≥ 3 days) and the owner updates.

**Biggest meaningful improvement.** The in-app results section with Copy and Run again (defect 1). It turns a multi-week wait into one click.

---

## 3. Moon/Sun video stacker

**Verdict.** For the Sun (and a near-full Moon) the rework is solid: colour right, sharpest frames chosen, alignment to a few hundredths of a pixel, drizzle
measurably sharper, memory flat. Two real problems remain: the drizzle prints a fine coloured mesh whenever frame brightness flickers, and a
partial-phase Moon with maria is still misaligned by tens of pixels. So tomorrow: Sun yes; first-quarter or gibbous Moon, probably soft or doubled.

### What I ran

`t_video.py`: lossless pal8 raw `GBRG` AVIs built like `tests/videosynth.py` (480×360, disk radius 110 px), with known truth: ±25 px drift plus 0.8 px
jitter, per-frame seeing blur σ 0.5–4 px, ±8 % brightness flicker, fixed-pattern noise, read noise.

| Check | Sun, 700 frames | Near-full Moon (maria + rays), 240 | Partial-phase Moon, 240 |
|---|---|---|---|
| Kept frames vs truly sharpest 30 % | 100 % overlap, rank corr 1.00 | 99 % | 97 % |
| Reference frame | the single sharpest (rank 1/700) | rank 1 | rank 1 |
| Colour R:G:B (truth) | 1 : 0.729 : 0.399 (1 : 0.72 : 0.38) | correct | correct |
| Per-frame alignment error | median 0.04 px, max 0.09 | median 0.05 px, max 0.12 | **median 24.9 px** |
| Equivalent blur of stack (achievable ≈ 0.7–1.1 px) | 1.1 px plain, **0.8 px drizzled** | 1.1 px | **4.0 px** |
| Detail correlation with truth | 0.81 plain → 0.93 drizzled | — | — |

Time 52–64 ms per decoded frame at 0.17 MP for both passes (38 s for 700 frames); extrapolated to 1080p that is about 0.6 s a frame, ~15 min for the
1,500-frame cap (**SUSPECTED**, not run at full size). Peak RSS was flat (425 MB including my own test arrays) with and without drizzle.

### Defects, ranked

1. **The drizzled still carries a coloured 3-pixel mesh when the capture's brightness flickers.** — **high** — **CONFIRMED**. `seestack/video/drizzle.py:269-297`
   (frames are deposited un-normalised), `lucky.py:639-656`.
   With ±8 % frame-to-frame brightness variation the drizzled Sun shows a 3×3 output-pixel lattice of **2.1–2.8 % peak-to-peak per colour channel**
   (plain stack: 0.04 %), rising to **4.2–5.5 % at "Medium" sharpen** — against real fine detail of 5.7 % rms. With brightness held constant the lattice is
   0.02 %. Cause: at ×1.5 each output-pixel phase is filled by a different subset of frames (those whose sub-pixel shift lands there), so any brightness
   difference between frames becomes a fixed pattern. Thin cloud and auto-exposure make real captures flicker (the code's own notes record his solar AVI's
   level varying strongly). This is the October "covered in a fine mesh" complaint in a subtler form, on by default on the Moon/Sun page.
   Fix (S): scale each kept frame to the reference's disk mean (per channel) before depositing — the plain accumulator should get the same so both agree.
   Regression test: the existing drizzle fixture with a brightness ramp; assert the 3×3 phase-mean spread.

2. **A Moon that is not close to full is aligned on an unstable blob.** — **high** for lunar captures — **CONFIRMED on synthetic data; SUSPECTED on his**.
   `lucky.py:231-262` (`_find_disk`: threshold halfway between sky and the 99.5th percentile, then the centroid of the largest connected region),
   `lucky.py:433-452` (refinement may move the centroid by at most 2 px, otherwise the centroid wins).
   On a gibbous Moon with maria at about half the highland brightness, bright ray craters and a terminator, the mask is the bright highlands only, and which
   piece is "largest" differs between the sharp reference and the softer frames: 70 of 72 kept frames had their refinement rejected and sat a constant
   ~25 px from the reference, with 3–4 px of scatter among themselves; `n_align_failed` was 0 and no warning was raised. The same scene at near-full
   phase aligned to 0.05 px. No test covers a phase or a mare-textured Moon (`tests/test_video_*` use a uniform disk).
   What he would see: a soft lunar picture with a ghost of the limb, and a report that every frame lined up.
   Fix (M): find the disk from a low threshold (sky + a few sigma) so the mask is the whole lit shape; take the coarse shift from a cross-correlation of
   heavily down-sampled frames instead of a centroid; if the fine correlation is rejected, drop the frame and count it rather than trusting the coarse shift.

3. **The plain (non-drizzle) path shifts frames with bilinear interpolation.** — **medium** — **CONFIRMED** (plain stack blur 1.1 px vs 0.8 px drizzled, and vs
   0.73 px median seeing of the kept frames). `lucky.py:455-470` (`order=1`). Any capture that keeps fewer than 200 frames (under ~670 graded at 30 %) never
   drizzles and takes this softening. Fix (S): cubic shift (`order=3`, NaN-aware edges) or Fourier shift.

4. Low: the 99.5th-percentile threshold in `_find_disk` is pulled around by a few very bright pixels (ray craters, a sunspot-free limb); speed at 1080p.

### Still weak next to AutoStakkert / RegiStax — what would visibly improve his pictures

- **Local (multi-point) alignment.** Seeing warps the disk differently across its face; one global shift per frame leaves the limb or the centre soft.
  A coarse grid of alignment tiles (even 6×6) with smoothly blended per-tile shifts is the single largest gain for the Moon. Size L.
- **Local quality.** Rank frames per tile, not per frame: a frame sharp at one limb and soft at the other currently counts once. Comes almost free with tiles.
- **Wavelet-style multi-scale sharpening** instead of the single 1.1 px unsharp mask (`detail.py`): two or three scales with a noise floor per scale give the
  crisp crater-rim look without the limb halo. One "how much" slider can still drive it. Size M.
- **Limb-darkening / flat disk option for the Sun**, and a neutral white balance from the disk itself (the stack keeps the raw filter colour).
- Brightness normalisation (defect 1) is also what AutoStakkert does before stacking.

---

## 4. Update button

**Verdict.** The request/status protocol is careful and I could not break it by reading: requests are data, claimed atomically, expire after an hour,
a lock prevents overlap, a heartbeat separates "not installed", "cron stopped" and "working". The one real gap is the failure that matters most: if the
build fails after the app has been stopped, the app stays down and the only place the failure is explained is the web page that is now unreachable.

Checked by reading `webapp/routers/updates.py`, `scripts/update_agent.py`, `scripts/deploy.sh`, `frontend/src/components/UpdatesCard.tsx` (not run: it
needs root, Docker and cron).

- Helper not installed → `helper: "missing"` → the card shows the one-time setup steps; every POST returns 409 with a plain sentence. Good.
- Cron stopped → stale heartbeat → the card says when the helper last checked in; a stuck `updating` state is shown as idle. Good.
- Double clicks / two tabs → `_require_ready` refuses while a request is pending or a job is running. Good.
- `apply` names the version shown, so it cannot install something the owner did not see. Good.

### Defects

1. **A failed build leaves the app stopped, with no automatic recovery and no visible message.** — **high** — **READ**.
   `scripts/deploy.sh:74-75` stops the app before backing up and building; a failing `docker compose up -d --build` (network down during the image build,
   disk full, a broken commit) exits through the `ERR` trap, which only prints "sudo docker start astrostack". `update_agent.py:349-359` then records
   "The update did not finish … see the log below, or roll back" in `status.json` — which only the stopped app could display.
   What he sees: he pressed Update, the page went away and never came back. He needs SSH, which the button exists to avoid.
   Fix (S): in `do_update`, when `deploy.sh` fails, check container health; if it is not healthy run `rollback.sh --yes` (or at least `docker start astrostack`)
   and report both outcomes, so the old version comes back up and shows the failure and its log tail.

2. Low — **READ**: a helper killed mid-deploy (NAS reboot) leaves no `last_result`; the next tick writes `idle`, so the card says nothing happened.
   Record the job id on start and report "interrupted" on the next tick. The card's 60-second wait for cron is explained in the UI.

**Biggest meaningful improvement.** Self-healing on failure (defect 1).

---

## 5. Planning features

**Verdict.** The astronomy is right; this subsystem will work for him tomorrow. (`seestack/plan.py` is the pipeline runner, not astronomy; the
astronomy is all in `seestack/nightplan.py`, on astropy with IERS downloads disabled.)

### What I ran (`t_plan.py`)

- Dark window against an independent 30-second Sun-altitude search for 10 site/date cases (40°N winter and tonight, London midsummer and the
  DST-change night, Sydney, Fiji across the date line, Hawaii, Helsinki in June, Tromsø midsummer and midwinter): every start/end within
  **+0.5 / −3.5 minutes** (the planner's 4-minute grid, always on the conservative side). 40°N 105°W on 2026-11-27: dark from 01:13 UTC = 18:13 local, as almanacs give.
- High latitudes: London in June falls back to nautical (−12°, 3.3 h) and the Tonight page labels it "nautical (short summer night)"; Helsinki falls back
  to −6° and is labelled "twilight only"; Tromsø midsummer returns no window and every caller handles `None`.
- Time zones / DST: everything is computed in UTC from the site longitude; the DST-change night is unaffected; a request made after midnight returns the
  night still in progress.
- Moon: illumination at the 2026 new / first quarter / full / last quarter instants = 0.002 / 0.500 / 0.998 / 0.500; waxing flips exactly at new and full.
  Moonrise inside the dark window 01:45 UTC vs independent 01:44 (geometric horizon, so about 4–6 minutes later than a printed almanac — fine for "~").
- Target geometry: IC 1848 from 40°N peaks at 69.5° (90 − |40 − 60.43| = 69.57°).
- First call 1.7 s (astropy warm-up), then 0.1–0.2 s.

No defect worth ranking. Minor: Moon rise/set use the geometric horizon rather than the refracted upper limb.

---

## Top findings overall

| # | Finding | Severity | Confidence | Status |
|---|---|---|---|---|
| 1 | Seestar telemetry thread dies permanently when the scope goes offline (`OSError` uncaught in `_poll_reconnect`) | critical | CONFIRMED | NEW |
| 2 | Lucky drizzle prints a coloured 3-px mesh under brightness flicker (2–3 %, ~5 % sharpened) | high | CONFIRMED | NEW |
| 3 | Partial-phase Moon misaligned ~25 px with no warning (`_find_disk` centroid) | high | CONFIRMED synthetic / SUSPECTED real | NEW |
| 4 | Default Seestar discovery (UDP only, bridged Docker) can never find his scope; settings hint is wrong | high | READ | NEW |
| 5 | Diagnostic results have no in-app view/copy/export; ≥ 5 backlog entries wait on them | high | CONFIRMED | NEW |
| 6 | Failed update build leaves the app stopped with the error shown only on the dead page | high | READ | NEW |
| 7 | `sensor_pattern` diagnostic reads plain colour vignetting as a fixed pattern (ratio 213, r = 1.0) | medium-high | CONFIRMED | NEW |
| 8 | Seestar `{ip}` unvalidated; no-key reconnect churn; controls ignore a running session | medium | CONFIRMED / READ | NEW |
