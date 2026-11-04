# Backlog — closed entries' stubs

Struck-through stubs of entries that had already shipped or closed (each one's full write-up is in
[`../SHIPPED.md`](../SHIPPED.md) or `SHIPPED-*` archives; its one-liner stays under `## Shipped`), moved verbatim
and in order out of the Ideas sections of [`../IMPROVEMENTS.md`](../IMPROVEMENTS.md) so the working list holds
open work only (AGENTS.md §2: archive, never delete). Newer moves go above older ones.

## Moved 2026-11-04 (Scout, branch `claude/exciting-wozniak-9ddn2i`)

*From `### Autonomy & friendliness (PRIORITY 2–3)`:*

- ~~**LEAD (Builder 2026-09-14, photographed on the bundled single field while shipping the v0.443.0 framing
  rung) — the readiness card still prices the canvas the coaching card has just told you to stop shooting.**~~
  — **✅ SHIPPED v0.444.2** (Builder 2026-09-14); entry cut to [`SHIPPED.md`](SHIPPED.md), one-liner under
  "Shipped" below. Built as the lead's shape (a), and its **"check first"** is what settled the gate: the
  question *"how often does a `partial` verdict co-occur with a readiness card?"* is already answered by the
  number v0.443.0 measured — `partial` fires on **any** object bigger than its canvas (95 % captured
  included), which is most of a big-object library, so the clause is gated on the *fragment* bar
  (`FRAMING_MAX_COVERAGE`) rather than on the verdict. Shared as one predicate, `framingIsFragment`, so the
  card that scopes the goal and the card that prescribes the wider framing cannot come to different opinions
  about which canvas is the right one.

*From `### Autonomy & friendliness (PRIORITY 2–3)`:*

- ~~**LEAD (Builder 2026-09-14, found by a `--mosaic --editor` dogfood pass that was otherwise CLEAN) — the
  coaching card and the framing card prescribe *different next sessions*.**~~ — **✅ SHIPPED v0.443.0**
  (Builder 2026-09-14); entry cut to [`SHIPPED.md`](SHIPPED.md), one-liner under "Shipped" below. Built as the
  lead's shape (a), a new `framing` rung, with the crowding-out risk answered by a coverage bar rather than by
  the verdict alone: `partial` fires just as readily at 95 % captured, so the rung asks for a third or more of
  the object to be *missing* (`FRAMING_MAX_COVERAGE = 0.67`). The lead's "check first" was carried out and is
  what set that bar.

*From `### Autonomy & friendliness (PRIORITY 2–3)`:*

- ~~**LEAD (Builder 2026-09-13, filed with v0.438.10) — a cropped export reports its depth against
  the canvas it has left.**~~ — **✅ SHIPPED v0.438.13–v0.438.14** (Builder 2026-09-13); entry cut to
  [`SHIPPED.md`](SHIPPED.md), one-liner under "Shipped" below. The lead's own first instruction was
  carried out first — measured on the bundled 2×2 mosaic against its `_framecov.fits` — and it answered
  the lead's open question: the two halves it separated really do diverge differently (the border trim
  +6.0 %, a content crop **+217 %**), but they take **one** rule, because reading the source stack's
  canvas is within 1.8 % / 12.8 % and errs *low* in both where the row's own canvas errs high.

*From `### Autonomy & friendliness (PRIORITY 2–3)`:*

- ~~**LEAD (Builder 2026-09-12) — the "Add more to what you're shooting" table loses its last column to a
  target's own `safe_name`.**~~ — **✅ SHIPPED v0.437.2** (Builder 2026-09-13); entry cut to
  [`SHIPPED.md`](SHIPPED.md), one-liner under "Shipped" below. Built as the lead's own shape and its Care note
  honoured exactly — the new `tonight.targetRowLabel` changes the **already-targeted branch only**, and the
  catalog rows still read `M31 — Andromeda Galaxy`. One thing the lead had not checked and the fix did: a
  renamed target's `name` and `safe_name` genuinely diverge (`rename_target` leaves the folder alone on
  purpose), and the name is the half a reader recognises — so the row shows it, and the safe name stays what
  it already was here, the link's destination.

*From `### Autonomy & friendliness (PRIORITY 2–3)`:*

- ~~**NEW IDEA (Builder 2026-08-30, the generalisation of the v0.311.3 "First light" bug) — sweep every date the app shows a beginner and ask whether it means *when you shot this* or *when the app did something*.**~~ — **✅ SWEEP FINISHED; cut to [`SHIPPED.md`](SHIPPED.md) 2026-09-11 (search "sweep every date") — do not re-pick it.** All five named surfaces are closed (Dashboard strip, keepsake and Target hero by earlier runs; the Gallery card and History row as v0.321.2; the Sky footprint line as v0.321.3), and the Library tile was measured to show no date at all — it reads `last_activity_utc` only to *sort*, which is the Care note's own exception. The rule that survives, and the only part still worth reading: **a stack run's own timestamp is right for "which run is newest" and wrong as the caption on a picture**; where both dates matter, say both ("shot 15 Nov 2024 · stacked 30 Aug 2026") and never flip a *sort* to capture time. `pictureDateLabel` / `formatStampDateTime` are the shared helpers — use them rather than slicing an ISO stamp.

*From `### Autonomy — "just works" (PRIORITY 2)`:*

- ~~**IMPROVEMENT IDEA (Builder 2026-07-25) — let the bootstrap anchor on an already-solved sub when a few
  (but < min_frames) subs did solve, instead of always re-solving the deep image.**~~ — **✅ SHIPPED v0.412.0**
  (`solve/bootstrap.pick_solved_anchor` + `BootstrapResult.anchored_on_solved_sub`). Entry in
  [`SHIPPED.md`](SHIPPED.md).

*From `### Autonomy — "just works" (PRIORITY 2)`:*

- ~~**NEW (Builder 2026-07-23, slice (c) follow-on to the shipped sibling-hint fill-in v0.180.0) — a *second*
  solve pass that retries first-round failures with the sibling hint at the tight radius.**~~ — **✅ SHIPPED
  v0.411.0** (`solve/runner.build_sibling_retry_arglist` + `scanner.run_qc_and_solve`'s
  `retry_unsolved_with_sibling_hint`). Entry in [`SHIPPED.md`](SHIPPED.md).

*From `### Image quality — for the OSC Seestar workflow (PRIORITY 4)`:*

- ~~**LEAD (Builder 2026-09-18, filed while shipping v0.464.0 — the third representative value, and the one the
  engine cannot see at all) — a gain-mismatched master dark is applied silently, and the run's own
  mismatch advisory is structurally unable to mention it.**~~ — **✅ SHIPPED v0.466.0** (Builder 2026-09-18, the
  same day). Entry cut to [`SHIPPED.md`](SHIPPED.md), one-liner under "Shipped". **The gate it was filed behind
  turned out to be the wrong question, and that is the part worth keeping:** the lead asked for a *gain
  tolerance* and rightly said no honest one exists in this repo — but a tolerance is what a *severity* verdict
  needs, and gain does not get one. An exposure has a correction (`scale_dark_to_light`) and a temperature is a
  continuous drift that earns a bar wide enough to cover a night; a gain is a **setting nothing anywhere
  corrects for**, and the app already treats it with zero tolerance in `_acquisition_reason`
  (*"it was shot at gain 200, your subs at gain 80"*, fired on `gain_d > 0`). So the advisory states both
  numbers instead of grading the gap, and `GAIN_MISMATCH_TOL` absorbs header round-trip noise and nothing else.
  Its shape (a) was built — `dark_gain` carried onto `CalibrationMasters` — and its (b) was built *with* it
  rather than instead of it, because the entry is right that (b) alone re-creates the form↔run split v0.464.1
  exists to close. The observer question it ends on is answered for free either way: the advisory is silent on a
  library shot at one gain, which is what a Seestar gives.

*From `### Image quality — for the OSC Seestar workflow (PRIORITY 4)`:*

- ~~**LEAD (Builder 2026-09-08, filed with v0.387.0 because it is the one thing that shipped unmeasured) — how
  long does the overlap gain pre-pass actually add to the owner's mosaic stack?**~~ — **⚪ CLOSED WITH THE
  NUMBER, measured 2026-09-28 at the owner's frame size; do not build the parallelisation.** Full write-up in
  [`SHIPPED.md`](SHIPPED.md) (search `overlap gain pre-pass timing`). **The headline: 285 s (4.8 min)** for a
  3×3 of 1920×1080 subs at 3.94″/px (S30: 150 mm, 2.1° field) onto a 3656×2816 union canvas, 4 cores, defaults
  (`background_flatten` and `suppress_hot_pixels` both on) — so the lead's own guess of "plausibly 1–3 minutes"
  was **low**, and it is ~all `align_one` (6.3 s per sub, flat). **Why it is still fine, and the one case where
  it is not:** the cost is 5 subs a panel, i.e. *one extra pass over ≤45 subs*, so on a mosaic of N subs the
  overhead is ≈ `5×panels ÷ N` — 1.3 % on a 3,600-sub raster, but **50 % on a 90-sub one**, i.e. night one on a
  fresh mosaic. The lever is exactly linear and available if that ever matters (`max_frames_per_panel=3` →
  **170 s**, 2.8 min, same 6.3 s per sub), and it is the right one: threads multiply this pass's peak memory on
  the path §6 names for its OOM history. **One thing the measurement showed that the lead did not predict:** the
  pre-pass pays the whole cost *before* it can decline — on the fixture it declined (unrelated stars across the
  overlaps, which is `MIN_OVERLAP_CORRELATION` working as designed) after spending all 285 s. So a night-one
  mosaic can pay 50 % overhead for nothing. Re-open only with a shape that decides *cheaply* whether to look.
  *(Original spec, kept for the reasoning:)* `overlapgain` runs up to
  `MAX_FRAMES_PER_PANEL = 5` subs per panel through `align.align_one` **sequentially** at stack setup — nine
  panels is 45 loads, each paying a debayer plus the per-frame `Background2D` fit, which is the expensive
  half. On this repo's fixtures it is seconds; on the owner's 1080×1920 subs it is plausibly 1–3 minutes,
  against a mosaic stack that runs for hours. That is very likely fine, which is exactly why it should be
  *measured* rather than pre-emptively parallelised: the obvious change (feed it the stacker's own
  `max_workers` pool) multiplies the pass's peak memory by the worker count on the one path §6 calls out for
  its OOM history. If a measurement ever says it matters, the cheaper lever is `MAX_FRAMES_PER_PANEL` — the
  ratio is a median over thousands of coarse cells, so 3 subs a panel would cost little accuracy — not
  threads. **Measure on real subs; the synthetic ones are 480×320 and prove nothing about this.**

*From `### Infra / maintainability`:*

- ~~**LEAD (Builder 2026-09-17) — no dogfood pass has ever held the owner's *scale*, and the probe measures
  the one dimension that hides it.**~~ — **✅ SHIPPED v0.455.3** the same run, as
  `scripts/agent-dogfood.sh --deep` + `scripts/dogfood_deep.mjs`. Entry cut to [`SHIPPED.md`](SHIPPED.md),
  one-liner under "Shipped". Its cost question was answered by measuring rather than guessing (per-frame QC is
  ~0.09 s at 160×120 against ~0.41 s at the field sample's 480×320, so 1,200 subs is ~2 minutes and the sensor
  is small for that reason and no other), and the drive was verified in **both** directions — it reported the
  windowed table on the fix and fired its own "ONE ROW PER SUB" detector on the window reverted. **The one
  thing it deliberately did not do, and the reason:** the entry's note about `AutoGradeModal`'s recommendation
  table (one row per flagged frame under a 25 % cap — ~1,369 rows on the owner's biggest target, ~6 nodes each,
  and only while the modal is open) stays a note. It is two orders of magnitude cheaper than the defect that
  prompted this, it is behind a deliberate click rather than on every page load, and `Stack.tsx` — the only
  other reader of the same complete frame list — renders none of it. So the frontend has **no** unbounded
  per-sub render left on a hot path; fix that one only if a `--deep` pass ever measures it as a problem.

*From `### Infra / maintainability`:*

- ~~**LEAD (Builder 2026-09-14, filed with v0.445.2/v0.445.3 — the fifth instance of the same hole, and the
  first one that hides a whole *subsystem* rather than one card) — every dogfood sample fits inside the
  preview proxy, so the editor's entire decimated-proxy surface has never been rendered in a browser.**~~
  — **✅ SHIPPED v0.446.0** (Builder 2026-09-14) as the lead's own named lever, a third opt-in
  `load_sample(shape="big")` + `scripts/agent-dogfood.sh --big`; entry cut to [`SHIPPED.md`](SHIPPED.md),
  one-liner under "Shipped" below. **Its "measure before scoping" was carried out first and is what set the
  size:** 900×600 panels give a 1694×1150 union canvas and `proxy_scale` exactly **2** — the smallest canvas
  that reaches the surface at all — measured at **61.5 s** of stack (vs 19.0 s for the small mosaic), so the
  flag costs about a minute rather than the twenty the lead worried about. The two existing samples are
  pinned **byte-identical** by digest, not by argument. Original reasoning kept below.
  *(Pillar: maintainability in service of not missing bugs — size M; **measure before scoping**. Confidence:
  arithmetic, checked this run against `sample_data._WIDTH` and `PROXY_MAX_PX`; not yet reproduced by
  building a bigger sample.)*
  `seestack/edit/proxy.py` decimates above **1500 px**. The field sample is `_WIDTH = 480`; the `--mosaic`
  sample's union canvas is ~907×615. Both give `proxy_scale == 1.0` — i.e. **`get_proxy` never strides on
  either sample**, and everything gated on a strided proxy is structurally unreachable by
  `scripts/agent-dogfood.sh`, including `--editor`, which clicks every op in the Add menu: the five
  preview↔export advisories (`sharpen_preview_understates`, `deconv_…`, `denoise_…`,
  `hot_pixels_preview_skipped`, `star_reduce_preview_overstates`), **and the whole of `FullSizeCheck`** — its
  button, its modal, its navigator, its `X-Loupe-Window` marker and its split comparison, ~250 lines of the
  priority-1 screen, none of which any pass has ever drawn. The owner's mosaics are ~3494×2470 and up, so
  this is his everyday state and the tooling's permanent blind spot. Both fixes shipped this run were found by
  *reading* for that reason, and both are pinned only by jsdom.
  **The lever, and the cost that has to be measured first:** `load_sample(shape=…)` already takes a shape, so
  a third opt-in shape (or a `--big` flag scaling `_WIDTH`/the panel step) is the shape of the fix — the
  `--mosaic` (v0.386.0) and `--incoming-lag` (v0.442.1) precedents both did exactly this. It must stay
  **opt-in and leave the two existing samples bit-identical**: the field sample's generated pixels are pinned,
  and the page-height baselines in `PROCESS-NOTES.md` are measured on it. What is *not* known is the stacking
  cost — a canvas over 1500 px on its short side means panels ≥ ~4× today's pixel count, and a dogfood pass
  that takes twenty minutes will stop being run. Measure one stack at the smallest canvas that strides
  (≈1600 px wide, `proxy_scale` 2 — the `tests/webapp/test_editor_loupe.py` fixture uses exactly 1600×900 for
  this reason) before scoping anything larger.

*From `### Infra / maintainability`:*

- ~~**LEAD (Builder 2026-09-12, filed with v0.435.0 because it is what that fix could not reach) — the
  bundled sample cannot light up the whole "PLAN A NIGHT" half of the app, so no dogfood pass has ever
  seen those screens with data.**~~ — **✅ SHIPPED v0.436.1** as the entry's own shape (a), and it found
  two things on its first pass; entry cut to [`SHIPPED.md`](SHIPPED.md). Original text kept below for the
  reasoning, which stands: *(Pillar: maintainability in service of not missing bugs — size S to
  measure, and **read the caution before building anything**. Confidence: reproduced in a browser this
  run.)*
  `tests/synth.write_seestar_fits` writes no `SITELAT`/`SITELONG` unless asked, and `webapp/sample_data`
  never asks — so with both samples loaded and stacked, `_resolve_observer` reports `"none"` and
  **Tonight, the Sky Map's placement, the life list's "Up tonight" chip, the wishlist's "the Tonight page
  will tell you when", `/api/plan/closing`, `/api/plan/week` and `/api/life-list/nearly-there` are all in
  their empty state**. Every "dogfood CLEAN" ever recorded was therefore a statement about the half of the
  app that does not need a site. That is a real coverage hole — v0.433.0, v0.430.0 and v0.426.0 all shipped
  into that half in the last week.
  **⚠ The obvious fix is the wrong one: do NOT write a site into the sample's headers.** A location in a
  frame header is not decoration — `_resolve_observer` *plans from it*, so a sample claiming to have been
  shot from Greenwich would silently tell an owner in Sydney which targets are up, computed for the wrong
  hemisphere, with only `location_source: "fits"` anywhere on the wire to say so. The sample is a demo, not
  a measurement, and the app has no way to mark a location as "pretend".
  **Shapes that might be honest, none of them checked:** (a) make it a *dogfood-only* step — the script
  `PUT`s a site into Settings on its own scratch install before probing, which is what a real owner's
  library supplies and touches no shipped data; (b) have `POST /api/sample` take an optional explicit
  location the caller chooses, defaulting to none, so the demo only ever plans from a site somebody asked
  for. (a) is nearly free and closes the coverage hole; (b) is a product decision and probably not worth
  it. Either way the sample's generated pixels must stay bit-identical (pinned since v0.386.0).

*From `### Infra / maintainability`:*

- ~~**LEAD (Builder 2026-09-15, filed with v0.447.0 because it is the axis that fix sits on rather than the fix
  itself) — `seam_residual` was one stored measurement whose estimator moved under it; nothing has asked which
  of the others did.**~~ — **✅ SWEPT AND CLOSED 2026-09-17 (Builder). One finding, shipped as v0.454.0
  (`transparency_ratio`); the other eight columns are non-findings or already dated. Read the two ↳ blocks
  below before re-opening — the whole point of this entry was to ask the question once.** *(Pillar: trust — PRIORITY 3/4; size S to *ask*, unknown to fix; **do not start by
  writing code**. Confidence: the axis is demonstrated — v0.313.1 is one confirmed instance, measured on the
  owner's library at 25 of 38 controlled pairs changing verdict; ~~whether there is a second is **not**
  checked~~ — there was exactly one, and it is fixed.)*
  A `stack_runs` row carries a dozen numbers measured **at stack time** and read, years later, through
  thresholds that live in today's code: `noise_sigma`, `stack_fwhm_px`, `transparency_ratio`,
  `rejection_fraction`, `grain_ratio`, `coverage_thin_frac`, `uncovered_frac`, `coverage_median_depth`,
  `duration_s`. Each is a *number with an estimator behind it*, and the estimator is in the repo while the
  number is in the owner's database — so any change to one silently re-scales every stored row, and every
  surface that compares two runs ("your cleanest stack", the Compare verdicts, the History chips) is comparing
  two quantities. The app already knows this in two places and neither generalises: `coverage_shares_version`
  versions the coverage shares and **re-derives** a stale one, and `seam_scale` (v0.447.0) dates the seam
  figure and heals it. Everything else is undated.
  **The work is a question before it is a change.** For each column: has its estimator moved since rows were
  written, and if so in which direction? `docs/SHIPPED.md` is the usable record — the repo clone an agent gets
  is **shallow**, so `git log -L` on the estimator will not answer it (that is what stopped this run going
  further). Two known leads to check first: `noise_sigma` goes through `seestack.edit.noise.estimate_noise_sigma`,
  which the editor's own noise measurement also feeds, and v0.225.0 changed how sky noise is measured on the
  *proxy* (MAD of adjacent-pixel differences, because the old form counted a mosaic's panel offsets as grain) —
  **check whether that change reached the estimator the stacker stamps, because `noise_sigma` is the number
  History ranks "cleanest" by and the walk-away degradation report was read off it**; and `grain_ratio`, whose
  own docstring argues its σ was *chosen* to survive a decimated read, i.e. somebody has already thought about
  its estimator once. **Only file a bug for a column where the change is actually found**, with the direction
  measured the way v0.447.0 measured the seam's (`se >= 0` on both ends, so one-sided) — a one-sided change can
  be *read* around, a two-sided one needs the heal. Do not add a version column to a measurement nobody has
  shown moved: that is nine migrations for a hypothesis.
  **↳ THE FIRST NAMED LEAD IS ANSWERED, AND IT IS A NON-FINDING — don't re-trace `noise_sigma` (Builder
  2026-09-17, read in the code and in this repo's own shipped record, which is what the lead says to use
  because the clone is shallow).** v0.225.0 did **not** change `edit.noise.estimate_noise_sigma`; it changed
  `presets.analyze_proxy`'s `sky_sigma` to *start calling* it. Its own entry says so in as many words — *"the
  same estimator already behind the editor's 'From your image' denoise suggestion, so the two halves of the
  crossfade finally measure the same thing"* — and the old form it replaced (`1.4826·MAD` of the sky's
  **levels**) has no other caller. `stacker._compute_noise_sigma` has gone straight to
  `estimate_noise_sigma` all along, so the column the History "cleanest" ranking and the walk-away degradation
  report are read off is stamped by an estimator whose formula has never moved. Two near-misses checked and
  cleared with it: `analyze_proxy` applies `_SKY_HALF_MAD_SCALE = 0.593` and `_compute_noise_sigma` does not,
  which is two scales for two consumers rather than drift in one; and the v0.354.1/v0.354.2 rounding fix is on
  the float→uint *pack*, downstream of the float array this σ is measured on. **`grain_ratio` and the other
  seven columns are still unchecked**, so the entry stays open — just not on this lead.
  **↳ LEAD TWO IS A FINDING, AND IT SHIPPED AS v0.454.0 (Builder 2026-09-17): `transparency_ratio`.** Its
  estimator moved in **v0.304.2** — `stacker._compute_transparency_ratio` stopped dividing a mosaic run's
  median by one target-wide `p90` and started comparing each panel against its own
  (`_panel_transparency_ratios`) — and, exactly as this entry predicts, the fix re-measured nothing and dated
  nothing while `HAZY_RATIO = 0.6` went on living in today's code. Reproduced on the fixture the fix itself
  ships: a steady-sky 3-panel mosaic stores **0.5001** and measures **0.9996** today. Direction measured the
  way this entry asks: **two-sided** (300 randomised mosaics, today's figure higher on 251 to +0.72, lower on
  49 to −0.27), so unlike the seam there is no half to read around and the rule is silence. Entry in
  [`SHIPPED.md`](SHIPPED.md).
  **✅ AND THE REST OF THE COLUMN LIST IS SWEPT, ALL NON-FINDINGS — the entry is CLOSED; do not re-trace it
  (same run, read in the code and in this repo's own shipped record, which is what the entry says to use
  because the clone is shallow).** Nine columns, one finding:
  - `noise_sigma` — cleared above (lead one).
  - `grain_ratio` + `grain_thin_frames` / `grain_deep_frames` / `grain_thin_share` — shipped **with**
    `measure_coverage_grain` itself in v0.406.0, and nothing has touched the estimator since. The later grain
    work (v0.406.2 and the shortfall gate) changed the *sentence* `stack_health` writes, never the σ; the
    `_robust_stats` it borrows last moved in v0.313.1, i.e. before the column existed.
  - `stack_fwhm_px` — `_compute_stack_fwhm` goes through `qc.metrics.detect_stars` / `median_fwhm` /
    `estimate_sky`, and the only post-v0.194.0 change to any of them is v0.345.4's `sigma_clipped_stats_finite`,
    whose own entry pins that the masked call returns **bit-identical** `(mean, median, std)` — "silence, not a
    new number". The `median_eccentricity` / `green_channel` fixes are v0.109.10, before the column.
  - `rejection_fraction` — not an estimate at all, but a tally of what the combine that ran actually rejected.
    Two runs differing here differ in their *pixels*, which is the honest reading.
  - `duration_s` — a wall clock.
  - `coverage_thin_frac` / `coverage_median_depth` / `uncovered_frac` — the one family that **was** already
    dated, and correctly: `coverage_shares_version` (v0.389.2) versions the thin reference and
    `coverage_backfill.backfill_coverage_shares` re-derives a stale run from the map still beside its master,
    dropping the share in memory when the map has gone. `uncovered_fraction` has not moved since v0.377.0.
  So the axis this entry named is real — it produced `seam_residual` and now `transparency_ratio` — and it is
  **exhausted against today's column list**. Re-open it only when a *new* estimator change ships against a
  stored column, which is the moment to stamp a generation beside the figure rather than the audit to repeat.

*From `### Infra / maintainability`:*

- ~~**NEW IDEA (Builder 2026-09-03, spotted while adding the sibling channel in v0.328.2) — `EditContext.op_notes`
  is keyed by op **id** where its new sibling `fitted` is keyed by op **uid**.**~~ — **✅ SHIPPED v0.475.2.**
  Entry cut to [`SHIPPED.md`](SHIPPED.md), one-liner under "Shipped". Two things the entry asked for and the
  build answered, kept here only because they change how the *next* entry of this shape should be read:
  **its "check first" was the whole size of it** — a double-op recipe *is* reachable (`Editor.tsx::addOp` has
  no duplicate guard, so two **Color calibration** ops is two clicks), which turns "an XS tidy-up" into a
  priority-1 parity fix; and the defect is **one field, not the note** — reporting the *last* instance's
  `mode_used` is right (a second calibration runs on top of the first), while `proxy_fallback` is a
  preview-vs-export warning that has to be **any** instance's, or the advisory silently disappears when the
  *first* op is the one that fell back. The entry's claim that `seestack/edit/ops/detail.py` writes `op_notes`
  too is **stale** — its advisories moved to `fitted` before this; `tone.color_calibrate` was the only writer.
