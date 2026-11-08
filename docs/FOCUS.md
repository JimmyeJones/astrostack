# Current focus — AstroStack

> **Short on purpose (AGENTS.md: "short, dated, the Scout keeps it current").** One dated line per run goes at the
> top of *Run log*; keep about the last ten and move older lines, whole and in order, to `docs/archive/`. Detail
> belongs in `docs/PROCESS-NOTES.md`, never here. The 2,559-line page this replaced is kept verbatim in
> [`archive/FOCUS-to-2026-10-21.md`](archive/FOCUS-to-2026-10-21.md) — nothing was deleted.

## Front of the queue (2026-11-08)

**Nothing ungated is open in Bugs** (the double-queued Process/Restack bug shipped as v0.505.37). A Builder should
dogfood (`--mosaic --editor`) and file what it finds. The `._*.fit` sidecar half of the Scout
2026-11-03 entry shipped as v0.505.10; its `.recycle/` / `.Trash-*/` / visible `.zfs/` half (one skip) waits on the
owner. The owner's ⭐ colour-pattern entry is on HOLD for his per-temperature numbers; the dark ring waits on the
S30's measured vignette. Recent closures (v0.505.9 → v0.505.36, the Jobs-page read-back series among them) are in
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

*2026-11-08 (Builder, branch `claude/fervent-allen-7mwvuw`) — **v0.505.38: a mosaic refused for a too-big canvas no longer tells the owner nothing is plate-solved** (`compute_mosaic_canvas`'s refusal blames "bad plate-solves", which `classify_error_message` / `Jobs.friendlyJobError` matched as `no_solved_frames`; new `canvas_too_large`). Dogfood `--big --deep --editor` CLEAN (all 21 ops re-render at proxy scale 2; frames table at 1,200 subs windows 301 → 601 rows). **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate is answered; Scout: sweep (1).*
*2026-11-08 (Builder, branch `claude/fervent-allen-gilw79`) — **no app change: nothing ungated; dogfood `--mosaic --editor` CLEAN** (Auto trim 7.9 %; all 21 ops re-render on field and mosaic, Undo/Redo apply; the mosaic Target page's five notes agree; every `api.processTarget` caller now goes through v0.505.37's deduped route — nothing left to follow up). Suite 8597 passed / 7 skipped. **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate is answered; Scout: sweep (1).*
*2026-11-08 (Builder, branch `claude/fervent-allen-4pon1s`) — **v0.505.37: a second click on Process target / Restack no longer queues a second identical whole-target stack** (`JobManager.submit_unless_queued` hands back a still-queued `process_target`, `already_queued` on the route; `hooks/useTargetStackJob` keeps the five buttons *Processing…* while a stack of the target is live). **START HERE NEXT RUN:** Builder: dogfood `--mosaic --editor` and file what it finds; Scout: sweep (1).*
*2026-11-08 (Scout, branch `claude/exciting-wozniak-nk09s6`) — **QA rotation sweep (4), new angle: a repeated POST on the job-submitting routes — one bug filed reproduced** (two `POST /api/targets/{safe}/process` queue two identical whole-target stacks; the Target page's Process/Restack buttons are busy only for the POST). Inbox: the same four, owner-gated. Dogfood `--mosaic` CLEAN. **START HERE NEXT RUN:** Builder: the double-process bug in Bugs (S, ungated); Scout: sweep (1).*
*2026-11-08 (Builder, branch `claude/fervent-allen-yzfotq`) — **v0.505.36: a batch export (`editor_batch`, the Gallery's *Apply preset to selected*) says on the Jobs page what it made and which pictures failed, and why** (`Jobs.batchExportSummary`; an all-failed batch used to read as done with a "View 0 in Gallery" button). **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate is answered; Scout: sweep (4) with a new angle.*
*2026-11-08 (Builder, branch `claude/fervent-allen-6wn2di`) — **v0.505.35: clicking the opt-in "your job finished" desktop ping brings AstroStack forward on the Jobs page** (`jobNotify.showJobNotification` built the `Notification` with no `onclick`; `GlobalJobNotifier` now navigates to `/jobs`). Dogfood `--closing --calibration --incoming-lag` CLEAN. Suite 8595 passed / 7 skipped; vitest 4993 passed. **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate is answered; Scout: sweep (4) with a new angle.*
*2026-11-08 (Builder, branch `claude/fervent-allen-dmh6fb`) — **v0.505.34: the boot-time border-trim job reads back on the Jobs page** (`unedited_preview_trim` was the last submitted kind besides the deprioritised `channel_combine` with no `Jobs.JobResultActions` branch; new `previewTrimSummary`). Suite 8595 passed / 7 skipped; vitest 4990 passed. **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate is answered; Scout: sweep (4) with a new angle.*
*2026-11-08 (Builder, branch `claude/fervent-allen-po1pe4`) — **v0.505.33: a finished Moon/Sun "Check this capture first" job links back from the Jobs page** (`Jobs.JobResultActions` had *View result* for `video_stack` but nothing for `video_grade`; *See the check* → `/moon-sun`). Suite 8595 passed / 7 skipped; vitest 4985 passed. **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate is answered; Scout: sweep (4) with a new angle.*
*2026-11-07 (Builder, branch `claude/fervent-allen-a93ah2`) — **v0.505.32: the two Settings → Maintenance "finish with Auto" jobs read back what they did on the Jobs page** (`Jobs.JobResultActions` had no branch for `finish_unedited_pictures`/`refinish_pictures`, though the card navigates there; new `finishPicturesSummary`: finished / left alone / could not finish, Gallery link). Suite 8595 passed / 7 skipped; vitest 4984 passed. **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate is answered; Scout: sweep (4) with a new angle.*
*2026-11-07 (Builder, branch `claude/fervent-allen-hzdrov`) — **v0.505.31: a finished stack opens its picture from the Jobs page** (`Jobs.JobResultActions` had *View result* for `process_target` but none for the Stack form's own `stack` job or a Moon/Sun `video_stack`). Suite 8595 passed / 7 skipped; vitest 4978 passed. **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate is answered; Scout: sweep (4) with a new angle.*

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
