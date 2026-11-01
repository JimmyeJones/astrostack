# Current focus — AstroStack

> **Short on purpose (AGENTS.md: "short, dated, the Scout keeps it current").** One dated line per run goes at the
> top of *Run log*; keep about the last ten and move older lines, whole and in order, to `docs/archive/`. Detail
> belongs in `docs/PROCESS-NOTES.md`, never here. The 2,559-line page this replaced is kept verbatim in
> [`archive/FOCUS-to-2026-10-21.md`](archive/FOCUS-to-2026-10-21.md) — nothing was deleted.

## Front of the queue (2026-11-01)

**One ungated bug is open and it is the Builder's next task:** "Try something new tonight" plans the whole night
even when most of it is gone (first Bugs entry, size S, reproduced by the Scout on 2026-11-01 — the v0.505.4 class
one card over: clip `well_placed_tonight`'s window to now, and check all four callers). After that, the owner's ⭐
entry from #1317 is closed apart from its part (4), the dark ring — the second Bugs entry, gated on the S30's
measured vignette. A Builder with nothing ungated should dogfood (`--mosaic --editor`) and file what it finds, or
take the beginner idea in "Features that serve real workflows" once its observer gate is answered. Recently closed:
the Calibration repair offer names what it repairs (v0.505.5); "Point here tonight" no longer recommends a target
that has set (v0.505.4); a catalogued galaxy is not a "star cluster" (v0.505.3); an Auto chip tap answers at once
(v0.505.2); "It's back" (v0.505.0); a stored bad stacking default no longer blocks every Settings save (v0.504.7,
Scout sweep (4)). Older closures are in the archived run log and `SHIPPED.md`.

**Gated, do not start:** the un-located-panel entry (third in Bugs) waits on the owner's hint-shape answer; the
other LEADs and ⚪ notes in Bugs wait on owner/observer measurements — read each one's gate first, and do not
re-litigate a stand-down that carries numbers. **Issue inbox:** #878, #880, #903, #1015 — all previously acted-on
and owner-gated, none updated since 2026-10-12 (re-checked 2026-11-01).

## QA rotation (Scout)

Order (AGENTS.md roles): (1) preview↔export parity at mosaic scale → (2) mosaic/walk-away per-panel divergence →
(3) ASTAP/ffmpeg filesystem side effects with a stub binary → (4) the webapp routers. **Last swept: (1), 2026-11-01
→ next sweep is (2).** Each (3) sweep must find a *new* angle — the list of angles already run is in the
`Sweep (3)` entries of `docs/PROCESS-NOTES.md` (grep `sweep (3)`).

## Run log (newest first)

*2026-11-01 (Scout, branch `claude/exciting-wozniak-seqf64`) — **QA rotation sweep (1), new angle: a non-trivial North-up angle (CD rotated 30°/−71°/12°) through the native share and wallpaper path on trimmed auto-edits — CLEAN** (landmarks within 0.05 % of the frame of the stored-preview twin). **Filed, reproduced:** "Try something new tonight" scores the whole ongoing night (`well_placed_tonight`). Inbox: the same four, owner-gated. Dogfood `--mosaic` CLEAN. One moot idea closed, one beginner idea filed (LP filter, observer-gated). **START HERE NEXT RUN:** Builder: the first Bugs entry. **Rotation: (1) done → next sweep is (2).***
*2026-11-01 (Builder, branch `claude/practical-shannon-ieouv1`) — **v0.505.5: the Calibration page's broken-pixel offer names what it repairs ("Repair hot or dead pixels on every stack from now on") instead of a "Repair these" above a table whose counts sit below it** (`calibration.defect_repair_offer`); dogfood `--mosaic --editor --calibration --no-site` otherwise CLEAN. Suite 8541 passed / 7 skipped; vitest 4905. **START HERE NEXT RUN:** Scout: sweep (1) and a fresh beginner idea; Builder: the observer can answer the dark-ring vignette gate.*
*2026-11-01 (Builder, branch `claude/practical-shannon-h7pyj4`) — **v0.505.4: the Dashboard's "Point here tonight" no longer recommends a started target that has already set** (`pickContinueTonight(nowMs)`; read at 04:14 it named a target whose window closed at 21:16); dogfood `--mosaic --deep --incoming-lag --closing` otherwise CLEAN. **START HERE NEXT RUN:** Scout: sweep (1) and a fresh beginner idea; Builder: the observer can answer the dark-ring vignette gate.*
*2026-11-01 (Builder, branch `claude/zen-fermat-j4oyhb`) — **v0.505.3: a catalogued galaxy/nebula the pixels call a star cluster gets no "Star cluster" chip and no cluster-bucket taste** (`presets.reconcile_with_catalog`; a small galaxy on the S30 field read as a cluster 12 of 16 times); dogfood `--mosaic --big --editor --restack` otherwise CLEAN. **START HERE NEXT RUN:** Scout: sweep (1) and a fresh beginner idea; Builder: the observer can answer the dark-ring vignette gate.*
*2026-10-31 (Builder, branch `claude/zen-fermat-tqx24a`) — **v0.505.2: an Auto feedback chip tap answers at once — the run's archetype and measured knobs are remembered per run's files** (`run_measure_memo`; tap 2.3–3.2 s → 15 ms); dogfood `--mosaic --dithered --editor` otherwise CLEAN. **START HERE NEXT RUN:** Scout: sweep (1) and a fresh beginner idea; Builder: the observer can answer the dark-ring vignette gate.*
*2026-10-31 (Builder, branch `claude/zen-fermat-0zsxqf`) — **v0.505.1: the Dashboard's sample card stops offering "Stack it" once the sample is stacked and leads with "Edit it"** (`SampleImageCard`, `sampleRunToEdit`); dogfood `--mosaic --editor` otherwise CLEAN (trim 7.9 %, 21 ops re-render, taste chips clean). **START HERE NEXT RUN:** Scout: sweep (1) and a fresh beginner idea; Builder: the observer can answer the dark-ring vignette gate.*
*2026-10-31 (Builder, branch `claude/zen-fermat-q4051c`) — **v0.505.0: "It's back" — the week-plan card names a target of his returning to the dark hours after two months away** (`nightplan._returning_targets`, `WeekPlan.returning`, `planweek.returningWeekNote`). **START HERE NEXT RUN:** Scout: sweep (1) and a fresh beginner idea; Builder: the observer can answer the dark-ring vignette gate.*
*2026-10-31 (Scout, branch `claude/exciting-wozniak-rg2y6y`) — **QA rotation sweep (4), new angle: the Settings page's whole-form GET → PUT round-trip — clean at all 49 field bounds, but one out-of-range value already stored in `default_stack_options` 422'd every save; Scout-fixed, v0.504.7** (`_sanitize_patch(stored=)`). Inbox: the same four, owner-gated. Dogfood `--mosaic` CLEAN. Features section curated (13 closed entries → `SHIPPED.md`) and one beginner idea filed. **START HERE NEXT RUN:** Builder: "It's back" (Features). **Rotation: (4) done → next sweep is (1).***
*2026-10-31 (Builder, branch `claude/zen-fermat-5mmpo5`) — **no code change: every open Bugs entry is gated on owner/observer data and "Features that serve real workflows" has no open beginner item; dogfood `--mosaic --editor` CLEAN on the standing baseline** (trim 7.9 %, 21 ops re-render, Auto + taste chips clean). Suite 8515 passed / 7 skipped. **START HERE NEXT RUN:** Scout: sweep (4) and a fresh beginner idea for the Features section; Builder: the observer can answer the dark-ring vignette gate.*
*2026-10-31 (Builder, branch `claude/relaxed-davinci-e0cu7i`) — **v0.504.6: a first Full-res PNG's stretch works in place and takes exact bracketed medians (`thumbnail._exact_median`) — 10.0 s → 5.4 s, peak 830 → 479 MB at 5000×7000, PNG bytes identical; closes the ⭐ 2026-10-28 entry.** **START HERE NEXT RUN:** Builder: a beginner feature from "Features that serve real workflows", or dogfood `--mosaic --editor`; the observer can answer the dark-ring vignette gate.*

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
