# Full audit — 2026-11-26 (v0.511.5)

The owner asked for a full audit after saying *"I feel like actual meaningful updates have not
been happening."* Seven independent read-only reviews ran in parallel. Each verified its claims
by running the real code on synthetic data shaped like his (a Seestar S30, ~105 targets, up to
35,894 subs per target, many mosaics). Their full reports are in this folder; this page is the
summary and the plan. Evidence paths inside the reports (`$S/…`, `/tmp/…`) point at the
auditors' scratch space, which is not kept. The key pictures are copied into [`img/`](img/).

| Report | Area |
|---|---|
| [`process.md`](process.md) | Is development producing meaningful progress, and why not |
| [`editor.md`](editor.md) | The editor and one-click Auto: does it make a finished picture? |
| [`engine.md`](engine.md) | The stacking engine and final image quality |
| [`ux.md`](ux.md) | The running app, screenshotted page by page, judged as the owner |
| [`backend.md`](backend.md) | Data safety (the `incoming/` guarantee), security, install/update |
| [`subsystems.md`](subsystems.md) | Seestar integration, diagnostics, Moon/Sun stacker, update button, planner |
| [`perf.md`](perf.md) | Speed and memory at the owner's scale |

## Verdict

**The owner is right.**
- **Most merges change nothing he can see.** Of 572 merges in 60 days, 42 % changed no code
  (51 % in the last 30 days), and only 7 % were things he asked for.
- **The work is chosen the wrong way.** Agents hunt edge cases on synthetic data, and the
  rules make every large, valuable job "gated" and parked.
- **Nobody measured the picture.** The two things that decide how his pictures look are the
  per-frame sky flatten in the stack and Auto in the editor. Both have large, measurable,
  fixable problems that no amount of edge-case work will surface.

**What is sound:**
- the stacking arithmetic, NaN and coverage handling;
- preview vs export agreement;
- the planner's astronomy;
- the Seestar protocol;
- the `incoming/` read-only guarantee in his configuration — a full HTTP walk of every write
  path left a snapshot of `incoming/` byte-identical.

## What would make his pictures visibly better (ranked)

1. **Auto: aim it at a finished picture, not a screen stretch.** Today it targets a sky of
   0.14–0.24 and has highlight protection off. Changing those two values (sky ≈ 0.10, "Hold
   back highlights" on) took the test galaxy's sky from 48 to 24 /255 and its grain from 15.6
   to 8.8 levels. White-clipped stars went from 72 % to 0 %. Size S; it changes the default
   look, so it needs his OK. See `img/auto-galaxy-today-vs-fixed.jpg` (top-left today,
   top-right with two values changed). [editor.md §2.1]
2. **The per-frame sky flatten erases large faint nebulae.** The 128 px box fit keeps only
   6–31 % of a nebula of radius ≥ 300 px and digs a dark bowl around it. Overlapping mosaic
   panels disagree by up to 66 % of the nebula's peak. A plane fit per frame, plus one gradient
   removal on the final stack, keeps 95–100 %. Size M–L, ship opt-in first. [engine.md]
3. **Nebula colour.** The gradient step's `match_channels` and the per-channel stretch undo
   the star colour calibration. The sky comes out teal, stars cyan and the red nebula washed
   out (`img/auto-nebula-colour-today-vs-reference.jpg`). Fix: a linked, sky-anchored stretch.
   Size M. [editor.md §2.2]
4. **Mosaic seams created by Auto's panel leveling** on nebula-filled canvases
   (`img/auto-mosaic-seams-today-vs-without-leveling.jpg`, top today, bottom without it).
   Size M–L. [editor.md §2.3]
5. **Hot pixels walk across the stack as coloured trails.** Cleanup runs after the debayer has
   smeared each one. A hot-pixel map learned from his own subs and repaired before debayer
   (`calibrate/defects.py` already exists but needs a dark he does not have) cut residual hot
   pixels from ~2,000 to ~50 per channel. Size M. [engine.md]
6. **Auto-drizzle buys almost nothing for ~7× the time** (stars 2.5 % smaller). A Bayer
   (raw-photosite) drizzle gives ~12 % smaller stars in every channel. Size M. [engine.md]
7. **The fixed sensor colour pattern** (his "colourful mosaic" blotches) is still on HOLD
   waiting for a diagnostic result that cannot arrive: the observer last posted on 2026-10-12.
   Size M–L. [process.md, subsystems.md]

## What gets in his way in the app (ranked)

1. **He cannot see the picture while editing.** At 1440×900 the editor image starts 715 px
   down under three explanation cards, and the Stretch sliders sit ~650 px below it. On a phone
   the image is off-screen (`img/ui-editor-1440x900.jpg`). Fix: pin the image and fold the cards
   into one tab. Size M. [ux.md]
2. **The clutter ratchet was gamed.** `tests/test_ui_clutter_budget.py` counts only the route
   file, so moving cards into child components drove the Dashboard count to 0. The page still
   pulls in 24 card kinds and 16 alerts. The measure must count what is rendered. Size S–M.
   [ux.md §6]
3. **Navigation: 19 sidebar links**, six of them about "your pictures"; Settings falls off a
   900 px screen. Proposed, nothing removed:
   - Home;
   - Pictures (Targets, Gallery, Best, My sky);
   - Plan (Tonight, Sky Map, Live);
   - Tools (Telescope, Calibration, Moon & Sun, Channel combine);
   - header icons for Jobs, Help and Settings.
   [ux.md §4]
4. **Main pages open with 2–3 notices of 40–100 words** before what he came for. "Start
   stacking" sits below the fold under expert switches. [ux.md]
5. **The Target page takes 9–18 s to load** (41 API calls), mostly planning data for a tab
   that isn't open. [ux.md]

## Speed at his scale ([perf.md](perf.md))

**Day-to-day use is fine.** The polled endpoints answer in 5–15 ms with 105 targets and 114k
frames, boot takes ~1 s, and Auto runs in ~2 s.

**Restacking is not.** These timings come from a 4-vCPU test box; his CPU is unknown, so each
figure is a range:

| Job | This box | 2.9× faster box |
|---|---|---|
| Plain stack, per sub | 2.2 s | 0.78 s |
| His biggest target (35,894 subs), plain | ≈ 22 h | ≈ 8 h |
| His biggest target, drizzle ×1.5 + reject | ≈ 51 h | ≈ 56 h |
| Restack everything (~110k subs) | ≈ 68 h | ≈ 24 h |

Every restack starts from scratch: `aligned_cache_path` is dead schema, and the default κ-σ
stack reads and fully reprocesses every sub twice.

**Biggest wins:**
1. **Incremental "add tonight's subs to the master".** Save the accumulator sums and the
   per-pixel mean/σ next to the run, then process only the new subs. 500 new subs would take
   ~10 min instead of ~22 h. Size L.
2. **On big targets, estimate κ-σ pass 1 from a sample of frames per panel.** About −45 % of
   every big plain stack. Size M, needs a parity test.
3. **Take drizzle's per-sub work off its single thread** and bound it to each sub's footprint.
   Saves ~25–50 h on the biggest target. Size M.

**Defects:**
- The out-of-memory guard underestimates mosaics by 1.7–3.2×, and ignores the post-stack
  steps that hit the same peak.
- A full-res export of an edited 8000×6000 picture takes 199 s and peaks at 4.85 GB, with no
  memory guard; its cache is thrown away on every update.
- The watcher treats every file as new after a restart.
- The biggest target's page downloads 20.6 MB of frame JSON with no gzip (~1.9 MB gzipped).

## Things that are broken or unsafe (ranked)

1. 🔒 **Fixed in v0.511.6:** the ASTAP path setting could name any program, and the next plate
   solve ran it (no password by default). [backend.md §1]
2. **Seestar page:**
   - the telemetry thread dies for good the first time the scope goes offline, and the page
     then shows stale numbers as "connected" (`webapp/seestar/manager.py`, catches only
     `SeestarError`);
   - default discovery is UDP-only from a bridged container, so it can never find his scope.
   [subsystems.md §1]
3. **Updates:** a failed image build leaves the app stopped, and a retry overwrites `last-good`
   with the broken version, so rollback "restores" the broken one. [backend.md §2,
   subsystems.md §4]
4. **Security hardening still open:**
   - no Host-header check (a DNS-rebinding page can use a password-less install's API);
   - PBKDF2 runs on the event loop for every request once a password is set (30 parallel GETs:
     5.4 s vs 0.5 s);
   - the container runs as root with `incoming/` read-write.
   [backend.md §3–4, §16]
5. **Imports repeat old work:** every import re-runs the full ASTAP ladder on every sub that
   already failed to solve (one new sub with 8 unsolvable ones: 27 ASTAP runs).
   [backend.md §5]
6. **Moon & Sun:**
   - drizzle prints a coloured 3-pixel mesh when frame brightness flickers;
   - a partial-phase Moon with maria can be misaligned by ~25 px with no warning.
   [subsystems.md §3]
7. **Disk:** the app cannot boot on a full disk (boot re-saves `config.json`), and deploy
   snapshots are never pruned. [backend.md §6–7]
8. **Diagnostics** have no in-app view or export, so nothing reaches the developers.
   [subsystems.md §2]

## Why progress stalled — and what to change ([process.md](process.md))

**Root causes:**
1. The work queue is fed by a synthetic bug-hunter (the Scout's four-sweep rotation and the
   dogfood), not by the owner or his data, and the one real-data channel (the observer) died
   unnoticed.
2. The rules reward small and safe. Anything large is "gated" and parked, every fix is its
   own PR and version, and idle runs still write a docs PR.
3. Surface and paperwork outgrew the mission:
   - 27 pages and 258 API routes;
   - test code 1.3× the app code;
   - ~192,000 words read at the start of every run;
   - a 1.2 MB backlog, 77 % of it a Shipped list.

**Recommended changes** (the drafts in process.md §8 are a starting point; the owner decides):
- Work in **owner-chosen themes** (at most three at a time), with picture quality measured on
  real data. Starting themes: *Auto makes a finished picture*, *the stack keeps faint nebulae*,
  *one simple screen per job*.
- Sweeps become weekly and file only serious bugs; small findings go into one monthly batch.
- **Idle runs write nothing.**
- Weekly releases with a five-bullet "What's new".
- Cap the docs and archive the Shipped list.
- **Gate in code, not in the backlog:** ship a risky change opt-in and self-checking rather
  than parking it.
- Give diagnostics an in-app **"Copy report for the developer"**, so nothing depends on the
  observer.
