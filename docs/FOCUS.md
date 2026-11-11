# Current focus — AstroStack

> **Short on purpose (AGENTS.md: "short, dated, the Scout keeps it current").** One dated line per run goes at the
> top of *Run log*; keep about the last ten and move older lines, whole and in order, to `docs/archive/`. Detail
> belongs in `docs/PROCESS-NOTES.md`, never here. The 2,559-line page this replaced is kept verbatim in
> [`archive/FOCUS-to-2026-10-21.md`](archive/FOCUS-to-2026-10-21.md) — nothing was deleted.

## Front of the queue (2026-11-10)

**No ungated bug is open** (the deepening-reel rebuild race shipped as v0.506.15). A Builder should dogfood
(`--mosaic --editor`) and file what it finds. The `._*.fit` sidecar half of the Scout
2026-11-03 entry shipped as v0.505.10; its `.recycle/` / `.Trash-*/` / visible `.zfs/` half (one skip) waits on the
owner. The owner's ⭐ colour-pattern entry is on HOLD for his per-temperature numbers; the dark ring waits on a
diagnostic (below).

**Gated, do not start:** the un-located-panel entry (second in Bugs) waits on diagnostic `mosaic_panel_hints` v2
(v0.506.10), the dark ring on `sky_falloff` v3 (v0.506.16) and the #878 headline LEAD on `twin_target_overcount` v1 (v0.506.8); the
other LEADs and ⚪ notes in Bugs wait on owner/observer measurements — read each one's gate first, and do not
re-litigate a stand-down that carries numbers. **Issue inbox:** #878, #880, #903, #1015 — all previously acted-on
and owner-gated, none updated since 2026-10-12 (re-checked 2026-11-11, Scout `optimistic-cannon-mw5sgl`). No `Diagnostic result:` issue has landed yet
(the diagnostics shipped in v0.506.0 / v0.506.1 run after the owner's next update).

## QA rotation (Scout)

Order (AGENTS.md roles): (1) preview↔export parity at mosaic scale → (2) mosaic/walk-away per-panel divergence →
(3) ASTAP/ffmpeg filesystem side effects with a stub binary → (4) the webapp routers. **Last swept: (2), 2026-11-10
→ next sweep is (3).** Each sweep must find a *new* angle — the angles already run are in the `Sweep (N)` entries
of `docs/PROCESS-NOTES.md` (grep `sweep (1)`).

## Run log (newest first)

*2026-11-11 (Scout, branch `claude/optimistic-cannon-mw5sgl`) — **collision, no app change:** sweep (2) took the same `sky_falloff` angle as `fwsbuf` and wrote the same fix; dropped for `main`'s v0.506.16 (`one_panel` skips un-solved mosaic subs instead of trusting a hint). Extra measurements in PROCESS-NOTES: v2's bias depends on panel *order* (rotation-shot < 0.005, block-shot 3×3 0.975–0.982). Inbox: the same four, owner-gated; no `Diagnostic result:` yet. Dogfood `--mosaic` CLEAN. **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate or a diagnostic result arrives; Scout: sweep (3) — push a `docs:` claim before starting a carry-forward item.*
*2026-11-10 (Scout, branch `claude/optimistic-cannon-fwsbuf`) — **QA rotation sweep (2), new angle: the dark-ring gate number `sky_falloff` v2 groups pairs by target, but a mosaic target is several fields — one bug, Scout-fixed as v0.506.16** (v2's pairs crossed panels, so each panel's own part of the object read as vignetting: a vignette-free library two-thirds mosaics read 0.70–0.90 against the 0.97 bar; v3 samples a mosaic's fullest panel, `sky_falloff.one_panel`). Inbox: the same four, owner-gated; no `Diagnostic result:` yet. Dogfood `--mosaic` CLEAN (trim 7.9 %). Suite 8689 passed / 7 skipped. **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate or a diagnostic result arrives; Scout: sweep (3), and file `Diagnostic result:` issues when they land.*
*2026-11-10 (Builder, branch `claude/focused-noether-9m2aks`) — **v0.506.15: overlapping deepening-reel requests render once and never serve a half-written file** (`_build_or_get_deepening_reel` per-reel lock; `write_deepening_reel` temp-then-`os.replace`); both regression tests fail before. **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate or a diagnostic result arrives; Scout: sweep (2), and file `Diagnostic result:` issues when they land.*
*2026-11-10 (Scout, branch `claude/optimistic-cannon-55nwei`) — **QA rotation sweep (1), new angle: the whole-library "Full-size versions" archive against a canvas wider than the Full-res PNG's 8000 px cap — one bug, Scout-fixed as v0.506.14** (`picturesarchive.build_full_size_archive` put an 8400 px canvas in at 8000 px and counted it in `n_full_res` with no note, though the card promises "their true size"; now `n_reduced` + `_reduced_size.txt`). Leads read clean: the editor's From-your-image suggestions on a strided proxy, and Pillow's decompression-bomb limit (no app path reopens a full-res PNG). Inbox: the same four, owner-gated; no `Diagnostic result:` yet. Dogfood `--mosaic` CLEAN. Suite 8682 passed / 7 skipped. **START HERE NEXT RUN:** Builder: the deepening-reel race (🟡 S, Bugs); Scout: sweep (2), and file `Diagnostic result:` issues when they land.*
*2026-11-10 (Builder, branch `claude/focused-noether-rbfy5l`) — **v0.506.13: four count labels stop saying "1 frames"/"1 subs"/"1 targets"** (`FrameCountBadge` — the single-frame thin-stack badge, the very case its cue warns about — plus `ContinueTonightCard`, `MergeSuggestionsCard` and `OutdatedTargetsBadge`'s label). Dogfood `--mosaic --dithered --big --closing --editor` otherwise CLEAN (Auto trim 7.9 % mosaic / 30.7 % dithered against its 30.3 % apron; all three editor drives clean; scale diff CLEAN). **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate or a diagnostic result arrives; Scout: sweep (4), and file `Diagnostic result:` issues when they land.*
*2026-11-10 (Scout, branch `claude/optimistic-cannon-cw2u6h`) — **QA rotation sweep (4), new angle: overlapping requests on a GET that builds and caches a file — one bug filed reproduced** (`_build_or_get_deepening_reel`: 24 staggered GETs → 9 full renders, 3 bodies 200 but undecodable; fix is a per-reel lock + temp-then-`os.replace`). Diagnostics payload privacy and the locked JSON stores read clean. Inbox: the same four, owner-gated; no `Diagnostic result:` yet. Dogfood `--mosaic` CLEAN. **START HERE NEXT RUN:** Builder: the deepening-reel race (🟡 S, Bugs); Scout: sweep (1), and file `Diagnostic result:` issues when they land.*
*2026-11-10 (Scout, branch `claude/optimistic-cannon-i30qi1`) — **QA rotation sweep (4), new angle: every image-returning GET route's cache headers against whether its URL changes when its picture does — one bug, Scout-fixed as v0.506.12** (`/api/targets/{safe}/thumbnail`, the Library/Life list/Wishlist/year-card picture at one bare URL, sent no `Cache-Control`, so a browser could keep showing the old picture for days after a new stack or a cover pin; now `no-cache`, as v0.210.7 did for the run preview). Inbox: the same four, owner-gated; no `Diagnostic result:` yet. Dogfood `--mosaic` CLEAN. Suite 8672 passed / 8 skipped (Qt-skip). **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate or a diagnostic result arrives; Scout: sweep (1), and file `Diagnostic result:` issues when they land.*
*2026-11-10 (Builder, branch `claude/focused-noether-zzbnof`) — **v0.506.11: the first-run "Your first image" card says "you're here" instead of linking a step to the page it sits on** (`firstImageSteps.stepIsHere`) — found by a `--empty` dogfood pass: on an empty Library "Open Library"/"Pick a target" were dead self-links, on an empty Gallery "Open a picture"/"Open your edit". Suite 8681 passed / 7 skipped. **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate or a diagnostic result arrives; Scout: sweep (4), and file `Diagnostic result:` issues when they land.*
*2026-11-10 (Scout, branch `claude/optimistic-cannon-mgl6hf`) — **QA rotation sweep (3), new angle: a `sys.addaudithook` tracer over every write-capable call (write-mode `open`/`os.open`, rename, remove, chmod, utime, mkdir, `fits.open(mode='update')`) naming a path under `incoming/`, through scan → QC + stub-ASTAP solve (serial and pool) → all five library diagnostics (direct and the boot job, `webapp.diagnostics`) → a mosaic stack, `copy_to_cache` off — CLEAN** (0 write attempts, 402 read-opens; positive controls fire). Inbox: the same four, owner-gated; no `Diagnostic result:` yet. Dogfood `--mosaic` CLEAN. Suite 8681 passed / 7 skipped. **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate or a diagnostic result arrives; Scout: sweep (4), and file `Diagnostic result:` issues when they land.*
*2026-11-10 (Builder, branch `claude/fervent-allen-dh3hxr`) — **no app change: nothing ungated; dogfood `--mosaic --dithered --closing --editor` CLEAN** (a combination no pass had run together: three editor drives re-render all 21 ops, Undo/Redo apply, taste chips behave; Auto trim 7.9 % mosaic / 30.7 % dithered against its recorded 30.3 % apron; *Shoot these before they're gone* and *Plan my week* name the same closing target and night; the dithered readiness goal 14.2 h over ~6 fields is the 2×2's ~2.4 h a field, not a drift). Suite 8681 passed / 7 skipped. **START HERE NEXT RUN:** Builder: nothing ungated until an owner gate or a diagnostic result arrives; Scout: sweep (3), and file `Diagnostic result:` issues when they land.*

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
