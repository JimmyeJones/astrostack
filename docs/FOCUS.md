# Current focus — AstroStack

> **Short on purpose (AGENTS.md: "short, dated, the Scout keeps it current").** One dated line per run goes at the
> top of *Run log*; keep about the last ten and move older lines, whole and in order, to `docs/archive/`. Detail
> belongs in `docs/PROCESS-NOTES.md`, never here. The 2,559-line page this replaced is kept verbatim in
> [`archive/FOCUS-to-2026-10-21.md`](archive/FOCUS-to-2026-10-21.md) — nothing was deleted.

## Front of the queue (2026-11-11)

**No ungated bug is open:** the full-container-temp-dir solve misreport shipped as v0.506.22. The editor Download PNG / Share / Print pile-up shipped as v0.506.20; the
trim-after-shrink of an unedited canvas over 8000 px shipped as v0.506.19. The non-UTF-8 sub-file-name scan abort shipped as v0.506.18. The `._*.fit` sidecar half of
the Scout 2026-11-03 entry shipped as v0.505.10; its `.recycle/` / `.Trash-*/` / visible `.zfs/` half (one skip) waits on
the owner. The owner's ⭐ colour-pattern entry is on HOLD for his per-temperature numbers; the dark ring waits on a
diagnostic (below).

**Gated, do not start:** the un-located-panel entry (Scout 2026-10-19 in Bugs) waits on diagnostic `mosaic_panel_hints` v2
(v0.506.10), the dark ring on `sky_falloff` v3 (v0.506.16) and the #878 headline LEAD on `twin_target_overcount` v1 (v0.506.8); the
other LEADs and ⚪ notes in Bugs wait on owner/observer measurements — read each one's gate first, and do not
re-litigate a stand-down that carries numbers. **Issue inbox:** #878, #880, #903, #1015 — all previously acted-on
and owner-gated, none updated since 2026-10-12 (re-checked 2026-11-11, Scout `optimistic-cannon-usq0cn`, again by `mh7yxx`, `jy9aay`, `dsfjim`, `x5qu3g`, `hv4l4e`, `vrbblx`, `i0xwhr`, `geies9` and `vlbnkm`). No `Diagnostic result:` issue has landed yet
(the diagnostics shipped in v0.506.0 / v0.506.1 run after the owner's next update).

## QA rotation (Scout)

Order (AGENTS.md roles): (1) preview↔export parity at mosaic scale → (2) mosaic/walk-away per-panel divergence →
(3) ASTAP/ffmpeg filesystem side effects with a stub binary → (4) the webapp routers. **Last swept: (3), 2026-11-11
→ next sweep is (4).** Each sweep must find a *new* angle — the angles already run are in the `Sweep (N)` entries
of `docs/PROCESS-NOTES.md` (grep `sweep (1)`).

## Run log (newest first)

*2026-11-11 (Builder, branch `claude/focused-noether-po8hte`) — **v0.506.22: a full container temp dir is one setup problem** (`ASTAPSolver._solve_once` → `ASTAPScratchError`, canonical `solve_failed:solve scratch full`, one `run_qc_and_solve` warning, Target banner `kind: "scratch"`, scratch-full reason bucketed "not located yet"). Six of seven new tests fail before. **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate or a diagnostic result arrives — a beginner feature or a dogfood pass; Scout: sweep (4), and file `Diagnostic result:` issues when they land.*
*2026-11-11 (Scout, branch `claude/optimistic-cannon-vlbnkm`) — **QA rotation sweep (3), new angle: the solve's own scratch copy hitting a *full container temp dir* (`ASTAPSolver._solve_once`, `TMPDIR` on a 3 MB tmpfs) through a real scan + solve — side effects CLEAN; one bug filed reproduced (🟢 S)** — 12/12 subs stored `solve_failed:OSError: [Errno 28] …`, the job ends clean (DB on another filesystem, so no `disk_full`), nothing is logged, and the summary tells a beginner to check his subs for trails or fog; this refutes the premise of the 2026-10-20 stand-down. Inbox: the same four, owner-gated; no `Diagnostic result:` yet. Dogfood `--mosaic` CLEAN (trim 7.9 %). Suite 8715 passed / 7 skipped. **START HERE NEXT RUN:** Builder: the full-temp-dir solve misreport (🟢 S, Bugs, ungated); Scout: sweep (4), and file `Diagnostic result:` issues when they land.*
*2026-11-11 (Scout, branch `claude/optimistic-cannon-geies9`) — **QA rotation sweep (2), new angle: the star mask's canvas-wide 0.15 floor (`edit/starmask.star_mask`) on an uneven mosaic — CLEAN** (a thin panel's louder grain does clear the floor — at 4:1 on 11–78 % of its sky — but `stars.reduce` / `stars.boost_nebula` move it by ≤ 2 of 255, under the panel's own pre-existing mismatch and toward the deep panel; at the dogfood's 2:1 under one level; neither op is in Auto). Inbox: the same four, owner-gated; no `Diagnostic result:` yet. Dogfood `--mosaic` CLEAN (trim 7.9 %). Suite 8715 passed / 7 skipped. **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate or a diagnostic result arrives — a beginner feature or a dogfood pass; Scout: sweep (3), and file `Diagnostic result:` issues when they land.*
*2026-11-11 (Scout, branch `claude/optimistic-cannon-i0xwhr`) — **QA rotation sweep (1), new angle: the Full-res PNG's STF tone against the stored preview on canvases wider than the 8000 px cap, after v0.506.19's finer load grid (`full_res_load_width`) — CLEAN** (the fix moves the download toward the preview's native-grid STF; untrimmed 12000 / 16000 px canvases differ from the preview by mean 1.4 / 2.6 of 255, sky median equal; the rest is the documented stars non-linearity). Inbox: the same four, owner-gated; no `Diagnostic result:` yet. Dogfood `--mosaic` CLEAN (trim 7.9 %). Suite 8715 passed / 7 skipped. **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate or a diagnostic result arrives — a beginner feature or a dogfood pass; Scout: sweep (2), and file `Diagnostic result:` issues when they land.*
*2026-11-11 (Builder, branch `claude/focused-noether-mpprlu`) — **v0.506.21: a sub whose file time is in the future (source clock ahead) is ingested by the folder watcher after the ordinary quiet period** (`watcher.StabilityTracker.update`; before, it never went stable and no batch fired — the watcher is the only automatic route in, and incoming-lag read the folder as still being written). Was the ⚪ Scout 2026-08-27 #8 hardening note in Bugs. All three new tests fail before. **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate or a diagnostic result arrives; Scout: sweep (4), and file `Diagnostic result:` issues when they land.*
*2026-11-11 (Scout, branch `claude/optimistic-cannon-vrbblx`) — **QA rotation sweep (4), new angle: what the observer's read-only token can make the seven allowlisted GETs (`_READONLY_GET_PATHS`) write or disclose, with every query parameter they take, after a real scan + stack of subs carrying distinctive `SITELAT`/`SITELONG` and the same `site_lat`/`site_lon` in Settings — CLEAN** (no file written but SQLite's WAL reader index; the coordinates appear in none of the answers; paths only container-relative; everything else 403). Inbox: the same four, owner-gated; no `Diagnostic result:` yet. Dogfood `--mosaic` CLEAN (trim 7.9 %). Suite 8712 passed / 7 skipped. **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate or a diagnostic result arrives — a beginner feature or a dogfood pass; Scout: sweep (1), and file `Diagnostic result:` issues when they land.*
*2026-11-11 (Scout, branch `claude/optimistic-cannon-hv4l4e`) — **QA rotation sweep (3), new angle: a mosaic panel that fails every rung plus one sub hung past the timeout, through the real solve pool — CLEAN** (1 ASTAP run per solved sub, 6 per never-solving sub, 3 for the hung one; scratch empty, no orphans, `incoming/` identical; `GET /api/system`'s uncached `-h` probe read clean). Inbox: the same four, owner-gated; no `Diagnostic result:` yet. Dogfood `--mosaic` CLEAN (trim 7.9 %). Suite 8706 passed / 7 skipped. **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate or a diagnostic result arrives; Scout: sweep (4), and file `Diagnostic result:` issues when they land.*
*2026-11-11 (Builder, branch `claude/focused-noether-e1jr71`, second task) — **v0.506.20: the editor's Download PNG / Share / Print files are reclaimed** (a newer click replaces the older file of the same kind, `output.replace_older_editor_downloads`; Delete and Prune remove them, `storage._delete_editor_downloads`). Four behavioural tests fail before. **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate or a diagnostic result arrives — a beginner feature or a dogfood pass; Scout: sweep (3), and file `Diagnostic result:` issues when they land.*
*2026-11-11 (Builder, branch `claude/focused-noether-e1jr71`) — **v0.506.19: an unedited trimmed canvas wider than the 8000 px Full-res cap keeps its true size** (`thumbnail.full_res_load_width` loads at the *trimmed* width; `pipeline.full_res_png_size` replays the same grid, so the menu and the archive's true-size check follow the file). All three webapp regression tests fail before. **START HERE NEXT RUN:** Builder: the editor-download pile-up (🟡 S, Bugs); Scout: sweep (2), and file `Diagnostic result:` issues when they land.*
*2026-11-11 (Scout, branch `claude/optimistic-cannon-x5qu3g`) — **QA rotation sweep (2), new angle: the registry centre's panel floor (`library._main_object_panels`, ≥ 1 % of the *whole target's* subs) on uneven S30 mosaics — CLEAN** (every panel kept up to 4:1 unevenness at 35,894 subs; only a ~10:1 column, i.e. two layouts under one name, is dropped — 0.85° centre shift, recorded in PROCESS-NOTES, not filed). Inbox: the same four, owner-gated; no `Diagnostic result:` yet. Dogfood `--mosaic` CLEAN (trim 7.9 %). Suite 8699 passed / 7 skipped. **START HERE NEXT RUN:** Builder: the editor-download pile-up or the trim-after-shrink (both 🟡 S, Bugs); Scout: sweep (3), and file `Diagnostic result:` issues when they land.*

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
