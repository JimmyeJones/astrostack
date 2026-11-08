# Current focus — AstroStack

> **Short on purpose (AGENTS.md: "short, dated, the Scout keeps it current").** One dated line per run goes at the
> top of *Run log*; keep about the last ten and move older lines, whole and in order, to `docs/archive/`. Detail
> belongs in `docs/PROCESS-NOTES.md`, never here. The 2,559-line page this replaced is kept verbatim in
> [`archive/FOCUS-to-2026-10-21.md`](archive/FOCUS-to-2026-10-21.md) — nothing was deleted.

## Front of the queue (2026-11-08)

**One ungated bug is open — take it:** a second click on "Process target" / "Restack" queues a second identical
whole-target stack (`routers/pipeline.trigger_process_target` has no active-job check; the Target page's buttons are
only busy for the POST's milliseconds). Filed reproduced by the 2026-11-08 Scout, size S, fix sketch in Bugs. After
that, a Builder should dogfood (`--mosaic --editor`) and file what it finds. The `._*.fit` sidecar half of the Scout
2026-11-03 entry shipped as v0.505.10; its `.recycle/` / `.Trash-*/` / visible `.zfs/` half (one skip) waits on the
owner. The owner's ⭐ colour-pattern entry is on HOLD for his per-temperature numbers; the dark ring waits on the
S30's measured vignette. Recent closures (v0.505.9 → v0.505.35, the Jobs-page read-back series among them) are in
the run log below and `SHIPPED.md`.

**Gated, do not start:** the un-located-panel entry (second in Bugs) waits on the owner's hint-shape answer; the
other LEADs and ⚪ notes in Bugs wait on owner/observer measurements — read each one's gate first, and do not
re-litigate a stand-down that carries numbers. **Issue inbox:** #878, #880, #903, #1015 — all previously acted-on
and owner-gated, none updated since 2026-10-12 (re-checked 2026-11-08).

## QA rotation (Scout)

Order (AGENTS.md roles): (1) preview↔export parity at mosaic scale → (2) mosaic/walk-away per-panel divergence →
(3) ASTAP/ffmpeg filesystem side effects with a stub binary → (4) the webapp routers. **Last swept: (4), 2026-11-08
→ next sweep is (1).** Each (3) sweep must find a *new* angle — the list of angles already run is in the
`Sweep (3)` entries of `docs/PROCESS-NOTES.md` (grep `sweep (3)`).

## Run log (newest first)

*2026-11-08 (Scout, branch `claude/exciting-wozniak-nk09s6`) — **QA rotation sweep (4), new angle: a repeated POST on the job-submitting routes — one bug filed reproduced** (two `POST /api/targets/{safe}/process` queue two identical whole-target stacks; the Target page's Process/Restack buttons are busy only for the POST). Inbox: the same four, owner-gated. Dogfood `--mosaic` CLEAN. **START HERE NEXT RUN:** Builder: the double-process bug in Bugs (S, ungated); Scout: sweep (1).*
*2026-11-08 (Builder, branch `claude/fervent-allen-6wn2di`) — **v0.505.35: clicking the opt-in "your job finished" desktop ping brings AstroStack forward on the Jobs page** (`jobNotify.showJobNotification` built the `Notification` with no `onclick`; `GlobalJobNotifier` now navigates to `/jobs`). Dogfood `--closing --calibration --incoming-lag` CLEAN. Suite 8595 passed / 7 skipped; vitest 4993 passed. **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate is answered; Scout: sweep (4) with a new angle.*
*2026-11-08 (Builder, branch `claude/fervent-allen-dmh6fb`) — **v0.505.34: the boot-time border-trim job reads back on the Jobs page** (`unedited_preview_trim` was the last submitted kind besides the deprioritised `channel_combine` with no `Jobs.JobResultActions` branch; new `previewTrimSummary`). Suite 8595 passed / 7 skipped; vitest 4990 passed. **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate is answered; Scout: sweep (4) with a new angle.*
*2026-11-08 (Builder, branch `claude/fervent-allen-po1pe4`) — **v0.505.33: a finished Moon/Sun "Check this capture first" job links back from the Jobs page** (`Jobs.JobResultActions` had *View result* for `video_stack` but nothing for `video_grade`; *See the check* → `/moon-sun`). Suite 8595 passed / 7 skipped; vitest 4985 passed. **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate is answered; Scout: sweep (4) with a new angle.*
*2026-11-07 (Builder, branch `claude/fervent-allen-a93ah2`) — **v0.505.32: the two Settings → Maintenance "finish with Auto" jobs read back what they did on the Jobs page** (`Jobs.JobResultActions` had no branch for `finish_unedited_pictures`/`refinish_pictures`, though the card navigates there; new `finishPicturesSummary`: finished / left alone / could not finish, Gallery link). Suite 8595 passed / 7 skipped; vitest 4984 passed. **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate is answered; Scout: sweep (4) with a new angle.*
*2026-11-07 (Builder, branch `claude/fervent-allen-hzdrov`) — **v0.505.31: a finished stack opens its picture from the Jobs page** (`Jobs.JobResultActions` had *View result* for `process_target` but none for the Stack form's own `stack` job or a Moon/Sun `video_stack`). Suite 8595 passed / 7 skipped; vitest 4978 passed. **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate is answered; Scout: sweep (4) with a new angle.*
*2026-11-07 (Builder, branch `claude/fervent-allen-gczctg`) — **no app change: nothing ungated; dogfood `--mosaic --dithered --restack --editor` CLEAN** (trims 7.9 % tiled / 30.7 % dithered against its recorded 30.3 % apron; all 21 ops re-render on both mosaic runs, undo/redo apply, taste chips behave; nothing overflowing, no console errors; only already-recorded non-findings — see `PROCESS-NOTES.md`). Suite 8595 passed / 7 skipped. **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate is answered; Scout: sweep (4) with a new angle.*
*2026-11-07 (Builder, branch `claude/fervent-allen-rqa3p8`) — **no app change: nothing ungated** (inbox the same four, owner-gated; code read of `histogram.measure_sky_cast` / `skyCast.canNeutraliseSkyCast` on NaN-gapped mosaics, `editor._decode_recipe_query` on non-dict bodies, `Editor.tsx` undo/redo keys, `curveDrag`, `Jobs.JobResultActions`: nothing to file — see `PROCESS-NOTES.md`). Suite 8595 passed / 7 skipped. **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate is answered; Scout: sweep (4) with a new angle.*
*2026-11-07 (Builder, branch `claude/fervent-allen-a3oq0w`) — **no app change: nothing ungated; dogfood `--mosaic --editor` CLEAN** (trim 7.9 %, all 21 ops re-render on both drives, taste chips and the Hold-back-highlights nudge behave, no console errors; the two standing non-findings only — see `PROCESS-NOTES.md`). Suite 8595 passed / 7 skipped. **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate is answered; Scout: sweep (3) with a new angle.*
*2026-11-07 (Scout, branch `claude/exciting-wozniak-eh1x5t`) — **QA rotation sweep (3), the listed open angle: a visible ZFS `.zfs/snapshot/` tree inside `incoming/` — side effects CLEAN, one finding reproduced** (two snapshots of 8 subs plan and scan as one `.zfs` target of 16 mixing two objects; folded into the owner-gated dot-folder entry in Bugs, one-sitting item 19, since one skip covers both). Inbox: the same four, owner-gated. Dogfood `--mosaic` CLEAN. Suite 8595 passed / 7 skipped. **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate is answered; Scout: sweep (4) with a new angle.*

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
