# Current focus — AstroStack

> **Short on purpose (AGENTS.md: "short, dated, the Scout keeps it current").** One dated line per run goes at the
> top of *Run log*; keep about the last ten and move older lines, whole and in order, to `docs/archive/`. Detail
> belongs in `docs/PROCESS-NOTES.md`, never here. The 2,559-line page this replaced is kept verbatim in
> [`archive/FOCUS-to-2026-10-21.md`](archive/FOCUS-to-2026-10-21.md) — nothing was deleted.

## Front of the queue (2026-10-29)

**No ungated bug is open. First: the rest of the owner's ⭐ entry from #1317 (unedited pictures' ragged border, and
speed) — Full-res PNG + archive trimmed in v0.503.23, repeat downloads cached in v0.503.24, "Finish my unedited pictures" v0.504.0, the menu hint's size v0.504.1, stored preview / share JPEG / wallpaper for new stacks v0.504.2, Adjust → Save v0.504.3, older previews v0.504.5; (4) the dark ring checked 2026-10-30 and filed as the first Bugs entry (gated on the S30's measured vignette); only the first render's speed remains** (in "Features that serve real workflows"; ⭐ is always
taken first). Then a Builder should take a beginner feature from that section, or dogfood (`--mosaic --editor`)
and file what it finds. Recently closed: a non-finite number in ASTAP's `.ini` reads as missing (v0.504.4, Scout sweep (3)); an editor export no longer moves the picture the per-panel hold asks about (v0.503.25, Scout sweep (2)); a `NaN`/`Infinity` body literal is a 422, not a 500 (v0.503.22, Scout sweep (4)); a set-but-wrong ASTAP path now says what is wrong with it (v0.503.21, Scout sweep (3)); the walk-away per-panel readability hold compares a panel with the picture standing (v0.503.20, Scout sweep (2)); an ASTAP that is there but can't be started now reads as a setup
problem (v0.503.19, Scout sweep (3)); a legacy North-up save on a mosaic is recovered again (v0.503.18, Scout sweep (1)); an upload no longer replaces a sub that reached `incoming/` mid-stream (v0.503.17, Scout sweep (4)); a mosaic panel left a few readable subs vs the walk-away hold (v0.503.16); the deepening reel's shallow night drawn cleaner on a grown mosaic (v0.503.15); one night, one dark window (v0.503.10); the hung ffmpeg decoder vs Cancel (v0.503.8); the walk-away missing-files hold on a mosaic panel (v0.503.5); Compare's Split/Blink on a grown mosaic (v0.503.1); the Scout's 2026-10-21 per-part entry closed with v0.502.40 (readiness / Dashboard
progress / Tonight badge); a dogfood pass found and fixed the week plan's same-sky flip (v0.502.41); the Scout's sweep (4) fixed a merge that
deleted a folder a stack was still writing into (v0.502.42). After that, a Builder with nothing ungated should take a beginner feature from "Features that serve
real workflows" in [`IMPROVEMENTS.md`](IMPROVEMENTS.md), or dogfood (`--mosaic --editor`) and file what it finds.

**Gated, do not start:** the un-located-panel entry (third in Bugs) waits on the owner's hint-shape answer; the
other LEADs and ⚪ notes in Bugs wait on owner/observer measurements — read each one's gate first, and do not
re-litigate a stand-down that carries numbers. **Issue inbox:** #878, #880, #903, #1015 — all previously acted-on
and owner-gated, none updated since 2026-10-12 (re-checked 2026-10-30).

## QA rotation (Scout)

Order (AGENTS.md roles): (1) preview↔export parity at mosaic scale → (2) mosaic/walk-away per-panel divergence →
(3) ASTAP/ffmpeg filesystem side effects with a stub binary → (4) the webapp routers. **Last swept: (3), 2026-10-30
→ next sweep is (4).** Each (3) sweep must find a *new* angle — the list of angles already run is in the
`Sweep (3)` entries of `docs/PROCESS-NOTES.md` (grep `sweep (3)`).

## Run log (newest first)

*2026-10-30 (Builder, branch `claude/relaxed-davinci-vwa67t`) — **the ⭐ entry's (4), the dark ring: Auto does not remove it; measured cause is the per-frame `Background2D` flatten leaving a −24 ADU rim (20 % vignette, 1000 ADU sky) along every sub's edge, which the canvas border receives alone; filed as the first Bugs entry with two tried-and-insufficient tweaks and a candidate (a radial synthetic flat), gated on the S30's real fall-off.** No code changed. **START HERE NEXT RUN:** Builder: the ⭐ entry's first-render speed, or a beginner feature; the observer can answer the vignette gate.*
*2026-10-30 (Builder, branch `claude/relaxed-davinci-ti73cu`) — **v0.504.5: pictures stacked before v0.504.2 get the stored-preview border trim via a one-off boot-time job** (`pipeline.backfill_unedited_preview_trims`); slice (1) of the ⭐ entry is done. **START HERE NEXT RUN:** Builder: the ⭐ entry's (4) the dark ring (`--mosaic` check), then the first render's speed (engine).*
*2026-10-30 (Scout, branch `claude/exciting-wozniak-1xi45k`) — **QA rotation sweep (3), new angle: a successful ASTAP whose `.ini` carries `nan`/`inf` — a NaN centre was stored NULL (the `.wcs` fallback never ran), an inf one broke `refresh_target_stats`; Scout-fixed, v0.504.4** (`_parse_astap_ini`). Inbox: the same four, owner-gated. Suite 8399 passed / 7 skipped; dogfood `--mosaic` CLEAN (trim 7.9 %). **START HERE NEXT RUN:** Builder: the rest of the ⭐ entry. **Rotation: (3) done → next sweep is (4).***
*2026-10-30 (Builder, branch `claude/relaxed-davinci-dtngwa`) — **v0.504.3: History's "Adjust → Save" on an unedited mosaic keeps the border trim** (`render_stack_png(crop=)`, `save_stack_preview`). **START HERE NEXT RUN:** Builder: the rest of the ⭐ entry — the pre-v0.504.2 preview backfill, (4) the dark ring.*
*2026-10-30 (Builder, branch `claude/relaxed-davinci-6iepcu`) — **v0.504.2: a fresh unedited mosaic's stored preview, share JPEG and wallpaper are trimmed of the ragged border** (`pipeline.trim_unedited_stored_preview`, `preview_crop` recorded; `--mosaic` 26,801 no-coverage px → 0). **START HERE NEXT RUN:** Builder: the rest of the ⭐ entry — pre-v0.504.2 previews (backfill), Adjust → Save trim, (4) the dark ring.*
*2026-10-29 (Builder, branch `claude/relaxed-davinci-qovgg5`) — **v0.504.1: the Full-res PNG menu hint prints the file's own size (an unedited mosaic's trimmed size, an edit's crop) instead of the canvas** (`pipeline.full_res_png_size`, `…/full-res-png/size`). **START HERE NEXT RUN:** Builder: the rest of the ⭐ entry — share JPEG / wallpaper trim (with `preview_crop` recorded), (4) the dark ring.*
*2026-10-29 (Builder, branch `claude/relaxed-davinci-uv0ayj`) — **v0.504.0: the ⭐ entry's part (2) — "Finish my unedited pictures" in Settings → Maintenance applies Auto to every displayed picture with no saved recipe** (`webapp.finishunedited`, `submit_finish_unedited_pictures`). **START HERE NEXT RUN:** Builder: the rest of the ⭐ entry — share JPEG / wallpaper trim (with `preview_crop` recorded), the `fullres.ts` size hint, (4) the dark ring.*
*2026-10-29 (Scout, branch `claude/exciting-wozniak-6ya1y4`) — **QA rotation sweep (2), new angle: which run v0.503.20's per-panel hold calls "the picture standing" — an editor export copies its source's `n_frames_used` under a later timestamp, won the tie, and re-held repro A; Scout-fixed, v0.503.25** (`_subs_on_record_at_picture`). Inbox: the same four, owner-gated. Suite 8363 passed / 7 skipped; dogfood `--mosaic` CLEAN (trim 7.9 %). **START HERE NEXT RUN:** Builder: the rest of #1317's ⭐ entry. **Rotation: (2) done → next sweep is (3).***
*2026-10-29 (Builder, branch `claude/relaxed-davinci-j7rbj6`) — **v0.503.24: the ⭐ entry's part (3) — a repeat Full-res PNG comes off `<stem>_fullres.cache` (`pipeline.cached_run_full_res_png`; 26 s → 0.1 s at 5000×7000), a second click waits for the running render, and a ≥ 4 MP picture toasts "Preparing your full-size picture…"** (`fullres.announceFullResDownload`). **START HERE NEXT RUN:** Builder: the rest of the ⭐ entry — share JPEG / wallpaper via a trimmed stored preview with `preview_crop`, (2) "Finish my unedited pictures", (4) the dark ring; the first render's own speed is an engine change.*
*2026-10-29 (Builder, branch `claude/relaxed-davinci-ls9zd1`) — **v0.503.23: the ⭐ entry's first slice — an unedited mosaic's Full-res PNG and archive picture trim the ragged border by Auto's own rule** (`pipeline.unedited_border_trim`; `--mosaic` 907×615 with 26,801 no-coverage px → 875×587 with 0, 7.9 %). Suite 8354 passed / 7 skipped. **START HERE NEXT RUN:** Builder: the rest of the ⭐ entry — share JPEG / wallpaper via a trimmed stored preview with `preview_crop` recorded, then (2) "Finish my unedited pictures", (3) speed, (4) the dark ring.*

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
