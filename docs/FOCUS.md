# Current focus — AstroStack

> **Short on purpose (AGENTS.md: "short, dated, the Scout keeps it current").** One dated line per run goes at the
> top of *Run log*; keep about the last ten and move older lines, whole and in order, to `docs/archive/`. Detail
> belongs in `docs/PROCESS-NOTES.md`, never here. The 2,559-line page this replaced is kept verbatim in
> [`archive/FOCUS-to-2026-10-21.md`](archive/FOCUS-to-2026-10-21.md) — nothing was deleted.

## Front of the queue (2026-10-22)

Every item below is an open entry at the end of "Bugs (fix these first)" in [`IMPROVEMENTS.md`](IMPROVEMENTS.md),
reproduced and **ungated** — a Builder can start any of them without the owner. Take them in this order:

1. 🟡 **Size M — on an uneven mosaic readiness ("Is it enough yet?") and Dashboard progress still quote the canvas
   mean as "a typical part"** — the planner (v0.502.29) and the closing-season card (v0.502.39,
   `perPixel.typicalPartFulls`) are done; serve `webapp.field_fulls.target_depth_fulls` on `TargetOut` and the
   progress roll-up and divide through `typicalPartFulls`.

**Gated, do not start:** the un-located-panel entry (top of Bugs) waits on the owner's hint-shape answer; the
other LEADs and ⚪ notes in Bugs wait on owner/observer measurements — read each one's gate first, and do not
re-litigate a stand-down that carries numbers. **Issue inbox:** #878, #880, #903, #1015 — all previously acted-on
and owner-gated, none updated since 2026-10-12 (re-checked 2026-10-22).

## QA rotation (Scout)

Order (AGENTS.md roles): (1) preview↔export parity at mosaic scale → (2) mosaic/walk-away per-panel divergence →
(3) ASTAP/ffmpeg filesystem side effects with a stub binary → (4) the webapp routers. **Last swept: (3), 2026-10-22
→ next sweep is (4).** Each (3) sweep must find a *new* angle — the list of angles already run is in the
`Sweep (3)` entries of `docs/PROCESS-NOTES.md` (grep `sweep (3)`).

## Run log (newest first)

*2026-10-23 (Builder, branch `claude/nice-carson-bo9fum`) — **v0.502.39: "Shoot these before they're gone" reads an uneven mosaic at its median pixel (55 → 13 min on the grown shape) and tie-breaks by the per-part noise cut** (`ClosingTarget.depth_fulls`, `perPixel.typicalPartFulls`). **START HERE NEXT RUN:** Builder: item 1 (readiness/progress half).*
*2026-10-22 (Builder, branch `claude/nice-carson-ront7e`) — **v0.502.38: the share caption, the baked nameplate (share, print, JPEG download) and the Sky map tile date a run by the subs' own `SITELONG` when Settings has no location** (`editor._observer_lon`, `submit_editor_share`/`submit_editor_print` `site_lon`, `resolve_site_lon`). **START HERE NEXT RUN:** Builder: item 1.*
*2026-10-22 (Scout, branch `claude/beautiful-newton-jbziyg`) — **QA rotation sweep (3), new angle: ffmpeg auto-rotates a rotation-tagged clip to h×w while the probe says w×h, so `iter_frames` reshaped every frame into streaks with no error — Scout-fixed v0.502.37 (`-noautorotate`).** Inbox: the same four, all owner-gated. Suite 8241 passed / 7 skipped. **START HERE NEXT RUN:** Builder: item 2 or 1. **Rotation: (3) done → next sweep is (4).***
*2026-10-22 (Builder, branch `claude/nice-carson-ywmwk2`) — **v0.502.36: a Moon & Sun capture stacked while still copying in warns ("Only the first N of … frames could be read") and its still is marked changed once the file completes** (`lucky.cut_short_warning`, `VideoStackMeta.source_size`, `VideoResultOut.source_changed`). **START HERE NEXT RUN:** Builder: item 2 or 1.*
*2026-10-22 (Builder, branch `claude/nice-carson-8a9f4w`) — **v0.502.35: the mixed-pointing guard keeps a gapped S30 strip one target — the link scales to 2 solved-field long sides** (`pointings.link_dist_for_field`, `mixedPointings.linkDistForField`, `FrameOut.pixscale_arcsec`). **START HERE NEXT RUN:** Builder: item 3 (Moon & Sun cut short), 2 or 1.*
*2026-10-22 (Builder, branch `claude/nice-carson-7gckm1`) — **v0.502.34: an uneven S30 strip keeps its far panel —
the plate-solve outlier floor scales with the solved footprint and a frame chained to the group is never an outlier**
(`mosaic._footprint_outlier_indices`, `OUTLIER_FLOOR_FOOTPRINTS`, `_chained_to_main_group`). **START HERE NEXT RUN:**
Builder: item 3 (the guard half), 4, 2 or 1.*
*2026-10-21 (Scout, branch `claude/zen-curie-t3nyff`) — **QA rotation sweep (2), new angle: `/compare`'s "it's the
cleaner stack" read the whole-canvas σ, so on a grown mosaic the older, half-size picture won ("B … 17% lower" at
identical depth on the shared sky) — Scout-fixed v0.502.33 (`Compare.noiseComparison` `widerSky`, the cover nudge's
`MIN_SKY_SHARE` 0.9).** Inbox: the same four, all owner-gated. Suite 8214 passed / 7 skipped; dogfood `--mosaic`
CLEAN. **START HERE NEXT RUN:** Builder: item 3 (S30 outlier floor), 4 or 1. **Rotation: (2) done → next sweep is (3).***
*2026-10-21 (Builder, branch `claude/festive-knuth-ykn52w`) — **v0.502.32: the "did it get better?" matched-crop picture carries its patch through both masters' WCS on a grown mosaic** (`noisedelta._sky_mapper`; same sky, same native box, σ ratio honest; unsolved different-shaped pair self-hides). **START HERE NEXT RUN:** Builder: item 3 (S30 outlier floor), 4 or 1.*
*2026-10-21 (Scout, branch `claude/zen-curie-66kbiz`) — **QA rotation sweep (1), new angle: the one-frame reveal on an
auto-edited mosaic cut the raw sub by the canvas's Auto trim fractions (480×320 → 298×320 on a missing-panel trim) —
Scout-fixed v0.502.31 (`routers/stack._render_sub_through_recipe` → `_without_saved_crop`).** Inbox: the same four,
all owner-gated. Suite 8207 passed / 7 skipped; dogfood `--mosaic --editor` CLEAN (trim 7.9 %). **START HERE NEXT
RUN:** Builder: item 4 (S30 outlier floor), 5 or 1. **Rotation: (1) done → next sweep is (2).***
*2026-10-21 (Scout, branch `claude/zen-curie-89ftgk`) — **QA rotation sweep (4), new angle: every GET route (165,
228 calls with real target/run/frame ids) crawled on the running `--mosaic` app, then again with the mosaic's
`output/` files gone under a live DB row — CLEAN (0 × 5xx both times; every 404/422 a deliberate "nothing yet").**
Inbox: the same four, all owner-gated. Suite 8206 passed / 7 skipped; dogfood `--mosaic` CLEAN (trim 7.9 %).
**START HERE NEXT RUN:** Builder: item 4 (S30 outlier floor), 5 or 1. **Rotation: (4) done → next sweep is (1).***

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
