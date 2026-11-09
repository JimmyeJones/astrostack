# Current focus — AstroStack

> **Short on purpose (AGENTS.md: "short, dated, the Scout keeps it current").** One dated line per run goes at the
> top of *Run log*; keep about the last ten and move older lines, whole and in order, to `docs/archive/`. Detail
> belongs in `docs/PROCESS-NOTES.md`, never here. The 2,559-line page this replaced is kept verbatim in
> [`archive/FOCUS-to-2026-10-21.md`](archive/FOCUS-to-2026-10-21.md) — nothing was deleted.

## Front of the queue (2026-11-09)

**Nothing ungated is open in Bugs** (the double-queued Process/Restack bug shipped as v0.505.37). A Builder should
dogfood (`--mosaic --editor`) and file what it finds. The `._*.fit` sidecar half of the Scout
2026-11-03 entry shipped as v0.505.10; its `.recycle/` / `.Trash-*/` / visible `.zfs/` half (one skip) waits on the
owner. The owner's ⭐ colour-pattern entry is on HOLD for his per-temperature numbers; the dark ring waits on the
S30's measured vignette. Recent closures (v0.505.9 → v0.505.36, the Jobs-page read-back series among them) are in
the run log below and `SHIPPED.md`.

**Gated, do not start:** the un-located-panel entry (second in Bugs) waits on the owner's hint-shape answer; the
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

*2026-11-09 (Builder, branch `claude/fervent-allen-13mekw`) — **no app change: nothing ungated; dogfood `--mosaic --restack --calibration --no-site --editor` CLEAN** (a combination no pass had run together: the calibrated restack 3 → 6 subs applies both masters and the calibration note withdraws; mosaic notes agree on the thin top-right panel; Auto trim 7.9 %; all 21 ops re-render, Undo/Redo apply, taste chips behave). The Scout's two unswept (1) leads — the year recap hero and a pinned cover saved North-up later — read clean: both resolve through `current_picture_path`, and a North-up save rewrites the pinned run's own `preview_path`. Suite 8638 passed / 7 skipped. **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate or a diagnostic result arrives; Scout: sweep (2).*
*2026-11-09 (Builder, branch `claude/fervent-allen-3qy836`) — **no app change: nothing ungated; dogfood `--mosaic --incoming-lag --no-site --editor` CLEAN** (the two flags no pass had run since 2026-10-21: the Dashboard's incoming-lag note reads 8 waiting / 11 days with its unreadable-file count; `/tonight` renders its no-site alert; mosaic Target page's next-best-move, readiness and framing notes point the same way; Auto trim 7.9 %; all 21 ops re-render, Undo/Redo apply, taste chips behave). Suite 8638 passed / 7 skipped. **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate or a diagnostic result arrives; Scout: sweep (2).*
*2026-11-09 (Builder, branch `claude/fervent-allen-j5xv2c`) — **v0.506.4: diagnostic `filter_card_values` v2 reads each sampled night at its first and last sub, with nights spread over the whole history** (`filter_card._sample`). v1 read one sub per night from the oldest nights only, so its within-night check could only say 0 and a card that only newer firmware writes was invisible; the LP-filter idea now waits on v2. **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate or a diagnostic result arrives; Scout: sweep (2).*
*2026-11-09 (Builder, branch `claude/fervent-allen-w38x6w`) — **v0.506.3: diagnostic `sensor_pattern_by_temperature` v2 splits its halves by *sky*, not by target** (`sky_groups`: a mosaic and its single field, or centres within 5°, are one sky). v1 — not yet on `stable` — read a nebula a field and its mosaic share as repeat_r 0.992 / ratio 15, a camera pattern that is not there; the ⭐ colour-pattern hold now waits on v2. **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate or a diagnostic result arrives; Scout: sweep (2).*
*2026-11-09 (Scout, branch `claude/exciting-wozniak-xxwm76`) — **QA rotation sweep (1), new angle: the deep-sky wall (`/api/gallery/montage.jpg`) and the recap poster (`/api/recap.jpg`) fed a North-up-turned run on a mosaic-size canvas — CLEAN** (both read the stored turned bytes through `current_picture_path`, as the Gallery does). Inbox: the same four, owner-gated. Dogfood `--mosaic` CLEAN. Suite 8631 passed / 7 skipped. **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate or a diagnostic result arrives; Scout: sweep (2).*
*2026-11-09 (Builder, branch `claude/fervent-allen-hnqmz2`) — **v0.506.2: the boot-time `diagnostics` job reads back on the Jobs page (`Jobs.diagnosticsSummary`) and a cancelled one reads *cancelled*, not *done*** (v0.506.0's body returned a truthy `{"ran": []}` with no sentinel). Dogfood `--empty` CLEAN. **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate or a diagnostic result arrives; Scout: sweep (1).*
*2026-11-09 (Builder, branch `claude/fervent-allen-lotulm`) — **v0.506.1: second library diagnostic `filter_card_values` v1** (`seestack/diag/filter_card.py`; header-only, sampled; tallies the `FILTER` card per value/target/night/family). It is the one gate on the Features idea "Was the light-pollution filter on?". Suite 8631 passed / 7 skipped. **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate or a diagnostic result arrives; Scout: sweep (1), and file `Diagnostic result:` issues when they land.*
*2026-11-09 (Builder, branch `claude/fervent-allen-1p92hi`) — **no app change: nothing ungated; dogfood `--dithered --deep --calibration --closing --editor` CLEAN** (calibrated stack applies both masters and the calibration note withdraws; dithered trim 30.7 % against its recorded 30.3 % apron; both editor drives re-render all 21 ops, Undo/Redo apply, taste chips behave; frames table at 1,200 subs windows 301 → 601 rows; the Tonight cards agree on the closing target). Suite 8598 passed / 7 skipped. **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate is answered; Scout: sweep (1).*
*2026-11-09 (Builder, branch `claude/fervent-allen-rqv3tt`) — **no app change: nothing ungated; dogfood `--combine --editor` CLEAN** (scan → no-solve refusal → merge nudge → *Combine into one deep target* → rescan stays combined → a new sub in the combined-away folder lands in the deep target; `incoming/` byte-for-byte unchanged; all 21 ops re-render, Undo/Redo apply, taste chips behave; Dashboard's "3 subs … aren't in the picture yet" agrees with the 3 solved subs the picture lacks). Suite 8598 passed / 7 skipped. **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate is answered; Scout: sweep (1).*
*2026-11-08 (Builder, branch `claude/fervent-allen-xl888i`) — **no app change: nothing ungated; dogfood `--restack --dithered --editor` CLEAN** (restack 3 → 6 subs, reel and noise-delta both available; dithered trim 30.7 % against its recorded 30.3 % apron; all 21 ops re-render on the field and the dithered mosaic, Undo/Redo apply, taste chips behave; `classify_error_message` re-read for v0.505.38's class — no other raised message mis-keys). Suite 8598 passed / 7 skipped. **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate is answered; Scout: sweep (1).*

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
