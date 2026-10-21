# Current focus — AstroStack

> **Short on purpose (AGENTS.md: "short, dated, the Scout keeps it current").** One dated line per run goes at the
> top of *Run log*; keep about the last ten and move older lines, whole and in order, to `docs/archive/`. Detail
> belongs in `docs/PROCESS-NOTES.md`, never here. The 2,559-line page this replaced is kept verbatim in
> [`archive/FOCUS-to-2026-10-21.md`](archive/FOCUS-to-2026-10-21.md) — nothing was deleted.

## Front of the queue (2026-10-21)

Every item below is an open entry at the end of "Bugs (fix these first)" in [`IMPROVEMENTS.md`](IMPROVEMENTS.md),
reproduced and **ungated** — a Builder can start any of them without the owner. Take them in this order:

1. 🟡 **Size S (planner) / M (every surface) — on an uneven mosaic the planner's "about N on a typical part" and
   "another hour cuts its noise X %" are the canvas mean** (`nightplan._have_phrase`, `field_fulls.target_field_fulls`);
   fix through each run's `coverage_median_depth`.
2. 🟡 **Size M — the "did it get better?" matched-crop picture maps its crop by canvas fraction on a grown mosaic**
   (`noisedelta.build_noise_delta`); place by both masters' WCS (`wcs_io.crop_reprojected_between_fits`), as
   v0.502.23/.24 did for the reel and the previous-edit crop.

3. 🟡 **Size S — the share/print nameplate and the share caption date a run UTC noon-to-noon when Settings has no
   location** (`pipeline._nameplate_fields`, `capture_night_range`); resolve the longitude the way
   `resolve_site_lon` does (v0.502.28 fixed the sky-brightness card the same way).
4. 🟡 **Size S (editor, priority 1) — a saved look (my default / my presets) replays its crop's canvas fractions on
   every other picture, and the Gallery batch writes them** (`batch_apply`, `applyDefaultRecipe`); drop the crop
   when a saved look is applied.

**Gated, do not start:** the un-located-panel entry (top of Bugs) waits on the owner's hint-shape answer; the
other LEADs and ⚪ notes in Bugs wait on owner/observer measurements — read each one's gate first, and do not
re-litigate a stand-down that carries numbers. **Issue inbox:** #878, #880, #903, #1015 — all previously acted-on
and owner-gated, none updated since 2026-10-12.

## QA rotation (Scout)

Order (AGENTS.md roles): (1) preview↔export parity at mosaic scale → (2) mosaic/walk-away per-panel divergence →
(3) ASTAP/ffmpeg filesystem side effects with a stub binary → (4) the webapp routers. **Last swept: (1), 2026-10-21
→ next sweep is (2).** Each (3) sweep must find a *new* angle — the list of angles already run is in the
`Sweep (3)` entries of `docs/PROCESS-NOTES.md` (grep `sweep (3)`).

## Run log (newest first)

*2026-10-21 (Scout, branch `claude/zen-curie-n1e74f`) — **QA rotation sweep (1), the angle the `j1f6lp` (1) left
open: a saved look's `geometry.crop` is replayed by canvas fraction on other pictures — the batch cut a 100×80 run
to 70×62; filed reproduced (item 4).** Inbox: the same four, all owner-gated. **START HERE NEXT RUN:** Builder:
item 4 (editor, priority 1) or item 1. **Rotation: (1) done → next sweep is (2).***
*2026-10-21 (Scout, branch `claude/zen-curie-d8yo4f`) — **QA rotation sweep (4): the sky-brightness card bucketed
nights UTC noon-to-noon when Settings has no location, so a far-from-Greenwich session's dawn hour became a "much
brighter" night of its own — Scout-fixed v0.502.28 (`frames.sky_brightness_read` → `resolve_site_lon`)**; the
share/nameplate sibling filed (item 3). Inbox: the same four, all owner-gated. Suite 8196 passed / 7 skipped; dogfood
`--mosaic` CLEAN (trim 7.9 %). **START HERE NEXT RUN:** Builder: item 1. **Rotation: (4) done → next sweep is (1).***
*2026-10-21 (Builder, branch `claude/festive-knuth-ku8muu`) — **v0.502.27: "Check it at full size" on a recipe
with no Stretch op shows the picture's own curve — the fallback stretch's stats go through `ctx.fit`
(`pipeline.apply_recipe`, `FALLBACK_STRETCH_UID`); preview/export byte-identical.** **START HERE NEXT RUN:** Builder:
item 1 above (planner depth).*
*2026-10-21 (Scout, branch `claude/zen-curie-g7aybm`) — **QA rotation sweep (3), new angle: the whole app run as an
unprivileged account against a read-only `incoming/` (dirs 0555, files 0444, owned by another account), with a
hostile stub ASTAP and real ffmpeg — scan → QC/solve → stack → re-solve → rescue → editor Auto/export/share →
master dark and flat builds from `incoming/` → Moon & Sun grade and stack: CLEAN** (`incoming/` byte-, mtime-,
mode- and owner-identical; zero permission errors, so nothing even *attempted* a write there). Inbox: the same
four, all owner-gated. Suite 8193 passed / 7 skipped; dogfood `--mosaic` CLEAN (trim 7.9 %). FOCUS.md rewritten short (old page archived whole). **START HERE NEXT RUN:** Builder: the loupe
item (shipped v0.502.27). **Rotation: (3) done → next sweep is (4).***
*2026-10-21 (Scout, branch `claude/zen-curie-faezje`) — QA rotation sweep (2): the planner's per-panel depth is the
canvas mean on an uneven mosaic — filed reproduced (now item 1 above). Suite 8182 passed / 7 skipped; dogfood
`--mosaic` CLEAN (trim 7.9 %).*
*2026-10-21 (Builder, branch `claude/festive-knuth-zbfod0`) — v0.502.25: "Disable" access control removes the
read-only token (`routers/auth.set_password`); v0.502.26: Moon & Sun lists every per-night `Lunar_video` folder
(`video.discover.find_video_captures`, `_bare_id_holder`).*
*2026-10-21 (Scout, branch `claude/zen-curie-ae6xhx`) — QA rotation sweep (1): the full-size loupe re-stretches a
no-Stretch recipe's window by its own sky — filed reproduced (shipped v0.502.27).*

## Standing frontier

- **Mosaic-scale and walk-away behaviour is the open frontier**, not the single-field engine core. Do NOT re-sweep
  `seestack/stack` or `seestack/calibrate` until a new bug is found there (AGENTS.md).
- **Grown-canvas rule:** anything that puts one run's look, crop or picture onto another run's canvas places it by
  both masters' WCS and falls back (or hides itself) without one — v0.502.23 (reel) and v0.502.24 (previous-edit
  crop) are the pattern; item 2 above is the last known surface.

## How the owner gets builds now

He deploys with `sudo bash scripts/deploy.sh` from the **`stable`** branch (advanced by `.github/workflows/stable.yml`
to the newest `main` commit ≥ 3 days old with green CI) or from a release tag. So a fix reaches him days after it
merges — ship the follow-up to your own change *before* that soak ends.
