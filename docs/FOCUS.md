# Current focus — AstroStack

> **Short on purpose (AGENTS.md: "short, dated, the Scout keeps it current").** One dated line per run goes at the
> top of *Run log*; keep about the last ten and move older lines, whole and in order, to `docs/archive/`. Detail
> belongs in `docs/PROCESS-NOTES.md`, never here. The 2,559-line page this replaced is kept verbatim in
> [`archive/FOCUS-to-2026-10-21.md`](archive/FOCUS-to-2026-10-21.md) — nothing was deleted.

## Front of the queue (2026-11-12)

**No ungated bug is open.** An added editor Stretch starting at asinh black 0.35 (half the sky clipped to black) shipped as v0.506.33. The `/api/system` ASTAP self-test calling a working ASTAP "can't start" was Scout-fixed as v0.506.32. The editor Resize point-sampling a shrink shipped as v0.506.31. The "~N more clear nights" estimate on an uneven mosaic shipped as v0.506.30. The full-size archive counting a non-right-angle North-up turn over the 8000 px cap as full size shipped as v0.506.28. The pre-sized mid-copy sub keeping a blank-frame QC shipped as v0.506.27. The grain verdict missing on an under-shot panel of a 3×3-or-larger mosaic shipped as v0.506.26. An unknown `/api` GET answering the SPA shell with 200 was Scout-fixed as v0.506.25. The Print default refused after Auto's mosaic trim shipped as v0.506.24. The full-container-temp-dir solve misreport shipped as v0.506.23. The editor Download PNG / Share / Print pile-up shipped as v0.506.20; the
trim-after-shrink of an unedited canvas over 8000 px shipped as v0.506.19. The non-UTF-8 sub-file-name scan abort shipped as v0.506.18. The `._*.fit` sidecar half of
the Scout 2026-11-03 entry shipped as v0.505.10; its `.recycle/` / `.Trash-*/` / visible `.zfs/` half (one skip) waits on
the owner. The owner's ⭐ colour-pattern entry is on HOLD for his per-temperature numbers; the dark ring waits on a
diagnostic (below).

**Gated, do not start:** the un-located-panel entry (Scout 2026-10-19 in Bugs) waits on diagnostic `mosaic_panel_hints` v2
(v0.506.10), the dark ring on `sky_falloff` v3 (v0.506.16) and the #878 headline LEAD on `twin_target_overcount` v1 (v0.506.8); the
other LEADs and ⚪ notes in Bugs wait on owner/observer measurements — read each one's gate first, and do not
re-litigate a stand-down that carries numbers. **Issue inbox:** #878, #880, #903, #1015 — all previously acted-on
and owner-gated, none updated since 2026-10-12 (re-checked 2026-11-11, Scout `optimistic-cannon-usq0cn`, again by `mh7yxx`, `jy9aay`, `dsfjim`, `x5qu3g`, `hv4l4e`, `vrbblx`, `i0xwhr`, `geies9`, `vlbnkm`, `kab7ux`, `facsy5`, `4ynjos`, `5y9dxt`, `crb7x5`, `50wcqa` and `g4pc96`, 2026-11-12). No `Diagnostic result:` issue has landed yet
(the diagnostics shipped in v0.506.0 / v0.506.1 run after the owner's next update).

## QA rotation (Scout)

Order (AGENTS.md roles): (1) preview↔export parity at mosaic scale → (2) mosaic/walk-away per-panel divergence →
(3) ASTAP/ffmpeg filesystem side effects with a stub binary → (4) the webapp routers. **Last swept: (3), 2026-11-12
→ next sweep is (4).** Each sweep must find a *new* angle — the angles already run are in the `Sweep (N)` entries
of `docs/PROCESS-NOTES.md` (grep `sweep (1)`).

## Run log (newest first)

*2026-11-13 (Builder, branch `claude/sweet-feynman-cojkqd`) — **no app change: nothing ungated; dogfood `--build --mosaic --dithered --closing --restack --editor` CLEAN as far as it ran** (trim 7.9 % / 30.7 % dithered; closing-season, plan-week and Target cards agree; the field editor drive re-rendered all 21 ops, Undo/Redo and the taste chips worked; the mosaic editor drive was cut at Rotate by the 30-minute background cap, not by the app). Suite 8772 passed / 7 skipped. **START HERE NEXT RUN:** Builder: nothing ungated — a beginner feature or a dogfood pass; Scout: sweep (4), and file `Diagnostic result:` issues when they land.*
*2026-11-13 (Builder, branch `claude/sweet-feynman-xik5fg`) — **no app change: nothing ungated; an added-op probe CLEAN** (every editor op added by hand at its start defaults onto the Auto recipe of a mosaic-shaped field, inserted where `insertOnCorrectSide` puts it: no error, no coverage lost; preview↔export medians at proxy step 3 within 0.003 on all but a second Sharpen, the documented `sharpen_understates_on_proxy` case). Suite 8772 passed / 7 skipped. **START HERE NEXT RUN:** Builder: nothing ungated — a beginner feature or a dogfood pass; Scout: sweep (4), and file `Diagnostic result:` issues when they land.*
*2026-11-12 (Builder, branch `claude/sweet-feynman-efy4co`) — **v0.506.33: an added editor Stretch starts in STF, the look the editor was already showing** (the "No stretch" nudge's Add stretch and the Add menu seeded the schema's asinh black 0.35, which sits on the sky median by construction: median sky 0.20 → 0.00, 54 % of pixels pure black; `opDefaults.ts` `ADDED_OP_DEFAULTS` feeds `newOp`, the panel's Reset and `opModified`; engine default untouched for saved recipes). Found by a probe of every editor op at each parameter's min/max on a mosaic-shaped field — otherwise CLEAN. Editor test fails before. **START HERE NEXT RUN:** Builder: nothing ungated — a beginner feature or a dogfood pass; Scout: sweep (4), and file `Diagnostic result:` issues when they land.*
*2026-11-12 (Builder, branch `claude/sweet-feynman-e6l80a`) — **no app change: nothing ungated; a star-op probe at a mosaic gap edge (`stars.boost_nebula`, `stars.reduce`, star field with an interior gap and a brighter panel) CLEAN; dogfood `--build --mosaic --big --calibration --incoming-lag --editor` CLEAN** (trim 7.9 % / 6.7 %; scale diff moved only `sky` 0.004→0.003; three editor drives re-render all 21 ops). Suite 8772 passed / 7 skipped. **START HERE NEXT RUN:** Builder: nothing ungated — a beginner feature or a dogfood pass; Scout: sweep (4), and file `Diagnostic result:` issues when they land.*
*2026-11-12 (Scout, branch `claude/sweet-euler-g4pc96`) — **QA rotation sweep (3), new angle: the *second* ASTAP call site — the `/api/system` self-test (`ASTAP -h`) — one bug, Scout-fixed (v0.506.32)** (its strict UTF-8 decode turned one Latin-1 byte in the help text into `runs: false`, so the Dashboard and Settings called a working ASTAP "can't start"; v0.506.17 had fixed only the solve path). Inbox: the same four, owner-gated; no `Diagnostic result:` yet. Dogfood `--mosaic` CLEAN. **START HERE NEXT RUN:** Builder: nothing ungated — a beginner feature or a dogfood pass; Scout: sweep (4), and file `Diagnostic result:` issues when they land.*
*2026-11-12 (Builder, branch `claude/sweet-feynman-kzkpgk`) — **no app change: nothing ungated; dogfood `--empty` and `--no-site --editor` CLEAN** (first-run Dashboard says one thing; no-site Tonight shows its set-your-site alert and the blank Night picker is the documented `shownNightDate` choice; the editor drive re-renders all 21 ops). Suite 8771 passed / 7 skipped. **START HERE NEXT RUN:** Builder: nothing ungated — a beginner feature or a dogfood pass; Scout: sweep (3), and file `Diagnostic result:` issues when they land.*
*2026-11-12 (Builder, branch `claude/sweet-feynman-o7z4at`) — **no app change: nothing ungated; dogfood `--deep --incoming-lag --mosaic --editor` CLEAN** (1,200-sub frames table windows at 300 and grows on scroll; the incoming-lag note names its unreadable sub; trim 7.9 %; both editor drives re-render all 21 ops). Suite 8771 passed / 7 skipped. **START HERE NEXT RUN:** Builder: nothing ungated — a beginner feature or a dogfood pass; Scout: sweep (3), and file `Diagnostic result:` issues when they land.*
*2026-11-12 (Builder, branch `claude/sweet-feynman-2yx883`) — **no app change: nothing ungated; a NaN/coverage probe of every editor op at proxy steps 1 and 3 CLEAN; dogfood `--mosaic --editor --dithered --calibration` CLEAN** (trim 7.9 % / 30.7 %; three editor drives re-render all 21 ops). Suite 8771 passed / 7 skipped. **START HERE NEXT RUN:** Builder: nothing ungated — a beginner feature or a dogfood pass; Scout: sweep (3), and file `Diagnostic result:` issues when they land.*
*2026-11-12 (Builder, branch `claude/sweet-feynman-esi1u4`) — **v0.506.31: the editor's Resize averages when it shrinks instead of point-sampling** (found by an editor bug hunt with nothing ungated in Bugs: at 0.25× the bare order-1 `zoom` left the noise no smoother than full size and a star's brightness swung ±41 % with its sub-pixel phase; `geometry._resize` now low-passes each channel first with a NaN-aware Gaussian, `_antialias_for_shrink` — coverage unchanged, enlarge byte-identical). Three regression tests fail before. **START HERE NEXT RUN:** Builder: nothing ungated — a beginner feature or a dogfood pass; Scout: sweep (3), and file `Diagnostic result:` issues when they land.*
*2026-11-11 (Builder, branch `claude/nice-galileo-hm2wbt`) — **no app change: nothing ungated; dogfood `--mosaic --editor --big --restack --closing` CLEAN** (scale diff 0 of 16 moved; trim 7.9 % / 7 %; three editor drives re-render all 21 ops; v0.506.30 re-read in its soak, every goal-gap caller reads `remainingHours`). Suite 8767 passed / 7 skipped. **START HERE NEXT RUN:** Builder: nothing ungated — a beginner feature or a dogfood pass; Scout: sweep (3), and file `Diagnostic result:` issues when they land.*

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
