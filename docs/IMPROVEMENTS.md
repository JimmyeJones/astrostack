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
- Implement the dead `transparency_score` frame metric (declared in the DB
  schema and `FrameRow` since day one but never computed) — e.g. median star
  flux vs the target's per-star baseline — and feed it into quality weighting
  and an advisory "poor transparency" grader hint. Turns two schema fields
  into real value on cloudy-night data. (M, correctness)
- Iterated κ-σ rejection (both paths): a very bright outlier inflates the
  pass-1 σ enough that clipping can't fire below ~11 frames
  ((n−1)/√n < κ). One re-estimation round after the first clip would let
  small stacks reject trails too. (M, correctness)
- Bias masters can be built but are never applied — `CalibrationMasters.load`
  only takes dark/flat/flat-dark. Wire bias in (and dark *scaling* by
  exposure ratio once bias exists) for mismatched-exposure dark workflows.
  (M, correctness)
- First-class session/night dimension in the project schema (frames only have
  `timestamp_utc`): per-session sky levelling before combine, per-session
  calibration binding, per-night QC roll-ups. Coverage-levelling's docstring
  already names "between sessions" as motivation but keys on coverage count.
  Large but high value for the multi-night Seestar workflow. (L, correctness)
- Audit NaN/coverage handling on the newer paths (calibration, mono) for
  single-frame and mosaic-edge cases. Add edge-case tests. (S–M) — *channel
  combine done (v0.16.1); mono single-frame + sigma-clip verified (v0.22.1);
  calibration and the mono mosaic-edge (partial-overlap → NaN) case still to
  audit.*
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
- Drizzle memory estimate surfaced in the Stack form before you run it. (S)
- Star-mask preview toggle in the editor (visualise the mask driving star ops). (S)
- Per-target "notes/tags" search improvements and saved filters in Library. (S)

### UX & polish
- Mobile layout polish across the newer pages (Calibration, Combine). (S)
- Better empty-states and error messages on long-running jobs. (S)
- Keyboard shortcuts beyond the frame grader (e.g. editor undo/redo hints). (S)

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
