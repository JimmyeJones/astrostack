# AstroStack improvement backlog

The shared blackboard for autonomous development. Read
[`../AGENTS.md`](../AGENTS.md) first — it defines the loop, the decision
framework, and the guardrails. This file is *what* to build; AGENTS.md is *how*.

**Conventions**
- Sections: **In progress** → **Ideas** (roughly prioritised) → **Shipped** →
  **Needs owner sign-off**.
- A new agent runs hourly and lands **several tasks per run**. Claim each item by
  moving it to **In progress** with your branch name, in the same commit that
  starts it. Move it to **Shipped** (with the commit/PR) when done, or back to
  **Ideas** if you abandon it.
- **Replenish the backlog every run.** Using AGENTS.md §4 (the ideation process),
  add at least one or two well-reasoned new ideas per run so this list never runs
  dry. Keep entries to a one-liner with a short "why", a rough size (S/M/L), and
  the pillar it serves (scale / correctness / approachability).

---

## In progress

_(none — claim an item here with your branch name)_

---

## Ideas (pick roughly top-down; use the value ÷ effort×risk rule)

### Correctness & robustness (highest priority)
- **Photometric (multiplicative) frame normalization before combine** — frames
  are additively sky-zeroed per frame, but nothing gain-matches them: haze/
  airmass scale the *signal* (stars + nebula) frame-to-frame by tens of
  percent across a multi-night stack, inflating the per-pixel σ that κ-σ
  rejection clips against (weaker rejection on bright structure) and letting
  hazy nights dim the weighted mean. Estimate a per-frame scale from matched
  bright-star fluxes vs the reference (the `transparency_score` machinery is
  most of it) and divide it out before accumulation. Needs care: robust to
  few-star frames, neutral fallback, off by default first. (M, correctness)
- Per-pixel extremes / percentile rejection for small stacks (the *robust*
  fix for a lone satellite/plane trail below ~11 frames). **NB:** the previously
  filed "iterated κ-σ" idea was investigated and dropped — re-estimation clips
  against the *same* κ, and a lone outlier's deviation is `(n−1)/√n·σ` which is
  already below κ for n<11 (κ=3), so it escapes the first clip *and* every
  refinement round (verified: n=6→2.04, n=10→2.85, n=11→3.02). Mean/σ-based
  methods (including Winsorising) all hit this wall because the outlier inflates
  its own σ. The tools that actually reject a lone trail in a tiny stack are
  **order-statistic**: reject the per-pixel max (min/max clipping) or a top
  percentile before averaging, or use **median/MAD** as the location/scale.
  Needs care for uniform/low-coverage pixels (don't reject the only sample) and
  a streaming, memory-bounded implementation (the app deliberately avoids
  holding all frames). (M, correctness)
- Bias masters can be built but are never applied — `CalibrationMasters.load`
  only takes dark/flat/flat-dark. Wire bias in (and dark *scaling* by
  exposure ratio once bias exists) for mismatched-exposure dark workflows.
  (M, correctness)
- First-class session/night dimension in the project schema (frames only have
  `timestamp_utc`): per-session sky levelling before combine, per-session
  calibration binding, per-night QC roll-ups. Coverage-levelling's docstring
  already names "between sessions" as motivation but keys on coverage count.
  Large but high value for the multi-night Seestar workflow. (L, correctness)
- Channel combine: reproject stacks that don't share a canvas (via WCS) instead
  of erroring, so filters shot in separate sessions can be combined. (M–L)
- Seestar client (`webapp/seestar/client.py`) has no reconnect/retry on a
  dropped TCP socket — a flaky Wi-Fi link to the scope currently requires
  the user to manually reconnect via the UI. Core hardware-integration
  path; needs care around not spamming reconnect attempts and should be
  testable in isolation from real hardware. (M, correctness)

### Features that serve real workflows
- Compare-two-stacks web view (side-by-side / blink) to judge setting changes. (M)
- Annotated sky overlay (label detected objects / show solved field). (M)
### UX & polish
- Mobile layout polish across the newer pages (Calibration, Combine). (S)
- Better empty-states and error messages on long-running jobs. (S)

### Performance (only with a measurement)
- Profile the stack hot path on a large synthetic target; find a safe win that
  doesn't touch memory bounds or correctness. (M)

### Infra / maintainability
- Chip away at the ~127 pre-existing `ruff check .` findings (don't add new ones);
  consider wiring ruff into CI once the count is low. (L, correctness/maintainability)
- ~~Add a retention/pruning policy for `jobs.sqlite`~~ — **already implemented**
  (`JobManager._evict_old` prunes the DB to ~10× `max_history` after every job);
  a future refinement could make the cap a configurable setting. (S, scale)
- Add a `SessionStart` hook (or a `scripts/setup.sh`) that provisions the venv +
  `npm ci` so every autonomous iteration starts from a known-green baseline. (S)
- Expand `docs/` (webapp.md) to cover calibration, mono/LRGB, auth. (S)
- `npm audit` still reports `esbuild`≤0.24.2/`vite`≤6.4.2/`vitest`≤3.2.5
  (moderate — dev server only, not the production build) after this run's
  `react-router`/`form-data` fix. `npm audit fix --force` wants `vite@8`,
  a real major-version bump across the toolchain (config changes, full
  suite re-verification) — needs a deliberate dedicated pass per
  `AGENTS.md`'s major-dependency-bump sign-off rule, not a blind
  `--force`. (M)

---

## Needs owner sign-off (do NOT start autonomously)
- AI star removal (StarNet-class ONNX): high wow-factor but adds a heavy ML
  runtime + model download that may hit the network policy. Needs an explicit OK.
- Anything that exposes the app publicly, changes auth defaults (e.g. turning auth
  on by default), or is otherwise hard to reverse.
- Live capture / real-time Seestar streaming integrations (explicitly de-scoped).

_(Normal, tested changes merge to the default branch automatically — see
AGENTS.md §8. Only the items above need a human's OK first.)_

---

## Shipped
_Newest first. One line each: what + commit/PR._

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
