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
- Audit NaN/coverage handling on the newer paths (calibration, mono) for
  single-frame and mosaic-edge cases. Add edge-case tests. (S–M) — *channel
  combine done (v0.16.1); calibration/mono still to audit.*
- Channel combine: reproject stacks that don't share a canvas (via WCS) instead
  of erroring, so filters shot in separate sessions can be combined. (M–L)
- Property/edge tests for `run_stack`: empty input, all-rejected, 1 frame,
  drizzle vs sigma-clip parity on a synthetic scene. (M)
- Seestar client (`webapp/seestar/client.py`) has no reconnect/retry on a
  dropped TCP socket — a flaky Wi-Fi link to the scope currently requires
  the user to manually reconnect via the UI. Core hardware-integration
  path; needs care around not spamming reconnect attempts and should be
  testable in isolation from real hardware. (M, correctness)

### Features that serve real workflows
- Auto-suggest calibration masters that match a target's frames (by exposure /
  gain / sensor-temp), so a beginner doesn't have to know which dark/flat/
  flat-dark goes with which lights. Registry already stores exposure_s/gain/temp
  on each master; surface a "recommended" badge and pre-select the best match in
  the Stack calibration picker. (M, approachability/correctness)
- Carry provenance headers into editor-export FITS too — `_apply_editor_to_run`
  writes a derived `master.fits` with no OBJECT/derived-from/recipe summary.
  Reuse the `header_meta` arg to record what it came from. (S, correctness)
- Show integration time + frame count on stack-run cards in History/Gallery now
  that the data is written (EXPTOTAL/NFRAMES); a beginner reads "2.3 h, 840
  subs" at a glance instead of digging into the FITS. (S, approachability)
- "Stack info" panel: read the FITS header cards (NCOMBINE/NFRAMES, EXPOSURE,
  EXPTOTAL, DATE-OBS/END, STACKER) from a run's `master.fits` and show them in
  the History detail view — no new storage needed, just a header read + a small
  endpoint. (S, approachability)
- Auto-suggest a sensible sigma-clip kappa (and whether to enable rejection)
  from the accepted-frame count — e.g. skip clipping under ~5 frames, loosen
  kappa for very large stacks — with a one-line "why" in the form. Removes a
  knob a beginner can't reason about. (M, approachability/correctness)
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
