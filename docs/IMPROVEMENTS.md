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
- **Feed `transparency_score` into quality weighting + a grader hint** — the
  per-frame metric is now computed (median flux of the brightest stars, shipped
  v0.33.0) and surfaced in the Target table, but nothing *uses* it yet. Next:
  normalise it against the target's best frame (a per-target baseline) and (a)
  optionally weight frames in the stack by relative transparency, (b) show an
  advisory "poor transparency night" hint when a run's median frame sits well
  below the target's clear-sky baseline. Needs care: the raw score isn't
  comparable across gain/exposure, so normalise within a target. (M, correctness)
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
- Per-target "notes/tags" search improvements and saved filters in Library. (S)

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
- Reduce the frontend bundle warning (code-split the heavy Sky/aladin chunks). (S)
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
