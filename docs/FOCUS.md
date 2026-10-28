# Current focus — AstroStack

> **Short on purpose (AGENTS.md: "short, dated, the Scout keeps it current").** One dated line per run goes at the
> top of *Run log*; keep about the last ten and move older lines, whole and in order, to `docs/archive/`. Detail
> belongs in `docs/PROCESS-NOTES.md`, never here. The 2,559-line page this replaced is kept verbatim in
> [`archive/FOCUS-to-2026-10-21.md`](archive/FOCUS-to-2026-10-21.md) — nothing was deleted.

## Front of the queue (2026-10-28)

**One ungated bug is open — the top of Bugs: the deepening reel draws an earlier, shallower night cleaner and
brighter than the newest on a mosaic whose canvas grew or shrank** (Scout sweep (1), reproduced, fix shape measured;
size S–M). Builder: take it first. Recently closed: one night, one dark window (v0.503.10); the hung ffmpeg decoder vs Cancel (v0.503.8); the walk-away missing-files hold on a mosaic panel (v0.503.5); Compare's Split/Blink on a grown mosaic (v0.503.1); the Scout's 2026-10-21 per-part entry closed with v0.502.40 (readiness / Dashboard
progress / Tonight badge); a dogfood pass found and fixed the week plan's same-sky flip (v0.502.41); the Scout's sweep (4) fixed a merge that
deleted a folder a stack was still writing into (v0.502.42). After that, a Builder with nothing ungated should take a beginner feature from "Features that serve
real workflows" in [`IMPROVEMENTS.md`](IMPROVEMENTS.md), or dogfood (`--mosaic --editor`) and file what it finds.

**Gated, do not start:** the un-located-panel entry (second in Bugs) waits on the owner's hint-shape answer; the
other LEADs and ⚪ notes in Bugs wait on owner/observer measurements — read each one's gate first, and do not
re-litigate a stand-down that carries numbers. **Issue inbox:** #878, #880, #903, #1015 — all previously acted-on
and owner-gated, none updated since 2026-10-12 (re-checked 2026-10-27).

## QA rotation (Scout)

Order (AGENTS.md roles): (1) preview↔export parity at mosaic scale → (2) mosaic/walk-away per-panel divergence →
(3) ASTAP/ffmpeg filesystem side effects with a stub binary → (4) the webapp routers. **Last swept: (1), 2026-10-28
→ next sweep is (2).** Each (3) sweep must find a *new* angle — the list of angles already run is in the
`Sweep (3)` entries of `docs/PROCESS-NOTES.md` (grep `sweep (3)`).

## Run log (newest first)

*2026-10-28 (Scout, branch `claude/blissful-einstein-96mvmu`) — **QA rotation sweep (1), new angle: the deepening reel's placement on a canvas that grew or shrank (`render_deepening_frames` / `_place_on_sky`) — the shallow night renders cleaner and brighter than the deep one (σ 25.3 vs 37.7, sky 73 vs 51; single field 49.3 → 37.7); filed reproduced at the top of Bugs with a measured fix shape.** Inbox: the same four, owner-gated. Suite 8310 passed / 7 skipped; dogfood `--mosaic` CLEAN (trim 7.9 %). **START HERE NEXT RUN:** Builder: that entry. **Rotation: (1) done → next sweep is (2).***
*2026-10-28 (Builder, branch `claude/nice-carson-mxelbj`) — **Dogfood `--incoming-lag --big --mosaic --editor` CLEAN; v0.503.13: the legacy desktop Library dialog's "solved N/M" counts real solves (`_target_summary_line`, `solve_ok`).** All 21 ops on field, 2×2 and full size; trim 7.9 %; scale pair 0 of 16 moved. **START HERE NEXT RUN:** Builder: no ungated bug — beginner feature or dogfood (`--restack --dithered`, `--calibration --big`).*
*2026-10-28 (Builder, branch `claude/nice-carson-6l8p8e`) — **Dogfood `--empty`, then `--deep --closing --mosaic --editor`, CLEAN; nothing shipped.** All 21 ops re-rendered on field and 2×2, Auto trim 7.9 %, deep table grew 301→601 rows, no overflow, no console errors. The deep sample's "7×7 vs 3×3" panel count is a two-sized-fixture artefact (PROCESS-NOTES). **START HERE NEXT RUN:** Builder: no ungated bug — beginner feature or dogfood (`--incoming-lag --big`, `--restack --dithered`).*
*2026-10-28 (Builder, branch `claude/nice-carson-rgalhh`) — **v0.503.12: an unstacked mosaic target is no longer badged "Needs 3×3 mosaic" about itself on Plan my week / Tonight** (`canvas_is_mosaic` honours `is_mosaic_target_name`), read off `--combine --calibration --editor --dithered`'s Tonight paragraph; that pass otherwise CLEAN (all ops re-rendered, no overflow, no console errors). Suite 8310 passed / 7 skipped. **START HERE NEXT RUN:** Builder: no ungated bug — beginner feature or dogfood (`--empty`, `--deep --closing --mosaic`).*
*2026-10-27 (Builder, branch `claude/nice-carson-3du8rr`) — **v0.503.11: History's Noise trend quotes the two σ at the precision that tells them apart** (`noiseTrendSummary`) — it said "Cleaner … (σ 0.001 vs 0.001)" beside a −43 % card, read off the `--restack --big --mosaic --editor` screenshots; that pass otherwise CLEAN (21 ops on field, 2×2 and full size; trim 7.9 %; scale pair 0 of 16 moved). **START HERE NEXT RUN:** Builder: no ungated bug — beginner feature or dogfood (`--combine --calibration`, `--dithered --closing`).*
*2026-10-27 (Scout, branch `claude/beautiful-newton-aovpvx`) — **QA rotation sweep (4), the 2026-10-23 sweep's in-flight-job leads reproduced with a held real job: `DELETE /api/targets/{safe}` mid-stack and `DELETE …/stack-runs/{id}` mid-export both hold; `cache/clear` judged low-stakes (stage 2 unread by the stack, stage 1 empty with `copy_to_cache` off). CLEAN, nothing filed.** Inbox: the same four, owner-gated. Dogfood `--mosaic` CLEAN (trim 7.9 %). **START HERE NEXT RUN:** Builder: no ungated bug — beginner feature or dogfood (`--incoming-lag`, `--combine --calibration`). **Rotation: (4) done → next sweep is (1).***
*2026-10-27 (Builder, branch `claude/nice-carson-ugfxmu`) — **v0.503.10: one night has one dark window whenever it is asked about** (`nightplan._local_noon_near`) — Tonight's header said dark ended 04:57 while Plan my week under it said shootable to 05:01; read off the `--incoming-lag --mosaic --editor` screenshots, that pass otherwise CLEAN. **START HERE NEXT RUN:** Builder: no ungated bug — beginner feature or dogfood (`--combine --calibration`, `--restack --big`).*
*2026-10-27 (Builder, branch `claude/nice-carson-viz24y`) — **v0.503.9: Tonight's Night picker shows the night it plans instead of a blank `mm/dd/yyyy`** (`shownNightDate`), read off the screenshots of dogfood `--empty` then `--deep --closing --editor`; both passes otherwise CLEAN (all 21 ops, trim n/a single field, deep table 301→601 rows). **START HERE NEXT RUN:** Builder: no ungated bug — beginner feature or dogfood (`--incoming-lag`, `--combine --calibration`).*
*2026-10-27 (Builder, branch `claude/nice-carson-jxxq55`) — **Dogfood `--dithered --big --mosaic --editor` CLEAN; nothing shipped.** All four editor drives (field, 2×2, full-size, dithered) re-rendered all 21 ops; the full-size loupe followed the navigator; Auto trim 7.9 % / 7 % / 30.7 % (dithered apron 30.3 %); taste chips behaved; nothing overflowing, no console errors. Baseline suite 8296 passed / 7 skipped. **START HERE NEXT RUN:** Builder: no ungated bug — beginner feature or dogfood (`--empty`, `--deep --closing`).*
*2026-10-26 (Builder, branch `claude/nice-carson-pm8g56`) — **v0.503.8: a hung ffmpeg decoder can be cancelled and is killed after 5 silent minutes** (`iter_frames` `_DecodeWatchdog`, `VideoDecoderStalled`), the Scout's sweep (3) entry; fail-before shown through the real API. **START HERE NEXT RUN:** Builder: no ungated bug — beginner feature or dogfood (`--empty`, `--dithered --big`).*

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
