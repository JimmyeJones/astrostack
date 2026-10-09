# Current focus — AstroStack

*Last edited 2026-10-09 (Builder — **`list_issues` had FIVE open, not the four this page said**: observer
[#1090](https://github.com/JimmyeJones/astrostack/issues/1090) was filed on the morning of 2026-10-08 and was
still untriaged. It was this run, and it is the front of the queue. **Its clock half is SHIPPED as v0.492.45**
and its **second, independent half is now the one verified, ungated open bug** at the top of "Bugs (fix these
first)" — see item 0. What shipped: `_auto_stack_settle_hold`, the guard that exists to stop the hands-off chain
publishing "a picture of a night that is not over", had **never held anything and structurally could not** — it
asked `Project.newest_accepted_sub_time()`, which preferred `frames.source_mtime` on the strength of a docstring
claiming it was "stamped at ingest". It is the *source file's own* mtime, so every timestamp-preserving copy
records the **capture** time and the 20-minute window was spent before the first sub of a folder reached the DB
(the observer measured it on **118 of 118** drop folders). Reproduced here end to end before the fix — subs
ingested *that second* read as **504.0 h** old — and after it reads 0.0 h and holds. New `frames.ingested_at`
stamped centrally in `Project.add_frame`; the answer is the **later** of arrival and capture, so the hold can
only have become more cautious. Ungated `ALTER`, no `SCHEMA_VERSION` bump, every existing row NULL → an upgrade
is unchanged until the next sub arrives. **What is still open is the mid-copy half**, which the observer was
careful to say the clock would *not* have fixed, and which is what actually published a picture from **6 of 742
subs**. **Method notes for the next run, in `docs/PROCESS-NOTES.md`: call `list_issues` before believing a dry
backlog; read an observer issue's "explicitly not claimed" section, because a good one means two tasks; and when
a fix turns a dormant guard on for the first time, re-read every string it will now print** (this one said
"waiting on N still being shot" for a folder that is merely still copying). `docs/SHIPPED.md` is still the
standing housekeeping task — 62,092 lines against the 64,000 ceiling. The 2026-10-08 note stands below.)
(Builder — **#1088 is SHIPPED as v0.492.44 and the issue is closed**, so
**"Bugs (fix these first)" once again held NO verified open bug at that point** — only the gated LEADs and ⚪ notes. The — **#1088 is SHIPPED as v0.492.44 and the issue is closed**, so
**"Bugs (fix these first)" once again holds NO verified open bug — only the gated LEADs and ⚪ notes.** The
"subs waiting in incoming/" note no longer offers a scan it cannot fulfil: the exclusion now comes from what the
scan *recorded* as skipped (`SkippedCalibrationFolder.folder` → `webapp/calibrationskips.py`), **unioned** with
the old `discover` walk so an install that has not scanned since upgrading is unchanged, and matching stays
**exact**. Both of #1088's granularity mismatches were reproduced before the fix and both fail-before through the
endpoint at `assert 6 == 0`. **The prefix roll-up the entry warned about is now a test that passes before *and*
after** (`test_a_light_folder_holding_nested_darks_still_reports_its_lag`) — darks filed inside a *light* unit
must not take that unit's real lag down with them. The three docstrings that asserted "the two sets are
identical" (v0.455.0) are corrected rather than left standing. **Next run: do not re-litigate the gated
stand-downs below; grep `SHIPPED.md` before building.** One thing worth a task of its own, filed in
`docs/PROCESS-NOTES.md` rather than as a bug: `docs/SHIPPED.md` is at 61,998 lines against the 64,000 ceiling the
docs-budget job enforces — **archive** the oldest entries to `docs/archive/`, never delete. The Scout's own
2026-10-08 note stands below.) (Scout 2026-10-08 — **a new observer issue, [#1088](https://github.com/JimmyeJones/astrostack/issues/1088),
verified and filed into "Bugs (fix these first)"** (issue left open with a verification comment; work not done). The
"subs waiting in incoming/" note (`webapp/incominglag.py::incoming_lag`) offers a **Scan incoming** button for a
calibration folder the scan will never import, whenever declared darks sit one directory deep (`Darks/20s/`): the
exclusion compares the plan's *recursive* unit folder (`Darks`) against discovery's *non-recursive* directory
(`Darks/20s`) by **exact** equality, and the two only coincide when calibration frames sit directly in a top-level
folder — exactly the shape the Calibration page's `MAX_DEPTH = 2` nesting invites. **Reproduced end-to-end** through
the real `plan_incoming_units` + `find_calibration_folders` + `incoming_lag`; severity **low/latent** (not firing on
the owner's library today — zero nested directories under his `incoming/`). The naive prefix roll-up is **wrong** —
it misses the `MIN_FRAMES`-floor variant and over-silences darks nested in a light unit — so the robust fix (consult
what the scan *actually* skipped) is Builder-sized; full entry in the backlog. **Rotation sweep (3) ASTAP/ffmpeg
filesystem side effects re-swept CLEAN**: ASTAP still copies each frame into a `TemporaryDirectory` before `-f` (no
`-update`, sidecars read from the temp copy), `video/ffmpeg.py` reads with `-i` and pipes raw frames to stdout (`-`,
never an output path), and the stub-binary readonly-guard tests (`tests/webapp/test_incoming_readonly_guard.py`) are
green in the baseline. **Dogfood** `--mosaic --incoming-lag --calibration` otherwise coherent (incoming-lag note,
mosaic readiness, stack-health all read sensibly); one minor finding — the self-hiding "Repair them" button's label
clips 3 px on phone width — filed under the Bugs "Minor / low-priority" bucket (cosmetic, fix when touching the file).
The other four open issues (#1015, #903, #880, #878) stay owner-gated — #1015's app half shipped, only the owner's
token-mint and the Observer's own clone-pin remain. Baseline 7468 passed / 4 skipped, CI green. Record in
`docs/PROCESS-NOTES.md`. The 2026-10-05 Builder note stands below.) (Builder 2026-10-05 — **closed observer issue #1069 in all four of its halves**: the backfill
guard **v0.492.39**, the destructive delete it was hiding **v0.492.40** (deleting an old stack could delete a
*current* picture), the display fork **v0.492.41**, settled with a signature that reads no files, and **v0.492.42** — the *write* side of the same sentence, found by grepping `SHIPPED.md` for what the earlier runs filed onto the entry they then cut — plus **v0.492.43**, observer #1079's drift guard, found by reading the issue list rather than trusting this page's count. The Scout's
earlier 2026-10-05 edit stands below: all five open issues triaged, rotation sweep **(4) the webapp routers**
CLEAN, `--mosaic` dogfood CLEAN and coherent (trim 7.9 %). Records in `docs/PROCESS-NOTES.md`.) **"Bugs (fix these
first)" now holds NO verified open bug — only the gated LEADs and ⚪ notes.** The earlier Builder 2026-10-05 note stands: a `--mosaic --editor --big` dogfood
after v0.492.38 is CLEAN and the scale-pair rig reads **0 of 16 canvas-independent answers moved**. **The Scout
rewrites this page** when the front of the queue changes; it stays short and dated. If this page and the backlog
disagree, the backlog's "Bugs (fix these first)" wins and this page is stale — fix it.*

## Front of the queue

0. **⭐ THE ONE VERIFIED, UNGATED OPEN BUG: the mid-copy half of [#1090](https://github.com/JimmyeJones/astrostack/issues/1090)**
   (Builder 2026-10-09, filed with the v0.492.45 fix of its other half). **A walk-away stack is published from
   the subs a folder had when the scan *walked* it, and nothing between the walk and the stack re-asks how many
   the folder now holds** — so a drop folder caught mid-copy reads as a complete, settled target. It has fired:
   the owner's `C_9` was published **and auto-edited from 6 of its 742 subs**, never QC-graded (`auto_grade`'s
   `MIN_FRAMES_FOR_GRADING` is 10), then re-stacked from 609 seventy minutes later. **v0.492.45 does not cover
   it and the observer measured why** — the folder's copy finished 35.9 min before the stack started, because
   the job spent 39 min stacking the other target first, so the settle window had honestly expired. Size **M**;
   severity medium-high. The full entry carries the fix shape *and* its trap: an unbounded count comparison
   **strands** a target on a file that cannot be ingested at all (~147 such rows, #880), so the hold must be
   bounded to **once per observed on-disk count**. Issue left **open** with a comment naming both halves.
   **Below this it is gated LEADs and ⚪ notes, as before — do not re-litigate the numbered stand-downs.**

0a. **The prior front of the queue, now history: "Bugs (fix these first)" held NO verified, ungated open bug.** 🟡 **#1088 shipped as v0.492.44**
   (Builder 2026-10-08) and the issue is closed; the entry is cut to [`SHIPPED.md`](SHIPPED.md). The method note
   worth carrying forward: **a false invariant written into three docstrings is a bug with three heads** —
   v0.455.0's "the two sets are identical, a folder could not fall between them" was in `plan_incoming_units`,
   `_calibration_units` *and* `_calibration_folders`, plus a test pinning the agreement on the one tree where it
   really holds; repairing the comparison and leaving the prose would have handed the next run the same wrong
   model. And **the candidate you reject earns a test when it is the cheap one**: the prefix roll-up is now
   `test_a_light_folder_holding_nested_darks_still_reports_its_lag`, green before and after, so the next run to
   reach for it goes red. The Scout's filing text follows.
   🟡 **As filed (Scout 2026-10-08), now shipped.**
   🟡 **The incoming-lag note offers a scan it can never fulfil when calibration frames sit one directory deep.**
   `webapp/incominglag.py::incoming_lag` excludes a calibration folder by **exact** equality (`if unit.folder in
   skip`), but the plan names the *recursive* unit (`Darks`) and discovery names the *non-recursive* directory
   (`Darks/20s`), so they only match when the frames sit directly in a top-level folder — and the Calibration
   page's `MAX_DEPTH = 2` deliberately accepts the nested shape. Reproduced end-to-end; severity low/latent (not
   on the owner's data today). The prefix roll-up is wrong on two counts (the `MIN_FRAMES`-floor variant, and
   over-silencing darks nested in a light unit), so the robust fix — have the note consult the scan's actual
   `SkippedCalibrationFolder` set — is **Builder-sized**. Full entry (repro, three layouts, fix shape) in the
   backlog; issue left open with a verification comment. **Below this, #1069 is closed in all FOUR of its halves
   (Builder 2026-10-05); the rest is gated LEADs and ⚪ notes.**
   🟠 **The fourth half shipped as v0.492.42** (Builder 2026-10-05), and finding it is a **method note, not a
   sweep**: the previous run filed two consequences "onto #1069's open display half", that half shipped, and the
   entry was cut to `SHIPPED.md` — so nothing in the backlog held them. **A run that ships an entry must check
   what was filed *onto* it**, because cutting the entry deletes the only pointer; grepping `SHIPPED.md` for the
   last runs' own *"deliberately not built"* paragraphs is what a dry backlog should do before a dogfood pass.
   One of the two was mis-severitied as cosmetic and is not: **"Adjust → Save as preview" on a displaced row
   re-rendered the *live* run's preview PNG** (its History thumbnail, Target hero, Library tile and Sky Map
   tile). Measured through the endpoint — the shared preview 64×64 → **86×86 turned 155°**, the rotation stamped
   on the *clicked* row, the live row's `preview_north_up_deg` left **NULL**, which is the exact mismatch that
   column exists to prevent. Refused with 409 (`preview_owner_by_run_id`); the live run — the *writer* — still
   saves, and the Adjust panel keeps every control. The other consequence (a displaced row reclaims no space) is
   answered by v0.492.41's badge. **The class, for the next run: v0.492.40 guarded *deletes* against "a row does
   not own what it points at"; this is the same sentence applied to *writes*. Grep `run.preview_path` /
   `run.fits_path` / `run_artifact_paths` for *writers*, not readers — as of this run the preview save was the
   last one.**
   🟡 **The display fork shipped as v0.492.41** and the whole entry is cut to [`SHIPPED.md`](SHIPPED.md). It took a
   **third** option the entry had not named: two rows naming one `fits_path` *is* the bug (the guard exists to stop
   exactly that), so it needs **no file read** — the listing already holds every row — which keeps the cheap History
   endpoints' no-file-read promise and settles the fork with no migration and no schema change. Its limitation is
   measured: a merge erases the signature (`_carry_pictures` copies under a `_free_basename`), under-reporting rather
   than mis-stating — which is why v0.492.39's sibling guard, already holding the file open, keys on `NAXIS` instead.
   **Next run: the one ungated verified bug is #1088 at the top of "Bugs"** (Scout 2026-10-08, Builder-sized —
   see item 0). Below it is gated LEADs and ⚪ notes; do not manufacture busywork, and do not re-litigate the
   gated stand-downs below.
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
   checked before a pixel is read and only on positive evidence. **No wrong number existed on the owner's library** — the observer
   measured every file-derived column NULL on all 56 rows, and an earlier draft of this page said otherwise; both
   fail-befores are synthetic. What the guard is for: `backfill_coverage_shares` is a *third* file-reading heal with
   **no `is_mosaic` gate at all**, so those rows were **one "How's my stack?" away** from a stamped wrong number
   rather than one `is_mosaic` backfill away (it stamps a 0.0667 thin share off the replacement picture); and
   `backfill_seam_residual` *re-measures* a superseded-scale figure, so a mosaic-flagged displaced row has a stored
   0.42 **overwritten** with 2.0542 off a different picture — the `is_mosaic` gate still holds on the owner's 56, so
   that one is a severity finding about the function, not a live condition. The guard adds no new silence (a row that records no canvas heals as before; a
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
3. **Open observer issues — FIVE open, FOUR of them owner-gated (Builder 2026-10-09).** #1090 is the fifth,
   and it was open and untriaged while this page said four: filed 2026-10-08T07:21Z, verified and reproduced
   2026-10-09, **clock half shipped as v0.492.45**, **mid-copy half filed into "Bugs"** (item 0), issue left
   open with a comment naming both. The other four (#878, #880, #903, #1015) carry **no repo code work** and
   stay owner-gated. ⚠️ A MATCHING COUNT IS NOT A MATCHING SET, and a *correct* count goes stale within hours:
   call `list_issues` before believing a dry backlog. The 2026-10-08 text follows.
   **The prior text — FOUR open (Builder 2026-10-08, after closing #1088 in the run that fixed it).**
   **#1088 is CLOSED** — verified, reproduced, fixed as **v0.492.44** and closed with a comment naming the
   version, all in one run (AGENTS.md: an issue whose work is done gets closed in the same run). The four
   that remain (#878, #880, #903, #1015) carry **no repo code work** and stay owner-gated. ⚠️ A MATCHING
   COUNT IS NOT A MATCHING SET: don't trust any count here over `list_issues`. The Scout's 2026-10-08 text
   for #1088 follows. **#1088
   appeared 2026-10-07 and was triaged by the Scout run before this one**: verified against the code, reproduced end-to-end, and
   filed into "Bugs (fix these first)" (item 0 above), severity low/latent, issue left open with a verification
   comment (work not done — the robust fix is Builder-sized). ⚠️ A MATCHING COUNT IS NOT A MATCHING SET: don't
   trust any count here over `list_issues`. The other **four** (#878, #880, #903, #1015) carry **no repo code
   work** and stay owner-gated — #1015's app half shipped (version now on `/api/health`, v0.479.3/.488.2) and only
   the owner's token-mint and the Observer's own clone-pin remain (both outside this repo). The Scout's 2026-10-05
   text for those four stands below.
   **The prior text: FIVE open, ALL now triaged (Scout 2026-10-05).** **#1069 is the one that got
   triaged this run**: verified against the code and filed into "Bugs (fix these first)" (item 0 above),
   severity low, issue left open with a verification comment (work not done). The other four were triaged
   2026-10-04 and **none carries code work** — all are blocked on an owner click/reading, with no new activity
   since needing action: #878 (reconcile shipped v0.482.1/.2 — closes on a reading that shows the 11 pairs
   gone), #880 (both live halves shipped v0.483.1/.2; only the ⚪ exception-repr remainder open), #903
   (prevention still open; existing damage has the v0.479.3 repair), #1015 (repo half shipped v0.488.2; the
   clone-pin + token-mint remainder is out of this repo). Don't trust any count here over `list_issues`.

## Standing frontier (unchanged until a finding says otherwise)

- **Mosaic-scale and walk-away behaviour is the open frontier**, not the single-field engine core.
- **Rotation state.** (1) preview↔export parity on a mosaic canvas — **swept CLEAN 2026-10-02, re-swept CLEAN
  2026-10-06 (Scout)**: the one-click Auto recipe renders proxy↔export within |Δ|≤0.0004/channel at proxy step 4,
  all divergence entering at `tone.stretch`'s documented resolution dependence; the 2026-10-06 re-sweep confirmed
  it from both ends — a code-level A2 audit (every pixel-unit op param scales by `ctx.scaled_px`/`proxy_scale`,
  with documented floors/advisories where the sub-pixel shrink degenerates) and the live scale-pair rig reading
  **0 of 16** canvas-independent answers moved on `--mosaic --big`. **Don't re-run (1).**
  (2) mosaic/walk-away divergence — a threshold taken from a whole-target or *peak* number that is really
  per-panel — swept 2026-10-03 (Scout, yielding the Tonight-planner bug **shipped v0.492.32**) and **re-swept
  CLEAN 2026-10-07 (Scout)**: the whole per-panel threshold family audited engine→webapp→frontend and run on the
  owner's mosaic shape — the best-tonight score/ranking/noise-% are provably scale-invariant (F cancels in
  `1 − √(T/(T+h))`), the stackhealth yardstick's `crop_depth` is the median not the peak, and readiness/thin-stack/
  grain/next-best-move/auto-stack-hold all divide by the per-panel `field_fulls`; the `--mosaic` dogfood read the
  per-panel sentences correctly on the 2×2 (and the single field unscaled). **Don't re-run (2).**
  (3) ASTAP/ffmpeg filesystem side effects — **re-swept CLEAN 2026-10-04 and again 2026-10-08 (Scout)**: ASTAP
  still copies each frame into a `TemporaryDirectory` before `-f` (no `-update`, sidecars read from the temp
  copy), `video/ffmpeg.py` only reads (`-i` in, raw frames out over stdout `-`, never an output path), both files
  substantively unchanged since the last sweep, and the stub-binary readonly-guard tests
  (`tests/webapp/test_incoming_readonly_guard.py`) are green in the baseline. (4) the webapp routers were swept
  2026-10-01. Details in `docs/PROCESS-NOTES.md`; don't re-run (1), (2), (3) or (4) before a finding says to —
  **next in rotation is (4).** **The fifth question — does a measurement change when only
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
