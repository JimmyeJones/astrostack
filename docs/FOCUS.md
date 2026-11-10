# Current focus — AstroStack

> **Short on purpose (AGENTS.md: "short, dated, the Scout keeps it current").** One dated line per run goes at the
> top of *Run log*; keep about the last ten and move older lines, whole and in order, to `docs/archive/`. Detail
> belongs in `docs/PROCESS-NOTES.md`, never here. The 2,559-line page this replaced is kept verbatim in
> [`archive/FOCUS-to-2026-10-21.md`](archive/FOCUS-to-2026-10-21.md) — nothing was deleted.

## Front of the queue (2026-11-10)

**Nothing ungated is open in Bugs** (the double-queued Process/Restack bug shipped as v0.505.37). A Builder should
dogfood (`--mosaic --editor`) and file what it finds. The `._*.fit` sidecar half of the Scout
2026-11-03 entry shipped as v0.505.10; its `.recycle/` / `.Trash-*/` / visible `.zfs/` half (one skip) waits on the
owner. The owner's ⭐ colour-pattern entry is on HOLD for his per-temperature numbers; the dark ring waits on a
diagnostic (below). Recent closures (v0.505.9 → v0.505.36, the Jobs-page read-back series among them) are in
the run log below and `SHIPPED.md`.

**Gated, do not start:** the un-located-panel entry (second in Bugs) waits on diagnostic `mosaic_panel_hints` v2
(v0.506.10), the dark ring on `sky_falloff` v2 (v0.506.9) and the #878 headline LEAD on `twin_target_overcount` v1 (v0.506.8); the
other LEADs and ⚪ notes in Bugs wait on owner/observer measurements — read each one's gate first, and do not
re-litigate a stand-down that carries numbers. **Issue inbox:** #878, #880, #903, #1015 — all previously acted-on
and owner-gated, none updated since 2026-10-12 (re-checked 2026-11-10, Scout `optimistic-cannon-mgl6hf`). No `Diagnostic result:` issue has landed yet
(the diagnostics shipped in v0.506.0 / v0.506.1 run after the owner's next update).

## QA rotation (Scout)

Order (AGENTS.md roles): (1) preview↔export parity at mosaic scale → (2) mosaic/walk-away per-panel divergence →
(3) ASTAP/ffmpeg filesystem side effects with a stub binary → (4) the webapp routers. **Last swept: (3), 2026-11-10
→ next sweep is (4).** Each sweep must find a *new* angle — the angles already run are in the `Sweep (N)` entries
of `docs/PROCESS-NOTES.md` (grep `sweep (4)`).

## Run log (newest first)

*2026-11-10 (Builder, branch `claude/focused-noether-zzbnof`) — **v0.506.11: the first-run "Your first image" card says "you're here" instead of linking a step to the page it sits on** (`firstImageSteps.stepIsHere`) — found by a `--empty` dogfood pass: on an empty Library "Open Library"/"Pick a target" were dead self-links, on an empty Gallery "Open a picture"/"Open your edit". Suite 8681 passed / 7 skipped. **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate or a diagnostic result arrives; Scout: sweep (4), and file `Diagnostic result:` issues when they land.*
*2026-11-10 (Scout, branch `claude/optimistic-cannon-mgl6hf`) — **QA rotation sweep (3), new angle: a `sys.addaudithook` tracer over every write-capable call (write-mode `open`/`os.open`, rename, remove, chmod, utime, mkdir, `fits.open(mode='update')`) naming a path under `incoming/`, through scan → QC + stub-ASTAP solve (serial and pool) → all five library diagnostics (direct and the boot job, `webapp.diagnostics`) → a mosaic stack, `copy_to_cache` off — CLEAN** (0 write attempts, 402 read-opens; positive controls fire). Inbox: the same four, owner-gated; no `Diagnostic result:` yet. Dogfood `--mosaic` CLEAN. Suite 8681 passed / 7 skipped. **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate or a diagnostic result arrives; Scout: sweep (4), and file `Diagnostic result:` issues when they land.*
*2026-11-10 (Builder, branch `claude/fervent-allen-dh3hxr`) — **no app change: nothing ungated; dogfood `--mosaic --dithered --closing --editor` CLEAN** (a combination no pass had run together: three editor drives re-render all 21 ops, Undo/Redo apply, taste chips behave; Auto trim 7.9 % mosaic / 30.7 % dithered against its recorded 30.3 % apron; *Shoot these before they're gone* and *Plan my week* name the same closing target and night; the dithered readiness goal 14.2 h over ~6 fields is the 2×2's ~2.4 h a field, not a drift). Suite 8681 passed / 7 skipped. **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate or a diagnostic result arrives; Scout: sweep (3), and file `Diagnostic result:` issues when they land.*
*2026-11-10 (Scout, branch `claude/exciting-wozniak-yw3dcx`) — **QA rotation sweep (2), new angle: the `mosaic_panel_hints` diagnostic's own per-panel bar on S30-shaped mosaics — one bug, Scout-fixed as v0.506.10** (v1's 0.25° "on its own panel" bar read per-panel hints carrying an ordinary 0.15–0.3° go-to offset as `mixed`, and counted the offset as missing panels; v2 asks which panel a hint is *nearest* and compares hints with hints at half the panel step — v1 never reached `stable`). Inbox: the same four, owner-gated; no `Diagnostic result:` yet. Dogfood `--mosaic` CLEAN. Suite 8678 passed / 7 skipped. **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate or a diagnostic result arrives; Scout: sweep (3), and file `Diagnostic result:` issues when they land.*
*2026-11-10 (Builder, branch `claude/fervent-allen-tvk8gv`) — **v0.506.9: diagnostic `sky_falloff` v2 takes its edge/centre slope only between subs of the same target** (`_pair_slope`). v1 (not yet on `stable`) fitted one line through every target, so a central nebula read as vignetting: a vignette-free synthetic library with an object on every target read 0.83–0.90, under the dark-ring entry's 0.97 threshold; v2 reads 1.000 / 0.897 (truth 0.90). Suite 8676 passed / 7 skipped. **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate or a diagnostic result arrives — the other not-yet-on-`stable` diagnostics (`mosaic_panel_hints` v1, `twin_target_overcount` v1) were read this run and look sound; Scout: sweep (2), and file `Diagnostic result:` issues when they land.*
*2026-11-10 (Builder, branch `claude/fervent-allen-pbc70q`) — **v0.506.8: fifth library diagnostic `twin_target_overcount` v1** (`seestack.diag.twin_overcount`): the registry sums the Dashboard headline shows against every sub counted once by source file — the gate on the #878 `/api/stats` headline LEAD, the last Bugs gate phrased "the observer can read both" that fits the record alone. Dogfood `--mosaic --deep --no-site --restack --big --editor` CLEAN (Auto trim 7.9 %; all 21 ops re-render, Undo/Redo apply, taste chips behave; scale diff 0 of 16 moved). Suite 8664 passed / 7 skipped before the change. **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate or a diagnostic result arrives; Scout: sweep (2), and file `Diagnostic result:` issues when they land.*
*2026-11-10 (Builder, branch `claude/fervent-allen-brcbxl`) — **two new library diagnostics answer the two Bugs gates that were waiting on the observer: v0.506.6 `mosaic_panel_hints` v1** (does a sub's pointing hint name its panel or the mosaic's centre — `seestack.diag.mosaic_hints`) **and v0.506.7 `sky_falloff` v1** (the S30's centre-to-edge sky fall-off with the pedestal taken out — `seestack.diag.sky_falloff`). Suite 8664 passed / 7 skipped. **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate or a diagnostic result arrives; Scout: sweep (2), and file `Diagnostic result:` issues when they land.*
*2026-11-10 (Builder, branch `claude/fervent-allen-5hddau`) — **v0.506.5: the two library diagnostics survey the library as four-column `SubRef`s instead of whole `FrameRow`s** (`seestack.diag.iter_sub_refs`); `sensor_pattern_by_temperature`'s peak on a 29,000-sub synthetic library 114.5 MB → 9.5 MB, identical results, no version bump — it lands before v2 reaches `stable`. **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate or a diagnostic result arrives; Scout: sweep (2).*
*2026-11-09 (Builder, branch `claude/fervent-allen-13mekw`) — **no app change: nothing ungated; dogfood `--mosaic --restack --calibration --no-site --editor` CLEAN** (a combination no pass had run together: the calibrated restack 3 → 6 subs applies both masters and the calibration note withdraws; mosaic notes agree on the thin top-right panel; Auto trim 7.9 %; all 21 ops re-render, Undo/Redo apply, taste chips behave). The Scout's two unswept (1) leads — the year recap hero and a pinned cover saved North-up later — read clean: both resolve through `current_picture_path`, and a North-up save rewrites the pinned run's own `preview_path`. Suite 8638 passed / 7 skipped. **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate or a diagnostic result arrives; Scout: sweep (2).*
*2026-11-09 (Builder, branch `claude/fervent-allen-3qy836`) — **no app change: nothing ungated; dogfood `--mosaic --incoming-lag --no-site --editor` CLEAN** (the two flags no pass had run since 2026-10-21: the Dashboard's incoming-lag note reads 8 waiting / 11 days with its unreadable-file count; `/tonight` renders its no-site alert; mosaic Target page's next-best-move, readiness and framing notes point the same way; Auto trim 7.9 %; all 21 ops re-render, Undo/Redo apply, taste chips behave). Suite 8638 passed / 7 skipped. **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate or a diagnostic result arrives; Scout: sweep (2).*

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
