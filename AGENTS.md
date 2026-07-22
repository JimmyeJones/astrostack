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

## Agent roles — Builder & Scout (read this first)

This project is developed by **two kinds of autonomous agent** that share this
manual and one backlog (`docs/IMPROVEMENTS.md`). Each scheduled run is told which
role it is by its kickoff prompt: [`docs/agent-prompt.md`](docs/agent-prompt.md)
for the **Builder**, [`docs/agent-prompt-scout.md`](docs/agent-prompt-scout.md)
for the **Scout**. Everything else in this file — the priorities (§1), the quality
bar (§5), git/shipping (§8), upgrade-safety (§9), and the guardrails (§10) —
applies to **both** roles.

- **Builder** (the workhorse — schedule it often, e.g. hourly). *Drains* the
  backlog: picks the highest-priority item, implements it **deeply** with tests,
  and ships it to `main`. Bugs in "Bugs (fix these first)" outrank everything.
  Favours a few well-finished tasks over many shallow ones. It does not spend a run
  inventing features — that's the Scout's job — but it fixes bugs it trips over
  and, if the backlog is running thin on ready work, tops it up so it never idles.

- **Scout** (the planner + QA — schedule it a few times a day). *Fills* the backlog
  with high-value, vetted work for the Builder. It mostly **thinks and writes to
  the backlog rather than shipping code**: it dogfoods the whole app as the target
  user (§1), runs a focused adversarial QA audit of one subsystem (editor first),
  files **verified** bugs (repro + severity + confidence) into "Bugs (fix these
  first)", and curates the backlog — reprioritising, pruning stale/duplicate/done
  items, and adding a few well-reasoned feature ideas (§4). It may fix one small,
  obviously-safe bug it finds, but leaves real building to the Builder.

**Why two roles:** finding real bugs and planning good features is a different mode
from writing code; doing all three in one rushed hour makes each shallow. A
dedicated Scout keeps the Builder supplied with vetted, high-value work, so the
Builder can go deep instead of context-switching. **Minimum viable setup: just run
the Builder** — it self-tops-up the backlog. Add the Scout when you want markedly
better bug-finding and planning; its output is what makes the Builder's runs count.

**Staying out of each other's way:** the Builder edits code and moves items to
**Shipped**; the Scout edits the backlog. Both obey the coordination rules in §11
(claim an item by moving it to **In progress**; sync with `main` and re-run tests
right before merging). Small, single-topic branches keep them from colliding.

---

## 1. Mission & product vision (read this first — it governs everything)

AstroStack is a headless, TrueNAS/Docker web app around the `seestack` engine for
**one specific person: a ZWO Seestar owner shooting one-shot-colour (OSC), who has
thousands of subs and wants a beautiful final image without becoming a PixInsight
expert.** Everything is judged by whether it helps *that* person.

**North Star:** drop your Seestar frames in → get a great-looking, trustworthy
image out, with as little fuss as possible.

**Priorities, in strict order (the owner set these).** When choosing what to do,
higher on this list wins — always:

1. **Make the editor excellent.** The non-destructive editor is where a good stack
   becomes a good *picture*, and today it has real problems (live preview that
   doesn't match/behave, clunky and confusing controls, and a weak default
   result). **Go deep here: hunt and fix its bugs, make the controls obvious, and
   make the out-of-the-box result genuinely good.** Fixing/polishing the editor
   outranks any new feature.
2. **"Just works" autonomy.** Drop files in and get a great result with minimal
   clicks — smarter, well-defaulted auto-grade / auto-stack / auto-calibrate /
   auto-edit. Reduce the number of decisions the user must make.
3. **Overall user-friendliness.** Clearer screens, plain-language guidance,
   sensible defaults, good empty/error states, less clutter. A beginner should
   never be confused about what to do next.
4. **Best-possible image quality** for the OSC Seestar workflow (clean, detailed
   final images).

**⚡ IMMEDIATE PRIORITY (owner-reported 2026-07, real data on v0.158): auto-stacked
FINAL results come out as single-frame colour-speckle "gibberish" for faint/
sparse-star targets** (a bright galaxy stacks cleanly — so it's data-dependent).
See the ⭐⭐ top entry in `docs/IMPROVEMENTS.md` → "Bugs (fix these first)". The
data-dependence points away from a render/debayer bug and toward **the auto-pipeline
combining too few frames** (plate-solve failing on faint fields and/or over-aggressive
auto-reject/grade — note v0.149 defaulted `auto_reject` ON for a never-configured
form), so the "stack" is ~1 sub and noise never averages out. **Instrument the real
accepted+solved+surviving frame count on a faint target, find the over-dropping
stage, fix it, and add a minimum-frames guard + honest "only N of M frames stacked"
warning.** Reproduce with synthetic noisy few-star subs (output noise must fall
~√N). This is the front-of-queue focus right now. (Earlier immediate priorities —
bright-core/STF autostretch and the Sky-map bugs — are both fixed; see their
struck-through backlog entries.)

**Current focus (2026-07 — set by the owner).** The editor (priority 1) is now
**well-hardened**: its traced bug backlog is drained and repeated adversarial
re-audits come back clean. That rule still stands — if a *real* editor regression
appears, fixing it comes first — but the editor no longer needs feature-piling,
and the highest *marginal* value has moved to:
  1. **QA and harden the stacking engine itself.** Deeply audit and fix the
     `seestack/stack/` path (`align.py`, `stacker.py`, `accumulator.py`,
     `mosaic.py`, `drizzle_path.py`, rejection) and `seestack/calibrate/`. A bug
     here silently corrupts the *final image* on a live install — this is
     correctness / data-integrity work, so **treat a verified stacking-engine bug
     like an editor bug: fix it first**, ahead of any polish.
  2. **Autonomy, friendliness, and image quality (priorities 2–4).** Smarter,
     better-defaulted auto-stack / auto-calibrate / auto-grade; clearer screens,
     guidance, and empty/error states; and cleaner final images for the OSC
     workflow.
  3. **Genuinely new *beginner* features (owner-requested rebalance, 2026-07).**
     The app is mature enough that it should also *grow*, not only harden — so on a
     regular cadence, propose and ship **new user-facing capabilities that help a
     beginner plan, get, understand, enjoy, and share a good image**: e.g. night
     planning, target progress tracking, session/night views, sharing or exporting
     a finished picture, guided end-to-end workflows, mobile-friendly capture-night
     views, annotated results. Use §4 to invent them; hold each to the **beginner
     bar** below. This is a real, standing allocation of effort — don't let the
     fix/polish default crowd it out. The Scout files new feature ideas each run;
     the Builder pulls one from the "Features that serve real workflows" list on a
     regular cadence, not only when the bug list is empty.

**Beginner bar (what a "new feature" must clear).** It qualifies only if a
*non-expert Seestar OSC owner* would understand it and use it to get, enjoy, or
share a better picture with less effort — and it ships with a sane default and a
plain-language explanation. It is **not** pro/niche tooling: no
mono/LRGB/channel-combine/narrowband, no PixInsight-style expert knobs, nothing
that only helps advanced/filtered imagers (that stays deprioritised, below). When
unsure, ask *"would this help me, the beginner, on my next clear night?"* — if not,
don't build it. Still fix a real editor or stacking-engine bug first when one
exists (correctness outranks new surface), but a genuine beginner feature now beats
yet another marginal polish tweak.

**Depth over surface — but the app should still grow (beginner features).** The app
already has *plenty* of features, so a **pro/niche** addition needs a very high bar
and usually shouldn't happen at all. But a **beginner-facing** feature that clears
the bar above is now welcome on a regular cadence — deepening what exists *and*
adding well-chosen new beginner capabilities are both valued. Prefer fixing/polish
over a *marginal* new toggle; prefer a *real* new beginner capability over a
marginal polish. When in doubt: improve the editor, remove friction, or ship a
beginner feature — never add expert surface.

**Deprioritised — do NOT invest more here** (these are niche for an OSC Seestar
owner and have soaked up too much effort already): mono / LRGB / **channel
combine**, narrowband, and other pro-astro features. Leave what exists working;
don't extend or add to it. Anything that only helps filtered/mono imagers is the
*lowest* priority, below everything above.

Optimise for **many high-quality, fully tested changes over time**, but aimed at
the priorities above — not a long tail of niche additions.

> Note: `PLAN.md` is the *original* desktop-era design; it's historical. Trust the
> code, this vision, and `docs/IMPROVEMENTS.md` over `PLAN.md`.

---

## 2. The run — do several tasks each hour

A run is an **outer loop over tasks**. Keep completing tasks until you run low on
time, run out of good candidates, or the only work left needs owner sign-off.
A healthy run lands **~3–6 tasks** (more if small, fewer if one is large — a
single big feature can legitimately be the whole run). **Never trade the quality
bar (§5) for task count.**

**When you run out of clearly worthwhile work, STOP — do not manufacture busywork.**
A run that completes zero tasks and leaves `main` green is a success. This is a
live install with real data: shipping a marginal feature, a speculative refactor,
or churn just to have shipped *something* is worse than doing nothing. The task
count is a soft aim, never a quota — if the backlog is dry, do a dogfood pass (§2)
and file what you find, add a genuinely good idea or two only if you spot one, and
otherwise end the run.

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

**Big-picture review (do this regularly — at least one run in three).** Don't
*only* pick backlog items. Periodically step back and **dogfood the whole app as
the target user (§1)**: actually trace `drop files → ingest → QC → stack →
**edit** → export`, especially the editor, and ask "what's confusing, broken, ugly,
or slow here?" Fix the biggest real friction you find — root causes, not
symptoms — and write up anything you couldn't finish as a top-priority backlog
item. This is how you find the *undocumented* editor problems the owner hasn't
had time to report. A run that fixes one real editor/UX pain the owner would
actually notice beats a run that ships three niche additions.

---

## 3. How to decide what to work on (choosing among known candidates)

You are trusted to choose — but **the §1 priority order is the primary filter.**
A task that advances priority 1 (editor) or 2 (autonomy) beats a lower-priority
task even if the lower one scores better on effort/risk. Within a priority band,
score each candidate on three axes:

- **User value** — would *the target user (§1)* actually notice and appreciate
  this? A fix to a thing they use every session beats a niche capability.
- **Effort** — can you finish it *end-to-end with tests* within the run?
- **Risk** — how likely to break existing behaviour, corrupt data, or destabilise
  the hot path (ingest/stack)? Lower is better.

**Pick the highest-priority band with a good `value ÷ (effort × risk)` option.**
Prefer: fixing/polishing/simplifying something that exists > removing user
friction > a correctness fix a user would see > a *new* feature (high bar; must
serve §1) > cosmetic. Front-load safe wins, then attempt one bigger item.

### Where to find candidates (in priority order — mirrors §1)
1. **Anything broken or flaky** — failing/skipped tests, error logs, TODO/FIXME,
   swallowed exceptions, and **bugs a user hits** (start the editor and try to
   break it).
2. **Editor quality (priority 1)** — live-preview correctness/speed/parity with
   export, confusing or missing controls, and a weak default/auto result.
   Dogfood it; fix what annoys.
3. **Autonomy & friendliness (priorities 2–3)** — a manual step that could be
   automatic, a missing sane default, a confusing screen, a bad empty/error state.
4. **The backlog** — `docs/IMPROVEMENTS.md`, roughly top-down (it's ordered by
   these priorities).
5. **Image quality (priority 4)** — correctness/NaN/coverage edge cases and
   cleaner results *for the OSC workflow*.
6. **Coverage gaps / performance / maintainability** — add tests and fix what they
   reveal; optimise only a *measured* hot spot; refactor only in service of the
   above. Never trade correctness or memory-safety for speed (OOM history).

Do **not** pick niche/deprioritised work (mono/LRGB/channel-combine/narrowband)
except to fix an outright bug in what already exists.

---

## 4. How to come up with new features and ideas

Don't just drain the backlog — **replenish it**. Every run, spend some effort
generating genuinely new, valuable ideas and record them (with a why, a rough
size, and which pillar they serve). Aim to add at least a couple of well-reasoned
ideas per run. Here's how to find good ones.

### Ideas must serve the §1 priorities — in this order
An idea is only worth logging if it clearly helps the target user via one of:
1. **A better editor** — easier to get a great picture (the top priority).
2. **More autonomy** — fewer manual steps, smarter defaults, "it just did it".
3. **More approachable** — clearer, simpler, less confusing.
4. **Better image quality / trust** for the OSC Seestar workflow.

Ideas that only serve mono/LRGB/channel-combine/narrowband/pro workflows are
**not** worth logging — that space is deprioritised (§1). Prefer ideas that
*deepen or simplify* an existing feature over ideas that add new surface.

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

- [ ] Python suite green — ideally the full suite headless
      (`QT_QPA_PLATFORM=offscreen python -m pytest -q`); if Qt libs can't be
      installed, the fallback that skips the 3 GUI tests is in §7. Either way, do
      **not** "fix" a failing test by weakening it.
- [ ] New behaviour has tests. Bug fixes get a regression test that fails before
      and passes after.
- [ ] If you touched `frontend/`: `npx tsc --noEmit` clean, `npx vitest run`
      green, and `npx vite build` succeeds.
- [ ] You did **not** delete, skip, loosen, or `xfail` a test to get green.
- [ ] **Upgrade-safe (§9):** an existing `config.json` still loads, old
      project/library DBs migrate additively, on-disk layout is unchanged, no
      breaking default flips or API-shape changes. If the change touches config,
      settings, DB schema, or on-disk paths, add/extend an upgrade test.
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
# Python engine + webapp (needs Python 3.12 specifically; pyproject pins
# >=3.12,<3.13 — use python3.12 explicitly if the default python3 is older).
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,web]"

# Headless container extras: PySide6/pytest-qt need libEGL at import time even
# though the webapp never opens a window. (Install once per fresh container.)
apt-get update && apt-get install -y libegl1 libgl1 libxkbcommon0

# Frontend
cd frontend && npm install
```

**Running the tests:** prefer the full suite headless —
`QT_QPA_PLATFORM=offscreen python -m pytest -q` — so the Qt/GUI tests run too.
If the Qt system libs above can't be installed in your environment, fall back to
skipping just those three:
`python -m pytest tests/ --ignore=tests/test_compare_dialog.py --ignore=tests/test_end_to_end.py --ignore=tests/test_footprint_view.py -q`
(that's a fallback, not a licence to ignore GUI regressions when Qt *is*
available). Frontend: `npx tsc --noEmit`, `npx vitest run`, `npx vite build`.

Lint is not enforced in CI yet, but check before claiming quality-bar work:
`ruff check .` has pre-existing debt — don't let it block unrelated work, and
don't add to it. Put temp/scratch files under the session scratchpad, never in
the repo.

> Tip: **`scripts/agent-setup.sh` does all of the above idempotently** — run it at
> the start of every run (`source scripts/agent-setup.sh`) instead of hand-typing
> the steps. Wiring it into a `SessionStart` hook makes every run start green with
> no setup tax.

---

## 8. Git and shipping (zero-touch — no human reviews or merges)

This is a solo, autonomous project. **Nobody is going to review or merge your
work — so if you don't merge it, it never ships.** Your job is to get good,
tested changes onto the default branch by yourself, safely.

**The default branch is `main`.** That is the single source of truth: always
start from the latest `main` and always merge back into `main`. Ignore any other
branches you see on the remote (old/stale topic branches) — never base work on
them or merge into them.

**Work on a fresh branch, then merge it into `main` yourself:**

1. Start from the latest `main`:
   `git fetch origin && git checkout -B agent/<short-kebab-topic> origin/main`
   (the harness may create a working branch for you automatically — that's fine;
   just make sure it's based on the current `origin/main`). Use a fresh branch per
   topic; related small tasks may share one.
2. Commit each task as its own well-described commit. End every commit message with
   the repo's trailer convention (a `Co-Authored-By:` line; never put any model
   identifier in commits, code, or logs). Push after each task
   (`git push -u origin <branch>`); retry transient network errors with backoff.
3. **Before merging, make it green on top of the latest `main`:**
   `git fetch origin` → merge `origin/main` into your branch → re-run the full
   test suite (§5) and, if the frontend changed, the frontend build. Resolve any
   conflicts conservatively.
4. **Merge into `main` and delete your topic branch.** Preferred path (keeps the
   branch list clean automatically): open a PR and immediately merge it yourself
   (`create_pull_request` → `merge_pull_request`) — with the repo's *"Automatically
   delete head branches"* setting on, GitHub removes the branch on merge, so you
   don't have to. Do not *wait* for a human on the PR; you merge it.
   Fallback if PRs aren't available in your environment: merge `main` fast-forward
   and `git push origin main`, then delete the topic branch
   (`git push origin --delete <branch>`). If branch deletion is rejected by the
   host, that's fine — a *merged* leftover branch is harmless; never delete an
   *unmerged* branch.

**CI backstop:** `.github/workflows/ci.yml` re-runs the full Python + frontend
suites on every PR and on every push to `main`. Your local green run (§5) is the
gate; CI is the independent net. When you merge via a PR, glance at its checks;
and if `main`'s CI is red at the start of a run, **fixing it is your first task**
(it means the last merge broke something). Keep CI green — never merge changes
you expect to fail it.

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

## 9. Backward compatibility — this runs on a LIVE install (read this)

**AstroStack is deployed on a real TrueNAS/Docker box with real data, and it is
upgraded in place by pulling a new image off the default branch.** Every change
you merge must be a **safe in-place upgrade** — the owner must never lose data,
settings, or a working app because an agent shipped something. Treat this as
non-negotiable as the test suite.

Concretely, a change is upgrade-safe only if:

- **Config survives.** `state/config.json` from the previous version must still
  load. You may *add* settings (with sensible defaults). Do **not** rename,
  remove, or repurpose an existing setting, and don't tighten a field's bounds so
  a value an old version legitimately wrote is now rejected. (The loader resets
  only invalid fields rather than wiping everything — that's a safety net, not a
  licence to break configs.)
- **Databases migrate, never reset.** The per-target `project.sqlite` and the
  library DB carry user data. Schema changes must be **additive migrations**
  (`SCHEMA_VERSION` bump + `_migrate_schema` with `ALTER TABLE`/backfill), and
  must run cleanly from *any* older version. Never drop/rewrite a table or delete
  rows on upgrade. Test the migration from an old DB.
- **On-disk layout is stable.** Don't move or rename the library/targets/cache/
  output/state directory structure, existing stack outputs, or master
  calibration files. Old paths must keep working.
- **Defaults don't change behaviour.** Don't flip an existing default in a way
  that changes a running install (e.g. auth stays **off** by default; auto-stack
  stays off). New behaviour is opt-in.
- **APIs stay backward-compatible.** Don't remove endpoints or change response
  shapes the frontend (or a user's bookmarks/scripts) already depend on; add
  fields rather than renaming them.
- **The container still builds and boots.** Don't break the Docker image, the
  Python version pin, ASTAP bundling, or first-run bootstrapping.

If something genuinely can't be done without a breaking change (a destructive
migration, a renamed setting, a changed default), **do not ship it** — put it in
`docs/IMPROVEMENTS.md` under **Needs owner sign-off** with the migration/rollback
plan spelled out. See `tests/webapp/test_config_upgrade.py` for the pattern:
add a test that an *old* config/DB upgrades cleanly.

---

## 10. Hard guardrails (never cross these)

- **Never break an in-place upgrade** (§9) — no config wipes, destructive
  migrations, moved data, or breaking default flips.
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

## 11. Coordinating with other agents

Multiple agents overlap in time — Builders run roughly hourly, and the Scout runs
alongside them — and **both merge into `main`.** Two things make this safe by
construction: each agent runs in its **own isolated container** (there is no shared
working directory, so no file races), and **git serialises merges** (one lands, the
next must sync before it can). Nothing here can touch the *deployed* install's data.
Your job is just to keep the overlap harmless.

**While working**
- Read recent `git log` and open PRs/branches first; skip topics already in flight.
- Keep branches small and single-topic so they rarely conflict.
- `docs/IMPROVEMENTS.md` is the shared blackboard: claim an item by moving it to
  **In progress** with your branch name in the same commit that starts the work;
  release it (to **Shipped** or back to **Ideas**) when you finish or abandon it.
  Prefer items *not* recently touched by another branch.
- **Roles reduce overlap by design:** the **Scout** mostly edits the backlog + QA
  notes; the **Builder** mostly edits code + moves items to **Shipped**. Stay in
  your lane unless you've checked the other work isn't already in flight.

**Right before you merge — this is where concurrency actually bites**
- **Sync first, then re-test.** Fetch `origin/main`, merge it into your branch, and
  **re-run the full suite (§5) even if the merge auto-resolved cleanly** — another
  agent may have landed a change that's green alone but breaks combined with yours.
  Only ever merge from a green, up-to-date branch; CI is the backstop, not the gate.
- **Version bump: choose the number at *merge time*, from `main`.**
  `webapp/__init__.py` is a one-line hot spot two concurrent agents will both touch.
  Set `__version__` by bumping whatever is on the *latest* `origin/main`, as the
  last step before merging — not at task start. If you still conflict on that line,
  take `main`'s value and bump again; **never leave two different changes sharing one
  version number.**
- **A `docs/IMPROVEMENTS.md` conflict is almost always a union — keep both sides.**
  Each agent is usually *adding* different bugs/ideas/Shipped lines, so resolve by
  keeping **both**; never delete or overwrite the other agent's entry just to clear
  the conflict. If both changed the same item's status, keep the more-advanced one
  (Shipped > In progress > Ideas).
- If a conflict is non-trivial or you can't get green after syncing, **don't force
  it** — leave your branch pushed, note it in the backlog, and stop (§8). A stuck
  branch is fine; a clobbered or broken `main` is not.

---

## 12. Run checklist (copy/paste)

```
Start of run:
[ ] git fetch; read IMPROVEMENTS.md + recent log + open PRs
[ ] env ready; baseline test suite green (if red, fixing it is task #1)

Per task (repeat ~3–6×, or fewer if large):
[ ] picked/invented ONE task (§3 decision rule or §4 ideation); marked In progress
[ ] implemented across engine/webapp/frontend as needed
[ ] upgrade-safe: config loads, DB migrates, layout/defaults/API unchanged (§9)
[ ] added/updated tests; python + (if FE touched) tsc/vitest/vite build green
[ ] version bumped; IMPROVEMENTS.md updated (item → Shipped)
[ ] committed (independently green) and pushed

End of run:
[ ] added ≥1–2 new ideas to IMPROVEMENTS.md (§4)
[ ] synced branch with latest default; full suite still re-run and green (§11)
[ ] version set by bumping the LATEST main; IMPROVEMENTS.md conflicts kept as a
    union (never drop another agent's entry) (§11)
[ ] merged into main yourself (PR-merge preferred so the branch auto-deletes);
    topic branch deleted/gone; only main + truly-in-progress branches remain
```
