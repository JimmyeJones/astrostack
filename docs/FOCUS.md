# Current focus — AstroStack

> **Short on purpose (AGENTS.md: "short, dated, the Scout keeps it current").** One dated line per run goes at the
> top of *Run log*; keep about the last ten and move older lines, whole and in order, to `docs/archive/`. Detail
> belongs in `docs/PROCESS-NOTES.md`, never here. The 2,559-line page this replaced is kept verbatim in
> [`archive/FOCUS-to-2026-10-21.md`](archive/FOCUS-to-2026-10-21.md) — nothing was deleted.

## Front of the queue (2026-10-31)

**No ungated bug is open (v0.505.3 closed a dogfood find: a catalogued galaxy read as a "star cluster"), and the owner's ⭐ entry from #1317 is closed** — trim on every surface (v0.503.23–v0.504.5), "Finish my unedited pictures" (v0.504.0), repeat downloads cached (v0.503.24) and the first render ~40 % faster with identical bytes (v0.504.6); its part (4), the dark ring, is the first Bugs entry, gated on the S30's measured vignette. "It's back" shipped as v0.505.0; a Builder with nothing ungated should dogfood (`--mosaic --editor`) and file what it finds. Recently closed: a stored out-of-range stacking default no longer blocks every Settings save (v0.504.7, Scout sweep (4)); a non-finite number in ASTAP's `.ini` reads as missing (v0.504.4, Scout sweep (3)); an editor export no longer moves the picture the per-panel hold asks about (v0.503.25, Scout sweep (2)); a `NaN`/`Infinity` body literal is a 422, not a 500 (v0.503.22, Scout sweep (4)); a set-but-wrong ASTAP path now says what is wrong with it (v0.503.21, Scout sweep (3)); the walk-away per-panel readability hold compares a panel with the picture standing (v0.503.20, Scout sweep (2)); an ASTAP that is there but can't be started now reads as a setup
problem (v0.503.19, Scout sweep (3)); a legacy North-up save on a mosaic is recovered again (v0.503.18, Scout sweep (1)); an upload no longer replaces a sub that reached `incoming/` mid-stream (v0.503.17, Scout sweep (4)); a mosaic panel left a few readable subs vs the walk-away hold (v0.503.16); the deepening reel's shallow night drawn cleaner on a grown mosaic (v0.503.15); one night, one dark window (v0.503.10); the hung ffmpeg decoder vs Cancel (v0.503.8); the walk-away missing-files hold on a mosaic panel (v0.503.5); Compare's Split/Blink on a grown mosaic (v0.503.1); the Scout's 2026-10-21 per-part entry closed with v0.502.40 (readiness / Dashboard
progress / Tonight badge); a dogfood pass found and fixed the week plan's same-sky flip (v0.502.41); the Scout's sweep (4) fixed a merge that
deleted a folder a stack was still writing into (v0.502.42). After that, a Builder with nothing ungated should take a beginner feature from "Features that serve
real workflows" in [`IMPROVEMENTS.md`](IMPROVEMENTS.md), or dogfood (`--mosaic --editor`) and file what it finds.

**Gated, do not start:** the un-located-panel entry (third in Bugs) waits on the owner's hint-shape answer; the
other LEADs and ⚪ notes in Bugs wait on owner/observer measurements — read each one's gate first, and do not
re-litigate a stand-down that carries numbers. **Issue inbox:** #878, #880, #903, #1015 — all previously acted-on
and owner-gated, none updated since 2026-10-12 (re-checked 2026-10-31).

## QA rotation (Scout)

Order (AGENTS.md roles): (1) preview↔export parity at mosaic scale → (2) mosaic/walk-away per-panel divergence →
(3) ASTAP/ffmpeg filesystem side effects with a stub binary → (4) the webapp routers. **Last swept: (4), 2026-10-31
→ next sweep is (1).** Each (3) sweep must find a *new* angle — the list of angles already run is in the
`Sweep (3)` entries of `docs/PROCESS-NOTES.md` (grep `sweep (3)`).

## Run log (newest first)

*2026-11-01 (Builder, branch `claude/zen-fermat-j4oyhb`) — **v0.505.3: a catalogued galaxy/nebula the pixels call a star cluster gets no "Star cluster" chip and no cluster-bucket taste** (`presets.reconcile_with_catalog`; a small galaxy on the S30 field read as a cluster 12 of 16 times); dogfood `--mosaic --big --editor --restack` otherwise CLEAN. **START HERE NEXT RUN:** Scout: sweep (1) and a fresh beginner idea; Builder: the observer can answer the dark-ring vignette gate.*
*2026-10-31 (Builder, branch `claude/zen-fermat-tqx24a`) — **v0.505.2: an Auto feedback chip tap answers at once — the run's archetype and measured knobs are remembered per run's files** (`run_measure_memo`; tap 2.3–3.2 s → 15 ms); dogfood `--mosaic --dithered --editor` otherwise CLEAN. **START HERE NEXT RUN:** Scout: sweep (1) and a fresh beginner idea; Builder: the observer can answer the dark-ring vignette gate.*
*2026-10-31 (Builder, branch `claude/zen-fermat-0zsxqf`) — **v0.505.1: the Dashboard's sample card stops offering "Stack it" once the sample is stacked and leads with "Edit it"** (`SampleImageCard`, `sampleRunToEdit`); dogfood `--mosaic --editor` otherwise CLEAN (trim 7.9 %, 21 ops re-render, taste chips clean). **START HERE NEXT RUN:** Scout: sweep (1) and a fresh beginner idea; Builder: the observer can answer the dark-ring vignette gate.*
*2026-10-31 (Builder, branch `claude/zen-fermat-q4051c`) — **v0.505.0: "It's back" — the week-plan card names a target of his returning to the dark hours after two months away** (`nightplan._returning_targets`, `WeekPlan.returning`, `planweek.returningWeekNote`). **START HERE NEXT RUN:** Scout: sweep (1) and a fresh beginner idea; Builder: the observer can answer the dark-ring vignette gate.*
*2026-10-31 (Scout, branch `claude/exciting-wozniak-rg2y6y`) — **QA rotation sweep (4), new angle: the Settings page's whole-form GET → PUT round-trip — clean at all 49 field bounds, but one out-of-range value already stored in `default_stack_options` 422'd every save; Scout-fixed, v0.504.7** (`_sanitize_patch(stored=)`). Inbox: the same four, owner-gated. Dogfood `--mosaic` CLEAN. Features section curated (13 closed entries → `SHIPPED.md`) and one beginner idea filed. **START HERE NEXT RUN:** Builder: "It's back" (Features). **Rotation: (4) done → next sweep is (1).***
*2026-10-31 (Builder, branch `claude/zen-fermat-5mmpo5`) — **no code change: every open Bugs entry is gated on owner/observer data and "Features that serve real workflows" has no open beginner item; dogfood `--mosaic --editor` CLEAN on the standing baseline** (trim 7.9 %, 21 ops re-render, Auto + taste chips clean). Suite 8515 passed / 7 skipped. **START HERE NEXT RUN:** Scout: sweep (4) and a fresh beginner idea for the Features section; Builder: the observer can answer the dark-ring vignette gate.*
*2026-10-31 (Builder, branch `claude/relaxed-davinci-e0cu7i`) — **v0.504.6: a first Full-res PNG's stretch works in place and takes exact bracketed medians (`thumbnail._exact_median`) — 10.0 s → 5.4 s, peak 830 → 479 MB at 5000×7000, PNG bytes identical; closes the ⭐ 2026-10-28 entry.** **START HERE NEXT RUN:** Builder: a beginner feature from "Features that serve real workflows", or dogfood `--mosaic --editor`; the observer can answer the dark-ring vignette gate.*
*2026-10-30 (Builder, branch `claude/relaxed-davinci-vwa67t`) — **the ⭐ entry's (4), the dark ring: Auto does not remove it; measured cause is the per-frame `Background2D` flatten leaving a −24 ADU rim (20 % vignette, 1000 ADU sky) along every sub's edge, which the canvas border receives alone; filed as the first Bugs entry with two tried-and-insufficient tweaks and a candidate (a radial synthetic flat), gated on the S30's real fall-off.** No code changed. **START HERE NEXT RUN:** Builder: the ⭐ entry's first-render speed, or a beginner feature; the observer can answer the vignette gate.*
*2026-10-30 (Builder, branch `claude/relaxed-davinci-ti73cu`) — **v0.504.5: pictures stacked before v0.504.2 get the stored-preview border trim via a one-off boot-time job** (`pipeline.backfill_unedited_preview_trims`); slice (1) of the ⭐ entry is done. **START HERE NEXT RUN:** Builder: the ⭐ entry's (4) the dark ring (`--mosaic` check), then the first render's speed (engine).*
*2026-10-30 (Scout, branch `claude/exciting-wozniak-1xi45k`) — **QA rotation sweep (3), new angle: a successful ASTAP whose `.ini` carries `nan`/`inf` — a NaN centre was stored NULL (the `.wcs` fallback never ran), an inf one broke `refresh_target_stats`; Scout-fixed, v0.504.4** (`_parse_astap_ini`). Inbox: the same four, owner-gated. Suite 8399 passed / 7 skipped; dogfood `--mosaic` CLEAN (trim 7.9 %). **START HERE NEXT RUN:** Builder: the rest of the ⭐ entry. **Rotation: (3) done → next sweep is (4).***

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
