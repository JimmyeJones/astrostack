# Current focus — AstroStack

*Last edited 2026-10-05 (Builder — **closed observer issue #1069 in all three of its halves**: the backfill
guard **v0.492.39**, the destructive delete it was hiding **v0.492.40** (deleting an old stack could delete a
*current* picture), and the display fork **v0.492.41**, settled with a signature that reads no files. The Scout's
earlier 2026-10-05 edit stands below: all five open issues triaged, rotation sweep **(4) the webapp routers**
CLEAN, `--mosaic` dogfood CLEAN and coherent (trim 7.9 %). Records in `docs/PROCESS-NOTES.md`.) **"Bugs (fix these
first)" now holds NO verified open bug — only the gated LEADs and ⚪ notes.** The earlier Builder 2026-10-05 note stands: a `--mosaic --editor --big` dogfood
after v0.492.38 is CLEAN and the scale-pair rig reads **0 of 16 canvas-independent answers moved**. **The Scout
rewrites this page** when the front of the queue changes; it stays short and dated. If this page and the backlog
disagree, the backlog's "Bugs (fix these first)" wins and this page is stale — fix it.*

## Front of the queue

0. **"Bugs (fix these first)" holds NO verified open bug — #1069 is closed in all three of its halves (Builder
   2026-10-05) — only gated LEADs and ⚪ notes remain.**
   🟡 **The display fork shipped as v0.492.41** and the whole entry is cut to [`SHIPPED.md`](SHIPPED.md). It took a
   **third** option the entry had not named: two rows naming one `fits_path` *is* the bug (the guard exists to stop
   exactly that), so it needs **no file read** — the listing already holds every row — which keeps the cheap History
   endpoints' no-file-read promise and settles the fork with no migration and no schema change. Its limitation is
   measured: a merge erases the signature (`_carry_pictures` copies under a `_free_basename`), under-reporting rather
   than mis-stating — which is why v0.492.39's sibling guard, already holding the file open, keys on `NAXIS` instead.
   **Next run: "Bugs" is dry of ungated work.** Per AGENTS.md §2 that means a dogfood pass and file what you find —
   do not manufacture busywork, and do not re-litigate the gated stand-downs below.
   🔴 **The serious one on this population shipped as v0.492.40** (Builder 2026-10-05), found by reading while
   scoping the display half: **deleting an old stack could delete a *current* picture.** `delete_run_artifacts`
   unlinks a run's three path columns plus every basename-derived sibling and checked nothing about whether another
   row still names them, so deleting one of the 56 displaced rows unlinked the live run's whole set — **16 files**
   in the reproduction — and **"Prune old stacks" targets the oldest rows first, which is exactly what all 56 are.**
   `purge_stack_run` now asks the DB what other rows still name; the set is re-read per run so the last row of a
   shared group still frees everything, and deleting the *live* row keeps what its displaced sibling serves. Raws
   were never at risk (`incoming/` is read-only). **The next Builder on half (1) has three candidate signatures,
   not two** — the entry's marker-migration and render-time-header-read, plus a zero-file-read one (two rows naming
   one path, which the observer's 71-rows-on-15-paths count corroborates exactly) whose **measured limitation is
   that a merge erases it** (`_free_basename` + per-run copy splits the pair). Details in
   `docs/PROCESS-NOTES.md`.
   🟡 **#1069's ready half shipped as v0.492.39** (Builder 2026-10-05): all three file-reading heals in
   `coverage_backfill.py` now decline a file whose `NAXIS` is not the row's `canvas_w`/`canvas_h` (`_canvas_of`),
   checked before a pixel is read and only on positive evidence. **The entry's "no wrong number exists today" was
   wrong twice, and the fail-before is the evidence**: `backfill_coverage_shares` is a *third* file-reading heal
   with **no `is_mosaic` gate** (it stamped a 0.0667 thin share off the replacement picture), and
   `backfill_seam_residual` *re-measures* a superseded-scale figure, so it **overwrote** a stored 0.42 with 2.0542
   taken off a different picture. The guard adds no new silence (a row that records no canvas heals as before; a
   superseded figure whose master is gone is kept, not cleared), and the invariant it rests on — a real
   `run_stack`'s row canvas *is* its master's `NAXIS`, drizzle included, which `StackEstimate.canvas_w`'s
   "pre-drizzle" docstring makes look doubtful — is pinned by its own test rather than argued. **What is still
   open is the design fork of half (1)**: how the History card *says* a pre-v0.81.8 picture is gone (a one-off
   additive marker migration, or a render-time `canvas`-vs-`NAXIS` check that costs the header read the cheap
   History endpoints promise to avoid). Ten fixtures that let a row's canvas differ from the map beside it were
   made faithful, not loosened.
   🟡 **#1069 as filed (Scout 2026-10-05), severity low.** A closed set of 56 pre-v0.81.7 History rows
   serve a *newer* run's picture and frame count — `Project.repoint_stack_runs` runs only at re-stack time and
   nothing migrated the rows written before the v0.81.7–0.81.8 overwrite guard (mechanism reproduced in the
   code; the per-target counts are the observer's live-library measurement). The pictures were overwritten, so
   the fix is to **say so**, not mend the path — a **design fork** (one-off additive migration marking the rows,
   vs. a render-time `canvas`-vs-`NAXIS` check that costs a header read the cheap History endpoints promise to
   avoid). The **ready-to-build half** is independent and obviously safe: `coverage_backfill.py`'s two
   file-reading backfills lack a `canvas`-vs-`NAXIS` guard and are one filled-in `is_mosaic` NULL away from
   stamping a wrong *number* onto a displaced row. Not #903, not a recurrence of the v0.81.7 bug. Full entry in
   the backlog.
   🟠 **The `sky_sigma` stride bug shipped as v0.492.38** (Builder 2026-10-05): `analyze_proxy`'s σ was a
   function of the proxy's *stride* and nothing else, so the same sky got a sharpen-dominated Auto as a single
   field and a near-saturated denoise as a mosaic — ×1.57 high off a strided grid, `noisy` False→True,
   crossfade weight 0.243→0.789 on *the same pixels*, and in the **over**-denoising direction because the
   recipe is applied to the full-resolution export. Of the entry's three candidates it took **(c)**, in the
   shape that needs no calibration: as a **ratio**. `noise.grain_lag_ratio` = `σ(lag 1)/σ(lag step)` on one
   array in one normalization — the proxy's lag-1 differences *are* the master's lag-`step` differences, so
   the normalization divides out exactly and nothing is calibrated between the grids; `proxy.source_grain_ratio`
   supplies it from un-strided windows of the master (memoized in the proxy sidecar). **No bar was moved**, and
   it is 1.0 by construction on an undecimated proxy and on white noise — so a single-field stack's Auto is
   byte-for-byte what it was. **(b) was rejected on a reason the entry had not spotted** (Auto measures
   `_measured_region`, not the canvas the stacker measured), and the entry's own objection to (b) — an "edited
   proxy mid-session" — does not exist: both call sites pass the raw `get_proxy` array.
   🟠 **The seam finding shipped as v0.492.37** (Builder 2026-10-04): `measure_seam_residual` was not scale-free
   — the bundled mosaic at three sensors read 0.4520 → 0.7075 → 0.8685 on 457 / 907 / 1693 px of the *same* sky,
   so the biggest canvas lost the "the panels of this mosaic evened out" note. The bodies agreed on all three to
   within half an ADU; what moved was how many 0.2–0.9 %-of-the-canvas slivers cleared the absolute
   `min_pixels_per_level` and were then allowed to set the whole `max − min`. The range is now **trimmed by share
   of the canvas**, not by pixel count: a level covering ≥ 1 % always votes at full value, and `share = 0` *is*
   the old range, so the bump of `SEAM_ESTIMATOR_GENERATION` (2 → 3) stays one-sided by construction. The
   per-level *floor* the entry warned about was built first and is measured wrong — it blinds the deep-dither
   catch — and the two bars are untouched. After: 0.0616 / 0.0931 / 0.0000.
   🟡 **#1063 shipped as v0.492.35** (Builder 2026-10-04): the incoming-lag note went silent on the owner's
   double-registered folders because `imported_by_folder` *summed* a folder's tally across targets, so #878's
   duplicates pushed it past the files on disk and `waiting <= 0` dropped the folder — 30 of 54 drop folders
   dark, a 41,727-sub dead zone. The rollup decision the entry left open was settled by **running candidate
   (a)**: `max` across targets fixes the repro *and* cries wolf on two targets holding disjoint halves of one
   folder, so the count is now distinct `source_path`s, taken **only for a folder more than one target
   claims** (a library with no duplication reads not one extra row). What is left below is **gated LEADs and
   ⚪ notes** (owner data, an unmeasured cost, or a numbered stand-down — see `docs/PROCESS-NOTES.md`; the
   2026-10-04 ⚪ is `classify_target`'s `confidence` pinned to 1.0, filed-not-fixed because nothing reads it).
   **Do not blind-flip a gated threshold or re-litigate a numbered stand-down.** Grep `docs/SHIPPED.md`
   before building.

1. **The editor (PRIORITY 1) — "re-audits come back clean" held until 2026-10-04, when one did not.** Judge
   Auto/editor on a tiled mosaic at the owner's scale (`--mosaic --editor --big`); a "What Auto did" trim
   above ~15 % of the canvas is a bug. **v0.492.33**: the preset chip called all three bundled star-only
   samples a *galaxy* at proxy step 1 and a star cluster at step 2, `classify_target`'s opening footprint
   being a fixed 7×7 in **proxy** pixels while `starmask.star_mask` next door had always scaled its own.
   **Reuse the instrument that found it** — the two bundled mosaic samples "differ in scale alone", so asking
   both the same question and diffing the answers tests any claim that should not depend on canvas size
   (lead filed under Infra).

2. **Owner-approved, buildable now: empty** — everything shipped and cut to [`SHIPPED.md`](SHIPPED.md).
3. **Open observer issues — FIVE open, ALL now triaged (Scout 2026-10-05).** **#1069 is the one that got
   triaged this run**: verified against the code and filed into "Bugs (fix these first)" (item 0 above),
   severity low, issue left open with a verification comment (work not done). The other four were triaged
   2026-10-04 and **none carries code work** — all are blocked on an owner click/reading, with no new activity
   since needing action: #878 (reconcile shipped v0.482.1/.2 — closes on a reading that shows the 11 pairs
   gone), #880 (both live halves shipped v0.483.1/.2; only the ⚪ exception-repr remainder open), #903
   (prevention still open; existing damage has the v0.479.3 repair), #1015 (repo half shipped v0.488.2; the
   clone-pin + token-mint remainder is out of this repo). Don't trust any count here over `list_issues`.

## Standing frontier (unchanged until a finding says otherwise)

- **Mosaic-scale and walk-away behaviour is the open frontier**, not the single-field engine core.
- **Rotation state.** (1) preview↔export parity on a mosaic canvas — **swept CLEAN 2026-10-02 (Scout)**: the
  one-click Auto recipe renders proxy↔export within |Δ|≤0.0004/channel at proxy step 4, all divergence entering
  at `tone.stretch`'s documented resolution dependence, every pixel-scaled op still routed through `scaled_px`.
  (2) mosaic/walk-away divergence — a threshold taken from a whole-target or *peak* number that is really
  per-panel — swept 2026-10-03 (Scout); it yielded the Tonight-planner bug, **shipped v0.492.32**, and the
  engine stacking side was otherwise clean. (3) ASTAP/ffmpeg filesystem side effects — **re-swept CLEAN
  2026-10-04 (Scout)**: ASTAP still copies each frame into a `TemporaryDirectory` before `-f` (no `-update`),
  `video/ffmpeg.py` only reads (output over a pipe, never an output path), and the stub-binary readonly-guard
  layers all pass. (4) the webapp routers were swept 2026-10-01. Details in `docs/PROCESS-NOTES.md`; don't
  re-run (1), (3) or (4) before a finding says to. **The fifth question — does a measurement change when only
  the canvas does? — is now half swept (Builder 2026-10-04): the pure-Python half came back CLEAN** (identical
  Auto op lists and identical verdicts at full resolution and `[::2, ::2]`, every difference at the rounding
  digit), **and the rig was deliberately not landed as a test because its synthetic fixture cannot reproduce
  the pre-v0.492.33 defect** — a green tick with no sensitivity. **The `--big` sample-pair half is now SHIPPED as
  v0.492.36** (`scripts/dogfood_scale_pair.py`, step 4a-ter of the dogfood pass) **and it found two things on
  its first run, both filed under "Bugs"**: `seam_residual` moves 0.6998 → 1.2218 on the same sky through a
  bigger sensor and loses the "panels evened out" note, and `sky_sigma`'s move turned out to be the proxy
  *stride* rather than the canvas. **The seam one is now SHIPPED as v0.492.37** (item 0 above):
  the entry's reproduction recipe held (0.4520 → 0.7075 → 0.8685 here, 10/35/100 s), the share *floor* it warned
  about was indeed measured wrong, and what works is the same bar applied as a **trim of the range** rather than a
  per-level veto — a group of thin levels that together clears 1 % of the canvas still sets the extreme, which is
  what keeps the deep-dither catch alive. Neither bar was flipped. **`sky_sigma` is now SHIPPED too, as v0.492.38** (item 0 above): the
  ×1.57 step-1→step-3 factor is a property of the reprojection's correlation (identical at σ 0.002/0.02/0.2, and
  1.00 for white noise), and the fix is that same correlation **measured** rather than calibrated —
  `σ(lag 1)/σ(lag step)` off un-strided windows of the master, which is dimensionless, so no bar moved and the
  two already-correct cases (undecimated proxy, uncorrelated grain) are 1.0 by construction. So question 5 is
  **answered where it could be asked, and both of its consequences are drained** — and the pair rig that found
  them now reads 0 of 16 moved.
  Next user of the rig: the pair differs in canvas extent *and* proxy stride at once, so ask any `MOVED` line
  of one master at two strides before calling it a canvas bug.
  Caveat for whoever takes it: the raw cues move ~30 % relative while the verdicts hold, so any future
  tightening of a `classify_target` threshold must be checked at two canvas sizes. Details in
  `docs/PROCESS-NOTES.md` and the Infra lead.
- **The single-field core is re-opened only narrowly** (a pixel-unit threshold tested on an eighth-size
  fixture; swept across `stack`/`calibrate`/`edit`/`render`/`qc` 2026-09-28 — CLEAN). Do **not** re-sweep
  `seestack/stack` or `seestack/calibrate` until a new bug is found there (AGENTS.md).
- **The UI rule:** nothing removed, consolidate rather than add, measure before slicing. Tallest pages and
  baselines: `docs/PROCESS-NOTES.md`, "DOGFOOD BASELINE".
- **A beginner feature on a regular cadence**, but the section is empty and the obvious ones are shipped
  (annotation overlay, share caption, print sizes, framing/mosaic advice, moon notes, "bring my pictures up
  to date") — **do not manufacture a marginal one (§4)**; grep `SHIPPED.md` before proposing another.

## How the owner gets builds now

He deploys with `sudo bash scripts/deploy.sh` from the **`stable`** branch (advanced by `.github/workflows/stable.yml`
to the newest `main` commit ≥ 3 days old with green CI) or from a release tag. So a fix reaches him days after it
merges — ship the follow-up to your own change *before* that soak ends.
