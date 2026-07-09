# AstroStack improvement backlog

The shared blackboard for autonomous development. Read
[`../AGENTS.md`](../AGENTS.md) first — it defines the loop, the decision
framework, and the guardrails. This file is *what* to build; AGENTS.md is *how*.

> **Current focus (2026-07 — see AGENTS.md §1 "Current focus").** The editor is now
> well-hardened, so the highest-value work has shifted to **(1) QA-ing and hardening
> the stacking engine** (`seestack/stack/*`, `seestack/calibrate/*` — a bug there
> corrupts the final image, so treat verified ones like editor bugs: fix first) and
> **(2) autonomy / friendliness / image-quality**. Still fix any real editor
> regression first, but favour these areas when picking new work.

**Conventions**
- Sections: **Bugs (fix these first)** → **In progress** → **Ideas** (roughly
  prioritised) → **Shipped** → **Needs owner sign-off**.
- Two kinds of agent share this list (see AGENTS.md "Agent roles"): the **Builder**
  *drains* it (implements + ships the top items), and the **Scout** *fills* it
  (files verified bugs, curates priorities, adds ideas). Claim any item you start by
  moving it to **In progress** with your branch name, in the same commit that starts
  it. Move it to **Shipped** (with the commit/PR) when done, or back to **Ideas** if
  you abandon it.
- **Scout — replenish and curate.** Each Scout run: file the bugs you verified into
  "Bugs (fix these first)" (symptom + location + repro + severity + confidence),
  reprioritise, prune done/stale/duplicate items, and add a few well-reasoned ideas
  (AGENTS.md §4) — but only ones that serve the **§1 priorities** (1 editor,
  2 autonomy, 3 friendliness, 4 image quality), each tagged with a size (S/M/L) and
  its priority. Do **not** log niche mono/LRGB/channel-combine/narrowband ideas.
- **Builder — fallback top-up.** If ready work is running thin, add an idea or two
  so you never idle; otherwise leave ideation to the Scout and keep shipping.
- **Priority order (from AGENTS.md §1) governs this list.** Work the top sections
  first. The editor is priority 1.

---

## In progress

_(none — claim an item here with your branch name)_

---

## Bugs (fix these first)

Each open entry below was traced through the code and, where marked *reproduced*,
demonstrated by running it. Editor bugs first (PRIORITY 1), within each group
ordered by severity (wrong-result > broken-UX > cosmetic). Each is scoped to be
fixable in one sitting; move an entry to **In progress**/**Shipped** as usual
when you take it.

- ~~**'Tonight' planner 500s (ZeroDivisionError) when the min-altitude floor is exactly 70°.**~~
  — **FIXED v0.97.1** (Builder audit 2026-07-09; reproduced end-to-end before fixing). The night
  planner's observability `_score` computed its altitude term as `(max_alt − min_alt) / (70.0 −
  min_alt)`, hard-coding 70° as the "high enough for a small scope" cap. With `min_altitude_deg == 70`
  — a legal value both as the `?min_alt` query param and the `min_target_altitude_deg` setting (both
  `ge=0 le=80`) — the denominator is **zero**, so any target that transits above 70° (a target near the
  zenith, i.e. dec ≈ observer latitude — common) raised `ZeroDivisionError`, surfacing as a 500 on
  `GET /api/plan/tonight?min_alt=70`. `_score` now saturates the altitude term to 1.0 when the floor is
  already at/above the 70° cap (and returns 0 when `max_alt ≤ min_alt`), so a floor of 70–80° scores
  cleanly instead of crashing. Regression test `test_high_min_altitude_does_not_crash_the_score`
  (min_alt 70 & 80; fails before / passes after). Newest-feature bug found by auditing the recently
  shipped nightplan path (v0.95–0.97), which the QA cycle hadn't covered yet.

- ~~**Watcher silently drops an auto-ingest batch forever when the enqueue hand-off *raises*.**~~
  — **FIXED v0.99.5** (Builder audit 2026-07-09; traced + reproduced with a regression test).
  `Watcher.poll_once` consumes newly-stable files from the `StabilityTracker` (a one-shot contract —
  they're never returned again) *before* invoking `_on_batch_ready`, and the only re-offer safety net
  (`_pending_batch`) was set solely on a clean `accepted is False` return. If the callback **raised**
  mid-hand-off — a transient `sqlite3.OperationalError: database is locked` / disk-full while
  `submit_pipeline` persists the job — the exception propagated to the poll loop (which logs and
  swallows it), leaving `_pending_batch` at its prior `False`; since the files were already consumed,
  the batch was never re-offered and sat unimported in `incoming/` forever. `poll_once` now sets
  `_pending_batch = True` before re-raising, so the next poll re-offers the batch once the callback
  recovers, while the failure is still logged. Regression test
  `tests/webapp/test_watcher.py::test_batch_reoffered_when_callback_raises` (fails before / passes
  after). Sibling of the v0.81.7 "declined while busy" fix, found by the same watcher audit as the
  v0.99.4 duplicate-pipeline fix.

- ~~**Watcher enqueues a *duplicate* auto-ingest pipeline once ≥20 newer jobs push the running
  one out of the recent-jobs window.**~~ — **FIXED v0.99.4** (Builder audit 2026-07-09; traced +
  reproduced with a regression test). `webapp/main.py::_on_batch_ready` guarded against a
  double-enqueue by scanning `jm.list(limit=20)` for an active `pipeline` — but `JobManager.list()`
  merges live + DB jobs, sorts by `created_utc DESC` and truncates to the limit, so a long-running
  auto-stack pipeline (old `created_utc`) is pushed past position 20 once 20 newer jobs
  (queued/finished editor/stack/reprocess work) exist. The guard then saw *no* active pipeline and
  enqueued a **second** one — a redundant full re-scan/QC/solve/stack pass (harmless because the
  single worker serialises them and ingest is idempotent, but wasteful). It now uses the unbounded
  in-memory `JobManager.active_of_kind("pipeline")` (which was purpose-built for exactly this and
  can't be truncated away). Regression test `tests/webapp/test_batch_trigger.py`
  (`test_on_batch_ready_defers_when_running_pipeline_is_past_the_recent_window`, fails before /
  passes after). Found by an adversarial audit of the watcher stabilise→enqueue path.

- ~~**Watcher can permanently drop a batch from auto-ingest when it stabilises during a
  running pipeline.**~~ — **FIXED v0.81.7** (see Shipped). `_on_batch_ready` now reports
  whether it enqueued a pipeline; when it declines because one is already `queued`/`running`,
  the watcher keeps the batch **pending** and re-offers it on later polls until accepted, so
  a file that stabilises mid-pipeline is picked up once that pipeline finishes instead of
  being silently dropped forever. Regression test in `tests/webapp/test_watcher.py`
  (`test_batch_pending_when_pipeline_busy_is_reoffered`, fails before / passes after).

- ~~**Single-field (non-mosaic) stacks are misclassified as mosaics → Auto silently
  crops the frame + the whole editor shows mosaic-only tools.**~~ — **FIXED
  v0.74.2** (see Shipped). The editor now uses the stacker's *authoritative* mosaic
  verdict (a persisted nullable `is_mosaic` column on `stack_runs`, schema 7→8
  additive migration) instead of the broken `coverage_max > coverage_min` heuristic;
  legacy runs (NULL) fall back to a coverage-distribution check, never the old test.
  **Scout 2026-07-05 re-verified the fix is live end-to-end:** a real 8-sub
  single-field stack (`POST …/stack` → `run_stack`) persists `is_mosaic=0` in the
  `stack_runs` row, `GET …/editor/histogram` returns `is_mosaic:false`, and `POST
  …/editor/auto` no longer prepends `background.level_coverage` or appends a
  `geometry.crop`. Fully closed; the verbose original write-up was pruned (it lived in
  the Shipped section) to keep the active bugs list a list of *open* bugs.

_(none of the traced *editor-engine* op bugs are open — that backlog stayed drained;
the entry above is a stacking/autonomy↔editor classification bug found by dogfooding
the real webapp stack→edit path.)_

- **Watcher can leave a batch unimported when an *accepted* pipeline later fails before ingesting
  (lower severity — self-recovers, so filed not blind-fixed).** *(traced, Builder audit 2026-07-09;
  the sibling of the v0.99.4/v0.99.5 watcher fixes.)* When `_on_batch_ready` returns `True`, the
  watcher treats the batch as consumed and clears `_pending_batch`. If that enqueued pipeline then
  *fails before ingesting* (a scan/QC error, an OOM refusal, a cancel), the newly-stable files stay
  in `incoming/` and in `StabilityTracker._stable` (kept by `self._stable &= seen` while they're
  present), and are never re-offered on their own. **Why it's lower severity / not a blind fix:** it
  self-recovers — the pipeline job body re-scans the *whole* incoming dir (`find_fits_files`), so the
  next batch (any new file) or a manual "Scan incoming" re-ingests the stranded files, and ingest is
  idempotent; only a site where no further files ever arrive *and* the user never manually scans is
  stuck. And the clean fix is a **design change**, not a one-liner: the watcher would need to learn
  whether the pipeline actually ingested (couple it to job outcomes, or re-arm `_pending_batch` on a
  pipeline that ends in `error`/`cancelled` without importing), which wants deliberate design + its
  own test rather than a reflexive patch. Candidate shapes for whoever takes it: (a) on a pipeline
  finishing non-`done`, re-offer the last batch; (b) periodically re-arm if `incoming/` is non-empty
  and no pipeline is active. (S–M design, autonomy/robustness) —
  *Builder-filed 2026-07-09, traced.*

- **Dead SExtractor skew-fallback guard in 4 background/leveling helpers (needs REAL-data
  threshold validation before fixing — NOT a blind Builder change).** *(traced + reproduced,
  Builder audit 2026-07-08; med confidence it produces a visibly-wrong result in practice.)*
  All four sky-mode estimators — `bg/per_frame.py::_zero_sky_per_channel` (~L300), the GPU
  `bg/per_frame.py::_subtract_background_gpu` tile branch (~L377), `bg/final_gradient.py::
  _subtract_luminance_with_mask` (~L224), and `bg/coverage_leveling.py` per-level offset (~L131) —
  compute `sky = 2.5·median − 1.5·mean` (SExtractor mode) and then guard `if abs(sky − median) >
  5.0·abs(median − mean + 1e-9): sky = median`. **That guard is mathematically dead**: by
  construction `abs(sky − median) = 1.5·abs(median − mean)`, and `1.5 < 5`, so the inequality is
  *always False* (it degenerates to a pure `isfinite` check). The intended "revert to median when
  the skew is implausibly extreme (bright-object contamination)" safety net therefore never fires,
  so a negatively-skewed sky sample (median > mean) over-subtracts and leaves that region darker
  than its neighbours — the coverage-/panel-shaped step these passes exist to remove. **Why it is
  NOT a blind fix (Builder measured this):** the obvious "use the standard SExtractor criterion
  `|mean − median| > 0.3·std → median`" is *wrong here* — a heavy diffuse **nebula** reads
  `|mean − median|/std ≈ 0.32` (measured on a realistic synthetic), i.e. it would trip the 0.3 rail
  and revert to median **exactly where `final_gradient`'s own comment says it deliberately wants the
  mode** ("so faint diffuse signal doesn't pull the zero down"). So a naïve threshold would *regress
  nebula images* (a core OSC target). Typical sky+stars reads `|mean − median|/std ≈ 0.001` (guard
  irrelevant either way), so the common case is unaffected. **What's needed:** pick a genuinely-safe
  revert threshold (well above the nebulosity regime, only catching truly-broken tiles) and validate
  on **real** OSC stacks that (a) normal sky + nebula frames are unchanged and (b) a genuinely
  pathological skew reverts — same real-data-gating as the SCNR / `sky_sigma` items in Image-quality
  below. Fix all four sites together (they share the bug). (S code / M validation, image-quality/correctness)

_(Scout QA audit 2026-07-09 (v0.98.2 baseline, suite green 950 passed / 2 skipped): with the editor,
stacking core, mosaic/drizzle geometry, calibration, bg, solve, render, routers, jobs and the newest
nightplan path all saturated by recent clean audits, rotated the focused subsystem audit onto the
**least-recently-covered ingest/data layer — `seestack/io/*` + `seestack/qc/*`** (fits_loader debayer +
header parsing, project.py schema migrations, library.py registry + `_median_radec`, merge.py, scanner.py,
ingest, and the QC metrics/grading/streaks + apply path). Read adversarially for wrong-colour debayer edges,
NaN/degenerate-input handling, RA-wrap, migration data loss, and auto-reject correctness. **No reachable
wrong-image bug found** — the debayer's normalized-convolution edge handling (zero-fill + per-channel sample
count) is correct and the prior edge-wrap fixes hold; `_coord_to_deg` handles the `-00 MM SS` sexagesimal
sign case and rejects out-of-range coords; project/library migrations are strictly additive and guarded
(incl. the empty/foreign-sqlite base-schema rebuild, v0.94.10); `_median_radec` uses the wrap-safe
`circular_median_ra_deg`; auto-grade's modified-z + practical-significance floors + MAX_REJECT rail + log-domain
non-positive handling are sound; the streak detector only ever *adds* a rejection on a clear elongated Hough
line (conservative); and merge/scanner idempotency + duplicate-skip are correct. **Two traced low-severity
trust/robustness findings (NOT wrong-result — filed to Ideas, not Bugs):** (1) a frame whose QC pass *raises*
(`compute_frame_metrics` → `apply_qc_result_to_db`, `metrics is None`) is stamped `reject_reason="qc_error:…"`
but kept **`accept=1`**, so it's invisible in the reject-summary (which counts `accept=0` only) and inflates the
accepted count; the stacker skips it gracefully at load (`stacker.py:1348-1356/1450-1456`, verified), so no
image corruption, but the beginner gets no signal that N subs were unreadable — friendliness/trust idea filed.
(2) `build_qc_arglist(only_new=True)` (the watcher auto-pipeline) treats a `qc_error` frame as "already done"
forever, so a *transient* QC failure is never re-QC'd automatically — the exact shape of the ingest-cache-retry
bug fixed in v0.94.9; a manual full re-QC recovers it, so low-severity — robustness idea filed. Three genuinely
new ideas added (auto-bind recommended calibration masters in the autonomous stack chains; surface
QC-uncheckable frames; auto-pipeline QC retry).)_

_(Builder dogfood 2026-07-09 (v0.99.2 baseline, suite green 960 passed / 2 skipped — the 2 skips are the
CuPy-only GPU-parity tests, expected on a CPU container). With the backlog drained of headless-shippable
work (the one open Bugs entry — the dead SExtractor skew guard — and both Image-quality items are
deliberately real-data-gated, twice-deferred), ran a big-picture dogfood of the **editor's one-click Auto
path** (the priority-1 "weak default result" concern) end-to-end through the real `auto_recipe`→
`apply_recipe` chain. **Auto's out-of-box result is healthy on a single-field OSC stack** (median grey 0.23,
black-clip 0.05%, balanced R/G/B, star cores preserved, preview↔export unaffected). Also re-probed the
deferred **SCNR-magenta** image-quality item and filed a genuinely new data point to it (see that entry):
gray-star colour-cal balances on *stars* and leaves the *diffuse background* green cast in place, so SCNR
is a measured **net win** on a real cast-carrying background (removes a +0.017 green excess for a −0.004
magenta overshoot) — the −14% magenta failure mode needs an *already-truly-neutral* sky, which gray-star
doesn't produce on cast data. Net: the twice-established deferral of the SCNR change is **correct**; no new
bug found; no code shipped this run (an idle run leaving main green — AGENTS.md §2).)_

_(Builder QA audit 2026-07-09 (v0.98.2 baseline): with the editor + stacking core saturated by weeks of
clean audits, rotated onto the **newest, least-hardened subsystem — the "Tonight" night planner**
(`seestack/nightplan.py`, `webapp/routers/plan.py`, `frontend/src/tonight.ts`, and the two bundled
catalogs), which had only had one real bug traced (the v0.97.1 ZeroDivisionError) and a fortnight of rapid
feature-piling. Read + numerically probed adversarially for degenerate geometry, wrong-shape broadcasts,
crossing-interpolation edges, and bad input. **No bug found.** `_find_dark_window` degrades correctly
through the −18→−12→−6→−0.833° twilight ladder (polar midsummer → `None`; polar midwinter → an 808-min
below-−18 run; southern-hemisphere + seasonal London/Sydney windows all sane); `_score` handles the
`min_alt ≥ 70°` cap (the v0.97.1 fix holds) and `max_alt ≤ min_alt`; `HorizonProfile.from_pairs` sanitises
malformed/non-finite/duplicate/out-of-range points and interpolates across the 0°/360° seam; `moon_window`
rise/set interpolation and `up/down_all_night` flags are consistent; the router's `date` picker validates
`[−1, +60] d` (clean 422 otherwise), `when` takes precedence, `_reference_for_date` aims local solar noon,
and `_parse_angle` handles sexagesimal + the `-00:MM` sign case. Both catalogs are clean: 157 unique ids
(no cross-file dups), every RA∈[0,360)/Dec∈[−90,90], every object typed (so the type-filter buckets never
fall through). The frontend pure helpers (`moonWindowNote`/`moonCueForTarget`/`objectTypeBucket`/
`partitionByUpTonight`/…) are well-tested and edge-guarded. **One candidate refinement investigated and
dismissed as measurably negligible (so a future agent needn't re-open it):** `_observability_batch` measures
each target's Moon separation at a single mid-window instant rather than at the target's own transit — but
because the Moon moves only ~13°/day in ICRS and the *separation* changes far more slowly than that,
measuring at transit instead differs by **≤0.25° across all up-targets** even for a target transiting ~6 h
from mid-window (mean 0.13°, p90 0.21° over the 100 up-targets on a bright-Moon London night). Below the
sub-degree precision the ranking cares about, so the documented approximation is correct and the change
would be pure churn. Baseline suite green: 950 passed, 2 skipped.)_

_(Builder engine-hardening audit 2026-07-08 (v0.94.16 baseline): fresh adversarial **numeric** audit of
the mosaic/drizzle **geometry** path — `stack/mosaic.py` (union canvas, `_bbox`, footprint-outlier
rejection, iterative canvas shrink), `stack/drizzle_path.py` (`_compute_output_canvas` CRPIX/CDELT scaling,
two-pass reject, `result()` weighted-average), and `stack/accumulator.py` (Welford / WeightedSum /
MinMaxReject NaN=coverage edges). Five standalone repro harnesses (in scratchpad): `MinMaxRejectAccumulator`
matched a brute-force sorted-trim reference across **2000 randomized trials** (k∈{1,2,3}, 1–9 frames, ties,
~25% NaN, all three count bands, `add`≡`add_window`); `WeightedSum`/`Welford` uphold NaN=gap (one-finite+one-NaN
→ finite w/ coverage 1; all-NaN → NaN w/ coverage 0; std matches `np.nanstd(ddof=1)` to ~3e-6, single-coverage
std NaN so pass-2 keeps it); `drizzle_path.result()` returns the weighted **mean** (not sum), the two-pass κ-σ
reject yields the exact inlier mean at n=25, and the n=8 lone-outlier non-rejection is the documented
`(n−1)/√n < κ` small-sample limit; `_compute_output_canvas` places corners at exactly 2× with the correct
+0.5 half-pixel offset under a **rotated CD-matrix** WCS and conserves flat-field surface brightness; every
mosaic panel corner lands inside the canvas for a real 2×2 straddling RA=0, a single degenerate frame, and a
4-panel run across the 0°/360° seam (wrap-safe `_circ_mean_ra_deg`). Both passes apply `photometric_scales`
+ per-frame `weight` identically, and quality weights are bounded [0.1, 1.0] so `neff = Σw ≤ count` keeps the
reject gate conservative (can't over-reject). **No reachable image-corruption bug found** — the geometry and
NaN=coverage semantics are correct, consistent with the prior clean audits. One negligible float-level drizzle
kernel weight-leak (~1e-11) examined and dismissed as unreachable (true gaps carry exactly zero weight → NaN).
Baseline suite green: 893 passed, 2 skipped.)_

_(Scout QA audit 2026-07-08 (v0.94.7 baseline): with the stacking/calibration core saturated by
a week of daily brute-force engine audits, rotated onto the **less-recently-covered final-image
edges** — `seestack/solve/*` (ASTAP wrapper + runner), `seestack/bg/*` (`per_frame`, `final_gradient`,
`coverage_leveling`), `seestack/post/color_cal.py` (gray-star + Gaia solvers), `seestack/render/thumbnail.py`
(asinh/STF autostretch + `render_stack_png` NaN-preserving stride), and `webapp/routers/system.py`
(`_astap_info`). Read adversarially for NaN=coverage violations, wrong-length array broadcasts, degenerate
inputs, and setup-error misclassification. **No verified bug found** — the bg fits degrade through their
`exclude_percentile`/box ladders, the Gaia solver's per-detection vs per-catalog indexing lines up (the
documented broadcast-bug fix holds), gray-star guards zero medians, the stretch paths are NaN-aware and
double-stretch-safe, and `_astap_info` already counts **both** `.290` and `.1476` databases (matching
`find_star_db_dir`), so a newer D-series-only install is *not* falsely reported as "no database". **One
trivial cosmetic wording nit logged to Infra** (the no-DB *hint* string still says "(*.290)" and only that,
though it fires only in a genuine zero-DB state and its actionable advice — "add e.g. d05" — is correct).
Confirmed the earlier `mosaic.py` iterative-shrink RA-median robustness note is **fixed** (v0.81.9 — the
loop now uses `_circ_mean_ra_deg`). Two genuinely-new ideas filed (Dashboard ASTAP-readiness banner;
Stack-form luminance-bg-mode nudge for extended-emission targets). Baseline suite green: 887 passed,
2 skipped.)_

_(Scout QA audit 2026-07-07 (v0.89.0 baseline): rotated the focused subsystem audit onto
the **webapp routers** (editor / stack / frames / watcher, plus a fan-out adversarial read of
system / storage / gallery / sky / stats / seestar / settings / calibration / targets). Read
each for None/empty inputs, wrong error codes (500-where-4xx), off-by-one, path traversal,
DB-handle leaks on error paths, and division guards. **Also dogfooded the real
stack→auto→preview→export journey end-to-end through the FastAPI app** on both a single-field
(800×600, proxy_scale 1.0 — preview↔export parity measured **0.00%** on the full Auto recipe)
and a 2000×3000 **mosaic** (proxy_scale 2.0). The mosaic's full-Auto stride-parity read 5–9%
mean, which I **traced to a benign sub-pixel `geometry.crop` origin-rounding artifact**, NOT a
real look mismatch: `crop` rounds its fractional bounds independently on the proxy (×1500) and
full-res (×3000) grids, so the export crop can be ±1 full-res px (½ proxy px) offset — e.g. the
export came out 1599 px tall where 2×799=1598. Isolating the ops confirmed it: `tone.stretch`
alone and `background.level_coverage`+stretch both parity-clean at **0.02%**; only recipes
containing `geometry.crop` show the gap, and a bilinear (sub-pixel-tolerant) comparison keeps
crop at the same ~3% as the no-crop decimation limit. Visually a ≤1px whole-image shift at the
crop edge — imperceptible; "what you see is what you export" holds to within a pixel, so **not
filed as a bug**. **Two genuine low-severity input-robustness bugs found and fixed (v0.89.1,
see Shipped):** the unclamped `stats` `recent_limit` and the missing `sky` preview-exists guard.
One near-unreachable note logged to Infra (calibration null-byte → 500). Baseline suite green:
839 passed, 2 skipped. **No wrong-final-image bug found — the router layer is well-hardened**,
consistent with the mature editor/engine audits.)_

_(Scout QA audit 2026-07-07 (v0.89.1 baseline): rotated the focused subsystem audit onto the
**job-orchestration layer** — `webapp/jobs.py` (`JobManager` queue/worker/cancel/recover/prune,
the `error_kind` classification, the `completed = result or job.result` done-vs-cancelled logic),
`webapp/pipeline.py` (the watcher auto-pipeline, `process_target`, `reprocess_all`, the
`_auto_stack_frame_count` crash-loop guard, the reprocess reuse/stale/fresh-basename logic, the
editor export/PNG/batch bodies + `_render_recipe_fullres`), and `webapp/watcher.py` +
`seestack/io/scanner.py` + `ingest.py` (the `StabilityTracker` debounce, the pending-batch
re-offer, zero-byte/OSError ingest guards, cache-resume by size). Read adversarially for lost
batches, duplicate/crash-loop stacks, cancel races, DB-handle leaks on error paths, and
non-destructive-reprocess invariants. **No reachable orchestration bug found** — the single-worker
serialisation, the crash-loop guard (mark-attempt-before-stack), the fresh version-tagged basename
that stops a reused `output_name="master"` from archiving the current master, and the best-effort
isolation of per-target failures are all correct and well-tested. **Also dogfooded the one-click
"Process target" autonomy chain end-to-end** on a realistic 1920×1080 8-sub single-field stack
(scan → solve → `run_stack` → `build_auto_recipe_for_run` → preview vs full-res export): `is_mosaic`
persists `False`, the Auto recipe is sane, preview↔export parity **1.5% mean / 7.0% p99** (the known
star-edge decimation limit on a proxy_scale-2 grid), median grey 0.19, R/G/B balanced (0.196/0.174/
0.196). **One image-quality opportunity logged to Ideas (not a bug):** on a *busy or very-flat*
1080px field the Auto recipe's `background.final_gradient` gives up entirely (its object mask covers
>80% of every 256px box → `Background2D` raises → op dropped) — verified it fails **consistently on
both preview and export** (so it is *not* a parity bug; op_errors surfaces it), but the beginner
silently loses gradient removal on cluster/dense-star targets; a graceful-degradation idea filed
below. Realistic gradient+nebula frames flatten cleanly (0.097 mean change, proxy==full-res).
Baseline suite green: 841 passed, 2 skipped.)_

_(Builder big-picture dogfood 2026-07-08 (v0.94.7 baseline): re-traced the real
`build stack → one-click Auto → live-preview proxy → full-res export` journey end-to-end on a
realistic **1920×1080, 12-sub dithered single-field** OSC stack (independent per-frame noise,
shared stars, sub-pixel dither; κ-σ stack). Healthy: `is_mosaic` persists **False**, the Auto recipe
is the full sane chain (`final_gradient → color_calibrate → denoise → stretch → scnr → saturation →
curves → sharpen` — both denoise **and** sharpen present at `sky_sigma≈0.016`, mid-crossfade),
**preview↔export parity 1.89% mean / 6.4% p99** (within the documented star-edge decimation limit at
proxy_scale 2), full 0..1 range, ~0.9% NaN border. **No wrong-image bug found** — consistent with the
mature engine/editor audits. Scanned the whole engine+webapp for TODO/FIXME/HACK (only one, in the
deprecated Qt GUI) and confirmed no open PRs and no recent in-flight branches. **One genuine
image-quality observation filed (not shipped — real-data-gated, most-used Auto path):** Auto's `tone.scnr`
one-sided green clip rectifies background noise and biases an already-neutral background slightly magenta
(export R/G/B 0.243/0.209/0.243; reproduced numerically on a neutral σ=0.03 background, green median
−0.010). Logged to Image-quality Ideas for the Scout to vet on real green-cast OSC data. Backlog is
otherwise genuinely dry of ready, safe, headless Builder work (recent v0.94.x commits are all small
polish), so this run files findings rather than manufacture marginal work (AGENTS.md §2/§3). Baseline
suite green: 887 passed, 2 skipped.)_

_(Builder run 2026-07-08 (v0.94.17 baseline): confirmed both suites green (Python **896 passed, 2 skipped**;
frontend **588 passed**, `tsc` clean) before touching anything. Surveyed for ready Builder code work and
found the backlog **genuinely dry**: the one open Bugs entry (dead SExtractor skew guard) is explicitly a
real-data-gated non-Builder change; the top open Ideas are real-data-gated (SCNR/`sky_sigma`), need owner
sign-off (first-open Auto seed, `vite@8`), or need networked/classifier plumbing (luminance-bg nudge — see
the feasibility note under that item). **Verified two things a Builder might have blindly grabbed are not
ready:** (1) editor op **help text is already complete** (every OpSpec + every param has `help` except the
`tone.curves` curve-widget, which is expected), so "add plain-language help" is done; (2) every Stack-form
**nudge already has its one-click action** (transparency/quality-weight/photometric/drizzle/streak/min-max/
auto-grade), so that family is complete. **Fresh in-process Auto dogfood** (realistic 1200×1600 nebula +
400 stars + left→right gradient + NaN border, low σ=0.003 noise): Auto emitted the sane chain
`final_gradient(luminance) → color_calibrate → denoise → stretch(stf) → scnr → saturation → curves`,
**preview↔export parity 1.97% mean / 7.85% p99** (proxy_scale 2, within the documented star-edge decimation
limit), full 0..1 range, 2.3% NaN border, medians R/G/B **0.197/0.179/0.197**. The green-low medians and the
**no-sharpen** pick both *reproduce the two already-logged real-data-gated observations* (SCNR magenta
background; gradient inflating `sky_sigma` → over-denoise/no-sharpen) — **no new bug**. Filed the SIMBAD-vs-local
feasibility note on the luminance-bg item; no code shipped (idle run leaving `main` green is a success,
AGENTS.md §2).)_

_(Builder engine-hardening audit 2026-07-08 (v0.94.1 baseline): fresh adversarial audit of the
stacking/calibration path with **numeric brute-force repros**, not just reading — the
`MinMaxRejectAccumulator` order statistic (matched a brute-force top/bottom-k reference *exactly*
for k=1,2,3,5 across all four coverage bands, via both `add()` and windowed `add_window()` with
random offsets/NaN), `WelfordAccumulator` mean/std (matched `np.nanmean`/`nanstd(ddof=1)` with 25%
random NaN), `WeightedSumAccumulator` (weighted average + NaN=gap preserved), `DrizzleStacker.result()`
(already a weighted average — not re-divided by coverage), and the two-pass drizzle reject (a 500-ADU
spike over 20 frames is correctly rejected to ~100; the 6-frame no-fire is the documented
`(n−1)/√n < κ` limit, not a bug). Close-read confirmed cross-pass weight/scale symmetry
(`photometric_scales` applied before the consumer in **both** κ-σ passes and in drizzle stats+final;
quality weights correctly in pass-2 combine only, provenance-gated to match), calibration
(no double-subtract; `_effective_dark` single pedestal; flat direction/floor; `apply_raw` never mutates
input; photometric scale direction hazy→up), NaN=coverage everywhere incl. `level_by_coverage`, and the
`_imap_bounded` memory cap on both paths. **No reachable image-corruption bug found** — clean, consistent
with the prior audits. One near-unreachable robustness note logged to Infra below (subpixel-shift edge
`cval=0` vs NaN). Baseline suite green: 876 passed, 2 skipped.)_

_(Builder engine-hardening audit 2026-07-06 (v0.86.1 baseline): another adversarial read of
the stacking/calibration path, going deeper on the areas prior audits didn't explicitly cover
— the recently-added `MinMaxRejectAccumulator` k-insertion order statistic + its four
coverage bands (verified numerically for k=1,2 incl. a satellite outlier), the two-pass κ-σ
NaN=coverage survival at a single-coverage mosaic-edge pixel, the `weights`/`photometric_scales`
application in *both* passes of every path (fresh per-frame `win_rgb`, so `*= scale` is safe
and NaN-preserving), `DrizzleStacker.result()`/variance/reject, and `calibrate/apply.py`'s
bias-vs-dark exclusivity + exposure-scaled dark. **No reachable image-corruption bug found** —
the combine maths, NaN=coverage, and neutral fallbacks are correct, consistent with the prior
clean audits. **One genuine provenance-honesty bug found and fixed (v0.86.2, see Shipped):** a
`quality_weighted` + `min_max_reject` stack stamped WGT* provenance even though the order
statistic ignores the weights. Also **dogfooded stack→auto-edit→export end-to-end** on both a
single-field (parity 0.50% mean; median grey 0.238; R/G/B 0.252/0.217/0.253) and a 2-panel
mosaic (coverage-level → gradient → stretch → crop; NaN gaps correctly trimmed; median grey
0.242) — both healthy. Two low-severity provenance notes for the Scout (not shipped, near-
unreachable): (1) the `STACKER` FITS card reads `min-max-reject` even when `min_max_reject` is
on but the min/max path *didn't* run (n<3 falls back to sigma-clip/mean), a smaller sibling of
the WGT* fix; (2) `final_gradient` still no-ops (op skipped, Auto completes) on a sub-~768px
frame whose object mask covers >80% of every box — the already-logged near-unreachable
small-image robustness item, unaffected by real ≥1080px Seestar stacks.)_

_(Builder engine-hardening audit 2026-07-05 (v0.84.7 baseline): adversarial read of the
current-focus stacking/calibration path — `stacker.py`'s κ-σ pass-2 clip
(`valid & (|aligned − mean| ≤ κ·std)`, NaN-std → +inf keep-all), the min/max-reject and
drizzle two-pass gates, the per-frame `weights`/`photometric_scales` application, and
`calibrate/apply.py` (`_effective_dark` bias+exposure guards, the never-double-subtract
pedestal, flat floor/normalise). **One genuine latent correctness bug found and fixed
(v0.84.8):** the two stacking passes looked up per-frame weight/scale with
`mapping.get(f.id or -1, 1.0)`, which drops a frame with `id == 0` to the neutral default
even though the maps are keyed by the real `f.id` — a store/lookup key mismatch (unreachable
today since SQLite ids start at 1, but a real data-integrity fragility in the final-image
path). Everything else — NaN=coverage, the rejection maths, the neutral calibration
fallbacks — is correct and well-tested, consistent with the prior clean audits.)_

_(Scout QA audit 2026-07-05 (v0.83.0 baseline): rotated the focused subsystem audit
onto **render + QC + the newest engine additions** — `render/thumbnail.py`
(`asinh_stretch`/`autostretch` MTF, the NaN-aware normalize, the striding
decimation that preserves NaN=coverage, `render_stack_png`'s display-space
verbatim path) and `render/colormap.py`; `qc/grading.py` (the modified-z /
MAD-fallback / practical-significance floors, the `MAX_REJECT_FRACTION` rail, the
log-domain non-positive handling); and the freshest final-image-affecting code:
`stack/photometric.py` + its two application sites in `stacker.py`
(`ref/transparency_score` direction, `win_rgb *= scale` / drizzle `rgb * scale`)
and `calibrate/apply.py::_effective_dark` (dark exposure-scaling `bias + (dark −
bias)·ratio`, bias-shape + exposure guards). **No new reachable wrong-result bug
found** — scale directions, NaN=coverage, robust-scale fallbacks and neutral
calibration fallbacks are all correct and well-tested. Also **dogfooded the real
stack→edit→export journey** end-to-end through the FastAPI app on an 8-sub
single-field target: `is_mosaic` persists correctly (`=0`), the Auto recipe is
sane, and **preview↔export parity measured 0.00%** on the full auto recipe (the
`background.final_gradient` op gracefully skips identically on both preview and
export for the tiny synthetic frame — the known, already-logged near-unreachable
sub-768 px robustness item). Baseline suite green: 804 passed, 2 skipped.)_

_(Scout QA audit 2026-07-04 (v0.73.0 baseline): rotated the focused subsystem audit
onto the **stacking accumulators + rejection + drizzle + mosaic + coverage-leveling**
(`accumulator.py`, `stacker.py` rejection/pass-2, `drizzle_path.py`, `mosaic.py`,
`bg/coverage_leveling.py`). Read adversarially — WeightedSum/Welford/MinMaxReject
NaN-and-coverage semantics and the k-insertion order statistic, the κ-σ pass-2 tol
(NaN-std → +inf keep-all), drizzle two-pass `clip_reference` (population variance +
Bessel + neff gate) and the pixmap out-of-bounds masking, `compute_mosaic_canvas`
RA-wrap + outlier rejection + size/area caps, and `level_by_coverage`'s per-level
SExtractor-mode subtraction. **No new reachable wrong-result bug found in the
combine maths** — the reductions, NaN=coverage, and memory guards are correct and
well-tested. The one filed bug above (single-field↔mosaic misclassification) came
from **dogfooding the real stack→edit journey**, not the maths. One low-severity
robustness inconsistency logged to Infra (not shipped): the iterative canvas-shrink
fallback in `compute_mosaic_canvas` (only reached when the union exceeds
`MAX_CANVAS_PX`) picks its "worst" frame with a plain `np.median` of corner RA
(`mosaic.py:287`), re-introducing the RA=0 wrap error that `_circ_mean_ra_deg` was
added to fix in the primary outlier pass — so a group straddling RA=0 *and* over the
16000 px cap could drop a good central frame. Baseline suite green: 731 passed, 2
skipped.)_

_(Scout run 2026-07-04 (v0.72.4 baseline): rotated the focused QA audit off the
much-scrutinised editor onto the **calibration + stack alignment** subsystems and
read them adversarially — `CalibrationMasters.load`/`apply_raw` (dark/bias
double-subtract guard, flat floor+normalisation, flat-dark subtraction, shape
guards), `build_master`/`_sigma_clip_mean` (NaN-fallback, even-sampling cap,
mode/median/mean paths), the library master store + `recommend_masters`/
`_match_distance`/`_recommend_flat_dark`, and `align.py`'s per-frame
load→calibrate→debayer→reproject (windowed footprint bbox, NaN/valid-mask
semantics, sub-pixel shift NaN propagation, CPU/GPU cval parity). **No reachable
wrong-result bug found** — the pedestal-selection, NaN=coverage, and shape
validation are all correct and well-tested. One low-severity robustness asymmetry
logged to Infra (not a shippable bug): `background.final_gradient` lacks the
image-size box clamp that `background.subtract` has, so on a sub-box (<~768 px)
image its editor wrapper *raises* ("edit op failed: Gradient removal") instead of
gracefully no-op'ing — reproduced on a 200×220 array, but near-unreachable for a
real ≥1080 px Seestar stack. Also **visually vetted the top P1 idea** (the Auto
contrast curve) on rendered dim stacks and marked it ✅ unblocked/ready — see Ideas.
Baseline suite green: 725 passed, 2 skipped.)_

_(Scout QA audit 2026-07-04: adversarial re-audit of the **editor** subsystem
end-to-end — engine ops (`tone`/`detail`/`stars`/`geometry`/`background`),
pipeline, proxy, registry, recipe/preset validation, the stretch functions, and
the webapp editor router. Verified NaN/coverage preservation across every op after
a stretch (no lost/spurious coverage, no fake-black), the degenerate-input guards
(Levels/Curves/crop/params), and proxy↔export parity of the spatial ops
(within the inherent ≤2% mean decimation sampling limit). **No new verified bug
found** — the subsystem is well-hardened. Full Python suite green: 688 passed, 2
skipped.)_

_(Builder big-picture dogfood 2026-07-04: re-traced `stack → open editor → Auto →
preview → export` end-to-end on realistic synthetic OSC stacks (sky + nebula +
stars, green tint). Auto-process lands a balanced, well-exposed one-click result
(median ≈0.24 display grey, R/G/B medians equal after gray-star + SCNR); the auto
`detail.denoise ↔ detail.sharpen` crossfade and mosaic handling behave as
documented; and proxy↔export parity for the whole auto recipe on a decimated
proxy (`proxy_scale 2`) measured **0.93% mean** |preview−export| (p99 2.8%, max
4.9% — localized star-edge sharpen/denoise on the decimated grid, the known limit)
— confirming the "what you see is what you export" P1 promise holds. **No new bug
or clear ready Builder task found; the editor + Stack-form autonomy are mature.**
Full suite green: 721 passed, 2 skipped.)_

_(Builder big-picture dogfood 2026-07-04 (v0.72.4 baseline): adversarial fuzz of
the **whole editor engine** — every op + all four built-in presets + the `auto`
recipe run through `apply_recipe` across proxy scales 1–8× on realistic OSC stacks
(sky+stars+green-tint) *and* mosaic-gap (NaN) inputs, checking for exceptions,
spurious NaN in the covered region, and out-of-[0,1] display output. **No
reachable bug found** — the only invariant violations surface exclusively on
degenerate **1-px-thin** images (a 1×N / N×1 array makes `detail.denoise`
wavelet emit all-NaN and `bilateral` raise `IndexError`), which cannot occur for
a real ≤1500 px Seestar proxy (a linear-stage op always sees the full proxy, never
a sliver — crop is nonlinear/after it, and no aspect ratio collapses an axis to
1 px at ≤1500 px). Logged as a low-priority robustness note (Infra) rather than
shipped, since a guard for an unreachable input is exactly the busywork AGENTS.md
§2 warns against. Also reviewed the full editor UI (1298-line `Editor.tsx`) and the
Stack form: every consequential control already carries a data-driven "from your
image" suggestion with provenance-naming labels, escape hatches, and footgun
guards; the Stack form already has streak/κ-σ/transparency/quality-weight hints +
auto-grade preview + memory estimates. **Backlog is genuinely dry of ready Builder
work** — the top item (Auto contrast curve) is legitimately blocked pending Scout
visual vetting on dim stacks, which a headless Builder can't do on a live install.
This run files findings for the Scout rather than manufacture marginal work.
Baseline suite green: 725 passed, 2 skipped.)_

_(The v0.67–0.69 runs fixed a large batch of verified bugs — Gaia colour cal,
RA≈0 frame rejection, debayer edge wrap, job-cancel result loss, hung-Gaia
timeout, several input-validation 500s, the NaN-through-stretch invariant, the
Save/undo-history race, the deconvolution preview understatement, the letterboxed
trim-crop overlay, the mouse-only curve points, and more. Their write-ups moved
to **Shipped**.)_

---

## Ideas (priority order — work top sections first; AGENTS.md §1)

### ⭐ Editor — make it excellent (PRIORITY 1)
The editor is where a good stack becomes a good *picture*, and it has real
problems. Dogfood it every big-picture run and fix root causes.
- **Live preview** — the preview must show **every** enabled action (that's the
  whole point of it). **DONE (v0.57.0):** the last hold-out, Deconvolution, was
  `proxy_safe=False` and got *skipped* in preview (only a badge told you it was
  hidden); it now renders on the proxy with a `proxy_scale`-corrected PSF, and the
  pipeline no longer skips any op. What remains here is *responsiveness* (heavy
  ops on the proxy can lag) and closing any remaining proxy↔export look
  differences — chase those, but never by hiding an action again. (S–M, editor)
- ~~**Give the Auto recipe a gentle contrast curve (as the presets already do)**~~ — **shipped v0.73.0** (see Shipped). The one-click Auto recipe now appends a data-driven `tone.curves` (auto contrast) after the saturation boost, matching the built-in galaxy/nebula presets.
- ~~**Reflect the auto-contrast curve's shape in the Curves widget (v0.73.0 follow-up).**~~
  — **shipped v0.74.4** (see Shipped). Both options landed: (a) when `auto` is on and the
  points are still identity the Curves widget now draws the derived shape (from the
  `…/editor/curve-suggestion` endpoint) as a read-only dashed ghost so it matches the
  preview, and (b) a "Bake to edit" button materialises those points into the recipe and
  clears `auto` so the user can hand-tune from the real shape.
- **Confusing / clunky controls** — too many ops with terse params and no obvious
  starting point. Add plain-language help, a simple/guided default layout, curated
  presets, and progressive disclosure of advanced ops so a beginner gets a good
  result without understanding every knob. (M, editor)
- **Weak default result** — the auto/default processing should produce a genuinely
  good image out of the box for a typical Seestar OSC stack (good stretch, colour,
  gentle denoise/sharpen). Improve the auto recipe so "Auto" is a great one-click
  start. (Gentle SCNR green-cast removal added to the auto recipe in v0.56.6 —
  more of these incremental tweaks welcome.) (M, editor)
- **Seed the editor with the Auto recipe on first open** — moved to **Needs owner
  sign-off** (2026-07-04): it's high-value PRIORITY-1 work, but its value *requires*
  it to be **on by default** (an off-by-default first-open seed helps no beginner),
  which trips the non-negotiable "new features off by default / defaults don't change
  behaviour on a live install" guardrail (AGENTS.md §9/§10). A Builder prototyped it
  (holds the editor on a loader while the one-time Auto build resolves, applies it as
  a single undoable step, only when the saved recipe is truly empty, never persisted
  unless Saved) and confirmed it's clean and reversible — but it does change the
  editor's default first-open view and supersedes the current empty-pipeline nudge, so
  it needs the owner's explicit OK for the default-on flip. See the sign-off entry.
- ~~**Name the "Auto curve" button's goal + dim it when already applied**~~ —
  **shipped v0.72.1** (see Shipped). The Curves header "Auto curve" button now
  names the grey it lifts the midtones toward and dims to a disabled "✓" once the
  current points already equal the suggestion, completing the data-driven family's
  name-the-goal + dim-when-applied consistency.
- **Editor bug hunt (ongoing)** — there are undocumented issues. Each big-picture
  run, use the editor end-to-end and fix what's broken/ugly: op failures, export
  mismatch, undo/state glitches, mobile layout, error handling. (ongoing, editor)
- ~~**Data-driven "From your image" starting curve for the Curves op**~~ —
  **shipped v0.72.0** (see Shipped). The Curves op now has a header "Auto curve"
  button that drops a gentle, strictly-monotone midtone-lift curve derived from the
  image's own histogram, completing the family of data-driven tonal defaults.
- ~~**Wavelet-denoise preview↔export parity**~~ — **investigated & closed as a
  non-issue (2026-07-04, Builder).** The concern was that a BayesShrink multi-level
  DWT tuned on the ≤1500 px proxy would smooth visibly differently on the full-res
  export. Measured it directly: denoise a 2400² synthetic (smooth signal + stars +
  white noise) at full-res, then compare that result *sampled to the proxy grid*
  against denoising the strided proxy — the standard preview↔export parity check.
  The mean |preview − export| is only **0.37 % of range at proxy_scale 2** and
  **0.53 % at proxy_scale 4** — well within the inherent ≤2 % decimation-sampling
  limit the Scout already documented for the other spatial ops. Explicitly capping
  `wavelet_levels` to `max_level − log2(proxy_scale)` changed the parity by <0.001 %
  (BayesShrink's per-subband threshold is estimated from the data, so it self-adapts
  to the level count). There's no measurable mismatch to fix, so shipping a
  `wavelet_levels` cap would be pure churn — dropped per AGENTS.md §2 ("don't
  manufacture busywork").
- **"Original" compare should match the stack's own baseline** — the editor's
  Compare ("Original") renders an *empty* recipe, which the backend tone-maps with
  a hard-coded default asinh (stretch 0.5 / black 0.35). **Analysis (2026-07):** that
  default *matches* the `render_stack_run` endpoint's own defaults (`_STRETCH_DEFAULT
  0.5 / _BLACK_DEFAULT 0.35`), so if the user saw the live adjustable render before
  editing, "Original" already lines up. The real mismatch is against the run's
  **stored** `preview_path` PNG (History/Target thumbnail), which `_write_preview_png`
  renders with `_autostretch_for_export` (MTF/STF), *not* asinh — a different look —
  and which `save_stack_preview` may have overwritten at a user-chosen stretch (whose
  values aren't persisted on the run). The clean, fully-honest fix is to serve the
  run's actual stored `preview_path` as the "Original" overlay (literally what the
  user saw), accepting that it's the ≤1024 px preview rather than the ≤1500 px editor
  proxy. Care: it's a behaviour change to Compare, so gate/validate the resolution
  swap doesn't jar the A/B. (S, editor/trust)
- ~~**Split-slider before/after in the preview (drag a divider to reveal Original vs
  Edited in one frame).**~~ — **shipped v0.78.0** (see Shipped). A new "Split" mode
  button next to Compare overlays the Original on the edited preview and clips it with
  a draggable vertical divider (left = Original, right = Edited), so the user judges
  exactly what a change did in one frame. Frontend-only, additive, its own mode
  (Compare stays a toggle).
- ~~**Split divider for the *per-op* "show without this op" compare too.**~~ —
  **shipped v0.80.0** (see Shipped). A "Split this op" button next to "Without this op"
  drags a divider to compare the image *with* vs *without* just the selected op
  (left = without, right = with), reusing the shipped `splitCompare.ts` helpers and the
  existing per-op `withoutOpPreview` render.
- ~~**A/B two saved looks with the split divider (recipe-A vs recipe-B).**~~ —
  **shipped v0.88.0** (see Shipped). A "Compare a look" picker (Auto + built-in + saved
  presets) next to Split/Compare renders the chosen look on the proxy via the ordinary
  `…/editor/preview` endpoint and feeds it into the *same* split-divider overlay as the
  "before" image, so the user drags to judge their current edit against any other look in
  one frame without committing to it. Built-in presets are sized to the target's data +
  made mosaic-aware exactly as *applying* them would be; Auto is fetched fresh (the
  endpoint only returns the recipe, never persists it); the look is rendered on the current
  edit's framing (`lookCompareOps`) so the divider lines up. Frontend-only, additive.
  **Follow-up shipped v0.89.0:** a "Switch to this look" action on the picker (shown while
  a look is being compared) adopts the compared look as the working recipe in one click —
  an undoable step, confirm-gated when it would replace a non-empty edit — closing the
  compare→adopt loop so a user who prefers the compared look switches to it without hunting
  the Presets menu.
- ~~**"Cropped view — showing N% of the frame" indicator + one-click "remove crop".**~~
  — **shipped v0.74.3** (see Shipped). A dimmed advisory caption below the preview now
  fires whenever an *enabled* `geometry.crop` is in the recipe, naming how much of the
  frame is still shown, with a one-click "Remove crop".
- ~~**Mark editor-export runs as display-space so re-editing doesn't
  double-stretch (and the FITS is honest)**~~ — **shipped v0.72.2** (see Shipped).
  Editor exports now stamp an `SSDISPLY` FITS card + honest `BUNIT` and a
  `display_space` options_json flag; the editor proxy, `render_stack_run` and the
  full-res export all skip their default asinh stretch for a display-space run, so
  re-opening/re-rendering an edited run no longer double-stretches it and the FITS
  is self-describing for Siril/PixInsight. Absence = today's linear behaviour, so
  old runs are unaffected.
### Autonomy — "just works" (PRIORITY 2)
- **⭐ OWNER-REQUESTED — "Reprocess everything" — ALL SLICES SHIPPED: (a) v0.74.0,
  (c) v0.76.0–0.77.0, (b) v0.83.0.** The stacking engine keeps improving (better rejection /
  alignment / calibration, bug fixes), but each target's existing stack was produced
  by whatever engine version was current when it ran — so after an upgrade the *final
  images stay stale* unless the user restacks each target by hand. **Slice (a)
  shipped v0.74.0:** a confirm-gated "Reprocess all targets" action on the Settings
  page + a `POST /api/reprocess-all` endpoint enqueue one serial `reprocess_all` job
  that restacks **every** target, reusing each target's last genuine stack run's
  settings (falling back to its saved defaults / global auto-defaults). It's
  non-destructive (each restack is a *new* `stack_runs` row alongside the old output)
  and memory-safe (per-target stacks run serially inside the one job), with
  between-target + within-target cancel and per-target failure isolation. **Remaining
  slices for a future run:** _(none — slice (b) shipped v0.83.0: an optional off-by-default
  `deep_rescan` flag on `POST /api/reprocess-all` re-runs QC / plate-solve / auto-grade over
  each target's existing frames before its restack, so a reprocess after an upgrade picks up
  QC/solve/grading improvements too, not just the stacker's. Best-effort per target, honours
  manual accept/reject (`user_override`), skips the rescan for `stale_only`-skipped targets.
  Settings → "Also re-run QC, plate-solving & grading first" toggle.)_ **Slice (c) shipped:**
  every stack run records
  the producing app version (`engine_version` column, schema 8→9, v0.76.0, surfaced
  on the History card as "made with vX"), and the reprocess action now has an
  **"only outdated targets"** toggle (v0.77.0, default on) — a `stale_only` flag on
  `POST /api/reprocess-all` that skips targets whose newest *genuine* stack was
  already made on the current version, so a large library isn't reprocessed
  wholesale. A **proactive "N targets are out of date" nudge** (Settings nav badge +
  Reprocess-panel Alert, backed by `GET /api/reprocess-status`) shipped v0.81.5, so the
  user is told to reprocess after an upgrade instead of having to remember. What remains is
  a nicety only: a richer dedicated N/total batch progress card (the Jobs summary already
  reports "restacked N/M — K already up to date"). (S remaining — polish only,
  autonomy/image-quality)
- ~~**Finish the *fully-autonomous* path too: chain the auto-edit onto watcher auto-stack.**~~
  — **shipped v0.89.3** (see Shipped). A new off-by-default `auto_edit_on_autostack` setting
  (requires `auto_stack`; Settings → "Auto-edit the auto-stacked master into a finished picture")
  chains the same best-effort `_auto_edit_process_run` helper onto every successful watcher
  auto-stack, so the north-star "drop a night's subs in the incoming folder, walk away, come back
  to a great image" path now returns a finished *picture* instead of a flat linear master. Reuses
  the shipped helper (saved editor recipe + re-rendered thumbnail, fully reversible in the editor);
  best-effort per target so a failed auto-edit never sinks the batch, and it only sets the recipe
  on the *new* run. Off by default (§9). The pipeline summary reports "auto_edited N".
- **Auto-pick the object preset from the image** — **first (safer) slice SHIPPED v0.94.0**
  (see Shipped): the classifier now runs and surfaces as a one-click *preset suggestion* chip in
  the editor (a wrong guess costs a click, not an image) — Auto's output is unchanged. Auto-process
  builds one general recipe, but the built-in presets (galaxy / nebula / cluster) are meaningfully
  different (per-channel vs luminance gradient, star reduction, saturation). **Remaining (higher-bar)
  slice:** actually *seed Auto* from the classified preset's structure instead of the fixed op list,
  keeping the general recipe as the low-confidence fallback. That changes the most-used one-click path
  on a live install, so it should wait until the shipped suggestion chip has gathered real-world signal
  (which classifications the owner accepts on real galaxy/nebula/cluster Seestar stacks) and the
  classifier is validated against real data, not just synthetic archetypes. (M, autonomy/editor)
  _(~~Follow-up idea, spotted shipping v0.94.0: the preset-suggestion chip only shows on an
  **empty** pipeline, so a user who clicks Auto straight away never learns their image was
  classified. Add one dimmed line to the "What Auto-process did" note.~~ — **shipped v0.94.2**
  (see Shipped). A new pure `presetSuggestionSentence` helper turns the (already-fetched,
  always-enabled) `…/editor/preset-suggestion` payload into one dimmed informational line —
  "Your image looks like a Star cluster — its preset is another good starting point to compare."
  — rendered inside the "What Auto-process did" Alert. Purely informational (no button, never
  implies Auto's recipe was wrong), hidden whenever the classifier declined (`preset_id`/`label`
  null), and it surfaces exactly the same already-shipped classification the empty-pipeline chip
  does, so it carries no new classifier-accuracy exposure. Frontend-only, additive.)_
  _(Still open for the Scout once signal exists: log which suggestions the owner accepts vs
  dismisses, to inform the graduation-to-seeding call.)_
  _(Builder note 2026-07-08: a fresh dogfood re-confirmed the current general Auto recipe is
  healthy and well-tuned (single-field: preview↔export parity 0.00%, median grey 0.24, balanced
  R/G/B), so the bar for **changing what Auto emits** is high — a confident classifier really does
  need validating against **real** galaxy/nebula/cluster Seestar stacks, not just synthetic fields,
  before it touches the most-used one-click path on a live install. A **lower-risk first slice worth
  considering**: keep Auto's output unchanged and instead surface the classification as a one-click
  **preset suggestion** — e.g. a dimmed "This looks like a star cluster — try the Star-cluster
  preset?" chip in the editor (and/or a line in the existing "Why these steps?" note) that the user
  can accept or ignore. A mis-pick then costs a wrong *suggestion*, not a worse *image*, so it can
  ship and gather real-world signal (which classifications the owner accepts) before graduating to
  actually seeding Auto. Same cheap cues (extended-vs-point-source fraction, colour spread) computed
  in `analyze_proxy`; additive; testable on the classifier in isolation.)_
- ~~**Chain the auto-edit onto "Reprocess everything" too (finished pictures after an
  upgrade).**~~ — **shipped v0.86.1** (see Shipped). Took the "toggle, off by default"
  direction the Scout note flagged: a new **"Also auto-edit each result into a finished
  picture"** switch on the Reprocess panel adds an `auto_edit` flag to `POST
  /api/reprocess-all` that chains the same `_auto_edit_process_run` helper onto every
  restacked run, so a library-wide reprocess can yield finished *pictures* (a saved editor
  recipe + re-rendered thumbnail), not flat linear masters. Off by default (it seeds an
  editor recipe on many runs at once), only touches each *new* run's own recipe/preview,
  best-effort per run, and fully reversible in the editor — completing the owner-requested
  "reprocess everything → great images" story. The Jobs summary reports "auto-edited N".
- **One-click "process this target"** — **core chain shipped v0.85.0** (see Shipped).
  A prominent "Process target" button on the Target page (+ `POST
  /api/targets/{safe}/process` → `process_target` job) now runs QC → plate-solve →
  auto-grade (when enabled) → stack in a single job, using the target's saved stack
  defaults, so the user reaches a finished master with no form to fill. Additive,
  opt-in, non-destructive (a new run alongside any existing), and independent of the
  global `auto_*` toggles. The stack step is skipped with a clear reason when nothing
  is plate-solved yet. **Remaining slice — SHIPPED v0.86.0** (see Shipped): the Process
  job now chains an *auto-edit* onto the fresh master — it persists the one-click Auto
  recipe as the run's editor recipe (so the editor opens on the finished *picture*, not a
  flat linear master) and re-renders the run's History/Target thumbnail through it. Runs
  only for the explicit Process action (existing manual/auto stacks untouched), best-effort
  (a failure never fails the Process job), and fully reversible in the editor (Reset/undo).
- ~~**Personal default recipe: "save this edit as my default", offered on open
  (opt-in).**~~ — **shipped v0.79.0** (see Shipped). A "Set current as my default" /
  "Clear my default edit" action in the editor's Presets menu stores one library-wide
  recipe; a run opened with no saved edit now offers a one-click "Use my default (N)"
  seed in the empty-pipeline nudge (validated on load, applied as a single undoable
  step, not persisted unless Saved). Off until the user sets one. *(Follow-up if ever
  wanted: auto-apply it on open with zero clicks instead of a nudge button — deferred
  to keep first-open behaviour unchanged and consistent with the "previous edit" nudge;
  the button already delivers the one-click house-style value.)*
- Auto-suggest stack settings from the data (frame count, FWHM spread, streaks)
  so the user rarely needs to touch the Stack form. (S–M, autonomy)
  _(Progress: the Stack form already carries a rich set of data-driven nudges
  (calibration picks, sigma/min-max frame-count guards, streak→min-max-k, transparency
  → quality-weight, transparency-spread → photometric-normalize, auto-grade drop-outliers,
  memory sizing). As of v0.84.6 every one of them is now one-click. A proactive **drizzle**
  nudge shipped v0.87.0 (see Shipped): on a large single-field set (≥200 accepted, solved
  frames — matching the field help's "200+ dithered frames") whose drizzle-*on* dry-run sizing
  fits the memory budget, the Stack form now suggests Drizzle with a one-click "Turn on
  Drizzle", so a beginner sitting on thousands of subs reaches the biggest resolution win
  without hunting the advanced knobs — gated on a feasibility estimate so it never nudges
  toward an OOM-refused run. Remaining genuine gaps a future run could pick up, each needing a
  careful classifier: **lucky_fraction** from FWHM spread (contentious — it drops signal, so
  weigh against quality-weighting); a background/gradient flatten nudge from a measured sky
  gradient.)_
- **Nudge `background_mode='luminance'` for extended-emission (nebula) targets.** (M,
  autonomy/image-quality) `StackOptions.background_mode` defaults to `per_channel` and has **no**
  data-driven nudge in the Stack form (unlike sigma/drizzle/quality-weight/etc.). `bg/per_frame.py`'s
  own docstring is explicit that per-channel flatten is *wrong* on extended emission nebulae ("cyan
  cores, red halos, black holes" — different channel morphology) and that luminance mode is "required"
  there — yet a beginner stacking M42 / Lagoon / North America gets the artefact-prone default with no
  guidance and no way to know the knob exists. Add a Stack-form nudge that suggests luminance mode when
  the target looks like extended emission, with a one-click "Use luminance background flatten".
  _(Partial mitigation shipped v0.99.3: `background_mode`/`final_gradient_mode` now carry plain-language
  help spelling out that per-channel leaves "cyan cores / red halos" on extended nebulae and to switch to
  Luminance for a big diffuse nebula — so the knob is now **discoverable**. That's the safe, no-classifier
  slice; the remaining work here is still the **data-driven auto-nudge**, which stays real-data-gated.)_
  **The
  work is the classifier, and it must be pre-stack** (the editor's extended-vs-point-source classifier
  runs on the *stacked* proxy, too late for a stack setting): candidate cheap signals are the target's
  Simbad/`post/target_id.py` object type when known (galaxy/nebula vs cluster/star), or a quick
  extended-flux fraction on one accepted, debayered, background-subtracted reference frame. Additive,
  off-nothing (only *suggests*; a wrong guess costs a click, and per-channel stays the default), gated on
  a confidence so it never nudges a star field. Serves image quality directly (removes a documented OSC
  colour artefact) and autonomy (one fewer knob the user must know about). Testable on the classifier in
  isolation; validate the suggestion on real nebula vs cluster Seestar stacks before it graduates from
  a suggestion to anything stronger.
  _(Builder feasibility note 2026-07-08: investigated which of the two candidate signals a Builder can
  actually ship headlessly. **The Simbad-OTYPE route is NOT headless-ready:** `post/target_id.py::identify_target`
  is wired **only** into the deprecated Qt GUI (`gui/main_window.py::_on_identify_target`) — nothing in
  `webapp/` or the pipeline calls it, no `object_type` is persisted as project meta, and it is a **network
  SIMBAD call**, so wiring it into the headless stack path adds a networked dependency → that route needs
  owner sign-off (AGENTS.md §10), not a blind build. **So the shippable route is the second one:** a purely-local
  extended-flux fraction on one accepted, debayered, background-subtracted reference frame (no network, testable
  on synthetic archetypes in isolation, real-data-gated only for the graduation-to-suggestion threshold). A future
  Builder should build the classifier as a local measurement and skip the SIMBAD idea unless the owner signs off on
  the network call. `friendly_object_type`/OTYPE mapping (v0.94.17) already exists if the SIMBAD route is ever
  approved.)_
- ~~**⭐ Auto-bind recommended calibration masters in the *autonomous* stack chains (Process target /
  watcher auto-stack / reprocess-all).**~~ — **shipped v0.99.0** (see Shipped). Landed as an off-by-default
  `auto_bind_calibration` setting: the three unattended chains bind the library's best *confidently-matching*
  master dark/flat/bias (stricter than the interactive recommender — a dark only when its exposure matches
  the subs within 25%) when no calibration was chosen, leaving an ambiguous library uncalibrated as today.
  The interactive Stack form is untouched. Original write-up kept below for provenance.
  (M, autonomy/image-quality) — *Scout-filed 2026-07-09, traced.*
  `webapp/calibration.py::recommend_masters` already ranks the library's master darks/flats/bias against a
  target's frames (exposure/gain/temp/dimensions match), but it is wired **only into the interactive Stack
  form** as a one-click "use recommended masters" nudge — the user must open the form and click it. The
  autonomous chains build their `StackOptions` purely from `settings.default_stack_options` → the target's
  saved defaults → explicit options (`webapp/pipeline.py::_stack_target` L1110-1128) and **never consult
  `recommend_masters`**. So a beginner who built masters once but reaches the finished image via the
  one-click **Process target**, the walk-away **watcher auto-stack**, or a library-wide **reprocess-all**
  gets an **uncalibrated** stack — even though a perfectly-matching master dark/flat is sitting in the
  calibration store — unless they happened to save calibration into their per-target defaults. This directly
  undercuts the north-star "drop subs, walk away, get a *great* image" promise (calibration is the single
  biggest OSC image-quality lever after stacking). **Shape:** when a stack in an autonomous chain has no
  explicit `dark_path`/`flat_path`/etc. set, call `recommend_masters` for that target and auto-bind any
  **confident** match (unmatched → uncalibrated exactly as today, so it's off-nothing and never applies a
  mismatched master); stamp the choice into the run's provenance (`CALSTAT` already exists) so the user can
  see what was applied. Purely local (no network), additive, gated on the existing match-confidence logic,
  and testable on `recommend_masters` + the chain in isolation. Serves autonomy (one fewer decision) *and*
  image quality (calibrated frames) at once. Consider surfacing "auto-applied your master dark+flat" in the
  auto-edit "why" note for trust.
- ~~**One-click "Drop N outlier frames" on the Stack-form auto-grade hint.**~~ —
  **shipped v0.83.2** (see Shipped). The auto-grade hint now carries a "Drop N outlier
  frames" button (beside the retained "Review Auto-grade" link) that calls
  `api.autoGradeApply(safe)` and swaps the yellow hint for a green "Dropped N — Undo"
  confirmation; Undo re-accepts the returned `changed_ids`.
  action in v0.81.10 — the auto-grade hint was the last un-one-clicked nudge, offering
  only a "Review Auto-grade" link that navigated the user away.
- ~~**Surface auto-grade's `capped` safety-rail in the *Stack-form* hint too.**~~ —
  **shipped v0.83.2** (see Shipped). When `GradeReport.capped` is set (a whole rough
  session where >25% of frames were flagged), the Stack-form auto-grade hint now appends
  a plain-language "this looks like a rough session — only the worst are recommended;
  review before stacking" sentence, matching the fuller notice the Target page already
  shows.
- ~~**Nudge to turn on Photometric normalization when the run's transparency varies a
  lot.**~~ — **shipped v0.81.3** (see Shipped). The Stack form now fires a sibling nudge
  when the p90/p10 transparency spread across the frames-to-be-stacked is wide (≳ 1.5×)
  and `photometric_normalize` is off, with a one-click "Turn on photometric
  normalization" button.
- ~~**"Apply my last edit to the newest stack" — recipe carry-over across re-stacks.**~~
  — **shipped v0.75.0** (see Shipped). When a re-stacked run opens with no saved edit,
  the empty-pipeline nudge now offers a one-click "Use my previous edit (N)" that copies
  the newest *other* edited run's recipe onto this run (server-validated on load, applied
  as a single undoable step, not persisted unless Saved). The related "personal default
  recipe" idea (a target-independent default) is still open below.
- ~~**"N new subs since your last stack — restack?" — proactively flag a master that's
  stale vs the user's own newer data.**~~ — **shipped v0.90.0** (see Shipped). The Target page
  now counts accepted + plate-solved frames captured *after* the target's most recent *genuine*
  stack run (an editor-export/combine run — `reusable === false` — doesn't reset the clock) and,
  when any exist, shows a "N new subs since your last stack" callout with a one-click **Restack**
  that reuses the existing `processTarget` chain. Frontend-only, additive, read-only detection
  (no backend/schema change); only accepted+solved frames count so rejected/unsolved new subs
  never nag, and the nudge is suppressed while the more-pressing "Ready to process?" /
  plate-solve-setup banners are showing. Timestamps are UTC-normalised so a browser in a non-UTC
  zone can't shift the comparison. Pure helper `countNewSubsSinceStack` + component tests.

### Friendliness (PRIORITY 3)
- ~~**"Why these steps?" — surface the Auto recipe's data-driven reasoning.**~~ — **shipped
  v0.91.0** (see Shipped). All three layers now ship: the *what* (`autoSummarySentence`) and
  the *chosen values* (`autoValueSentence`) were already there, and this run added the missing
  *causal-input* layer — the measured cues that **drove** each pick ("Measured from your image:
  a ~0.10 sky, 4.7 px stars, some background noise, 12% of ragged mosaic edge to trim."). A new
  additive `POST …/editor/auto-analysis` sibling endpoint returns those cues
  (`presets.analyze_auto_inputs`, mirroring exactly what `auto_recipe` consumes: `analyze_proxy`
  sky/noise, the FWHM→sharpen-radius map, the mosaic trim rect), keeping the `…/editor/auto`
  Recipe response shape untouched. The editor fetches it best-effort alongside Auto and shows
  `autoCauseSentence` as a dimmed line above the values in the "What Auto-process did" note, so a
  beginner sees Auto tuned itself to *their* data. Every cue is nullable and degrades gracefully
  (an unmeasurable proxy / no solved stars / a single-field stack simply omits the line).
- ~~**Carry the Auto "why" note onto the *autonomous* auto-edit paths (Process target /
  reprocess / watcher auto-stack).**~~ — **shipped v0.92.0** (see Shipped). `_auto_edit_process_run`
  now stamps a plain-language "what Auto did (and why)" note (new pure `presets.auto_edit_summary`,
  the Python mirror of `autoSummarySentence` + `autoCauseSentence`) as a per-run project meta
  whenever an unattended job auto-edits a run; the run `…/info` endpoint returns it as a nullable
  `auto_edit` field and the History Info panel shows it ("Auto-edited: flattened the background,
  balanced the colour, then sharpened detail · measured a ~0.1 sky, 4.7 px stars."). Additive,
  off-nothing (only annotates runs the auto-edit already touched — manual/un-edited runs get no
  note), and it covers all three chains at once since they share the helper.
- ~~**Show the auto-edit "why" note in the *editor* when opening an already-auto-edited run.**~~
  — **shipped v0.93.0** (see Shipped). A new read-only `…/editor/auto-note` endpoint serves the
  plain-language note a background job stamped (the same `editor_auto_note:` meta the History Info
  panel reads, v0.92.0), and the editor shows it as a dimmed "This picture was auto-edited" note —
  purely explanatory, no new op/control — but *only* while the pipeline is still pristine (a frozen
  seed-signature check) and only when a note was actually stored, so a hand-built recipe never
  surfaces it and it fades the moment the user hand-edits. Closes the trust gap on the surface the
  Process-target deep-link (v0.85.3) actually lands the user on.
- Guided "getting started" / empty states that tell a first-timer exactly what to
  do next; audit every screen for jargon and add plain-language "why" tooltips;
  reduce visible option clutter (progressive disclosure). (M, friendliness)
  _(Progress: the **Jobs page** — the very first screen a beginner lands on after
  clicking "Scan incoming" — was the last route showing raw engine jargon; its
  snake_case job kinds (`pipeline`, `qc_solve`, `editor_png`…) are now translated
  to plain language and its empty state guides to "Scan incoming" — shipped
  v0.84.2. A Builder dogfood of the other five routes (Dashboard/Library/Target/
  History/Editor) found them already well-handled with icon+prose+next-step empty
  states, beginner tooltips, and translated reject/combine labels.)_
- ~~**Surface "N frames couldn't be quality-checked" on the Target page.**~~ — **shipped v0.99.1**
  (see Shipped). Frontend-only, zero backend change: a new pure `countQcUncheckable(frames)` helper counts
  frames whose `reject_reason` starts with `qc_error` (from the already-fetched frames list, any accept
  state), and a dimmed gray Target-page callout ("N frames couldn't be quality-checked") explains they're
  unreadable/corrupt and skipped when stacking, with a one-click "Re-check these frames" that reuses the
  existing QC + Solve action (`only_new_qc=False`, so it retries `qc_error` frames). Original write-up kept
  below for provenance. (S, friendliness/trust) —
  *Scout-filed 2026-07-09, traced.* When `compute_frame_metrics` raises on a frame (unreadable/corrupt/
  truncated FITS), `apply_qc_result_to_db` stamps `reject_reason="qc_error:…"` but leaves the frame
  **`accept=1`** (`webapp/routers/... / seestack/qc/runner.py:75-76`). The consequence: the frame is counted
  as accepted (inflating the "N accepted" figure), it silently drops out of the stack (the stacker skips a
  frame it can't load — verified, no corruption), and — because `reject_reason_counts()` / the `/reject-summary`
  endpoint tally only `accept=0` rows — it **never appears in the "why frames were dropped" breakdown**. So a
  beginner gets zero signal that some subs were unreadable. Add a small, separate Target-page count/callout —
  "N frames couldn't be quality-checked" — computed from frames carrying a `qc_error` reject reason (regardless
  of accept state), ideally with a one-click "Re-check these frames" that re-runs QC on just them (a full
  `run_qc_and_solve` already retries them since `only_new=False`). Read-only detection, additive, no schema
  change. (Note: whether such a frame *should* auto-reject is a separate call — a QC failure isn't always a
  reason to exclude, since detection-only failures still stack fine — so this idea only makes them *visible*,
  not rejected.)
- ~~**Proactive "plate-solving isn't set up yet" banner on the Dashboard.**~~ — **shipped
  v0.94.12** (see Shipped). A dismissible yellow Alert now shows on the Dashboard when
  `GET /api/system` reports ASTAP isn't ready, distinguishing "ASTAP wasn't found" from
  "ASTAP found but no star database" and linking to Settings ("Fix in Settings"), so a
  first-timer catches the setup gap upfront in the one place a beginner always starts —
  not after scanning frames and hitting a wall. A pure `astapReadiness(astap)` helper mirrors
  the exact `astap.found` / `star_db_found` signals the Settings page reads (only a *definite*
  `star_db_found === false` flags the database, so an older backend that omits the field never
  shows a spurious warning); dismissal is one-time via localStorage (guarded), and the banner
  self-clears once ASTAP is set up. Frontend-only, additive, no backend/schema/default change.
- ~~**Extend the Dashboard readiness banner to a missing/unwritable incoming or data folder.**~~
  — **shipped v0.94.13** (see Shipped). `GET /api/system` now carries an additive `folders`
  field reporting the resolved incoming + library directories' `exists`/`writable` state (new
  `_folder_status` helper — cheap, never raises); the Dashboard shows a second dismissible yellow
  Alert (its own localStorage key) when either folder is missing or read-only, distinguishing the
  four cases (incoming/library × missing/unwritable) and linking to Settings. A pure
  `folderReadiness(folders)` helper mirrors the shipped `astapReadiness` pattern (only a *definite*
  `exists`/`writable` false fires, so an older backend without the field never nags; incoming is
  checked before library). Frontend-only wiring + one small additive backend field; off-nothing,
  no default/schema change.
  _(Builder note 2026-07-08: filed while shipping the ASTAP Dashboard banner (v0.94.12). Also
  noted a minor robustness nicety on that banner itself — its dismissal is a single global
  boolean, so a user who dismisses the "ASTAP missing" banner during setup won't see it again if
  ASTAP later *breaks* after having worked. The reactive Settings/Target backstops still cover
  that case, so it's a low-priority polish, not a bug: keying the localStorage dismissal on the
  readiness *kind* (or clearing it when readiness flips to ready) would make the banner re-surface
  on a genuinely new/returning problem. Only worth doing if a run is already in that file.)_
  — **DONE v0.94.14** (both the ASTAP and the new folder banner): dismissal now stores the
  readiness *signature* (`astapReadinessSignature` = `astap`|`database`; `folderReadinessSignature`
  = `{kind}:{problem}`) instead of a bare boolean, so a banner reappears when the live problem
  differs from the dismissed one (a different or returning fault), and still auto-hides once fixed.
  Done as a follow-up while already in `Dashboard.tsx` for the folder banner. Pure signature helpers
  + tests.
- ~~**Make the new "Process target" one-click the guided next step for a fresh target.**~~
  — **shipped v0.85.1** (see Shipped). A dimmed "Ready to process?" getting-started callout
  now appears on a Target whose newest frames haven't been turned into a stack (no stack run
  yet, or accepted-but-unsolved frames present), with a one-click "Process target" button.
  Suppressed while the plate-solve setup banner is showing and once the target is solved and
  stacked, so it fades out rather than nagging.
- ~~**Deep-link the "Process target" result straight to its editor, not just History.**~~
  — **shipped v0.85.3** (see Shipped). `StackResult`/`_stack_target` now carry the new
  `stack_runs` row id, and the Jobs "View result" button points at `/targets/{safe}/edit/{run_id}`
  when known (falling back to History on an older backend), so the one-click Process lands the
  user *on the finished picture* in one hop.
- Better long-job feedback and clearer error messages. (S, friendliness)
  _(~~Idea: map the handful of known fatal `job.error` messages to plain language~~ —
  **shipped v0.84.3** (see Shipped). A `friendlyJobError` helper now translates the
  memory-budget refusal, "nothing plate-solved to stack", empty-alignment, and
  missing-reference-WCS failures into a plain sentence + next step, falling back to the
  raw text verbatim for anything unrecognised. Remaining long-job-feedback ideas welcome.)_
  _(~~Follow-up idea, found while shipping v0.84.3: `friendlyJobError` matches on the raw
  exception *string*, which is brittle if an engine message is reworded. Stamp a stable
  canonical `error_kind` server-side and prefer it in the frontend.~~ — **shipped v0.84.4**
  (see Shipped). `JobManager` now classifies a fatal exception into a canonical `error_kind`
  (`memory_budget`/`no_solved_frames`/`no_alignment`/`no_reference_wcs`) at the catch point,
  persists it (additive `error_kind` column, in-place migration), and exposes it on the job;
  `friendlyJobError(raw, kind)` prefers it and falls back to the string matcher on an older
  backend.)_
  _(~~Follow-up, found while shipping v0.84.4: the calibration **Build-master** job raises a
  bare `FileNotFoundError: No FITS files found in {dir}` when pointed at an empty/wrong
  folder — a common beginner mistake in the darks/flats workflow that showed a raw Python
  exception on Jobs.~~ — **shipped v0.84.5** (see Shipped). Added a `no_fits_in_folder` kind +
  translation ("No FITS frames were found in that folder" + point-at-the-right-folder next
  step), matched on the specific phrase so internal FileNotFoundErrors aren't mis-dressed.)_
- ~~**Actionable "plate-solving isn't set up" banner when a whole target fails to solve**~~
  — **shipped v0.84.0** (see Shipped). When ASTAP (or, best-effort, its star database) is
  missing, every frame's solve fails identically and the Target page now shows one
  actionable banner (with "Re-run QC + Solve" + "Open Settings") instead of a wall of
  "Plate-solve failed" chips with no guidance.
- ~~**Make the star-database "not set up" signal robust (server-side classification).**~~
  — **shipped v0.84.1** (see Shipped). Setup failures (ASTAP/star-database missing) are now
  stored with a stable canonical `reject_reason` at solve time (where the full log is
  available), and the reject-summary response carries a server-computed `solve_setup_problem`
  field the Target banner prefers — so the database case is now as reliable as the
  astap-missing one, not just best-effort.

### Image quality — for the OSC Seestar workflow (PRIORITY 4)
- **Scout to vet on REAL data: does the Auto denoise↔sharpen crossfade over-read a *sky
  gradient* as noise?** (M, image-quality/autonomy) `presets.auto_recipe` picks its denoise
  strength and whether to sharpen from `analyze_proxy`'s `sky_sigma`, measured on the **raw**
  linear proxy — *before* Auto's own first op (`background.final_gradient`) removes the gradient.
  A Builder dogfood (2026-07-08) found `sky_sigma` is materially sensitive to a smooth background
  gradient and to dynamic range: on synthetic proxies, gradient 0.0→0.10 moved `sky_sigma`
  0.071→0.184 at *fixed* noise (crossfade band is 0.012–0.028, so it saturates to "very noisy" →
  full denoise, **no sharpen**). This is very likely just an unrepresentative synthetic (the Scout's
  real-data dogfoods *do* get sharpen chosen, so real proxies read < 0.012), **not** a confirmed
  bug — hence a Scout item, not a Builder change to the most-used one-click path. Worth checking on
  a real light-polluted / strong-gradient Seestar stack whether Auto ever *wrongly* drops sharpen and
  over-denoises. If real: measure the crossfade `sky_sigma` on a **coarsely background-subtracted**
  proxy (a cheap large-box detrend, matching what `final_gradient` will remove anyway) so it reflects
  true pixel noise, not the gradient. Additive, testable on `analyze_proxy`/`auto_recipe` in isolation;
  changing Auto's output needs the usual real-data validation.
  _(Builder measurement 2026-07-08, v0.94.5 baseline — sharpens the case but did **not** ship a change,
  deferring to the two prior deferrals + the real-data requirement. Three findings: **(1) The mechanism
  is real, not merely a low-dynamic-range synthetic artifact.** My earlier same-day probe used a synthetic
  whose 99.5th percentile landed *in the sky* (too little bright signal), which by itself blows up
  `sky_sigma`. With a **realistic** proxy (extended nebula + 400 varied stars → proper normalization span)
  and **low** noise (σ≈0.003), a modest left→right gradient still pushes `sky_sigma` well over `_NOISE_HI`
  (0.028): gradient 0.00→0.05→0.10→0.20 of range → `sky_sigma` 0.015→0.028→0.054→0.098, i.e. Auto flips
  from `sharpen≈0.40` to **sharpen 0.0 / full denoise** by a gradient of only ~0.05. This is exactly the
  light-polluted-but-well-stacked case (gradient present, pixel noise driven low by thousands of subs) —
  arguably *common* for the target user, not an edge. **(2) Op-order proof it's measuring the wrong signal
  by construction:** in `auto_recipe` `background.final_gradient` is the **first** tone/detail op, *before*
  `detail.denoise` — so the noise the denoise op actually sees is the post-gradient-removal noise, yet
  `analyze_proxy` measures `sky_sigma` on the raw (gradient-laden) proxy. **(3) A naïve detrend backfires
  — the fix is non-trivial.** A quick block-median + nearest-neighbour-upsample detrend *increased*
  `sky_sigma` on a flat proxy (0.015→0.058) via block-edge steps, i.e. a poorly-tuned detrend adds
  structure that reads as noise. So the eventual fix must use a genuinely smooth background estimate
  (photutils `Background2D`-style interpolation, or a true low-pass) that removes only the large-scale
  gradient while leaving pixel noise intact — and be validated on a **real** light-polluted Seestar stack
  that it (a) leaves a flat clean stack's `sky_sigma` ≈ unchanged (so clean stacks still sharpen) and
  (b) reads a gradient-heavy-but-low-noise stack as *not* very noisy. Safety of the eventual change:
  flat images ≈ byte-for-byte (detrend ≈ no-op), genuinely-noisy images unchanged (high-freq noise
  survives a coarse detrend), only gradient-heavy-low-noise images shift toward sharpen — but it still
  touches the most-used one-click path, so it stays a Scout/real-data item.)_
- **Scout to vet on REAL data: does Auto's SCNR tint an already-neutral *background* magenta?**
  (S–M, image-quality) `tone.scnr` (`seestack/edit/ops/tone.py::_scnr`) is a one-sided clip — it
  can only ever pull green *down* toward the `0.5·(R+B)` neutral, never up. On data that already
  carries a real green cast (light pollution, OSC green bias) that's exactly right and wanted. But
  on a background that is already colour-balanced and noisy, the clip is asymmetric on the green
  *noise*: positive green excursions get clipped, negative ones are kept, so it **rectifies the
  noise and biases the background median magenta**. Auto applies it at `amount=0.8` after
  `tone.color_calibrate` (gray-star, which has already neutralised the background), so the residual
  it clips is largely noise. **Verified numerically (Builder dogfood 2026-07-08, no change shipped):**
  on a perfectly neutral background (R=G=B=0.30, independent σ=0.03 per-channel noise), `_scnr(amount=0.8)`
  shifts the green median −0.010 and the mean −0.012 (≈0.34σ) — R/B untouched — i.e. a faint magenta
  cast. In the full stack→Auto→export dogfood (realistic 1920×1080 12-sub dithered stack) the export's
  background medians came out R/G/B **0.243 / 0.209 / 0.243** (green ~14% low); a prior audit note
  recorded the same signature (0.196 / 0.174 / 0.196) and read it as "balanced", so this has been live
  and accepted for a while. **Why it's a Scout/real-data item, not a headless Builder change:** it
  touches the most-used one-click Auto path, and whether the clip is a net win depends entirely on how
  much *real* green cast a genuine Seestar background carries (which a headless synthetic can't stand in
  for) — same reasoning as the `sky_sigma` item above. If it reproduces on real neutral-background OSC
  stacks, candidate mitigations to weigh: lower Auto's SCNR `amount`; or protect the background (only apply
  SCNR where signal is above a sky-relative threshold, so the noise floor isn't rectified); or run SCNR
  on the post-denoise image only. Each must be validated so a real green-cast stack still gets its cast
  removed. Testable on `_scnr` / `auto_recipe` in isolation; additive.
  _(Builder dogfood 2026-07-09, v0.99.2 baseline — re-confirmed the artifact and, more usefully, gathered
  a new data point that leans the disposition toward "leave Auto's SCNR as-is." Two synthetic runs through
  the real `auto_recipe`→`apply_recipe` chain: **(1) truly-neutral noisy sky** (R=G=B=0.168 after STF
  stretch, no cast) → `_scnr(amount=0.7)` drops the sky green median 0.168→0.145 (**−14%, a visible magenta
  tint**) while leaving R/B untouched — the pure one-sided-clip-rectifies-noise mechanism, exactly as filed.
  **(2) A green-cast sky** (OSC green bias + gradient), full Auto chain **with vs. without** the SCNR op,
  measured on the background population: *without* SCNR the sky keeps a residual **green excess** (G 0.145 vs
  R/B ~0.127, i.e. +0.017 green) — i.e. `tone.color_calibrate` (gray-star) balances on the *stars* and
  leaves the *diffuse background* green cast **in place**; *with* SCNR the background lands near-neutral
  (G 0.168 vs the 0.172 R/B neutral, only −0.004 magenta). So on a background that carries any real residual
  cast — which post-gray-star OSC backgrounds typically do — SCNR is a **net win** (removes a +0.017 green
  excess for a −0.004 magenta overshoot), and the −14% magenta failure mode needs a background that is
  *already truly neutral*, which gray-star does **not** produce on cast data. This strengthens the existing
  "net value depends on real cast magnitude" reasoning with direct evidence that the common case is
  net-positive, so the safest read is still: **don't blind-change the most-used Auto path**; if a future
  agent does touch it, prefer a **noise-symmetric** mitigation (a soft-clip whose transition width tracks
  the measured background green-noise σ — removes a genuine cast ≫σ as fully as the hard clip while not
  rectifying within-noise excursions) over uniformly lowering `amount` (which would under-remove real
  casts), and gate on a real neutral-vs-cast OSC background sample. No change shipped — the deferral holds.)_
- ~~**Graceful degradation for `final_gradient` on busy / dense-star fields (instead of
  giving up).**~~ — **shipped v0.89.2** (see Shipped). The `Background2D` fit now degrades
  through an `exclude_percentile` ladder (80 → 95 → 100) and, as a last try, a half-size box,
  instead of vanishing when the object mask covers >80% of every box — so a dense cluster / very
  flat field still gets a coarse gradient subtract. The strict `exclude_percentile=80` fit is the
  first rung, so a normal stack's export is byte-for-byte unchanged.
- ~~**Photometric (multiplicative) frame normalization before combine**~~ —
  **shipped v0.81.0** (see Shipped). A `photometric_normalize` StackOptions flag
  (off by default) gain-matches every frame's signal to the run's median
  transparency before accumulation, so haze/airmass flux variation no longer
  inflates the rejection spread or lets hazy nights dim the result. Bounded
  scales, neutral fallback, applied consistently across every stacking path.
- Follow-ups to min/max reject (shipped v0.56.0). (Item (2), the Stack-form
  small-stack hint, shipped v0.56.2; top/bottom-k trimmed-mean reject shipped
  v0.58.0.) No remaining sub-items.
- ~~**Dark exposure-scaling** (slice (b), now that bias is wired for lights)~~ —
  **shipped v0.82.0** (see Shipped). An off-by-default `scale_dark_to_light`
  StackOptions flag scales a master dark's dark current to the light's exposure
  (`dark = bias + (dark − bias)·(t_light/t_dark)`) when a master bias is present,
  so a dark library shot at one exposure calibrates subs at another; neutral
  fallback (unscaled dark) when the bias or either exposure is unknown, and the
  existing dark-exposure-mismatch warning gained a one-click to enable it.
- ~~**Surface dark exposure-scaling provenance on the run Info / History card**~~
  — **shipped v0.82.1** (see Shipped). When a stack actually scaled its dark to the
  subs' exposure, `_build_output_header_meta` now stamps `DARKSCAL`/`DARKDEXP`/
  `DARKLEXP` cards, the run `…/info` endpoint parses them into a `dark_scaling`
  summary, and the History Info panel renders one line ("Dark scaled to sub
  exposure · 30s → 10s"). Omitted (like `PHOTNORM`) whenever nothing was scaled.
- ~~**Proactively nudge dark exposure-scaling from the calibration store**~~ —
  **shipped v0.82.2** (see Shipped). When the dark's exposure is mismatched, no bias
  is selected, *and* the library holds a master bias, the Stack form's dark-mismatch
  Alert now carries a one-click "Select your master bias and scale the dark" (prefers
  the recommended bias, else the first available) that selects the bias and enables
  scaling in one step, replacing the two-step discovery.
- First-class session/night dimension in the project schema (frames only have
  `timestamp_utc`): per-session sky levelling before combine, per-session
  calibration binding, per-night QC roll-ups. Coverage-levelling's docstring
  already names "between sessions" as motivation but keys on coverage count.
  Large but high value for the multi-night Seestar workflow. (L, correctness)
- ~~**Surface how much the stack's rejection actually clipped (trust).**~~ — **shipped
  v0.84.9** (see Shipped). The default κ-σ pass-2 now tallies two scalars over the per-pixel
  keep mask it already computes (contributed vs rejected samples — memory-free, no extra
  canvas), stamps `REJMODE`/`REJFRAC`/`REJNREJ`/`REJNTOT` FITS cards, the run `…/info`
  endpoint parses them into a `rejection` summary, and the History Info panel renders one
  plain trust line ("Rejection clipped ~0.4% of samples (transient outliers)"; "data was
  already clean" at 0%; a caution once the fraction is unusually high).
- ~~**Extend the rejection-clipped trust metric to min/max-reject**~~ — **shipped v0.84.10**
  (see Shipped). `MinMaxRejectAccumulator.rejection_counts()` derives `(n_contributed,
  n_rejected)` from its final `_count` map (memory-free, no streaming change), the min/max
  branch stamps `REJMODE="min-max-reject"`, and `rejectionSummaryText` is now mode-aware —
  min/max's fraction is *structural* (≈ 2k / frames), so it reads "Rejection dropped the ~X%
  most-extreme samples (min/max reject)" with **no** over-clipping caution (a big number at a
  short stack is by design, not a too-tight κ). Drizzle-reject still remaining below.
- ~~**Extend the rejection-clipped trust metric to drizzle-reject.**~~ — **shipped v0.84.11**
  (see Shipped). Completes the rejection-trust family: `DrizzleStacker` now tallies
  `(n_contributed, n_rejected)` memory-free while pass 2 zero-weights outlier contributions
  (`rejection_counts()`), and the stacker's drizzle branch emits a
  `RejectionStats(mode="drizzle-reject", …)` whenever the two-pass reject ran. The fraction is
  *data-driven* (contributions outside `mean ± κ·σ`), so it reuses the shipped FITS-card +
  info-endpoint + History wiring and renders with the sigma-clip trust wording — a small share
  reads "transient outliers", a large one keeps the too-tight-κ caution (unlike min/max's
  structural drop). Plain single-pass drizzle stamps no provenance.

### Features that serve real workflows
- **⭐ OWNER-REQUESTED — "Tonight" night planner: rank the best targets to shoot
  tonight, showing what you've already captured vs. what you haven't.** A
  pre-capture planning view that complements the post-capture stack/edit pipeline:
  for tonight at the owner's site it lists deep-sky targets ranked by how
  *observable* they actually are (rises high enough, clears the trees, away from
  the moon, inside the dark window) and clearly separates **already-targeted**
  objects (badged with how much integration you already have, so you can decide to
  add more) from **not-yet-targeted** ones worth starting. Build it in slices, and
  keep the astronomy core fully useful **offline** — only the weather enrichment
  touches the network:
  - ~~**(a) Offline astronomy core — the bulk of the value, no network.**~~ —
    **SHIPPED v0.95.0** (see Shipped). A new engine module `seestack/nightplan.py`
    (pure `astropy`, offline, deterministic) computes tonight's dark window
    (astronomical −18° with nautical/civil fallbacks for short summer nights, and
    `None` for polar day), and per candidate: max altitude, transit time, usable
    minutes above a configurable min altitude, Moon separation + illumination → a
    0–100 observability score. Candidate set = the user's library targets
    ("already targeted", annotated with subs + integration) + a **bundled 110-object
    Messier catalog** (`seestack/data/messier.json`, static, no network) with the
    catalog copy of any already-targeted object deduped out. Observer location comes
    from new opt-in `site_lat`/`site_lon`/`site_elevation_m` Settings, else it's read
    best-effort from a solved frame's `SITELAT`/`SITELONG` FITS header (the Seestar
    writes these, so it usually "just works"). `GET /api/plan/tonight` serves the
    ranked plan; a new read-only **Tonight** page shows the dark window, Moon phase,
    and two ranked tables ("add more to what you're shooting" vs "start something
    new"). Additive/read-only throughout; new config fields default to unset (§9).
  - ~~**(b) Horizon / tree-cover mask — local, small UI.**~~ — **SHIPPED v0.96.0**
    (see Shipped). A new off-by-empty `horizon_profile` setting (a list of
    `[azimuth_deg, min_altitude_deg]` points) lets the user map where trees /
    buildings / the house block the low sky; `nightplan.HorizonProfile` interpolates
    between the points (wrapping at 360°) and the planner now counts a target as
    usable only while it clears **both** the numeric min-altitude floor *and* the
    obstruction at its azimuth — so an object that transits high but only briefly
    clears the trees ranks below one lower in an open part of the sky. `max_altitude`
    stays the honest physical peak; an empty profile (the default) is byte-for-byte
    the old flat-floor behaviour. Settings → Observing site gets a compact point
    editor (azimuth + compass label + min altitude), and the Tonight page notes when
    the mask shaped the windows (`horizon_active`). Additive, opt-in, upgrade-safe
    (old config → empty mask), pure offline computation.
  - **(c) Weather enrichment — OPTIONAL, needs owner sign-off (new outbound network
    dependency).** Enrich the plan with tonight's cloud cover / seeing / transparency
    from a weather/clear-sky API. This adds an **outbound network call**, which the
    NAS network policy may block and which §9/§10 flag — so it must be **off by
    default, behind a config toggle + user-supplied endpoint/key, degrade gracefully
    to the offline plan on any failure, and is filed under Needs owner sign-off
    before building** (confirm the specific API + that outbound is allowed). The
    astronomy plan (a)+(b) must stand alone without it.
  Additive and read-only throughout (never touches stacks/data); the catalog is a
  static bundled file (no network, no heavy dependency); location/horizon are opt-in
  with sane fallbacks. Overall L; **slice (a) shipped v0.95.0, slice (b) shipped
  v0.96.0** — remaining: (c) the sign-off-gated weather enrichment. ~~A future slice
  could also widen the bundled catalog beyond Messier (a curated Caldwell/NGC set).~~
  — **catalog-widening shipped v0.97.0** (47 curated popular non-Messier NGC/IC targets
  in `data/deepsky_popular.json`, concatenated by `load_catalog()`). Could still grow
  further (a broader Caldwell/NGC/IC set, or a southern-sky pack) — the loader + scorer
  handle any number of objects — but the current 157-object list already covers the
  popular OSC targets, so only worth it if the owner wants more suggestions. (L, autonomy/workflow)
- Annotated sky overlay (label detected objects / show solved field). (M) —
  related to the night planner above; the planner's "plot tonight's targets" view
  can reuse this.
- ~~**Tonight planner: distinguish a waxing vs waning Moon (evening vs morning problem).**~~
  — **shipped v0.97.4** (see Shipped). The Moon card now reads "Waxing gibbous (72%)" /
  "Waning gibbous", "First Quarter" / "Last Quarter", "Waxing crescent" / "Waning crescent" —
  the direction that tells the planner *when* the Moon is up (waxing sets in the evening, waning
  rises after midnight), which the illuminated fraction alone can't. A new offline
  `nightplan.moon_is_waxing(when_utc)` compares the Moon's vs the Sun's ecliptic longitude
  (`0 < Δλ < 180` = waxing), surfaced as an additive nullable `moon_waxing` field on the plan and
  woven into `moonPhaseLabel(illum, waxing)`. New/Full never take a prefix; an absent state
  (older backend) falls back to the plain labels. The optional rise/set-time cue was left for a
  future run. Additive, offline, tested on the pure helpers (Python + TS) and the endpoint.
- ~~**Tonight planner: show tonight's Moon rise/set time on the Moon card.**~~ — **shipped v0.97.5**
  (see Shipped). A new offline `nightplan.moon_window(observer, window)` samples the topocentric Moon
  altitude across tonight's dark window on a 5-minute grid and reports the first setting / rising
  horizon crossing *inside* it (linearly interpolated, rounded to the nearest minute), or an
  `up_all_night` / `down_all_night` flag when the Moon never crosses during the darkness. Surfaced as
  an additive nullable `moon_window` field on the plan (null when no dark window could be computed) and
  woven into the Moon card as one dimmed line under `moonPhaseLabel` via a pure `moonWindowNote` helper
  ("Sets ~23:40, dark after" / "Rises ~01:10, dark before" / "Above the horizon all night" / "Below the
  horizon all night"), replacing the generic "nearer + brighter" hint only when a concrete cue exists.
  Offline, deterministic, upgrade-safe (an older backend without the field falls back to the plain
  hint). Regression tests pin the full-Moon (up all night), new-Moon (down all night), waxing-sets and
  waning-rises cases against real 2026 ephemeris dates with a crossing-direction check, plus the plan
  wiring, the endpoint shape, and the pure TS helper.
- ~~**Tonight planner: fold "is the Moon even up while the target is?" into the observability score.**~~
  — **shipped v0.97.6** (see Shipped). `_observability_batch` now samples the topocentric Moon altitude
  across the same 5-minute dark-window grid it already builds, and weights each target's Moon penalty by
  the **overlap** between that target's *usable* window and the Moon-up interval (`moon_up_fraction` = the
  share of the target's usable samples during which the Moon is above the horizon). A new
  `moon_up_fraction` arg on `nightplan._score` (default 1.0 → old behaviour) scales the existing
  illumination×proximity penalty by it, so a bright Moon that has already **set** — or hasn't yet
  **risen** — while the target is up no longer docks the score. Conservative and monotonic: the penalty
  can only *shrink* (a target's score never drops below the old full-penalty value), so a normal
  moonlit night where the Moon is up all night is byte-for-byte unchanged; only targets observable while
  the Moon is down get relief. Additive, offline, deterministic. Regression tests: the penalty scales
  0→full with overlap (and a zero-overlap score equals an unlit sky); a full-Moon-up-all-night night
  matches the old formula; a waxing-Moon-sets-partway night lifts the penalty on post-moonset targets.
- ~~**Tonight planner: surface *why* the Moon (didn't) hurt a target — a per-row Moon cue.**~~ —
  **shipped v0.97.7** (see Shipped). The planner now exposes each target's Moon-up overlap as a nullable
  `moon_up_fraction` on `PlannedTarget`/`Observability` (the same overlap that weights the score, surfaced
  instead of discarded; `None` when the target has no usable window), and the Tonight page renders a dimmed
  per-row cue from it via a pure `moonCueForTarget` helper — "Moon down for its window" when the overlap is
  ~0 (reconciling a scary single-instant separation with the ranking), "Moon up N% of its window" for a
  partial overlap, and nothing when the Moon is up throughout (the separation column already tells that
  story). Additive/offline (new nullable field, old rows/backends omit it), no score/ranking change.
- ~~**Tonight planner: plan a *future* night, not just tonight (offline date picker).**~~ —
  **shipped v0.98.0** (see Shipped). A new optional `date=YYYY-MM-DD` query param on
  `GET /api/plan/tonight` plans an upcoming night's dark window instead of tonight, capped to a
  sane horizon (`_MAX_LOOKAHEAD_DAYS = 60`, one day of slack behind "today" for timezone skew;
  a bad/too-far/past date is a clean 422). The date is resolved to that night's *local solar noon*
  once the observer's longitude is known (`_reference_for_date`), so the engine's existing
  ±12 h solar-noon search lands on the right night regardless of longitude. `plan_tonight` already
  took the reference moment explicitly, so no engine change was needed; a precise `when` timestamp
  still takes precedence when supplied. The Tonight page gains a native "Night" date picker
  (min = today, max = +60 d) with a one-click "Tonight" reset; the subtitle and both section
  headings name the chosen night ("Start something new on Sat 15 Aug"). Additive (default preserves
  today's behaviour), fully offline, upgrade-safe. Pure helpers `isoDate`/`planDateBounds`/
  `planNightLabel` + `_reference_for_date` are unit-tested, plus endpoint tests for a future date,
  moon-differs-from-tonight, and the far-future/past/malformed 422s.
- ~~**Tonight planner: narrow "start something new" by object type (a quick filter).**~~ —
  **shipped v0.98.1** (see Shipped). A small segmented control (All · Galaxy · Nebula · Cluster · …)
  above the "start something new" table filters the catalog suggestions by object type, so a user
  after "a nebula tonight" cuts straight to it. Pure client-side filter over the already-fetched plan
  (no backend/endpoint change); the fine catalog types coalesce into friendly buckets via
  `objectTypeBucket` (planetary nebula / supernova remnant → Nebula; open/globular cluster + star
  cloud/asterism → Cluster; everything else → Other). The control only shows when ≥2 buckets are
  present and lists just the buckets that actually appear; a stale selection is inert (falls back to
  All). Unit-tested helpers `objectTypeBucket`/`typeFilterOptions`/`filterByTypeBucket` plus component
  tests (filter narrows the list; the control hides for a single type).
### UX & polish
- Mobile layout polish across the newer pages (Calibration, Combine). (S)
- Better empty-states and error messages on long-running jobs. (S)

### Performance (only with a measurement)
- Profile the stack hot path on a large synthetic target; find a safe win that
  doesn't touch memory bounds or correctness. (M)

### Infra / maintainability
- ~~**Low-priority: manual re-stacks (not just reprocess) still overwrite the target's
  `master` output.**~~ — **FIXED v0.81.8** (see Shipped). Took the "newest run stays
  `master`, older run renamed+rerowed" direction the note preferred: `write_stack_outputs`
  now archives an existing output set to a single consistent `{base}_{stamp}` basename
  (keeping the coverage/preview siblings resolvable) and returns the `{old→archived}` map;
  the stacker (and editor-export / channel-combine paths) repoint the previous run's history
  row at its archived files before recording the new run. History now genuinely keeps both,
  and no `stack_runs` row silently serves another run's image.
- ~~**Low-priority (editor): the whole-recipe Split/Compare divider misaligns when an
  enabled geometry op reshapes the frame.**~~ — **FIXED v0.83.3** (see Shipped; upgraded from
  "low-priority" once a Builder editor-UI dogfood traced the more visible half — a cropped
  live preview letterboxing with spurious black bars right after the one-click mosaic "Trim
  border"). Both root causes are fixed: (1) the histogram endpoint now reports the *rendered*
  post-geometry dims (`render_width`/`render_height`) and the preview box is sized from them,
  so a cropped/rotated preview fills the box; (2) the Split/Compare "Original" (and the star-
  mask overlay) are now rendered through the recipe's enabled geometry ops, so both divider
  layers share the edit's framing and line up.
- ~~**Low-priority robustness: mosaic canvas iterative-shrink picks its "worst"
  frame with a wrap-unsafe RA median.**~~ — **FIXED v0.81.9** (see Shipped). The
  iterative canvas-shrink fallback now computes each active frame's centre RA with
  the wrap-safe `_circ_mean_ra_deg` (mirroring the primary outlier pass) instead of a
  plain `np.median` of corner RAs, so a group straddling RA=0° over the pixel cap drops
  the actual far outlier rather than a good central (wrap-straddling) frame. Regression
  test `test_canvas_shrink_loop_drops_the_real_outlier_near_ra_zero` (fails before /
  passes after).
- ~~**Low-priority (editor/consistency): the `denoise-suggestion` endpoint measures the *raw*
  proxy, not the recipe-aware display image.**~~ — **FIXED v0.93.1** (see Shipped). The endpoint
  now accepts optional `recipe`+`uid` and, when the per-op "From your image" button supplies them,
  measures the *linear image entering* the denoise op (prior linear ops applied, default stretch
  suppressed) via the same `_recipe_before_uid` machinery as levels/stretch/curve — so an upstream
  gradient/colour-balance op (the Auto recipe places both ahead of denoise) is reflected instead of
  ignored. With no recipe the bare proxy is measured exactly as before, so the "Your data" noise
  chip + bulk apply (which want the stack's *inherent* noise) are byte-for-byte unchanged.
- ~~**Low-priority (engine/robustness, unreachable today): per-frame weight/scale lookups use
  `weights.get(f.id or -1, 1.0)`.**~~ — **FIXED v0.84.8** (see Shipped). All four hot-path sites
  (`stacker.py` `_pass` weight+scale, `_drizzle_pass` weight+scale) now key with
  `f.id if f.id is not None else -1`, matching how the maps are built, so a frame with `id == 0`
  reads its real weight/scale instead of the neutral default. Regression test
  `tests/test_stack_frame_id_zero.py` (fails before / passes after).
- ~~**Low-priority robustness: `background.final_gradient` has no image-size box
  clamp (unlike `background.subtract`).**~~ — **FIXED v0.84.12** (see Shipped).
  `_fit_background_2d` now clamps `box_size` to tile the image
  (`min(box, max(8, min(h//4, w//4)))`, mirroring `BackgroundOptions.for_image_size`
  on the per-frame path) before handing it to `photutils.Background2D`, so a box wider
  than a small frame no longer leaves too few unmasked boxes to survive
  `exclude_percentile` (which raised and turned into a hard `RuntimeError: edit op
  failed: Gradient removal`, breaking the whole Auto preview/export since Auto includes
  `final_gradient`). On a real ≥1080 px Seestar stack the 256 px box already tiles ≥4×,
  so the clamp is a no-op and exports are byte-for-byte unchanged. Regression tests
  `test_small_image_does_not_raise_and_still_flattens` (fails before / passes after)
  and `test_full_size_box_is_unchanged_by_the_clamp`.
- **Low-priority (editor/consistency, spotted shipping v0.93.1): the bulk "Set all suggested
  values" button still uses the *raw-proxy* denoise strength.** Now that the per-op denoise
  "From your image" button is recipe-aware (v0.93.1), the bulk apply (`dataDrivenDefaults`, driven
  by the eager recipe-independent `denoise` query) can set a denoise strength that differs from what
  the per-op button suggests once a linear gradient/colour op precedes denoise. Defensible as-is —
  bulk apply is a from-scratch "quick start from your data" convenience and the raw stack noise is a
  reasonable seed there — so this is a consistency nicety, not a bug. Only worth aligning if a future
  run is already in that button's wiring. (S, editor/consistency)
- ~~**Low-priority robustness (near-unreachable): `geometry.rotate` on a sub-3-px image blanks the
  whole covered region (NaN=coverage violation).**~~ — **FIXED v0.94.5** (see Shipped). `_rotate`
  was the odd one out of the geometry/detail degenerate-guard family — `_crop` (`<2`), `_resize`
  (`max(1,…)`) and `_denoise` (`<2`) all guard tiny sizes, but rotate did not. Rotation's order-1
  NaN border fill reaches ~1 px in from every edge, so a frame with `<3` px on an axis has no
  interior to survive and came back **entirely NaN** — turning a fully-covered image into "no
  coverage" (reproduced numerically at 2×2, 1×5, 2×3, … via `geometry.rotate`; a `<2` px crop
  upstream can feed exactly a 2×2). `_rotate` now returns the sliver untouched when `h < 3 or w < 3`,
  mirroring its siblings. A no-op on any real ≥3 px image (byte-for-byte unchanged — the full-size
  rotate still grows the canvas and exposes NaN corners). Regression tests
  `test_rotate_on_a_tiny_image_is_a_safe_noop` (2×2/1×5/5×1/2×3/3×2; fails before / passes after)
  and `test_rotate_full_size_is_unchanged_by_the_tiny_guard`. Found by a fresh adversarial
  numeric audit of the editor ops (2026-07-08), which otherwise came back clean.
- ~~**Low-priority robustness: `detail.denoise` on a 1-px-thin image.**~~ — **FIXED v0.94.1**
  (see Shipped). A 1×N / N×1 RGB array made the wavelet path emit all-NaN in the covered region
  (violating the NaN=coverage hard guardrail) and the `bilateral` path raise `IndexError`. `_denoise`
  now guards the degenerate case (`shape[0] < 2 or shape[1] < 2` → return the image untouched),
  mirroring the `geometry` ops' degenerate-size guards — a sliver has no neighbourhood to denoise
  over. Parametrized regression test `test_denoise_on_a_one_px_thin_image_is_a_safe_noop`
  (wavelet/bilateral/tv × 1×N/N×1; fails before / passes after). Reachability was near-nil in
  practice (the crop op's own `<2 px` guard prevents slivers upstream) but it's a reproduced
  violation of a documented invariant + a crash, so worth the cheap guard.
- ~~**Low-priority robustness (near-unreachable): calibration Build-master returns 500 (not
  400) on a null-byte `source_dir`.**~~ — **FIXED v0.94.4** (see Shipped). `POST
  /api/calibration/masters` now wraps `Path(source_dir).is_dir()` in a `(OSError, ValueError)`
  guard and treats a raise (e.g. an embedded null byte → `ValueError` on platforms that raise
  rather than return `False`) as "not a folder" → 400, matching every other bad-input path in the
  handler instead of surfacing a 500. The prior Builder couldn't reproduce the raise on the CI
  container (Python 3.12.3 returns `False`), so the regression test **monkeypatches `Path.is_dir`
  to raise `ValueError` on a null-byte path** (`test_build_master_source_dir_that_raises_is_400_not_500`,
  fails before / passes after) — platform-independent — plus a plain `test_build_master_bad_source_dir_is_400`.
  Defensive/additive; the guard is a no-op on platforms where `is_dir()` returns `False`.
- ~~**Low-priority robustness (near-unreachable): sub-pixel shift fills vacated edges toward 0
  instead of NaN when a window is fully finite.**~~ — **FIXED v0.94.3** (see Shipped). Both
  `align.py::_apply_subpixel_shift` and `_apply_subpixel_shift_windowed` now run the NaN-restore
  block **unconditionally** (dropped the `if nan_mask.any()` guard): the `cval=1.0` order-0 shift of
  the NaN mask treats out-of-frame as uncovered, so the ~1 px edge vacated by the correction shift is
  marked NaN even on a fully-finite window instead of being left as the `cval=0.0` fill (a fractional
  dimming of the ring). A measured shift of ~0 vacates nothing, so it still adds no NaN. Reproduced
  first (a fully-finite frame + a known sub-pixel correction left the vacated edge at 0.0, `isnan`
  count 0), then fixed. Regression tests `test_subpixel_shift_marks_vacated_edge_as_nan_on_a_fully_finite_frame`,
  `test_subpixel_shift_windowed_marks_vacated_edge_as_nan` (fail before / pass after) and
  `test_subpixel_shift_zero_shift_adds_no_nan` (the no-spurious-NaN guard). Was near-unreachable in
  practice (real reprojected frames carry a NaN border; `subpixel_refine` is off by default), but a
  reproduced violation of the NaN=coverage hard invariant with a cheap, additive, byte-for-byte-safe
  fix on real frames — so worth closing while in the file.
- ~~**Extract the RA 0°/360° unwrap heuristic into one shared helper (regression-proofing).**~~
  — **shipped v0.93.4** (see Shipped). The `if span > 180: ra = where(ra>180, ra-360, ra)` unwrap
  is now a single dependency-free `seestack/coords.py` with `unwrap_ra_deg(ras)` +
  `circular_median_ra_deg(ras)`; all three sites (`stack/mosaic.py` `_bbox` **and**
  `_footprint_outlier_indices`, `stack/reference.py::pick_reference_frame`,
  `io/library.py::_median_radec`) call it, so a *fourth* site is hard to get wrong. Centralising
  surfaced + fixed a latent float-boundary edge: a target sitting exactly on the seam medianed to a
  tiny-negative that `% 360.0` folds to exactly `360.0` (outside `[0, 360)`) — the helper now snaps
  that back to `0.0`. New `tests/test_coords.py` pins the boundary cases; the three existing
  per-site wrap regression tests still pass unchanged.
- ~~**Low-priority robustness (ingest, traced 2026-07-08): a transient copy error permanently leaves a
  frame uncached.**~~ — **FIXED v0.94.9** (see Shipped). `ingest_files` now keys `existing` on the
  frame row (not just the source-path string) and, when an already-registered frame is still
  uncached (`cached_path` NULL from an earlier `OSError`) and `copy_to_cache` is on, retries the
  Stage-1 copy on the re-scan instead of skipping it forever. The copy logic is extracted into a
  shared `_copy_to_stage1` helper so the first-ingest and retry paths behave identically; an
  already-cached frame is never re-copied (its skip touches nothing). Regression tests
  `test_ingest_retries_cache_after_a_transient_copy_failure` (fails before / passes after) and
  `test_ingest_does_not_recopy_an_already_cached_frame`.
- ~~**Low-priority robustness (QC, traced 2026-07-09): the watcher auto-pipeline never re-QCs a frame
  that failed on a *transient* error.**~~ — **FIXED v0.99.2** (see Shipped). Took the bounded "retry
  once" direction. `build_qc_arglist(only_new=True)` now re-offers a frame carrying a plain `qc_error:…`
  reject reason (a first, possibly-transient failure) so the auto-pipeline retries it automatically, while
  a *second* consecutive failure is stamped terminal (`qc_error_final:…` by `apply_qc_result_to_db`) and
  skipped thereafter — so a genuinely-corrupt file isn't re-QC'd on every scan forever; a manual full re-QC
  (`only_new=False`) still retries even terminal frames. Bonus correctness fix: a retry that finally succeeds
  now clears the stale `qc_error` reject reason (it no longer shows as "couldn't be quality-checked"), and
  a user/auto reject is never touched. No schema change (upgrade-safe). Regression tests in
  `tests/test_qc_retry.py` + updated `tests/test_qc_idempotent.py` (fail before / pass after).
- ~~**Low-priority robustness (traced 2026-07-08, near-unreachable): opening an empty/foreign
  `project.sqlite` yields a DB with no `frames` table.**~~ — **FIXED v0.94.10** (see Shipped).
  `_migrate_schema` now detects a missing `frames` table (an empty/foreign sqlite at `user_version==0`)
  and runs `SCHEMA_SQL` to build the base schema before applying the additive ALTERs — every statement
  in `SCHEMA_SQL` is `CREATE … IF NOT EXISTS`, so it's a no-op for a genuine older project (which
  always went through `Project.create`) and byte-for-byte unchanged for real migrations. Regression
  test `test_open_empty_sqlite_builds_the_base_schema` (fails before / passes after).
- ~~**Trivial (cosmetic): the ASTAP no-database *hint* still says "(*.290)" only.**~~ —
  **FIXED v0.94.11** (see Shipped). The zero-database hint in `webapp/routers/system.py::_astap_info`
  now reads "no star database (*.290 or *.1476) was found", matching the count (which already tallies
  both) and its own D-series `d05` example (a `.1476` file). Purely cosmetic (fires only in a genuine
  zero-database state); no behaviour or test change.
- **Low-priority (diagnostics): the *drizzle*+quality_weighted coverage_min/max still reports Σweights,
  not a frame count.** *(Builder-filed 2026-07-09, follow-up to the v0.99.6 `WeightedSumAccumulator`
  fix.)* The v0.99.6 fix gave the standard weighted-sum path an honest unweighted `frame_coverage` for
  the "N frames per pixel" diagnostics, and the min/max-reject path already reported a true count — but
  the **drizzle** accumulator's `.coverage` is still Σ of drizzle weights, so a `drizzle=True` +
  `quality_weighted=True` run understates coverage_min/max exactly as the standard path used to. Niche
  (both are opt-in, and drizzle+weighting together is rare), and diagnostic-only (no image impact), so
  low priority. Shape: track an unweighted per-output-pixel contribution count in `DrizzleStacker`
  (increment where a frame's weight footprint is > 0), expose it like `frame_coverage`, and route it
  through the same `frame_cov` branch in `run_stack`. (S, diagnostics/trust)
- **Low-priority (traced, off-by-default): sub-pixel-refine darkens a ≤1–2 px band at an *interior*
  coverage boundary.** *(Builder audit 2026-07-09, PLAUSIBLE — needs a real-frame repro.)* When
  `subpixel_refine=True` (off by default) `align.py::_apply_subpixel_shift_windowed`'s order-1 data
  shift blends real data with the NaN region's 0-fill at a footprint's *interior* NaN boundary, and
  those pixels are kept as covered (only the fully-vacated ring is NaN'd), so a ~1 px ring at a
  data/gap edge dims (measured 100→60 on a synthetic edge, align.py ~L462-472). The science region is
  untouched and it's the same class as the documented `FRAME_EDGE_INSET_PX` tradeoff, so it's low
  severity; the code comment ("shift is <1 pixel") is also inaccurate since shifts up to ~5 px are
  applied. Candidate: also NaN (or inset) the interior-boundary ring, or mark it uncovered so it can't
  darken the average. Validate on a real dithered set with `subpixel_refine` on. (S, image-quality/robustness)
- **Trivial (doc): `calibrate/apply.py:119` comment says flat values ≤0.1·mean are "floored to 0.1"
  but the code sets them to 1.0 (no correction).** *(Builder audit 2026-07-09.)* The behaviour is the
  *safer* choice (a near-zero flat pixel gets no gain applied rather than a ×0.1→×10 amplification);
  only the comment is imprecise. Fix the comment to match on the next pass through that file. (XS, doc)
- Chip away at the ~127 pre-existing `ruff check .` findings (don't add new ones);
  consider wiring ruff into CI once the count is low. (L, correctness/maintainability)
- ~~Add a retention/pruning policy for `jobs.sqlite`~~ — **done, then made
  configurable** (`JobManager._evict_old` + the `job_history_limit` setting,
  v0.51.1). (S, scale)
- ~~Add a `scripts/setup.sh` that provisions the venv + `npm ci` so every
  autonomous iteration starts from a known-green baseline~~ — **done**
  (`scripts/agent-setup.sh`, idempotent; run via `source scripts/agent-setup.sh`).
  Remaining sliver: wire it into an actual `SessionStart` hook so setup is
  zero-tax with no manual invocation. (S)
- ~~**Low-priority robustness (near-unreachable): the Gaia colour solver can compute a *negative*
  blue scale on an extremely-reddened field.**~~ — **FIXED v0.94.16** (see Shipped). `_solve_gaia`
  now clamps both solved channel scales to a physical positive range (`_MIN_CAL_SCALE 0.05` …
  `_MAX_CAL_SCALE 20.0`) before returning, so the linear-in-colour model's negative `expected_bg`
  on a `BP−RP > 2.44` field can no longer make `scale_b` negative and *invert* the blue channel;
  the note records "(clamped an out-of-range channel scale)" when it fires. A no-op on any realistic
  OSC field (solved scales sit near 1.0). Regression test
  `test_solve_gaia_clamps_a_negative_channel_scale` (BP−RP=3.0 → would-be `scale_b ≈ −0.25`; fails
  before / passes after).
- ~~**Trivial (cosmetic): `post/target_id.py` sets `object_type_name` to the raw short code.**~~ —
  **FIXED v0.94.17** (see Shipped). A new `_OTYPE_NAMES` table + public `friendly_object_type(code)`
  helper map the common Simbad OTYPE codes to plain words ("G" → "Galaxy", "GlC" → "Globular cluster",
  "HII" → "HII region", …), covering every code we give a bg-flatten hint for plus the common OSC
  targets; `identify_target` now sets `object_type_name` from it and the GUI identify dialog shows the
  friendly name instead of the bare code. Unknown codes fall back to the raw code (never hide data),
  and a missing code stays `None`. Regression tests `test_friendly_object_type_maps_known_codes_to_plain_words`
  and `test_friendly_object_type_falls_back_to_the_raw_code`.
- Expand `docs/` (webapp.md) to cover calibration, mono/LRGB, auth. (S)
- `npm audit` still reports `esbuild`≤0.24.2/`vite`≤6.4.2/`vitest`≤3.2.5
  (moderate — dev server only, not the production build) after this run's
  `react-router`/`form-data` fix. `npm audit fix --force` wants `vite@8`,
  a real major-version bump across the toolchain (config changes, full
  suite re-verification) — needs a deliberate dedicated pass per
  `AGENTS.md`'s major-dependency-bump sign-off rule, not a blind
  `--force`. (M)

---

## Deprioritised — do NOT invest further (niche for an OSC Seestar owner)
Leave what exists working; don't extend or add to it. Only touch these to fix an
outright bug in existing behaviour, never to add capability.
- Mono / LRGB / **channel combine** (incl. cross-canvas reprojection), narrowband,
  and other filtered/pro-astro features. The owner shoots OSC and gets no value
  from these; they've already absorbed too much effort.

---

## Needs owner sign-off (do NOT start autonomously)
- AI star removal (StarNet-class ONNX): high wow-factor but adds a heavy ML
  runtime + model download that may hit the network policy. Needs an explicit OK.
- Anything that exposes the app publicly, changes auth defaults (e.g. turning auth
  on by default), or is otherwise hard to reverse.
- Live capture / real-time Seestar streaming integrations (explicitly de-scoped).
- **Surface SIMBAD target identification in the headless webapp (opt-in).** The engine
  already has `seestack/post/target_id.py` (`identify_target` → name + friendly object type +
  bg-flatten hint from a target's median plate-solved RA/Dec), but it is **GUI-only** — the
  headless webapp never calls it, so a beginner on the web app never learns "you're imaging
  M42, an emission nebula → use luminance background flatten." Wiring it into the Target page
  (show the identified object + friendly type, and pre-select the bg-mode hint / feed the
  existing "nudge luminance for extended-emission" Stack-form idea) would directly serve
  autonomy + friendliness + image quality. **Why sign-off, not a free build:** it makes an
  **outward network call** from the live install to CDS/SIMBAD (via `astroquery`), which is an
  outward-facing change the owner must OK against the deployment's network policy (guardrail
  §10). If approved it should be **opt-in / off by default** with a cached result per target,
  never blocking the pipeline. (S–M, autonomy/friendliness/image-quality — owner: OK to let the
  server query SIMBAD?)
- **Auto-seed the editor with the Auto recipe on first open (default-on).** When a
  run is opened with no saved recipe, auto-populate the working recipe with the
  `…/editor/auto` output so a beginner's first frame is a good image, not the flat
  default asinh stretch. Directly serves PRIORITY 1 ("out-of-the-box result genuinely
  good") and is fully reversible (Undo/Reset, single undoable step) and non-persistent
  (nothing is saved unless the user hits Save; never overwrites a saved recipe). The
  **only** reason it's here rather than shipped: it's on-by-default (that's the whole
  point — an opt-in seed helps no beginner), so it changes the editor's default
  first-open behaviour on the live install and replaces the current empty-pipeline
  "nudge toward Auto-process" first view. Rollback is trivial and total (UI-only, no
  data/config/schema touched — revert the frontend change). **Owner: OK to turn this
  on by default?** A Builder has a clean prototype ready to finish + test.

_(Normal, tested changes merge to the default branch automatically — see
AGENTS.md §8. Only the items above need a human's OK first.)_

---

## Shipped
_Newest first. One line each: what + commit/PR._
- **v0.99.6** — Honest per-pixel *frame count* for `coverage_min`/`coverage_max` under quality
  weighting (stacking-engine hardening — current focus, Builder 2026-07-09). Found by a deep
  adversarial audit of the stacking hot path (the audit otherwise came back clean of any
  image-corrupting bug). `WeightedSumAccumulator.coverage` is Σ-of-weights, not a frame count, so
  with `quality_weighted` on the persisted `coverage_min`/`coverage_max` diagnostics — surfaced to
  the user as "coverage N–M **frames** per pixel" (History Info) — *understated* coverage (a
  fully-covered 4-frame stack could report max 2; a heavily-weighted 100-frame stack could read
  "0–6 frames"). The accumulator now also keeps a cheap 2-D **unweighted** contribution count
  (`frame_coverage`), and `run_stack` reads it for the coverage_min/max scalars, so "frames per
  pixel" is honest even when weights ≠ 1. `.coverage` (Σweights) is unchanged, so `level_by_coverage`
  and the on-disk `master_coverage.fits` are byte-for-byte identical; an unweighted stack (the
  default) is byte-for-byte identical too (count == Σweights). The min/max-reject path already
  reported a true count; **drizzle+quality_weighted still reports Σweights** (a niche opt-in-on-opt-in
  combo) — logged as a follow-up idea below. Regression tests: `tests/test_accumulator.py`
  (`frame_coverage` semantics: unweighted parity, NaN gaps, windowed) + `tests/test_stack_pipeline.py::
  test_quality_weighted_coverage_reports_frame_count_not_weight_sum` (a weighted 4-frame stack reports
  coverage_max 4, not the weight sum; fails before / passes after).
- **v0.99.3** — Plain-language help on every advanced Stack-form knob (friendliness — priority 3,
  Builder 2026-07-09). The advanced group of the Stack form was a wall of bare jargon: 14 fields
  (Background mode, Background/Final-gradient box size, Hot-pixel suppression + σ, Sub-pixel refine,
  Final gradient mode, Color calibration + mode, Canvas mode, TIFF mode, Drizzle pixfrac/scale/kernel)
  had no `help` tooltip at all, so a beginner opening "Advanced" got no idea what any of them did or when
  to change them. Added a concise "what/why" tooltip to each in `webapp/schemas.py::_DESCRIPTORS` (they
  flow to the tooltip via the existing `HintLabel`, so no frontend change — and the same help now also
  appears on the Settings default-stack-options editor, which reuses `StackOptionControl`). In particular
  `background_mode`/`final_gradient_mode` now spell out the documented OSC gap — per-channel flatten leaves
  "cyan cores / red halos" on extended emission nebulae, so switch to Luminance for a big diffuse nebula —
  a safe, no-classifier slice of the still-open luminance-bg nudge idea (surfaces the knob so a beginner
  can find it, without touching Auto/defaults). New regression guard
  `test_every_form_field_has_plain_language_help` (fails before / passes after) keeps future fields from
  shipping without help. Purely additive descriptor text, zero behaviour/default/schema change,
  upgrade-safe.
- **v0.99.2** — Retry a transient QC error in the auto-pipeline (autonomy/robustness — priority 2,
  Builder 2026-07-09; Scout-traced, the QC analog of the v0.94.9 ingest cache-copy retry). When
  `compute_frame_metrics` raised on a frame (a transient read blip — NAS hiccup, a file still being
  written), it was stamped `qc_error:…` and `build_qc_arglist(only_new=True)` treated it as permanently
  "done", so the watcher auto-pipeline never re-measured it — it stayed uncheck-able until a manual full
  re-QC. Now a first `qc_error` is **re-offered once** by the auto-pipeline; a second consecutive failure
  is stamped terminal (`qc_error_final:…`) and skipped thereafter, so a genuinely-corrupt file isn't
  re-QC'd on every scan forever (a manual `only_new=False` re-QC still retries even terminal frames). Bonus
  correctness fix: a retry that finally succeeds clears the stale `qc_error` reject reason (so it no longer
  shows as "couldn't be quality-checked") while never touching a user/auto reject. No schema change,
  additive, upgrade-safe. `tests/test_qc_retry.py` (retryable→terminal, success-clears-stale,
  user-reject-untouched) + updated `tests/test_qc_idempotent.py`.
- **v0.99.1** — Surface "N frames couldn't be quality-checked" on the Target page (friendliness/trust —
  priority 3, Builder 2026-07-09; Scout-traced). When QC *raises* on a frame (unreadable/corrupt/truncated
  FITS) it's stamped `reject_reason="qc_error:…"` but left `accept=1`, so it inflates the accepted count,
  silently drops out of the stack (the stacker skips a frame it can't load), and — because the
  reject-summary tallies only `accept=0` rows — never appears in the "why frames were dropped" breakdown,
  leaving a beginner with zero signal that some subs were unreadable. New pure `countQcUncheckable(frames)`
  helper counts `qc_error`-reasoned frames (from the already-fetched frames list, any accept state) and a
  dimmed gray Target-page callout names the count, explains they're skipped when stacking, and offers a
  one-click "Re-check these frames" reusing the existing QC + Solve action (`only_new_qc=False` retries
  them, in case the read failure was transient). Frontend-only, additive, read-only detection — no backend
  or schema change. Helper unit tests + two component tests (callout appears + re-checks; quiet when clean).
- **v0.99.0** — Auto-bind matching calibration masters to the *unattended* stack chains (autonomy +
  image-quality — priorities 2 & 4, Builder 2026-07-09). `recommend_masters` was wired **only** into the
  interactive Stack form, so a beginner who built masters once but reached a finished image via the
  one-click **Process target**, the walk-away **watcher auto-stack**, or a library-wide **reprocess-all**
  got an *uncalibrated* stack even with a perfectly-matching master dark/flat sitting in the store. New
  off-by-default `auto_bind_calibration` setting (Settings → "Auto-apply matching calibration masters to
  hands-off stacks"): when a stack in one of those chains has no calibration chosen, a new pure
  `calibration.auto_bind_master_paths` picks the library's best **confidently-matching** masters and binds
  them — stricter than the interactive recommender (which only *warns* on a poor match): a dark only when
  its exposure matches the subs within 25% (mirroring the Stack form's own `expMismatch` threshold), the
  recommended flat + flat-dark, and a bias only when no dark matched. An ambiguous/mismatched library
  leaves the stack uncalibrated exactly as today, and the bound masters flow through the normal path so
  `CALSTAT` provenance records what was applied. The interactive Stack form is untouched — it still honours
  exactly what the user picked (or deliberately left blank). Off by default (§9): a live install's
  autonomous output is unchanged until the user opts in. Tests: `auto_bind_master_paths` unit coverage
  (confident dark+flat bound / exposure-mismatched dark dropped / bias-only-when-no-dark / empty store),
  reprocess-all integration (auto-binds when on, uncalibrated when off), a regression that the interactive
  form never auto-binds even with the setting on, and a config-upgrade default-off assertion.
- **v0.98.2** — Tonight planner (friendliness — priority 3, Builder dogfood-found 2026-07-09): the
  "Start something new" (and "Add more to what you're shooting") tables listed **every** target the
  planner returns regardless of observability — and the engine returns the whole 157-object catalog, so
  on a typical night ~**half the rows were dead** (targets that never clear the minimum-altitude floor
  tonight: score 0, "—" transit / "—" time-up), diluting the ranking whose entire job is "what's worth
  shooting tonight?" (measured: 79 of 157 fresh catalog rows unobservable at a 40°N / min-alt-30 October
  night). Both tables now list only targets **up tonight** (`minutes_above_min_alt > 0`) and collapse the
  rest into a dimmed footnote naming the count with a "lower the minimum altitude to include them" hint —
  so nothing is hidden (the escape hatch is one control away) but the table reads as a clean shortlist,
  and the "well placed tonight" copy is honest. New pure helpers `partitionByUpTonight` + `notUpTonightNote`
  (unit-tested) + a component test (dead row hidden behind the count); the type filter now derives its
  buckets from the up-tonight set too. Frontend-only, additive, read-only — no engine/schema/API/default
  change (`minutes_above_min_alt` has always been on the response). Dogfood also confirmed the planner is
  healthy end-to-end across polar (no dark window), southern-hemisphere, future-date and min-alt 0/80
  edge cases — no engine bug found.
- **v0.97.8** — Tonight planner (friendliness/autonomy — priority 3, Builder §4 top-up): show *when
  tonight* a target is actually shootable, which the single transit time can't answer (a 7-hour target
  could clear the floor at 21:00 or not until 01:00). `_observability_batch` now derives the usable
  window's enclosing clock bounds from the per-sample above-floor mask it already computes and reports
  them as nullable `usable_start_utc`/`usable_end_utc` on `Observability`/`PlannedTarget` (both `None`
  when never usable); the Tonight page renders them as a dimmed "HH:MM–HH:MM" line under "Time up" via a
  pure `usableWindowNote` helper. Honest: `minutes_above_min_alt` stays the true usable total, so a rare
  horizon-mask gap shows as the enclosing span (exact for the common no-mask case). Additive/offline, no
  score/ranking change. Tests: `test_nightplan.py` (bounds enclose transit & sit in the dark window, span
  matches usable minutes, `None` when never usable) + a `usableWindowNote` block in `tonight.test.ts`. (#PR)
- **v0.97.7** — Tonight planner (friendliness/trust): a dimmed per-row Moon cue explains *why* a
  bright-Moon night still ranked a target well. The planner now surfaces each target's Moon-up overlap
  (`moon_up_fraction` on `PlannedTarget`/`Observability` — the same share the score already computes,
  `None` when the target has no usable window) and the Tonight page renders it via a pure
  `moonCueForTarget` helper: "Moon down for its window" when the overlap is ~0 (reconciling a scary
  single-instant `moon_separation_deg` with the ranking), "Moon up N% of its window" for a partial
  overlap, and nothing when the Moon is up throughout. Additive/offline, no score/ranking change. Tests:
  `test_nightplan.py` (per-target fraction, relief-tracking, `None` for a never-usable target) + a
  `moonCueForTarget` block in `tonight.test.ts`. (#PR)
- **v0.97.6** — Tonight planner (autonomy/trust): the observability score now weights each target's Moon
  penalty by whether the Moon is *actually up* while the target is observable. `_observability_batch`
  samples topocentric Moon altitude over the dark-window grid and passes each target a `moon_up_fraction`
  (share of its usable samples with the Moon above the horizon) to the new `moon_up_fraction` arg on
  `_score` (default 1.0 = old behaviour), which scales the illumination×proximity penalty. Monotonic:
  the penalty can only shrink, so a Moon-up-all-night sky is unchanged and only post-moonset/pre-moonrise
  targets get relief — fewer good targets buried by a Moon that isn't up for them. Offline, additive.
  Tests in `test_nightplan.py` (scaling, up-all-night no-change, waxing-sets relief). (#PR)
- **v0.97.5** — Tonight planner (friendliness): the Moon card now shows *when* the Moon rises or sets
  during tonight's dark window, complementing the phase with a concrete time. New offline
  `nightplan.moon_window(observer, window)` samples the topocentric Moon altitude across the dark
  window (5-min grid) and reports the first setting/rising horizon crossing inside it (interpolated,
  rounded to the minute), or an `up_all_night` / `down_all_night` flag when it never crosses; surfaced
  as an additive nullable `moon_window` field on the plan and rendered as one dimmed line under
  `moonPhaseLabel` via a pure `moonWindowNote` helper ("Sets ~23:40, dark after" / "Rises ~01:10, dark
  before" / "Above/Below the horizon all night"), which replaces the generic "nearer + brighter" hint
  only when a concrete cue exists. Additive, offline, upgrade-safe (older backend → plain hint). Tests:
  `test_nightplan.py` (full/new-Moon all-night, waxing-sets, waning-rises against real 2026 ephemeris
  with a crossing-direction check, plan wiring, no-window case), `test_plan.py` (endpoint carries
  `moon_window`), and TS (`tonight.test.ts` `moonWindowNote`, `Tonight.test.tsx` Moon card). Found
  dogfooding the newest feature.
- **v0.97.4** — Tonight planner (friendliness): the Moon card now distinguishes a **waxing** from a
  **waning** Moon ("Waxing gibbous (72%)" / "Waning gibbous"; "First Quarter" / "Last Quarter";
  "Waxing crescent" / "Waning crescent"), which tells the planner *when* the Moon is up — a waxing
  Moon sets in the evening (early-night targets stay dark), a waning one rises after midnight — a
  distinction the illuminated *fraction* alone can't make. New offline
  `nightplan.moon_is_waxing(when_utc)` (Moon-vs-Sun ecliptic longitude, `0 < Δλ < 180` = waxing),
  surfaced as an additive nullable `moon_waxing` field on the plan (`asdict`) and woven into
  `moonPhaseLabel(illum, waxing)`. New/Full never take a prefix; an older backend without the field
  falls back to the plain labels. Additive, offline, upgrade-safe. Tests: `test_nightplan.py`
  (`test_moon_waxing_matches_the_phase_cycle`, `test_plan_reports_moon_waxing_state`), `test_plan.py`
  (endpoint carries `moon_waxing`), and TS (`tonight.test.ts` waxing/waning labels, `Tonight.test.tsx`
  Moon card). Found dogfooding the newest feature.
- **v0.97.3** — Tonight planner (friendliness): section-accurate empty states. The two target
  tables shared one message — "Nothing here clears your minimum altitude tonight." — which is
  *never* accurate for the "Add more to what you're shooting" (already-targeted) section: the engine
  always lists a positioned library target in the plan (with score 0 if it doesn't clear the floor),
  so that section is empty **iff** the user has no positioned library targets, not because of
  altitude. A first-timer with an empty library was told the wrong reason. `TargetTable` now takes an
  `empty` message: the already-targeted section says "You haven't shot any targets with a known
  position yet — start something new below."; the catalog section keeps the (accurate-there) altitude
  message with a "try lowering it" nudge. Frontend-only, additive. Component regression in
  `Tonight.test.tsx` (empty library shows the guidance, not the altitude blame). Found in the same
  §2 dogfood as v0.97.2.
- **v0.97.2** — Tonight planner (friendliness): the "Minimum altitude" picker no longer renders
  **blank** when the user's `min_target_altitude_deg` setting isn't one of the round presets. The
  Settings input steps by 5° (so 15° / 45° / 55° are all reachable) but the Tonight `Select` only
  listed {10,20,30,40,50}, so an active floor like 45° left the control showing nothing (the plan was
  still correct — only the control looked broken). New pure `minAltOptions(active)` helper (in
  `tonight.ts`) splices the active floor into the options list, numerically sorted, whenever it isn't
  already a preset, so the picker always shows the real floor the plan was computed for. Frontend-only,
  additive, no backend/API change. Unit tests for the helper (`tonight.test.ts`: preset/non-preset/
  rounded/null cases) + a component regression (`Tonight.test.tsx`: a 45° floor renders "45°", not
  blank). Found by a big-picture dogfood of the newest feature (§2).
- **v0.97.0** — ⭐ OWNER-REQUESTED "Tonight" night planner — widen the bundled catalog beyond Messier.
  A second static, offline file `seestack/data/deepsky_popular.json` (47 curated popular non-Messier
  NGC/IC targets — Double Cluster, Veil, North America/Pelican, Heart/Soul, Rosette, Iris, Cocoon,
  Helix, Blue Snowball, Cat's Eye, Sculptor Galaxy, Centaurus A, Needle, Omega Cen, 47 Tuc, …) is now
  concatenated into `nightplan.load_catalog()` (refactored into `_load_catalog_file` + a de-duping
  loop keyed on id — first file wins), so "Start something new" suggests the well-known objects an OSC
  Seestar owner actually shoots, not just Messier. Same schema/vocabulary as `messier.json`; coordinates
  are sub-degree J2000 (ample for altitude/window ranking); ids are the primary NGC/IC designation and
  don't collide with Messier ids. Additive, offline, upgrade-safe (packaging already globs `data/*.json`;
  API shape unchanged — just more entries). New validation tests pin catalog well-formedness (unique ids,
  valid IAU constellations, known types, no positional overlap with Messier) and that a curated target
  surfaces in a plan. Frontend "Start something new" description reworded to match. (this branch)
- **v0.96.0** — ⭐ OWNER-REQUESTED "Tonight" night planner, slice (b) — horizon / tree-cover mask: an opt-in `horizon_profile` (azimuth→min-clear-altitude points) shapes each target's usable window past low obstructions; `HorizonProfile` interpolates with 360° wrap, Settings gets a point editor, Tonight flags `horizon_active`. Additive, upgrade-safe (empty default = old flat-floor behaviour).
- **v0.95.0** — ⭐ OWNER-REQUESTED "Tonight" night planner, slice (a) — the offline astronomy core.
  New pure engine module `seestack/nightplan.py` (astropy, offline, deterministic): computes tonight's
  dark window (astronomical −18° with nautical/civil fallbacks; `None` for polar day), and per target
  max altitude, transit, usable minutes above a configurable min altitude, Moon separation + phase → a
  0–100 observability score. Combines the user's library targets ("already targeted", annotated with
  subs + integration) with a **bundled 110-object Messier catalog** (`seestack/data/messier.json`,
  static, no network), deduping the catalog copy of any already-shot target. New `GET /api/plan/tonight`
  (observer location from new opt-in `site_lat`/`site_lon`/`site_elevation_m` Settings, else read
  best-effort from a solved frame's `SITELAT`/`SITELONG` header) + a read-only **Tonight** frontend page
  (dark-window/Moon summary, two ranked tables). Additive, read-only, off-by-default config (§9). Tests:
  `tests/test_nightplan.py`, `tests/webapp/test_plan.py`, `test_config_upgrade` site cases, frontend
  `tonight.test.ts` + `Tonight.test.tsx`.
- **v0.94.17** — Friendliness: `post/target_id.py` now maps SIMBAD short OTYPE codes to plain words
  via a new `_OTYPE_NAMES` table + `friendly_object_type()` helper, so `object_type_name` (and the GUI
  identify dialog) reads "Galaxy"/"Globular cluster"/"HII region" instead of a bare "G"/"GlC"/"HII";
  unknown codes fall back to the raw code. Tests `test_friendly_object_type_*`.
- **v0.94.16** — Colour-calibration robustness: `post/color_cal.py::_solve_gaia` now clamps both solved
  per-channel scales to a physical positive range (`0.05`–`20.0`) before returning, so the linear-in-colour
  model's negative `expected_bg` on an extremely-reddened (`BP−RP > 2.44`) field can no longer produce a
  negative `scale_b` that would *invert* the blue channel; a no-op on realistic OSC fields. Regression test
  `test_solve_gaia_clamps_a_negative_channel_scale`.
- **v0.94.15** — Engine/data-integrity fix (found by a fresh adversarial editor-pipeline audit): the
  full-res editor **export** dropped the NaN=coverage restore that the live preview performs. When a
  recipe has **no explicit stretch op** (an empty recipe, or a custom/preset recipe relying on the
  default), `_render_recipe_fullres` applied its fallback `asinh_stretch` — which renders uncovered
  (NaN) pixels as black `0` — and returned it **without** re-marking those pixels NaN, unlike
  `seestack/edit/pipeline.apply_recipe` (which does `out[uncovered] = np.nan`). Because `_write_fits`
  writes the float32 cube verbatim (no `nan_to_num`), the exported **FITS** baked a mosaic-gap /
  reproject-border "no coverage" region to *real black* — so the export diverged from the live preview
  (which shows NaN) and a **re-edit** of that export saw the gap as covered black (`finite_mask` reports
  it covered), mis-treating it in coverage-leveling / border-trim / histogram-levels. The image-only
  PNG/TIFF looked identical (both `nan_to_num` to black), which is why prior image audits missed it.
  Fix mirrors the preview exactly (`finite_mask` → asinh → restore NaN); a recipe *with* a stretch op
  was already correct and stays byte-for-byte unchanged. Regression test
  `test_fullres_export_keeps_nan_coverage_on_a_no_stretch_recipe` (fails before / passes after) plus a
  guard that the explicit-stretch export is unchanged. (`webapp/pipeline.py`, `tests/webapp/test_editor.py`)
- **v0.94.14** — Friendliness polish: the Dashboard readiness banners' dismissal now keys on the
  *specific* problem (readiness *signature*) instead of a global boolean, so dismissing one banner
  no longer suppresses a genuinely different or returning problem (ASTAP→database, incoming→library,
  or a fault that recurs after having worked). New pure `astapReadinessSignature` /
  `folderReadinessSignature` helpers + a shared signature-keyed localStorage dismissal in the
  Dashboard; both banners still self-hide once fixed. Closes the follow-up note filed with v0.94.12.
  Frontend-only, additive (`astapReadiness.ts`, `folderReadiness.ts`, `routes/Dashboard.tsx`).
- **v0.94.13** — Friendliness (first-run): extended the Dashboard readiness banners to a
  missing/unwritable **incoming or library folder** — the other silent first-run blocker after
  the plate-solver. `GET /api/system` gained an additive `folders` field (`_folder_status` reports
  each resolved directory's `exists`/`writable`, cheap + never raises), and the Dashboard shows a
  second dismissible yellow Alert (own localStorage key) covering the four cases (incoming/library ×
  missing/unwritable) with a "Fix in Settings" link, so a beginner learns upfront instead of after a
  Scan finds nothing / a stack fails to write. Pure `folderReadiness(folders)` helper mirrors
  `astapReadiness` (only a *definite* false fires → older backends never nag; incoming checked
  first). Off-nothing, no default/schema change (`webapp/routers/system.py`,
  `frontend/src/components/dashboard/folderReadiness.ts`, `frontend/src/routes/Dashboard.tsx`).
- **v0.94.12** — Friendliness/autonomy: a proactive, dismissible "plate-solving isn't set up"
  banner on the **Dashboard** (the one screen a beginner always lands on first). A pure
  `astapReadiness(astap)` helper classifies `GET /api/system` into ready / ASTAP-missing /
  star-database-missing (only a *definite* `star_db_found === false` flags the DB, so an older
  backend that omits the field never nags), and the Dashboard shows a yellow Alert with a "Fix
  in Settings" link when it isn't ready — caught upfront instead of after scanning frames and
  hitting a mid-workflow wall. One-time localStorage dismissal (guarded); self-clears once
  ASTAP is set up. Frontend-only, additive, no backend/schema/default change
  (`frontend/src/components/dashboard/astapReadiness.ts`, `frontend/src/routes/Dashboard.tsx`
  + tests).
- **v0.94.11** — Friendliness (cosmetic): the ASTAP "no star database" hint on Settings now
  reads "(*.290 or *.1476)" instead of "(*.290)" only — the count already tallied both series
  and the hint's own `d05` example is a `.1476` file, so the old wording was misleading in a
  genuine zero-database state. Text-only; no behaviour or test change (`webapp/routers/system.py`).
- **v0.94.10** — Project-DB robustness: opening an empty/foreign `project.sqlite` (a blank or
  corrupt file sitting at `user_version==0` with no `frames` table) no longer produces a
  structurally-broken DB. `_migrate_schema` ran only `ALTER TABLE frames …` (each swallowing
  `OperationalError`) and never `SCHEMA_SQL`, so with no `frames` table the ALTERs no-op'd,
  `user_version` was stamped current, and the next `add_frame` raised "no such table: frames".
  It now builds the base schema (idempotent `CREATE … IF NOT EXISTS`) when the `frames` table is
  missing, before migrating — a no-op for every genuine older project. Regression test in
  `tests/test_project.py`. Near-unreachable (real projects go through `Project.create`) but a
  reproduced structural break with a cheap, additive fix.
- **v0.94.9** — Ingest robustness: a transient Stage-1 copy failure (a NAS blip during
  `shutil.copy2`) no longer leaves a frame **permanently** uncached. `ingest_files` keyed
  `existing` on the source-path string, so a re-scan skipped the already-registered row and
  never retried the copy — the size-check "resume" branch was dead for this case. It now keys
  `existing` on the frame row and, when a registered frame is still uncached and caching is on,
  retries the copy via a shared `_copy_to_stage1` helper; already-cached frames are never
  re-copied. Not a wrong-image bug (downstream falls back to `source_path`), but the Stage-1
  cache is now populated on the next scan instead of never. Regression tests in `tests/test_ingest.py`.
- **v0.94.8** — Stacking-engine data-integrity fix (current-focus §1): the bilinear debayer
  (`seestack/io/fits_loader.py`) systematically **darkened the outermost 1-px ring of every
  debayered frame** (~50% on edges, ~75% at the four corners). Root cause: the missing-sample
  interpolators average same-channel neighbours, but the colour planes are *sparse* (zero at every
  non-sample site), and when an edge pixel's interpolation reached off the frame the previous
  edge-replicate `_shift` replicated a **zero line** — so a real edge sample got averaged against 0.
  The align path insets 3 px so it never showed there, but the **drizzle stack path feeds the full
  frame** (no inset) straight into the drizzler, so the dark seam reached the *final image*. Fix:
  `_shift` now zero-fills the vacated edge and both `_interp_g`/`_interp_rb` use **normalized
  convolution** — each average divides by the count of genuine in-frame same-channel samples it
  summed, so an off-frame contributor is *excluded* rather than diluting toward 0. Interior sites
  (all neighbours present) are **byte-for-byte unchanged** (verified on random data); only the border
  is corrected. Found by a fresh adversarial audit of the FITS I/O layer + reproduced numerically (a
  constant mosaic now debayers to that exact constant across all four Bayer patterns). Regression
  tests `test_bilinear_debayer_constant_image` (strengthened to assert the full frame, all patterns —
  fails before / passes after) and `test_bilinear_debayer_border_not_darkened`.
- **v0.94.7** — Job-progress robustness (autonomy/friendliness): fixed two real `useJobEvents` SSE bugs
  found by a fresh adversarial audit of the job-events + export-polling surface. **(1)** `es.onerror`
  unconditionally called `es.close()`, defeating EventSource's built-in auto-reconnect — so any
  *transient* mid-job drop (laptop sleep, proxy idle-timeout, a network blip during a multi-minute
  stack) permanently froze the progress panel on its last snapshot: the job could finish while
  disconnected and the UI never resolved (stuck spinner, frame list never refreshed, reload required).
  The backend re-sends current state (plus `done` if already terminal) on *every* reconnect, so the fix
  is to let EventSource reconnect and only close when it has permanently given up (`readyState ===
  CLOSED`). **(2)** The hook reset its snapshot only when `jobId` became falsy, so on a job→job change
  (e.g. starting a second stack without leaving the page) it returned the *previous* job's stale
  (often `"done"`) snapshot — with its "View result" button — until the new stream emitted. Now it
  clears on every id change. Frontend-only, additive. Regression tests for both (fail before / pass
  after), using an extended EventSource mock (readyState + terminal constant). The editor's own
  export/PNG polling loops were audited and found correct (terminal-state handling, no stale-job
  closures, no blob leak, button-gated against progress races).
- **v0.94.6** — Editor/undo correctness (PRIORITY 1): fixed undo *over-reverting* a second use of the
  same control. `useUndoable`'s coalescing keyed only off the previous set's key with **no
  gesture-end signal** — and releasing a slider fires no event — so a second drag of the *same*
  slider merged into the first history entry, making the value between the two gestures unreachable by
  undo (e.g. drag strength 3→5, release, drag 5→7, Ctrl+Z → jumped back to 3, not 5). Root-cause fix:
  coalesce a keyed set only when it lands within `COALESCE_WINDOW_MS` (500 ms) of the previous
  same-key set, so the time gap between two gestures ends one (continuous drag ticks fire ms apart and
  still collapse to one step). Also fixed a related contract violation the audit flagged: `CurvesWidget`
  passed `coalesce=true` for **every** curve mutation, so a *discrete* structural edit (add/remove point,
  keyboard Delete, the "reset" link) merged into the preceding drag — one Ctrl+Z then wiped a whole
  curve-editing session. `CurvesWidget.onChange` now carries a `coalesce` flag (true only for a point
  drag or an arrow-key nudge; false for add/remove/reset), threaded through `OpParamPanel`. Frontend-only,
  additive. Regression tests: `useUndoable` gesture-boundary test (fails before / passes after) +
  `CurvesWidget` discrete-vs-continuous flag assertions. Found by a fresh adversarial editor-logic audit
  (which otherwise came back clean: preview races, split/compare geometry, suggestion wiring, recipe
  immutability, history bounds all verified correct).
- **v0.94.5** — Engine/NaN-coverage: `geometry.rotate` now guards degenerate sizes (`h < 3 or
  w < 3` → return the sliver untouched), the last op in the geometry/detail degenerate-guard family
  that lacked one. Rotation's ~1 px NaN border consumes a sub-3-px axis entirely, so a fully-covered
  2×2/1×5/… came back all-NaN (a NaN=coverage violation; a `<2` px crop upstream can feed exactly a
  2×2). No-op on any real ≥3 px image. Regression tests `test_rotate_on_a_tiny_image_is_a_safe_noop`
  + `test_rotate_full_size_is_unchanged_by_the_tiny_guard`. Found by a fresh adversarial numeric
  editor-ops audit that otherwise came back clean.
- **v0.94.4** — Robustness/friendliness: `POST /api/calibration/masters` now returns 400 (not 500)
  when `Path(source_dir).is_dir()` *raises* (e.g. an embedded null byte → ValueError on platforms
  that raise). Wrapped the check in a `(OSError, ValueError)` guard treating a raise as "not a
  folder", matching every other bad-input path in the handler. Regression test monkeypatches
  `Path.is_dir` to raise so it's platform-independent (the CI container returns False rather than
  raising). Defensive/additive, no-op where `is_dir()` returns False.
- **v0.94.3** — Engine/NaN-coverage: sub-pixel refine now marks the vacated edge NaN on a
  fully-finite window. `align.py::_apply_subpixel_shift` + `_apply_subpixel_shift_windowed` dropped
  the `if nan_mask.any()` guard so the `cval=1.0` NaN-mask shift always runs — the ~1 px strip vacated
  by the correction shift is NaN=uncovered, not the old `cval=0.0` fill (a fractional dimming of the
  ring). A ~0 shift still adds no NaN. Reproduced first, then fixed; regression tests in
  `tests/test_subpixel_align.py` (fail before / pass after). Near-unreachable in practice (real frames
  carry a NaN border; `subpixel_refine` off by default) but a reproduced violation of the NaN=coverage
  hard invariant, byte-for-byte-safe on real frames.
- **v0.94.2** — Editor friendliness: surface the content classification in the "What Auto-process
  did" note. The "try this preset?" chip only shows on an *empty* pipeline, so a user who clicked
  Auto straight away never learned their image was classified; a new pure `presetSuggestionSentence`
  helper now renders one dimmed informational line ("Your image looks like a Star cluster — its
  preset is another good starting point to compare.") inside the Auto note, reusing the
  already-fetched `…/editor/preset-suggestion` payload. Purely informational (no button, never
  implies Auto was wrong), hidden when the classifier declined, and it exposes the same
  already-shipped classification the chip does — no new classifier-accuracy risk. Frontend-only,
  additive; unit tests on the helper + a component test that the line rides alongside the Auto note.
- **v0.94.1** — Robustness: `detail.denoise` now guards a degenerate 1-px-thin image
  (`shape[0] < 2 or shape[1] < 2` → return untouched), mirroring the geometry ops' degenerate-size
  guards. Before the guard the wavelet path emitted all-NaN in the *covered* region (breaking the
  NaN=coverage hard guardrail) and bilateral raised `IndexError`. Regression test
  `test_denoise_on_a_one_px_thin_image_is_a_safe_noop` (wavelet/bilateral/tv × 1×N/N×1; fails
  before / passes after).
- **v0.94.0** — Auto-preset classifier — *safer-first slice* (a preset **suggestion**, not a change
  to Auto's output). New pure `presets.classify_target(rgb)` coarsely classifies a run's own proxy as a
  **star cluster / nebula / galaxy** from cheap geometry-first cues (`star_share` from a grey-opening
  compact-vs-diffuse split; `ext_frac` = frame fraction of extended signal; colour as a soft nebula
  gate so a big *neutral* galaxy like M31 isn't confidently mis-labelled) and returns the matching
  built-in preset — or **declines (`preset_id=None`)** on an ambiguous/blank field so it stays quiet
  unless one archetype is clear. A read-only `POST …/editor/preset-suggestion` endpoint serves it; the
  editor shows a dimmed *"This looks like a Star cluster — try the Star-cluster preset?"* chip in the
  empty-pipeline nudge that applies the preset (sized to the target's data + mosaic-aware, as the
  Presets menu does) in one undoable click. A mis-pick costs a *click*, not a worse image — Auto's
  output is untouched — so it can ship and gather real-world signal before any graduation to seeding
  Auto. Additive; nothing persisted; new suggestion is off-nothing (hidden when unsure).
  `tests/test_target_classify.py` (6 archetype cases incl. the neutral-galaxy guard),
  `tests/webapp/test_editor.py` (endpoint classifies a cluster / declines on a blank field),
  `Editor.test.tsx` (chip shows + applies; hidden when declined) (`claude/happy-franklin-3zj9nk`).
- **v0.93.4** — Extracted the RA 0°/360° unwrap heuristic into one shared dependency-free
  `seestack/coords.py` (`unwrap_ra_deg` + `circular_median_ra_deg`) and pointed all three sites at it
  (`stack/mosaic.py` `_bbox`+`_footprint_outlier_indices`, `stack/reference.py::pick_reference_frame`,
  `io/library.py::_median_radec`), so a fourth site can't reintroduce the wrap bug. Fixed a latent
  float-boundary edge (a seam-centred target folding to exactly `360.0`). `tests/test_coords.py` pins
  the boundary cases; the three existing per-site regression tests pass unchanged (`claude/happy-franklin-jlglfe`).
- **v0.93.3** — Target aggregate RA is now 0°/360°-wrap-safe (`claude/happy-franklin-te45e2`).
  `_median_radec` (`seestack/io/library.py`) set a target's catalog `ra_deg`/`dec_deg` from a plain
  `np.median` of its accepted frames' RAs. For a target imaged near RA=0h whose frames straddle the
  wrap that flipped the position ~180° to the opposite side of the sky (a 50/50 split of
  359.9°/0.1° medians to **180.0°**), so the **sky-map plot** placed the target wrong and
  `find_target_within` target-matching/dedup compared against a bogus centre. Fix unwraps the RAs
  into a continuous range before the median (the same heuristic `compute_mosaic_canvas` /
  `pick_reference_frame` use) and folds back to `[0, 360)`; a no-op when nothing straddles the wrap,
  so a normal target's stored position is unchanged. Sibling of the v0.93.2 reference-frame fix.
  Regression test `test_target_ra_is_wrap_safe_across_ra_zero` (fails before at 180.0° / passes
  after near 0°).
- **v0.93.2** — Reference-frame selection is now RA 0°/360°-wrap-safe
  (`claude/happy-franklin-te45e2`). `pick_reference_frame` (`seestack/stack/reference.py`) took a
  naive `sorted()` median of candidate RAs and plain `(ra − med_ra)` distances, so for a target
  imaged near RA=0h whose frames straddle the wrap (some ~359.9°, some ~0.1°) it scored the
  wrapped frames as ~360° distant — picking a poorly-centred, *blurrier* edge frame as the output
  canvas reference (defeating the sharpest-central-frame rule) and reporting a garbage ~360° span.
  Verified: a single field with its sharpest frame at RA 0.0 and edges at 359.85–0.15 picked the
  0.15° edge frame and reported span ~338° before; now picks the central frame and span < 1°. Fix
  unwraps the candidate RAs into a continuous range (the same heuristic `compute_mosaic_canvas`
  already uses) before the median/distance/span — a no-op when no wrap, so a normal target is
  byte-for-byte unchanged. Affects both single-field (canvas = reference footprint) and mosaic
  (reference seeds `ref_shape` + canvas). Regression test
  `test_picks_central_frame_across_ra_zero_wrap` (fails before / passes after).
- **v0.93.1** — Make the editor's `denoise-suggestion` recipe-aware, matching its
  levels/stretch/curve siblings (`claude/happy-franklin-a5ivvh`). The per-op "From your image"
  denoise button now measures the *linear image entering* the denoise op (any prior linear ops —
  the Auto recipe places `background.final_gradient` + `tone.color_calibrate` ahead of denoise —
  applied, default stretch suppressed so σ stays in the linear domain) instead of the bare proxy,
  so an upstream gradient/colour op is reflected in the suggested strength rather than ignored.
  Backend `GET …/editor/denoise-suggestion` gained optional `recipe`+`uid` (via the shared
  `_recipe_before_uid`); with neither it measures the raw proxy **byte-for-byte as before**, so the
  recipe-independent "Your data" noise chip + bulk-apply (the stack's *inherent* noise) are
  unchanged and old clients keep working. Frontend adds one gated recipe-aware query for the per-op
  button only. Regression tests: backend (empty-recipe ≡ raw; a sharpen ahead of denoise raises the
  measured σ) + frontend (the per-op button reads the recipe-aware strength, called with recipe+uid).
- **v0.93.0** — Show the auto-edit "why" note in the *editor* when opening a run a background
  job auto-edited (`claude/happy-franklin-c8bh0j`). Process-target deep-links straight into the
  editor (v0.85.3) on a recipe the user didn't build; before this it opened with a non-empty
  pipeline and *no* explanation — the trust gap v0.92.0 closed on History Info but not on the
  surface the user actually lands on. New read-only `GET …/editor/auto-note` serves the stored
  `editor_auto_note:` note (`AutoNoteOut`, `None` when no unattended job touched the run); the
  editor fetches it best-effort and shows a dimmed "This picture was auto-edited" note — purely
  explanatory, no new op/control — gated on (a) a note actually being stored (a hand-built recipe
  never shows one) and (b) the pipeline still matching a frozen open-time seed signature, so it
  fades the instant the user hand-edits and never re-appears (even after a Save). While pristine
  the working recipe *is* the auto recipe, so the note also surfaces the same "Tuned to your data:
  sky level … saturation …" values line (`autoValueSentence`) the interactive Auto note shows —
  so a Process-target lander gets an equally-complete explanation as a user who clicked Auto.
  Backend test
  `test_auto_note_endpoint_returns_stored_note_only`; frontend tests for show-then-hide-on-edit
  and no-note-for-a-hand-built-recipe. Additive, off-nothing, API-back-compat (new sibling
  endpoint; the recipe endpoint shape is untouched).
- **v0.92.0** — Carry the Auto "why" note onto the *autonomous* auto-edit paths
  (`claude/happy-franklin-yidmkh`). The interactive editor already explains a clicked Auto
  (what → values → why), but the unattended chains that auto-apply the same recipe in a
  background job (Process-target, Reprocess-everything, watcher auto-stack) produced the
  finished picture *silently*. A new pure `presets.auto_edit_summary(recipe, analysis)` (the
  Python mirror of the frontend `autoSummarySentence` + `autoCauseSentence`) builds a
  plain-language note; `_auto_edit_process_run` stamps it as a per-run project meta
  (`editor_auto_note:{id}`) alongside the recipe it already saves; the run `…/info` endpoint
  returns it as a nullable `auto_edit` field and the History Info panel shows it ("Auto-edited:
  flattened the background, balanced the colour, then sharpened detail · measured a ~0.1 sky,
  4.7 px stars."). All three chains share the helper, so one change covers them all. Additive
  and off-nothing (manual/un-edited runs get no note; absent field on older backends). Tests:
  `auto_edit_summary` pure unit test, `_auto_edit_process_run`→`…/info` integration (note present
  on Process, absent on a manual stack), and a History render test.
- **v0.91.0** — "Why these steps?" — surface the Auto recipe's *causal inputs*
  (`claude/happy-franklin-fifsfa`). Completes the trust-note trilogy (what → chosen values →
  *why*): a new additive `POST …/editor/auto-analysis` sibling endpoint returns the measured
  cues that drove the recipe (`presets.analyze_auto_inputs` — the same `analyze_proxy` sky/noise,
  FWHM→sharpen-radius map, and mosaic trim rect `auto_recipe` consumes), and the editor shows
  `autoCauseSentence` ("Measured from your image: a ~0.10 sky, 4.7 px stars, some background noise,
  12% of ragged mosaic edge to trim.") as a dimmed line in the "What Auto-process did" note. Keeps
  the `…/editor/auto` Recipe response shape untouched; fetched best-effort so an older backend just
  omits the line; every cue nullable and degrades gracefully. Tests: `analyze_auto_inputs` +
  endpoint (single-field & mosaic-trim) + `autoCauseSentence` unit tests.
- **v0.90.0** — "N new subs since your last stack — restack?" nudge on the Target page
  (`claude/happy-franklin-tz1lk5`). Serves the multi-night Seestar workflow: after a target is
  stacked, the owner drops another night's frames in and the master silently no longer reflects
  all their subs. The page now counts accepted + plate-solved frames captured *after* the target's
  most recent *genuine* stack run (an editor-export/combine run — `reusable === false` — doesn't
  reset the clock) and shows a "N new subs since your last stack" callout with a one-click
  **Restack** reusing the existing `processTarget` chain. Frontend-only, additive, read-only
  detection (no backend/schema change); only accepted+solved frames count so rejected/unsolved
  new subs never nag; suppressed while the "Ready to process?" / plate-solve-setup banners take
  precedence; UTC-normalised timestamps so a non-UTC browser can't shift the comparison. Pure
  helper `countNewSubsSinceStack` + 3 unit + 3 component tests in `Target.test.tsx`.
- **v0.89.3** — Chain the auto-edit onto the watcher's background auto-stack
  (`agent/auto-edit-on-autostack`), closing the last gap in the fully-unattended "just works"
  story: the one-click Process (v0.86.0) and Reprocess-everything (v0.86.1) already finished their
  masters into pictures, but the watcher auto-stack — the most autonomous path — stopped at a flat
  linear `master.fits`. A new off-by-default `auto_edit_on_autostack` setting (requires
  `auto_stack`) runs the same best-effort `_auto_edit_process_run` after each successful auto-stack,
  so "drop subs in, walk away, come back to a great image" now returns a finished picture. Off by
  default (§9 — it seeds an editor recipe on every unattended stack), best-effort per target, only
  sets the recipe on the new run, fully reversible in the editor. Settings toggle + summary
  "auto_edited N". Tests: `test_auto_edit_on_autostack_finishes_the_picture` /
  `test_auto_stack_without_auto_edit_leaves_linear_master` + a config-upgrade default-off assertion.
- **v0.89.2** — Graceful degradation for `background.final_gradient` on busy / dense-star
  fields (`agent/final-gradient-degrade`). The `Background2D` fit used to raise and the op
  vanish silently when the object mask covered >80% of every box (a dense cluster — the *cluster*
  preset's own target — or a very-flat frame), so the beginner lost gradient removal on exactly
  those fields with no fallback. `_fit_background_2d` now retries through an `exclude_percentile`
  ladder (80 → 95 → 100) and finally a half-size box before giving up, degrading to a coarse
  gradient subtract instead of none. The strict `exclude_percentile=80` fit stays the first rung,
  so any stack that already succeeded is byte-for-byte unchanged (full-res export parity holds).
  Regression tests: `test_dense_field_degrades_instead_of_giving_up` (fails before / passes
  after — a 6000-star field that raises at strict-80 now flattens with no surfaced error) and
  `test_ladder_first_rung_matches_strict_fit` (a succeeding fit is identical to the old path).
- **v0.89.1** — Two verified low-severity webapp-router robustness fixes (Scout,
  `agent/router-input-robustness`): (1) `GET /api/stats?recent_limit=…` now clamps the
  user-supplied slice size to `[1,100]` like the other int query params (render `size`,
  frame_preview `size`) — a negative value previously sliced `recent[:-n]` and silently
  dropped the oldest stacks, and `0` returned an empty strip. (2) `GET /api/sky` now guards
  `Path(run.preview_path).exists()` when picking the run to place (matching gallery.py /
  stats.py and its own "actually has a preview on disk" comment), so a run whose preview PNG
  was deleted isn't placed on the sphere with a 404-ing tile. Regression tests fail before /
  pass after.
- **v0.89.0** — Editor "Compare a look" follow-up: a "Switch to this look" action on the
  picker adopts the currently-compared look (Auto / a preset) as the working recipe in one
  click — an undoable step, confirm-gated when replacing a non-empty edit — so the user goes
  from compare straight to adopt. Reuses the v0.88.0 resolved-look ops. Frontend-only.
  Editor integration test.
- **v0.88.0** — Editor "Compare a look" split: a picker (Auto + built-in + saved presets)
  next to Split/Compare renders the chosen look on the proxy and feeds it into the same
  split-divider overlay as the "before" image, so a repeat imager can drag to judge their
  current edit against any other look in one frame. Built-in presets sized to the data +
  mosaic-aware (as applying would be); Auto fetched fresh (never persisted); rendered on the
  current edit's framing (`lookCompareOps`) so the divider aligns. Frontend-only, additive.
  New `LookComparePicker` component + `lookCompareOps` helper; unit + Editor integration tests.

- **Companion caution: Drizzle on with too few frames (v0.87.1, image-quality/PRIORITY 4).**
  The symmetric footgun to the v0.87.0 nudge: drizzle only pays off with *lots* of dithered
  frames (the engine recommends 200+) — spreading each sub across a finer output grid needs
  enough dither-phased samples to fill it, so with few frames it's slower for no gain and, at
  higher scales, noisier/gappier, while the ordinary weighted-mean path is "faster, equally
  clean" on Seestar data (`drizzle_path.py`). Since drizzle is off by default this only fires
  when the user turned it on (manually or via "Reuse settings") on a small stack (<100
  accepted+solved frames), with a one-click "Turn off Drizzle". Advisory; mirrors the existing
  sigma-clip-too-few-frames caution. Frontend-only, additive. Tests in `Stack.test.tsx`
  (cautions under the floor; silent on a large set / when drizzle off; one-click off then hides).
- **Proactive Drizzle nudge on the Stack form (v0.87.0, autonomy/image-quality/PRIORITY 2–4).**
  Drizzle recovers the fine detail a Seestar's Bayer sensor + short focal length under-sample,
  but it lives in the advanced knobs and is off by default, so a beginner sitting on thousands
  of auto-dithered subs never reaches for one of the biggest resolution wins available. The
  Stack form now fires an advisory blue nudge (with a one-click "Turn on Drizzle") when the
  accepted+solved frame count is large enough to be worth it (≥200, matching the field help's
  "200+ dithered frames"), drizzle is off, **and** a drizzle-*on* dry-run sizing (`stack-estimate`
  with `drizzle=true`) confirms it fits the memory budget and isn't a giant mosaic canvas — so
  it never nudges toward a run that'd be refused for OOM. Frontend-only (reuses the existing
  `stack-estimate` endpoint), additive, advisory (nothing changes until the user clicks). The
  feasibility query sits with the other hooks above the loading early-return (rules-of-hooks).
  Tests in `frontend/src/routes/Stack.test.tsx` (nudges on a large fitting set; silent on a
  small set / over-budget drizzle / mosaic canvas; one-click enable then hides).
- **Don't claim quality weighting influenced a min/max-reject stack (v0.86.2, image-quality/
  trust/PRIORITY 4).** Found by the Builder's 2026-07-06 stacking-engine audit. The min/max
  order-statistic combine path (`min_max_reject` on a non-drizzle ≥3-frame stack) combines by
  rank and *ignores* per-frame weights, but `_build_output_header_meta` still stamped
  `WGTMODE=quality`/`WGTNDOWN`/… into the FITS header + `stack_runs` row whenever
  `quality_weighted` computed a `wstats` — so a stack run with **both** flags on told the
  History Info card "N frames down-weighted" when the weights had zero effect on the pixels: a
  false trust signal. The fix threads a `weights_applied` flag into the provenance builder
  (`False` only when the min/max path actually ran) and gates the WGT* stamping on it; every
  other path (drizzle, κ-σ pass-2 weighted sum, plain weighted sum, min/max fall-back-to-mean
  at n<3) still records it honestly. Not pixel corruption — the stacked image is correct either
  way; this is a provenance-honesty fix in the same family as the rejection/dark-scaling/
  photometric trust lines. Regression tests: unit `test_weighting_provenance_absent_when_min_max_
  reject_ignored_the_weights` + e2e `test_weighting_provenance_omitted_when_min_max_reject_ignores_
  weights` (both fail before / pass after; the e2e keeps a κ-σ control that still stamps WGT*).

- **Chain the auto-edit onto library-wide "Reprocess everything" (v0.86.1, autonomy/image-
  quality/PRIORITY 2).** Completes the owner-requested "reprocess everything → great images"
  story: a new off-by-default `auto_edit` flag on `POST /api/reprocess-all` (surfaced as an
  "Also auto-edit each result into a finished picture" switch on the Settings Reprocess panel)
  chains the shipped `_auto_edit_process_run` helper onto every restacked run, so a reprocess
  can produce finished *pictures* (saved editor recipe + re-rendered thumbnail) across the
  whole library, not flat linear masters. Only touches each new run's own recipe/preview
  (never an existing run's saved edit), best-effort per run, reversible in the editor; the
  Jobs summary reports "auto-edited N". Regression tests in `tests/webapp/test_reprocess_all.py`
  (unit: chains per-run on / never on by default; e2e: recipe saved on each new run vs empty
  by default) + `Settings.test.tsx`/`Jobs.test.tsx`.
- **Chain a one-click auto-edit onto the "Process target" result (v0.86.0, autonomy/editor/
  PRIORITY 2).** Completes the one-click autonomy story: after `process_target` stacks a
  fresh master it now chains `_auto_edit_process_run`, which builds the run's own Auto recipe
  (the shared `build_auto_recipe_for_run` helper factored out of the `…/editor/auto`
  endpoint), persists it as the run's saved editor recipe (`editor_recipe:{run_id}` meta), and
  re-renders the run's History/Target preview thumbnail through it (`render_run_display_array`
  + `_write_preview_png`, display-space) — so the one-click Process lands the user on a
  finished *picture*, not a flat linear master. Best-effort (a failure only skips the edit;
  the master is already recorded), scoped to the explicit Process action (existing manual/auto
  stacks and old runs untouched), additive (recipe meta + this run's own preview PNG only),
  and fully reversible in the editor (Reset/undo restores linear). Regression test
  `test_process_target_chains_auto_edit`.
- **Deep-link the one-click "Process target" result to its editor in one hop (v0.85.3,
  friendliness/autonomy/PRIORITY 2–3).** `StackResult` now carries the produced `stack_runs`
  row id (`run_id`, captured from `add_stack_run`'s return, `None` on the cancel path), and
  `_stack_target` exposes it in its job summary. The Jobs "View result" button now points at
  `/targets/{safe}/edit/{run_id}` when known — landing the user *on the finished picture* to
  edit — and falls back to the target's History on an older backend that didn't report the id.
  Additive summary field, no schema/API-shape break. Tests: `test_process_target_stacks_end_to_end`
  now asserts `result["stack"]["run_id"]` equals the created run; three Jobs.tsx integration
  tests cover the edit deep-link, the History fallback, and the "Open target" no-stack case.

- **Surface the one-click "Process target" job's outcome + a "View result" link on Jobs
  (v0.85.2, friendliness/PRIORITY 3).** The new `process_target` job (v0.85.0) finished with a
  bare "done" and no action — unlike `reprocess_all`/`editor_export`, the user was left not
  knowing whether a master was produced or where it is. `JobResultActions` now renders a
  plain-language `processTargetSummary` line ("Stacked N frames into a new master", or, when the
  stack was skipped, why — nothing plate-solved yet / cancelled) plus a "View result" button to
  the target's History (or "Open target" when nothing stacked, so the user can fix solving).
  Pure tested helper `processTargetSummary` (5 cases); frontend-only, additive.

- **"Ready to process?" getting-started callout for a fresh target (v0.85.1,
  friendliness/PRIORITY 3).** A dimmed violet callout on the Target page now highlights the
  one-click "Process target" (QC + solve + stack) as the next step whenever the target has
  frames but no stack yet, or accepted frames still awaiting a plate-solve — so a beginner
  who just ingested frames isn't left guessing which toolbar button to press. Suppressed
  while the plate-solve *setup* banner is showing (that must be fixed first) and once every
  accepted frame is solved and a stack exists, so it fades out instead of nagging. Reuses
  the shipped `api.processTarget` mutation; frontend-only, additive, changes no defaults.
  Tests in `Target.test.tsx` (fires on a fresh target / on accepted-but-unsolved frames;
  stays quiet once processed / while the setup banner shows).

- **One-click "Process target" — QC + solve + auto-grade + stack in one job (v0.85.0,
  autonomy/PRIORITY 2).** A prominent "Process target" button on the Target page and a new
  `POST /api/targets/{safe}/process` endpoint enqueue one `process_target` job that runs QC →
  plate-solve → auto-grade (when `auto_grade_frames` is on) → stack, reusing the same tested
  primitives as the auto pipeline (`run_qc_and_solve` → `_auto_grade_target` → `_stack_target`)
  but scoped to one target, on demand, independent of the global `auto_*` toggles. The stack
  uses the target's saved defaults (falling back to the global defaults) and is non-destructive
  (a new `stack_runs` row); the stack step is skipped with a `stack_skipped_reason`
  (`no_solved_frames`/`cancelled`) instead of failing the whole job when there's nothing solved.
  Plain-language Jobs label added. Tests: `test_process_target_stacks_end_to_end` (full chain on
  a solved fixture → real run) and `test_process_target_skips_stack_when_nothing_solved`; a
  frontend Target test drives the button; `jobKindLabel` test extended. Additive, opt-in,
  changes no defaults (upgrade-safe).

- **De-flake the Stack-form photometric-nudge test that reddened main CI + fix the underlying
  nudge flash (v0.84.13, bug/friendliness).** Main CI was red at this run's start (v0.84.10):
  `Stack.test.tsx > does not nudge photometric normalization when it is already on` flaked
  because the form body rendered for one frame after `getStackDefaults` resolved but *before*
  the effect that seeds `values` committed — so `values.photometric_normalize` was still the
  empty-state `undefined` and the transparency nudge briefly flashed even when the default was
  on. Root-caused (not just retried): the loading guard now also waits on an `initialized` flag
  set once `values` is seeded, so no data-driven nudge renders against the empty initial state.
  Hardened the seed effect to settle on the reuse (`?from=`) fetch succeeding *or erroring*
  (the new gate would otherwise hang the loader on a reuse error) — deterministic regression
  test `still renders the form (never hangs the loader) when the reuse fetch errors`
  (fails before / passes after).

- **Clamp `background.final_gradient`'s box to the image size so Auto can't hard-fail on a
  small frame (v0.84.12, robustness).** `_fit_background_2d` clamps `box_size` to tile the
  image (`min(box, max(8, min(h//4, w//4)))`, mirroring `BackgroundOptions.for_image_size`) —
  a box wider than a small frame previously left too few unmasked boxes to survive
  `exclude_percentile`, so `photutils.Background2D` raised and the editor turned it into a hard
  `RuntimeError: edit op failed: Gradient removal`, breaking the whole Auto preview/export
  (Auto includes `final_gradient`). On a real ≥1080 px stack the 256 px box already tiles ≥4×
  so the clamp is a no-op (exports unchanged). Tests:
  `test_small_image_does_not_raise_and_still_flattens`, `test_full_size_box_is_unchanged_by_the_clamp`.

- **Extend the rejection-clipped trust line to the drizzle-reject path (v0.84.11, PRIORITY-4
  image-quality/trust; completes the rejection-trust family started v0.84.9).** The
  "Rejection …%" History line covered κ-σ (v0.84.9) and min/max (v0.84.10) but not the two-pass
  drizzle-reject path. `DrizzleStacker` now tallies `(n_contributed, n_rejected)` memory-free
  as pass 2 zero-weights outlier contributions (`rejection_counts()` — only samples that would
  have contributed, in-bounds & finite), and the stacker's drizzle branch emits a
  `RejectionStats(mode="drizzle-reject", …)` when the reject pass ran. Data-driven fraction
  (contributions outside `mean ± κ·σ`), so it reuses the shipped FITS-card/info-endpoint/History
  wiring and the sigma-clip trust wording (transient-outliers vs too-tight-κ caution), not
  min/max's structural one; plain single-pass drizzle stamps nothing. Tests:
  `test_rejection_counts_tallies_the_clip`, `test_rejection_counts_zero_without_clip`,
  `test_e2e_drizzle_reject_stamps_rejection_provenance`, plus a `rejectionSummaryText`
  drizzle-reject case.

- **Extend the rejection-clipped trust line to the min/max-reject path (PRIORITY-4
  image-quality/trust; completes the v0.84.9 feature for a path real users hit).** The
  v0.84.9 "Rejection clipped ~X% of samples" History line only appeared for the default κ-σ
  path — but the Stack form actively *nudges* users toward min/max reject when a streak is
  detected, so a user who took that nudge saw no rejection line at all and couldn't tell it
  did anything. `MinMaxRejectAccumulator` now exposes `rejection_counts() → (n_contributed,
  n_rejected)`, derived from its final `_count` map at reduce time (no per-frame tracking, no
  extra canvas — matching the exact 2k/2/0-per-pixel drop schedule `result()` applies), and
  the min/max branch stamps the same `REJMODE`/`REJFRAC`/`REJNREJ`/`REJNTOT` cards tagged
  `mode="min-max-reject"`. Because min/max's fraction is *structural* (≈ 2k / frames — small
  at a long stack, large-by-design at a short one), `rejectionSummaryText` is now mode-aware:
  min/max reads "Rejection dropped the ~X% most-extreme samples (min/max reject)" with **no**
  "too-tight κ" over-clipping caution (which would misfire on a 4-frame stack's structural
  50%), while κ-σ keeps its data-driven wording. Engine-only counting + additive FITS cards +
  a display-only frontend branch — no config/schema/API/default change, upgrade-safe. Tests:
  pytest (`rejection_counts` full-trim / k=3 multi-band / empty cases; a real min/max stack
  stamps `REJMODE="min-max-reject"` with a positive `REJFRAC == REJNREJ/REJNTOT`) + Vitest
  (`rejectionSummaryText` words min/max as a by-design drop and never shows the κ caution).
  Drizzle-reject logged as the remaining follow-up. (v0.84.10, this run — Builder)

- **Surface how much the stack's rejection actually clipped — a trust line on History
  (PRIORITY-4 image-quality/trust; current-focus stacking-engine area).** When the default
  κ-σ rejection runs, the user previously had no visibility into whether it quietly removed
  transient outliers (satellites/planes/cosmic rays — good) or over-clipped real signal (a
  too-tight κ — bad); they just got an image and had to trust it. Pass-2 already computes a
  per-pixel `keep` mask, so `run_stack` now sums two scalars over it — `contributed` (covered
  samples seen) and `rejected` (those that failed the κ-σ test) — **memory-free, no extra
  canvas** (respecting the OOM-bounded hot path). A new `RejectionStats` dataclass carries the
  tally into `_build_output_header_meta`, which stamps `REJMODE`/`REJFRAC`/`REJNREJ`/`REJNTOT`
  provenance cards (mirroring the `PHOTNORM`/`DARKSCAL` pattern — present only when a κ-σ pass
  actually ran, even at 0% since "clipped nothing" is itself a clean-data signal). The run
  `…/info` endpoint parses them into a `rejection` summary and the History Info panel renders
  one plain line ("Rejection clipped ~0.4% of samples (transient outliers)", "…(data was
  already clean)" at 0%, or a "check that κ isn't clipping real signal" caution once the
  fraction is unusually high). Engine-only counting + additive FITS cards + one info field +
  one History line — no config/schema/API/default change, upgrade-safe (old runs without the
  cards simply omit the line). Only the default κ-σ path reports it for now (min/max &
  drizzle reject logged as a follow-up idea). Tests: pytest (`_build_output_header_meta`
  stamps/omits the cards incl. the 0%-rejected and no-pass cases; a real 12-frame κ-σ stack
  with a planted streak stamps a positive `REJFRAC` == `REJNREJ`/`REJNTOT` while a plain-mean
  stack stamps nothing; the `…/info` endpoint surfaces/omits the `rejection` summary) + Vitest
  (`rejectionSummaryText` — transient-outlier / clean / <0.1% / too-tight-κ / missing-fraction
  wording). (v0.84.9, this run — Builder)

- **Stacking hot path: per-frame weight/scale lookups honour a frame whose DB id is 0
  (current-focus engine hardening).** The quality-weight and photometric-scale maps are keyed by
  the frame's real `id` (frames with `id is None` are skipped when the maps are built), but the
  two stacking passes read them with `mapping.get(f.id or -1, 1.0)` — which silently drops a
  frame with `id == 0` (`0 or -1 == -1`) to the neutral `1.0` default instead of its real value,
  a store-key/lookup-key mismatch that would corrupt that frame's contribution to the *final
  image*. Unreachable today (SQLite autoincrement ids start at 1) but a genuine latent
  correctness bug in the hot path, in the current-focus stacking-engine area. All four sites
  (`_pass` weight + photometric scale, `_drizzle_pass` weight + photometric scale) now key with
  `f.id if f.id is not None else -1`, keeping store- and lookup-keys identical. Engine-only,
  additive, upgrade-safe — no config/schema/API/default change; a value that was already correct
  for every real id stays correct, and the id-0 case now reads its real value. Test: pytest
  (`tests/test_stack_frame_id_zero.py` — a `_pass` over a frame with `id == 0` applies its real
  weight and photometric scale, not the 1.0 defaults; fails before / passes after). (v0.84.8,
  this run — Builder)

- **Target page: recoverable error state instead of a broken shell when the target 404s
  (PRIORITY-3 friendliness).** Found by a Builder friendliness dogfood: the Target route — the
  app's most-visited screen — handled `isLoading` but had **no** error branch, while all five
  sibling data routes (Dashboard/Library/Gallery/Jobs via `QueryError`, History via an Alert)
  already do. Because every field access is optional-chained, a 404 from `api.getTarget` (a
  deleted target, or a stale bookmark / shared link to a removed one — `deps.open_target_project`
  raises `HTTPException(404)`) didn't crash but rendered a *broken shell*: a blank title, a
  "`/accepted`" badge and an empty frame table, with no explanation and no recovery. It now shows
  the shared `QueryError` ("Couldn't load this page" + Retry), gated on `!target.data` so a
  background-refetch blip never blanks a working page. Frontend-only, additive, upgrade-safe — no
  engine/API/schema/default change, reuses the existing component the siblings use. Tests: Vitest
  (a rejected `getTarget` renders the error + Retry instead of the empty table). (v0.84.7,
  this run — Builder)

- **One-click actions on the three remaining advisory-only Stack-form rejection nudges
  (PRIORITY-2/3 autonomy/friendliness; completes the "every nudge is one-click" pattern).**
  Nearly every Stack-form nudge already carries a one-click action (turn on sigma/min-max/
  quality-weight/photometric, drop outliers, use recommended masters…), but three rejection
  hints were still advisory-only text: the large-stack **sigma-κ tighten** hint (told the user
  to "lower the Sigma kappa in Advanced options"), the **streak-with-no-rejection** warning, and
  the **drizzle+sigma-clip mismatch** hint. Each now has a button that applies exactly the
  suggested change in place, matching the v0.83.2 auto-grade one-click work that closed the last
  *other* un-one-clicked nudge: "Tighten κ to 2.5" (`sigma_kappa` → 2.5, so the hint self-clears
  as κ drops below 3), a context-aware "Turn on sigma clipping" / "Turn on drizzle outlier
  rejection" on the streak warning (picks the field that fits the current path), and "Turn on
  drizzle outlier rejection" on the drizzle mismatch. Frontend-only, additive, upgrade-safe — no
  engine/API/schema/default change; each button flips a setting the user could already toggle by
  hand. Tests: Vitest (each button appears, applies the change, and the nudge disappears once its
  condition is resolved). (v0.84.6, this run — Builder)

- **Plain-language "Build master" empty-folder failure (PRIORITY-3 friendliness; follow-up to
  v0.84.4).** The calibration Build-master job raised a bare `FileNotFoundError: No FITS files
  found in {dir}` when a beginner pointed it at an empty or wrong folder (a real mistake in the
  OSC darks/flats workflow), which surfaced verbatim on the Jobs page. Added a
  `no_fits_in_folder` canonical `error_kind` (classified server-side on the specific
  "no FITS files found" phrase, so internal missing-target/run FileNotFoundErrors aren't
  mis-dressed as a folder problem) and its plain-language translation ("No FITS frames were
  found in that folder." + a point-it-at-your-.fits-calibration-frames next step), extending
  the v0.84.4 error-kind family. Additive/upgrade-safe — no schema/API/default change. Tests:
  pytest (`classify_job_error` maps the folder phrase, leaves an internal `no target` FNF as
  None) + Vitest (`friendlyJobError` translates it via both the raw phrase and the canonical
  kind). (v0.84.5, this run — Builder)

- **Robust server-side `error_kind` on failed jobs — makes the plain-language job-error
  translation reword-proof (PRIORITY-3 friendliness/robustness; follow-up to v0.84.3).** The
  v0.84.3 `friendlyJobError` helper recognised known-fatal failures by string-matching the raw
  `job.error` text — which silently breaks if an engine message is ever reworded. `JobManager`
  now classifies a fatal exception into a **stable canonical** `error_kind` at the catch point
  in `_run` (webapp/jobs.py), where the exception *type* and the full untruncated message are
  both available: `memory_budget` (type-based — `MemoryError`, so it survives any message
  wording), `no_solved_frames`, `no_alignment`, `no_reference_wcs` (message signatures), or
  `None` for anything unrecognised so the raw text is still shown verbatim. The kind is
  persisted (additive nullable `error_kind` column, added in place via `ALTER TABLE` so old
  `jobs.sqlite` history migrates cleanly, never a reset) and exposed on the job dict; the
  frontend `friendlyJobError(raw, kind)` prefers the kind and falls back to the existing string
  matcher when it's absent (older backend) or unknown. Additive/upgrade-safe — new nullable
  column + new response field + a text map moved into `JOB_ERROR_KIND`; no schema-version,
  API-shape, or default change. Tests: pytest (`classify_job_error` matrix incl. type-based
  memory + unrecognised→None; a MemoryError job's kind persists + reloads from disk; an old
  pre-column DB migrates in place and keeps serving its rows) + Vitest (`friendlyJobError`
  prefers a known kind over unrecognisable raw text and falls back when absent/unknown; a
  JobsView job whose raw text is unmatchable still renders the plain message via its
  `error_kind`). (v0.84.4, this run — Builder)

- **Plain-language job failure messages on the Jobs page (PRIORITY-3 friendliness; follow-up to
  v0.84.2).** A failed job previously surfaced its raw `job.error` string verbatim — stored as
  `"{ExceptionType}: {message}"` (webapp/jobs.py), so a beginner's first stack failure read as a
  bare Python exception like `MemoryError: stack output canvas 8000×6000 ×2 drizzle needs ~7.2 GB
  …` or `ValueError: no accepted, plate-solved frames to stack`. A new pure `friendlyJobError`
  helper (mirroring the `jobKindLabel`/`rejectReasonLabel` translation pattern) recognises the
  handful of *known fatal* signatures — the memory-budget refusal (the OOM guard), nothing
  accepted+plate-solved to stack, an empty-alignment failure (non-overlapping / different-field
  frames), and a missing-reference-WCS — and renders a plain sentence in red plus a dimmed
  next-step line, falling back to the raw text **verbatim** for anything unrecognised so no
  information is ever hidden. Frontend-only, additive, upgrade-safe — no engine/API/schema/default
  change, purely a display translation of an existing field. Tests: Vitest unit (each known
  signature → plain message + next step; unrecognised → raw text unchanged) + JobsView (a
  MemoryError job shows the plain message and never the `MemoryError:` prefix; an unknown
  `OSError` falls back to raw). (v0.84.3, this run — Builder)

- **Plain-language job names + a guided empty state on the Jobs page (PRIORITY-3 friendliness).**
  Found by a Builder friendliness dogfood: the Jobs page is the *very first screen a new Seestar
  owner lands on* — clicking the header's "Scan incoming" submits a job and navigates straight
  here — yet it was the one route still showing the engine's raw snake_case job identifiers
  (`pipeline`, `qc_solve`, `stack`, `reprocess_all`, `editor_png`, `editor_export`,
  `editor_batch`, `build_master`, `channel_combine`) verbatim, so a beginner's first-ever action
  produced a row that just said `pipeline`. Every other screen already translates engine jargon
  (History's `combineMethodLabel`, Target's `rejectReasonLabel`); Jobs now matches with a pure,
  tested `jobKindLabel` map ("Importing & processing new frames", "Quality check & plate-solve",
  "Stacking", …) that falls back to the raw kind for any future job type. Its bare "No jobs yet."
  empty state is also brought into the house style (icon + plain-language + a "click 'Scan
  incoming'…" next-step, matching Dashboard/Library/Target/History). Frontend-only, additive,
  upgrade-safe — no engine/API/schema/default change, purely a display translation. Tests: Vitest
  (`jobKindLabel` maps every known kind + falls back for an unknown; the first `pipeline` job a
  beginner sees renders as plain language and never as `pipeline`; the empty state guides to Scan
  incoming; the two existing kind-label assertions updated to the new "Stacking" label). A dogfood
  of the other five routes found them already well-handled (logged under Friendliness). (v0.84.2,
  this run — Builder)

- **Robust server-side plate-solve setup classification — makes the star-database "not set up"
  signal as reliable as the astap-missing one (PRIORITY-3 friendliness/robustness; follow-up
  to v0.84.0).** The v0.84.0 banner detected the setup problem from the stored (120-char
  truncated) `reject_reason` strings — reliable for the deterministic "astap.exe not found"
  installer message, but only best-effort for "no star database", whose ASTAP log line can
  land past the truncation window (leaving the whole target's frames as un-classifiable
  "Plate-solve failed" chips). Now: (1) a new engine helper `classify_solve_setup_error`
  (in `seestack/solve/astap.py`, mirroring the frontend's conservative signatures — a generic
  "could not open / error reading" is *not* a setup problem) classifies a failure at solve
  time, where the *full* log is available; (2) `apply_solve_result_to_db` stores a **stable
  canonical** `reject_reason` (`solve_failed:no star database` / `solve_failed:astap not found`)
  for setup failures so the signature always survives truncation, keeping the raw truncated
  message only for ordinary per-frame failures; (3) the `…/frames/reject-summary` response gains
  a server-computed `solve_setup_problem` `{kind, frames}` field, and the Target banner prefers
  it (falling back to the existing client-side `detectSolveSetupProblem(counts)` on an older
  backend). Additive/upgrade-safe: no schema change (same `reject_reason` column, just canonical
  values for *new* setup failures — old rows keep working via the client fallback), a new
  response field (nothing removed/renamed), and the banner still renders nothing when there's no
  setup problem. Tests: engine/runner (`classify_solve_setup_error` matrix; a "no star database"
  message buried past char 120 is canonicalised so it's reliably classifiable — fails before /
  passes after; a per-frame failure keeps its raw message) + webapp (reject-summary reports the
  `solve_setup_problem` for a database-missing target, `None` for ordinary rejects) + Vitest
  (the banner fires from the server field even when `counts` lacks the raw phrase). (v0.84.1,
  this run — Builder)

- **Actionable "plate-solving isn't set up" banner on the Target page (PRIORITY-3 friendliness +
  "just works").** Found by a Builder friendliness pass: when ASTAP (the plate-solver) or its
  star database isn't available, *every* frame's solve fails with the same fatal message, so a
  fresh/misconfigured install piles up a whole target's frames as "Plate-solve failed" chips with
  no hint that the fix is a one-time setup step (install/point at ASTAP, download a star database)
  rather than dropping frames one by one — a total blocker at first use with zero guidance. The
  Target page now shows one orange Alert when the target's rejected-reason tally carries a solve
  *setup* signature, with the right plain-language guidance for the ASTAP-missing vs
  star-database-missing case and one-click "Re-run QC + Solve" + "Open Settings" actions. Detection
  is a pure, tested helper (`detectSolveSetupProblem`) that mirrors the engine's own
  `_is_fatal_solve_error` signatures + the "astap.exe not found" installer hint, and is
  deliberately conservative — a generic "could not open / error reading" (which can be one corrupt
  frame) does **not** trigger it, so it never nags about setup when the real issue is a single bad
  file. Frontend-only, additive, upgrade-safe — reads the existing `reject-summary` `counts`, no
  schema/API/default change; renders nothing (today's behaviour) when there's no setup problem.
  Tests: Vitest unit (setup vs per-frame vs corrupt-file vs empty; case-insensitive; ASTAP-missing
  preferred over database) + Target route (banner + its actions render for a whole-target
  ASTAP-missing failure; absent for an ordinary "no solution" per-frame failure). A robustness
  follow-up (server-side classification so the star-database case is as reliable as ASTAP-missing)
  is logged under Friendliness. (v0.84.0, this run — Builder)

- **QA — stacking-engine adversarial audit + one-click Auto dogfood (top current-focus areas),
  both clean; no code shipped.** Per the 2026-07 focus, ran a fresh adversarial correctness audit
  of the stacking engine (`stacker.py` rejection/pass-2 + photometric-scale application,
  `accumulator.py` WeightedSum/Welford/MinMaxReject NaN+order-statistics, `align.py` sub-pixel
  shift/valid-mask, `drizzle_path.py` two-pass clip, `photometric.py` scale direction,
  `calibrate/apply.py`+`build.py`, plus the always-on `coverage_leveling.py`). **No reachable
  wrong-result bug found** — NaN=coverage preservation, k-min/k-max disjointness (`count≥2k+1`),
  transparency-scale direction (`ref/score`, hazy→scale>1), Bessel corrections (Welford `M2/(n−1)`,
  drizzle `neff/(neff−1)` gated ≥3), dark exposure-scaling pedestal math, and neutral calibration
  fallbacks all verified correct. Near-misses explicitly ruled out (all non-bugs): pass-2 `tol=0`
  on a bit-exact-constant pixel (Welford `delta=0` keeps it safe), `level_by_coverage` running on a
  single-field stack (offset ≈0 for an already-bg-subtracted frame; object-masked), the stale
  `win_valid` after a sub-pixel shift (never read — coverage derives from `isfinite`). Separately
  **dogfooded the one-click Auto recipe** across five realistic proxies (typical / very-dim /
  bright / heavy-green / noisy): no op errors, **zero NaN leak** in the covered region, sensible
  display medians (~0.19–0.25), green cast removed (post-SCNR green below max(R,B) in every case),
  and minimal clipping — the out-of-the-box result is solid. Recorded so future runs/Scout don't
  re-tread these two well-hardened areas. (this run — Builder)

- **Fix (PRIORITY-1 editor): a cropped/geometry-edited live preview letterboxed with spurious
  black bars, and the Split/Compare divider mis-aligned, whenever a reshaping geometry op was
  in the recipe.** Found by a Builder editor-UI dogfood: the histogram endpoint reported
  `proxy_width`/`proxy_height` from the *raw* proxy (measured before `apply_recipe`), but the
  preview PNG is the *post-recipe* image — so after any enabled `geometry.crop`/rotate/resize
  (the headline case: one-click mosaic **Trim border → Apply**) the editor sized its image box
  to the un-cropped aspect and `objectFit:contain` pillarboxed the cropped preview inside it —
  unexplained black bars that read as "the crop broke something" — while the Split/Compare
  "Original" (a full un-cropped render) and the divider no longer lined up with the edited
  frame. Export was unaffected (it never reads these dims). Fix, additive/upgrade-safe: (a) the
  histogram endpoint now also returns `render_width`/`render_height` from the rendered `out`
  shape (equal to the raw proxy dims when there's no reshaping op; the raw `proxy_*` stay put
  for the "downscaled ×N" caption), and the editor sizes its box from those (fallback to
  `proxy_*` on an older backend); (b) the Split/Compare "Original"/base render and the star-mask
  overlay are now rendered through the recipe's enabled geometry ops (reusing `apply_geometry_to_map`,
  the same path the coverage overlay already uses), so every overlay shares the edit's framing
  and the divider aligns. No schema/API-shape/default change — new response fields + a
  frontend box-sizing/overlay change. Tests: webapp (histogram reports rendered dims matching
  the cropped preview PNG and < the raw proxy dims; the star-mask width tracks a recipe crop) +
  Vitest (the box aspect follows `render_*`, falls back to `proxy_*` when absent, and the split
  "Original" fetch carries only the geometry ops). (v0.83.3, this run — Builder)

- **Engine hardening (PRIORITY-1 stacking-engine QA): correct a stale `WelfordAccumulator`
  docstring that claimed population variance `M2/n`.** A Builder adversarial audit of the
  combine maths found the class docstring stated it uses population variance "not the sample
  variance", directly contradicting `variance()`, which deliberately returns the *unbiased
  sample* variance `M2/(n-1)` (NaN for `n<2`, so the sigma-clip pass keeps single-coverage
  mosaic-edge pixels). The lie briefly misled the auditor itself; the docstring now matches
  the code. Docs-only, zero behaviour change (no version-visible effect; rides the v0.83.3
  bump). (this run — Builder)

- **One-click "Drop N outlier frames" + safety-cap notice on the Stack-form auto-grade hint
  (PRIORITY-2/3 autonomy + friendliness).** The auto-grade hint was the last Stack-form
  advisory nudge with no one-click action — it only offered a "Review Auto-grade" link that
  sent the user to the Target page. It now carries a **"Drop N outlier frames"** button (beside
  the retained link) that calls the already-shipped `api.autoGradeApply(safe)`; on success the
  yellow hint is replaced by a green **"Dropped N — Undo"** confirmation whose Undo re-accepts
  the returned `changed_ids` (auto-grade never sets `user_override`, so the revert is clean).
  Because this mutates target-wide accept-state, the frame/auto-grade-preview/stack-estimate
  queries are invalidated on both apply and undo. Companion change: when the grader hits its 25%
  `MAX_REJECT_FRACTION` safety cap (`GradeReport.capped`), the hint now appends a plain-language
  "this looks like a rough session — only the worst are recommended; review before stacking"
  sentence, so a user who skips the Target page still learns many more frames were suppressed.
  Frontend-only, additive, advisory — no engine/API/schema change; the endpoint + client method
  already existed. Tests: Vitest (the Drop button applies + swaps to the green Undo confirmation
  and Undo re-accepts the ids; the capped notice appears when `capped` is true). (v0.83.2, this
  run — Builder)

- **Surface the deep-rescan count on the finished reprocess-all job summary (follow-up to
  v0.83.0; PRIORITY-3 friendliness).** The Jobs page's plain-language reprocess outcome now
  reads "Restacked N/M targets — re-ran QC/solve/grade on K …" when the deep_rescan option
  was used (the new `rescanned` summary field), closing the feedback loop so the user can
  confirm the (slower) rescan actually ran. Omitted entirely for a plain restack
  (`rescanned` 0). Pure `reprocessSummary` helper + Vitest (rescan clause present/omitted and
  ordered before the skip/failure notes). Frontend-only, additive. (v0.83.1, this run — Builder)

- **Reprocess-everything slice (b): optional deep full rescan (re-QC / re-solve / re-grade
  before restacking) — completes the ⭐ owner-requested "reprocess everything" feature
  (PRIORITY-2 autonomy).** The slice-(a) reprocess restacks each target with the current
  engine, but reused the target's existing QC/solve/grade decisions — so improvements to
  *those* steps (not just the stacker) didn't reach the reprocessed image. A new
  off-by-default `deep_rescan` flag on `POST /api/reprocess-all` re-runs QC + plate-solve
  (`run_qc_and_solve` with `only_new_qc=False`, so every frame is re-derived with the new
  engine) and, when the user has grading enabled, re-applies auto-grade over each target's
  existing frames *before* that target's restack. A new `_refresh_target` helper does the
  refresh best-effort per target (a flaky re-QC is logged and swallowed, never sinking the
  restack) and honours manual accept/reject decisions (`apply_qc_result_to_db` respects
  `user_override`, so re-QC can't clobber a hand-made choice); solving is best-effort (no
  ASTAP → nothing solved). It runs only for targets that will actually be restacked, so a
  `stale_only` skip skips the (expensive) rescan too, and the batch stays cancellable between
  targets. The job summary gains a `rescanned` count. Settings → Reprocess panel adds an
  off-by-default "Also re-run QC, plate-solving & grading first" switch (with a confirm-dialog
  note and manual-choices reassurance) wired through `api.reprocessAll(staleOnly, deepRescan)`.
  Additive/upgrade-safe: a new opt-in flag on an existing endpoint + one new job-summary field
  + one UI switch — no schema/default/API-shape change; an omitted flag is exactly today's
  plain restack. Tests: webapp (deep_rescan re-runs QC/solve with `only_new_qc=False` before
  each stack + reports `rescanned`; default off never rescans; a failing refresh is isolated
  and the restack still happens; a `stale_only`-skipped target isn't rescanned) + Vitest (the
  toggle passes `deep_rescan=true`; the two existing scope tests updated to the two-arg call).
  (v0.83.0, this run — Builder)

- **Proactively nudge dark exposure-scaling from the calibration store (PRIORITY-2 autonomy;
  follow-up to the v0.82.0 `scale_dark_to_light` feature).** The one-click "Scale this dark to
  your subs' exposure" only appeared once the user had *manually* selected a master bias — so a
  beginner with a mismatched dark and an unused bias in the library still faced a two-step
  discovery (find and pick the bias, then flip the option). Now, when the dark's exposure is
  mismatched, no bias is selected, *and* the library holds a master bias, the Stack form's
  dark-mismatch Alert offers a single "Select your master bias and scale the dark" button that
  selects the bias (the recommended one when it's among the available options, else the first)
  and enables scaling in one click — replacing the yellow warning with the teal "scaling is on"
  confirmation. Falls back to the existing prose ("Add a master bias to scale it…") when there's
  genuinely no bias to select. Frontend-only, additive, advisory — no engine/API/schema change,
  nothing happens until the user clicks. Tests: Vitest (the button appears with an available bias
  and selecting it turns on scaling + swaps to the teal note; absent when the library has no
  bias). (v0.82.2, this run — Builder)

- **Surface dark exposure-scaling provenance on the run Info / History card (PRIORITY-4
  image-quality/trust; companion to the v0.82.0 `scale_dark_to_light` feature, mirroring
  the v0.81.1 photometric-normalization provenance).** The off-by-default dark
  exposure-scaling shipped in v0.82.0, but a stack that used it said nothing — the user
  couldn't tell from History whether the feature actually rescaled the dark. Now, when a
  dark was genuinely scaled to the subs' exposure — the option was on, a master bias was
  present to hold the pedestal fixed, a dark was set, and the dark's exposure differs from
  the subs' — `_build_output_header_meta` stamps three provenance cards (`DARKSCAL`
  "exposure" mode + `DARKDEXP`/`DARKLEXP`, the dark and sub exposures) alongside the
  existing `PHOTNORM`/`WGT*`/`CALSTAT` keys. The scale is applied per-frame, so the stamp
  records the run-level option + the (median) exposures, not a per-pixel value; it's
  omitted (exactly like `PHOTNORM`) whenever nothing was actually scaled — a matched
  exposure, no bias, or an unknown exposure all leave the dark unscaled. The run `…/info`
  endpoint parses them into a `dark_scaling` `{mode, dark_exposure, light_exposure}`
  summary, and the History Info panel renders one dimmed line ("Dark scaled to sub
  exposure · 30s → 10s") via a pure `darkScalingSummaryText` helper. Additive/upgrade-safe:
  new nullable FITS cards + a new response field + one advisory UI line — no schema/API-shape/
  default change; an old run with no `DARKSCAL` card simply omits the line. Tests: engine
  unit (stamped when scaled to a 10s sub from a 30s dark; absent when the option is off, the
  exposures match, or the bias/exposure is missing) + webapp (the info endpoint parses the
  cards into `dark_scaling` and reports `null` for a plain stack) + Vitest
  (`darkScalingSummaryText` null/exposures/fractional/mode-only). (v0.82.1, this run — Builder)

- **Dark exposure-scaling — reuse a dark library shot at one exposure to calibrate subs
  at another (PRIORITY-4 image-quality/correctness; slice (b) of the calibration item).**
  A master dark records thermal (dark-current) signal at a *specific* exposure, so a dark
  shot at a different exposure than the lights either under- or over-subtracts — today
  AstroStack only *warns* about the mismatch, leaving the user to re-shoot darks per
  exposure. A new off-by-default `scale_dark_to_light` StackOptions flag scales the dark's
  dark current to the light's integration time while holding the exposure-independent bias
  pedestal fixed: `dark = bias + (dark − bias)·(t_light / t_dark)`. It needs a master bias
  (to separate pedestal from dark current) and known exposures; without either — or when
  the exposures match — it falls back to the unscaled dark, so nothing changes for the
  common matched-dark case. The light's own exposure is threaded from `load_seestar_raw`
  into `CalibrationMasters.apply_raw(raw, light_exposure_s=…)` at both hot-path call sites
  (`align.py`, the drizzle prepare worker); direct callers that omit it get the unscaled
  dark (backward-compatible). The Stack form's existing dark-exposure-mismatch warning now
  carries a one-click **"Scale this dark to your subs' exposure"** (shown only when a master
  bias is also selected) that flips the flag, replacing the yellow warning with a teal
  "scaling is on" confirmation; the "bias ignored because a dark is present" note is
  correctly suppressed while scaling is on (the bias *is* used then). Additive/upgrade-safe:
  a new off-by-default option field with a descriptor (drift test satisfied) + an optional
  `apply_raw` kwarg — no schema/API/default/on-disk change; an existing install's stacks are
  identical until opted in. Tests: engine unit (scales the dark current to a 10 s sub from a
  30 s dark / matched-exposure and off-by-default and missing-bias and missing-exposure all
  neutral) + end-to-end through `align_one` (the synth sub's 10 s exposure reaches
  `apply_raw` and scales the 30 s dark, the aligned output higher by the pedestal
  difference) + Vitest (the warning's one-click enables scaling and swaps to the teal note).
  (v0.82.0, this run — Builder)

- **Make the remaining advisory Stack-form nudges one-click actionable (PRIORITY-2/3
  autonomy + friendliness).** Three Stack-form advisory hints told the user to change a
  setting but made them hunt for it, while their siblings (photometric-normalization,
  min/max-reject) already offered a one-click button — an inconsistency a beginner feels
  as friction. Now: the **quality-weighting** nudge (fires on a wide FWHM/star-count
  spread) and the **hazy-transparency** hint (run median well below the target's clear-sky
  baseline) each carry a one-click **"Turn on quality weighting"** button, and the
  **sigma-clip-low-frame** caution (sigma clip on with <5 accepted+solved frames) carries a
  one-click **"Turn off sigma clipping"** — each doing exactly the safe action the hint's
  own text recommends. The transparency-hint button is guarded on `!quality_weighted` (so it
  vanishes once weighting is on while the "you were shot through haze" advisory stays), and
  the quality-weighting nudge already only renders while weighting is off. Prose reworded so
  it reads naturally beside a button ("Turn on Quality weighting in the options above" →
  the button carries the action). Frontend-only, additive, advisory — no engine/API/schema
  change, nothing happens until the user clicks. Tests: Vitest (each button turns its option
  on and clears/updates the nudge; the transparency button leaves the advisory text in
  place). (v0.81.10, this run — Builder)

- **Fix: mosaic canvas iterative-shrink dropped a good central frame instead of the real
  outlier when the group straddled RA=0° (stacking-engine data-integrity).** The primary
  plate-solve-outlier pass computes each frame's centre RA wrap-safely with
  `_circ_mean_ra_deg`, but the *iterative canvas-shrink fallback* — reached only when the
  union footprint exceeds the pixel cap (`MAX_CANVAS_PX`, 16000 px) — picked the frame to
  drop using a plain `np.median` of its corner RAs. For a frame whose footprint straddles
  the 0°/360° wrap (corners at, say, 359.6° and 0.4°) that median is ~180°, flinging the
  frame's apparent centre to the opposite side of the sky — so a perfectly good *central*
  frame looked like the worst outlier and was dropped from the mosaic (silently losing a
  real panel), while the actual far frame survived. Fix: the shrink loop now uses the same
  wrap-safe `_circ_mean_ra_deg` for each frame's centre RA (Dec doesn't wrap, so its median
  is unchanged), mirroring the primary pass. Reachable only for a genuinely huge (>16000 px)
  mosaic *and* an RA≈0 straddle, but a real data-integrity path in the top-focus stacking
  engine when it triggers. Engine-only, additive/upgrade-safe (no schema/API/default change;
  a well-solved non-straddling stack is unaffected — the loop is a rarely-hit backstop).
  Regression test `test_canvas_shrink_loop_drops_the_real_outlier_near_ra_zero`: four frames
  around RA≈0 (below the proactive pass's frame threshold, so the size-cap loop does the
  dropping) with a forced small `max_canvas_px` — before the fix the central straddler is
  dropped (n_footprints=2), after it the real far frame is dropped and the central one kept
  (n_footprints=3). (v0.81.9, this run — Builder)

- **Fix: a manual re-stack (or re-export/re-combine) under an existing basename silently
  made the *previous* run's history row serve the new image (data-integrity/trust).** A
  plain re-stack from the Stack form defaults to `output_name="master"` (the frontend sends
  no name), so `write_stack_outputs` archived the existing `master.*` to a timestamped file
  that **no** `stack_runs` row referenced, then wrote the new pixels back at `master.fits` —
  and the *old* run's row (still pointing at `master.fits`) began serving the new image while
  the true old image was orphaned. History showed two runs but both resolved to the newest
  image, defeating before/after comparison (the same mechanic the v0.81.4 reprocess fix
  addressed, but user-initiated). Fix takes the note's preferred "newest stays `master`,
  older is renamed+rerowed" direction: `_archive_existing_outputs` now moves an existing set
  aside under a single consistent `{base}_{stamp}` basename (so the `_coverage`/`_preview`
  siblings stay siblings of the archived FITS — `coverage_path_for` resolves them from the
  FITS basename) and returns a `{original→archived}` map; `write_stack_outputs` surfaces it
  as a new additive `"archived"` result key; and the stacker (plus the editor-export and
  channel-combine paths) call a new `Project.repoint_stack_runs` to point the previous run's
  `fits/tiff/preview` columns at the archived files *before* recording the new run. Net:
  `master.*` is always the newest image, the previous run keeps resolving to its own
  (byte-for-byte preserved) image + coverage, and nothing is orphaned. Reprocess-all is
  unaffected (it already uses fresh version-tagged basenames, so it archives nothing).
  Additive/upgrade-safe: no schema/API/default change — a new nullable-ish result key and a
  history repoint (no run added/deleted/content-changed); direct engine callers that ignore
  the new key are unaffected. Tests: engine unit (archive to one basename + coverage sibling
  resolvable; repoint moves the old row to distinct existing files; no-op on empty map) +
  end-to-end (two real `run_stack`s under `master` — old row repointed to a distinct file
  holding its original bytes, new run keeps `master.fits`; fails before / passes after).
  (v0.81.8, this run — Builder)

- **Fix: watcher could permanently drop a batch from auto-ingest when a file stabilised
  during a running pipeline (PRIORITY-2 autonomy / data-completeness).** Frames dropped
  into `incoming/` while a prior pipeline job was mid-run were silently never imported: the
  `StabilityTracker` reports each file "newly stable" exactly once, and `_on_batch_ready`
  skipped enqueuing (with no re-trigger flag) when a pipeline was already `queued`/`running`
  — so the file's one-and-only trigger was lost and it sat unprocessed in `incoming/` until
  some later new file happened to kick a fresh pipeline (or the user manually clicked Scan).
  Worst case (the last batch of a session, nothing arriving after) it was never picked up at
  all — undermining the core "drop files in and it just processes" promise. Fix:
  `_on_batch_ready` now **returns** whether it enqueued a pipeline (`True`) or declined
  because one was active (`False`); on a decline the watcher marks the batch **pending** and
  re-offers it on every subsequent poll until it's accepted, so the deferred batch is picked
  up on the first poll after the running pipeline finishes (bounded by the poll interval)
  rather than being dropped forever. Self-contained to the watcher's poll loop — no schema,
  API, config, or default change (additive/upgrade-safe; a callback returning `None`, as the
  legacy signature did, is still treated as "consumed"). Regression test
  (`test_batch_pending_when_pipeline_busy_is_reoffered`) simulates a busy-then-free pipeline
  and asserts the pending batch is re-offered until accepted then not again — fails before,
  passes after. (v0.81.7, this run — Builder)

- **Fix four more flaky Editor "From your data" tests that reddened main's CI (test-only,
  same remount race #109 fixed).** The v0.81.5 merge's frontend CI job failed on
  `Editor.test.tsx > 'sets both black+white points via Auto stretch'` (`Set Strength from
  your data` not disabled). Root cause is the same toolbar-remount race #109 traced: the
  per-op suggestion / default-recipe queries settle and remount the toolbar right after the
  buttons first appear, so a `fireEvent.click` fired *before* the remount lands on a detached
  node (its React `onClick` never runs) and the button never reaches its applied/disabled
  state — or a button reference captured before the remount is stale by assertion time. Fix
  is **test-only** and does not weaken any assertion: for the four sibling "From your data" /
  "Auto stretch/levels" tests, re-find the button and (where a click is needed) re-click
  *inside* the existing `waitFor` so the idempotent click retries across the remount flicker,
  matching the durable pattern #109 introduced for the "Auto curve" test. Verified the
  Editor suite passes 44/44 across 4 consecutive local runs. No source/behaviour change.
  (v0.81.6, this run — Builder)

- **Proactive "N targets are out of date" nudge — reprocessing after an upgrade is no
  longer purely reactive (PRIORITY-2 autonomy / PRIORITY-3 friendliness).** The
  "Reprocess everything" feature (owner-requested) + per-run `engine_version` provenance
  (v0.76) + the `stale_only` filter (v0.77) shipped, but nothing *told* the user their
  images were stale — after an in-place upgrade they silently kept whatever engine build
  made them unless the user remembered to visit Settings and reprocess. Now a read-only
  `GET /api/reprocess-status` reports `{current_version, outdated, up_to_date,
  total_targets}` (a target is *outdated* when its newest **genuine** stack — editor/combine
  runs skipped, via a shared `_newest_genuine_stack_run` helper — was made by a different
  version than the running build; a never-stacked target is neither, so the count is exactly
  the images a reprocess would change). A small grape count badge on the Settings nav link
  (`OutdatedTargetsBadge`) surfaces it app-wide, and the Settings → Reprocess panel shows a
  plain-language advisory Alert ("N targets were last stacked with an older AstroStack
  version… reprocess — it's non-destructive") built from a pure, unit-tested
  `reprocessNudgeText` helper. Advisory only — no reprocess happens until the user clicks the
  existing (default-on "outdated only") button. Additive/upgrade-safe: new read-only endpoint
  + advisory UI, no schema/default/API-shape change; the badge/nudge simply don't show when
  nothing is outdated. Tests: webapp (status counts outdated vs up-to-date vs never-stacked;
  legacy `engine_version=None` counts as outdated; newest-run-wins; editor/combine runs
  ignored; endpoint end-to-end) + Vitest (`reprocessNudgeText` null/singular/plural; the
  Alert renders when outdated and is absent when up to date). (v0.81.5, this run — Builder)

- **Fix: "Reprocess everything" silently overwrote each target's existing stack output
  (data-integrity bug on the owner-requested feature; found by a Builder webapp audit).**
  `submit_reprocess_all` reused each target's last run's `options_json`, which carries the
  original run's `output_name="master"`. So the restack wrote to the *same* basename:
  `write_stack_outputs`→`_archive_if_exists` renamed the existing `master.fits`/`.tif`/
  `_preview.png` to timestamped files that **no DB row references**, and wrote the new
  pixels back at the original paths — so the *old* run's `stack_runs` row (still pointing
  at `master.fits`) silently began serving the *new* image, and the original became an
  orphan the UI never shows. This directly contradicted the feature's promise ("nothing is
  deleted or overwritten — compare them in History") and defeated its safety guarantee (a
  worse restack *could* lose a good result). Fix: reprocess now writes each run to a fresh,
  version-tagged basename (`master_v<version>`, `_2`/`_3` suffixed if that already exists),
  via a new `output_name` override threaded into `_stack_target` — so the reprocessed image
  lands *alongside* the existing one, both reachable as separate runs. Nothing reads
  `master.fits` by name (all reads go through the run row's `fits_path`), so the rename is
  safe. Additive/upgrade-safe: no schema/API/default change; only the on-disk basename of
  *new* reprocess outputs changes. Tests: pure (`_reprocess_output_basename` version-tag +
  collision-suffix) + end-to-end regression (a real first stack's `master.fits` is
  byte-for-byte unchanged after reprocess, and a second version-tagged run appears with its
  own FITS — fails before the fix, passes after). (v0.81.4, this run — Builder)

- **Stack form nudges to enable Photometric normalization when transparency varies a lot
  (PRIORITY-2/3 autonomy + friendliness, companion to v0.81.0).** v0.81.0 shipped the
  off-by-default `photometric_normalize` option that gain-matches hazy vs clear subs
  before combine, but a beginner won't know to reach for it. The Stack form now fires a
  sibling advisory nudge (alongside the existing hazy-night and quality-weighting hints)
  when the transparency spread across the frames-to-be-stacked is wide — p90/p10 ≳ 1.5×,
  computed from the `transparency_score` values already fetched — *and* the option is off:
  it explains in plain language that the frames vary a lot in brightness (haze/airmass
  across nights) and offers a one-click **"Turn on photometric normalization"** button.
  Requires ≥5 measured frames so a couple of subs can't trigger it (the engine itself
  needs ≥3 to normalize at all). Distinct from the quality-weighting nudge (that
  down-weights the worst subs' *contribution*; this gain-matches their *values* — they
  compose). Frontend-only, additive, advisory — no engine/API/schema change and nothing
  changes until the user opts in. Tests: Vitest (fires on a wide 2000…9000 spread and the
  button turns the option on + clears the nudge; silent on a tight spread; silent when
  already on). (v0.81.3, this run — Builder)

- **Fix flaky Editor "Auto curve" test that was intermittently reddening main's CI.**
  The frontend CI job failed on several recent `main` pushes (including a docs-only
  commit, `#108`), always in `Editor.test.tsx > sets a gentle starting curve via the
  header 'Auto curve'`. Root cause (traced with an instrumented repro): the test
  captured the "Auto curve" `<button>` reference across an `await`, but the toolbar
  subtree **remounts** while the per-op suggestion / `default-recipe` (v0.79.0) queries
  settle — so the captured node is detached (`isConnected === false`) by click time and
  its React `onClick` never fires (a native listener still fires, which is the tell).
  The added async queries shifted render timing so the remount now reliably lands right
  after the button first appears. Fix is **test-only** and does not weaken the assertion:
  re-find and click the button *inside* the existing `waitFor`, polling until the
  suggested points reach a preview fetch (the durable effect) — the click is idempotent
  (sets the same points), so retrying across the remount flicker is safe. Verified the
  test now passes fast (≈1.4 s vs the prior 20 s `asyncUtilTimeout`) and stably (5/5
  reruns); full frontend suite green (454 passed). No source/behaviour change. (v0.81.2,
  this run — Builder)

- **Surface photometric-normalization provenance on the run Info / History card
  (PRIORITY-4 trust, companion to v0.81.0).** The stack run's `…/info` endpoint now
  parses the `PHOTNORM`/`PHOTN*` FITS keys into a friendly `photometric` summary
  (mirroring the existing quality-`weighting` summary), and the History provenance
  card renders a single line — "Photometrically normalized · N frames gain-matched ·
  scales lo–hi (median m)" — so a user who turned normalization on can see it happened
  and how many subs were actually scaled (and trust the off-by-default feature did
  something). Present only on normalized stacks; absent otherwise. New pure
  `photometricSummaryText` helper. Additive/upgrade-safe (new nullable response field +
  advisory UI line, no schema/behaviour change). Tests: webapp (a stamped run surfaces
  the parsed summary; a plain run reports `photometric: null`) + Vitest
  (`photometricSummaryText`: null when un-normalized / full range / singular-frame +
  missing-range tolerant). (v0.81.1, this run — Builder)

- **Photometric (multiplicative) frame normalization before combine — gain-match the
  signal so haze/airmass doesn't weaken rejection or dim the result (PRIORITY-4
  image-quality/correctness).** Frames are additively sky-zeroed per frame, but nothing
  gain-matched their *signal*: haze, airmass and thin cloud scale a sub's recorded star/
  nebula flux by tens of percent across a multi-night session, which (a) inflates the
  per-pixel spread κ-σ / min-max rejection clips against — so real outliers on bright
  structure survive — and (b) lets hazy nights quietly dim the combined image. A new
  `photometric_normalize` StackOptions flag (**off by default**) estimates a per-frame
  multiplicative scale from the frame's own `transparency_score` (the median flux of its
  brightest stars, already measured by QC) relative to the **median** transparency of the
  stacked frames, and the stacker multiplies it into each frame's pixels *before*
  accumulation — so it flows identically through every path (single-pass mean, κ-σ pass
  1+2, min/max reject, and the drizzle prepare worker) and every accumulator. Normalising
  to the median keeps overall brightness stable (half scale gently up, half down); scales
  are bounded to `[0.5, 2×]` so one wild transparency estimate can't blow a frame up; a
  frame with no usable score stays neutral (1.0), and if fewer than 3 frames carry a score
  the whole run is neutral (a median off 1–2 frames isn't trustworthy). Orthogonal to and
  composes with quality weighting (that down-weights the *contribution*; this gain-matches
  the *values*). The run self-documents via `PHOTNORM`/`PHOTN*` FITS provenance keys
  (mirroring the `WGT*` keys). New engine module `seestack/stack/photometric.py`
  (`compute_photometric_scales` + `PhotometricStats`); surfaces in the Stack form as an
  advanced checkbox (descriptor-driven, no frontend change). Additive/upgrade-safe: a new
  off-by-default option field + new nullable FITS header keys, no schema/API/default change
  — an existing install's stacks are unaffected until opted in. Tests: engine unit
  (gain-match to median / clamp both sides / missing-score neutral / <3-measured fully
  neutral / identical-transparency all-neutral / non-positive scores ignored / NaN
  coverage preserved) + end-to-end (a hazy frame's boost lifts the combined bright-star
  level ~1.1×+ and stamps PHOTNORM; off by default writes no PHOTNORM; enabled-but-no-
  transparency stays neutral; runs on the drizzle path). (v0.81.0, this run — Builder)

- **Per-op split before/after — drag a divider to see the image with vs without just
  the op you're tuning (PRIORITY-1 editor/trust).** v0.78.0 added a whole-recipe split
  divider (Original vs Edited); this extends it to the more common editing question,
  "is *this* slider actually helping?". A new "Split this op" button next to the
  existing "Without this op" per-op compare overlays the editor's already-fetched
  *without-this-op* render (`withoutOpPreview`) on the edited preview and clips it with
  the same draggable vertical divider — left of the divider shows the image **without**
  the selected op, right shows it **with** — so the user judges exactly what one
  Sharpen/denoise/curve did at a glance, not just the whole recipe vs the raw base. It
  reuses the shipped `splitCompare.ts` geometry helpers and the shared `splitFrac`/
  divider drag state (one render block now serves both splits, choosing its "before"
  image + labels from which mode is active), so the only new state is a per-op
  `soloSplit` toggle (reset on selection change like the existing `soloExclude`, and
  mutually exclusive with every other overlay/trim/compare mode). Frontend-only,
  additive — no engine/API/schema change, off until clicked, no default change.
  Tests: Vitest (an Editor test that toggling "Split this op" on a selected Curves op
  overlays the clipped without-op render + divider at the default 50%, labels the sides
  "Without Curves" / "With", and clears when toggled off) on top of the existing
  `splitCompare.ts` helper coverage. (v0.80.0, this run — Builder)

- **Personal default recipe — "my house style" one click away on every new run
  (PRIORITY-2 autonomy).** User presets already let you save a recipe, but you had to
  name it and dig into the Presets menu to reuse it on each new target. Now the editor
  keeps one designated **default** recipe library-wide: a "Set current as my default" /
  "Clear my default edit" action in the Presets menu (`PUT`/`GET`/`DELETE
  /api/editor/default-recipe`, stored as a validated `editor_default_recipe` library-
  meta key alongside user presets), and any run opened with **no** saved edit now
  offers a one-click "Use my default (N)" button in the empty-pipeline nudge (next to
  the existing "Use my previous edit"), so a repeat imager's preferred look seeds a new
  target in one click. The seed is applied as a single **undoable** step and is not
  persisted unless the user Saves; the stored recipe is validated on load (unknown ops
  dropped, params clamped) so a stale op can never 500 the editor. **Off until the user
  sets a default** — nothing changes on a live install until they opt in (no default
  flip, no schema change — reuses the existing library-meta KV store; additive,
  upgrade-safe). Tests: webapp (unset → empty; set→get round-trips validated ops and
  drops unknown ones; DELETE and empty-PUT both clear) + Vitest (PresetMenu Set calls
  `putDefaultRecipe` with the current ops, Clear appears only once a default exists and
  calls `deleteDefaultRecipe`; an Editor test that a saved default surfaces the "Use my
  default (2)" seed, applying it lands exactly those ops in the pipeline and fires a
  preview carrying them, and the nudge clears once non-empty). (v0.79.0, this run —
  Builder)

- **Split before/after compare — drag a divider to see Original vs Edited in one
  frame (PRIORITY-1 editor/trust).** Compare was a *toggle*: you flipped the whole
  preview between "Original" and "edited" and had to remember the difference. A new
  "Split" mode button (next to Compare) overlays the Original empty-recipe render on
  top of the edited preview and clips it with a draggable vertical divider — the left
  of the divider shows the Original, the right shows the edit — so the user judges
  exactly what a stretch/denoise/curve changed at a glance, the clearest answer to the
  priority-1 "is my edit actually an improvement?" question. It reuses the two renders
  the editor already fetches (live edited preview + the existing `basePreview`
  empty-recipe "Original"), sits inside the existing `previewBoxStyle` image box so it
  lines up under `objectFit: contain`, and is its own mode (mutually exclusive with the
  mask/coverage/Compare overlays and suppressed during a trim preview). Frontend-only,
  additive — no engine/API/schema change, no default change (Compare stays a toggle,
  split is off until clicked). New pure helpers `splitFraction` / `splitClipLeft` /
  `splitLeftPct` in `splitCompare.ts` (pointer-x → clamped divider fraction → clip-path
  / offset). Tests: Vitest helper (pointer inside/past-edge clamping, unmeasured-box
  centre fallback, clip/offset strings) + an Editor test that toggling Split shows the
  clipped Original overlay + divider at the default 50%, disables Compare while on, and
  clears cleanly when toggled off. (v0.78.0, this run — Builder)

- **Reprocess-everything gains an "only outdated targets" filter (owner-requested
  slice c) — skips targets already stacked on the current version.** Building on the
  v0.76.0 per-run version stamp, the reprocess maintenance action no longer has to
  restack the *whole* library after an upgrade: a new `stale_only` flag on
  `POST /api/reprocess-all` (Settings toggle, **default on**) skips any target whose
  most recent *genuine* stack (a `_last_stack_version_for_target` helper walks
  newest-first, skipping editor/combine runs) already carries the current
  `webapp.__version__` — so only the images an upgrade would actually change get
  reprocessed. The batch summary now reports `skipped`, surfaced on the Jobs card as
  "… — K already up to date". Strictly opt-in and backward-compatible: the endpoint
  defaults `stale_only=False` for any caller that omits it (so the plain "reprocess
  everything" behaviour is unchanged), a target with no genuine stack / no recorded
  version is treated as stale and reprocessed, and nothing is ever deleted. The
  Settings toggle defaults to the more useful "outdated only" and relabels the button
  accordingly. Tests: engine (stale_only skips a current-version target and stacks a
  stale one; default reprocesses even current-version targets) + webapp end-to-end
  (POST `{stale_only:true}` skips up-to-date targets and adds no new runs) + Vitest
  (`reprocessSummary` skipped line; the Settings toggle drives the button label and
  passes the flag). (v0.77.0, this run — Builder)

- **Stack runs record the producing app version ("made with vX") — provenance +
  foundation for stale-target reprocessing (owner-requested slice c).** After an
  in-place upgrade a target's stack stays stale until restacked, and there was no way
  to tell *which* engine build produced a given image — so the "Reprocess everything"
  feature could only restack the whole library wholesale. Every stack run now stamps
  the AstroStack version that made it: a new nullable `engine_version TEXT` column on
  `stack_runs` (schema `SCHEMA_VERSION` 8→9, additive `ALTER TABLE`, backfilling NULL —
  old DBs migrate cleanly, pre-existing runs read None), populated from
  `webapp.__version__`. The engine stays webapp-free: `run_stack` gained an optional
  `app_version` param the webapp passes (`None` for direct engine callers); the two
  webapp-layer run records (editor export, channel combine) stamp it directly. The
  version rides through `StackRunOut` to the History card's metadata line ("… · v0.76.0"),
  omitted for legacy runs. Additive / upgrade-safe (new nullable column + new response
  value, no default/API-shape change). Tests: schema (v8→v9 migrates, old run reads
  None, new insert round-trips a version), engine end-to-end (`run_stack` records the
  passed version; `None` when unset), webapp (the stack-runs endpoint surfaces
  `webapp.__version__`), and Vitest (`formatEngineVersion` v-prefix/blank cases + the
  History card shows the version for a versioned run and omits it for a legacy one).
  (v0.76.0, this run — Builder)

- **Recipe carry-over across re-stacks: one-click "Use my previous edit"** — the Seestar
  user re-stacks a target repeatedly as more nights come in, and each new run opened on
  the flat default, losing the look they'd dialled in. A new read-only
  `GET …/editor/previous-recipe` endpoint returns the newest *other* stack run of the
  target that carries a non-empty saved recipe (walking `stack_runs` newest-first,
  probing `editor_recipe:{id}` meta; the recipe is validated on load so stale ops are
  dropped). When the current run has no saved edit, the editor's empty-pipeline nudge now
  shows a "Use my previous edit (N)" button that copies those ops into the working recipe
  as a single **undoable** step (a violet notification says Undo to revert / Save to
  keep); nothing is persisted unless the user Saves, and the query only fires when the
  run's saved recipe is empty (never nags a run with its own edit). **Off until clicked**
  — no default flip, no schema change (recipes already live in project meta keyed by run
  id, so it's a copy), upgrade-safe/additive. Tests: webapp (returns the newest edited
  run's ops with validated params / prefers the most recent of several / None when no
  other run is edited / None when nothing's edited) + Vitest (the button names the step
  count, applying it lands the ops in the pipeline and fires a preview carrying exactly
  those ops, and the nudge disappears once non-empty). (v0.75.0, this run — Builder)

- **Curves widget now previews the auto-contrast curve (read-only ghost) + "Bake to
  edit"** — the v0.73.0 auto-contrast (`tone.curves` `auto`) derives its curve at
  *render* time from the image entering the op while the stored points stay a flat
  identity, so selecting Auto's curve op showed **contrast in the preview but a flat
  identity line in the Curves widget** — a preview↔control mismatch and a missed teaching
  moment. Now when auto is engaged (on + points still identity) the widget draws the
  derived shape — the same one `…/editor/curve-suggestion` returns — as a read-only
  dashed ghost behind the (still-identity) editable curve, with a caption explaining
  what's happening, and a one-click **"Bake to edit"** that writes those points into the
  recipe and clears `auto` so the user can hand-tune from the real shape (a single
  undoable step). The redundant header "Auto curve" button is hidden while auto is
  engaged, so Bake is the single control. Frontend-only, additive, no API/behaviour
  change (the ghost is advisory; nothing is written until Bake or a manual edit). New
  pure `isIdentityCurve` helper (mirrors the engine `_points_are_identity`); a `ghost`
  prop on `CurvesWidget`; `curveGhost`/`onBakeCurve` on `OpParamPanel`. Vitest:
  `isIdentityCurve` (identity/moved/malformed), the widget ghost (dashed read-only
  polyline, not a draggable handle; absent when no ghost), and an Editor test that an
  auto+identity curve shows the ghost/caption, hides the header button, and Bake writes
  the suggested points with `auto:false`. (v0.74.4, this run — Builder)

- **"Cropped view — showing N% of the frame" indicator + one-click "Remove crop"** —
  a `geometry.crop` op silently shrinks the visible frame, so an auto-applied trim or a
  forgotten manual crop just looked like "my image got smaller" with nothing to say so.
  A dimmed advisory caption now renders below the editor preview whenever the recipe has
  an *enabled* `geometry.crop`, naming how much of the frame is still shown ("Cropped
  view — showing 64% of the frame."), with a one-click "Remove crop" that drops the
  crop op(s) as a single undoable step. The kept fraction is derived purely from the
  crop ops' own fractional bounds (mirroring the engine `_crop`'s clamp-to-[0,1] + sort
  semantics, and *multiplying* successive crops since each is relative to its input), so
  no new data/endpoint is needed. A disabled crop op is ignored (it isn't shrinking the
  view), and a crop that keeps the whole frame doesn't nag. Frontend-only, additive,
  advisory — no engine/API/behaviour change. New pure helpers `cropCoveragePct` /
  `cropCoverageFraction` / `removeCropOps` in `mosaicTrim.ts`. Vitest: the helpers
  (no-crop / full-frame / single & multiplied crops / clamp+sort of out-of-range bounds
  / garbage-tolerant / disabled-crop-kept) + an Editor test that a loaded crop shows the
  64% caption and "Remove crop" clears it. (v0.74.3, this run — Builder)

- **Fix: single-field stacks were misclassified as mosaics (Scout-verified
  wrong-result/broken-UX bug on the primary user's every-session case)** — the
  editor decided "is this a mosaic?" from `coverage_max > coverage_min`, but a real
  reprojected stack *always* has an uncovered NaN/zero border, so `coverage_min` is
  ~always 0 and the test was ~always True — mislabelling **single-field** stacks as
  mosaics. Consequence: one-click Auto prepended a no-op `background.level_coverage`
  *and* appended a spurious `geometry.crop` that trimmed a few px off every edge (and
  changed the export dimensions), plus the editor showed the mosaic banner, the
  "Trim border" button and the coverage-map overlay — all on a plain single-field
  OSC frame. Root fix: persist the stacker's **authoritative** union-canvas decision
  (`run_stack`'s own `is_mosaic_canvas`) as a new nullable `is_mosaic` column on
  `stack_runs` (schema `SCHEMA_VERSION` 7→8, additive `ALTER TABLE` migration,
  backfilling NULL — old DBs migrate cleanly, old runs read None). The three editor
  sites (histogram `is_mosaic`, trim-suggestion, Auto) now resolve the verdict via a
  shared `_run_is_mosaic` helper: the persisted flag when present, else — for legacy
  NULL runs — a **coverage-distribution** check (`coverage_is_mosaic`: a genuine
  mosaic has ≥2 large coverage plateaus at distinct levels; a single-field stack has
  one dominant interior level + a thin border ramp), *never* the old
  `max>min` test. `auto_recipe` now takes an explicit `is_mosaic: bool` (the buggy
  `coverage_span`→`_is_mosaic` heuristic is removed from the engine entirely). The
  histogram hot path reuses the coverage array it already loads (no extra I/O);
  legacy trim/auto load a strided coverage map. Additive/upgrade-safe (nullable
  column, no default/API-shape change; `is_mosaic` is a new response *value*, not a
  new field). Tests: engine (`coverage_is_mosaic` single-field-with-ramp→False /
  two-plateaus→True / empty / 3-D), schema (v7→v8 migrates, old run reads None, new
  inserts round-trip True/False), end-to-end (a real single-field `run_stack` records
  `is_mosaic=False`), and webapp regression (a **legacy** single-field run with a
  realistic coverage sibling now reports `is_mosaic:false` where the old heuristic
  said true; a legacy mosaic still classifies true). The fabricated
  `coverage_min==coverage_max` editor tests were updated to set the authoritative
  flag so a fabricated span can't hide the bug again. (v0.74.2, this run — Builder)

- **Jobs page surfaces the reprocess-all batch outcome in plain language** —
  companion to the v0.74.0 reprocess-everything feature: a finished `reprocess_all`
  job carries a `{total, stacked, failed, cancelled}` summary that the Jobs page
  previously didn't render, so the user couldn't see how many targets restacked or
  which failed. The job row now shows "Restacked N/M targets [(cancelled early)]
  [— K failed]." plus a red "Failed: …" line naming the targets that errored,
  driven by a pure, tested `reprocessSummary` helper (singularises one target;
  tolerates missing/garbage `failed` entries). Frontend-only, additive, advisory
  (no API/behaviour change). Vitest: helper (clean run / cancel+failures /
  singular+garbage-tolerant) + a Jobs row test that a batch result renders the
  summary and the failed-target list. (v0.74.1, this run — Builder)

- **⭐ OWNER-REQUESTED — "Reprocess everything" (slice a): one-click restack of
  every target with the current engine** — after an engine upgrade a target's
  final image stays stale until it's restacked by hand. A new confirm-gated
  "Reprocess all targets" action on the Settings page (a `Maintenance` panel) hits
  a new `POST /api/reprocess-all` endpoint that enqueues one serial `reprocess_all`
  job. The job walks every target and restacks it **reusing the settings that made
  its current image** — a new `_last_stack_options_for_target` helper reads each
  target's newest *genuine* stack run's `options_json` (a companion
  `_stack_options_from_run_json` rejects editor-export/channel-combine runs, which
  share the `stack_runs` table, and empty/garbage JSON), falling back to the
  target's saved stack defaults / global auto-defaults when it has none. It's
  **non-destructive** (each restack is recorded as a *new* `stack_runs` row via the
  normal `run_stack` path — old outputs are never touched, so a worse restack can't
  lose a good result and both show up in History) and **memory-safe** (the
  per-target stacks run serially inside the single job, so the memory-bounded stack
  hot path is never oversubscribed — OOM history). Cancellable between targets *and*
  within each target's stack; a target that fails to stack is isolated (its error is
  recorded and the batch carries on). A duplicate-batch guard
  (`JobManager.active_of_kind`) returns the running job instead of enqueuing a
  second. Additive / upgrade-safe: new endpoint + job kind + UI action, reusing the
  existing `stack_runs` schema and job manager (no config/DB/on-disk/API-shape
  change). Tested: engine (helper accept/reject cases; the batch reuses each
  target's last kappa, isolates a failing target, cancels between targets; the
  guard is active only for queued/running jobs) + webapp end-to-end (the endpoint
  enqueues a batch that restacks both targets and leaves the seeded prior run in
  place — additive) + Vitest (the confirm gate, the start/already-running/error
  notifications). (v0.74.0, this run — Builder)

- **Auto-process now gives its one-click result a gentle, data-driven contrast
  curve (the top PRIORITY-1 item, Scout-vetted & unblocked)** — the built-in
  galaxy/nebula presets ship a `tone.curves` S-curve, but the general `auto_recipe`
  was the flat exception (denoise → stretch → SCNR → saturation → sharpen, *no*
  contrast shaping), so the one-click "Auto" result was flatter than the presets the
  same app ships. `tone.curves` gained an `auto` bool param (default False): when set
  *and* the points are still the untouched identity, the op derives a gentle
  midtone-lift curve from its own (display-space) input **at apply time** via
  `suggest_tone_curve` — pinning the sky floor (p1) and highlight shoulder (p99.5) on
  the identity so it only *gently* lifts faint midtone structure (no sky brightening,
  no blown star cores), falling back to the presets' fixed gentle S-curve when the
  data offers no useful suggestion. `auto_recipe` appends `("tone.curves",
  {"auto": True})` after the saturation boost. Because it's computed at apply time
  from robust global percentiles it adapts to the actual stack *and* holds
  proxy↔export parity (measured mean |diff| ~0 for the curve itself). A hand-edited
  (non-identity) curve always wins, so toggling auto never discards manual work; Auto
  is an explicit button (no default flip, upgrade-safe/additive — older recipes
  simply lack the op/param). Verified empirically on a dim synthetic OSC stack
  (p50 0.191→0.221, sky/highlight deltas ≤0.0001), matching the Scout's visual
  vetting. Tests: engine (auto lifts the midtone from identity / falls back to the
  fixed S-curve when the suggestion is None / manual points win / NaN preserved),
  auto_recipe (curve appended after saturation with `auto=True` + identity points;
  end-to-end the rendered result's median rises), webapp (the `/editor/auto` recipe
  carries the curve). Frontend: the Auto-summary names it "added a gentle contrast
  curve"; the `auto` toggle surfaces as an advanced control on the Curves op.
  (v0.73.0, this run — Builder)

- **Auto-process summary names the mosaic coverage-leveling step in plain language** —
  the "What Auto-process did" summary maps each Auto op to a plain-language phrase
  (v0.70.1 added `geometry.crop`), but `background.level_coverage` — which
  `auto_recipe` prepends as the *first* step on a mosaic to even out uneven-overlap
  panel brightness — had no phrase, so on a Seestar mosaic the whole one-click
  summary opened with the bare jargon registry label "Coverage leveling" while
  every other step read cleanly. Added a phrase ("evened out the mosaic panel
  brightness") to `OP_PHRASES`, completing plain-language coverage of every op Auto
  can emit. Frontend-only, additive, advisory (no image/behaviour/API change).
  Vitest: a regression case that a `background.level_coverage`-led recipe summarises
  with the plain phrase, not the jargon label. (v0.72.5, this run — Builder)

- **Fix: SCNR "Protect" tooltip had gentler/stronger reversed (misled the most
  common OSC fix)** — Builder editor audit found the `tone.scnr` `mode` param's help
  read "to the average (gentler) or maximum (stronger) of red/blue" — exactly
  backwards. SCNR caps green with `min(g, neutral)`: `average` uses the *lower*
  neutral `0.5·(r+b)` so it removes **more** green (stronger), `maximum` uses the
  *higher* neutral `max(r,b)` so it removes **less** (gentler) — matching standard
  (PixInsight "Average/Maximum Neutral") terminology. A beginner wanting a light
  touch reads "average (gentler)", picks it, and gets the *most* aggressive green
  removal — desaturating real teal/cyan nebulosity, the opposite of the promise.
  Green-cast removal is the single most common OSC nebula fix and this tooltip is
  the only guidance for the choice, so the label matters. Swapped the parentheticals
  to "average (stronger) or maximum (gentler)". Metadata/text-only, additive,
  upgrade-safe (no behaviour, API, or default change). Regression test in
  `tests/test_edit_tone_ops.py` pins the *semantics* (average caps green to
  `0.5·(r+b)`, maximum to `max(r,b)`, so average leaves less green — the stronger
  effect) **and** asserts the help text labels them that way round, so the tooltip
  can't drift back out of sync with the maths. (v0.72.4, this run — Builder)

- **Fix: a thin crop + downscale no longer crashes the editor preview/export with
  an empty image** — Builder dogfood (fuzzing every edit op with adversarial
  inputs) found that `geometry.resize` computed its output shape via scipy `zoom`'s
  `round(dim·scale)`, so a heavy downscale of a thin frame (a ≤2px sliver crop on
  the proxy — which survives the crop op's own `>=2px` guard — or a small proxy)
  drove an axis to **0 px**, yielding a `(0, N, 3)` empty image that then raised
  `ValueError: cannot write empty image` in the PNG/TIFF render — an unhandled
  **500** in `GET …/editor/preview`, `…/editor/histogram`, `POST …/editor/export`
  and `…/editor/export-png`, plus a failed batch job (same input-hardening class as
  the v0.69.0/v0.69.5 malformed-recipe 500 fixes). `_resize` now derives exact
  per-axis zoom factors from a guaranteed-`>=1px` target shape, so an extreme
  downscale lands on a valid 1px strip instead of an empty array (and the coverage
  overlay's `apply_geometry_to_map`, which reuses the same op, is covered too).
  Engine-only, additive/upgrade-safe (the effect is unchanged for any resize that
  didn't previously collapse). Regression tests: engine (`geometry.resize` never
  returns a zero-size axis on collapsing scales; a stretch→thin-crop→downscale
  recipe stays PNG-encodable) + webapp (the preview & histogram endpoints return a
  valid PNG/200 for that recipe instead of a 500) — all three fail before the fix.
  (v0.72.3, this run — Builder)

- **Editor exports are marked display-space — no more re-edit double-stretch, and
  the FITS is honest** — an editor export writes its already tone-mapped `[0,1]`
  result to a FITS, but it was stamped `BUNIT = "ADU (linear)"` and carried no
  "this is display-space" marker, so (a) re-opening the edited run in the editor
  (empty recipe) ran the default asinh stretch *again* — the re-edit
  double-stretch — and (b) the FITS told Siril/PixInsight it was linear ADU when
  it's a picture. Now `_write_fits` stamps an `SSDISPLY = T` card + honest
  `BUNIT = "display"` on editor exports, the export run's `options_json` carries a
  `display_space` flag, and a new engine helper `fits_is_display_space` +
  `EditContext.already_display` let the render/edit paths *skip* the default
  fallback stretch for a display-space image: `render_stack_png` (used by
  `render_stack_run`/save-preview) renders it verbatim, the editor proxy preview/
  histogram/star-mask/levels+curve suggestions build the context with
  `already_display`, and `_render_recipe_fullres` (re-edit → export) suppresses its
  fallback too. An explicit stretch op the user adds still runs. Absence of the
  card/flag = today's linear behaviour, so old runs and non-editor stacks are
  unaffected (upgrade-safe, additive). Engine (`output.py`, `registry.py`,
  `pipeline.py`, `thumbnail.py`) + webapp (`pipeline.py`, editor router). Tested:
  engine (`already_display` suppresses the fallback but an explicit stretch still
  runs; `SSDISPLY`/BUNIT stamped for display exports and absent for linear;
  `fits_is_display_space` incl. missing-file), render (display-space FITS renders
  verbatim, sliders a no-op, vs a linear stack), webapp (export marks the new run
  in options_json + FITS, source unaffected; re-opening a display-space run's
  editor preview doesn't double-stretch while the same data without the flag
  does). (v0.72.2, this run — Builder)

- **"Auto curve" button names its goal + dims when already applied (data-driven
  family consistency)** — small follow-up to v0.72.0: the new Curves-op "Auto
  curve" header button was opaque ("Auto curve") and always enabled, unlike the
  rest of the data-driven tonal family (Auto levels shows its black–white values,
  Auto stretch its strength, the gamma button names "~25% grey", per-param buttons
  flip to a disabled ✓). It now reads "Auto curve (lifts to ~N% grey)" — the grey
  the midtone lift solves for, served honestly from the suggestion's existing
  `target_bg` — and dims to a disabled "Auto curve ✓" once the current control
  points already equal the suggestion, so re-clicking a no-op isn't invited. A pure
  `curvePointsMatch` helper does the structural point-list compare (same length,
  each `[x,y]` within a tiny epsilon; a missing/malformed list or absent suggestion
  never matches). Frontend-only, additive; no API or behaviour change beyond the
  label/disabled state. Vitest: helper (identical / within-epsilon / moved /
  different-length / absent suggestion / malformed) + the existing Editor "Auto
  curve" test extended to assert the goal-naming label and the disabled ✓ after a
  click. (v0.72.1, this run — Builder)

- **Data-driven "Auto curve" starting point for the Curves op (completes the
  family of data-driven tonal defaults)** — the Curves op was the last major tonal
  control that dropped a beginner on a flat identity line to hand-shape, while
  Levels (black/white/gamma), Stretch (strength/black), Sharpen, Denoise, Star-size
  and Deconv-PSF all offer a one-click "From your image" start. A new pure engine
  helper `seestack/edit/curve.py:suggest_tone_curve` measures the display-space
  histogram of the image *entering* the op and returns a gentle, strictly-monotone
  midtone-lift curve: the sky floor (p1) and highlight shoulder (p99.5) sit on the
  identity (background not crushed, star cores roll off rather than blow) while the
  median is lifted a *fraction* of the way (`_LIFT_FRACTION` 0.5) toward the same
  pleasant target grey (`CURVE_TARGET_BG` 0.25) the Levels gamma suggestion uses. It
  returns `None` on degenerate/low-range data or when the typical tone already sits
  at/above target (nothing to lift), merges a zero-valued sky anchor into the pinned
  (0,0) endpoint (so a hard black clip doesn't force a duplicate point), and
  validates the assembled points are strictly increasing in both axes so the LUT can
  never invert or posterise. Exposed as a `…/editor/curve-suggestion` endpoint
  (mirrors levels/stretch-suggestion; measures the image entering the op via
  `_recipe_before_uid(..., drop_ids=("tone.curves",))`) plus a header "Auto curve"
  one-click. Engine + one endpoint + frontend; additive/upgrade-safe (older clients
  ignore the endpoint). Tested: engine (midtone lifted toward target / ends anchored
  / monotone, clamp+round, NaN-ignored, degenerate & already-bright → None, and the
  suggested curve round-trips through the real `_curves` op preserving NaN and
  staying in range), webapp (a stretched stack yields a monotone endpoint-pinned
  curve + target_bg; unknown-uid falls back to 200), Vitest (selecting the Curves op
  surfaces "Auto curve" and one click propagates exactly the suggested points into
  the recipe). (v0.72.0, this run — Builder)

- **Every tonal control's landing shown on the histogram (Stretch/clip edges +
  Curves points, not just Levels)** — the `Histogram` `guides` prop (v0.65.0) only
  ever marked the Levels black/white points, so a beginner setting a Curves bend or
  over-stretching into a clip had no visual cue of *where on the tonal range* it
  landed. Now (a) whenever the clipping caption fires, an orange "clip" guide marks
  the exact edge it warns about — value 0 (crushed shadows) and/or value 1 (blown
  highlights) — driven by a new `clippingEdges` helper refactored out of
  `clippingCaption` so the caption and the guide can never disagree; and (b) when a
  `tone.curves` op is selected, faint dashed purple guides mark each *interior*
  control point's input position (endpoints are pinned at 0/1 and already covered by
  the clip edges), with a one-line caption, so the user can see whether a bend sits
  on the sky peak, the midtones, or the highlights. A new pure `tonalHistGuides`
  composes the Levels + Curves + clipping guide helpers into the single `guides`
  prop. Frontend-only, additive, advisory (changes nothing about the image). Vitest:
  `clippingEdges` (threshold parity with the caption), `curvesHistGuides` (interior
  only / identity curve / malformed points), `clippingHistGuides` (each edge + both),
  `tonalHistGuides` (composition), plus an Editor test that selecting a Curves op
  surfaces the caption. (v0.71.2, this run — Builder)

- **Fix flaky frontend CI at the root: run vitest test files sequentially
  (`fileParallelism: false`)** — `main`'s frontend CI had been intermittently red
  (it was already failing on the commit this run branched from) with "unable to find
  element" timeouts in `Editor.test.tsx`, despite the code being fine and the suite
  passing locally. Root cause (as v0.69.19 diagnosed but only mitigated with
  timeouts): the heavy Editor tests spin up many full-app renders, and when several
  test-file workers run in parallel on a small CI runner the Editor worker is
  CPU-starved — a `findBy*`/`waitFor` that settles sub-second when scheduled instead
  drags past 10s, and any *synchronous* assertion right after it races the lagging
  render. Raising timeouts repeatedly didn't stop it. Serialising the test files
  (each gets the full CPU; whole suite ~65s vs ~27s parallel — a fine trade for a
  reliably green gate) removes the starvation so the timeouts are never approached.
  Also hardened this run's new Stretch-suggestion test to click the header button via
  `findByRole` (waits for its render) rather than a synchronous `getByRole`.
  Test-infra only; no product code or assertion weakened. (v0.71.1, this run — Builder)

- **Data-driven "From your image" Strength + Black point for the asinh Stretch
  (completes the family of data-driven tonal defaults)** — the Stretch op was the
  single most consequential editor control yet the only major tonal op *without* a
  data-driven suggestion button (Levels/Sharpen/Denoise/Star-size/Deconv-PSF all
  have one), so a beginner hand-guessed its two asinh sliders. A new pure engine
  helper `seestack/edit/stretch.py:suggest_asinh_stretch` measures the *linear*
  image entering the op and solves for a good pair: the **black point** puts the
  sky floor (a low percentile) at black — exactly as the Levels suggestion does —
  by inverting asinh's `shadows = median + (6·black − 2)·σ`; the **strength** is
  solved (bisection; the asinh response is monotone in stretch) so the sky median
  lands at a clean dark-sky grey (`STRETCH_TARGET_BG`, 0.10 — deliberately below
  the STF's 0.20 because asinh's gentler curve can't reach it on a bright-star
  stack, so the suggestion lands on a meaningful intermediate value instead of
  always maxing out). Exposed as a `…/editor/stretch-suggestion` endpoint (mirrors
  levels-suggestion; measures the linear proxy via a new opt-in
  `apply_recipe(..., auto_stretch=False)` that suppresses the default-stretch
  fallback so we never measure a tone-mapped image) plus a header "Auto stretch"
  one-click and per-slider "From your image" buttons (only in asinh mode; the
  Strength button names the target grey it solves for). Engine + one endpoint +
  frontend; additive/upgrade-safe (older clients ignore the endpoint; the new
  `auto_stretch` flag defaults to today's behaviour). Tested: engine (target-grey
  landing verified against the real `asinh_stretch`, higher-DR-needs-more-strength,
  clamp-on-extreme-DR, NaN/degenerate/rounding guards), pipeline
  (`auto_stretch=False` returns the linear ops output), webapp (in-range
  strength/black + target_bg, unknown-uid fallback), Vitest (Auto stretch sets both,
  the buttons name the values/goal, and the suggestion is hidden in STF mode).
  (v0.71.0, this run — Builder)

- **Auto-process summary names the mosaic border trim in plain language** — small
  companion to v0.70.0: now that Auto can append a `geometry.crop`, the "What
  Auto-process did" note would have fallen back to a bare "…then crop." (the op's
  registry label). Added a plain-language phrase for `geometry.crop` ("trimmed the
  ragged mosaic border") so the one-click summary reads honestly and a beginner
  understands the frame shrank on purpose. Frontend-only, additive. Vitest: the
  phrase appears in `autoSummaryPhrases`. (v0.70.1, this run — Builder)

- **Auto-process trims a mosaic's ragged low-coverage border (cleanly framed
  one-click result)** — on a mosaic, `auto_recipe` levelled the panel steps but
  left the union canvas's ragged, single-frame-coverage fringe in the one-click
  result, so "Auto" framed the picture with a noisy low-coverage border the user
  had to discover the Trim tool to remove. Auto now appends a final `geometry.crop`
  to the largest well-covered rectangle — reusing the exact `largest_covered_rect`
  machinery behind the "Trim border" button (extracted into a shared
  `_trim_rect_for_run` helper the trim-suggestion endpoint now also calls). The crop
  runs *last* (after every tone/detail op) so the coverage-leveling op still sees the
  native-geometry coverage map, and it's only added when the trim is *meaningful*
  (`largest_covered_rect` returns `None` on a full-frame result) and only on a mosaic
  — a single-field stack is never cropped. The crop is a normal, visible, removable
  op (and the coverage overlay, per v0.69.20, now follows it). Off-by-default risk is
  nil (Auto is an explicit button; no default flip). Engine (`auto_recipe` gains an
  optional `trim_crop`) + webapp wiring; additive/upgrade-safe. Tested: engine (crop
  appended last iff a trim is supplied; none for single-field/None), webapp (a mosaic
  with a ragged coverage sibling gets a final interior crop; single-field and
  no-sibling get none). (v0.70.0, this run — Builder)

- **Coverage overlay now follows the recipe's geometry ops (was frozen on the
  uncropped frame)** — the editor's mosaic coverage-map overlay rendered the run's
  *raw* full-frame coverage sibling, so once a `geometry.crop`/rotate/resize op was
  in the recipe (very likely after "Trim border") the heatmap no longer lined up
  with the reshaped preview — v0.61.5 could only *caption* the mismatch ("shown for
  the uncropped frame"). Now a pure engine helper `apply_geometry_to_map(cov,
  recipe, ctx)` (in `seestack/edit/ops/geometry.py`, keyed on a new `GEOMETRY_OP_IDS`
  constant) runs the recipe's *enabled geometry ops only*, in recipe order, over the
  2-D coverage map — feeding it through each op as three identical channels —
  preserving NaN = uncovered (crop copies, rotate fills exposed corners with NaN,
  resize interpolates). The `…/editor/coverage-map` endpoint takes an optional
  `recipe` query param and applies it before colouring; the editor passes the
  debounced recipe and keys the query on just the geometry ops (`geometryOpsKey`) so
  a tone tweak doesn't refetch. The caption drops the "uncropped frame" disclaimer.
  Engine + one endpoint param + frontend; additive/upgrade-safe (older clients omit
  `recipe` → today's raw full-frame overlay). Tested: engine (crop reshapes + keeps
  NaN, tone/disabled ops are no-ops, rotate NaN-corners), webapp (a crop recipe
  yields a strictly smaller coverage PNG), Vitest (`geometryOpsKey` 3 cases + the
  overlay passes the recipe and the caption no longer disclaims). (v0.69.20, this
  run — Builder)

- **Fix flaky frontend CI at the root: raise vitest `testTimeout` above
  `asyncUtilTimeout`** — three `Editor.test.tsx` tests kept reddening `main`'s
  frontend CI ("Test timed out in 5000ms") on *unrelated* merges (took down the
  push CI for #79). Root cause: v0.69.6 raised Testing Library's `asyncUtilTimeout`
  to 10000ms so `waitFor`/`findBy*` could ride out a slow-CI debounce/re-fetch
  settle, but vitest's per-test `testTimeout` was left at its 5000ms default — so a
  10s async retry was *killed at 5s* before it could ever succeed; the raised
  async ceiling was dead. Set `testTimeout`/`hookTimeout` to 30000ms (comfortably
  above the async ceiling) in `vite.config.ts` and raised `asyncUtilTimeout` to
  20000ms after a full local parallel run starved the heavy Editor worker to a
  10534ms `waitFor`; the settle it waits on is sub-second when scheduled, so the
  headroom covers scheduling starvation without slowing passing tests (the retry
  stops early on success — verified: two back-to-back full runs 378/378, duration
  unchanged). Also wrapped one post-error "Star mask" caption assertion in
  `waitFor` (it's torn down a render tick after the error message, so the bare
  synchronous check raced the suppression under load). Test-infra only; no product
  code or assertion weakened. (v0.69.19, this run — Builder)

- **Gamma suggestion names the goal it solves for (not just a bare number)** — the
  data-driven midtone button (v0.66.0) read "From your image (midtones 1.6)"; like
  the sharpen/denoise buttons that name *why* (FWHM, noise σ), it now reads "From
  your image (midtones 1.6 — lands the sky at ~25% grey)", so the number has visible
  provenance and the beginner sees it's brightening the typical tone to a target, not
  a magic value. The target grey is served honestly from the engine constant
  (`GAMMA_TARGET`, the value `suggest_levels_gamma` actually solves for) as a new
  optional `gamma_target` field on the `levels-suggestion` payload, so the label
  can't drift from the maths. Engine constant + one API field + label; additive/
  upgrade-safe (older clients ignore the field, fall back to the bare label).
  Tested: webapp (`gamma_target` present iff a gamma is suggested and equals the
  constant), Vitest (the gamma button names "~25% grey"). (v0.69.18, this run —
  Builder)

- **"Edited" dot on tuned op rows in the pipeline list** — after Auto-process or a
  preset drops a dozen ops in, a user couldn't tell at a glance which ops they'd
  tuned vs which sat at stock defaults. Each `OpList` row whose params differ from
  the op's schema defaults now shows a small grape "•" with an "Edited — one or
  more settings differ from this op's defaults." tooltip. Driven by a pure
  `opModified` helper (mirrors the `isDefault` comparison in `OpParamPanel`:
  missing/null = default, stale keys ignored, structured curve params compared by
  value). Frontend-only, additive, advisory. Vitest: helper (8 cases) + OpList
  (dot shows only on the tuned row, absent when all at defaults). (v0.69.17, this
  run — Builder)

- **Editable numeric readout beside every editor slider** — the editor rendered
  each bounded param (`StackOptionControl` `preferSlider`) as a slider with a
  *dimmed, read-only* value, so a user who knew the exact value they wanted
  (gamma 1.35, PSF σ 1.8, black 0.07) could only approximate it by dragging — hard
  to hit precisely on a touch/trackpad. The readout is now a small editable
  `NumberInput` sharing the field's value/min/max/step (right-aligned, no spinner,
  clamp-on-blur, int fields round), so coarse dragging and exact typing both work
  and stay in sync. Respects `disabled`; feeds the same `onChange` (so drag/undo
  coalescing is unchanged). Frontend-only, additive, no default change; only the
  editor uses `preferSlider` (the Stack/Settings forms already had number inputs).
  Vitest: readout shows the current value, typing emits the number, int rounds,
  empty is ignored. (v0.69.16, this run — Builder)

- **Fix (a11y): editor curve points are keyboard-operable** — the last open
  editor bug. The Curves op's control points were drag-only SVG circles, so a
  keyboard user couldn't add, move, or remove a curve point. Each point is now a
  focusable `role="slider"` (`tabIndex=0`, descriptive `aria-label` +
  `aria-valuetext`): arrow keys nudge it (Shift = coarse step), Delete/Backspace
  removes an interior point, and a new keyboard-accessible "add point" button
  inserts a point in the widest gap (on the current curve) and focuses it. Pure
  `nudgeCurvePoint` / `removeCurvePoint` / `addCurvePointInLargestGap` helpers
  (all reusing the existing ordering-safe `moveCurvePoint`) drive it; the mouse
  drag/double-click paths are unchanged. Frontend-only, additive. Vitest: helper
  suite (nudge clamps + endpoint-x-lock + no-mutate; remove keeps endpoints; add
  in-largest-gap incl. identity) + a widget suite (points are focusable sliders,
  ArrowUp/Shift-Arrow nudge, Delete removes, endpoint x stays locked, the button
  adds a mid point). (v0.69.15, this run — Builder)

- **Fix: trim-crop preview rectangle misaligned on a letterboxed preview** — the
  dashed "proposed crop" overlay mapped fractional bounds to percentages of the
  *container*, but the preview `<img>` is width-100% capped at 62vh with
  `objectFit: contain`, so on a portrait frame / short window it pillarboxes
  inside its element and the rectangle landed offset/mis-scaled vs the visible
  image. The preview image now lives in an *image box* wrapper sized to the shown
  image's exact content box (a new pure `previewBoxStyle` helper gives the box the
  image's own aspect ratio — from the already-reported `proxy_width`/`proxy_height`
  — and caps its width so the aspect-preserved height never exceeds 62vh, so there's
  no letterbox), and the proposed-crop rectangle is drawn inside that box, so its
  percentage bounds line up in every framing. Falls back to plain full-width when
  the proxy dims aren't loaded yet (old behaviour). Frontend-only, additive.
  Vitest: `previewBoxStyle` (fallback / portrait aspect+width-cap / custom
  max-height); existing trim-preview Editor tests still green. (v0.69.14, this
  run — Builder)

- **Fix: deconvolution's live preview silently understated the export on large
  stacks — now captioned honestly** — the top editor bug. On a heavily-decimated
  preview proxy (a ≤1500 px view of a wide mosaic/drizzle, `proxy_scale` ≥ ~4)
  the proxy-corrected PSF `max(0.4, scaled_px(psf_sigma))` collapses to the floor
  and Richardson-Lucy's near-delta 3×3 kernel barely acts, so the preview showed
  a fraction of the star-sharpening the full-res export applies — a preview↔export
  mismatch with *no notice* to the user. The sub-pixel blur genuinely isn't
  representable on the decimated grid (no PSF tweak recovers it), so instead of
  silently misleading we now surface an honest advisory: a pure
  `deconv_understates_on_proxy(psf_sigma, proxy_scale)` engine helper (shared with
  the backend and the `_DECONV_PSF_FLOOR` constant it keys on) flags exactly the
  floored case; the histogram endpoint reports `deconv_preview_understates` for any
  enabled Deconvolution op that collapses on the current proxy; and the editor
  shows a dimmed "preview understates the effect — the export applies it at full
  strength" caption under the preview. Engine + one endpoint field + frontend;
  additive/upgrade-safe (older clients ignore the new field). Tested: engine
  (the flag matches a *measured* weak preview — <½ the export's effect — and the
  rule's boundary cases incl. degenerate inputs), webapp (the flag fires only for
  an enabled, collapsing deconv op on a decimated proxy), Vitest (caption helper
  3 cases). (v0.69.13, this run — Builder)

- **Fix: editor overlay-zoom mislabel + keyboard access gaps (a11y)** — three
  editor a11y fixes. (1) The zoom lightbox titled whatever was shown as "edited"
  unless Compare was on, so zooming the Star-mask/Coverage overlay mislabelled the
  overlay as "edited"; the title now reads from the active overlay's own label
  ("Star mask"/"Coverage map"/"Original"), falling back to "edited" only when no
  overlay is up. (2) The Curves "reset" control was a bare `<Text onClick>` (not
  focusable, no role) → now a real `<Anchor component="button">`. (3) `OpList` rows
  were click-only `<Paper>` divs, so selecting an op to edit was impossible by
  keyboard; rows are now `role="button" tabIndex=0 aria-pressed` and activate on
  Enter/Space (without hijacking a focused inner switch/arrow/✕). Frontend-only,
  additive. Vitest: new OpList a11y suite (focusable rows, Enter/Space selects,
  aria-pressed) + an Editor test that the lightbox titles from the overlay, not
  "edited". Remaining gap (mouse-only curve points) filed as an a11y follow-up.
  (v0.69.12, this run — Builder)

- **Fix: background/gradient op failures now surface in the editor (were a silent
  no-op / colour-shift)** — `remove_final_gradient` swallowed its Background2D fit
  failure and returned the input, and `subtract_background` skipped a failed channel
  and continued — so the v0.61.11 "surface failed ops" contract never saw the bg
  ops' likeliest real failure, and a per-channel skip could subtract from some
  channels but not others (colour cast) with no notice. Both functions grew an
  opt-in `errors` collector: the stack path leaves it `None` (unchanged best-effort
  skip-and-continue), but the editor wrappers (`seestack/edit/ops/background.py`)
  pass a collector and `raise` when it's non-empty, so `apply_recipe` surfaces the
  failure in the existing preview/export error UI — and a per-channel failure is now
  all-or-nothing (return the input unchanged rather than a partial, colour-shifting
  subtract). Engine + editor-wrapper, additive/upgrade-safe. Regression tests: a
  monkeypatched-to-fail Background2D makes every editor bg op (both modes) raise and
  the error reach `apply_recipe`'s collector, while the stack path stays
  non-raising. (v0.69.11, this run — Builder)

- **Fix flaky `detail.sharpen` NaN test (route unsharp mask around skimage)** — the
  `detail.sharpen` op called scikit-image's `unsharp_mask(..., channel_axis=-1)` on
  `float32`, which on some scikit-image/scipy builds intermittently returned
  uninitialised finite garbage (`7.7e37`, denormals) or a stray NaN in the *covered*
  region — reddening `main`'s CI (took down PR #66) via
  `test_detail_ops_preserve_nan_on_partial_coverage[detail.sharpen-params1]` in
  full-suite order. Replaced it with a deterministic per-channel unsharp mask in
  pure numpy/scipy (`sharp = img + amount·(img − gaussian_filter(img, sigma,
  mode="nearest"))`), which fully initialises the output and matches skimage's
  effect. Stress-tested 200× (zero garbage). Engine-only, additive; the effect is
  unchanged for users. Updated the proxy-scale parity test to capture the Gaussian
  sigma instead of the (now-unused) `unsharp_mask` radius. (v0.69.10, this run — Builder)

- **Fix: "Use data defaults" toolbar and the per-param "✓ already set" indicator
  now agree** — `applyDataDrivenDefaults`/`countDataDrivenDefaults` compared the
  current value to the suggestion with strict `!==`, while the per-param "From your
  data" button uses `matchesSuggestion` (half-step tolerance) — so a value within
  half a step of the suggestion (slider lands on 1.4, suggestion 1.36) read "✓
  already set" on the param yet the toolbar still offered "Use data defaults"; the
  count also included *disabled* ops. Both functions now share a `wouldChange`
  helper that uses `matchesSuggestion` with each param's step (threaded into the
  suggestion from the op schema) and skips disabled ops, so the toolbar count, the
  apply action, and the per-param indicator are consistent. Frontend-only,
  additive. Vitest: added within-half-step-is-already-set and disabled-op-skipped
  cases to the existing helper suite. (v0.69.9, this run — Builder)

- **Fix: star-mask overlay now reflects the display-space image the ops gate on
  (was computed on the raw linear proxy)** — the "Star mask" trust overlay ran
  `star_mask` on the *linear* proxy, but `stars.reduce`/`stars.boost_nebula` (both
  `stage="nonlinear"`) gate on the **stretched** image at their pipeline position,
  where faint stars pop out of the noise — so the overlay drastically
  under-represented what the ops actually touch (faint stars simply weren't shown).
  `edit_star_mask` now accepts the current `recipe` + selected star-op `uid`,
  applies the recipe up to (but not including) that op via a generalized
  `_recipe_before_uid(..., drop_ids=("stars.reduce","stars.boost_nebula"))`, and
  masks the resulting display-space image (empty recipe → the pipeline's default
  asinh stretch, matching the ops). Falls back to the linear proxy when no recipe
  is passed (old clients). Same run also **debounces** the overlay: `maskSizePx`
  and the recipe are now debounced and in the query key, so dragging "Star size"
  no longer fires a `star_mask` render per tick. Engine/webapp + frontend;
  additive/upgrade-safe (new optional query params, response unchanged). Tested:
  webapp (a stretched recipe marks ≥2.5× more faint-star mask weight than the
  linear render; recipe+uid stops before the selected op) + Vitest
  (`editStarMaskUrl` carries size/recipe/uid; the overlay passes the recipe with no
  uid when no star op is selected). (v0.69.8, this run — Builder)

- **Fix: one slider/curve drag no longer floods (and evicts) the editor's undo
  history** — every editor slider tick and every curve pointer-move went through
  the history-capturing `setOps`, so a single drag pushed dozens of entries and a
  couple of long drags evicted all earlier edits (added ops, Auto-process) past the
  100-entry cap; Ctrl+Z then undid one sub-pixel of a drag instead of the whole
  edit. `useUndoable.set` now takes an optional `coalesceKey`: consecutive sets
  sharing a key update in place *without* a new history entry, so a continuous drag
  collapses to one undoable step. `OpParamPanel` passes a per-param key
  (`param:<key>`, namespaced by op uid in `Editor.setParams`) for the continuous
  slider/curve controls and *omits* it for discrete button edits (reset,
  suggestions), so each of those stays its own step. Different params and different
  ops never merge (distinct keys); a keyed set right after an undo starts a fresh
  entry. Frontend-only, additive; no API/behaviour change beyond history grouping.
  Vitest: `useUndoable` coalescing (4 cases: collapse-a-drag / no-merge-across-keys
  / discrete-keyless / fresh-after-undo) + `OpParamPanel` (slider carries
  `param:amount`, buttons are single-arg keyless). (v0.69.7, this run — Builder)

- **Fix flaky frontend CI (Editor Levels "From your image" / "Auto levels" tests)** —
  these tests click a data-driven button and `waitFor` it to flip to its
  already-applied (disabled + ✓) state, which only settles after a debounced recipe
  re-render / re-fetched suggestion. Testing Library's default 1000ms async timeout
  was too tight for the slower CI runner, so the suite passed locally (332/332) but
  reddened `main`'s CI on unrelated merges (#74, #75). Raised `asyncUtilTimeout` to
  5000ms globally in `src/test/setup.ts` — no assertion changed, only how long
  `waitFor`/`findBy*` retry. Restores the CI safety net. (v0.69.6, this run)

- **Editor recipe with a non-mapping `params` no longer 500s** — a recipe body
  whose op carried `params` as a list/string/number (a malformed client body or a
  hand-built recipe) hit `dict(o.get("params"))` in `recipe_from_dict`, which
  raised `ValueError`/`TypeError` — an **unhandled 500** in `PUT …/editor/recipe`
  and `POST /api/editor/presets`, and a failed export/PNG/batch job. Reproduced via
  the real API (TestClient) with `params: ["x","y","z"]` → 500. `recipe_from_dict`
  now coerces any non-mapping `params` to `{}`, so `validate_ops` fills each key
  from the op's schema defaults (the op is kept, not dropped). Same
  input-validation-hardening class as the v0.69.0 stack/frames 500 fixes.
  Engine-only, additive/upgrade-safe. Regression test: a non-mapping `params`
  (list/str/int/None) keeps the op at its defaults instead of raising. (v0.69.5,
  this run — Scout)

- **One-click "Reset points" on the Levels op header** — the Levels header had
  "Auto levels" to *set* data-driven points but no matching one-click to *undo* a
  bad manual drag back to the neutral identity (only per-param reset icons). Added
  a "Reset points" header action (next to "Auto levels") that restores black=0,
  white=1, gamma=1 in one click, dimmed when already neutral — a clean escape hatch
  symmetric with Auto for a beginner who over-dragged. Pure `levelsReset` helpers
  (`levelsAtIdentity`/`resetLevelsPoints`) drive it; frontend-only, additive.
  Vitest: helper (identity/moved/preserve-other-keys/no-mutate) + an Editor test
  that clicking Reset returns an over-dragged op to neutral (button dims).
  (v0.69.4, this run)

- **Data-driven midtone (gamma) point for the Levels op** — the Levels suggestion
  (v0.62.0) + "Auto levels" (v0.64.0) set the black/white points from the histogram
  but left the **gamma** (midtone) slider — the control that most affects perceived
  brightness — at 1.0 for a beginner to hand-guess. A new pure
  `suggest_levels_gamma` helper solves `x_m**(1/γ)=target` for the image's median
  tone after the black/white remap (lands the typical tone at a pleasant 0.25 grey),
  returned as an optional `gamma` on the `levels-suggestion` payload. "Auto levels"
  now applies all three at once and a "From your image (midtones …)" per-param button
  appears on the gamma slider (only when a meaningful lift exists). NaN-aware,
  clamped to the op's 0.1–5.0 range, `None` when the median already sits at/above
  target or the range is degenerate. Engine + endpoint + frontend; additive/
  upgrade-safe (older clients ignore the new field). Tested: engine helper (5 cases:
  dark-median lift lands near target / bright-median no-lift / degenerate range /
  too-few-pixels / clamp+round), webapp (payload carries `gamma`), Vitest (one Auto
  levels click leaves all three per-param buttons ✓/disabled). (v0.66.0, this run)

- **Friendly labels on the last jargon-bare editor dropdown (denoise Method)** — the
  Noise-reduction op's Method enum was the only editor dropdown still showing raw
  engine ids ("wavelet" / "tv" / "bilateral"); every other enum already had friendly
  `option_labels`. Added them ("Wavelet (recommended)" / "Total-variation" /
  "Bilateral"), surfaced automatically in the op panel via the descriptor. Also added
  a drift-guard test asserting *every* editor enum param carries friendly labels for
  *all* its options, so a future enum op can't ship bare ids. Metadata + test only,
  additive. (v0.65.1, this run)

- **Show the Levels black/white points as guides on the histogram** — while setting
  the Levels op's black/white points a beginner couldn't see *where* on the tonal
  range they land (relative to the sky peak / the highlights they clip). When a
  `tone.levels` op is selected, the editor histogram now overlays two solid vertical
  guides ("B"/"W") at the current black/white points, plus faint dashed blue markers
  at the data-driven suggestion (only where it differs from the current value), with
  a one-line caption explaining them. Pure, testable `levelsHistGuides` helper drives
  it; the `Histogram` component grew an optional `guides` prop. Frontend-only,
  additive, advisory. Vitest: helper (5 cases: none/non-Levels/current-only/
  suggestion-diff/both-diff) + an Editor test that the caption appears only once the
  Levels op is selected. (v0.65.0, this run)

- **Single-click "Auto levels" on the Levels op** — the data-driven Levels buttons
  (v0.62.0) were per-point, so auto-levelling a beginner's image took *two* clicks
  (black, then white). The Levels op-panel header now shows one "Auto levels
  (black–white)" button that applies *both* suggested points at once, from the same
  already-fetched `levels-suggestion` payload — so the common case is a single
  click. The per-param "From your image" buttons stay for fine control (and read as
  already-applied ✓ once Auto levels sets them). Frontend-only, additive; reuses the
  existing endpoint + `setParams`. Vitest: one click leaves both per-param buttons
  disabled/✓ (proving black *and* white were set together). (v0.64.0, this run)

- **Editor: accurate data-driven value labels (Levels buttons + Auto's crossfaded
  sharpen strength)** — two small honesty fixes on data-driven readouts. (1) The new
  Levels "From your image" buttons each set only their *own* point, but both showed
  "From your image (black X, white Y)", implying each sets both; each now names just
  the value it applies ("black X" / "white Y"). (2) Now that the Auto crossfade
  (v0.63.0) eases the sharpen *amount* below its full 0.5 on noisier stacks, the
  "Tuned to your data" note surfaces that strength alongside the radius ("sharpen
  radius 1.4 px (strength 0.3)") when reduced — so the note reflects the crossfade's
  new adaptivity. Frontend-only, additive. Vitest updated (distinct Levels labels;
  the eased-sharpen value phrase; full-strength case unchanged). (v0.63.1, this run)

- **Smooth the Auto recipe's noisy/clean cliff (denoise ↔ sharpen crossfade)** —
  `auto_recipe` treated `analyze_proxy`'s `noisy` verdict as a hard boolean
  (`sky_sigma > 0.02`), so a stack just over the line got denoise and *no* sharpen
  while one just under got sharpen and *no* denoise — two near-identical stacks
  producing visibly different one-click results. The two now *crossfade* across a
  band around the old threshold (`_noise_fraction`, 0.012–0.028): denoise strength
  (still data-driven from the measured noise) fades in and the sharpen amount fades
  out as σ rises, so a mildly-noisy stack gets a light touch of *both*. The clean
  end (sharpen only) and very-noisy end (denoise only) are unchanged, and an
  unmeasurable image falls back to sharpen-only as before. Auto is an explicit
  button, so no default flips. Engine-only, additive. Tested: `_noise_fraction`
  endpoints + monotonicity, and that a mid-band stack carries both ops with denoise
  rising / sharpen falling across the band; existing adapts-to-noise and
  strength-scaling tests still green. (v0.63.0, this run)

- **One-click "From your image" black/white points for the Levels op** — the Levels
  op made a beginner hand-guess a black point and a white point, when the natural
  values come straight from the image's own histogram. The Levels param panel now
  offers a data-driven "From your image (black X, white Y)" button on both the
  black and white sliders (mirroring the sharpen/denoise/star-size buttons), driven
  by a new pure `seestack/edit/levels.py:suggest_levels_points` helper (p1 of the
  finite sky → black, p99.5 → white, NaN-aware, clamped, and returns `None` when the
  range would collapse — the v0.61.12 degenerate case) and a `…/editor/levels-suggestion`
  endpoint that measures the percentiles on the display-space image *entering* that
  op (all prior ops applied, so the values are correct post-stretch; falls back to
  dropping the Levels op(s) when the uid is stale). Engine + one endpoint + frontend;
  additive/upgrade-safe. Tested: engine helper (5 cases), webapp (valid pair on a
  stretched image + unknown-uid fallback), Vitest (the black button shows the
  measured value and reads as applied after a click). (v0.62.0, this run)

- **Test the PNG-render path also surfaces failed ops** — coverage follow-up to the
  v0.61.11 export-error surfacing: added a webapp test that a full-res PNG render
  (the download path, `submit_editor_png`) with a monkeypatched-to-fail op reports
  the failure in its job `op_errors`, matching the export-run path already covered.
  Test-only. (v0.61.14, this run)

- **Warn about a degenerate Levels op (empty black↔white range)** — companion to
  the v0.61.12 engine guard: since a Levels op with `white ≤ black` is now silently
  treated as identity, the pipeline panel shows an orange advisory ("A Levels op has
  its white point at or below its black point, so its range is empty — it does
  nothing.") with a one-click "Reset the black & white points" that restores the
  0..1 range — so the guard doesn't leave the user staring at a control that
  quietly does nothing (mirrors the double-stretch advisory). Pure
  `degenerateLevelsUids` helper drives it; frontend-only, additive. Vitest: helper
  (5 cases: white<black / white==black / healthy / disabled / non-Levels) + an
  Editor test that the warning shows and clicking the fix clears it. (v0.61.13,
  this run)

- **Guard the Levels op against a degenerate (white ≤ black) range** — the Levels
  op's black-point and white-point are independent 0..1 sliders, so a beginner can
  drag the white point down to or below the black point. That collapses the range
  (`rng` was floored to `1e-6`) and hard-thresholds every pixel to pure black/white
  — silently binarising the picture with no error, the same class of foot-gun as
  the single-point Curves case (v0.61.10). `_levels` now returns the input
  unchanged (identity) when `white - black < 1e-3`, so a mis-set slider can't
  destroy the image. Engine-only, additive/upgrade-safe. Regression test covers the
  inverted (white < black) and equal (white == black) cases (identity + NaN border
  preserved). (v0.61.12, this run)

- **Surface failed ops on export, not just in the live preview** — the preview /
  histogram paths collect per-op failures into `errors` and show them under the
  image, but the full-res export path (`_render_recipe_fullres`) only *logged* a
  failed op and dropped it silently, so an op that fails on the full-res data (but
  worked on the proxy, or vice versa) changed the exported look with no notice.
  `_render_recipe_fullres` now appends each failure (same `label: Type: msg` format
  as the preview) to an `errors` list threaded into both the export-run and PNG job
  results as `op_errors`; the editor polls the job and shows an orange "N operations
  failed and were skipped in the exported image: …" notification (pure
  `opErrorsMessage` helper) on both the export and full-res-PNG paths. Reuses the
  best-effort try/except; additive/upgrade-safe (new result field). Tested: webapp
  (a monkeypatched-to-fail op surfaces in the export job's `op_errors`; a clean
  recipe reports `[]`) + Vitest helper (4 cases). (v0.61.11, this run)

- **Fix stale/misleading maintainer comments & docstrings** — three inaccuracies a
  future maintainer would trust: the `edit_coverage_map` endpoint docstring still
  said "Grayscale … white = most frames" though it renders a viridis heatmap
  (yellow = most); the CurvesWidget top comment said "click empty space to add a
  point" when adding is bound to double-click (the visible help text was already
  correct); and the registry docstring claimed `apply_recipe` is "the source of
  truth for ordering" when it executes ops in recipe order and does **not** reorder
  by stage. Corrected all three. Comment/docstring-only, no behaviour change.
  (housekeeping, this run)

- **Guard the Curves op against a degenerate (blank-the-image) curve** — a tone
  curve with a single control point (or all-equal x) makes `np.interp` return a
  constant, blanking the whole image to a flat tone. The CurvesWidget can't produce
  that (endpoints are locked), but a hand-built or `base64`-encoded recipe / preset
  could, with no error. `_curves` now returns the input unchanged (identity) when
  the curve has fewer than two points spanning a range of x, so a degenerate recipe
  can't silently destroy the picture. Engine-only, additive. Regression test covers
  the one-point and flat-x cases (identity + NaN preserved). (v0.61.10, this run)

- **Expose the Rotate op's `expand` control (was a dead read)** — `geometry.rotate`
  read `params.get("expand", True)` but never registered an `expand` param, so the
  reshape-vs-crop behaviour was uncontrollable: every rotated export always grew
  the canvas with black corners, with no way to keep the original size. Registered
  an `expand` bool param (default True = current behaviour, surfaced automatically
  in the op panel via the descriptor), so a user can now turn it off to keep the
  frame size and let the rotated corners fall outside. Engine-only, additive/
  upgrade-safe (default preserves old behaviour). Regression test asserts the param
  is exposed and actually toggles the output canvas size. (v0.61.9, this run)

- **Warn about a redundant second Stretch (double-stretch bug)** — `apply_recipe`
  marks the pipeline stretched on *every* `is_stretch` op and never dedupes, so two
  enabled Stretch ops both run — the second re-stretches already display-space data
  and washes the image out (flat/dark). A beginner hits it by running Auto-process
  or a preset (both include a stretch) then clicking "Add operation → Stretch" to
  "tune" it, with no warning. The pipeline panel now shows an orange advisory when
  more than one Stretch is enabled, with a one-click "Disable the extra stretch(es)"
  that keeps only the first (via a pure `extraEnabledStretchUids` helper). Advisory
  + one-click, frontend-only, additive. Vitest: helper (4 cases: single/multi/
  disabled/first-enabled) + an Editor test that the warning shows and clicking the
  fix clears it. (v0.61.8, this run)

- **Show the proposed trim over the coverage heatmap** — when the user opened the
  "Trim border" preview (v0.61.4) the dashed crop drew over whatever overlay
  happened to be up (usually the plain edited image), so you couldn't see that it
  lands on the well-covered interior. Entering trim preview now auto-shows the
  coverage heatmap (v0.61.3) on a mosaic (remembering the prior overlay state so
  Cancel/Apply restores it), and the two top-left captions are de-conflicted: the
  generic overlay label is suppressed during trim preview and the crop caption
  reads "Proposed crop over coverage — keeps the central W% × H%". Frontend-only,
  additive, advisory. Vitest: entering trim preview flips the overlay to "Hide
  coverage" + the over-coverage caption, and Cancel restores it. (v0.61.7, this run)

- **Show render progress for the full-res PNG download** — "Download full-res PNG"
  polls the render job to completion but only spun the button, so on a large mosaic
  (the slowest editor action) it read as "stuck" with no signal it was working. The
  editor now shows a live "Rendering — NN%" line under the button while the job
  polls, from the job's `phase`/`done`/`total` via a pure `pngProgressLabel` helper
  (percentage when the total is known, phase name otherwise). Frontend-only,
  additive. Vitest: helper (percent / clamp / phase-fallback / blank / null) + an
  Editor test that the progress line shows while the job polls. (v0.61.6, this run)

- **Note the coverage overlay is for the uncropped frame when a crop is applied** —
  the coverage-map overlay (v0.61.0) renders the run's *raw* full-frame coverage
  sibling, so once a `geometry.crop`/rotate/resize op is in the recipe (very likely
  now that "Trim border" adds one) the overlay no longer lines up with the reshaped
  preview — the coverage looked larger/offset vs the cropped image with no
  explanation. The overlay label now reads "Coverage map — shown for the uncropped
  frame" whenever an enabled geometry op is present, via a pure `hasEnabledGeometryOp`
  helper. Honest, additive, frontend-only. Vitest: helper (enabled/disabled/
  non-geometry) + the Editor caption with a crop in the recipe. (v0.61.5, this run)

- **Preview the "Trim border" rectangle before committing** — the one-click "Trim
  border" (v0.60.0) applied a `geometry.crop` immediately, so a user who didn't like
  the auto-crop had to undo. "Trim border" now first draws the *proposed* crop as a
  dashed magenta outline over the preview (with the area outside dimmed and a
  "Proposed crop — keeps the central W% × H%" caption), and the toolbar shows
  **Apply crop** / **Cancel** — nothing changes until Apply, which commits the Crop
  op and selects it (as before). Fractional `trim-suggestion` bounds map straight to
  image-space percentages via a pure `trimRectStyle`/`trimKeptLabel` helper. Builds
  trust in the auto-crop and avoids an undo round-trip. Frontend-only, additive.
  Vitest: helpers (pct mapping + kept-label) and the Editor preview→Apply flow
  (dashed caption shows, no Crop op until Apply). (v0.61.4, this run)

- **Colour heatmap + legend for the coverage overlay** — the coverage-map overlay
  (v0.61.0) rendered grayscale, which read slowly and looked much like the star
  mask. A new pure engine `seestack/render/colormap.py` (viridis LUT, no matplotlib
  dependency) now colours the normalized coverage — dark blue = fewest frames →
  yellow = most — so the gradient is legible at a glance and visually distinct from
  the grayscale star mask. The editor adds a small "fewer ↔ more frames" gradient
  legend under the preview whenever the coverage overlay is up. Engine + one
  endpoint + frontend; purely cosmetic/additive (PNG shape unchanged: still a
  same-size image, now RGB). Tested: engine colormap (LUT endpoints, brightness
  monotonicity, NaN/out-of-range clamp), Vitest asserts the legend caption shows
  with the overlay. (v0.61.3, this run)

- **Fix a flaky Stack-form vitest ("does not suggest min/max reject when already
  on")** — the test waited only for the schema-driven "Min/max rejection" *label*
  before asserting the streak nudge was absent, but the nudge is suppressed by the
  `getStackDefaults` value (`min_max_reject: true`) which resolves in a *separate*
  query — so between the two queries the switch reads off and the nudge shows
  transiently, racing the negative assertion (it took down main's CI on the prior
  merge, though the code was fine). Now it waits for the switch to actually read
  *checked* (defaults applied) before asserting the nudge is gone — same assertion,
  no race. Test-only; keeps CI reliable. (v0.61.2, this run)

- **"Trim border" selects the new Crop op + reports the kept fraction** — polish on
  the v0.60.0 trim feature: applying "Trim border" now selects the resulting
  `geometry.crop` op (so its adjustable bounds panel opens immediately — making
  clear it's a normal op the user can fine-tune or remove, not a baked-in change)
  and the confirmation names how much is kept ("keeps the central 78% × 85%") for
  trust. Frontend-only, additive; Vitest asserts the crop op is selected after the
  trim. (v0.61.1, this run)

- **Coverage-map overlay in the editor (mosaic trust/explain)** — a Seestar
  mosaic's ragged edges, the "Trim border" crop (v0.60.0) and the "Coverage
  leveling" op all act on the per-pixel frame-coverage map, but the user had no
  way to *see* it. A `…/editor/coverage-map` endpoint renders the run's coverage
  sibling (strided to the preview proxy so it lines up with the shown image) as a
  grayscale PNG — white where the most frames overlap, black at the uncovered
  edges/gaps — and the editor adds a "Coverage" overlay toggle (next to Star mask)
  shown **only on a mosaic** (`is_mosaic`), mutually exclusive with the other
  overlays. So a beginner can look at exactly what "Trim border" and "Coverage
  leveling" are addressing. 404 (no button) on a single-field stack. Engine +
  one endpoint + frontend; additive/upgrade-safe. Tested: webapp (PNG on a
  mosaic / 404 without a sibling), Vitest (button shows + toggles on a mosaic,
  hidden on single-field). (v0.61.0, this run)

- **One-click "Trim to well-covered area" for mosaics** — a Seestar mosaic's union
  canvas has ragged, low-coverage edges (single-frame corners, NaN gaps) that look
  messy and are noisier than the well-covered interior, and trimming them by hand
  means fiddling four fractional crop sliders. A new pure `largest_covered_rect`
  engine helper finds the largest axis-aligned rectangle whose pixels are all well
  covered (coverage ≥ a fraction of the peak; NaN counts as uncovered) via the
  classic O(h·w) maximal-rectangle sweep, returning fractional bounds or `None`
  when there's nothing worth trimming (uniform/single-field coverage, or an
  already-full-frame result). A `…/editor/trim-suggestion` endpoint strides the
  run's coverage sibling down (≤512 px) and runs it, offered **only** on a mosaic
  (`coverage_max > coverage_min`); the editor shows a "Trim border" button that
  sets/updates a `geometry.crop` op to that rectangle (pure `applyTrimCrop` helper —
  updates an existing crop in place rather than stacking duplicates). Off-by-default
  risk nil (explicit button; the crop op is visible and removable). Engine + one
  endpoint + frontend; additive/upgrade-safe (no on-disk change). Tested: engine
  helper (7 cases: uniform/none/ragged-interior/NaN-hole/full-frame/clamp), webapp
  (mosaic crop / single-field no-op / missing sibling), Vitest (helper 5 cases +
  Editor: button shows on a mosaic and adds a Crop op, hidden on single-field).
  (v0.60.0, this run)

- **Highlight/shadow clipping warning in the editor** — over-stretching is the
  classic beginner mistake: push the stretch/levels too far and star/nebula cores
  blow out to pure white or the sky crushes to pure black, losing detail
  irreversibly on export. The editor's live histogram clips values into [0, 1], so
  a pure `clippingCaption` helper measures the fraction of pixels piled in the top
  bin (blown white) and bottom bin (crushed black) across r/g/b and, above tuned
  thresholds (highlights 2% — reliable/most-damaging; shadows 35% — conservative to
  avoid nagging on legitimately dark skies), shows a subtle orange caption under the
  preview ("Highlights are clipping — about 4% of pixels are pure white. Ease the
  stretch or lower the white point…"). Advisory only, changes nothing; teaches good
  stretch discipline on the priority-1 editor. Pure helper Vitest-covered (7 cases:
  thresholds each side, both-clip, worst-channel, null-safety) + an Editor wiring
  test; frontend-only, additive. (v0.59.4, this run)

- **Explain the editor's TIFF export mode** — the Export panel's "TIFF" dropdown
  offered the raw values "linear" / "autostretch" with no explanation, so a
  beginner couldn't tell which to pick or that it only affects the .tiff file. It
  now shows friendly labels ("Linear" / "Auto-stretched") and an info-tooltip on
  the label explaining Linear keeps raw unstretched data for editing elsewhere,
  Auto-stretched bakes in a display stretch so the file looks right when opened
  directly, and the FITS/PNG outputs are unaffected. The stored values are
  unchanged (still "linear"/"autostretch"), so the export API is untouched.
  Copy/label-only, frontend, additive. (v0.59.3, this run)

- **Built-in presets prepend Coverage leveling on a mosaic** — a built-in preset
  (Galaxy / Nebula / Star cluster) carries a fixed op list that can't know whether
  *this* stack is a mosaic, so applying one on a Seestar mosaic left the panel steps
  in. Applying a **built-in** preset now prepends a `background.level_coverage` pass
  (the same one Auto-process adds, v0.59.0) when the run is a mosaic — reusing the
  histogram's `is_mosaic` flag (v0.59.1) — on top of the existing data-driven size
  seeding, so a built-in preset lands both sized to your data and mosaic-aware.
  Single-field stacks and **user-saved** presets are unchanged (applied exactly as
  tuned). Pure `prependCoverageLeveling` helper (no-op when not a mosaic, op absent,
  or a leveling pass is already present, so re-applying never duplicates);
  frontend-only, additive. Vitest-covered (helper: 5 cases; editor: preset apply on
  a mosaic leads with the pass). (v0.59.2, this run)

- **Tell the user when "Coverage leveling" will do nothing** — the op only
  equalises panels on a multi-coverage mosaic; on a single-field stack (uniform
  coverage) it's a deliberate no-op, so a beginner who added it saw no effect and
  no explanation. The histogram endpoint now reports `is_mosaic` (the run's
  `coverage_max > coverage_min`), and when the `background.level_coverage` op is
  selected on a non-mosaic run the editor shows a subtle grey "No effect on this
  stack — it's a single-field image… this op equalises mosaic panels" note, so the
  control explains its own applicability instead of silently doing nothing. Pairs
  with the v0.59.0 auto-add-for-mosaics autonomy change. One additive API field +
  frontend; upgrade-safe. Tested: webapp asserts `is_mosaic` on the histogram;
  Vitest asserts the note shows on a single-field run and is absent on a mosaic.
  (v0.59.1, this run)

- **Auto-add Coverage leveling to the Auto recipe for mosaics** — now that the
  "Coverage leveling" op works (v0.58.6), one-click Auto-process detects a mosaic
  (the run row's `coverage_max > coverage_min`, i.e. uneven panel overlap) and
  prepends `background.level_coverage` on linear data — before the gradient fit and
  the stretch — so a Seestar mosaic gets flat, step-free panels without the user
  ever discovering the op exists. A single-field stack (uniform coverage) and an
  unknown span leave the recipe unchanged (the pass would be a no-op there anyway).
  The run's coverage span is threaded into `auto_recipe` (mirroring how
  `median_fwhm` is already threaded for the sharpen radius). Auto is an explicit
  button, so no default flips. Engine + one endpoint thread, additive/upgrade-safe.
  Tested: mosaic prepends & orders the pass before gradient/stretch; single-field
  and unknown span omit it. (v0.59.0, this run)

- **Fix: "Coverage leveling" editor op was a permanent silent no-op** — the
  Background-group "Coverage leveling" control (equalises sky across mosaic panels
  with different frame coverage — a core Seestar mosaic case) read `ctx.coverage`,
  but `EditContext.coverage` was *never* populated anywhere in production (preview,
  histogram, or export), so the op returned its input unchanged for every user: a
  guaranteed dead control. Each stack run already writes a sibling
  `{basename}_coverage.fits`; a new `load_coverage` helper reads it (striding it to
  the proxy step so the preview lines up with the full-res export), and the export
  (`_render_recipe_fullres`), preview and histogram paths now feed it into
  `EditContext.coverage`. Added a shape-mismatch guard so a prior geometry op
  (crop/resize) makes the op skip cleanly instead of crashing the render. Engine +
  webapp wiring, additive/upgrade-safe (no on-disk change; None → the existing
  no-op for single-field images). Tested: `load_coverage` load/stride/None, the
  webapp `_proxy_coverage` wiring, and the new shape-guard. (v0.58.6, this run)

- **Fix: star-mask overlay ignored the op's star size (always the default 4 px)** —
  the editor's "Star mask" overlay exists so a beginner can see what the star ops
  (`stars.reduce` / `stars.boost_nebula`) treat as stars while tuning "Star size",
  and the endpoint already accepts a matching `size_px` — but the frontend never
  passed it and the query key had no size, so raising Star size never moved the
  overlay: it silently misrepresented what the op would gate. The overlay is now
  sized from the *selected* star op (`2·size` for reduce, `size` for boost-nebula,
  matching the ops' own gate) via a pure `starMaskSizePx` helper, and the size is in
  the query key so it refetches on change; a non-star (or no) selection falls back
  to the endpoint default. Helper Vitest-covered (5 cases) + the overlay wiring
  test; frontend-only, additive. (v0.58.5, this run)

- **Fix: star-reduction over-shrank stars in the live preview vs export** — the
  `stars.reduce` op scaled its star-mask *gate* for the decimated preview proxy
  (via `star_mask(..., ctx)`) but built its grey-erosion footprint from the raw
  full-res `size`, so on a big image (`proxy_scale`≈4) the footprint covered ~4×
  more scene in the preview than the export delivered — the preview pulled star
  cores down harder than the exported result, a WYSIWYG/parity violation (the same
  class of bug fixed for sharpen/denoise/background in v0.56.19/v0.57.1). The
  footprint now shrinks by `ctx.scaled_px(size)` exactly like the mask, a no-op on
  export so the exported image is byte-for-byte unchanged. Engine-only, additive;
  monkeypatched-footprint test proves the erosion side-length shrinks 9→5→3 as
  proxy_scale goes 1→2→4. (v0.58.4, this run)

- **Auto-suggest the min/max reject count (k) from the streaked-frame count** — with
  min/max reject on, the default k=1 drops only the single worst extreme per pixel, so
  a session with several satellite/plane trails leaves the rest in the result. The
  Stack form now shows a blue advisory when ≥2 accepted frames are streaked and the
  current k is below the streak count, suggesting `k = min(N_streaked, 5,
  ⌊(n−1)/2⌋)` (capped so it never over-shoots the frame budget and trips the
  too-high warning) with a one-click "Set k = N". Reuses the per-frame streak QC;
  suggestion-only, frontend-only, additive. Vitest-covered (suggests at 3 streaks,
  caps at the frame budget, no-fire for a single streak). (v0.58.3, this run)

- **Warn when the min/max reject k is too aggressive for the frame count** — the
  top/bottom-k trim (v0.58.0) applies its full k-drop only where a pixel is covered
  by ≥ 2k+1 frames, silently degrading to a single min/max drop below that. The
  Stack form now shows a yellow advisory (mirroring the small-stack min/max nudge)
  when `min_max_reject` is on with `min_max_reject_count>1` and `2·k+1 >
  accepted+solved`, explaining it needs at least `2k+1` frames per pixel and will
  mostly fall back to a single drop, with a one-click "Lower k to N" that sets k to
  the largest value the stack can fully apply (`⌊(n−1)/2⌋`). Reuses the frame-count
  the form already has; advisory-only, frontend-only, additive. Vitest-covered
  (fires at k=3/6-frames, one-click lower, no-fire at k=3/8-frames). (v0.58.2,
  this run)

- **Show the k-count in the rejection badge for a top/bottom-k trim** — follow-on to
  v0.58.0: the `RejectionBadge` on History/Gallery/Compare cards derives the combine
  method from a run's stored options, so a stack combined with `min_max_reject_count>1`
  now reads "min-max ×3" (with a tooltip explaining it dropped the 3 highest and
  lowest per pixel) instead of a bare "min-max", while the default single drop and
  old runs (no count stored) still read "min-max". Reuses the already-serialised
  option; Vitest-covered (×3 label + default/explicit-1 stays plain); frontend-only,
  additive. (v0.58.1, this run)

- **Top/bottom-k trimmed-mean reject** — generalised `MinMaxRejectAccumulator` to
  drop the *k* smallest and *k* largest per pixel via an opt-in
  `StackOptions.min_max_reject_count` (default 1 = exactly today's single min/max
  drop), so multiple satellite/plane trails crossing one pixel across a session
  (k=3 → up to 3 trails) are removed where a single-extreme drop left two behind.
  Stays single-pass and memory-bounded: k sorted min-planes and k max-planes
  (`2 + 2k` canvas planes) updated by a vectorised insertion (min/max bubble), the
  full k-trim applied only where `count ≥ 2k+1` (the two sides are then disjoint
  with a middle), degrading to the proven single min/max drop for `3 ≤ count < 2k+1`
  and a plain mean below 3 — so k=1 is byte-identical to before. `_estimate_peak_bytes`
  / the memory guard now charge the extra `2k` planes (`_min_max_reject_arrays`) so a
  big k can't slip past the OOM guard. Descriptor-driven Stack-form control
  (advanced, `depends_on=min_max_reject`, bounds 1–5) surfaces it automatically.
  Unit-tested (k=3 trim / three-trail kill / <2k+1 degrade / NaN+tie / windowed /
  k=1-identity), guard-tested (k=3 refused where k=1 fit), and end-to-end. Additive/
  upgrade-safe (new field defaults 1). (v0.58.0, this run)

- **"slower preview" chip in the Add-operation menu** — the `heavy` spec hint
  (v0.57.17) was only consumed by the preview debounce; now the Add-operation menu
  (both the curated Common section and the full grouped list) shows a small "slower
  preview" chip next to each heavy op (Deconvolution / Noise reduction), so a
  beginner knows *before* adding the op why its live preview will update after a
  beat rather than instantly — setting the expectation up-front instead of leaving
  them wondering if it's stuck. Reuses the already-threaded `heavy` field via a
  shared `SlowPreviewChip`; Vitest-covered (chip shown in the menu); frontend-only,
  additive. (v0.57.22, this run)

- **Retire the now-dead "export only" preview scaffolding → "slower preview"** —
  since v0.57.0 *every* editor op is `proxy_safe=True`, so the OpList "export only"
  badge and the selected-op "The live preview doesn't show this effect" note (both
  gated on `!proxy_safe`) were unreachable and, worse, stale (they'd lie if an op
  were ever re-marked non-proxy-safe). Repointed both at the live `heavy` spec hint
  (v0.57.17): the row now shows a "slower preview" chip and the note explains the
  preview updates *after a short pause* (matching the adaptive debounce) rather than
  falsely claiming the effect never shows. Accurate copy, one fewer foot-gun on the
  priority-1 editor. Vitest case repointed (badge + note); frontend-only, additive.
  (v0.57.21, this run)

- **NaN-preservation regression tests for the spatial detail ops** — the
  denoise / sharpen / deconvolve ops run on a NaN-filled copy (skimage can't
  tolerate NaN) and restore the uncovered border via `_with_nan_filled`; that
  fragile fill→process→restore contract had no direct guard (the same class of
  gap that let the hot-pixel op regress). Added a parametrized
  `test_detail_ops_preserve_nan_on_partial_coverage` asserting each keeps an
  uncovered mosaic border NaN and never leaks NaN into (or a filled value out of)
  the covered region. Test-only; confirmed all three already correct. (v0.57.20,
  this run)

- **Fix: hot-pixel editor op silently did nothing on mosaic (NaN) images** — the
  editor's `detail.hot_pixels` op called `suppress_hot_cold_pixels` directly, which
  derives its outlier threshold from the median of the whole-image residual; with
  any uncovered (NaN) pixel that median is NaN, so the threshold went NaN, every
  `|residual| > NaN` comparison was False, and the op became a silent no-op on
  *every* mosaic/partial-coverage stack (a Seestar owner adding hot-pixel removal
  to a mosaic edit got nothing, with no error). Wrapped it in the same
  `_with_nan_filled` helper the other detail ops (denoise/sharpen/deconvolve) use,
  so it fills NaN with the finite median, suppresses on the clean array, and
  restores NaN — now it removes hot pixels on mosaics *and* preserves the uncovered
  border. Engine-only, editor-scoped (the shared stack-path function is untouched);
  regression test covers mosaic-NaN + fully-covered. (v0.57.19, this run)

- **Show Auto's chosen data-driven values in the "What Auto-process did" note** —
  the note listed *which* ops Auto ran but not the *values* it picked from your
  data, which is exactly where Auto's adaptivity lives. A pure `autoValueSentence`
  helper reads the built recipe's op params directly (no new API) and adds a second
  line — "Tuned to your data: sky level 0.2, saturation 1.1×, sharpen radius 1.4 px"
  — for the STF sky level, denoise strength, saturation and sharpen radius, skipping
  any op whose value isn't present so it degrades gracefully. Turns "it did
  something" into "it did *this, because of my data*". Vitest-covered (7 helper
  cases + the Editor note-wiring test asserts the values line); frontend-only,
  additive. (v0.57.18, this run)

- **Adaptive live-preview debounce for heavy editor ops** — dragging a slider
  while an expensive op (deconvolution, wavelet denoise) is in the pipeline still
  kicked a full proxy render on every 250 ms debounce step, so several slow
  intermediate frames rendered before the value you landed on. Ops now carry a
  `heavy` spec hint (set on `detail.denoise` / `detail.deconvolve`, threaded to the
  frontend via the ops schema), and a pure `previewDebounceMs(ops, specs)` helper
  stretches the editor's preview debounce to 600 ms whenever an *enabled* heavy op
  is present — so only the value you settle on renders — while light-only recipes
  keep the snappy 250 ms. Vitest-covered (6 cases incl. disabled-op and
  missing-`heavy` graceful degrade) + a backend assertion that the schema exposes
  `heavy`. Additive/upgrade-safe (new optional field defaults false). (v0.57.17,
  this run)

- **Data-driven saturation in the one-click Auto recipe** — Auto's final
  saturation boost was a fixed `1.2` for every stack, but chroma noise scales with
  the boost, so on a noisy Seestar stack that fixed lift just amplified colour
  speckle. Auto now scales the saturation to the measured background noise
  (`analyze_proxy`'s `sky_sigma`) — a clean stack gets the full `1.25` lift, a
  noisy one eases down toward `1.05` — with a neutral `1.2` fallback when the proxy
  can't be measured. Completes the "adapt every knob to the data" pattern already
  applied to Auto's denoise strength, sharpen radius and STF target. Engine-only,
  additive; Auto is an explicit button so no default flips. Test asserts the boost
  is gentler on a noisy stack than a clean one and falls back to 1.2. (v0.57.15,
  this run)

- **"Your data" context chip in the editor header** — the four data-driven
  suggestion buttons quote their measured value inline ("FWHM 3.2px"), but there
  was no single place a user could see what the editor measured about *this* stack.
  A small dimmed chip under the title ("Measured: stars ≈ 3.2 px FWHM · background
  noise σ 0.021") — built from the already-fetched psf/sharpen/star-size (`fwhm_px`)
  and denoise (`noise_sigma`) queries via pure `coalesceFwhm` / `measuredContextText`
  helpers — gives the data-driven buttons visible provenance and builds trust,
  shown (with an explanatory tooltip) only when at least one measure is available.
  Pure helpers Vitest-covered (8 cases) + an Editor render test; frontend-only,
  additive. (v0.57.14, this run)

- **Keep the old preview + "Updating…" badge while re-rendering (editor
  responsiveness)** — on every (debounced) edit the live-preview query key changes,
  so react-query dropped `preview.data` to `undefined` and the panel flashed to a
  black `<Loader>` before the new render arrived — a jarring blink on every slider
  drag, and no signal that a render was underway. Added `placeholderData:
  keepPreviousData` so the previous render stays visible while the next one loads,
  plus a small "Updating…" overlay badge (shown only when a render is in flight and
  an image is already up) so the momentarily-stale image reads as "refreshing", not
  "stuck". Pairs with this run's superseded-render abort. Vitest-covered (the old
  image persists and the badge appears while a render pends). Frontend-only,
  additive. (v0.57.16, this run)

- **Cancel superseded live-preview renders (editor responsiveness)** — the live
  preview refetches on every debounced param change, but the four blob `fetch`
  queries (preview, base, star-mask, without-op) and the histogram query never
  passed react-query's `AbortSignal`, so while a user dragged a slider on a heavy
  op each stale render ran to completion server-side and the newest result queued
  behind them — the named "heavy ops on the proxy can lag" hold-out of the
  live-preview item. Threaded the query `signal` into every `fetch(url, { signal })`
  and into `api.getHistogram(..., signal)` (which already accepted a `RequestInit`
  via `req`), so a superseded request aborts the moment the recipe changes, cutting
  proxy render backlog and latency. Vitest-covered (the preview fetch is called with
  an `AbortSignal`). Frontend-only, additive, no API change. (v0.57.13, this run)

- **Direct pixel-transform + NaN-safety tests for the tone/colour editor ops** —
  `seestack/edit/ops/tone.py`'s ops (SCNR, saturation, white balance, curves,
  levels) had no dedicated pixel-level test: the engine test only exercised a full
  recipe end-to-end, so each op's own param-forwarding and NaN handling was
  unguarded. Added `tests/test_edit_tone_ops.py` (11 cases) asserting each does the
  transform its params ask for (SCNR caps excess green to the R/B neutral and never
  *adds* green; saturation spreads channels around luminance with a true identity
  at 1.0; white balance applies per-channel gain; curves/levels identity + midtone
  lift) **and** leaves an uncovered NaN border as NaN — closing a coverage gap on
  the priority-1 editor and locking in the "gaps never become a black wedge"
  invariant. Confirmed all five are already correct; test-only, no code change.
  (v0.57.12, this run)

- **Built-in presets land sized to your data** — the built-in editor presets
  (Galaxy / Nebula / Star cluster) carried *generic* default sizes for their
  data-scalable ops (Galaxy's sharpen `radius=2.0`, Star-cluster's `stars.reduce
  size=2`), the same fixed guesses the one-click Auto recipe already outgrew.
  Applying a **built-in** preset now seeds those data-driven params (sharpen
  radius, star size) from this target's own median star FWHM via the same
  `applyDataDrivenDefaults` helper as the "Use data defaults" toolbar action, so a
  preset lands sized to what you actually shot. **User-saved** presets are applied
  exactly as the user tuned them (a new `source` arg on `PresetMenu.onApply`
  distinguishes the two). Reuses the already-fetched suggestion queries;
  frontend-only, additive. Vitest-covered end-to-end (applying the Galaxy preset
  seeds its sharpen radius to the measured value). (v0.57.11, this run)

- **"Apply data-driven defaults" one-click on the editor** — a user hand-building
  a recipe previously had to open each of the four suggestion-carrying ops
  (Deconvolution, Noise reduction, Sharpen, Star reduction) and click its "From
  your data" button individually. The editor toolbar now shows a single "Use data
  defaults (N)" button that seeds every *present* op's data-driven param (PSF σ,
  denoise strength, sharpen radius, star size) from the already-fetched
  suggestions in one click. It's shown only when at least one present op still
  diverges from its measured value (so it never nags once everything's applied),
  and N counts how many ops would change. Pure `applyDataDrivenDefaults` /
  `countDataDrivenDefaults` helpers (no mutation) drive it; Vitest-covered (helper:
  8 cases; editor: button appears, applying it makes it disappear). Frontend-only,
  additive, explicit-button (off by nothing). (v0.57.10, this run)

- **Dim the "From your data" suggestion button when the param already matches** —
  the editor's four data-driven suggestion buttons (PSF σ, sharpen radius, denoise
  strength, star size) always looked clickable, so while tuning a user couldn't
  tell whether the current value *was* the suggestion or had diverged. The
  `OpParamPanel` suggestion button now dims/disables and prefixes a "✓" (with an
  "already set to the value measured from your data" tooltip) when the param's
  current value already equals the suggested value within half the control's step,
  via a pure `matchesSuggestion` helper — so the button doubles as an "am I
  optimal?" indicator. Vitest-covered (helper: 5 cases; panel: disabled+✓ state);
  frontend-only, additive. (v0.57.9, this run)

- **Complete + enforce plain-language help on every editor control** — finished the
  help sweep by adding hints to the last bare params (geometry crop/rotate/resize,
  manual white-balance R/G/B gains, coverage-leveling σ), so *every* editor slider
  now shows a one-line explanation. The help-coverage test now asserts this as an
  invariant — every param must carry help except the curve-editor widget (which has
  op-level help) — so a future op can't ship a bare, unexplained control.
  Metadata + test only, additive. (v0.57.8, this run)

- **Plain-language help on the remaining jargon-bare editor sliders** — v0.56.17
  gave the detail/levels ops per-param help, but the commonly-used tone/star/
  background sliders still showed *no* hint under the control: `tone.saturation`
  amount, `tone.scnr` amount, `tone.color_calibrate` mode, `stars.reduce`
  amount/size, `stars.boost_nebula` amount, and `background.subtract` /
  `final_gradient` box_size/σ/dilate/mode. Added a one-line plain-language hint to
  each (what it does + a sensible starting point), plus friendly `option_labels`
  for the two background `mode` enums so the dropdowns read "Per channel" /
  "Luminance" instead of raw ids — surfaced automatically in the op param panel via
  the already-threaded `help`/`option_labels` fields. Metadata-only, additive; the
  help-coverage test now asserts every one of these params carries a hint.
  (v0.57.7, this run)

- **Data-driven sharpen radius in the one-click Auto recipe** — when Auto-process
  sharpens a clean stack it used a *fixed* `radius=2.0`, the same for a tight-star
  and a bloated-star image, even though v0.57.4 already ships the exact FWHM→radius
  conversion (radius ≈ the star's Gaussian σ) behind the editor's sharpen-from-stars
  button. The auto endpoint now threads the target's `median_fwhm()` into
  `auto_recipe`, which sizes the auto sharpen radius to the target's *own* stars
  (clamped to the op's 0.5–10 step/range), falling back to the neutral 2.0 when no
  frame carries an FWHM — so the one-click result sharpens the right detail scale
  instead of guessing. Test asserts the auto sharpen radius tracks the FWHM and
  falls back to 2.0; engine + one endpoint thread, additive/upgrade-safe.
  (v0.57.6, this run)

- **Star-size-from-stars suggestion for the star-reduce op** — the `stars.reduce`
  op's `size` param is a physical star-scale in px a beginner can't reason about,
  and QC already measures exactly that as the median star FWHM. A new
  `GET …/editor/star-size-suggestion` endpoint maps the target's median FWHM to an
  integer `size` (rounded, clamped to the op's 1–8 range), and the Star reduction
  op's param panel offers a one-click "From your stars (size X, FWHM Ypx)" button —
  the fourth data-driven button, mirroring the PSF-, sharpen- and denoise-from-data
  suggestions exactly. Backend tested (median/clamp/none cases); additive/
  upgrade-safe. (v0.57.5, this run)

- **Sharpen-radius-from-stars suggestion** — the editor's Sharpen op made the user
  hand-guess a radius, when the natural detail scale to enhance is the star's own
  blur, which QC already measures. A new `GET …/editor/sharpen-suggestion` endpoint
  converts the target's median star FWHM to a Gaussian σ (the same
  `FWHM/2·√(2·ln2)` the deconvolution PSF button uses), clamped to the op's
  0.5–10 slider range and rounded to its 0.5 step, and the Sharpen op's param panel
  offers a one-click "From your stars (radius X, FWHM Ypx)" button — mirroring the
  PSF-from-stars and denoise-from-image buttons. Also folds in a small polish: the
  editor's zoom lightbox title now carries the "preview is downscaled" note, since
  zoom is exactly where the proxy resolution surprises users. Backend tested
  (median/clamp/none cases); additive/upgrade-safe. (v0.57.4, this run)

- **Data-driven denoise strength in the one-click Auto recipe** — when Auto-process
  decides a stack is noisy it added a wavelet denoise at a *fixed* `strength=0.5`,
  the same for a barely-grainy stack and a very noisy one. It now scales that
  strength to the actual measured background noise via the existing
  `suggest_denoise_strength` estimator (the same one behind the editor's "From your
  image" one-click), so a mildly-noisy result gets a lighter touch and a very noisy
  one a firmer cut — with a neutral 0.5 fallback when the proxy can't be measured.
  Makes the one-click Auto result adapt to the data instead of guessing. Test
  asserts the auto denoise strength rises with noise level; engine-only, additive.
  (v0.57.3, this run)

- **"Preview is downscaled" hint in the editor** — the live preview always runs on
  a ≤1500 px proxy of what may be a 150 MP mosaic, so fine detail reads differently
  than the exported full-res image (even now that spatial ops are proxy-corrected).
  The histogram response now carries the proxy geometry (`proxy_scale`,
  `proxy_width/height`), and a pure `previewScaleCaption` helper turns it into a
  small dimmed caption under the preview ("Preview shown at 1500 px — export renders
  at full resolution (4.0× larger)."), shown only when the proxy is meaningfully
  downscaled (>1.05×) so small stacks that fit the proxy budget aren't nagged. Sets
  the right expectation and heads off "why does my export look different?"
  confusion. Pure helper Vitest-covered (5 cases); one additive API field.
  (v0.57.2, this run)

- **Preview↔export parity for the background ops** — v0.56.19 corrected the spatial
  *detail* ops for the decimated preview proxy, but `background.subtract` /
  `background.final_gradient` still fed full-resolution pixel measures (`box_size`,
  `dilate_px`) straight through, so their gradient mesh was estimated at a coarser
  physical scale in the preview than in the full-res export. A new `_scaled_box`
  helper divides those px measures by `EditContext.scaled_px()` (a no-op on the
  export, so the exported result is byte-for-byte unchanged), floored so
  `Background2D` still gets a sane box with a few cells across the small proxy —
  and `for_image_size` floors `subtract`'s box further so the mesh always tiles.
  As a bonus this also makes `final_gradient` behave better on the proxy (a 256 px
  box on a ≤1500 px proxy previously left barely one mesh cell). Monkeypatched-arg
  tests prove box_size (and final-gradient's dilate_px) shrink 1×→2×→4× with
  proxy_scale while the export stays at the param value. Engine-only, additive.
  (v0.57.1, this run)

- **Auto-process note clears when the recipe changes** — follow-up to v0.56.18's
  "What Auto-process did" note: it previously persisted (until dismissed) even
  after the user edited the pipeline, so it could describe ops that were no longer
  there. The editor now records the recipe signature right after Auto runs and
  drops the note the moment the pipeline diverges from it (manual edit, undo,
  redo), so it only ever describes the current auto result. Frontend-only;
  Vitest-covered (removing the auto op hides the note). (v0.56.20, this run)

- **Preview↔export parity for spatial detail ops** — the live preview runs on a
  striding-decimated proxy (≤1500 px), but the sharpen radius, bilateral-denoise
  spatial extent, etc. are in *full-resolution* pixels and ignored `proxy_scale`,
  so on a big image a `radius=2px` sharpen covered `proxy_scale`× more of the
  proxy than of the full-res export — the preview over-sharpened/over-smoothed
  relative to what you actually got. Added `EditContext.scaled_px()` (divides a
  full-res pixel measure by `proxy_scale`, no-op on the export where scale=1) and
  applied it to `detail.sharpen`'s radius and `detail.denoise`'s bilateral
  `sigma_spatial`, so the preview now sharpens/smooths the same physical detail as
  the export. Deconvolution is preview-skipped (`proxy_safe=False`) so it was
  already export-only. Unit-tested: `scaled_px` scaling + a monkeypatched-radius
  test proving the sharpen radius shrinks 4→2→1 as proxy_scale goes 1→2→4.
  Engine-only, additive, export output unchanged. (v0.56.19, this run)

- **Explain what Auto-process did** — after Auto-process builds a recipe the user
  saw a pipeline of op names but no sense of *why* those ops, so the one-click
  result was a black box. A new pure `autoSummarySentence` helper turns the built
  recipe's *enabled* ops into a plain-language sentence via a phrase map keyed by
  op id ("Flattened the background, balanced the colour, applied a natural stretch,
  removed the green cast, boosted colour saturation, then sharpened detail."),
  falling back to the registry label for any unmapped op. The Editor shows it in a
  dismissible violet "What Auto-process did" note after Auto runs. Builds trust in
  the one-click path and teaches the recommended order. Pure helper unit-tested
  (9 cases) + an Editor wiring test; frontend-only, additive. (v0.56.18, this run)

- **Per-op "Reset to defaults" (already shipped)** — the backlog listed this as an
  Idea, but it was in fact already implemented (in `0c333bd`): the selected-op
  param panel carries both a per-param reset icon and a "Reset op" button that
  restore each param to its spec default. Moved to Shipped to correct the record;
  no code change. (housekeeping, this run)

- **Plain-language help on the jargon-heavy editor ops** — several detail/tone ops
  spoke in astro-jargon a beginner can't decode ("Wavelet / bilateral / TV
  denoise", "Unsharp mask", "Black/white point + gamma") and their sliders (denoise
  method/strength, sharpen amount/radius, deconvolve iterations/PSF, hot-pixel σ,
  levels black/white/gamma) carried *no* per-param help at all. Rewrote the op help
  in plain language (what it does + when to use it) and added a one-line hint to
  each of those sliders — surfaced automatically in the Add-operation menu and the
  op param panel via the already-threaded `help` field. Also relabelled the
  cryptic "PSF σ (px)" → "Blur width (px)" and "σ" → "Threshold (σ)". Metadata-only,
  additive; a test asserts every op has help and the key detail/levels params now
  carry hints. (v0.56.17, this run)

- **Per-op "without this op" preview compare** — the editor's Compare button shows
  the whole recipe vs the raw base, but while tuning one op a user wants to see
  *just that op's* contribution. The selected op's panel now carries a "Without
  this op" toggle that renders the full recipe with only that op bypassed (reusing
  the existing preview path with a modified recipe), overlaying a "Without: <op>"
  label so the isolated op's effect is obvious. Mutually exclusive with the
  Compare/Star-mask overlays and resets when the selection changes, so each op
  starts from "showing with". Vitest-covered (toggle flips label + button state);
  frontend-only, additive. (v0.56.16, this run)

- **Progressive disclosure of the "Add operation" menu** — the menu listed all ~19
  editor ops flat across four groups, so a beginner opening it was faced with every
  knob at once and no hint which few matter. The menu now leads with a curated
  **Common** section (Stretch, Curves, Saturation, SCNR, Noise reduction, Sharpen,
  Background subtract) and tucks the full grouped list behind a **More operations**
  toggle (collapsed by default, `closeMenuOnClick={false}` so expanding it keeps the
  menu open). The common list is restricted to ops the engine actually exposes, so
  it degrades gracefully if an op id changes. Vitest-covered (Common shown, a
  non-common op hidden until "More operations" is expanded); frontend-only.
  (v0.56.15, this run)

- **Auto-place a newly-added op on the correct side of the stretch** — adding an op
  from the menu appended it at the end of the pipeline, so a linear op (background,
  colour cal, denoise) added after the stretch immediately tripped the v0.56.10
  "should be before the stretch" caution the user then had to Fix. A new pure
  `insertOnCorrectSide` helper now inserts a freshly-added op on its correct side of
  the *enabled* stretch by default — linear just before, nonlinear just after,
  `any`-stage (and anything added with no enabled stretch) still appended at the
  end exactly as before — so the common add-then-tune flow never lands on the wrong
  side. Reuses the same side/stretch logic as `moveToCorrectSide`; unit-tested
  (5 cases: linear-before, nonlinear-after, any-appends, no-stretch-appends,
  empty-pipeline); frontend-only. (v0.56.14, this run)

- **"No stretch step" nudge in the editor pipeline** — if a recipe has ops but no
  *enabled* Stretch op, the pipeline silently auto-inserts a default asinh stretch
  at the end so the preview isn't black — but the user's tone/colour ops then run
  on un-stretched (linear) data and the result looks wrong, with no explanation.
  The pipeline panel now shows a subtle yellow advisory in that case, with a
  one-click "Add stretch" (or "Enable stretch" when a bypassed one exists) so a
  beginner gets an explicit, controllable stretch. Complements this run's
  stage-conflict warning. Pure `hasEnabledStretch` helper, unit-tested;
  frontend-only, advisory. (v0.56.13, this run)

- **Friendly names for enum dropdowns (editor + Stack/Settings forms)** — enum
  params rendered their raw internal values ("asinh", "stf", "gray_star", "gaia",
  "per_channel", "luminance", "average", "maximum") in the Select dropdowns, jargon
  a beginner can't decode. Added an optional additive `option_labels` (value →
  display name) to the shared param descriptor (`EditParam` + `StackOptionField`),
  threaded through the editor-ops and stack-options schema endpoints, and rendered
  by the shared `StackOptionControl` (falls back to the raw value for any option
  without a mapping). Populated it for the Stretch curve (Asinh (manual) / Auto
  (STF)), SCNR protect, editor + stack colour-calibration mode, and background /
  final-gradient mode. Upgrade-safe: new optional field defaults null; recipes and
  configs store values, not labels, so nothing changes on disk. Vitest-covered
  (friendly label shown + raw-value fallback). (v0.56.12, this run)

- **Grey out stretch params that don't apply to the chosen curve** — the Stretch op
  exposes both the Asinh knobs (Strength, Black point) and the STF knob (STF sky
  level), but only one set does anything for a given `mode`, so a beginner drags a
  slider that silently has no effect. `depends_on` (the descriptor gating already
  used across the Stack/Settings/editor forms) gained an optional `key=value` form
  so a field can depend on a *specific* enum choice, not just a boolean; the Asinh
  params now declare `depends_on="mode=asinh"` and STF sky level `depends_on="mode=stf"`,
  so the irrelevant ones grey out as the user switches curve. STF sky level was also
  promoted from Advanced to the main params so STF mode always shows its one active
  control, and each param got a clearer help line. Backward-compatible: a bare
  `depends_on` key stays a truthiness check, so every existing boolean dependency is
  unchanged. Pure `dependencyMet` helper unit-tested (bare-key, `key=value`,
  stringify) + a render test that the STF slider disables in Asinh mode. Frontend +
  metadata-only. (v0.56.11, this run)

- **Stage-conflict caution + one-click fix in the editor OpList** — ops declare a
  `stage` (linear / nonlinear / any), and the pipeline runs them across a single
  stretch boundary, but the op list lets a user drag e.g. a background-gradient
  (linear) op below the stretch, where it silently operates on display-space data
  and misbehaves. Each op row now shows a subtle orange caution ("should be
  before/after the stretch", with an explanatory tooltip) when an *enabled* op
  sits on the wrong side of the *enabled* stretch, plus a one-click "Fix" that
  repositions it to the correct side (linear → just before the stretch, nonlinear
  → just after). Pure, unit-tested `stageConflicts` / `moveToCorrectSide` helpers
  (10 cases: both sides, `any`-stage neutrality, disabled-op / no-stretch
  no-ops); frontend-only, advisory. (v0.56.10, this run)

- **Combine-method facet on the Gallery** — a "All / Drizzle / Min-max / σ-clip /
  Mean" `SegmentedControl` (shown only when the set is *mixed* — >1 distinct
  method present — mirroring the calibration filter chip) that isolates e.g. every
  drizzled result across every target. A new pure `combineMethodKey` helper
  (coarse key with the engine's precedence: drizzle > min/max > σ-clip > mean;
  null for editor/channel-combine runs) drives both the facet options and the pure
  `filterByMethod`. Unit-tested (key precedence + filter) plus render tests for the
  mixed-vs-uniform gating and narrowing. Frontend-only, additive. (v0.56.8, this run)

- **One-click "Turn on min/max rejection" on the Stack-form nudge** — the
  small-stack streaked-frame hint (v0.56.2) told the user min/max reject is the
  right tool but made them hunt for the toggle in Advanced options. The advisory
  now carries a one-click "Turn on min/max rejection" button that flips
  `min_max_reject` on (mirroring the calibration "Use recommended" one-click), so
  a beginner acts on the advice without knowing where the knob lives; the nudge
  self-dismisses once it's on. Frontend-only, additive. Vitest-covered.
  (v0.56.7, this run)

- **Gentle green-cast removal in the one-click Auto recipe** — an OSC Seestar
  stack almost always carries a residual green cast (the Bayer green is the
  strongest channel), which every built-in nebula preset already fixes with SCNR
  but the `Auto-process` recipe skipped. Auto now appends a gentle
  `tone.scnr` (amount 0.7) after the STF stretch and *before* the saturation
  boost, so the boost lifts real colour instead of amplifying the green. SCNR is
  monotone (it can only cap green above the R/B neutral, never invent colour), so
  it's safe on galaxies/clusters too. Auto-process is an explicit button (not a
  silent upgrade default) and saved recipes are untouched — upgrade-safe. Test
  asserts SCNR presence + ordering. (v0.56.6, this run)

- **Guided empty-pipeline nudge in the editor** — a first-timer opening the editor
  with no saved recipe saw only "No operations yet" with no hint of the one-click
  path. The empty pipeline now shows a grape guided nudge explaining what
  Auto-process does (background & colour balance, natural stretch, gentle
  denoise/sharpen) with its own Auto-process button, so a beginner gets a good
  starting point in one click instead of guessing which op to add first. Reuses
  the existing `auto` mutation; frontend-only, additive. Vitest-covered.
  (v0.56.9, this run)

- **"Export only" flag for preview-approximate editor ops** — the Deconvolution op
  is `proxy_safe=False`, so it's silently skipped in the fast live preview: a user
  would add it, drag its PSF σ / iterations sliders and see *no change*, which reads
  as a broken control. The editor now surfaces this: each non-`proxy_safe` op row
  carries a grape "export only" badge (with a tooltip), and selecting such an op
  shows an explanatory note ("The live preview doesn't show this effect — it's
  heavy, so it only runs when you Export or Download full-res PNG"). Reuses the
  `proxy_safe` field already carried on the ops schema; frontend-only, additive.
  Vitest-covered (badge + note). (v0.56.5, this run)

- **Plain-language "Combined:" line in the History Info panel** — the Info panel
  showed the raw `STACKER` FITS card ("min-max-reject", "sigma-clip", "mean",
  "drizzle") — engine jargon a beginner won't recognise. It now also renders a
  friendly "Combined: Min/max (extremes) rejection — drops the highest and lowest
  value at each pixel" line (alongside the existing Integration / Quality-weighted
  / Processing lines), derived from the STACKER card via a pure, case-insensitive
  `combineMethodLabel` helper (returns null for channel-combine / unknown methods,
  so the line is simply omitted). Unit-tested + a render assertion. Frontend-only,
  additive. (v0.56.4, this run)

- **Combine-method badge in the Compare view** — the `RejectionBadge` (v0.56.1)
  now also appears on each panel of the A/B Compare view, so when a user compares
  two stacks of one target to answer "did changing the rejection method help?"
  they can see each side's method ("σ-clip κ3" vs "min-max") at a glance next to
  the noise verdict. Reuses the gallery `options` the Compare view already
  fetches; frontend-only, additive. (v0.56.3, this run)

- **Min/max-reject nudge on the Stack form for small streaked stacks** — below
  ~11 frames κ-σ mathematically can't reject a lone satellite/plane trail (a
  single outlier's deviation stays within κ·σ of the mean), which is exactly the
  regime this run's min/max reject handles. The Stack form now shows a
  plain-language hint suggesting "Min/max rejection" when a small stack (3 ≤
  accepted+solved < 11, non-drizzle) carries streaked frames and min/max reject
  isn't already on — superseding the generic "turn on sigma clipping" streak
  warning in that regime (where that advice doesn't actually work). Also fixed a
  pre-existing advisory gap: the streak-no-rejection warning's `rejectionOn`
  didn't count min/max reject as per-pixel rejection, so it wrongly fired when
  only min/max reject was enabled. Frontend-only, advisory. (v0.56.2, this run)

- **Rejection-method badge on History/Gallery cards** — a stack can be combined
  one of four ways (mean / σ-clip / min-max reject / drizzle), recorded in the
  run's stored options. A shared, tooltip'd violet `RejectionBadge` now shows the
  *effective* combine method ("min-max" / "σ-clip κ3" / "drizzle ×2", nothing for
  a plain mean) on both Gallery and History cards, honouring the engine's method
  precedence (drizzle > min-max > σ-clip). The Gallery's `highlightBadges` dropped
  its ad-hoc σ-clip/drizzle chips in favour of the dedicated badge (which also
  covers min-max and carries a plain-language tooltip); History gained a new
  additive `options` field on `StackRunOut` (parsed from the run's `options_json`)
  to derive it. Pure `rejectionBadge` helper unit-tested (precedence, kappa/scale
  formatting, editor/channel-combine → null) plus backend tests that the
  stack-runs list exposes options. Frontend + one additive API field;
  upgrade-safe. (v0.56.1, this run)

- **Min/max (extremes) rejection for small stacks** — the order-statistic fix
  for a lone satellite/plane trail below ~11 frames that κ-σ mathematically can't
  reject (a lone outlier's deviation stays below κ for n<11). A new single-pass,
  NaN-aware `MinMaxRejectAccumulator` tracks per-pixel sum/count/min/max and
  outputs `(sum − min − max)/(count − 2)` for count≥3 (plain mean below that), so
  it drops exactly one per-pixel min and max before averaging — tie-safe (a
  saturated core shared by several frames only loses one contribution) and
  memory-bounded (four canvas planes, one pass, within the existing peak-array
  budget). Wired as an opt-in `StackOptions.min_max_reject` (default off, takes
  precedence over κ-σ on the standard path; descriptor-driven so it surfaces on
  the Stack form automatically) and stamped into the `STACKER` provenance card.
  Unit-tested (drop/tie/NaN/low-coverage/windowed) + end-to-end. Additive/
  upgrade-safe. (v0.56.0, this run)

- **Capped exponential backoff for Seestar reconnects** — the poll loop
  re-`connect()`ed a dropped scope on every cycle (default a few seconds) with no
  backoff, so a scope that's genuinely gone got hammered indefinitely. Each ip now
  carries a consecutive-failure count and a monotonic "next attempt" time; a
  failed reconnect grows the delay `base·2^(fails-1)` up to a 300 s cap, a
  successful one clears it (so a brief Wi-Fi blip still recovers fast), and the
  device surfaces a "reconnecting…" state (orange badge) for the dashboard.
  Reconnect logic factored into a testable `_poll_reconnect` + a pure
  `_reconnect_delay_s`, unit-tested with an injected clock (no hardware).
  Additive/upgrade-safe (new optional device field). (v0.55.5, this run)

- **"You have calibration masters but aren't using them" nudge on the Stack
  form** — the single most common beginner mistake is stacking uncalibrated even
  though the library holds a matching master. When `calibration-suggestions`
  returns a recommended dark/flat/bias *and* no calibration selector is set yet,
  the Stack form now shows a prominent teal advisory ("You have a matching master
  dark + flat in your library, but this stack isn't calibrated — calibrating
  removes amp glow, dust shadows and vignetting…") with the same one-click "Use
  recommended". Once any selector is set it falls back to the existing subtle
  hint, so it never badgers a user already engaging with calibration. Advisory
  only, within-target, frontend-only. (v0.55.4, this run)

- **Calibration-status filter chip on the Gallery** — building on the searchable
  `calstat` column (v0.55.2), the Gallery gained an "All / Calibrated /
  Uncalibrated" `SegmentedControl` (shown only when the set is *mixed* — some
  calibrated, some not — so it's never a no-op chip) that isolates the
  uncalibrated stacks worth re-running without typing. Pure, non-mutating
  `filterByCalibration`/`isCalibrated` helpers, unit-tested plus a render test
  for the mixed-vs-uniform gating. Frontend-only, additive. (v0.55.3, this run)

- **Gallery search matches calibration status** — building on this run's
  `calstat` column, the Gallery free-text search now also matches a run's
  calibration status, so typing "flat" surfaces every flat-calibrated stack and
  "dark" the dark-calibrated ones across every target — handy for finding your
  properly-calibrated results. Extracted the inline filter into a pure,
  non-mutating `filterGallery` helper (matches label + target + filename +
  calstat) and unit-tested it. Frontend-only, additive. (v0.55.2, this run)

- **Seestar reconnect hygiene (fd-leak fix)** — the manager's poll loop
  re-`connect()`s a disconnected client every cycle, but `SeestarClient.connect()`
  overwrote `self._sock` without closing the dead one or clearing the in-flight
  `_pending` replies the dropped link left behind — so a flaky Wi-Fi link to the
  scope leaked a file descriptor (and a stranded pending reply) on every
  reconnect. `connect()` now runs a shared `_teardown_locked()` (extracted from
  `disconnect()`) before opening a fresh socket, closing the stale fd and waking
  any waiter with "disconnected". Unit-tested with injected stale state (no
  hardware). (v0.55.1, this run)

- **Calibration chip on History/Gallery cards** — a stack now records which
  calibration masters were applied to its lights in a new additive
  `stack_runs.calstat` column (schema v6→v7 migration; "dark+flat", "bias+flat",
  "flat", …, NULL when uncalibrated / for old runs), mirroring the `CALSTAT` FITS
  card the engine already stamps but read from the run record so no per-card FITS
  read is needed. `StackRunOut` and the gallery response carry it, and a shared
  teal `CalibrationBadge` shows a small "dark+flat" chip (with a plain-language
  tooltip) on History and Gallery cards — so a user sees at a glance whether a
  stack was calibrated, useful when comparing a calibrated vs uncalibrated run.
  Additive/upgrade-safe. (v0.55.0, this run)

- **Per-target noise-σ trend sparkline** — the History page now shows a small
  "Noise trend" card (a reusable inline-SVG `Sparkline`) plotting each measured
  stack's background-noise σ oldest→newest, so a user sees the *trajectory* (are
  my results getting cleaner as I add nights?) at a glance, not just the last
  hop — teal + "Cleaner than your first" when trending down, orange + "Noisier"
  when up. Shown only with ≥2 measured runs. Pure `noiseTrendSeries` /
  `sparklinePoints` helpers, tested; reuses the recorded `noise_sigma`;
  within-target, frontend-only. (v0.52.1, this run)

- **Recommend a master bias for the bias+flat (no-dark) workflow** — completes
  the v0.53.0 bias feature. `recommend_masters` now also ranks bias masters
  (exposure-independent, so matched on gain/temp like a flat) and returns a
  `bias_master_id`; the endpoint passes it through, and the Stack form badges the
  best bias "★ recommended" and includes it in the "Use recommended" one-click —
  but only when *no* dark is recommended (a dark already carries the bias, so the
  engine would ignore it). So the no-dark calibration path is now as guided as
  dark+flat. Additive/upgrade-safe. (v0.54.0, this run)

- **Record which calibration masters were applied in the FITS header** — a
  calibrated stack didn't self-document its calibration (only the log said so).
  `run_stack` now stamps a `CALSTAT` provenance card recording the masters
  actually applied to the lights ("dark+flat", "bias+flat", "flat", …), threaded
  from `CalibrationMasters.describe()` into `_build_output_header_meta`, and the
  run Info panel surfaces it (added to `_INFO_CARDS`). Omitted when nothing was
  applied. Additive/upgrade-safe; extends the existing STACKER/COLORTYP
  provenance pattern. (v0.53.1, this run)

- **Bias-only calibration for lights when no dark is chosen** (bias slice (a))
  — master bias frames could be built but were never applied to lights.
  `CalibrationMasters.load` now takes a `bias_path`; `apply_raw` subtracts the
  bias as the readout pedestal — `(light − bias) / flat` — but **only when no
  master dark is set** (a dark already contains the bias, so both would
  double-subtract it: the bias is loaded but inert when a dark is present).
  Threaded end-to-end: `StackOptions.bias_path` (+ `NON_FORM_KEYS`),
  `resolve_master_paths` returns a 4th bias path, the stack router resolves a
  `bias_master_id` server-side and the reuse-settings endpoint reverse-maps it,
  and the Stack form gained a "Master bias (no dark)" selector with a caution
  when a dark is also picked. Additive/upgrade-safe (new optional field,
  default None). Slice (b) — dark exposure-scaling — filed above. (v0.53.0,
  this run)

- **"Compare with previous run" action on the History page** — the Compare view
  (v0.51.0) was reachable only from the Gallery's multi-select, but the most
  common comparison is two stacks of the *same* target ("did adding subs /
  changing κ actually help?"). Each History card (all but the oldest run) now
  carries a grape "Compare" button that deep-links into the existing
  `/compare?a=…&b=…` route against the chronologically previous run — the
  Compare view resolves both refs from the gallery, so no backend change. Pure
  `previousRunId` (walks the newest-first list, null for the oldest/unknown) and
  `historyCompareHref` helpers, tested; frontend-only, additive. (v0.52.0, this run)

- **"Which stack is cleaner" verdict in the Compare view** — when both compared
  stacks carry a measured noise σ, the Compare page now shows a plain-language
  banner ("B has 20% lower background noise — it's the cleaner stack"), turning
  the A/B comparison into a concrete answer for the "did this setting change
  help?" question. Pure `noiseComparison` helper (guards missing/zero/equal σ);
  frontend-only, additive. (v0.51.2, this run)

- **Configurable job-history retention** — the job-history cap (how many finished
  jobs the in-memory map keeps, and at ~10× how many rows `jobs.sqlite` retains)
  was a hard-coded 200; it's now a `job_history_limit` setting (default 200,
  bounds 10–100000) surfaced on the Settings page and threaded into the
  `JobManager` at startup. A settings change applies to the running manager
  immediately (no restart). Additive/upgrade-safe: the default equals the old
  constant, so an existing install keeps exactly as much history as before.
  (v0.51.1, this run)

- **Compare-two-stacks web view** — a new `/compare?a=<safe>:<run>&b=<safe>:<run>`
  route (bookmarkable) shows two stacks **side by side** or as a **blink**
  comparator (auto-alternates the two images in one frame at ~0.7 s, with
  play/pause + manual flip) so a subtle difference — less noise, a cleaned
  satellite trail, sharper stars — pops out. Each panel carries the target,
  settings-relevant metadata and the noise readout. Launched from the Gallery's
  existing multi-select: selecting exactly two images reveals a "Compare" action.
  Reuses the gallery query + preview URLs (no new endpoint); handles a
  deleted/missing run gracefully. Pure `parseRef`/`compareHref` helpers tested;
  frontend-only, additive. (v0.51.0, this run)

- **Noise-improvement readout vs the previous stack** — each History card now
  shows its background-noise σ as a delta against the same target's *previous*
  measured stack ("−18% noise vs your last stack", teal for cleaner / orange for
  a regression / dimmed when ≈unchanged), so a user tuning settings or adding
  subs sees at a glance whether the change actually helped — trial-and-error
  becomes feedback. Pure `noiseDeltas` helper walks the runs oldest→newest so
  "previous" is chronological (independent of the display sort) and guards a
  zero baseline; runs with no earlier measured σ get no readout. Reuses the
  recorded `noise_sigma`; frontend-only, additive. (v0.50.0, this run)

- **Newest/Cleanest sort on the Gallery** — extends the History-page noise sort
  (v0.49.0) to the Gallery, where runs span every target: a `SegmentedControl`
  (shown only with >1 image and at least one measured σ) reorders cards by
  ascending `noise_sigma`, keeping unmeasured (pre-v0.48) runs last — a global
  "show me my cleanest results" that reuses the recorded σ (normalized so it's
  comparable across gain/exposure). Pure `sortGallery` helper; frontend-only,
  additive. (v0.49.1, this run)

- **Newest/Cleanest sort on the History page** — completes the noise series: the
  History view gained a Newest/Cleanest `SegmentedControl` (shown only with >1 run
  and at least one measured σ) that reorders the run cards by ascending
  `noise_sigma`, keeping unmeasured (pre-v0.48) runs last — so a user with many
  stacks of one target can jump straight to the least-noisy result rather than
  eyeballing every card. Pure `sortRuns` helper; frontend-only, additive.
  (v0.49.0, this run)

- **Stamp the background-noise σ into the master FITS header** — extends the
  v0.48.0 noise readout: `run_stack` now measures the finished stack's noise σ
  *once* and records it both as a `BKGSIGMA` FITS provenance card (so Siril/
  PixInsight/APP see how clean the result is) and in the run record (previously
  computed twice), and the run Info panel surfaces the card. Additive/upgrade-
  safe; extends the existing STACKMTD/DECONPSF provenance pattern. (v0.48.1,
  this run)

- **Per-stack noise-floor readout + "cleanest stack" badge** — `run_stack` now
  records each stack's normalized background-noise σ (reusing
  `seestack/edit/noise.estimate_noise_sigma` on the finished image) in a new
  additive `stack_runs.noise_sigma` column (schema v5→v6 migration; old runs stay
  NULL). `StackRunOut` and the gallery response carry it; History and Gallery
  cards show a small "Noise 0.021" readout (lower = cleaner, with a plain-language
  tooltip), and the History page (all runs of one target) flags the single
  lowest-noise run with a teal "Cleanest" badge — but only when ≥2 runs carry a
  measured σ, so a lone stack is never singled out. Turns "which looks less noisy"
  into a number. Additive/upgrade-safe; within-target comparison only. (v0.48.0,
  this run)

- **Editor processing chain in the History Info panel** — the run Info endpoint
  (`GET …/stack-runs/{id}/info`) now parses the `AstroStack: op.id(args)` FITS
  `HISTORY` cards an editor export writes (v0.46.0) into a friendly, ordered
  `processing` list (op id + registry label), and the History Info panel shows
  "Processing: Stretch → Noise reduction → Sharpen" — so a user sees how a run
  was edited without opening the FITS in Siril. Unknown op ids fall back to the
  raw id; non-AstroStack HISTORY cards are ignored; plain stacks report an empty
  chain. Additive/upgrade-safe (just a header read + new response field).
  (v0.47.0, this run)

- **Full editor-recipe HISTORY provenance in exported FITS** — an editor export
  previously recorded only the op *count* (`STACKMTD="editor recipe (N ops)"`).
  The derived `master.fits` now also carries one FITS `HISTORY` card per enabled
  op with its key params (e.g. `AstroStack: detail.denoise(method=wavelet,
  strength=0.5)`) — the canonical provenance mechanism that Siril/PixInsight/APP
  display — so an edited export self-documents its full processing chain.
  `_merge_header_meta` gained list-valued `HISTORY` (appends commentary cards)
  support; disabled/long-structured params are skipped and each card is clamped
  to the 72-char limit. Additive/upgrade-safe. (v0.46.0, this run)

- **Code-split the frontend vendor bundle** — the eager app bundle was one
  720 kB `index` chunk (React + Mantine + TanStack + all routes). A `manualChunks`
  split in `vite.config.ts` peels the rarely-changing vendors into `react`
  (65 kB), `mantine` (461 kB) and `query` (41 kB) chunks, dropping the main app
  chunk to ~153 kB — so no eager chunk trips the 500 kB warning and vendors stay
  cached across app deploys. The only remaining large chunks are the already
  lazy-loaded Sky/aladin atlas (loaded only on the Sky page). Build-config only.
  (v0.45.1, this run)

- **"From your image" denoise-strength suggestion** — the editor's noise-
  reduction op made the user hand-tune a 0..1 strength knob. A new engine module
  (`seestack/edit/noise.py`) estimates the run's background noise σ robustly
  (MAD of adjacent-pixel differences, normalized to the image's own p0.5..p99.5
  signal range so it's comparable across gain/exposure) and maps it linearly to
  a starting strength (clamped to the op's 0.1..1.0 range, rounded to its 0.05
  step). Pure-numpy so it never depends on PyWavelets. Exposed via
  `GET …/editor/denoise-suggestion` and offered as a one-click "From your image
  (strength X)" button on `detail.denoise`, reusing the generic `suggestions`
  prop (v0.43.0). Additive/upgrade-safe. (v0.45.0, this run)

- **Record the deconvolution PSF σ in the exported FITS header** — when an
  editor recipe includes an enabled `detail.deconvolve` op, the derived
  `master.fits` now carries a `DECONPSF` card recording the Gaussian PSF σ (px)
  actually used (a single float, or comma-joined when several deconvolutions ran
  in order), and the History Info panel surfaces it (added to `_INFO_CARDS`). So
  a sharpened export self-documents in Siril/PixInsight/APP whether and how hard
  it was deconvolved, extending the existing STACKMTD/EDITFROM provenance
  pattern. Additive/upgrade-safe. (v0.44.0, this run)

- **PSF-from-stars for editor deconvolution** — the deconvolution op made the
  user hand-guess a Gaussian PSF σ. A new `GET …/editor/psf-suggestion`
  endpoint derives it from `Project.median_fwhm()` (median FWHM of accepted
  frames, already measured by QC): σ = FWHM / (2·√(2·ln2)), clamped to the op's
  0.5–5.0 slider range, null when no frame carries an FWHM. The editor's op
  param panel gained a generic, reusable `suggestions` prop; for
  `detail.deconvolve` it renders a one-click "From your stars (σ≈X, FWHM Ypx)"
  button that sets `psf_sigma`. Additive/upgrade-safe. (v0.43.0, this run)

- **Auto-grade hint on the Stack form** — the Stack form now calls the
  `frames/auto-grade` preview endpoint (only once there are ≥10 accepted frames,
  matching the grader's robust-stats floor) and, when it flags some accepted
  frames as likely quality outliers, shows a yellow advisory ("Auto-grade thinks
  N of your M accepted frames look like quality outliers …") with a "Review
  Auto-grade" button linking back to the Target page — so a user about to stack
  junk is pointed at the one-click cleanup. Advisory only; nothing is rejected
  from the Stack form. (v0.42.2, this run)

- **Nudge quality weighting when frame quality varies a lot** — the Stack form
  now shows an advisory when the frames that would be stacked (accepted +
  solved) show a wide *robust* spread — interquartile spread (p75−p25)/median ≥
  0.3 in FWHM or ≥ 0.4 in star count — but `quality_weighted` is off, because a
  mixed-quality set is exactly where down-weighting the worst subs helps and a
  uniform set barely changes. Needs ≥8 frames; IQR/median is scale-free and
  outlier-robust so a couple of bad subs don't trigger it. Client-side,
  within-target, advisory only; reuses the metrics already fetched for the
  transparency hint. (v0.42.1, this run)

- **"N trailed frames" badge on the Target view** — mirrors the "N streaked"
  badge for star *shape*. A shared `trailed_frame_ids` helper flags accepted
  frames whose `eccentricity_median` is *both* a strong within-target outlier
  (> median + 3·MAD) *and* above a 0.6 absolute floor of noticeably elongated
  stars (needs ≥5 measured frames, so a tiny set is never nuked) — a
  bad-tracking/wind/bumped-mount night. The Target view shows a yellow
  "N trailed" badge (computed client-side with the identical criterion) with a
  one-click "Reject all" that calls a new `reject_trailed` bulk action
  (reason `bulk:trailed`, wired into the existing one-click undo). Reuses
  existing plumbing; additive/upgrade-safe. (v0.42.0, this run)

- **Auto-grade: automatic, explained frame-quality grading** — the QC layer
  measured five per-sub quality metrics but (streaks aside) nothing acted on
  them; picking "reject worst N% by metric X" needs exactly the judgment a
  beginner lacks. A new engine module (`seestack/qc/grading.py`) grades a
  target's accepted frames with robust one-sided modified z-scores
  (median/MAD, meanAD fallback; log-domain for the multiplicative metrics —
  star count, sky, transparency; linear for FWHM/eccentricity) and only flags
  frames that are *also* practically worse (≥25% softer FWHM, ≥1.5× brighter
  sky, ≥30% star/transparency loss, +0.15 eccentricity), each with a
  plain-language reason ("far fewer stars than typical (25 vs 400) — likely
  cloud"). Safety rails: ≥10 measured frames per metric, ≤25% of frames ever
  recommended (worst-by-z kept), user-graded frames never touched, machine
  rejections don't set `user_override` (reason `auto:grade:<metric>`).
  Exposed as `GET/POST …/frames/auto-grade[/apply]` (apply recomputes
  server-side and returns `changed_ids` for the shared one-click undo), a
  preview-first modal on the Target page, and an opt-in
  `auto_grade_frames`(+`auto_grade_sensitivity`) setting that grades
  hands-off after QC in the watcher pipeline and manual QC+solve. Also fixed a
  pre-existing staleness bug the undo flow exposed: manual accept/reject and
  bulk frame actions never refreshed the registry's accepted counts. Additive/
  upgrade-safe; default off. (v0.41.0, manual/frame-auto-grading)

- **Plain-language hints on the Target metric columns** — the FWHM, Stars, Ecc.
  and Sky column headers now carry the same dotted-underline hint tooltip that
  only Transparency had, each explaining in one sentence what the metric means
  and which direction is better (e.g. "Ecc. — median star elongation: 0 = round,
  closer to 1 = trailed; flags tracking error/wind. Lower is better."). Removes a
  layer of jargon for a beginner scanning their subs. Frontend-only.
  (v0.40.1, this run)

- **Transparency-night badge on History/Gallery cards** — completes the
  transparency series. `run_stack` now records each run's transparency verdict
  (`median transparency of the stacked frames ÷ the target's p90 clear-sky
  baseline`) in a new additive `stack_runs.transparency_ratio` column (schema
  v4→v5 migration; old runs stay NULL), mirroring the Stack-form pre-run hint's
  within-target normalisation. `StackRunOut` and the gallery response carry it,
  and a shared `HazyNightBadge` shows a small orange "Hazy night" badge (with a
  "% below clearest nights" tooltip) on History and Gallery cards when the ratio
  is below 0.6 — so a user browsing past stacks sees which were shot through
  haze at a glance, no reopening. Additive/upgrade-safe. (v0.40.0, this run)

- **Surface the quality-weighting summary in the run Info panel** — a
  quality-weighted stack now stamps its `WeightingStats` onto the master FITS
  header (`WGTMODE`/`WGTNDOWN`/`WGTMIN`/`WGTMAX`/`WGTMED`), and the run Info
  endpoint parses those into a friendly `weighting` object so the History Info
  panel shows "Quality-weighted · N frames down-weighted · weights 0.31–1.00
  (median 0.72)". Lets a user trust the (off-by-default) weighting did something
  and gauge how aggressive it was, with no extra storage — just header cards,
  matching the existing provenance pattern. Added `n_downweighted` to
  `WeightingStats`. (v0.39.0, this run)

- **Eccentricity factor in quality weighting** — `compute_frame_weights` gained a
  fifth `ecc_factor` (`clip(median_ecc / frame_ecc, min_weight, 1.0)`), so with
  quality-weighting on, frames whose stars are more *elongated* than the run's
  median (tracking error / wind / a mount bump) pull less into the average, while
  rounder-than-median frames cap at the neutral 1.0. Captures star *shape* where
  the FWHM factor captures *size*, so the two aren't redundant. Guards
  `frame_ecc == 0` (perfectly round = best case) against divide-by-zero and only
  applies when the run's median eccentricity is itself measurable. Additive;
  gated by the off-by-default `quality_weighted`. (v0.38.0, this run)

- **Library search matches notes + persistent filter view** — the Library
  free-text search now also matches a target's `notes` (not just name/tags), and
  the whole view (search text, sort, active tag chips) is persisted to
  localStorage so a user with a big library keeps their filters when they open a
  target and come back, or reload. Defensively guarded so a disabled/broken
  store never breaks the page. Frontend-only. (v0.37.0, this run)

- **Transparency-night hint on the Stack form** — completes the transparency
  weighting pair (v0.36.0). The Stack form now shows an advisory when the median
  transparency of the frames that would be stacked (accepted + solved) sits well
  below (<60% of) this target's clear-sky baseline — the 90th percentile of
  transparency across all frames that carry a score — so a user knows the stack
  was shot through haze/thin cloud even if they didn't reject those subs, and is
  pointed at quality weighting or rejecting the hazy subs. Client-side,
  within-target normalisation; advisory only. (v0.36.1, this run)

- **Weight the stack by frame transparency** — `compute_frame_weights` gained a
  fourth `transparency_factor` (`frame_transparency / median_transparency`,
  clipped to `[min_weight, 1.0]`), so with quality-weighting on, hazy/thin-cloud
  subs (whose bright stars dimmed) pull less into the average while clear frames
  cap at the neutral factor. Normalised against the median of the frames being
  stacked (within one target), because the raw score isn't comparable across
  gain/exposure. Frames without a transparency score keep the neutral factor.
  Additive; gated by the existing (off-by-default) `quality_weighted` flag.
  (v0.36.0, this run)

- **Inline reject-reason chip on rejected frame rows** — rejected rows in the
  Target table were only dimmed; each now carries a small muted plain-language
  reason chip (with a raw-reason tooltip) so a user scanning the table sees *why
  each specific frame* was dropped, not just the aggregate. `rejectReasonLabel`
  was extended to cover the remaining persisted reason forms (`auto:*`,
  `qc_error:*`, `solve_failed:*`), which also improves the existing reject-reason
  breakdown hover-card. Frontend-only. (v0.35.1, this run)

- **"Reject worst by transparency" bulk action** — building on this run's
  `transparency_score`, the `reject_worst` `BulkFrameAction` metric enum and the
  Target view's "Reject worst by" dropdown now include Transparency. Because
  higher transparency is *better*, the worst = the *lowest* scores, so the
  engine's "higher is better" flag set was extended (`star_count` +
  `transparency_score`). A user can now drop their haziest subs in one gesture.
  (v0.35.0, this run)

- **Editor undo/redo keyboard shortcuts** — the editor's undo/redo buttons now
  have keyboard equivalents: Cmd/Ctrl+Z undoes an op-pipeline change, Cmd/Ctrl+
  Shift+Z (or Ctrl+Y) redoes. Skipped while a text field is focused so editing
  the output name / curve inputs isn't hijacked, and the button tooltips now show
  the shortcut. Frontend-only; reuses the existing `useUndoable` history.
  (v0.34.1, this run)

- **Star-mask preview toggle in the editor** — a new
  `GET …/editor/star-mask` endpoint renders the soft `[0,1]` mask that gates the
  star ops (`stars.reduce` / `boost_nebula`) as a grayscale PNG on the live
  proxy (`size_px`/`grow` query params, clamped). The Editor gained a grape
  "Star mask" toggle next to Compare that overlays the mask (white = treated as a
  star) with a "Star mask" label, so a user can *see* what the editor considers a
  star vs background/nebula before dialling in star reduction. Additive;
  no-store, proxy-only. (v0.34.0, this run)

- **Compute the dead `transparency_score` frame metric** — the column has been
  in the schema and `FrameRow` since day one but was never populated. QC now
  computes it as the median instrumental flux of a frame's brightest ~10 stars
  (via `median_star_flux`): haze/thin cloud dims all stars, so the bright ones
  (which stay detected on clear *and* hazy nights) fade measurably, while using
  only the brightest avoids the confounder where a hazy frame loses its faint
  stars and inflates the survivors' median. Wired through
  `apply_qc_result_to_db`, exposed on `FrameOut` (+ sortable), and shown as a new
  "Transp." column (with a plain-language header tooltip) on the Target view — an
  imager can now sort to find their haziest subs. Relative within a target; not
  an absolute magnitude. Follow-up (weighting + grader hint) filed above.
  Additive/upgrade-safe. (v0.33.0, this run)

- **Undo the last bulk reject + reject-reason breakdown on the Target view** —
  two related approachability wins. `/frames/bulk` now returns `changed_ids`, so
  after a `reject_worst`/`reject_streaked` cut the Target view shows a one-click
  "Undo" that re-accepts exactly those ids (reuses the `accept` bulk action).
  And a new `GET /frames/reject-summary` (server-side `Project.reject_reason_counts`,
  NULL-reason bucketed as `user`) powers a "N rejected" badge with a hover-card
  breakdown by reason (QC: FWHM, Streaked (bulk), Manual, …) so a beginner sees
  *why* frames were dropped and can spot a dominant failure mode. Purely additive;
  the summary query is gated on there being rejected frames. (v0.32.0, this run)

- **Calibration mosaic-edge NaN/coverage audit** — completes the NaN/coverage
  audit series (channel combine v0.16.1, mono single-frame v0.22.1, mono
  mosaic-edge v0.28.1). Added a regression test that stacks two dark/flat-
  *calibrated* frames with only partial footprint overlap onto a union canvas
  and asserts the uncovered margin stays NaN — calibration (dark subtract + flat
  divide) never fabricates a zero wedge where there's no coverage — while
  coverage is genuine (0..2) and the interior stays finite. Confirms the
  calibration path already handles partial coverage correctly; no code change.
  (v0.31.1, this run)

- **Suggest the reference canvas when a non-drizzle mosaic is over budget** —
  the drizzle-off mirror of the v0.28.0 drizzle-scale suggestion. `stack-estimate`
  now returns `suggested_reference_canvas`: when drizzle is off and the union
  mosaic canvas alone blows the memory budget but the smaller reference-frame
  canvas would fit, the Stack form's over-budget alert offers a one-click "Use
  the reference canvas instead" that sets `mosaic_canvas=reference`. Turns the
  other over-budget refusal into a usable path. (v0.31.0, this run)

- **Warn when the stack budget exceeds available RAM** — `/api/system` now
  reports `memory.total_gb`/`available_gb` (from `/proc/meminfo`), and the
  Settings page shows an advisory Alert when `max_stack_memory_gb` is set higher
  than the box's currently-available RAM — a footgun that re-opens the OOM door
  the guard exists to close. Advisory only; the value is still honoured.
  Additive/upgrade-safe. (v0.30.1, this run)

- **One-click "reject all streaked frames"** — the "N streaked" badge on the
  Target view now carries a "Reject all" action (with a confirm) that rejects
  every accepted frame flagged `streak_detected` in one gesture, via a new
  `reject_streaked` `BulkFrameAction` (reject reason `bulk:streaked`,
  `user_override` set). For users who'd rather drop the streaked subs than rely
  on per-pixel rejection. Reuses the existing flag + bulk plumbing; additive.
  (v0.30.0, this run)

- **De-flake `Editor.test.tsx`** — `main`'s CI was intermittently red on the
  editor "loads the saved recipe" test: it gated `waitFor` on the static "Add
  operation" toolbar button (which renders before the async saved-recipe query
  resolves) and then checked the recipe op "Stretch" synchronously, so it raced
  on slower CI. Now it awaits the recipe-dependent text via `findByText`.
  Test-only. (v0.29.1, this run)

- **Stack memory budget as a Setting** — a new `max_stack_memory_gb` setting
  (default None = auto ~70% of RAM, clamped 0.5–1024 GB) lets the user view/raise/
  lower the per-stack working-memory cap from Settings instead of editing
  container env. Threaded into `run_stack`/`estimate_stack` via a
  `memory_budget_gb` param, so both the pre-run estimate and the in-run guard
  honour it. Precedence: the `ASTROSTACK_MAX_STACK_GB` env override still wins,
  then the setting, then auto. Additive/upgrade-safe (new optional field).
  (v0.29.0, this run)

- **Mono mosaic-edge NaN/coverage audit** — added a regression test that stacks
  two mono frames whose sky footprints only partially overlap onto a union
  canvas and asserts the uncovered margin stays NaN (never zero-filled into a
  black wedge that would drag downstream reductions toward zero), coverage is
  genuine (min 0, max 2), and the output stays pure luminance. Confirms the mono
  path already handles partial coverage correctly; no code change. (v0.28.1,
  this run)

- **Suggest a fitting drizzle scale when over budget** — the `stack-estimate`
  endpoint now returns `suggested_drizzle_scale`: when a drizzle run would blow the
  memory budget, the engine computes the largest scale (on a 0.1 grid, < the
  requested one) whose peak still fits, and the Stack form's over-budget alert
  offers a one-click "Use drizzle ×N instead" that fills it in. Turns a hard
  refusal into a usable path. None when drizzle is off, the run already fits, or
  even ×1.0 exceeds. (v0.28.0, this run)

- **Streaked-frame count badge on the Target view** — an orange "N streaked" badge
  next to the accepted count shows how many *accepted* frames still carry a
  satellite/plane trail (`streak_detected`), with a tooltip explaining that
  sigma-clip / drizzle outlier rejection can clean the trail while keeping the
  frame — so with "keep streaked frames" on, the user sees at a glance what
  per-pixel rejection needs to handle. Reuses the existing flag; frontend-only.
  (v0.27.1, this run)

- **Frame count / mosaic flag inline in the Stack estimate** — the pre-run sizing
  line now leads with "N accepted, solved frames · mosaic canvas · output W×H ·
  ~X GB peak memory", so the user confirms *what* is about to be stacked (count +
  mosaic-vs-reference) alongside the sizing, reusing `n_frames`/`is_mosaic` the
  `stack-estimate` endpoint already returned. Frontend-only. (v0.27.1, this run)

- **Reclaim streaked subs** — new opt-in `keep_streaked_frames` setting (default
  off). QC still detects satellite/plane trails, but with this on it *flags* the
  frame instead of auto-rejecting it, so a stack with per-pixel rejection
  (sigma-clip or drizzle rejection) removes just the streak while keeping the
  frame's ~99% good signal — valuable on big stacks. Threaded through
  `run_qc_and_solve(auto_reject_streaks=…)` and both webapp QC paths; a Settings
  toggle exposes it, and the Stack form warns when accepted streaked frames would
  be stacked *without* rejection (the footgun). User overrides are never
  clobbered. Additive/upgrade-safe (new setting defaults off). (v0.27.0, this run)

- **Large-stack sigma-kappa hint** — completes the sigma-clip guidance pair. The
  low-frame "don't clip under ~5" caution shipped in v0.22.0; now, when a stack
  has ≥200 accepted frames and κ is at/above the default 3, the Stack form
  suggests nudging κ down (~2.5) because the per-pixel spread is very well
  measured and a tighter clip safely rejects more satellites/planes/cosmic rays.
  Advisory only. (v0.26.1, this run)

- **Show/search run labels in the Gallery** — the gallery response now carries
  each run's `notes` label, so the Gallery card shows it (in violet, above the
  metadata line) and a new search box filters cards by label + target name +
  output filename. A user can finally find "best RGB v2" across every target
  without opening each History page. Purely additive (new response field, new
  UI). (v0.26.0, this run)

- **Drizzle memory estimate in the Stack form** — subsumed by the pre-run stack
  estimate below: the "~X GB peak memory" line covers drizzle scales directly, so
  the standalone "drizzle memory estimate" idea is done. (v0.25.0, this run)

- **Pre-run stack estimate endpoint** — new `GET /targets/{safe}/stack-estimate`
  (`drizzle`/`drizzle_scale`/`drizzle_reject`/`mosaic_canvas` query params) does a
  dry-run sizing: picks the reference, computes the reference-vs-union canvas the
  way `run_stack` does, and returns the output dimensions + estimated peak memory
  and the server budget, flagging `would_exceed`. The peak-memory maths is
  factored into a shared `_estimate_peak_bytes` so the warning can never disagree
  with the in-run `_guard_stack_memory`. The Stack form shows a live "Output
  canvas W×H · ~X GB peak memory" line and turns it into a red "over budget, run
  will be refused" alert when it would OOM — so a big drizzle/mosaic canvas is
  caught *before* the user hits Stack, not after. (v0.25.0, this run)

- **Outlier-safe drizzle** — new opt-in `drizzle_reject`: two-pass κ-σ
  rejection for the drizzle path (pass 1 drizzles values + squares for
  per-output-pixel contribution statistics, pass 2 zero-weights contributions
  outside mean ± κ·σ). Removes satellites/plane trails/cosmic rays that
  single-pass drizzle kept forever, without eating star cores under dither
  (output-space statistics cancel PSF-gradient systematics; verified to <2%
  star photometry). Plus drizzle parity/memory fixes shipped alongside:
  hot-pixel suppression and quality weights were silently ignored on the
  drizzle path, NaN input pixels were injected as zeros, and the unused
  drizzle context bitmask grew a full-canvas int32 plane per 32 frames with a
  full re-copy each time (tens of GB + quadratic copying on 5k+ sub stacks —
  now disabled). Memory guard charges the rejection pass; Stack form gained
  the toggle + a "sigma-clip doesn't cover drizzle" hint. (v0.24.0, this run)

- **Editable notes/label on History cards** — the long-standing `notes` column
  finally has a UI: a new `PATCH /api/targets/{safe}/stack-runs/{id}` (trims
  whitespace, empty → null, capped at 500 chars) plus `Project.set_stack_run_notes`.
  Each History card shows an inline pencil-edit label ("best RGB v2", "cloudy
  night") so users can annotate and later recognise runs. Additive/upgrade-safe.
  (v0.23.0, this run)

- **Mono single-frame edge test** — verified the mono stack path on a
  one-frame, sigma-clip-on stack: coverage tops at 1, the single-coverage
  pixels stay finite (no spurious clip-to-NaN), and the output stays grayscale.
  Closes the single-frame half of the mono NaN/coverage audit. (v0.22.1, this run)

- **Low-frame sigma-clip caution** — the Stack form now shows an inline caution
  when sigma-clip rejection is enabled but fewer than ~5 accepted, plate-solved
  frames exist ("you only have 3 accepted, solved frames … it can reject real
  signal as an outlier — consider turning it off"). Removes a knob a beginner
  can't reason about; advisory only, the setting still stands. (v0.22.0, this run)

- **Integration time inline on History cards + Reuse settings from Gallery** —
  `StackRunOut` now carries `total_exposure_s`, so each History card shows the
  friendly "2.3 h"/"42 min" integration on its metadata line without opening the
  Info panel (matching the Gallery). The Gallery response gained a `reusable`
  flag (false for editor-recipe/channel-combine runs), and Gallery cards now
  offer the same "Reuse settings" action as History, opening the Stack form
  pre-filled via `?from=<runId>`. (v0.21.0, this run)

- **Fix red CI (pytest-qt import crash)** — CI had been failing on every merge:
  the `pytest-qt` plugin imports Qt at configure time and died on the runner's
  missing `libEGL.so.1`, aborting the whole run before any test executed (the 3
  GUI test *files* were ignored, but the plugin still loaded). Added
  `-p no:pytest-qt` to the CI pytest command so the headless suite runs green,
  matching the documented local fallback. No app-code change. (this run)

- **Integration time on Gallery cards** — stack runs now record their effective
  integration time (median sub × frames combined) via a new additive
  `total_exposure_s` column (schema v3→v4 migration; old runs stay NULL). The
  gallery response exposes it and each card shows a friendly "2.3 h"/"42 min"
  next to the frame count — no per-card FITS read, so it scales. Extracted the
  shared `formatIntegration` helper to `frontend/src/format.ts`. (v0.20.0, this run)

- **Reuse stack settings from a previous run** — new
  `GET /stack-runs/{id}/options` returns a run's settings as a form-ready payload
  (knobs kept, `output_name` dropped so a rerun can't clobber the old output,
  calibration paths reverse-mapped to master ids). `StackRunOut` gained a
  `reusable` flag (false for editor/channel-combine runs); History cards show a
  "Reuse settings" button on reusable runs that opens the Stack form pre-filled
  via `?from=<id>`. Repeatability without re-deriving knobs. (v0.19.0, this run)

- **Warn on a mismatched calibration master pick** — the Stack form now shows an
  inline caution when a chosen dark's exposure is far (>25%) from the target's
  subs ("this dark was shot at 120 s but your subs are 30 s") and when a chosen
  flat-dark's exposure doesn't match the selected flat. Purely advisory — the
  pick is still honoured. Complements the recommender so a wrong pick doesn't
  silently degrade the stack. (v0.18.3, this run)

- **Auto-suggest a matching flat-dark** — `recommend_masters` now also returns
  `flat_dark_master_id`: the dark whose exposure best matches the *recommended
  flat* (flat-darks calibrate the flat, not the lights), gated so a wildly
  mismatched dark (e.g. 300 s for a 2 s flat) is never suggested. The Stack
  form's flat-dark selector badges it "★ recommended" and the one-click "Use
  recommended" now fills it in too. (v0.18.2, this run)

- **Drizzle flux-scale fix** — `DrizzleStacker.result()` no longer divides the
  already-averaged `out_img` by `out_wht` (the STScI drizzle library keeps
  `out_img` as a running weighted *average*, not a sum). The old double-normalise
  deflated drizzle brightness by ~N (the frame count) and threw an "overflow in
  divide" warning; drizzle at `scale=1, pixfrac=1` now conserves surface
  brightness and matches the weighted-mean path. Tightened the parity test from
  order-of-magnitude to <2× and added a multi-frame flux-conservation unit test.
  (v0.18.1, this run)

- **Auto-suggest calibration masters** — new `recommend_masters` ranks the
  library's dark/flat masters against a target's median frame exposure/gain/temp
  (darks match on exposure+gain+temp; flats are exposure-independent, matched on
  gain+temp), exposed via `GET /api/targets/{safe}/calibration-suggestions`. The
  Stack form badges the best-matching dark/flat with "★ recommended" and offers a
  one-click "Use recommended" — a beginner no longer needs to know which master
  goes with which lights. Advisory only; nothing is auto-applied. (v0.18.0, this run)

- **Stack info panel** — new `GET /stack-runs/{id}/info` reads the provenance
  cards from a run's `master.fits` (OBJECT, NFRAMES/NCOMBINE, EXPOSURE, EXPTOTAL,
  DATE-OBS/END, STACKER/STACKMTD, COLORTYP, EDITFROM…) and an "Info" toggle on
  each History card shows them, led by a friendly integration-time line
  ("Integration: 2.3 h · 840 subs"). No new storage — just a header read.
  (v0.17.0, this run)

- `run_stack` edge-case tests — single accepted frame (degenerate stack, coverage
  tops at 1, finite output), all-frames-rejected (raises cleanly instead of
  garbage), and a drizzle-vs-sigma-clip order-of-magnitude parity guard. The
  parity test surfaced a real drizzle flux-scale discrepancy, now filed as its own
  backlog item. (v0.16.3, this run)

- Editor-export provenance — the derived `master.fits` from an editor recipe now
  carries the source integration cards (OBJECT/NFRAMES/EXPOSURE/EXPTOTAL/COLORTYP/
  DATE-OBS/END) forward and records `STACKMTD="editor recipe (N ops)"` + `EDITFROM`
  (source run id), so an edited export self-documents in Siril/PixInsight/APP.
  (v0.16.2, this run)

- Channel-combine provenance — the LRGB/RGB combined FITS now carries
  `NCOMBINE` (source stacks) and `STACKMTD` ("channel-combine (RGB)"), matching
  the stack-export provenance headers. (v0.16.1, this run)
- Accessibility sweep — added `aria-label` to the remaining icon-only
  `ActionIcon` buttons (frame accept/reject, delete calibration master, delete
  preset) so they have accessible names for screen readers, plus a test
  asserting the delete-master button is reachable by name. (v0.16.1, this run)
- Channel-combine NaN fix — LRGB pixels covered in G/B/L but uncovered in a
  colour channel now become cleanly uncovered (NaN) instead of `[NaN, 0, 0]`
  (which zeroed real G/B signal at mosaic edges). Added NaN/coverage +
  single-pixel edge tests. (v0.16.1, this run)
- **Flat-dark support** — a master flat can now be dark-subtracted before
  normalising (`CalibrationMasters.load` gains `flat_dark_path`,
  `StackOptions.flat_dark_path`, server-resolved from a `flat_dark_master_id`).
  Removes the flat's dark-current/bias pedestal for a more correct flat; opt-in
  via a new Flat-dark selector on the Stack page. (v0.16.0, this run)
- **Dashboard stats caching** — `GET /api/stats` no longer re-opens every target's
  SQLite on each poll. The expensive per-target roll-up is cached on the app,
  keyed by a cheap registry signature (per-target activity stamp + latest preview)
  so a completed stack refreshes it promptly, with a 30 s TTL backstop.
  (v0.15.1, this run)
- **Settings backup & restore** — `GET /api/settings/export` downloads a portable
  JSON backup and `POST /api/settings/import` restores it; secrets and
  host-specific paths (data root, incoming/library, ASTAP path) are excluded so a
  backup is safe to share and restores on any install. Backup & restore panel on
  the Settings page. (v0.15.0, this run)
- **FITS output provenance headers** — `master.fits` now records OBJECT (target),
  NFRAMES, EXPOSURE (per-sub), EXPTOTAL (integration time), STACKER (method) and
  COLORTYP so the scientific output self-documents for Siril/PixInsight/APP.
  Additive `header_meta` arg on `write_stack_outputs`; defensive card merge.
  (v0.14.0, this run)
- CI safety net (`.github/workflows/ci.yml`) — full Python + frontend suites run
  on every PR and push to `main`; independent check on autonomous self-merges.

- **Autonomous run (agent, this session):** security fixes — Seestar `goto`
  RA/Dec bounds validation, closed a quick-look-preview gap in the
  `output_name` sanitizer (`_save_quick_look` built its own unsanitized
  filename), `react-router`/`form-data` CVE patches (`npm audit fix`) —
  plus `lucky_fraction` bounds validation, confirm+error-surfacing on
  stack-run deletion (`History.tsx`), job-cancel error feedback and a
  Logs-download filter bug (`Jobs.tsx`/`Logs.tsx`). Reconciled with a
  concurrent autonomous run that independently fixed the `bayer`
  path-traversal and `output_name` sanitizer issues and its own take on
  the `History.tsx` delete confirmation — merged rather than duplicated.
- **Autonomous run #1 (agent):** security + reliability/operability hardening +
  frontend error states — `output_name` sanitizer, `bayer` param validation, 404s
  for unknown targets, settings bounds (pydantic `Field` ge/le + 422), jobs-list
  clamp, shared `QueryError` component across 7 routes, editor-op pixel tests.
  (PR #28)
- Autonomous dev playbook (`AGENTS.md`) + this backlog.
- Mono stacking + LRGB/RGB channel combine — `StackOptions.mono`, `channel_combine`,
  combine job/endpoint, Channel combine page. (v0.12.0, `9485e28`)
- Star-mask-aware local edits — `edit/starmask.py`, mask-gated `stars.reduce`,
  new `stars.boost_nebula`. (v0.11.0, `d33c7c9`)
- Optional HTTP Basic access control (opt-in, PBKDF2, middleware). (v0.10.0, `7a995fc`)
- Dark/flat calibration — engine, master store, build job, API, UI. (v0.9.0)
- Keyboard shortcuts for frame grading on the Target page. (`2de2099`)
- Sigma-clip fix: no longer over-clips single-coverage (mosaic-edge) pixels. (`ab3883d`)
