# Current focus — AstroStack

> **Short on purpose (AGENTS.md: "short, dated, the Scout keeps it current").** One dated line per run goes at the
> top of *Run log*; keep about the last ten and move older lines, whole and in order, to `docs/archive/`. Detail
> belongs in `docs/PROCESS-NOTES.md`, never here. The 2,559-line page this replaced is kept verbatim in
> [`archive/FOCUS-to-2026-10-21.md`](archive/FOCUS-to-2026-10-21.md) — nothing was deleted.

## Front of the queue (2026-10-23)

**No ungated bug is open.** The Scout's 2026-10-21 per-part entry closed with v0.502.40 (readiness / Dashboard
progress / Tonight badge); a dogfood pass found and fixed the week plan's same-sky flip (v0.502.41); the Scout's sweep (4) fixed a merge that
deleted a folder a stack was still writing into (v0.502.42). A Builder with nothing ungated should take a beginner feature from "Features that serve
real workflows" in [`IMPROVEMENTS.md`](IMPROVEMENTS.md), or dogfood (`--mosaic --editor`) and file what it finds.

**Gated, do not start:** the un-located-panel entry (top of Bugs) waits on the owner's hint-shape answer; the
other LEADs and ⚪ notes in Bugs wait on owner/observer measurements — read each one's gate first, and do not
re-litigate a stand-down that carries numbers. **Issue inbox:** #878, #880, #903, #1015 — all previously acted-on
and owner-gated, none updated since 2026-10-12 (re-checked 2026-10-23).

## QA rotation (Scout)

Order (AGENTS.md roles): (1) preview↔export parity at mosaic scale → (2) mosaic/walk-away per-panel divergence →
(3) ASTAP/ffmpeg filesystem side effects with a stub binary → (4) the webapp routers. **Last swept: (4), 2026-10-23
→ next sweep is (1).** Each (3) sweep must find a *new* angle — the list of angles already run is in the
`Sweep (3)` entries of `docs/PROCESS-NOTES.md` (grep `sweep (3)`).

## Run log (newest first)

*2026-10-23 (Builder, branch `claude/nice-carson-unkvbg`) — **No ungated bug, no open beginner feature: two big-picture dogfood passes, both CLEAN, nothing shipped.** `--mosaic --dithered --editor --restack` and `--mosaic --big --editor` — all 21 ops re-render on the field, the 2×2, the dithered and the full-size runs; full-size check, navigator and Noise-reduction caveat behave; 0 of 16 scale-pair answers moved; trims 8 % (2×2) / 30.7 % (dithered, recorded apron 30.3 %). Suite 8259 passed / 7 skipped. **START HERE NEXT RUN:** Builder: no ungated bug — the Scout's unfiled (4) leads (cache clear / run prune under a running job) were traced and look low-stakes (see `docs/PROCESS-NOTES.md`); otherwise dogfood a flag not run lately (`--calibration`, `--deep`, `--combine`).*
*2026-10-23 (Scout, branch `claude/beautiful-newton-v9b2h7`) — **QA rotation sweep (4), new angle: mutating routes vs an in-flight job — `POST /api/targets/merge` rmtree'd a source a stack was still writing into (job "done", picture orphaned); Scout-fixed v0.502.42 (409 while a source is busy).** Leads for the next (4): cache clear / run delete under a running job (`docs/PROCESS-NOTES.md`). Inbox: the same four, owner-gated. **Rotation: (4) done → next sweep is (1).***
*2026-10-23 (Builder, branch `claude/nice-carson-ojgjii`) — **v0.502.41: "Plan my week" names one twin of a same-sky pair every night — the dogfood `--mosaic` library's single field and 2×2 mosaic of M42 swapped on a 0.1-point score wobble (six rows mosaic, Thursday the field, headline following the odd one out, with a "Needs 3×3 mosaic" badge on it)** (`plan_week` → `_same_sky_pick`, `WEEK_SAME_SKY_DEG`, `WEEK_SAME_SKY_SCORE_TOLERANCE`). Dogfood `--mosaic --editor` otherwise CLEAN. **START HERE NEXT RUN:** Builder: no ungated bug — beginner feature or dogfood.*
*2026-10-23 (Builder, branch `claude/nice-carson-gzxsm8`) — **v0.502.40: "Is it enough yet?", Dashboard progress, the Tonight row badge and the "keep going tonight" pick price an uneven mosaic's goal at its median pixel** (`depth_fulls` on `TargetOut`/`TargetProgressOut`/`PlannedTarget`, `integrationReadiness` → `typicalPartFulls`). **START HERE NEXT RUN:** Builder: no ungated bug — beginner feature or dogfood.*
*2026-10-23 (Builder, branch `claude/nice-carson-bo9fum`) — **v0.502.39: "Shoot these before they're gone" reads an uneven mosaic at its median pixel (55 → 13 min on the grown shape) and tie-breaks by the per-part noise cut** (`ClosingTarget.depth_fulls`, `perPixel.typicalPartFulls`). **START HERE NEXT RUN:** Builder: item 1 (readiness/progress half).*
*2026-10-22 (Builder, branch `claude/nice-carson-ront7e`) — **v0.502.38: the share caption, the baked nameplate (share, print, JPEG download) and the Sky map tile date a run by the subs' own `SITELONG` when Settings has no location** (`editor._observer_lon`, `submit_editor_share`/`submit_editor_print` `site_lon`, `resolve_site_lon`). **START HERE NEXT RUN:** Builder: item 1.*
*2026-10-22 (Scout, branch `claude/beautiful-newton-jbziyg`) — **QA rotation sweep (3), new angle: ffmpeg auto-rotates a rotation-tagged clip to h×w while the probe says w×h, so `iter_frames` reshaped every frame into streaks with no error — Scout-fixed v0.502.37 (`-noautorotate`).** Inbox: the same four, all owner-gated. Suite 8241 passed / 7 skipped. **START HERE NEXT RUN:** Builder: item 2 or 1. **Rotation: (3) done → next sweep is (4).***
*2026-10-22 (Builder, branch `claude/nice-carson-ywmwk2`) — **v0.502.36: a Moon & Sun capture stacked while still copying in warns ("Only the first N of … frames could be read") and its still is marked changed once the file completes** (`lucky.cut_short_warning`, `VideoStackMeta.source_size`, `VideoResultOut.source_changed`). **START HERE NEXT RUN:** Builder: item 2 or 1.*
*2026-10-22 (Builder, branch `claude/nice-carson-8a9f4w`) — **v0.502.35: the mixed-pointing guard keeps a gapped S30 strip one target — the link scales to 2 solved-field long sides** (`pointings.link_dist_for_field`, `mixedPointings.linkDistForField`, `FrameOut.pixscale_arcsec`). **START HERE NEXT RUN:** Builder: item 3 (Moon & Sun cut short), 2 or 1.*
*2026-10-22 (Builder, branch `claude/nice-carson-7gckm1`) — **v0.502.34: an uneven S30 strip keeps its far panel —
the plate-solve outlier floor scales with the solved footprint and a frame chained to the group is never an outlier**
(`mosaic._footprint_outlier_indices`, `OUTLIER_FLOOR_FOOTPRINTS`, `_chained_to_main_group`). **START HERE NEXT RUN:**
Builder: item 3 (the guard half), 4, 2 or 1.*

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
