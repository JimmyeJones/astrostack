# Current focus — AstroStack

> **Short on purpose (AGENTS.md: "short, dated, the Scout keeps it current").** One dated line per run goes at the
> top of *Run log*; keep about the last ten and move older lines, whole and in order, to `docs/archive/`. Detail
> belongs in `docs/PROCESS-NOTES.md`, never here. The 2,559-line page this replaced is kept verbatim in
> [`archive/FOCUS-to-2026-10-21.md`](archive/FOCUS-to-2026-10-21.md) — nothing was deleted.

## Front of the queue (2026-11-07)

**No ungated bug is open.** The "Hold back highlights" severity is measured on a native window of the master and no longer drifts with the proxy step (v0.505.23; its size floor was v0.505.22). A trim lands in one crop, not every crop (v0.505.21). The Levels/Curves histogram guides sit on the op's own input histogram (v0.505.20). Every split before/after divider answers the arrow keys (v0.505.17). The imaging calendar's night answers Enter/Space (v0.505.16). The full-size check's navigator answers the arrow keys (v0.505.15). A tap on the crop rectangle no longer re-rounds Auto's trim (v0.505.14). A Curves double-click on the box's edge no longer makes a hidden endpoint (v0.505.13). Tonight's planner tables fit a phone as of v0.505.12 (stacked rows, like Calibration's v0.505.11). The `._*.fit` sidecar half of the Scout 2026-11-03 entry shipped as v0.505.10; its
`.recycle/` / `.Trash-*/` / visible `.zfs/` half (one skip) waits on the owner. A Builder should dogfood (`--mosaic --editor`) and file what it finds. The owner's ⭐
colour-pattern entry is on HOLD for his per-temperature numbers; the dark ring waits on the S30's measured vignette.
Recently closed: a one-target stack after a Combine shows its deeper picture (v0.505.9); "It's back" names the deepest
returning target per part (v0.505.8); Compare's same-object pair (v0.505.7). Older closures are in the archived run
log and `SHIPPED.md`.

**Gated, do not start:** the un-located-panel entry (second in Bugs) waits on the owner's hint-shape answer; the
other LEADs and ⚪ notes in Bugs wait on owner/observer measurements — read each one's gate first, and do not
re-litigate a stand-down that carries numbers. **Issue inbox:** #878, #880, #903, #1015 — all previously acted-on
and owner-gated, none updated since 2026-10-12 (re-checked 2026-11-07).

## QA rotation (Scout)

Order (AGENTS.md roles): (1) preview↔export parity at mosaic scale → (2) mosaic/walk-away per-panel divergence →
(3) ASTAP/ffmpeg filesystem side effects with a stub binary → (4) the webapp routers. **Last swept: (3), 2026-11-07
→ next sweep is (4).** Each (3) sweep must find a *new* angle — the list of angles already run is in the
`Sweep (3)` entries of `docs/PROCESS-NOTES.md` (grep `sweep (3)`).

## Run log (newest first)

*2026-11-07 (Builder, branch `claude/fervent-allen-a93ah2`) — **v0.505.32: the two Settings → Maintenance "finish with Auto" jobs read back what they did on the Jobs page** (`Jobs.JobResultActions` had no branch for `finish_unedited_pictures`/`refinish_pictures`, though the card navigates there; new `finishPicturesSummary`: finished / left alone / could not finish, Gallery link). Suite 8595 passed / 7 skipped; vitest 4984 passed. **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate is answered; Scout: sweep (4) with a new angle.*
*2026-11-07 (Builder, branch `claude/fervent-allen-hzdrov`) — **v0.505.31: a finished stack opens its picture from the Jobs page** (`Jobs.JobResultActions` had *View result* for `process_target` but none for the Stack form's own `stack` job or a Moon/Sun `video_stack`). Suite 8595 passed / 7 skipped; vitest 4978 passed. **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate is answered; Scout: sweep (4) with a new angle.*
*2026-11-07 (Builder, branch `claude/fervent-allen-gczctg`) — **no app change: nothing ungated; dogfood `--mosaic --dithered --restack --editor` CLEAN** (trims 7.9 % tiled / 30.7 % dithered against its recorded 30.3 % apron; all 21 ops re-render on both mosaic runs, undo/redo apply, taste chips behave; nothing overflowing, no console errors; only already-recorded non-findings — see `PROCESS-NOTES.md`). Suite 8595 passed / 7 skipped. **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate is answered; Scout: sweep (4) with a new angle.*
*2026-11-07 (Builder, branch `claude/fervent-allen-rqa3p8`) — **no app change: nothing ungated** (inbox the same four, owner-gated; code read of `histogram.measure_sky_cast` / `skyCast.canNeutraliseSkyCast` on NaN-gapped mosaics, `editor._decode_recipe_query` on non-dict bodies, `Editor.tsx` undo/redo keys, `curveDrag`, `Jobs.JobResultActions`: nothing to file — see `PROCESS-NOTES.md`). Suite 8595 passed / 7 skipped. **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate is answered; Scout: sweep (4) with a new angle.*
*2026-11-07 (Builder, branch `claude/fervent-allen-a3oq0w`) — **no app change: nothing ungated; dogfood `--mosaic --editor` CLEAN** (trim 7.9 %, all 21 ops re-render on both drives, taste chips and the Hold-back-highlights nudge behave, no console errors; the two standing non-findings only — see `PROCESS-NOTES.md`). Suite 8595 passed / 7 skipped. **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate is answered; Scout: sweep (3) with a new angle.*
*2026-11-07 (Scout, branch `claude/exciting-wozniak-eh1x5t`) — **QA rotation sweep (3), the listed open angle: a visible ZFS `.zfs/snapshot/` tree inside `incoming/` — side effects CLEAN, one finding reproduced** (two snapshots of 8 subs plan and scan as one `.zfs` target of 16 mixing two objects; folded into the owner-gated dot-folder entry in Bugs, one-sitting item 19, since one skip covers both). Inbox: the same four, owner-gated. Dogfood `--mosaic` CLEAN. Suite 8595 passed / 7 skipped. **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate is answered; Scout: sweep (4) with a new angle.*
*2026-11-07 (Builder, branch `claude/fervent-allen-94cy8a`) — **v0.505.30: a finished Share or Print file can be collected from the Jobs page** (`Jobs.JobResultActions` had a download for `editor_png` and the archive but not `editor_share`/`editor_print`, so leaving the editor mid-render stranded the JPEG). **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate is answered; Scout: sweep (3) with a new angle.*
*2026-11-07 (Builder, branch `claude/fervent-allen-kwf1nt`) — **v0.505.29: the Jobs page and the job-finished ping name the editor's Share and Print jobs in plain words** (`Jobs.KIND_LABEL` lacked `editor_share`/`editor_print`, so they read as raw ids); new `tests/test_job_kind_labels.py` fails on any submitted job kind with no label. **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate is answered; Scout: sweep (3) with a new angle.*
*2026-11-07 (Builder, branch `claude/fervent-allen-bf5zb9`) — **v0.505.28: an editor export queued behind a running stack says it is waiting, not "Rendering"** (`pngProgress.pngProgressLabel` read a queued job's empty phase as "Rendering"; the single worker makes that wait hours on a big stack). Dogfood `--mosaic --editor` CLEAN (trim 7.9 %, all 21 ops re-render on both drives, no console errors). Suite 8593 passed / 7 skipped. **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate is answered; Scout: sweep (3) with a new angle.*
*2026-11-06 (Builder, branch `claude/fervent-allen-6vw4kr`) — **v0.505.27: an editor export or render an out-of-memory restart cut off is named as a restart, not "Failed to fetch"** (`pollJob.pollJobUntilDone` gave up after five 500 ms polls — ~2.5 s, shorter than a container restart — and when the app was back in time it quoted the stack-shaped restart note's plate-solve advice; it now backs off (`pollErrorBackoffMs`, ~2.4 min of outage) and `jobFailureMessage` says what happened). Found by a code read of the UX & polish job-error item. **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate is answered; Scout: sweep (3) with a new angle.*

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
