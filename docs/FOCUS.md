# Current focus — AstroStack

> **Short on purpose (AGENTS.md: "short, dated, the Scout keeps it current").** One dated line per run goes at the
> top of *Run log*; keep about the last ten and move older lines, whole and in order, to `docs/archive/`. Detail
> belongs in `docs/PROCESS-NOTES.md`, never here. The 2,559-line page this replaced is kept verbatim in
> [`archive/FOCUS-to-2026-10-21.md`](archive/FOCUS-to-2026-10-21.md) — nothing was deleted.

## Front of the queue (2026-11-04)

**No ungated bug is open.** The full-size check's navigator answers the arrow keys (v0.505.15). A tap on the crop rectangle no longer re-rounds Auto's trim (v0.505.14). A Curves double-click on the box's edge no longer makes a hidden endpoint (v0.505.13). Tonight's planner tables fit a phone as of v0.505.12 (stacked rows, like Calibration's v0.505.11). The `._*.fit` sidecar half of the Scout 2026-11-03 entry shipped as v0.505.10; its
`.recycle/` / `.Trash-*/` half waits on the owner. A Builder should dogfood (`--mosaic --editor`) and file what it finds. The owner's ⭐
colour-pattern entry is on HOLD for his per-temperature numbers; the dark ring waits on the S30's measured vignette.
Recently closed: a one-target stack after a Combine shows its deeper picture (v0.505.9); "It's back" names the deepest
returning target per part (v0.505.8); Compare's same-object pair (v0.505.7). Older closures are in the archived run
log and `SHIPPED.md`.

**Gated, do not start:** the un-located-panel entry (second in Bugs) waits on the owner's hint-shape answer; the
other LEADs and ⚪ notes in Bugs wait on owner/observer measurements — read each one's gate first, and do not
re-litigate a stand-down that carries numbers. **Issue inbox:** #878, #880, #903, #1015 — all previously acted-on
and owner-gated, none updated since 2026-10-12 (re-checked 2026-11-04).

## QA rotation (Scout)

Order (AGENTS.md roles): (1) preview↔export parity at mosaic scale → (2) mosaic/walk-away per-panel divergence →
(3) ASTAP/ffmpeg filesystem side effects with a stub binary → (4) the webapp routers. **Last swept: (4), 2026-11-04
→ next sweep is (1).** Each (3) sweep must find a *new* angle — the list of angles already run is in the
`Sweep (3)` entries of `docs/PROCESS-NOTES.md` (grep `sweep (3)`).

## Run log (newest first)

*2026-11-04 (Scout, branch `claude/exciting-wozniak-9ddn2i`) — **QA rotation sweep (4), new angle: every GET route crawled on an owner-shaped install (subs read in place from `incoming/`, `copy_to_cache` off) with a byte/mtime snapshot of the whole data root before and after — CLEAN** (`incoming/` untouched; the only writes are first-call caches inside `library/`; a second crawl writes nothing at all, files or DB rows; 0 × 5xx). Inbox: the same four, owner-gated. Dogfood `--mosaic` CLEAN. Backlog: 14 closed stubs (236 lines) archived to `archive/IMPROVEMENTS-closed-stubs.md`. **START HERE NEXT RUN:** Builder: nothing ungated — dogfood `--mosaic --editor`; Scout: sweep (1) with a new angle.*
*2026-11-04 (Builder, branch `claude/fervent-allen-mfjvsj`) — **v0.505.15: the full-size check's navigator moves with the arrow keys** (`loupe.nudgeSpot`; it was a focusable `role="button"` with only an `onClick`, so a keyboard user could not move the full-resolution window off the centre). Code read of the editor's widgets; suite 8567 passed / 7 skipped. **START HERE NEXT RUN:** Scout: sweep (4) with a new angle; Builder: nothing ungated — other focusable `role="button"`s (`OpList`, `ImagingCalendarCard`) are the same class, worth one read.*
*2026-11-04 (Builder, branch `claude/fervent-allen-lsjgul`) — **v0.505.14: a tap on the crop rectangle is no longer an edit** (`cropDrag.cropDragCommitParams`; it re-rounded Auto's exact mosaic trim, moving the exported crop, and withdrew "What Auto did"; a cancelled drag now drops). Code read of the editor's drag widgets. **START HERE NEXT RUN:** Scout: sweep (4) with a new angle; Builder: the split dividers (`Editor.tsx` split, `FullSizeCheck`) also lack `onPointerCancel` — harmless (no commit), so only if touching them.*
*2026-11-04 (Builder, branch `claude/fervent-allen-l0f4s3`) — **v0.505.13: a double-click on the Curves box's edge no longer adds a hidden second endpoint** (`curveDrag.insertCurvePoint`; on the right edge it greyed star cores). Found by a code read of the editor's drag widgets. **START HERE NEXT RUN:** Scout: sweep (4) with a new angle; Builder: nothing ungated — a code read of the other editor widgets (`cropDrag`, `FullSizeCheck` split) is the same class.*
*2026-11-03 (Builder, branch `claude/fervent-allen-dlwmrz`) — **v0.505.12: the Tonight planner's target tables fit a phone** (`TargetTable` / `TargetSummary` / `tonight.targetSpecsLine`; at 420 px the 520 px table hid the Moon and Score columns on the page read at the scope). Dogfood `--mosaic --editor` CLEAN; phone `/tonight` 3,521 px. The remaining scroll tables (Target frames grid, Nights card) are fine as they are. **START HERE NEXT RUN:** Scout: sweep (4) with a new angle; Builder: nothing ungated — dogfood and file what you find.*
*2026-11-03 (Builder, branch `claude/fervent-allen-gsmulj`) — **v0.505.11: the Calibration page's masters list fits a phone** (`CalibrationView` / `masterSpecsLine`; at 420 px the 680 px table hid Exp/Gain/Temp/Size and the delete button off the right edge, which the overflow probe skips by design since it is a scroll container). Dogfood `--mosaic --calibration --combine` otherwise CLEAN. **START HERE NEXT RUN:** Scout: sweep (4) with a new angle; Builder: nothing ungated — a phone-width look at other pages' `Table.ScrollContainer`s is the same class.*
*2026-11-03 (Builder, branch `claude/fervent-allen-6hrl7o`) — **no app change: nothing ungated; first-ever dogfood `--mosaic --dithered --big --deep --incoming-lag --editor` CLEAN** (`[scale]` 0/16 moved, trim 7.9 % / 6.7 % full-size, dithered 30.7 % against its 30.3 % apron, four editor drives clean, deep frames table windowed at 301 of 1,200 rows). Suite 8567 passed / 7 skipped. **START HERE NEXT RUN:** Scout: sweep (4) with a new angle; Builder: nothing ungated until the sensor-temperature or vignette gate is answered.*
*2026-11-03 (Builder, branch `claude/fervent-allen-7cutrz`) — **v0.505.10: a macOS `._<name>.fit` sidecar in `incoming/` is no longer read as a sub** (`ingest.is_appledouble_sidecar`, shared by `find_fits_files` / `scan_and_organize` / `plan_incoming_units`; part (a) of the Scout's sweep (3) entry). Part (b), the `.recycle/` / `.Trash-*/` folder skip, stays open and owner-gated. Suite 8567 passed / 7 skipped. **START HERE NEXT RUN:** Scout: sweep (4) with a new angle; Builder: nothing ungated — dogfood `--mosaic --editor`.*
*2026-11-03 (Scout, branch `claude/exciting-wozniak-bnak6b`) — **QA rotation sweep (3), new angle: junk a NAS share or desktop leaves in `incoming/` (`._*.fit`, `.recycle/`, `.Trash-*/`) — side effects CLEAN, one bug filed reproduced** (no walker skips a dot-name). Inbox: the same four, owner-gated. Dogfood `--mosaic` CLEAN. **START HERE NEXT RUN:** Builder: part (a) of that entry (ungated); Scout: sweep (4) with a new angle.*
*2026-11-03 (Builder, branch `claude/fervent-allen-9aep51`) — **no app change: nothing ungated; two new-angle probes CLEAN** — a sub deleted from disk before its stack is skipped with a plain log line (7 of 8 stacked), and all 21 editor ops keep mosaic holes as holes at every parameter extreme. Suite 8557 passed / 7 skipped. **START HERE NEXT RUN:** Scout: sweep (3) with a new angle; Builder: nothing ungated until the sensor-temperature or vignette gate is answered.*

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
