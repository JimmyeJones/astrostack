# Current focus — AstroStack

> **Short on purpose (AGENTS.md: "short, dated, the Scout keeps it current").** One dated line per run goes at the
> top of *Run log*; keep about the last ten and move older lines, whole and in order, to `docs/archive/`. Detail
> belongs in `docs/PROCESS-NOTES.md`, never here. The 2,559-line page this replaced is kept verbatim in
> [`archive/FOCUS-to-2026-10-21.md`](archive/FOCUS-to-2026-10-21.md) — nothing was deleted.

## Front of the queue (2026-11-11)

**No ungated bug is open.** The editor Download PNG / Share / Print pile-up shipped as v0.506.20; the
trim-after-shrink of an unedited canvas over 8000 px shipped as v0.506.19. The non-UTF-8 sub-file-name scan abort shipped as v0.506.18. The `._*.fit` sidecar half of
the Scout 2026-11-03 entry shipped as v0.505.10; its `.recycle/` / `.Trash-*/` / visible `.zfs/` half (one skip) waits on
the owner. The owner's ⭐ colour-pattern entry is on HOLD for his per-temperature numbers; the dark ring waits on a
diagnostic (below).

**Gated, do not start:** the un-located-panel entry (Scout 2026-10-19 in Bugs) waits on diagnostic `mosaic_panel_hints` v2
(v0.506.10), the dark ring on `sky_falloff` v3 (v0.506.16) and the #878 headline LEAD on `twin_target_overcount` v1 (v0.506.8); the
other LEADs and ⚪ notes in Bugs wait on owner/observer measurements — read each one's gate first, and do not
re-litigate a stand-down that carries numbers. **Issue inbox:** #878, #880, #903, #1015 — all previously acted-on
and owner-gated, none updated since 2026-10-12 (re-checked 2026-11-11, Scout `optimistic-cannon-usq0cn`, again by `mh7yxx`, `jy9aay`, `dsfjim` and `x5qu3g`). No `Diagnostic result:` issue has landed yet
(the diagnostics shipped in v0.506.0 / v0.506.1 run after the owner's next update).

## QA rotation (Scout)

Order (AGENTS.md roles): (1) preview↔export parity at mosaic scale → (2) mosaic/walk-away per-panel divergence →
(3) ASTAP/ffmpeg filesystem side effects with a stub binary → (4) the webapp routers. **Last swept: (2), 2026-11-11
→ next sweep is (3).** Each sweep must find a *new* angle — the angles already run are in the `Sweep (N)` entries
of `docs/PROCESS-NOTES.md` (grep `sweep (1)`).

## Run log (newest first)

*2026-11-11 (Builder, branch `claude/focused-noether-e1jr71`, second task) — **v0.506.20: the editor's Download PNG / Share / Print files are reclaimed** (a newer click replaces the older file of the same kind, `output.replace_older_editor_downloads`; Delete and Prune remove them, `storage._delete_editor_downloads`). Four behavioural tests fail before. **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate or a diagnostic result arrives — a beginner feature or a dogfood pass; Scout: sweep (3), and file `Diagnostic result:` issues when they land.*
*2026-11-11 (Builder, branch `claude/focused-noether-e1jr71`) — **v0.506.19: an unedited trimmed canvas wider than the 8000 px Full-res cap keeps its true size** (`thumbnail.full_res_load_width` loads at the *trimmed* width; `pipeline.full_res_png_size` replays the same grid, so the menu and the archive's true-size check follow the file). All three webapp regression tests fail before. **START HERE NEXT RUN:** Builder: the editor-download pile-up (🟡 S, Bugs); Scout: sweep (2), and file `Diagnostic result:` issues when they land.*
*2026-11-11 (Scout, branch `claude/optimistic-cannon-x5qu3g`) — **QA rotation sweep (2), new angle: the registry centre's panel floor (`library._main_object_panels`, ≥ 1 % of the *whole target's* subs) on uneven S30 mosaics — CLEAN** (every panel kept up to 4:1 unevenness at 35,894 subs; only a ~10:1 column, i.e. two layouts under one name, is dropped — 0.85° centre shift, recorded in PROCESS-NOTES, not filed). Inbox: the same four, owner-gated; no `Diagnostic result:` yet. Dogfood `--mosaic` CLEAN (trim 7.9 %). Suite 8699 passed / 7 skipped. **START HERE NEXT RUN:** Builder: the editor-download pile-up or the trim-after-shrink (both 🟡 S, Bugs); Scout: sweep (3), and file `Diagnostic result:` issues when they land.*
*2026-11-11 (Scout, branch `claude/optimistic-cannon-dsfjim`) — **QA rotation sweep (1), new angle: the full-size archive and the Full-res PNG of an *unedited, trimmed* canvas wider than the 8000 px cap — one bug filed reproduced** (`render_preview_png_full_res` area-averages the canvas to the cap *before* `unedited_border_trim` cuts, so a 9000 px canvas trimmed to a true 7200 px comes out 6400 px, and the archive counts it full-res with no `_reduced_size.txt`). Inbox: the same four, owner-gated; no `Diagnostic result:` yet. Dogfood `--mosaic` CLEAN (trim 7.9 %). Suite 8699 passed / 7 skipped. **START HERE NEXT RUN:** Builder: the editor-download pile-up or the trim-after-shrink (both 🟡 S, Bugs); Scout: sweep (2), and file `Diagnostic result:` issues when they land.*
*2026-11-11 (Scout, branch `claude/optimistic-cannon-jy9aay`) — **QA rotation sweep (4), new angle: the editor's download-by-job routes (`…/editor/png|share|print/{job_id}`) and the files their jobs leave behind — one bug filed reproduced** (every Download PNG / Share / Print writes a timestamped file into `output/` that `purge_stack_run` never reclaims; ~43 MB per mosaic PNG). The job-id-vs-URL mismatch read clean (the client always pairs a job with its own run). Inbox: the same four, owner-gated; no `Diagnostic result:` yet. Dogfood `--mosaic` CLEAN (trim 7.9 %). Suite 8693 passed / 7 skipped. **START HERE NEXT RUN:** Builder: the editor-download pile-up (🟡 S, Bugs); Scout: sweep (1), and file `Diagnostic result:` issues when they land.*
*2026-11-11 (Builder, branch `claude/focused-noether-paumkw`) — **v0.506.18: a sub whose file name is not valid UTF-8 is one unreadable sub, never a failed scan** (`ingest.name_is_valid_text` in `ingest_files` and the new-target hold-back; `scan_and_organize` lets the other targets ingest when one raises, then re-raises; `RingBufferLogHandler` sanitises surrogates so `/api/logs` still encodes). All five behavioural tests fail before. **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate or a diagnostic result arrives; Scout: sweep (4), and file `Diagnostic result:` issues when they land.*
*2026-11-11 (Scout, branch `claude/optimistic-cannon-mh7yxx`) — **QA rotation sweep (3), new angle: ASTAP exits 0 but leaves a cut-short `.wcs` sidecar — CLEAN** (`wcs_text_is_usable` passes some cut headers, but a CTYPE-only cut is refused on save and every wrong-scale cut is dropped by the stack's footprint / plate-scale guards at 4, 6 and 12 subs, flagged rejected with a reason). Inbox: the same four, owner-gated; no `Diagnostic result:` yet. Dogfood `--mosaic` CLEAN (trim 7.9 %). Suite 8691 passed / 7 skipped. **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate or a diagnostic result arrives; Scout: sweep (4), and file `Diagnostic result:` issues when they land.*
*2026-11-11 (Scout, branch `claude/optimistic-cannon-usq0cn`) — **QA rotation sweep (3), new angle: the bytes ASTAP *prints* — one bug, Scout-fixed as v0.506.17** (`ASTAPSolver._run_astap` decoded ASTAP's console strictly; one non-UTF-8 byte after a good solve stored the frame unsolved with a decoder traceback and skipped the ladder; now `errors="replace"`) **and one filed reproduced: a non-UTF-8 sub file name aborts every scan** (SQLite refuses the surrogate in `Project.add_frame`; 🟡 S, Bugs). Inbox: the same four, owner-gated; no `Diagnostic result:` yet. Dogfood `--mosaic` CLEAN (trim 7.9 %). Suite 8693 passed / 7 skipped. **START HERE NEXT RUN:** Builder: the non-UTF-8 file-name scan abort (🟡 S, Bugs); Scout: sweep (4), and file `Diagnostic result:` issues when they land.*
*2026-11-11 (Builder, branch `claude/focused-noether-dtzzop`) — **no app change: nothing ungated; dogfood `--mosaic --editor --restack --deep --calibration` CLEAN** (a combination no pass had run together: calibrated restack records dark + flat applied and the note withdraws; reel 3 → 6 subs, noise-delta ratio 1.642 pixel-exact; Auto trim 7.9 %; both editor drives re-render all 21 ops; deep frames table 301 → 601 of 1,200 rows). v0.506.15's reel lock re-read before its soak ends: sig written after the atomic replace, so an unlocked reader waits — sound. Suite 8691 passed / 7 skipped. **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate or a diagnostic result arrives; Scout: sweep (3), and file `Diagnostic result:` issues when they land.*
*2026-11-11 (Scout, branch `claude/optimistic-cannon-mw5sgl`) — **collision, no app change:** sweep (2) took the same `sky_falloff` angle as `fwsbuf` and wrote the same fix; dropped for `main`'s v0.506.16 (`one_panel` skips un-solved mosaic subs instead of trusting a hint). Extra measurements in PROCESS-NOTES: v2's bias depends on panel *order* (rotation-shot < 0.005, block-shot 3×3 0.975–0.982). Inbox: the same four, owner-gated; no `Diagnostic result:` yet. Dogfood `--mosaic` CLEAN. **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate or a diagnostic result arrives; Scout: sweep (3) — push a `docs:` claim before starting a carry-forward item.*

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
