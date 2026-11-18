# Current focus — AstroStack

> **Short on purpose (AGENTS.md: "short, dated, the Scout keeps it current").** One dated line per run goes at the
> top of *Run log*; keep about the last ten and move older lines, whole and in order, to `docs/archive/`. Detail
> belongs in `docs/PROCESS-NOTES.md`, never here. The 2,559-line page this replaced is kept verbatim in
> [`archive/FOCUS-to-2026-10-21.md`](archive/FOCUS-to-2026-10-21.md) — nothing was deleted.

## Front of the queue (2026-11-15)

**Nothing ungated is open.** The Scout's 2026-11-15 🟠 (a mosaic panel ~9× shallower than the rest never levelled) shipped as v0.506.43. The editor export applying a different auto-contrast curve from the preview shipped as v0.506.40. Auto's post-stretch colour-blotch smoothing / SCNR leaving `[0, 1]` shipped as v0.506.39. A typed editor *Output name* becoming the zoom clip's cache path (the Scout's `output_basename` lead) shipped as v0.506.38. The keep-processed save recording 0° for a recipe-rotated picture (the v0.506.35 lead) shipped as v0.506.37. A download named after a typed *Output name* with a dash, emoji or quote failing was Scout-fixed as v0.506.36. An added editor Stretch starting at asinh black 0.35 (half the sky clipped to black) shipped as v0.506.33. The `/api/system` ASTAP self-test calling a working ASTAP "can't start" was Scout-fixed as v0.506.32. The editor Resize point-sampling a shrink shipped as v0.506.31. The "~N more clear nights" estimate on an uneven mosaic shipped as v0.506.30. The full-size archive counting a non-right-angle North-up turn over the 8000 px cap as full size shipped as v0.506.28. The pre-sized mid-copy sub keeping a blank-frame QC shipped as v0.506.27. The grain verdict missing on an under-shot panel of a 3×3-or-larger mosaic shipped as v0.506.26. An unknown `/api` GET answering the SPA shell with 200 was Scout-fixed as v0.506.25. The Print default refused after Auto's mosaic trim shipped as v0.506.24. The full-container-temp-dir solve misreport shipped as v0.506.23. The editor Download PNG / Share / Print pile-up shipped as v0.506.20; the
trim-after-shrink of an unedited canvas over 8000 px shipped as v0.506.19. The non-UTF-8 sub-file-name scan abort shipped as v0.506.18. The `._*.fit` sidecar half of
the Scout 2026-11-03 entry shipped as v0.505.10; its `.recycle/` / `.Trash-*/` / visible `.zfs/` half (one skip) waits on
the owner. The owner's ⭐ colour-pattern entry is on HOLD for his per-temperature numbers; the dark ring waits on a
diagnostic (below).

**Gated, do not start:** the un-located-panel entry (Scout 2026-10-19 in Bugs) waits on diagnostic `mosaic_panel_hints` v2
(v0.506.10), the dark ring on `sky_falloff` v3 (v0.506.16) and the #878 headline LEAD on `twin_target_overcount` v1 (v0.506.8); the
other LEADs and ⚪ notes in Bugs wait on owner/observer measurements — read each one's gate first, and do not
re-litigate a stand-down that carries numbers. **Issue inbox:** #878, #880, #903, #1015 — all previously acted-on
and owner-gated, none updated since 2026-10-12 (re-checked 2026-11-11, Scout `optimistic-cannon-usq0cn`, again by `mh7yxx`, `jy9aay`, `dsfjim`, `x5qu3g`, `hv4l4e`, `vrbblx`, `i0xwhr`, `geies9`, `vlbnkm`, `kab7ux`, `facsy5`, `4ynjos`, `5y9dxt`, `crb7x5`, `50wcqa` and `g4pc96`, 2026-11-12; `c961hx`, 2026-11-13; `r0r7nj`, 2026-11-14; `n2dcsi`, 2026-11-15; `rxvumk`, 2026-11-16; `0rt6q3`, 2026-11-17). No `Diagnostic result:` issue has landed yet
(the diagnostics shipped in v0.506.0 / v0.506.1 run after the owner's next update).

## QA rotation (Scout)

Order (AGENTS.md roles): (1) preview↔export parity at mosaic scale → (2) mosaic/walk-away per-panel divergence →
(3) ASTAP/ffmpeg filesystem side effects with a stub binary → (4) the webapp routers. **Last swept: (4), 2026-11-17
→ next sweep is (1).** Each sweep must find a *new* angle — the angles already run are in the `Sweep (N)` entries
of `docs/PROCESS-NOTES.md` (grep `sweep (1)`).

## Run log (newest first)

*2026-11-18 (Builder, branch `claude/fervent-bohr-p8kzq5`) — **no app change: nothing ungated; an editor-op probe on a NaN-gapped mosaic canvas CLEAN** — every non-geometry op at its defaults, linear and display stage: coverage held everywhere; the only out-of-`[0, 1]` results are linear-stage ops placed after the stretch, which `stageConflicts.ts` already flags with a one-click fix. Inbox unchanged (the same four), no open PRs. Suite 8874 passed / 7 skipped. **START HERE NEXT RUN:** Builder: nothing ungated — stop early unless an owner gate, a `Diagnostic result:` issue or a Scout-filed bug has landed; Scout: sweep (1), and file `Diagnostic result:` issues when they land.*
*2026-11-18 (Builder, branch `claude/fervent-bohr-mj7qy0`) — **no app change: nothing ungated; dogfood `--build --combine` and `--empty` CLEAN** — the two flags not yet run since the declutter (combine: scan → refused unsolved stack → nudge → merge → two rescans stay one target, §10 CLEAN, 7 originals unchanged; empty: the no-ASTAP note alone). Every dogfood flag has now run since the declutter. Suite 8874 passed / 7 skipped. **START HERE NEXT RUN:** Builder: nothing ungated — a beginner feature or an editor bug hunt on a tiled mosaic; Scout: sweep (1), and file `Diagnostic result:` issues when they land.*
*2026-11-18 (Builder, branch `claude/fervent-bohr-1901i7`) — **no app change: nothing ungated; dogfood `--build --deep --restack --closing` CLEAN** — the post-declutter combination the last run named (deep frames table 301 of 1,200 rows, grows to 601 on scroll, first paint 1.5 s; restack reel 3 → 6 subs, noise-delta 1.658 pixel-exact; *Shoot these before they're gone* and *Plan my week* name the same target and the same night). Suite 8874 passed / 7 skipped. **START HERE NEXT RUN:** Builder: nothing ungated — a beginner feature or a dogfood pass (`--combine` and `--empty` have not run since the declutter); Scout: sweep (1), and file `Diagnostic result:` issues when they land.*
*2026-11-18 (Builder, branch `claude/fervent-bohr-9l42qw`) — **no app change: nothing ungated; dogfood `--build --mosaic --calibration --big --incoming-lag --editor` CLEAN** — the first post-declutter pass that holds masters, a decimated preview and a lagging `incoming/` at once (21 ops re-render on all three runs, Auto trim 7.9 %, scale-pair 1 of 16 moved = the known `sky` rounding). Suite 8874 passed / 7 skipped. **START HERE NEXT RUN:** Builder: nothing ungated — a beginner feature or a dogfood pass (`--deep --restack --closing` is the post-declutter combination not yet run); Scout: sweep (1), and file `Diagnostic result:` issues when they land.*
*2026-11-17 (Builder, branch `claude/fervent-bohr-uh3xuc`) — **no app change: nothing ungated; dogfood `--build --mosaic --dithered --editor` CLEAN** — the first full editor drive after the seven declutter slices (21 ops re-render, Auto summary inline, trim 8 %). Suite 8874 passed / 7 skipped. **START HERE NEXT RUN:** Builder: nothing ungated — a beginner feature or a dogfood pass; Scout: sweep (1), and file `Diagnostic result:` issues when they land.*
*2026-11-17 (Builder, branch `claude/fervent-bohr-e4d7pd`) — **v0.507.12: declutter slice 7 on Moon & Sun** — each capture card's re-stack / crop / sharpen offers go on one `AlertNoticeBoard` (5 → 1 `<Alert>` sites), and **the ⭐ declutter entry is closed** (no route over 5 alert sites; Settings' five read, not a wall; the ratchet test stays). **START HERE NEXT RUN:** Builder: nothing ungated — a beginner feature or a dogfood pass; Scout: sweep (1), and file `Diagnostic result:` issues when they land.*
*2026-11-17 (Builder, branch `claude/fervent-bohr-gr597o`) — **v0.507.11: ⭐ declutter slice 6 on Target** — its 13 `<Alert>` sites (nine already on the `target-notes` board, four in the Auto-grade dialog) are drawn through the shared `alertNoticeNode`; 13 → 0, nothing removed, page unchanged for a reader. No route holds more than 5 `<Alert>` sites now. **START HERE NEXT RUN:** Builder: measure MoonSun / Settings (5 each) with the data that fills them before slicing, or close the ⭐ declutter entry; Scout: sweep (1), and file `Diagnostic result:` issues when they land.*
*2026-11-17 (Builder, branch `claude/fervent-bohr-6qegv8`) — **v0.507.10: ⭐ declutter slice 5 on Jobs** — its 10 `<Alert>` sites go through three `AlertNoticeBoard`s (a finished stack's warnings, a finished scan's notes with problems first, the page's waiting-import note); 10 → 0, nothing removed. **START HERE NEXT RUN:** Builder: ⭐ declutter slice 6 — Target's 13 `<Alert>` sites; Scout: sweep (1), and file `Diagnostic result:` issues when they land.*
*2026-11-17 (Builder, branch `claude/fervent-bohr-y4cpj2`) — **v0.507.9: ⭐ declutter slice 4 on the Editor** — its 16 `<Alert>` sites go through three notice boards (the Stack form's board, now shared as `components/AlertNoticeBoard.tsx`: notes above the pipeline, the pipeline's own warnings, the selected step's notes); "What Auto-process did" never folds; the preview box's three exclusive errors are one site; 16 → 2, nothing removed. **START HERE NEXT RUN:** Builder: ⭐ declutter slice 5 — Jobs' 10 `<Alert>` sites (then Target's 13); Scout: sweep (4), and file `Diagnostic result:` issues when they land.*
*2026-11-17 (Scout, branch `claude/sweet-euler-0rt6q3`) — **QA rotation sweep (4), new angle: `HEAD` and `Range` on all 22 file-serving GETs on the mosaic data root — CLEAN** (no 500; `FileResponse` routes answer ranges RFC-correctly, in-memory ones a full 200; `HEAD` 405 everywhere, which nothing sends). Inbox: the same four, owner-gated; no `Diagnostic result:` yet. Dogfood `--build --mosaic` CLEAN; suite 8873 passed / 7 skipped. **START HERE NEXT RUN:** Builder: ⭐ declutter slice 4 — the Editor's 16 `<Alert>` sites (then Jobs' 10); Scout: sweep (1), and file `Diagnostic result:` issues when they land.*

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
