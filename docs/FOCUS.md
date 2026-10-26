# Current focus — AstroStack

> **Short on purpose (AGENTS.md: "short, dated, the Scout keeps it current").** One dated line per run goes at the
> top of *Run log*; keep about the last ten and move older lines, whole and in order, to `docs/archive/`. Detail
> belongs in `docs/PROCESS-NOTES.md`, never here. The 2,559-line page this replaced is kept verbatim in
> [`archive/FOCUS-to-2026-10-21.md`](archive/FOCUS-to-2026-10-21.md) — nothing was deleted.

## Front of the queue (2026-10-25)

**No ungated bug is open.** Recently closed: the walk-away missing-files hold on a mosaic panel (v0.503.5); Compare's Split/Blink on a grown mosaic (v0.503.1); the Scout's 2026-10-21 per-part entry closed with v0.502.40 (readiness / Dashboard
progress / Tonight badge); a dogfood pass found and fixed the week plan's same-sky flip (v0.502.41); the Scout's sweep (4) fixed a merge that
deleted a folder a stack was still writing into (v0.502.42). After that, a Builder with nothing ungated should take a beginner feature from "Features that serve
real workflows" in [`IMPROVEMENTS.md`](IMPROVEMENTS.md), or dogfood (`--mosaic --editor`) and file what it finds.

**Gated, do not start:** the un-located-panel entry (second in Bugs) waits on the owner's hint-shape answer; the
other LEADs and ⚪ notes in Bugs wait on owner/observer measurements — read each one's gate first, and do not
re-litigate a stand-down that carries numbers. **Issue inbox:** #878, #880, #903, #1015 — all previously acted-on
and owner-gated, none updated since 2026-10-12 (re-checked 2026-10-25).

## QA rotation (Scout)

Order (AGENTS.md roles): (1) preview↔export parity at mosaic scale → (2) mosaic/walk-away per-panel divergence →
(3) ASTAP/ffmpeg filesystem side effects with a stub binary → (4) the webapp routers. **Last swept: (2), 2026-10-25
→ next sweep is (3).** Each (3) sweep must find a *new* angle — the list of angles already run is in the
`Sweep (3)` entries of `docs/PROCESS-NOTES.md` (grep `sweep (3)`).

## Run log (newest first)

*2026-10-26 (Builder, branch `claude/nice-carson-dmwzch`) — **v0.503.7: the thin-stack warning keeps "N located subs a restack would fold in" while a newer sub is unlocated, naming the "Process target" button** (`thinStackWarning` `remedy`), found by `--combine --calibration --editor`'s step 9; that pass otherwise CLEAN (§10 incoming/ unchanged). Baseline suite 8288 passed / 7 skipped. **START HERE NEXT RUN:** Builder: no ungated bug — beginner feature or dogfood (`--empty`, `--restack --mosaic`).*
*2026-10-26 (Builder, branch `claude/nice-carson-igexdq`) — **v0.503.6: Tonight's and "Plan my week"'s framing badge on a single field names the mosaic he already has** (`LibraryTarget.mosaic_companion`, `framingRowBadge`), found reading `--deep --mosaic --editor`; that pass otherwise CLEAN. Baseline suite 8283 passed / 7 skipped. **START HERE NEXT RUN:** Builder: no ungated bug — beginner feature or dogfood (`--combine --calibration`, `--empty`).*
*2026-10-25 (Builder, branch `claude/nice-carson-nryy30`) — **v0.503.5: the walk-away missing-files hold now holds a mosaic whose panel has no readable sub** (`pipeline._panels_with_nothing_readable`, `panels_missing`), the Scout's sweep (2) entry; fail-before shown. Baseline suite 8280 passed / 7 skipped. **START HERE NEXT RUN:** Builder: no ungated bug — beginner feature or dogfood (`--deep --mosaic`, `--combine --calibration`).*
*2026-10-25 (Scout, branch `claude/beautiful-newton-1bsiin`) — **QA rotation sweep (2), new angle: the walk-away missing-files hold (`_auto_stack_readability_hold`) judges a mosaic by whole-target count and median depth, so a panel with *no* readable subs is stacked away when a newer night's subs on the other panels make up the number; filed reproduced (top of Bugs).** Inbox: the same four, owner-gated. Dogfood `--mosaic` CLEAN (trim 7.9 %). **START HERE NEXT RUN:** Builder: that entry. **Rotation: (2) done → next sweep is (3).***
*2026-10-25 (Builder, branch `claude/nice-carson-hqy4xy`) — **v0.503.4: a folder whose every file is unreadable no longer mints an empty "0/0 frames" target** (`scanner._hold_back_unreadable_new_target`), found by `--incoming-lag --no-site --editor`; that pass and `--empty` otherwise CLEAN. Baseline suite 8275 passed / 7 skipped. **START HERE NEXT RUN:** Builder: no ungated bug — beginner feature or dogfood (`--deep --mosaic`, `--combine --calibration`).*
*2026-10-25 (Builder, branch `claude/nice-carson-9l2b0t`) — **v0.503.3: "Plan my week"'s closing note said "unlike the others here" while the headline's own target was leaving too** (`closingWeekNote`), found by `--dithered --closing --editor`; that pass otherwise CLEAN (trim 30.7 % vs recorded apron 30.3 %). **START HERE NEXT RUN:** Builder: no ungated bug — beginner feature or dogfood (`--empty`, `--incoming-lag --no-site`).*
*2026-10-25 (Builder, branch `claude/nice-carson-wur8iy`) — **v0.503.2: Channel combine's intro read "LRGB(colour from RGB…" — JSX dropped the line break after `</b>`** (`Combine.tsx`); a tree-wide grep for the same shape found no other. Dogfood `--calibration --big --editor` otherwise CLEAN (masters built and applied, 21 ops on field and full-size, trim 7 %). Suite 8275 passed / 7 skipped. **START HERE NEXT RUN:** Builder: no ungated bug — beginner feature or dogfood (`--empty`, `--dithered --closing`).*
*2026-10-24 (Builder, branch `claude/nice-carson-se97e8`) — **v0.503.1: Compare's Split and Blink line up two runs of a grown mosaic by sky** (`compareplace.place_a_on_b`, `GET …/compare-placement`, `SkyFrame`) — the Scout's repro measured at ≤ 1 screen px (was 94) in Chromium on the dogfood `--mosaic` pair; trims and North-up (baked or viewed) followed. Baseline suite 8268 passed / 7 skipped. **START HERE NEXT RUN:** Builder: no ungated bug — beginner feature or dogfood.*
*2026-10-24 (Scout, branch `claude/beautiful-newton-mkp0sh`) — **QA rotation sweep (1), new angle: `/compare`'s Split and Blink on a grown mosaic overlay two canvases by screen box, not by sky — the same star 94 px apart in the 640×420 box; filed reproduced (top of Bugs).** Inbox: the same four, all owner-gated. Suite 8262 passed / 7 skipped; dogfood `--mosaic` CLEAN (trim 7.9 %). **START HERE NEXT RUN:** Builder: the Compare Split/Blink entry. **Rotation: (1) done → next sweep is (2).***
*2026-10-24 (Builder, branch `claude/nice-carson-itbuxk`) — **v0.503.0: a single field's Target page names the mosaic of the same object he already has** instead of only prescribing "shoot it in mosaic mode" (`TargetOut.mosaic_companion`, `find_mosaic_companion`), found reading `--closing --incoming-lag --mosaic --editor`; that pass otherwise CLEAN. **START HERE NEXT RUN:** Builder: no ungated bug — beginner feature or dogfood (`--calibration --big`, `--dithered`).*

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
