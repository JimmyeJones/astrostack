# Current focus — AstroStack

> **Short on purpose (AGENTS.md: "short, dated, the Scout keeps it current").** One dated line per run goes at the
> top of *Run log*; keep about the last ten and move older lines, whole and in order, to `docs/archive/`. Detail
> belongs in `docs/PROCESS-NOTES.md`, never here. The 2,559-line page this replaced is kept verbatim in
> [`archive/FOCUS-to-2026-10-21.md`](archive/FOCUS-to-2026-10-21.md) — nothing was deleted.

## Front of the queue (2026-10-21)

Every item below is an open entry at the end of "Bugs (fix these first)" in [`IMPROVEMENTS.md`](IMPROVEMENTS.md),
reproduced and **ungated** — a Builder can start any of them without the owner. Take them in this order:

1. 🟠 **Editor, size S — "Check it at full size" on a recipe with no Stretch op re-stretches each loupe window by its
   own sky** (`pipeline.apply_recipe` fallback `autostretch`, `routers/editor._render_loupe_png`). PRIORITY 1.
2. 🟡 **Size S (planner) / M (every surface) — on an uneven mosaic the planner's "about N on a typical part" and
   "another hour cuts its noise X %" are the canvas mean** (`nightplan._have_phrase`, `field_fulls.target_field_fulls`);
   fix through each run's `coverage_median_depth`.
3. 🟡 **Size M — the "did it get better?" matched-crop picture maps its crop by canvas fraction on a grown mosaic**
   (`noisedelta.build_noise_delta`); place by both masters' WCS (`wcs_io.crop_reprojected_between_fits`), as
   v0.502.23/.24 did for the reel and the previous-edit crop.

**Gated, do not start:** the un-located-panel entry (top of Bugs) waits on the owner's hint-shape answer; the
other LEADs and ⚪ notes in Bugs wait on owner/observer measurements — read each one's gate first, and do not
re-litigate a stand-down that carries numbers. **Issue inbox:** #878, #880, #903, #1015 — all previously acted-on
and owner-gated, none updated since 2026-10-12.

## QA rotation (Scout)

Order (AGENTS.md roles): (1) preview↔export parity at mosaic scale → (2) mosaic/walk-away per-panel divergence →
(3) ASTAP/ffmpeg filesystem side effects with a stub binary → (4) the webapp routers. **Last swept: (3), 2026-10-21
→ next sweep is (4).** Each (3) sweep must find a *new* angle — the list of angles already run is in the
`Sweep (3)` entries of `docs/PROCESS-NOTES.md` (grep `sweep (3)`).

## Run log (newest first)

*2026-10-21 (Scout, branch `claude/zen-curie-g7aybm`) — **QA rotation sweep (3), new angle: the whole app run as an
unprivileged account against a read-only `incoming/` (dirs 0555, files 0444, owned by another account), with a
hostile stub ASTAP and real ffmpeg — scan → QC/solve → stack → re-solve → rescue → editor Auto/export/share →
master dark and flat builds from `incoming/` → Moon & Sun grade and stack: CLEAN** (`incoming/` byte-, mtime-,
mode- and owner-identical; zero permission errors, so nothing even *attempted* a write there). Inbox: the same
four, all owner-gated. Suite 8193 passed / 7 skipped; dogfood `--mosaic` CLEAN (trim 7.9 %). FOCUS.md rewritten short (old page archived whole). **START HERE NEXT RUN:** Builder: item 1
above. **Rotation: (3) done → next sweep is (4).***
*2026-10-21 (Scout, branch `claude/zen-curie-faezje`) — QA rotation sweep (2): the planner's per-panel depth is the
canvas mean on an uneven mosaic — filed reproduced (item 2 above). Suite 8182 passed / 7 skipped; dogfood
`--mosaic` CLEAN (trim 7.9 %).*
*2026-10-21 (Builder, branch `claude/festive-knuth-zbfod0`) — v0.502.25: "Disable" access control removes the
read-only token (`routers/auth.set_password`); v0.502.26: Moon & Sun lists every per-night `Lunar_video` folder
(`video.discover.find_video_captures`, `_bare_id_holder`).*
*2026-10-21 (Scout, branch `claude/zen-curie-ae6xhx`) — QA rotation sweep (1): the full-size loupe re-stretches a
no-Stretch recipe's window by its own sky — filed reproduced (item 1 above).*

## Standing frontier

- **Mosaic-scale and walk-away behaviour is the open frontier**, not the single-field engine core. Do NOT re-sweep
  `seestack/stack` or `seestack/calibrate` until a new bug is found there (AGENTS.md).
- **Grown-canvas rule:** anything that puts one run's look, crop or picture onto another run's canvas places it by
  both masters' WCS and falls back (or hides itself) without one — v0.502.23 (reel) and v0.502.24 (previous-edit
  crop) are the pattern; item 3 above is the last known surface.

## How the owner gets builds now

He deploys with `sudo bash scripts/deploy.sh` from the **`stable`** branch (advanced by `.github/workflows/stable.yml`
to the newest `main` commit ≥ 3 days old with green CI) or from a release tag. So a fix reaches him days after it
merges — ship the follow-up to your own change *before* that soak ends.
