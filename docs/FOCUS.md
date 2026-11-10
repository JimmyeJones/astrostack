# Current focus — AstroStack

> **Short on purpose (AGENTS.md: "short, dated, the Scout keeps it current").** One dated line per run goes at the
> top of *Run log*; keep about the last ten and move older lines, whole and in order, to `docs/archive/`. Detail
> belongs in `docs/PROCESS-NOTES.md`, never here. The 2,559-line page this replaced is kept verbatim in
> [`archive/FOCUS-to-2026-10-21.md`](archive/FOCUS-to-2026-10-21.md) — nothing was deleted.

## Front of the queue (2026-11-09)

**Nothing ungated is open in Bugs** (the double-queued Process/Restack bug shipped as v0.505.37). A Builder should
dogfood (`--mosaic --editor`) and file what it finds. The `._*.fit` sidecar half of the Scout
2026-11-03 entry shipped as v0.505.10; its `.recycle/` / `.Trash-*/` / visible `.zfs/` half (one skip) waits on the
owner. The owner's ⭐ colour-pattern entry is on HOLD for his per-temperature numbers; the dark ring waits on a
diagnostic (below). Recent closures (v0.505.9 → v0.505.36, the Jobs-page read-back series among them) are in
the run log below and `SHIPPED.md`.

**Gated, do not start:** the un-located-panel entry (second in Bugs) waits on diagnostic `mosaic_panel_hints` v1
(v0.506.6), the dark ring on `sky_falloff` v2 (v0.506.9) and the #878 headline LEAD on `twin_target_overcount` v1 (v0.506.8); the
other LEADs and ⚪ notes in Bugs wait on owner/observer measurements — read each one's gate first, and do not
re-litigate a stand-down that carries numbers. **Issue inbox:** #878, #880, #903, #1015 — all previously acted-on
and owner-gated, none updated since 2026-10-12 (re-checked 2026-11-09). No `Diagnostic result:` issue has landed yet
(the diagnostics shipped in v0.506.0 / v0.506.1 run after the owner's next update).

## QA rotation (Scout)

Order (AGENTS.md roles): (1) preview↔export parity at mosaic scale → (2) mosaic/walk-away per-panel divergence →
(3) ASTAP/ffmpeg filesystem side effects with a stub binary → (4) the webapp routers. **Last swept: (1), 2026-11-09
→ next sweep is (2).** Each (3) sweep must find a *new* angle — the list of angles already run is in the
`Sweep (3)` entries of `docs/PROCESS-NOTES.md` (grep `sweep (3)`).

## Run log (newest first)

*2026-11-10 (Builder, branch `claude/fervent-allen-tvk8gv`) — **v0.506.9: diagnostic `sky_falloff` v2 takes its edge/centre slope only between subs of the same target** (`_pair_slope`). v1 (not yet on `stable`) fitted one line through every target, so a central nebula read as vignetting: a vignette-free synthetic library with an object on every target read 0.83–0.90, under the dark-ring entry's 0.97 threshold; v2 reads 1.000 / 0.897 (truth 0.90). Suite 8676 passed / 7 skipped. **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate or a diagnostic result arrives — the other not-yet-on-`stable` diagnostics (`mosaic_panel_hints` v1, `twin_target_overcount` v1) were read this run and look sound; Scout: sweep (2), and file `Diagnostic result:` issues when they land.*
*2026-11-10 (Builder, branch `claude/fervent-allen-pbc70q`) — **v0.506.8: fifth library diagnostic `twin_target_overcount` v1** (`seestack.diag.twin_overcount`): the registry sums the Dashboard headline shows against every sub counted once by source file — the gate on the #878 `/api/stats` headline LEAD, the last Bugs gate phrased "the observer can read both" that fits the record alone. Dogfood `--mosaic --deep --no-site --restack --big --editor` CLEAN (Auto trim 7.9 %; all 21 ops re-render, Undo/Redo apply, taste chips behave; scale diff 0 of 16 moved). Suite 8664 passed / 7 skipped before the change. **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate or a diagnostic result arrives; Scout: sweep (2), and file `Diagnostic result:` issues when they land.*
*2026-11-10 (Builder, branch `claude/fervent-allen-brcbxl`) — **two new library diagnostics answer the two Bugs gates that were waiting on the observer: v0.506.6 `mosaic_panel_hints` v1** (does a sub's pointing hint name its panel or the mosaic's centre — `seestack.diag.mosaic_hints`) **and v0.506.7 `sky_falloff` v1** (the S30's centre-to-edge sky fall-off with the pedestal taken out — `seestack.diag.sky_falloff`). Suite 8664 passed / 7 skipped. **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate or a diagnostic result arrives; Scout: sweep (2), and file `Diagnostic result:` issues when they land.*
*2026-11-10 (Builder, branch `claude/fervent-allen-5hddau`) — **v0.506.5: the two library diagnostics survey the library as four-column `SubRef`s instead of whole `FrameRow`s** (`seestack.diag.iter_sub_refs`); `sensor_pattern_by_temperature`'s peak on a 29,000-sub synthetic library 114.5 MB → 9.5 MB, identical results, no version bump — it lands before v2 reaches `stable`. **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate or a diagnostic result arrives; Scout: sweep (2).*
*2026-11-09 (Builder, branch `claude/fervent-allen-13mekw`) — **no app change: nothing ungated; dogfood `--mosaic --restack --calibration --no-site --editor` CLEAN** (a combination no pass had run together: the calibrated restack 3 → 6 subs applies both masters and the calibration note withdraws; mosaic notes agree on the thin top-right panel; Auto trim 7.9 %; all 21 ops re-render, Undo/Redo apply, taste chips behave). The Scout's two unswept (1) leads — the year recap hero and a pinned cover saved North-up later — read clean: both resolve through `current_picture_path`, and a North-up save rewrites the pinned run's own `preview_path`. Suite 8638 passed / 7 skipped. **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate or a diagnostic result arrives; Scout: sweep (2).*
*2026-11-09 (Builder, branch `claude/fervent-allen-3qy836`) — **no app change: nothing ungated; dogfood `--mosaic --incoming-lag --no-site --editor` CLEAN** (the two flags no pass had run since 2026-10-21: the Dashboard's incoming-lag note reads 8 waiting / 11 days with its unreadable-file count; `/tonight` renders its no-site alert; mosaic Target page's next-best-move, readiness and framing notes point the same way; Auto trim 7.9 %; all 21 ops re-render, Undo/Redo apply, taste chips behave). Suite 8638 passed / 7 skipped. **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate or a diagnostic result arrives; Scout: sweep (2).*
*2026-11-09 (Builder, branch `claude/fervent-allen-j5xv2c`) — **v0.506.4: diagnostic `filter_card_values` v2 reads each sampled night at its first and last sub, with nights spread over the whole history** (`filter_card._sample`). v1 read one sub per night from the oldest nights only, so its within-night check could only say 0 and a card that only newer firmware writes was invisible; the LP-filter idea now waits on v2. **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate or a diagnostic result arrives; Scout: sweep (2).*
*2026-11-09 (Builder, branch `claude/fervent-allen-w38x6w`) — **v0.506.3: diagnostic `sensor_pattern_by_temperature` v2 splits its halves by *sky*, not by target** (`sky_groups`: a mosaic and its single field, or centres within 5°, are one sky). v1 — not yet on `stable` — read a nebula a field and its mosaic share as repeat_r 0.992 / ratio 15, a camera pattern that is not there; the ⭐ colour-pattern hold now waits on v2. **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate or a diagnostic result arrives; Scout: sweep (2).*
*2026-11-09 (Scout, branch `claude/exciting-wozniak-xxwm76`) — **QA rotation sweep (1), new angle: the deep-sky wall (`/api/gallery/montage.jpg`) and the recap poster (`/api/recap.jpg`) fed a North-up-turned run on a mosaic-size canvas — CLEAN** (both read the stored turned bytes through `current_picture_path`, as the Gallery does). Inbox: the same four, owner-gated. Dogfood `--mosaic` CLEAN. Suite 8631 passed / 7 skipped. **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate or a diagnostic result arrives; Scout: sweep (2).*
*2026-11-09 (Builder, branch `claude/fervent-allen-hnqmz2`) — **v0.506.2: the boot-time `diagnostics` job reads back on the Jobs page (`Jobs.diagnosticsSummary`) and a cancelled one reads *cancelled*, not *done*** (v0.506.0's body returned a truthy `{"ran": []}` with no sentinel). Dogfood `--empty` CLEAN. **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate or a diagnostic result arrives; Scout: sweep (1).*

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
