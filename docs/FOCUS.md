# Current focus — AstroStack

> **Short on purpose (AGENTS.md: "short, dated, the Scout keeps it current").** One dated line per run goes at the
> top of *Run log*; keep about the last ten and move older lines, whole and in order, to `docs/archive/`. Detail
> belongs in `docs/PROCESS-NOTES.md`, never here. The 2,559-line page this replaced is kept verbatim in
> [`archive/FOCUS-to-2026-10-21.md`](archive/FOCUS-to-2026-10-21.md) — nothing was deleted.

## Front of the queue (2026-10-28)

**One ungated bug is open — the top of Bugs: an ASTAP that is present but cannot run is reported as "found" and
every sub as an ordinary solve failure** (sweep (3), reproduced, size S). Builder: take it first. Recently closed: an upload no longer replaces a sub that reached `incoming/` mid-stream (v0.503.17, Scout sweep (4)); a mosaic panel left a few readable subs vs the walk-away hold (v0.503.16); the deepening reel's shallow night drawn cleaner on a grown mosaic (v0.503.15); one night, one dark window (v0.503.10); the hung ffmpeg decoder vs Cancel (v0.503.8); the walk-away missing-files hold on a mosaic panel (v0.503.5); Compare's Split/Blink on a grown mosaic (v0.503.1); the Scout's 2026-10-21 per-part entry closed with v0.502.40 (readiness / Dashboard
progress / Tonight badge); a dogfood pass found and fixed the week plan's same-sky flip (v0.502.41); the Scout's sweep (4) fixed a merge that
deleted a folder a stack was still writing into (v0.502.42). After that, a Builder with nothing ungated should take a beginner feature from "Features that serve
real workflows" in [`IMPROVEMENTS.md`](IMPROVEMENTS.md), or dogfood (`--mosaic --editor`) and file what it finds.

**Gated, do not start:** the un-located-panel entry (fourth in Bugs) waits on the owner's hint-shape answer; the
other LEADs and ⚪ notes in Bugs wait on owner/observer measurements — read each one's gate first, and do not
re-litigate a stand-down that carries numbers. **Issue inbox:** #878, #880, #903, #1015 — all previously acted-on
and owner-gated, none updated since 2026-10-12 (re-checked 2026-10-28).

## QA rotation (Scout)

Order (AGENTS.md roles): (1) preview↔export parity at mosaic scale → (2) mosaic/walk-away per-panel divergence →
(3) ASTAP/ffmpeg filesystem side effects with a stub binary → (4) the webapp routers. **Last swept: (1), 2026-10-28
(after #1312's (4)) → next sweep is (2).** Each (3) sweep must find a *new* angle — the list of angles already run is in the
`Sweep (3)` entries of `docs/PROCESS-NOTES.md` (grep `sweep (3)`).

## Run log (newest first)

*2026-10-28 (Scout, branch `claude/blissful-einstein-dck0um`) — **QA rotation sweep (1), new angle: the legacy North-up recovery asked the master's WCS at the preview grid's centre, so a pre-v0.288 North-up save on a mosaic read as un-rotated (14 of 16 cases); Scout-fixed, v0.503.18** (`recovered_north_up_deg`). `noisedelta` held by reading. Inbox: the same four, owner-gated. Suite 8321 passed / 7 skipped; dogfood `--mosaic` CLEAN (trim 7.9 %). Ran beside #1312's sweep (4). **START HERE NEXT RUN:** Builder: the un-startable ASTAP entry (top of Bugs). **Rotation: (1) done → next sweep is (2).***
*2026-10-28 (Scout, branch `claude/blissful-einstein-ptp2yd`) — **QA rotation sweep (4), new angle: `upload`, the one router that writes into `incoming/`, against §10 — a sub landing at the same name *while* an upload streamed was silently replaced (`os.replace` after a pre-stream `exists()`); Scout-fixed as v0.503.17 (`_place_new`, create-only `os.link`).** Inbox: the same four, owner-gated. Suite 8318 passed / 7 skipped; dogfood `--mosaic` CLEAN (trim 7.9 %). **START HERE NEXT RUN:** Builder: the un-startable-ASTAP entry. **Rotation: (4) done → next sweep is (1).***
*2026-10-28 (Builder, branch `claude/pensive-hawking-3f01rd`) — **v0.503.15: the deepening reel's shallow night no longer reads cleaner on a grown/shrunk mosaic** (`render_deepening_frames` loads each night at the newest frame's sky scale, places it linear + nearest before the stretch; grown 26.1 → 49.3 vs deep 37.7); **v0.503.16: the walk-away hold also holds a mosaic panel keeping under half its subs** (`_panels_with_nothing_readable` `thinned`, additive `panels_thinned`). Suite 8315 passed / 7 skipped before the second. **START HERE NEXT RUN:** Builder: the un-startable ASTAP entry (now top of Bugs).*
*2026-10-28 (Scout, branch `claude/blissful-einstein-h93a4i`) — **QA rotation sweep (3), new angle: an ASTAP that is present but cannot be started (0644 / `noexec`, wrong-format binary) — no filesystem side effect, but it reads "ASTAP found" everywhere and every sub gets an exception string as an ordinary solve failure (`_run_astap` catches only `TimeoutExpired`; `classify_solve_setup_error` misses it); filed reproduced in Bugs.** Inbox: the same four, owner-gated. Suite 8313 passed / 7 skipped; dogfood `--mosaic` CLEAN (trim 7.9 %). **START HERE NEXT RUN:** Builder: the reel entry, the panel-hold entry, then this one. **Rotation: (3) done → next sweep is (4).***
*2026-10-28 (Scout, branch `claude/blissful-einstein-3560ux`) — **QA rotation sweep (2), new angle: v0.503.5's per-panel missing-files hold at a panel left with *a few* readable subs — a panel going 510 → 10 subs passes every gate (`_auto_stack_readability_hold`); filed reproduced in Bugs.** Inbox: the same four, owner-gated. Suite 8313 passed / 7 skipped; dogfood `--mosaic` CLEAN (trim 7.9 %). **START HERE NEXT RUN:** Builder: the reel entry, then this one. **Rotation: (2) done → next sweep is (3).***
*2026-10-28 (Builder, branch `claude/pensive-hawking-uy9mbo`) — **v0.503.14: the Dashboard's "~2 more nights" chip explains itself on tap/hover in the planner's own words** (`libraryProgress.nightsToGoHint`, `LibraryProgressCard` `HintAnchor`), the backlog's XS friendliness entry, taken with no ungated bug unclaimed. Suite 8313 passed / 7 skipped; vitest 4871. **START HERE NEXT RUN:** Builder: the Scout's deepening-reel entry (top of Bugs), else a beginner feature or dogfood (`--restack --dithered`, `--calibration --big`).*
*2026-10-28 (Scout, branch `claude/blissful-einstein-96mvmu`) — **QA rotation sweep (1), new angle: the deepening reel's placement on a canvas that grew or shrank (`render_deepening_frames` / `_place_on_sky`) — the shallow night renders cleaner and brighter than the deep one (σ 25.3 vs 37.7, sky 73 vs 51; single field 49.3 → 37.7); filed reproduced at the top of Bugs with a measured fix shape.** Inbox: the same four, owner-gated. Suite 8310 passed / 7 skipped; dogfood `--mosaic` CLEAN (trim 7.9 %). **START HERE NEXT RUN:** Builder: that entry. **Rotation: (1) done → next sweep is (2).***
*2026-10-28 (Builder, branch `claude/nice-carson-mxelbj`) — **Dogfood `--incoming-lag --big --mosaic --editor` CLEAN; v0.503.13: the legacy desktop Library dialog's "solved N/M" counts real solves (`_target_summary_line`, `solve_ok`).** All 21 ops on field, 2×2 and full size; trim 7.9 %; scale pair 0 of 16 moved. **START HERE NEXT RUN:** Builder: no ungated bug — beginner feature or dogfood (`--restack --dithered`, `--calibration --big`).*
*2026-10-28 (Builder, branch `claude/nice-carson-6l8p8e`) — **Dogfood `--empty`, then `--deep --closing --mosaic --editor`, CLEAN; nothing shipped.** All 21 ops re-rendered on field and 2×2, Auto trim 7.9 %, deep table grew 301→601 rows, no overflow, no console errors. The deep sample's "7×7 vs 3×3" panel count is a two-sized-fixture artefact (PROCESS-NOTES). **START HERE NEXT RUN:** Builder: no ungated bug — beginner feature or dogfood (`--incoming-lag --big`, `--restack --dithered`).*
*2026-10-28 (Builder, branch `claude/nice-carson-rgalhh`) — **v0.503.12: an unstacked mosaic target is no longer badged "Needs 3×3 mosaic" about itself on Plan my week / Tonight** (`canvas_is_mosaic` honours `is_mosaic_target_name`), read off `--combine --calibration --editor --dithered`'s Tonight paragraph; that pass otherwise CLEAN (all ops re-rendered, no overflow, no console errors). Suite 8310 passed / 7 skipped. **START HERE NEXT RUN:** Builder: no ungated bug — beginner feature or dogfood (`--empty`, `--deep --closing --mosaic`).*

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
