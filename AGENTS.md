# Autonomous development playbook — AstroStack

This file tells an AI agent how to improve this app **on its own, one iteration at
a time, with no human in the loop**. Read it in full before doing anything. It is
the source of truth for *how to decide what to build and how to ship it safely*.
The living list of *what* to build is [`docs/IMPROVEMENTS.md`](docs/IMPROVEMENTS.md).

If anything here conflicts with an explicit instruction from the user in your
session, the user wins. Otherwise, follow this document exactly.

---

## 1. Mission

AstroStack is a headless, TrueNAS/Docker-deployable astrophotography web app that
wraps the `seestack` stacking engine, aimed at ZWO Seestar owners (and, now,
mono/filtered imagers) who want to stack thousands of subs and edit the result
without being PixInsight experts.

Your job each run: **make the app meaningfully better for that user** — more
capable, more correct, more pleasant to use — and leave the tree green, the
history clean, and the backlog updated. Ship *one* well-scoped, fully-tested
improvement per iteration. Depth over breadth.

> Note: `PLAN.md` is the *original* desktop-era design. It is historical. The app
> has since grown a web layer, a non-destructive editor, dark/flat calibration,
> mono + LRGB stacking, and optional auth. Trust the code and `docs/IMPROVEMENTS.md`
> over `PLAN.md` when they disagree.

---

## 2. The loop (do this every iteration)

1. **Orient.** `git fetch`, read `docs/IMPROVEMENTS.md`, skim recent `git log`
   (last ~20 commits) so you don't redo or fight in-flight work. Get the current
   `webapp/__init__.py` `__version__`.
2. **Set up the environment** (§6) and confirm the test suite is green *before*
   you touch anything. If it's already red, your iteration's job is to fix it —
   that outranks new features.
3. **Choose one improvement** using the decision framework (§3). Prefer the
   highest value-per-risk item you can finish and fully test in this iteration.
4. **Plan briefly**, then **implement** across all relevant layers (engine +
   webapp + frontend) matching existing style (§5).
5. **Test everything** (§4). Add tests for what you changed. No green, no ship.
6. **Commit & push** to your own branch (§7). Bump the version.
7. **Update `docs/IMPROVEMENTS.md`**: move the item to "Shipped" with the commit,
   and add any new ideas you discovered while working.
8. **Open/refresh a PR** (§7) and stop. Do **not** merge to the default branch
   yourself unless §7's merge policy explicitly allows it.

One iteration = one focused, shippable change. If a task turns out to be huge,
split it: ship the first safe slice and record the rest in the backlog.

---

## 3. How to decide what to work on (make educated decisions)

You are trusted to choose. Score candidate work on three axes and pick the best:

- **User value** — does a real Seestar/astro imager notice and benefit? Correct
  results and "it finally does X" beat cosmetic tweaks.
- **Effort** — can you finish it *end-to-end with tests* in one iteration?
- **Risk** — how likely to break existing behaviour, corrupt data, or destabilise
  the hot path (ingest/stack)? Lower is better.

**Pick the highest `value ÷ (effort × risk)`.** When two are close, prefer:
finishing/polishing something half-done > fixing a correctness bug > improving a
hot path safely > new self-contained feature > cosmetic.

### Where to find candidates (in priority order)
1. **Anything broken or flaky** — failing/skipped tests, error logs, TODO/FIXME/
   HACK/XXX comments, `# noqa`d smells, swallowed exceptions.
2. **The backlog** — `docs/IMPROVEMENTS.md` "Ideas" section, roughly top-down.
3. **Correctness gaps** — places the math, NaN handling, coverage handling, or
   edge cases (empty input, single frame, mosaic edges, huge stacks) are wrong or
   untested. Astro correctness matters more than features.
4. **Coverage gaps** — modules/branches with thin or no tests; add tests *and*
   fix what they reveal.
5. **Real workflow needs** — what an imager actually does next: better previews,
   sensible defaults, clearer errors, batch operations, export formats, docs.
6. **Performance** — only with a measurement showing a real hot spot; never
   trade correctness or memory-safety for speed (this app has OOM history).
7. **Maintainability** — safe refactors that reduce duplication or clarify a
   confusing module, *when* they enable upcoming work.

### Judgment calls
- Prefer improving what exists over adding surface area. A great editor/stacker
  beats a pile of half-features.
- Respect the target user: every user-facing option needs a sane default and a
  plain-language explanation/tooltip.
- If you're unsure whether something is wanted, build the *conservative,
  reversible, opt-in* version and note the fuller version in the backlog.

---

## 4. Definition of done (non-negotiable quality bar)

A change is shippable only when ALL of these hold:

- [ ] Python suite green:
      `python -m pytest tests/ --ignore=tests/test_compare_dialog.py --ignore=tests/test_end_to_end.py --ignore=tests/test_footprint_view.py -q`
      (those 3 are Qt-GUI tests that need PySide6, absent in this env — leave them
      ignored; do **not** "fix" them by weakening anything).
- [ ] New behaviour has tests. Bug fixes get a regression test that fails before
      and passes after.
- [ ] If you touched `frontend/`: `npx tsc --noEmit` clean, `npx vitest run`
      green, and `npx vite build` succeeds.
- [ ] You did **not** delete, skip, loosen, or `xfail` a test to get green.
- [ ] `__version__` in `webapp/__init__.py` bumped (patch for fixes/polish, minor
      for features).
- [ ] `docs/IMPROVEMENTS.md` updated.
- [ ] Code matches surrounding style, comment density, and naming. New engine ops/
      settings stay JSON-safe and (for `StackOptions`) either have a form
      descriptor or are added to `NON_FORM_KEYS` (a drift test enforces this).

If you can't meet the bar this iteration, ship a smaller slice that can, and log
the rest.

---

## 5. Architecture map (so you know where things go)

- `seestack/` — the pure processing engine (no webapp imports).
  - `io/` — FITS load (`fits_loader.py`), ingest, `project.py` (per-target SQLite;
    additive migrations via `SCHEMA_VERSION` + `_migrate_schema`), `library.py`.
  - `stack/` — `stacker.py` (`run_stack`, `StackOptions`), `align.py` (per-frame
    load→calibrate→debayer→bg→reproject), `accumulator.py`, `drizzle_path.py`,
    `mosaic.py`, `channel_combine.py` (LRGB/RGB).
  - `calibrate/` — master dark/flat build + apply (raw-Bayer domain).
  - `edit/` — non-destructive editor: `registry.py` (op spec + `EditContext`),
    `ops/` (tone/detail/background/geometry/stars), `recipe.py`, `proxy.py`,
    `pipeline.py`, `starmask.py`.
  - `qc/`, `bg/`, `post/`, `solve/` (ASTAP), `render/`.
- `webapp/` — FastAPI layer. `main.py` (app + lifespan + auth middleware),
  `config.py` (`Settings` + atomic store), `jobs.py` (single-worker JobManager,
  SQLite-persisted), `pipeline.py` (job bodies), `watcher.py`, `deps.py`,
  `schemas.py` (adapts engine specs to the frontend), `routers/`, `calibration.py`,
  `auth.py`.
- `frontend/` — React + Mantine + TanStack Query + react-router. Descriptor-driven
  forms (`StackOptionControl`) render engine schemas generically, so many new
  engine params/ops surface in the UI with no frontend work. Routes in
  `src/routes/`, registered in `src/main.tsx`, nav in `src/App.tsx`.
  `webapp/static/` is the **build output — gitignored; never edit or commit it.**
- `tests/` — pytest; `tests/webapp/` uses a real Library/Project fixture (see
  `conftest.py`), `tests/synth.py` writes synthetic Seestar FITS.

Key invariants to respect:
- Engine functions stay free of `webapp` imports.
- `StackOptions` must stay JSON-serialisable (it's persisted in run records).
- The stack hot path is memory-bounded on purpose (OOM history) — don't
  accumulate unbounded per-frame results.
- Calibration master paths are resolved **server-side**; never accept raw
  filesystem paths from the client.
- NaN = "no coverage". Keep reductions NaN-aware; don't turn gaps into zeros.

---

## 6. Environment setup (the container is ephemeral)

Recreate tooling at the start of each iteration if missing:

```bash
# Python engine + webapp (uses a scratch venv; python3.11+ is fine)
python3 -m venv /tmp/astrotest && . /tmp/astrotest/bin/activate
pip install -q numpy scipy astropy photutils scikit-image Pillow tifffile \
  drizzle reproject astroalign ccdproc tqdm platformdirs matplotlib pydantic \
  fastapi "uvicorn[standard]" watchdog sse-starlette python-multipart pytest httpx

# Frontend
cd frontend && npm ci
```

PySide6/Qt is intentionally absent — the 3 GUI tests stay ignored. Put any
temp/scratch files under the session scratchpad dir, never in the repo.

> Tip: a `SessionStart` hook that runs the above makes every iteration reliable.
> If one doesn't exist yet, creating it is itself a good backlog item.

---

## 7. Git, branches, PRs, and merge policy

- **Never commit directly to the default branch.** Each iteration works on its own
  branch off the latest default:
  `git fetch origin && git checkout -B agent/<short-kebab-topic> origin/<default>`.
  Keep one topic per branch.
- Commit in logical, well-described steps. End every commit message with the
  repo's trailer convention (a `Co-Authored-By:` line; do **not** put any model
  identifier in commits, code, PR text, or logs).
- Push with `git push -u origin <branch>`; retry transient network failures with
  backoff.
- Open a PR describing what changed and why, how you tested it, and the risk. If a
  PR template exists, fill it in.
- **Merge policy (default: conservative).** Do **not** merge your own PR into the
  default branch automatically. Leave it green and open for review. Only merge
  autonomously if the repo owner has explicitly enabled that mode (branch
  protection + required CI green) — and even then, never force-push shared
  history and never merge a red PR. When in doubt, leave it for review and move on
  to the next branch/iteration.
- Do not open a second PR for something an open PR already covers — push follow-ups
  to that branch instead.

---

## 8. Hard guardrails (never cross these)

- Never weaken, delete, skip, or `xfail` tests to go green. Fix the code.
- Never break the ingest/stack hot path's memory bounds or NaN/coverage semantics.
- Never do anything destructive to a user's data. Prefer additive, reversible,
  opt-in changes. New features default **off** unless clearly safe on.
- Never add a heavy/networked dependency (e.g. large ML runtimes/models like an
  ONNX StarNet) or make an outward-facing/irreversible change on your own —
  record it in the backlog as "needs owner sign-off" instead.
- Never commit secrets or the `webapp/static/` build artifact. Never disable TLS
  verification or touch proxy/CA settings.
- Never regress the security posture (auth, server-side path resolution,
  input validation).
- Don't rewrite large subsystems speculatively. Refactor only in service of a
  concrete improvement, in small reviewable steps.
- Respect the ephemeral env: commit/push anything worth keeping; assume the
  container is wiped after the session.

---

## 9. Coordinating with other agents

Multiple agents may run this loop. Avoid collisions:
- Read recent `git log` and open PRs/branches first; skip topics already in
  flight.
- Keep branches small and single-topic so they rarely conflict.
- `docs/IMPROVEMENTS.md` is the shared blackboard: claim an item by moving it to
  "In progress" with your branch name in the same commit that starts the work;
  release it (to "Shipped" or back to "Ideas") when you finish or abandon it.

---

## 10. Iteration checklist (copy/paste)

```
[ ] git fetch; read IMPROVEMENTS.md + recent log
[ ] env ready; baseline test suite green
[ ] picked ONE item (value ÷ (effort×risk)); noted it In progress
[ ] implemented across engine/webapp/frontend as needed
[ ] added/updated tests; python + (if FE touched) tsc/vitest/vite build green
[ ] version bumped; IMPROVEMENTS.md updated
[ ] branch pushed; PR opened/updated; NOT merged to default
```
