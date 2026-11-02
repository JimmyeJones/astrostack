# Current focus — AstroStack

> **Short on purpose (AGENTS.md: "short, dated, the Scout keeps it current").** One dated line per run goes at the
> top of *Run log*; keep about the last ten and move older lines, whole and in order, to `docs/archive/`. Detail
> belongs in `docs/PROCESS-NOTES.md`, never here. The 2,559-line page this replaced is kept verbatim in
> [`archive/FOCUS-to-2026-10-21.md`](archive/FOCUS-to-2026-10-21.md) — nothing was deleted.

## Front of the queue (2026-11-01)

**No ungated bug is open** (re-checked by a Builder dogfood `--mosaic --editor --big --deep`, CLEAN). "Try something new tonight" scoring the whole ongoing night closed in v0.505.6. The
owner's ⭐ entry from #1317 is closed apart from its part (4), the dark ring — the first Bugs entry, gated on the S30's
measured vignette. A Builder with nothing ungated should dogfood (`--mosaic --editor`) and file what it finds, or
take the beginner idea in "Features that serve real workflows" once its observer gate is answered. Recently closed:
"Try something new tonight" scores only the darkness left (v0.505.6); the Calibration repair offer names what it
repairs (v0.505.5); "Point here tonight" no longer recommends a target that has set (v0.505.4); a catalogued galaxy is
not a "star cluster" (v0.505.3); an Auto chip tap answers at once (v0.505.2); "It's back" (v0.505.0). Older closures are in the archived run log and `SHIPPED.md`.

**Gated, do not start:** the un-located-panel entry (second in Bugs) waits on the owner's hint-shape answer; the
other LEADs and ⚪ notes in Bugs wait on owner/observer measurements — read each one's gate first, and do not
re-litigate a stand-down that carries numbers. **Issue inbox:** #878, #880, #903, #1015 — all previously acted-on
and owner-gated, none updated since 2026-10-12 (re-checked 2026-11-01).

## QA rotation (Scout)

Order (AGENTS.md roles): (1) preview↔export parity at mosaic scale → (2) mosaic/walk-away per-panel divergence →
(3) ASTAP/ffmpeg filesystem side effects with a stub binary → (4) the webapp routers. **Last swept: (1), 2026-11-01
→ next sweep is (2).** Each (3) sweep must find a *new* angle — the list of angles already run is in the
`Sweep (3)` entries of `docs/PROCESS-NOTES.md` (grep `sweep (3)`).

## Run log (newest first)

*2026-11-02 (Builder, branch `claude/fervent-allen-40n5a5`) — **no code change: nothing ungated; first-run dogfood `--empty` CLEAN** (the only tall page is the documented non-bug `[phone] /life-list [Still to shoot]` 14,604 px, v0.492.2); the two ungated "Minor" items re-read and left as filed (`MergeResult.n_skipped_missing_file` is read only by the desktop GUI). Suite 8545 passed / 7 skipped. **START HERE NEXT RUN:** Scout: sweep (2) and triage #1344's hold; Builder: nothing ungated until the sensor-temperature or vignette gate is answered.*
*2026-11-01 (Builder, branch `claude/fervent-allen-u0a7vz`) — **no code change: nothing ungated (#1344's ⭐ sensor-pattern entry holds itself for the owner's per-temperature diagnostic); dogfood `--combine --mosaic --editor` CLEAN**, and §10 was measured: `incoming/` was unchanged through scan, merge and rescan. **START HERE NEXT RUN:** Scout: sweep (2) and triage #1344; Builder: nothing ungated until #1344's hold or the vignette gate is answered.*
*2026-11-01 (Builder, branch `claude/practical-shannon-qz759n`) — **no code change: nothing ungated; dogfood `--mosaic --editor --big --deep` CLEAN** — the highlight-nudge difference between the two mosaic samples measured as honest (preview and export agree on each). Suite 8545 passed / 7 skipped. **START HERE NEXT RUN:** Scout: sweep (2); Builder: nothing ungated — the observer can answer the dark-ring vignette gate or the LP-filter count.*
*2026-11-01 (Builder, branch `claude/practical-shannon-yc744h`) — **v0.505.6: "Try something new tonight" read late in the night scores only the darkness left** (`nightplan.well_placed_tonight` clips the ongoing window to now; at 43 min to dawn it showed the evening's six picks at 629 min each → now self-hides). Also fixes the nearly-there, life-list and wishlist "up tonight" cards. Suite 8545 passed / 7 skipped. **START HERE NEXT RUN:** Scout: sweep (2); Builder: nothing ungated — dogfood `--mosaic --editor`; the observer can answer the dark-ring vignette gate.*
*2026-11-01 (Scout, branch `claude/exciting-wozniak-seqf64`) — **QA rotation sweep (1), new angle: a non-trivial North-up angle (CD rotated 30°/−71°/12°) through the native share and wallpaper path on trimmed auto-edits — CLEAN** (landmarks within 0.05 % of the frame of the stored-preview twin). **Filed, reproduced:** "Try something new tonight" scores the whole ongoing night (`well_placed_tonight`). Inbox: the same four, owner-gated. Dogfood `--mosaic` CLEAN. One moot idea closed, one beginner idea filed (LP filter, observer-gated). **START HERE NEXT RUN:** Builder: the first Bugs entry. **Rotation: (1) done → next sweep is (2).***
*2026-11-01 (Builder, branch `claude/practical-shannon-ieouv1`) — **v0.505.5: the Calibration page's broken-pixel offer names what it repairs ("Repair hot or dead pixels on every stack from now on") instead of a "Repair these" above a table whose counts sit below it** (`calibration.defect_repair_offer`); dogfood `--mosaic --editor --calibration --no-site` otherwise CLEAN. Suite 8541 passed / 7 skipped; vitest 4905. **START HERE NEXT RUN:** Scout: sweep (1) and a fresh beginner idea; Builder: the observer can answer the dark-ring vignette gate.*
*2026-11-01 (Builder, branch `claude/practical-shannon-h7pyj4`) — **v0.505.4: the Dashboard's "Point here tonight" no longer recommends a started target that has already set** (`pickContinueTonight(nowMs)`; read at 04:14 it named a target whose window closed at 21:16); dogfood `--mosaic --deep --incoming-lag --closing` otherwise CLEAN. **START HERE NEXT RUN:** Scout: sweep (1) and a fresh beginner idea; Builder: the observer can answer the dark-ring vignette gate.*
*2026-11-01 (Builder, branch `claude/zen-fermat-j4oyhb`) — **v0.505.3: a catalogued galaxy/nebula the pixels call a star cluster gets no "Star cluster" chip and no cluster-bucket taste** (`presets.reconcile_with_catalog`; a small galaxy on the S30 field read as a cluster 12 of 16 times); dogfood `--mosaic --big --editor --restack` otherwise CLEAN. **START HERE NEXT RUN:** Scout: sweep (1) and a fresh beginner idea; Builder: the observer can answer the dark-ring vignette gate.*
*2026-10-31 (Builder, branch `claude/zen-fermat-tqx24a`) — **v0.505.2: an Auto feedback chip tap answers at once — the run's archetype and measured knobs are remembered per run's files** (`run_measure_memo`; tap 2.3–3.2 s → 15 ms); dogfood `--mosaic --dithered --editor` otherwise CLEAN. **START HERE NEXT RUN:** Scout: sweep (1) and a fresh beginner idea; Builder: the observer can answer the dark-ring vignette gate.*
*2026-10-31 (Builder, branch `claude/zen-fermat-0zsxqf`) — **v0.505.1: the Dashboard's sample card stops offering "Stack it" once the sample is stacked and leads with "Edit it"** (`SampleImageCard`, `sampleRunToEdit`); dogfood `--mosaic --editor` otherwise CLEAN (trim 7.9 %, 21 ops re-render, taste chips clean). **START HERE NEXT RUN:** Scout: sweep (1) and a fresh beginner idea; Builder: the observer can answer the dark-ring vignette gate.*

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
