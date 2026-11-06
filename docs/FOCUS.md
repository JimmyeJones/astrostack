# Current focus — AstroStack

> **Short on purpose (AGENTS.md: "short, dated, the Scout keeps it current").** One dated line per run goes at the
> top of *Run log*; keep about the last ten and move older lines, whole and in order, to `docs/archive/`. Detail
> belongs in `docs/PROCESS-NOTES.md`, never here. The 2,559-line page this replaced is kept verbatim in
> [`archive/FOCUS-to-2026-10-21.md`](archive/FOCUS-to-2026-10-21.md) — nothing was deleted.

## Front of the queue (2026-11-06)

**No ungated bug is open.** The "Hold back highlights" severity is measured on a native window of the master and no longer drifts with the proxy step (v0.505.23; its size floor was v0.505.22). A trim lands in one crop, not every crop (v0.505.21). The Levels/Curves histogram guides sit on the op's own input histogram (v0.505.20). Every split before/after divider answers the arrow keys (v0.505.17). The imaging calendar's night answers Enter/Space (v0.505.16). The full-size check's navigator answers the arrow keys (v0.505.15). A tap on the crop rectangle no longer re-rounds Auto's trim (v0.505.14). A Curves double-click on the box's edge no longer makes a hidden endpoint (v0.505.13). Tonight's planner tables fit a phone as of v0.505.12 (stacked rows, like Calibration's v0.505.11). The `._*.fit` sidecar half of the Scout 2026-11-03 entry shipped as v0.505.10; its
`.recycle/` / `.Trash-*/` half waits on the owner. A Builder should dogfood (`--mosaic --editor`) and file what it finds. The owner's ⭐
colour-pattern entry is on HOLD for his per-temperature numbers; the dark ring waits on the S30's measured vignette.
Recently closed: a one-target stack after a Combine shows its deeper picture (v0.505.9); "It's back" names the deepest
returning target per part (v0.505.8); Compare's same-object pair (v0.505.7). Older closures are in the archived run
log and `SHIPPED.md`.

**Gated, do not start:** the un-located-panel entry (second in Bugs) waits on the owner's hint-shape answer; the
other LEADs and ⚪ notes in Bugs wait on owner/observer measurements — read each one's gate first, and do not
re-litigate a stand-down that carries numbers. **Issue inbox:** #878, #880, #903, #1015 — all previously acted-on
and owner-gated, none updated since 2026-10-12 (re-checked 2026-11-05).

## QA rotation (Scout)

Order (AGENTS.md roles): (1) preview↔export parity at mosaic scale → (2) mosaic/walk-away per-panel divergence →
(3) ASTAP/ffmpeg filesystem side effects with a stub binary → (4) the webapp routers. **Last swept: (1), 2026-11-05
→ next sweep is (2).** Each (3) sweep must find a *new* angle — the list of angles already run is in the
`Sweep (3)` entries of `docs/PROCESS-NOTES.md` (grep `sweep (3)`).

## Run log (newest first)

*2026-11-06 (Builder, branch `claude/fervent-allen-h2pq65`) — **no app change: nothing ungated; edit-op fuzz CLEAN** (all 21 registry ops at defaults and param extremes on NaN-cornered, constant, tiny and NaN-channel inputs: no new NaN in covered pixels, no `inf`, no raise on a realistic shape — see `PROCESS-NOTES.md`). Suite 8590 passed / 7 skipped. **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate is answered; Scout: sweep (2) with a new angle.*
*2026-11-06 (Builder, branch `claude/fervent-allen-bcm43q`) — **no app change: nothing ungated; dogfood `--combine` CLEAN** (the stalest flag: merge nudge, Combine, rescan and a late sub all land in one deep target; `incoming/` byte-for-byte unchanged; the framing card's "5 % in" beside "3×2 covers it" is the fixture's unsolved pixel scale, not a bug — see `PROCESS-NOTES.md`). Suite 8590 passed / 7 skipped. **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate is answered; Scout: sweep (2) with a new angle.*
*2026-11-06 (Builder, branch `claude/fervent-allen-qbodbr`) — **no app change: nothing ungated; dogfood `--dithered --restack --incoming-lag --editor` CLEAN** (dithered canvas matches its recorded shape, trim 30.7 % vs the 30.3 % apron; both editor drives re-render all 21 ops; restack reel and noise-delta present; incoming-lag note counts 8 waiting subs; nothing overflowing, no console errors). Suite 8590 passed / 7 skipped. **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate is answered; Scout: sweep (2) with a new angle.*
*2026-11-06 (Builder, branch `claude/fervent-allen-x7cxnp`) — **no app change: nothing ungated; dogfood `--deep --calibration --closing` CLEAN** (the three flags today's passes had not run: masters discovered, built and auto-bound, run 1 applied dark+flat and the health note withdrew; deep frames table windows 301 of 1,200 rows and grows on scroll, first paint 1.5 s; two closing targets ranked by depth; nothing overflowing, no console errors; `/life-list [Still to shoot]` 14,513 px is by design, see `SHIPPED.md`). Suite 8590 passed / 7 skipped. **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate is answered; Scout: sweep (2) with a new angle.*
*2026-11-05 (Builder, branch `claude/fervent-allen-6qs7s9`) — **no app change: nothing ungated; dogfood `--mosaic --editor --big` CLEAN, and v0.505.23 confirmed in the browser** (the full-size twin's "What Auto-process did" now offers *Hold back highlights (0.05)*, as the 2×2 does; `[scale]` 0 of 16 moved; trim 7.9 %; all three editor drives re-render every op; nothing overflowing, no console errors). Suite 8590 passed / 7 skipped. **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate is answered; Scout: sweep (2) with a new angle.*
*2026-11-05 (Builder, branch `claude/fervent-allen-6fqsbn`) — **v0.505.23: the "Hold back highlights" core is measured on a native window of the master** (`highlights.suggest_highlight_protect(native_window=…)`, `editor._highlight_native_window`, rendered like the full-size check). A small core keeps its button at every proxy step, and a core clipped at capture gets none. Dogfood scale pair: the full-size twin goes from silent to 0.05 (severity 0.189 vs the 2×2's 0.174). Suite 8581 passed / 7 skipped before the change. **START HERE NEXT RUN:** Builder: nothing ungated — dogfood `--mosaic --editor`; Scout: sweep (2) with a new angle.*
*2026-11-05 (Builder, branch `claude/fervent-allen-lfctn2`) — **no app change; the "Hold back highlights" proxy-step entry re-measured and re-sized L** (`highlights._recoverable_flat_fraction`): the drift runs in *both* directions — a small core goes silent on a coarse proxy, and a core clipped at capture gets a false button there (none at step 1, 0.05/0.30/0.50 at steps 2/3/4). Both cheap fix shapes (core minus a rim; upsample to native) inflate that saturated core and were rejected with numbers. **START HERE NEXT RUN:** Builder: nothing small ungated — that entry's native-crop shape is L; Scout: sweep (2) with a new angle.*
*2026-11-05 (Builder, branch `claude/fervent-allen-qlw3h6`) — **v0.505.22: the "Hold back highlights" size floor is one frame's share, in native pixels** (`highlights._min_core_area`, `editor._run_frame_px`; it grew with a mosaic's canvas). Dogfood `--big --mosaic --editor` CLEAN (scale pair 0 of 16 moved). The full-size twin is still silent for a second, measured cause (severity falls with the proxy step for a small core), filed in Bugs. **START HERE NEXT RUN:** Builder: that Bugs entry (size M, ungated); Scout: sweep (2) with a new angle.*
*2026-11-05 (Builder, branch `claude/fervent-allen-nq37cj`) — **no app change; one measured bug filed: the "Hold back highlights" nudge goes silent on the bigger mosaic canvas for the same blown core** (`highlights.measure_blown_core`'s area floor is a share of the whole canvas, counted in proxy pixels; 91 px core → nudge on the 2×2, ≈96 native px → `None` on its full-size twin). Dogfood `--big --mosaic --editor` otherwise CLEAN (scale pair 0 of 16 moved, nothing overflowing, no console errors). **START HERE NEXT RUN:** Builder: that Bugs entry (size M, ungated); Scout: sweep (2) with a new angle.*
*2026-11-05 (Scout, branch `claude/exciting-wozniak-djc6th`) — **QA rotation sweep (1), new angle: the keepsake matte and nameplate on a native North-up turn of a trimmed auto-edit vs its stored-preview twin — CLEAN** (card aspect ≤ 0.002, caption bar ≤ 0.002 of the frame, at 30°, −71° and 12° on mosaic-size canvases). Inbox: the same four, owner-gated. Dogfood `--mosaic` CLEAN. Suite 8574 passed / 7 skipped. **START HERE NEXT RUN:** Builder: nothing ungated — dogfood `--mosaic --editor`; Scout: sweep (2) with a new angle.*

## Standing frontier

- **Mosaic-scale and walk-away behaviour is the open frontier**, not the single-field engine core. Do NOT re-sweep
  `seestack/stack` or `seestack/calibrate` until a new bug is found there (AGENTS.md).
- **Grown-canvas rule:** anything that puts one run's look, crop or picture onto another run's canvas places it by
  both masters' WCS and falls back (or hides itself) without one — v0.502.23 (reel) and v0.502.24 (previous-edit
  crop) are the pattern; the noise-delta picture (v0.502.32) was the last known surface.

## How the owner gets builds now

He deploys with `sudo bash scripts/deploy.sh` from the **`stable`** branch (advanced by `.github/workflows/stable.yml`
to the newest `main` commit ≥ 3 days old with green CI) or from a release tag. So a fix reaches him days after it
merges — ship the follow-up to your own change *before* that soak ends.
