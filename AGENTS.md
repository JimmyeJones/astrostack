# Autonomous development playbook — AstroStack

This file tells an AI agent how to improve this app **on its own, with no human in
the loop**. A fresh agent starts **once an hour**; each run should complete
**several** well-scoped improvements, not just one. Read this file in full before
doing anything. It is the source of truth for *how to decide what to build and how
to ship it safely*. The living list of *what* to build is
[`docs/IMPROVEMENTS.md`](docs/IMPROVEMENTS.md).

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
history clean, and the backlog updated. Optimise for **many high-quality, fully
tested changes over time**. Each individual change is small and safe; each hourly
run lands a batch of them.

> Note: `PLAN.md` is the *original* desktop-era design. It is historical. The app
> has since grown a web layer, a non-destructive editor, dark/flat calibration,
> mono + LRGB stacking, and optional auth. Trust the code and `docs/IMPROVEMENTS.md`
> over `PLAN.md` when they disagree.

---

## 2. The run — do several tasks each hour

A run is an **outer loop over tasks**. Keep completing tasks until you run low on
time, run out of good candidates, or the only work left needs owner sign-off.
A healthy run lands **~3–6 tasks** (more if small, fewer if one is large — a
single big feature can legitimately be the whole run). **Never trade the quality
bar (§5) for task count.**

**Start of run (once):**
1. `git fetch`; read `docs/IMPROVEMENTS.md` and skim the last ~20 commits and open
   PRs/branches so you don't redo or collide with in-flight work.
2. Set up the environment (§7) and confirm the baseline test suite is green. If
   it's already red, fixing it is your first task — that outranks everything.

**Per task (repeat):**
3. **Choose** the next task with the decision framework (§3), or invent one with
   the ideation process (§4). Mark it **In progress** in `docs/IMPROVEMENTS.md`
   (with your branch) in the commit that starts it.
4. **Implement** it across all relevant layers (engine + webapp + frontend),
   matching existing style (§6).
5. **Test** everything (§5). Add tests for what you changed. No green, no ship.
6. **Commit** the task as its own logical commit; bump the version; move the item
   to **Shipped** in `docs/IMPROVEMENTS.md`. Re-run the suite so each commit is
   independently green.
7. **Push** and keep going to the next task.

**End of run (once):**
8. Add any new ideas you found to `docs/IMPROVEMENTS.md`, then **merge your green
   work into the default branch yourself** and clean up (§8). This project is
   zero-touch: no human reviews or merges, so shipping = merging. Then stop.

**Batching guidance:** group closely-related small changes onto one branch as
separate commits and one PR; put unrelated changes on their own branches/PRs so
each stays reviewable and revertible. If a task turns out huge, ship the first
safe slice and log the rest as a new backlog item — then move on.

---

## 3. How to decide what to work on (choosing among known candidates)

You are trusted to choose. Score each candidate on three axes:

- **User value** — does a real Seestar/astro imager notice and benefit? Correct
  results and "it finally does X" beat cosmetic tweaks.
- **Effort** — can you finish it *end-to-end with tests* within the run?
- **Risk** — how likely to break existing behaviour, corrupt data, or destabilise
  the hot path (ingest/stack)? Lower is better.

**Pick the highest `value ÷ (effort × risk)`.** When two are close, prefer:
finishing/polishing something half-done > fixing a correctness bug > improving a
hot path safely > new self-contained feature > cosmetic. Sequence a run to front-
load safe, high-confidence wins, then attempt one riskier/bigger item if time
allows.

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

---

## 4. How to come up with new features and ideas

Don't just drain the backlog — **replenish it**. Every run, spend some effort
generating genuinely new, valuable ideas and record them (with a why, a rough
size, and which pillar they serve). Aim to add at least a couple of well-reasoned
ideas per run. Here's how to find good ones.

### The three product pillars — every idea should push one
1. **Scale** — handle 10k+ subs, mosaics, big canvases without falling over.
2. **Correctness** — physically/photometrically right results (calibration,
   alignment, coverage, colour, noise).
3. **Approachability** — a non-expert gets a great result with sane defaults,
   plain-language options, and a "why". This is the app's edge over PixInsight.

An idea that advances one pillar without hurting the others is a good idea.

### Method A — walk the user's journey and find friction
Trace the whole path and ask "what's missing, confusing, or manual here?":
`capture → drop files → ingest → QC → plate-solve → stack → preview → edit →
export → share/compare`. Mentally dogfood each step for a beginner *and* for
someone with 8,000 subs of one target. Friction points are features:
missing feedback, no sane default, a manual step that could be automatic, a
failure with no guidance, a result you can't trust or compare.

### Method B — learn from mature tools, then fit our niche
Look at what established astro software does and adapt what fits a **headless,
web, beginner-friendly, scalable** product (not a pro desktop clone):
DeepSkyStacker, Siril, GraXpert (gradient/denoise), Starnet++ (stars), ASI Studio /
ASIDeepStack, Astro Pixel Processor, N.I.N.A., PixInsight. Translate a capability
into *our* idiom — automatic, explained, with presets — rather than exposing a
hundred knobs. Respect the guardrails (§9): anything needing heavy ML runtimes or
big model downloads goes to **Needs owner sign-off**, not straight into a build.

### Method C — mine the code and telemetry
- Settings/`StackOptions`/engine capabilities that have **no UI** yet.
- Editor ops that *could* exist next to the ones present (`edit/ops/`).
- FITS header fields we read but don't use; formats/cameras we don't support.
- Failure modes in logs and error strings — each is a "help the user avoid/fix
  this" feature (e.g. better guidance when a plate-solve fails).
- Half-built or TODO-marked seams.

### Method D — think in workflows, not knobs
The best features remove work or uncertainty: automation (auto-pick best subs,
auto-suggest settings from the data), trust (show what changed, let users compare
before/after or A/B two stacks), and repeatability (presets, saved recipes, batch
apply). Favour these over yet another slider.

### Feasibility filter (before adding an idea)
Keep an idea if it: fits the headless/web/TrueNAS model; needs no heavy/networked
dependency without sign-off; can ship with a sane default and a plain-language
explanation; is additive/reversible; and can be tested. Otherwise, either reshape
it until it passes or file it under **Needs owner sign-off** with the reason.

Record survivors in `docs/IMPROVEMENTS.md` → **Ideas**, tagged with the pillar
they serve and a size estimate, so future runs (and other agents) can pick them up.

---

## 5. Definition of done (non-negotiable quality bar, per task)

A task is shippable only when ALL of these hold:

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
      for features). One bump per task is fine.
- [ ] `docs/IMPROVEMENTS.md` updated (item moved to Shipped; new ideas added).
- [ ] Code matches surrounding style, comment density, and naming. New engine ops/
      settings stay JSON-safe and (for `StackOptions`) either have a form
      descriptor or are added to `NON_FORM_KEYS` (a drift test enforces this).

Every committed task must be independently green — so a bad one can be reverted
without unpicking the others. If you can't meet the bar, ship a smaller slice that
can, and log the rest.

---

## 6. Architecture map (so you know where things go)

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

## 7. Environment setup (the container is ephemeral)

Recreate tooling at the start of each run if missing:

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

> Tip: a `SessionStart` hook that runs the above makes every run reliable. If one
> doesn't exist yet, creating it is itself a good backlog item.

---

## 8. Git and shipping (zero-touch — no human reviews or merges)

This is a solo, autonomous project. **Nobody is going to review or merge your
work — so if you don't merge it, it never ships.** Your job is to get good,
tested changes onto the default branch by yourself, safely.

**Work on a branch, then merge it yourself:**

1. Start from the latest default branch:
   `git fetch origin && git checkout -B agent/<short-kebab-topic> origin/<default>`
   (the harness may create a branch for you automatically — that's fine; just make
   sure it's based on the current default). Use a fresh branch per topic; related
   small tasks may share one.
2. Commit each task as its own well-described commit. End every commit message with
   the repo's trailer convention (a `Co-Authored-By:` line; never put any model
   identifier in commits, code, or logs). Push after each task
   (`git push -u origin <branch>`); retry transient network errors with backoff.
3. **Before merging, make it green on top of the latest default:**
   `git fetch origin` → merge `origin/<default>` into your branch → re-run the full
   test suite (§5) and, if the frontend changed, the frontend build. Resolve any
   conflicts conservatively.
4. **Merge into the default branch** (fast-forward or a normal merge commit is
   fine), push the default branch, and delete your topic branch. Opening a PR
   first is optional and nice for history, but do not *wait* on it — merge it
   yourself once green.

**Absolute rules for merging:**
- Only ever merge a **fully green** branch. Green tests are the safety gate that
  replaces a human reviewer — treat §5 as mandatory before every merge.
- **Never force-push** the default branch or rewrite its history. Only add to it.
- If a merge conflict is non-trivial or you can't get green after syncing, **do
  not force it** — leave your branch pushed, note it in `docs/IMPROVEMENTS.md`, and
  move on. A stuck branch is fine; a broken default branch is not.
- One change per merge, each independently green, so any single change can be
  reverted later without unpicking the others.

---

## 9. Hard guardrails (never cross these)

- Never merge anything that isn't fully green (§5), and never force-push or rewrite
  the default branch's history. Merge via a branch (§8), don't commit straight onto
  the default branch.
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

## 10. Coordinating with other agents

A new agent runs every hour, so runs overlap in time and history. Avoid
collisions:
- Read recent `git log` and open PRs/branches first; skip topics already in
  flight.
- Keep branches small and single-topic so they rarely conflict.
- `docs/IMPROVEMENTS.md` is the shared blackboard: claim an item by moving it to
  **In progress** with your branch name in the same commit that starts the work;
  release it (to **Shipped** or back to **Ideas**) when you finish or abandon it.
- Prefer picking items *not* recently touched by another branch.
- Because everyone merges into the same default branch, always sync with the
  latest default and re-run tests right before you merge (§8) — another agent may
  have merged while you were working.

---

## 11. Run checklist (copy/paste)

```
Start of run:
[ ] git fetch; read IMPROVEMENTS.md + recent log + open PRs
[ ] env ready; baseline test suite green (if red, fixing it is task #1)

Per task (repeat ~3–6×, or fewer if large):
[ ] picked/invented ONE task (§3 decision rule or §4 ideation); marked In progress
[ ] implemented across engine/webapp/frontend as needed
[ ] added/updated tests; python + (if FE touched) tsc/vitest/vite build green
[ ] version bumped; IMPROVEMENTS.md updated (item → Shipped)
[ ] committed (independently green) and pushed

End of run:
[ ] added ≥1–2 new ideas to IMPROVEMENTS.md (§4)
[ ] synced branch with latest default; full suite still green
[ ] merged your green work into the default branch yourself; pushed; branch tidied
```
