# AGENTS.md — operating manual for autonomous work on AstroStack

This file is the operating manual for any agent (human or AI) doing unattended,
scheduled development on this repo. It did not exist before this document was
written — if you're reading it fresh, you're either the first autonomous run
or someone deleted it; either way, keep it up to date as the loop evolves.

## 1. What this project is

AstroStack / Seestack is an astrophotography stacker for the ZWO Seestar smart
telescope, built to handle 10,000+ raw subs without falling over (the thing
DeepSkyStacker can't do). It ships as:

- `seestack/` — the processing engine (io, qc, solve, align, bg, stack, post,
  edit) plus a PySide6 desktop GUI (`seestack/gui/`). Requires Qt at runtime;
  in headless CI/containers, run with `QT_QPA_PLATFORM=offscreen` and make
  sure `libegl1`/`libgl1` are installed or `pytest-qt` tests crash at collection.
- `webapp/` — a headless FastAPI service (no PySide6) that watches a dataset
  folder, auto-ingests/QCs/solves new Seestar frames, and exposes a REST+SSE
  API for the frontend. This is the primary deployable surface (TrueNAS /
  Docker) and where most user-facing value now accrues.
- `frontend/` — React + Vite + TypeScript SPA, built into `webapp/static/` and
  served by FastAPI as a single origin.

Read `PLAN.md` for the original engine design/rationale and `README.md` +
`docs/webapp.md` for the web service. `docs/glossary.md` is the beginner-facing
term glossary linked from the UI — keep it in sync with any new jargon you
introduce in either UI.

## 2. Pillars (what "value" means here)

Every backlog item and every commit should serve one of these. Tag backlog
entries with the pillar they serve:

- **Reliability** — correctness of the pipeline, no data loss, graceful
  handling of partial/malformed/adversarial input (half-written files, corrupt
  FITS, network drops mid-transfer), crash resistance under real Seestar
  device conditions.
- **Scale** — the 10k-frame promise: constant/bounded memory, streaming
  algorithms, job throughput, watcher performance on large datasets.
- **Usability** — plain-language UI, sensible defaults, presets, "Why?"
  panels, discoverability. The target user is a Seestar owner who is not a
  PixInsight expert.
- **Operability** — logs, health checks, job observability, safe restarts,
  TrueNAS/Docker deployment friction, config surfaces that don't require
  editing JSON by hand.
- **Security & data safety** — this is a LAN-exposed service with no auth by
  default watching a real filesystem. Path traversal, unbounded resource
  consumption, and destructive file operations are all in scope. Never trade
  safety for convenience.
- **Quality** — test coverage, lint cleanliness, type-checking, reducing
  flakiness/tech debt.

## 3. How to choose work

Score every candidate as **value ÷ (effort × risk)**:

- **Value**: how much it advances a pillar, weighted toward things a real
  Seestar owner would notice (a bug that loses a night's stack > a marginal
  UI polish).
- **Effort**: implementation + test size. Prefer S/M items most runs; only
  take an L item if nothing smaller scores comparably and you can still land
  it fully green within the run.
- **Risk**: chance of breaking existing behavior, chance the change is
  contentious (touches defaults, deletes data, changes on-disk formats),
  chance it can't be verified by the test suite alone.

Within `docs/IMPROVEMENTS.md`, prefer items with a clear pillar tag and size
estimate that are NOT in the "Needs owner sign-off" section. Do 3-6 per run
(fewer if one is genuinely large); each must land fully tested and green
before moving to the next.

## 4. Ideation guide — how to find new work

When the backlog runs low, generate new candidates by actually looking, not
guessing:

- **Read recent commit history** (`git log --oneline -30`) for patterns —
  repeated bug-fix commits in the same area usually mean a missing test or a
  structural gap, not just a one-off bug.
- **Grep for `TODO`/`FIXME`/`XXX`** across `seestack/`, `webapp/`, `frontend/src/`.
- **Read router/endpoint code for missing edge-case handling**: unbounded
  inputs, missing validation on path/query params (esp. target names / file
  paths — this app reads a real filesystem), missing error responses.
- **Read frontend routes for missing empty/error/loading states** — a route
  that renders nothing useful when a fetch fails is a usability gap.
- **Check `docs/glossary.md` against UI copy** for undefined jargon.
- **Look for perf hot paths** in `seestack/stack/` and `webapp/pipeline.py`
  that could regress at 10k frames — anything that isn't streaming/bounded.
- **Run `ruff check .`** — pre-existing lint debt is fair game for small
  cleanup tasks, but don't let a lint sweep replace substantive work.
- **Re-read this file's "Needs owner sign-off" list** before finalizing an
  idea — if it's on that list, write it up in the backlog but do not start it.

Add at least 1-2 new well-reasoned ideas to `docs/IMPROVEMENTS.md` every run,
each tagged with pillar + size (S/M/L).

## 5. Quality bar

- The full test suite (Python `pytest` + frontend `vitest`) must be green
  before you start and green again before you merge. If it's red at the
  start, fixing it is the first task of the run, before anything else.
- Every behavior change ships with a test that would fail without it.
- Never weaken, skip, delete, or reduce the scope of an existing test to make
  the suite pass. If a test is genuinely wrong (asserts old, superseded
  behavior you're intentionally changing), update it to assert the new
  correct behavior — don't just relax it.
- New/touched Python files should be `ruff check` clean for the lines you
  touched (pre-existing errors elsewhere are backlog material, not a blocker).
- Frontend changes: `npm run build` (tsc + vite build) must succeed; add a
  `vitest` test alongside any new component/hook with real logic.
- User-facing changes update `docs/webapp.md` and/or `docs/glossary.md` when
  they add a setting, endpoint, or new piece of jargon.
- Keep diffs additive and reversible. New features default OFF unless you're
  confident the on-by-default behavior is safe (no data loss, no surprising
  resource use, no behavior change for existing users' saved projects).

## 6. Git / merge policy

- Work happens on the branch the harness assigns for the session (currently
  `claude/friendly-lovelace-4327jj`) — never push directly to `main`.
- One commit per logical task, clear message, no bundling unrelated changes.
- Bump `pyproject.toml` `[project].version` (and `frontend/package.json`
  `version` if the change touches the frontend) with each shipped task —
  patch bump for a fix/small feature, minor bump for a larger feature. This
  repo has no changelog file yet; the git log + `docs/IMPROVEMENTS.md`
  "Shipped" entries are the changelog.
- Before merging: rebase/sync on the latest default branch, re-run the full
  suite, resolve conflicts without discarding either side's intent.
- To actually ship: open a PR from the working branch and merge it yourself
  via the GitHub API (`merge_pull_request`) once it's green and synced —
  nobody else will click merge. Only ever merge fully-green work.
- Never force-push, never skip hooks, never rewrite already-pushed history on
  a branch that might have a PR against it.

## 7. Environment setup

```bash
# Python engine + webapp (needs Python 3.12 specifically; pyproject pins
# >=3.12,<3.13 — use python3.12 explicitly if the default python3 is older)
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,web]"

# Headless container extras: PySide6/pytest-qt need libEGL at import time
# even though the webapp itself never opens a window.
apt-get update && apt-get install -y libegl1 libgl1 libxkbcommon0

# Run the Python suite headless:
QT_QPA_PLATFORM=offscreen python -m pytest -q

# Frontend
cd frontend
npm install
npm test              # vitest
npm run build          # tsc --noEmit && vite build -> ../webapp/static
```

Lint (not currently enforced in CI, but check before claiming "quality bar"
work): `ruff check .` — there is pre-existing debt (~127 findings as of this
writing); don't let it block unrelated work, but don't add to it either.

## 8. Guardrails (non-negotiable)

- Only ever merge fully-green work (Python + frontend suites both pass).
- Never weaken, skip, or delete tests to get to green.
- Never force-push; never break the default branch.
- Keep changes additive/reversible; new features default OFF unless clearly
  safe to default ON (no data loss, no surprising resource/network use).
- Do not touch anything in "Needs owner sign-off" below without explicit
  human approval — write it up as a backlog idea instead.
- This app reads/writes a real filesystem on behalf of the user (the mounted
  dataset). Never add code that deletes or overwrites source frames /
  `library/` outputs without an explicit, already-approved user action behind
  it. When in doubt about destructiveness, don't.

## 9. Needs owner sign-off (do NOT start these autonomously)

- Anything that changes the on-disk project/dataset layout or SQLite schema
  in a way that isn't backward-compatible with existing users' data.
- Adding authentication/authorization to the web service (changes the threat
  model and deployment story; needs a human decision on approach).
- Adding any outbound network dependency that isn't already present (e.g. new
  third-party API calls, telemetry, analytics) — this is explicitly a
  no-cloud-services, everything-in-house project (see `PLAN.md`).
- Changing default values for destructive or resource-heavy settings
  (`auto_stack`, `copy_to_cache`, cache eviction, anything that deletes
  files).
- Major version bumps of core deps (FastAPI, React, Vite, numpy/astropy/etc.)
  or swapping the plate-solver / stacking library.
- Docker/deployment topology changes (ports, volumes, compose service
  boundaries) beyond fixing a clear bug.
- Anything touching the real Seestar device network protocol
  (`webapp/seestar/`) without a way to verify it against real or recorded
  device traffic — silent protocol regressions are hard to detect from unit
  tests alone.
- Large refactors that touch >1 pillar's worth of code with no incremental,
  independently-testable steps.
