# Current focus — AstroStack

> **Short on purpose (AGENTS.md: "short, dated, the Scout keeps it current").** One dated line per run goes at the
> top of *Run log*; keep about the last ten and move older lines, whole and in order, to `docs/archive/`. Detail
> belongs in `docs/PROCESS-NOTES.md`, never here. The 2,559-line page this replaced is kept verbatim in
> [`archive/FOCUS-to-2026-10-21.md`](archive/FOCUS-to-2026-10-21.md) — nothing was deleted.

## Front of the queue (2026-10-28)

**No ungated bug is open. First: the owner's ⭐ entry from #1317 — a picture he never edited comes out of
Full-res PNG with a ragged colour-confetti border, and slowly** (in "Features that serve real workflows"; ⭐ is always
taken first). Then a Builder should take a beginner feature from that section, or dogfood (`--mosaic --editor`)
and file what it finds. Recently closed: a `NaN`/`Infinity` body literal is a 422, not a 500 (v0.503.22, Scout sweep (4)); a set-but-wrong ASTAP path now says what is wrong with it (v0.503.21, Scout sweep (3)); the walk-away per-panel readability hold compares a panel with the picture standing (v0.503.20, Scout sweep (2)); an ASTAP that is there but can't be started now reads as a setup
problem (v0.503.19, Scout sweep (3)); a legacy North-up save on a mosaic is recovered again (v0.503.18, Scout sweep (1)); an upload no longer replaces a sub that reached `incoming/` mid-stream (v0.503.17, Scout sweep (4)); a mosaic panel left a few readable subs vs the walk-away hold (v0.503.16); the deepening reel's shallow night drawn cleaner on a grown mosaic (v0.503.15); one night, one dark window (v0.503.10); the hung ffmpeg decoder vs Cancel (v0.503.8); the walk-away missing-files hold on a mosaic panel (v0.503.5); Compare's Split/Blink on a grown mosaic (v0.503.1); the Scout's 2026-10-21 per-part entry closed with v0.502.40 (readiness / Dashboard
progress / Tonight badge); a dogfood pass found and fixed the week plan's same-sky flip (v0.502.41); the Scout's sweep (4) fixed a merge that
deleted a folder a stack was still writing into (v0.502.42). After that, a Builder with nothing ungated should take a beginner feature from "Features that serve
real workflows" in [`IMPROVEMENTS.md`](IMPROVEMENTS.md), or dogfood (`--mosaic --editor`) and file what it finds.

**Gated, do not start:** the un-located-panel entry (third in Bugs) waits on the owner's hint-shape answer; the
other LEADs and ⚪ notes in Bugs wait on owner/observer measurements — read each one's gate first, and do not
re-litigate a stand-down that carries numbers. **Issue inbox:** #878, #880, #903, #1015 — all previously acted-on
and owner-gated, none updated since 2026-10-12 (re-checked 2026-10-28).

## QA rotation (Scout)

Order (AGENTS.md roles): (1) preview↔export parity at mosaic scale → (2) mosaic/walk-away per-panel divergence →
(3) ASTAP/ffmpeg filesystem side effects with a stub binary → (4) the webapp routers. **Last swept: (1), 2026-10-28
→ next sweep is (2).** Each (3) sweep must find a *new* angle — the list of angles already run is in the
`Sweep (3)` entries of `docs/PROCESS-NOTES.md` (grep `sweep (3)`).

## Run log (newest first)

*2026-10-28 (Scout, branch `claude/blissful-einstein-4u2f5p`) — **QA rotation sweep (1), new angle: every picture download (Full-res PNG, JPEG, both turned North-up, the wallpaper) measured against the stored preview over HTTP on the decimated `--big` mosaic — CLEAN** (smoothed diff ≤ 1.54/255; the raw 23/255 is star dots under a half-pixel offset, not tone). The "Gallery lightbox prev/next" lead does not exist (no prev/next) and is closed. Inbox: the same four, owner-gated. Suite 8344 passed / 7 skipped; dogfood `--mosaic --big` CLEAN (trim 7.9 %). Ran beside #1320's sweep (4). **START HERE NEXT RUN:** Builder: #1317's ⭐ entry. **Rotation: (1) done → next sweep is (2).***
*2026-10-28 (Scout, branch `claude/blissful-einstein-m8o5zc`) — **QA rotation sweep (4), new angle: bare `NaN`/`Infinity` JSON literals into every mutating route's body — nothing reaches disk, but 86 of 269 rejections crashed into 500s (FastAPI's 422 echoing the input through an `allow_nan=False` encoder); Scout-fixed, v0.503.22** (`main._install_validation_handler`). Inbox: the same four, owner-gated. Suite 8342 passed / 7 skipped; dogfood `--mosaic` CLEAN (trim 7.9 %). Ran beside #1317 (owner answers, docs). **START HERE NEXT RUN:** Builder: #1317's ⭐ owner entry (the unedited Full-res PNG border), else a beginner feature or dogfood. **Rotation: (4) done → next sweep is (1).***
*2026-10-28 (Builder, branch `claude/pensive-hawking-9jw3c3`) — **v0.503.21: a set-but-wrong Settings `astap_path` is cleaned / searched / named** (`_clean_user_path`, `astap_path_problem`). **v0.503.20: the walk-away per-panel readability hold asks about the subs each panel had when the standing picture was made** (`_subs_on_record_at_picture`, `frames.ingested_at` ≤ the best run's `timestamp_utc`); the Scout's repros A and B now stack. **START HERE NEXT RUN:** Builder: any ⭐ owner entry, else a beginner feature or dogfood.*
*2026-10-28 (Scout, branch `claude/blissful-einstein-oxratg`) — **QA rotation sweep (3), new angle: the binary the
app is *told* to run — a set-but-wrong Settings `astap_path` (space, quotes, host path, `astap_cli`, the folder)
shadows the working bundled ASTAP (`find_astap` never falls back) and the screens advise installing ASTAP or adding a
database he has; filed reproduced in Bugs.** Inbox: the same four, owner-gated. Suite 8326 passed / 7 skipped;
dogfood `--mosaic` CLEAN (trim 7.9 %). **START HERE NEXT RUN:** Builder: the panel-hold entry, then this one.
**Rotation: (3) done → next sweep is (4).***
*2026-10-28 (Builder, branch `claude/pensive-hawking-4fcqpx`) — **v0.503.19: an ASTAP that is there but can't be started is a setup problem** (`ASTAPCannotRunError`, `SOLVE_SETUP_ASTAP_CANNOT_RUN`; Target banner, Dashboard cue via `astapReadiness` `runs === false`, Settings badge). **START HERE NEXT RUN:** Builder: the Scout's walk-away per-panel hold entry (top of Bugs).*
*2026-10-28 (Scout, branch `claude/blissful-einstein-13a3el`) — **QA rotation sweep (2), new angle: what the per-panel readability hold compares a panel *with* — subs on record, not the standing picture; an off-line newest night on one panel, or a brand-new off-line panel, holds a strictly better stack with "would be much thinner / out of the picture" (`_panels_with_nothing_readable`); filed reproduced in Bugs.** Inbox: the same four, owner-gated. Suite 8323 passed / 7 skipped; dogfood `--mosaic` CLEAN (trim 7.9 %). Ran beside #1313's sweep (1). **START HERE NEXT RUN:** Builder: the ASTAP entry, then this one. **Rotation: (2) done → next sweep is (3).***
*2026-10-28 (Scout, branch `claude/blissful-einstein-dck0um`) — **QA rotation sweep (1), new angle: the legacy North-up recovery asked the master's WCS at the preview grid's centre, so a pre-v0.288 North-up save on a mosaic read as un-rotated (14 of 16 cases); Scout-fixed, v0.503.18** (`recovered_north_up_deg`). `noisedelta` held by reading. Inbox: the same four, owner-gated. Suite 8321 passed / 7 skipped; dogfood `--mosaic` CLEAN (trim 7.9 %). Ran beside #1312's sweep (4). **START HERE NEXT RUN:** Builder: the un-startable ASTAP entry (top of Bugs). **Rotation: (1) done → next sweep is (2).***
*2026-10-28 (Scout, branch `claude/blissful-einstein-ptp2yd`) — **QA rotation sweep (4), new angle: `upload`, the one router that writes into `incoming/`, against §10 — a sub landing at the same name *while* an upload streamed was silently replaced (`os.replace` after a pre-stream `exists()`); Scout-fixed as v0.503.17 (`_place_new`, create-only `os.link`).** Inbox: the same four, owner-gated. Suite 8318 passed / 7 skipped; dogfood `--mosaic` CLEAN (trim 7.9 %). **START HERE NEXT RUN:** Builder: the un-startable-ASTAP entry. **Rotation: (4) done → next sweep is (1).***
*2026-10-28 (Builder, branch `claude/pensive-hawking-3f01rd`) — **v0.503.15: the deepening reel's shallow night no longer reads cleaner on a grown/shrunk mosaic** (`render_deepening_frames` loads each night at the newest frame's sky scale, places it linear + nearest before the stretch; grown 26.1 → 49.3 vs deep 37.7); **v0.503.16: the walk-away hold also holds a mosaic panel keeping under half its subs** (`_panels_with_nothing_readable` `thinned`, additive `panels_thinned`). Suite 8315 passed / 7 skipped before the second. **START HERE NEXT RUN:** Builder: the un-startable ASTAP entry (now top of Bugs).*
*2026-10-28 (Scout, branch `claude/blissful-einstein-h93a4i`) — **QA rotation sweep (3), new angle: an ASTAP that is present but cannot be started (0644 / `noexec`, wrong-format binary) — no filesystem side effect, but it reads "ASTAP found" everywhere and every sub gets an exception string as an ordinary solve failure (`_run_astap` catches only `TimeoutExpired`; `classify_solve_setup_error` misses it); filed reproduced in Bugs.** Inbox: the same four, owner-gated. Suite 8313 passed / 7 skipped; dogfood `--mosaic` CLEAN (trim 7.9 %). **START HERE NEXT RUN:** Builder: the reel entry, the panel-hold entry, then this one. **Rotation: (3) done → next sweep is (4).***

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
