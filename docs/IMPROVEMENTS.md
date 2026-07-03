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
- **Coverage overlay should follow the recipe's geometry ops** — the coverage-map
  overlay renders the run's *raw* full-frame coverage sibling, so once a crop/rotate/
  resize op is in the recipe it no longer lines up with the reshaped preview
  (v0.61.5 added an honest "shown for the uncropped frame" caption acknowledging
  this). The proper fix is to run the recipe's *enabled geometry ops* over the
  coverage map (via `apply_recipe` on a geometry-only sub-recipe, or reuse the same
  crop/rotate math) before the PNG, so the overlay tracks the edited image. Reuses
  the existing geometry ops; additive. Care: keep NaN = uncovered through the
  transform, and only apply geometry (not tone) ops. (M, editor/trust)
- **Wavelet-denoise preview↔export parity** — every other spatial op (sharpen
  radius, deconv PSF, bilateral spatial σ, background box) is corrected for the
  decimated preview proxy via `ctx.scaled_px`, but the **default** denoise method
  (`method="wavelet"`, also what Auto-process uses) has no size compensation: a
  BayesShrink multi-level DWT's effect scales with image dimensions, so a strength
  tuned on the ≤1500 px proxy smooths visibly differently on the full-res export.
  The wavelet branch decomposes the whole image, so there's no single "radius" to
  scale; a defensible fix is to cap the decomposition `wavelet_levels` to a
  proxy-independent count (e.g. tie it to a physical scale via `proxy_scale`) or to
  denoise the export on a matched-resolution pyramid. Needs care and a parity test
  (compare denoise on a full image vs its 2×/4× strided proxy). Off nothing (it's
  a correctness fix), but validate it doesn't weaken the clean-image case.
  (M, editor/correctness)
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
- **Guide lines on the histogram for the Stretch/clipping too** — the new
  `Histogram` `guides` prop (v0.65.0) draws the Levels black/white points; the same
  mechanism could mark the pure-black (0) and pure-white (1) clipping edges whenever
  the clipping caption fires, and the Curves op's endpoint handles, so *every* tonal
  control shows where it lands on the graph. Small, reuses the guides prop;
  frontend-only, advisory. (S, editor/trust)
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
- **A "Reset all points" / whole-op Auto for the Levels op header** — the Levels
  panel now has a header "Auto levels" (v0.64.0) that *sets* data-driven points, but
  no matching one-click to *undo* a bad manual drag back to the 0/1/1.0 identity
  (only the per-param reset icons and the degenerate-range fix exist). Add a small
  "Reset points" header action next to "Auto levels" that restores black=0, white=1,
  gamma=1 in one click, so a beginner who over-dragged has a clean escape hatch
  symmetric with Auto. Pure, reuses `setParams`; frontend-only, additive. (S,
  editor/friendliness)
- **Surface the measured midtone target on the gamma suggestion** — the new
  data-driven gamma button (v0.66.0) reads "From your image (midtones 1.6)"; like the
  sharpen/denoise buttons that name *why* (FWHM, noise σ), it could name the goal it
  solves for ("lands the sky at ~25% grey"), so the number has visible provenance and
  the beginner understands it's brightening the typical tone, not a magic value. Pure
  label change on the existing suggestion; frontend-only, additive. (S,
  editor/trust)

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
  small-stack hint, shipped v0.56.2; top/bottom-k trimmed-mean reject shipped
  v0.58.0.) No remaining sub-items.
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
- **Flaky CI: `test_detail_ops_preserve_nan_on_partial_coverage[detail.sharpen-params1]`** —
  this NaN-preservation test (v0.57.20) intermittently fails **on CI only** (it took
  down `main`'s CI on the PR #66 merge, run 28671857844; passes 15/15 locally and on
  the very next merge). The failure shows the *covered* region containing both a NaN
  and huge finite garbage (`7.7e37`, denormals) after `detail.sharpen` — the
  signature of uninitialized-memory / a platform-specific skimage/scipy quirk, not a
  logic bug in `_with_nan_filled` (which is provably correct: it fills per-channel,
  processes, then re-NaNs the border). **Do NOT "fix" it by scrubbing NaN in the
  covered region** — the garbage finite values would remain, so that would mask the
  corruption and ship a broken image to users. Investigate instead: pin/roll the CI
  `scikit-image`/`scipy`/`numpy` versions and try to reproduce under CI's exact
  build; if it's an skimage `unsharp_mask` float32+`channel_axis` bug, route the op
  around it (e.g. per-channel gaussian unsharp in pure numpy). (M, correctness/infra)
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
