# Current focus — AstroStack

> **Short on purpose (AGENTS.md: "short, dated, the Scout keeps it current").** One dated line per run goes at the
> top of *Run log*; keep about the last ten and move older lines, whole and in order, to `docs/archive/`. Detail
> belongs in `docs/PROCESS-NOTES.md`, never here. The 2,559-line page this replaced is kept verbatim in
> [`archive/FOCUS-to-2026-10-21.md`](archive/FOCUS-to-2026-10-21.md) — nothing was deleted.

## Front of the queue (2026-10-27)

**No ungated bug is open.** Recently closed: the hung ffmpeg decoder vs Cancel (v0.503.8); the walk-away missing-files hold on a mosaic panel (v0.503.5); Compare's Split/Blink on a grown mosaic (v0.503.1); the Scout's 2026-10-21 per-part entry closed with v0.502.40 (readiness / Dashboard
progress / Tonight badge); a dogfood pass found and fixed the week plan's same-sky flip (v0.502.41); the Scout's sweep (4) fixed a merge that
deleted a folder a stack was still writing into (v0.502.42). After that, a Builder with nothing ungated should take a beginner feature from "Features that serve
real workflows" in [`IMPROVEMENTS.md`](IMPROVEMENTS.md), or dogfood (`--mosaic --editor`) and file what it finds.

**Gated, do not start:** the un-located-panel entry (second in Bugs) waits on the owner's hint-shape answer; the
other LEADs and ⚪ notes in Bugs wait on owner/observer measurements — read each one's gate first, and do not
re-litigate a stand-down that carries numbers. **Issue inbox:** #878, #880, #903, #1015 — all previously acted-on
and owner-gated, none updated since 2026-10-12 (re-checked 2026-10-27).

## QA rotation (Scout)

Order (AGENTS.md roles): (1) preview↔export parity at mosaic scale → (2) mosaic/walk-away per-panel divergence →
(3) ASTAP/ffmpeg filesystem side effects with a stub binary → (4) the webapp routers. **Last swept: (4), 2026-10-27
→ next sweep is (1).** Each (3) sweep must find a *new* angle — the list of angles already run is in the
`Sweep (3)` entries of `docs/PROCESS-NOTES.md` (grep `sweep (3)`).

## Run log (newest first)

*2026-10-27 (Scout, branch `claude/beautiful-newton-aovpvx`) — **QA rotation sweep (4), the 2026-10-23 sweep's in-flight-job leads reproduced with a held real job: `DELETE /api/targets/{safe}` mid-stack and `DELETE …/stack-runs/{id}` mid-export both hold; `cache/clear` judged low-stakes (stage 2 unread by the stack, stage 1 empty with `copy_to_cache` off). CLEAN, nothing filed.** Inbox: the same four, owner-gated. Dogfood `--mosaic` CLEAN (trim 7.9 %). **START HERE NEXT RUN:** Builder: no ungated bug — beginner feature or dogfood (`--incoming-lag`, `--combine --calibration`). **Rotation: (4) done → next sweep is (1).***
*2026-10-27 (Builder, branch `claude/nice-carson-viz24y`) — **v0.503.9: Tonight's Night picker shows the night it plans instead of a blank `mm/dd/yyyy`** (`shownNightDate`), read off the screenshots of dogfood `--empty` then `--deep --closing --editor`; both passes otherwise CLEAN (all 21 ops, trim n/a single field, deep table 301→601 rows). **START HERE NEXT RUN:** Builder: no ungated bug — beginner feature or dogfood (`--incoming-lag`, `--combine --calibration`).*
*2026-10-27 (Builder, branch `claude/nice-carson-jxxq55`) — **Dogfood `--dithered --big --mosaic --editor` CLEAN; nothing shipped.** All four editor drives (field, 2×2, full-size, dithered) re-rendered all 21 ops; the full-size loupe followed the navigator; Auto trim 7.9 % / 7 % / 30.7 % (dithered apron 30.3 %); taste chips behaved; nothing overflowing, no console errors. Baseline suite 8296 passed / 7 skipped. **START HERE NEXT RUN:** Builder: no ungated bug — beginner feature or dogfood (`--empty`, `--deep --closing`).*
*2026-10-26 (Builder, branch `claude/nice-carson-pm8g56`) — **v0.503.8: a hung ffmpeg decoder can be cancelled and is killed after 5 silent minutes** (`iter_frames` `_DecodeWatchdog`, `VideoDecoderStalled`), the Scout's sweep (3) entry; fail-before shown through the real API. **START HERE NEXT RUN:** Builder: no ungated bug — beginner feature or dogfood (`--empty`, `--dithered --big`).*
*2026-10-26 (Scout, branch `claude/beautiful-newton-k4ixuv`) — **QA rotation sweep (3), new angle: a hung ffmpeg decoder (`ffmpeg.iter_frames`, no deadline) can't be cancelled and wedges the single job worker; filed reproduced (top of Bugs).** Inbox: the same four, owner-gated. Suite 8288 passed / 7 skipped; dogfood `--mosaic` CLEAN (trim 7.9 %). **START HERE NEXT RUN:** Builder: that entry. **Rotation: (3) done → next sweep is (4).***
*2026-10-26 (Builder, branch `claude/nice-carson-lejb4i`) — **Big-picture dogfood `--restack --mosaic --editor` CLEAN; nothing shipped.** Both editor drives (field + 2×2) re-rendered all 21 ops, Auto trim 7.9 %, taste chips behaved; restack reel/noise-delta available; nothing overflowing, no console errors; the Target, Dashboard and Tonight paragraphs agree. Baseline suite 8288 passed / 7 skipped. **START HERE NEXT RUN:** Builder: no ungated bug — beginner feature or dogfood (`--empty`, `--dithered --big`).*
*2026-10-26 (Builder, branch `claude/nice-carson-dmwzch`) — **v0.503.7: the thin-stack warning keeps "N located subs a restack would fold in" while a newer sub is unlocated, naming the "Process target" button** (`thinStackWarning` `remedy`), found by `--combine --calibration --editor`'s step 9; that pass otherwise CLEAN (§10 incoming/ unchanged). Baseline suite 8288 passed / 7 skipped. **START HERE NEXT RUN:** Builder: no ungated bug — beginner feature or dogfood (`--empty`, `--restack --mosaic`).*
*2026-10-26 (Builder, branch `claude/nice-carson-igexdq`) — **v0.503.6: Tonight's and "Plan my week"'s framing badge on a single field names the mosaic he already has** (`LibraryTarget.mosaic_companion`, `framingRowBadge`), found reading `--deep --mosaic --editor`; that pass otherwise CLEAN. Baseline suite 8283 passed / 7 skipped. **START HERE NEXT RUN:** Builder: no ungated bug — beginner feature or dogfood (`--combine --calibration`, `--empty`).*
*2026-10-25 (Builder, branch `claude/nice-carson-nryy30`) — **v0.503.5: the walk-away missing-files hold now holds a mosaic whose panel has no readable sub** (`pipeline._panels_with_nothing_readable`, `panels_missing`), the Scout's sweep (2) entry; fail-before shown. Baseline suite 8280 passed / 7 skipped. **START HERE NEXT RUN:** Builder: no ungated bug — beginner feature or dogfood (`--deep --mosaic`, `--combine --calibration`).*
*2026-10-25 (Scout, branch `claude/beautiful-newton-1bsiin`) — **QA rotation sweep (2), new angle: the walk-away missing-files hold (`_auto_stack_readability_hold`) judges a mosaic by whole-target count and median depth, so a panel with *no* readable subs is stacked away when a newer night's subs on the other panels make up the number; filed reproduced (top of Bugs).** Inbox: the same four, owner-gated. Dogfood `--mosaic` CLEAN (trim 7.9 %). **START HERE NEXT RUN:** Builder: that entry. **Rotation: (2) done → next sweep is (3).***

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
