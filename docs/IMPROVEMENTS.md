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
- **Replenish the backlog every run.** Using AGENTS.md §4, add one or two
  well-reasoned ideas per run — but only ones that serve the **§1 priorities**
  (1 editor, 2 autonomy, 3 friendliness, 4 image quality). Tag each with a size
  (S/M/L) and which priority it serves. Do **not** log niche mono/LRGB/
  channel-combine/narrowband ideas.
- **Priority order (from AGENTS.md §1) governs this list.** Work the top sections
  first. The editor is priority 1.

---

## In progress

_(none — claim an item here with your branch name)_

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
- **Confusing / clunky controls** — too many ops with terse params and no obvious
  starting point. Add plain-language help, a simple/guided default layout, curated
  presets, and progressive disclosure of advanced ops so a beginner gets a good
  result without understanding every knob. (M, editor)
- **Weak default result** — the auto/default processing should produce a genuinely
  good image out of the box for a typical Seestar OSC stack (good stretch, colour,
  gentle denoise/sharpen). Improve the auto recipe so "Auto" is a great one-click
  start. (Gentle SCNR green-cast removal added to the auto recipe in v0.56.6 —
  more of these incremental tweaks welcome.) (M, editor)
- **Editor bug hunt (ongoing)** — there are undocumented issues. Each big-picture
  run, use the editor end-to-end and fix what's broken/ugly: op failures, export
  mismatch, undo/state glitches, mobile layout, error handling. (ongoing, editor)

### Autonomy — "just works" (PRIORITY 2)
- **Auto-pick the object preset from the image** — Auto-process builds one general
  recipe, but the built-in presets (galaxy / nebula / cluster) are meaningfully
  different (per-channel vs luminance gradient, star reduction, saturation). The
  proxy analysis already computes sky/noise; extend it with a couple of cheap
  content cues (fraction of bright extended pixels vs point sources, colour spread)
  to *classify* the target coarsely and have Auto start from the matching preset's
  structure instead of a fixed op list — so "Auto" is tuned to what you actually
  shot. Keep the current general recipe as the fallback when classification is
  low-confidence. Off-by-default risk is nil (Auto is an explicit button). Needs a
  careful, well-tested classifier so it never mis-picks confidently. (M, autonomy/editor)
- **One-click "process this target"** — after ingest, reach a good stack *and* a
  good auto-edited preview with zero manual steps: QC → solve → auto-grade →
  stack → auto-edit, well-defaulted and safe. (M, autonomy)
- Auto-suggest stack settings from the data (frame count, FWHM spread, streaks)
  so the user rarely needs to touch the Stack form. (S–M, autonomy)

### Friendliness (PRIORITY 3)
- Guided "getting started" / empty states that tell a first-timer exactly what to
  do next; audit every screen for jargon and add plain-language "why" tooltips;
  reduce visible option clutter (progressive disclosure). (M, friendliness)
- Better long-job feedback and clearer error messages. (S, friendliness)

### Image quality — for the OSC Seestar workflow (PRIORITY 4)
- **Photometric (multiplicative) frame normalization before combine** — frames
  are additively sky-zeroed per frame, but nothing gain-matches them: haze/
  airmass scale the *signal* (stars + nebula) frame-to-frame by tens of
  percent across a multi-night stack, inflating the per-pixel σ that κ-σ
  rejection clips against (weaker rejection on bright structure) and letting
  hazy nights dim the weighted mean. Estimate a per-frame scale from matched
  bright-star fluxes vs the reference (the `transparency_score` machinery is
  most of it) and divide it out before accumulation. Needs care: robust to
  few-star frames, neutral fallback, off by default first. (M, correctness)
- Follow-ups to min/max reject (shipped v0.56.0). (Item (2), the Stack-form
  small-stack hint, shipped v0.56.2.) Remaining:
  - **Top/bottom-k trimmed-mean reject** — generalise `MinMaxRejectAccumulator`
    to drop the *k* smallest and *k* largest per pixel (opt-in
    `min_max_reject_count`, default 1 = exactly today's behaviour). Handles
    multiple satellite/plane trails crossing the same pixel across a session
    (k=3 → up to 3 trails) that a single-extreme drop leaves behind. Stays
    memory-bounded and single-pass by tracking the k smallest/largest as 2k
    canvas planes (vectorised sorted insertion), applying the full k-trim only
    where `count ≥ 2k+1` (so the two sides are disjoint) and degrading to the
    proven single min/max drop for `3 ≤ count < 2k+1`. NB: the earlier
    "percentile (drop p%)" and "median/MAD" framings are **not** streaming-
    feasible — an exact per-pixel median/percentile needs *every* frame's value
    held per pixel (tens of GB on a big canvas), which the OOM-bounded hot path
    forbids; the k-extremes trim is the memory-safe realisation. Must extend
    `_estimate_peak_bytes` / the memory guard to charge the extra 2k planes so
    the pre-run estimate stays exact. (M, correctness)
- **Dark exposure-scaling** (slice (b), now that bias is wired for lights) —
  `scaled_dark = bias + (dark − bias)·(t_light/t_dark)` so a dark shot at a
  different exposure than the lights can still be used. Needs the per-frame
  light exposure threaded into `apply_raw` (the harder part) and a neutral
  fallback (unscaled dark) when either exposure or a bias is unknown. Keep it
  opt-in and guard shape/exposure mismatches. Slice (a) — bias-only for lights
  when no dark is chosen, `(light − bias) / flat` — shipped v0.53.0.
  (M, correctness)
- First-class session/night dimension in the project schema (frames only have
  `timestamp_utc`): per-session sky levelling before combine, per-session
  calibration binding, per-night QC roll-ups. Coverage-levelling's docstring
  already names "between sessions" as motivation but keys on coverage count.
  Large but high value for the multi-night Seestar workflow. (L, correctness)

### Features that serve real workflows
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
- ~~Add a retention/pruning policy for `jobs.sqlite`~~ — **done, then made
  configurable** (`JobManager._evict_old` + the `job_history_limit` setting,
  v0.51.1). (S, scale)
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

_(Normal, tested changes merge to the default branch automatically — see
AGENTS.md §8. Only the items above need a human's OK first.)_

---

## Shipped
_Newest first. One line each: what + commit/PR._

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
