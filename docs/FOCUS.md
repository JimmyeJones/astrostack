# Current focus — AstroStack

> **Short on purpose (AGENTS.md: "short, dated, the Scout keeps it current").** One dated line per run goes at the
> top of *Run log*; keep about the last ten and move older lines, whole and in order, to `docs/archive/`. Detail
> belongs in `docs/PROCESS-NOTES.md`, never here. The 2,559-line page this replaced is kept verbatim in
> [`archive/FOCUS-to-2026-10-21.md`](archive/FOCUS-to-2026-10-21.md) — nothing was deleted.

## Front of the queue (2026-11-04)

**No ungated bug is open.** The Levels/Curves histogram guides sit on the op's own input histogram (v0.505.20). Every split before/after divider answers the arrow keys (v0.505.17). The imaging calendar's night answers Enter/Space (v0.505.16). The full-size check's navigator answers the arrow keys (v0.505.15). A tap on the crop rectangle no longer re-rounds Auto's trim (v0.505.14). A Curves double-click on the box's edge no longer makes a hidden endpoint (v0.505.13). Tonight's planner tables fit a phone as of v0.505.12 (stacked rows, like Calibration's v0.505.11). The `._*.fit` sidecar half of the Scout 2026-11-03 entry shipped as v0.505.10; its
`.recycle/` / `.Trash-*/` half waits on the owner. A Builder should dogfood (`--mosaic --editor`) and file what it finds. The owner's ⭐
colour-pattern entry is on HOLD for his per-temperature numbers; the dark ring waits on the S30's measured vignette.
Recently closed: a one-target stack after a Combine shows its deeper picture (v0.505.9); "It's back" names the deepest
returning target per part (v0.505.8); Compare's same-object pair (v0.505.7). Older closures are in the archived run
log and `SHIPPED.md`.

**Gated, do not start:** the un-located-panel entry (second in Bugs) waits on the owner's hint-shape answer; the
other LEADs and ⚪ notes in Bugs wait on owner/observer measurements — read each one's gate first, and do not
re-litigate a stand-down that carries numbers. **Issue inbox:** #878, #880, #903, #1015 — all previously acted-on
and owner-gated, none updated since 2026-10-12 (re-checked 2026-11-04).

## QA rotation (Scout)

Order (AGENTS.md roles): (1) preview↔export parity at mosaic scale → (2) mosaic/walk-away per-panel divergence →
(3) ASTAP/ffmpeg filesystem side effects with a stub binary → (4) the webapp routers. **Last swept: (4), 2026-11-04
→ next sweep is (1).** Each (3) sweep must find a *new* angle — the list of angles already run is in the
`Sweep (3)` entries of `docs/PROCESS-NOTES.md` (grep `sweep (3)`).

## Run log (newest first)

*2026-11-05 (Builder, branch `claude/fervent-allen-nq37cj`) — **no app change; one measured bug filed: the "Hold back highlights" nudge goes silent on the bigger mosaic canvas for the same blown core** (`highlights.measure_blown_core`'s area floor is a share of the whole canvas, counted in proxy pixels; 91 px core → nudge on the 2×2, ≈96 native px → `None` on its full-size twin). Dogfood `--big --mosaic --editor` otherwise CLEAN (scale pair 0 of 16 moved, nothing overflowing, no console errors). **START HERE NEXT RUN:** Builder: that Bugs entry (size M, ungated); Scout: sweep (1) with a new angle.*
*2026-11-05 (Builder, branch `claude/fervent-allen-rammv4`) — **v0.505.21: Trim / Re-trim / Re-centre write their bounds into one crop** (`mosaicTrim.applyTrimCrop`; it wrote them into every `geometry.crop`, so a recipe with a second crop from the Add menu was cut twice and lost its framing). Suite 8574 passed / 7 skipped. **START HERE NEXT RUN:** Scout: sweep (1) with a new angle; Builder: nothing ungated.*
*2026-11-05 (Builder, branch `claude/fervent-allen-1b4gnh`) — **no app change: nothing ungated; dogfood `--mosaic --editor` CLEAN** (both editor drives: 21 ops re-render, Undo/Redo, Auto-process notes and the taste chips answer; mosaic trim 7.9 %; nothing overflowing, no console errors). Code read of `stageConflicts`, `coverageLeveling`, `recentreCrop`, `savedLookCrop`, `pollJob`, `previewDebounce`, `geometry.py`, `tone._levels`: nothing to file. Suite 8574 passed / 7 skipped. **START HERE NEXT RUN:** Scout: sweep (1) with a new angle; Builder: nothing ungated until an owner gate is answered.*
*2026-11-05 (Builder, branch `claude/fervent-allen-ptpf1h`) — **v0.505.20: the Levels B/W and Curves guides are drawn on the histogram of the picture *entering* the op** (`tonalHistView`, `editor.op_input_histogram`; they sat on the finished picture's histogram, where Levels has already moved its black point to 0). **START HERE NEXT RUN:** Scout: sweep (1) with a new angle; Builder: nothing ungated — other editor captions that read the finished histogram (`clippingCaption`, sky cast) are correct by design.*
*2026-11-04 (Builder, branch `claude/fervent-allen-lrf9oe`) — **v0.505.19: an upload never writes a macOS sidecar into `incoming/`** (`upload.is_mac_metadata_name`; every macOS-made zip carries `__MACOSX/._*.fit` twins, which the endpoint saved into the §10 folder and, flattened, re-created the v0.505.10 unreadable-sub symptom). **START HERE NEXT RUN:** Scout: sweep (1) with a new angle; Builder: nothing ungated.*
*2026-11-04 (Builder, branch `claude/fervent-allen-aje4n8`) — **v0.505.18: the editor's Presets menu asks before deleting a saved preset** (`PresetMenu.deletePreset`; the trash icon sits inside the row that applies the preset and deleted it for good on one tap, while applying already asked; Enter in the save dialog now saves). Code read of `PresetMenu`, `LookComparePicker`, `UnsavedLookGuard`: nothing else to file. **START HERE NEXT RUN:** Scout: sweep (1) with a new angle; Builder: nothing ungated.*
*2026-11-04 (Builder, branch `claude/fervent-allen-8ytsh9`) — **no app change: nothing ungated; dogfood `--mosaic --editor` run to the end this time, CLEAN** (the editor drive finished: all 21 ops re-render, Undo/Redo, Auto-process and its taste chips answer; trim 7.9 %; nothing overflowing, no console errors). Code read of `CurvesWidget`, `OpParamPanel`, `useUndoable`, `SkylineEditor`: nothing to file. Suite 8567 passed / 7 skipped. **START HERE NEXT RUN:** Scout: sweep (1) with a new angle; Builder: nothing ungated until an owner gate is answered.*
*2026-11-04 (Builder, branch `claude/fervent-allen-sxqaq7`) — **v0.505.17: every split before/after divider moves with the arrow keys** (`splitCompare.nudgeSplit` / `splitSliderProps`; the editor's Split, the full-size check, One frame vs your stack and Compare were drag-only and not focusable). Dogfood `--mosaic --editor` CLEAN as far as it ran (the editor drive was cut off by the run's own 10-min timeout after all 21 ops re-rendered). **START HERE NEXT RUN:** Scout: sweep (1) with a new angle; Builder: nothing ungated — dogfood `--mosaic --editor` with a longer timeout.*
*2026-11-04 (Scout, branch `claude/exciting-wozniak-9ddn2i`) — **QA rotation sweep (4), new angle: every GET route crawled on an owner-shaped install (subs read in place from `incoming/`, `copy_to_cache` off) with a byte/mtime snapshot of the whole data root before and after — CLEAN** (`incoming/` untouched; the only writes are first-call caches inside `library/`; a second crawl writes nothing at all, files or DB rows; 0 × 5xx). Inbox: the same four, owner-gated. Dogfood `--mosaic` CLEAN. Backlog: 14 closed stubs (236 lines) archived to `archive/IMPROVEMENTS-closed-stubs.md`. **START HERE NEXT RUN:** Builder: nothing ungated — dogfood `--mosaic --editor`; Scout: sweep (1) with a new angle.*
*2026-11-04 (Builder, branch `claude/fervent-allen-pist1v`) — **v0.505.16: the imaging calendar's focused night answers Enter/Space** (`ImagingCalendarCard` `Cell`; Tab landed on a `role="button"` that ignored both keys). Read of every focusable `role="button"`: `OpList`, `HintIcon`, `HintAnchor` already handle the keys. **START HERE NEXT RUN:** Scout: sweep (4) with a new angle; Builder: nothing ungated — dogfood `--mosaic --editor`.*

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
