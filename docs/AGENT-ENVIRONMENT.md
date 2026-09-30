# Agent environment, tests and dogfood tooling — AstroStack

Moved verbatim out of `AGENTS.md` §7 on 2026-09-27, when that file was cut down to its live rules. `AGENTS.md` §7 keeps the short list of traps; this is the full text, including every flag of `scripts/agent-dogfood.sh`. Section references (§1, §2 …) point at `AGENTS.md`.

## Environment setup (the container is ephemeral)

Recreate tooling at the start of each run if missing:

```bash
# Python engine + webapp (needs Python 3.12 specifically; pyproject pins
# >=3.12,<3.13 — use python3.12 explicitly if the default python3 is older).
python3.12 -m venv .venv && source .venv/bin/activate
# `gui` is the PySide6 extra. It is NOT in the base dependencies (v0.418.0 moved
# it out, so the Docker image's own `pip install .[web]` stops dragging 650 MB of
# Qt into a deploy that never imports it) — so the three pytest-qt tests and
# `pytest-qt`'s own configure hook need it asked for explicitly here.
pip install -e ".[dev,web,gui]"

# Headless container extras: PySide6/pytest-qt need libEGL at import time even
# though the webapp never opens a window. ffmpeg is the decoder behind "Stack
# video" (Moon/Sun captures) — bundled in the Docker image; without it the
# tests/test_video_*.py files skip. (Install once per fresh container.)
apt-get update && apt-get install -y libegl1 libgl1 libxkbcommon0 ffmpeg

# Frontend
cd frontend && npm install
```

**Running the tests:** prefer the full suite headless —
`QT_QPA_PLATFORM=offscreen python -m pytest -q` — so the Qt/GUI tests run too.

> **⚠️ Redirect the output; never pipe it.** `pytest … | tail -15` reports
> **`tail`'s** exit status, not pytest's, so a run that collected *nothing* —
> pytest exits 4 on an unrecognised flag, printing an `inifile:` / `rootdir:`
> block that looks nothing like a summary — reads as a clean pass. That has
> already cost one run three commits written on top of an unverified tree
> (2026-09-03). Use `python -m pytest -q > run.log 2>&1; echo "EXIT=$?"` and read
> the file. **A summary line that does not end in `passed` or `failed` is not a
> result**, whatever the exit code said.
>
> **⚠️ Do not edit a source file while the suite is running** *(added 2026-09-14)*.
> The workers import modules as they collect, so a file changed mid-run gives
> failures that belong to the harness rather than to the tree — and they read
> exactly like a red `main`, which §2 makes task #1. One run edited
> `seestack/framing.py` at the 39 % mark and finished **`22 failed`**, every one
> of them in the two test modules whose source had moved; the identical suite
> against the settled tree passed. The tell is that every failure names
> something you touched minutes ago. Start the suite, then **read** — the
> backlog, the code, the docs — until its summary line prints.
>
> > **⚠️⚠️ And "edit" means the bytes on disk, not who wrote them — `git stash`
> > counts** *(added 2026-09-30, after it cost a second run its whole suite)*. A
> > run wanting to know whether `ruff`'s complaints were pre-existing did
> > `git stash` → `ruff` → `git stash pop` while the suite was running: twenty
> > seconds, no editor, and every file in the diff rewritten twice under four
> > workers. **Any git command that rewrites the working tree is an edit** —
> > `stash`, `stash pop`, `checkout <path>`, `restore`, `merge`. (Use
> > `git worktree add` for a scratch comparison; it touches nothing the suite is
> > reading.)
> >
> > **And for this variant the tell above is exactly backwards.** It finished
> > `2 failed` in **`tests/webapp/test_derived_light.py`** — a file the run had
> > *not* touched, in a subsystem its change did not go near. Those two are
> > **drift guards**: they read their own production module's source through
> > `inspect.getsource`, which resolves `co_firstlineno` against the file on
> > disk, so a module whose line numbers moved (`webapp/pipeline.py`, by ~75
> > lines) makes a guard **elsewhere** slice out the wrong function. Several
> > tests here are that shape — `test_derived_light.py`,
> > `test_project_schema_drift.py`, the `pack_unit` tree-grep, the
> > `StackOptions` form-descriptor drift test — so **a red naming a file your
> > diff does not touch is a reason to re-run that file alone before believing
> > it** (five seconds against eighteen minutes). Details in
> > `docs/PROCESS-NOTES.md`, 2026-09-30.
>
> **⚠️ Clear `/tmp/pytest-of-root` between suite runs** *(added 2026-09-14)*. One
> run leaves **~7 GB** there — pytest keeps the last three `tmp_path` roots per
> invocation and `-n 4` multiplies them — so the fourth suite of a run hits
> `OSError: [Errno 28] No space left on device` **inside pytest's own terminal
> writer**, and `vitest` dies the same way mid-file. That reads exactly like a
> broken checkout and is not one: `rm -rf /tmp/pytest-of-root` took a box with
> 147 MB free back to 28 GB and the identical re-run passed. On any ENOSPC, look
> there first (see the container note about the fixed per-session allowance —
> `df`'s "Used" will look small while "Avail" is zero).
>
> **⚠️ The runner is not this container's interpreter, and `python-version: "3.12"`
> does not pin the patch release** *(added 2026-09-28, after it took `main` red).*
> `.venv` here is **3.12.3**; CI's `actions/setup-python` resolves `"3.12"` to the
> newest available, which was **3.12.14**. They differ in observable behaviour: for
> an f-string containing a quoted literal, `ast.unparse` on 3.12.3 reuses the quote
> (PEP 701) — `f'…or 'unknown'…'` — while 3.11, 3.12.14 and 3.13 switch to
> `f"…or 'unknown'…"`. v0.484.2 keyed a test's exemption list on that string, passed
> **6,894 tests locally** and failed four assertions on the runner (fixed in
> v0.484.5). **So: a test whose assertions are computed from source text, from a
> `repr()`, or from any other interpreter-formatted string is not proven by one local
> run.** Recompute its key under the other interpreters this container already has —
> `/usr/bin/python3.11`, `/usr/bin/python3.12`, `/usr/bin/python3.13` — or, better,
> make the test itself assert every rendering (which is what v0.484.5's does).
>
> **And the suite is ~11 minutes, not ~75 — cap the BLAS threads before the first
> run, not after the third.** `OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
> MKL_NUM_THREADS=1 … python -m pytest -q -n 4 --dist worksteal`, after
> `pip install pytest-xdist` into the run's own `.venv` (it is deliberately not a
> project dependency, and installing it changes nothing in the repo). Sequential,
> the same suite projects to about 75 minutes and nothing about that looks wrong
> while it is happening. Details in `docs/PROCESS-NOTES.md`, 2026-09-13.
> **⚠️ Don't interleave `tests/` and `tests/webapp/` paths on one pytest command
> line** *(added 2026-09-27)*. Running a selection shaped
> `tests/webapp/a.py tests/b.py tests/webapp/c.py` — a `tests/webapp/` file, then a
> `tests/` file, then another `tests/webapp/` file — makes pytest report
> **`fixture 'client' not found`** for the *last* file, listing only the builtin
> fixtures: re-entering the directory does not re-apply
> `tests/webapp/conftest.py`. It has nothing to do with your change (it reproduces
> on unmodified `main` with two existing files), and it reads exactly like a broken
> fixture you just wrote. **Group the paths by directory** —
> `tests/a.py tests/b.py tests/webapp/c.py` — or run the whole suite. Cost: one
> false "did my test break the webapp fixtures?" detour.

If the Qt system libs above can't be installed in your environment (e.g. `apt`
is blocked, so `libEGL.so.1` is missing), fall back to:
`python -m pytest tests/ -p no:pytest-qt --ignore=tests/test_compare_dialog.py --ignore=tests/test_end_to_end.py --ignore=tests/test_footprint_view.py -q`
**The `-p no:pytest-qt` is not optional here:** without `libEGL`, the `pytest-qt`
plugin's `pytest_configure` hook fails at import (`ImportError: libEGL.so.1`),
which is a collection-time **INTERNALERROR that aborts the whole run** — so
`--ignore`-ing the three GUI files alone is *not* enough (the plugin crashes
before any test is collected). Disabling the plugin skips it cleanly; the three
`--ignore`d files are the ones that actually use its `qtbot` fixture. (This is a
fallback, not a licence to ignore GUI regressions when Qt *is* available.)
Frontend: `npx tsc --noEmit`, `npx vitest run`, `npx vite build`.

> **⚠️ Run all three from `frontend/`, and check you are there.** They are the
> same trap as the pytest one above, in a second costume: from the **repo root**
> there is no `tsconfig.json` and no local `typescript`, so `npx tsc --noEmit`
> prints TypeScript's **help text and exits 0** — a clean pass that compiled
> nothing. (`vitest` and `vite build` at least exit non-zero there.) A shell's
> working directory persists between tool calls, so one `cd` earlier in a run is
> enough to poison every later check. Prefix each command with its own
> `cd frontend &&`, and treat tsc output that does not name files — or names none
> — with the same suspicion as a pytest summary that doesn't end in `passed`.
> *(Cost: two type errors reached a pushed commit on 2026-09-08 behind a green
> `npx tsc` run from the root.)*

Lint is not enforced in CI yet, but check before claiming quality-bar work:
`ruff check .` has pre-existing debt — don't let it block unrelated work, and
don't add to it. Put temp/scratch files under the session scratchpad, never in
the repo.

> Tip: **`scripts/agent-setup.sh` does all of the above idempotently** — run it at
> the start of every run (`source scripts/agent-setup.sh`) instead of hand-typing
> the steps. Wiring it into a `SessionStart` hook makes every run start green with
> no setup tax.
>
> **If it prints `ERROR: the Python environment is NOT ready`, that is an install
> failure, not a broken checkout.** A PyPI read over the agent proxy can time out
> mid-resolve and leave a `.venv` holding nothing but `pip`; the tell is
> `No module named pytest` from `.venv/bin/python`. Just retry the install
> (`pip install --timeout 120 --retries 5 -e ".[dev,web]"`) and carry on. *(The
> script used to print a cheerful "agent env ready" over exactly that state — it
> is `source`d, and its `set -e` did not stop the failed install; it now verifies
> the toolchain imports before saying it is ready, v0.378.1.)*

> **A normal pass now gives the scratch install an observing site** *(added
> 2026-09-12 with v0.436.1)*. Before that it had none — the bundled samples'
> FITS deliberately carry no `SITELAT`/`SITELONG`, so `_resolve_observer`
> answered `"none"` and **Tonight, the Sky Map's placement, the life list's "Up
> tonight" chip, the wishlist prompt, `/api/plan/closing`, `/api/plan/week` and
> `/api/life-list/nearly-there` were all in their empty state on every pass ever
> run**, while three features shipped into that half in one week. The site goes
> into the scratch install's **Settings**, never into the sample's headers (a
> demo that claimed a location would have the planner plan a real owner's night
> from it); `DOGFOOD_SITE="lat,lon"` moves it, `--no-site` skips it, and
> `--empty` never sets one. The pass prints `location_source` and the row count
> so a silent failure can't pass for the old empty state.
>
> Tip: **`scripts/agent-dogfood.sh` boots a real app with real data** for the §2
> big-picture pass — scratch data root, the bundled sample loaded and stacked,
> then Playwright full-page screenshots at 1440 px **and** 420 px plus an
> overflow probe. Use it instead of re-reading route files: the bugs that survive
> code-level audits are the ones only a running app shows. `--serve` leaves it up
> to poke by hand; `--no-probe` skips the page sweep (and, with `--editor`, only
> the page sweep — the editor drive still runs). Everything lands in a
> scratch dir, never the repo. Whatever it finds still needs a real regression
> test in the suite — it is a finder, not a test.
>
> **⚠️ Never run it at the same time as `pytest`** *(added 2026-09-10, after it
> cost a run an hour)*. It runs `npx vite build`, and `frontend/vite.config.ts`
> sets `emptyOutDir: true` on an `outDir` of `../webapp/static` — so a dogfood
> pass **deletes `webapp/static/` and rebuilds it**, and every `tests/webapp`
> test that calls `create_app()` inside that window fails at fixture setup. The
> tell is fourteen `RuntimeError: Directory '…/webapp/static/assets' does not
> exist` **errors** (not failures) in an otherwise-passing suite, which reads
> exactly like "`main` is red, and fixing it is task #1" (§2). Serialise them:
> dogfood first, `pytest` after. (It only builds on `--build` or when
> `webapp/static/index.html` is missing, so the *second* pass of a run is
> usually safe and the first is not.) *(The same accident found a real §9 bug —
> the app used to refuse to boot in that state; fixed in v0.414.2, so today it
> degrades to "Frontend not built" instead. The test collision remains.)*
>
> **On any run making an Auto/editor claim, add `--mosaic`** *(v0.386.0)*. §1
> judges those claims on a tiled mosaic at the owner's scale, never on the
> 6-frame single field — and until now the tooling could not produce one, so
> every "dogfood CLEAN" recorded here was still measured on the field. `--mosaic`
> loads and stacks a second, generated sample: four overlapping panels of one
> shared sky, uneven depth (6/6/6/3), one panel shot through haze, and a ragged
> union canvas that is genuinely ~5 % uncovered — so the surfaces gated on NaN
> "no coverage" are finally in front of a browser. It prints the trim Auto would
> apply to that canvas (**above ~15 % is a bug, not a ragged edge**) and writes
> its shots to `$SHOTS/mosaic/`, leaving the field sample's page-height baselines
> alone. Combine with `--editor` to drive the editor on the *mosaic* run.
>
> **And read the block it prints under "what the app SAYS about this mosaic" as
> one paragraph** *(added 2026-09-09 with v0.406.2)*. A "CLEAN" pass is a
> statement about console errors — not about pixels (v0.406.0's lesson) and not
> about **sentences**. Three consecutive findings were in the *gap between* two
> of the app's own claims rather than in any one of them: a "flat" seam number
> answering a question about the sky's *level* to someone looking at a difference
> in *depth*; the History chip repeating it; and the panel map drawing a hole
> where the thin panel was, over the words *"no part of the picture is being held
> back"*, while the health panel on the same run called a quarter of that picture
> 1.4× grainier. Every one of those passes was CLEAN. So the question to ask of
> that block is not "did anything error?" but **"could a beginner hold all of
> these at once?"**
>
> **On any run that touches the editor, add `--editor`.** The pass above only
> *photographs* the editor, in the one state it opens in — priority 1 is the
> editor and the owner's complaints about it are all about what happens after a
> click, so nothing in this repo's tooling had ever clicked one. `--editor` runs
> `scripts/dogfood_editor.mjs`: it adds every op the Add menu offers, one at a
> time, and checks the live preview actually re-renders with no console error and
> no failed request, then undoes and redoes. A few minutes on top of a normal
> pass, which is why it is a flag rather than the default.
>
> **The probe now prints that paragraph for you — read "what the Target page
> SAYS"** *(added 2026-09-13 with v0.437.8)*. The shell block above is the
> **server-side** half (the panel map and the health notes, straight off the
> API); the cards that actually produced four of the last five findings —
> the readiness goal, the grain projection, "to make this even better", the
> plateau verdict — are computed in the **frontend**, so nothing in Python could
> print them and every one had to be cropped out of a screenshot afterwards.
> `dogfood_probe.mjs` reads them off the rendered page and prints them together,
> **each tagged `inline` or `FOLDED behind "more notes"`**. Read the folded ones
> too: `NoticeBoard` shows two notes and hides the rest, so what the page says
> and what a reader sees without clicking are different questions — and the
> second one is where the "what does this page say when the other cards are
> quiet?" failures live.
>
> **And it reads `/tonight` the same way — "what the TONIGHT page SAYS"** *(added
> 2026-09-14 with v0.445.1)*. The Target page tells the owner what to do with a
> picture he already has; **Tonight is the other page that prescribes**, and it
> does so from **four independent self-hiding cards in one column** — the
> wishlist card, "nearly there", "shoot these before they're gone" and the week
> plan — each naming a target, none knowing what the others named. That column
> had never been read as one paragraph, and v0.445.0 was found in the gap between
> two of its cards: one arguing *"a clear night spent on one of these buys
> something the rest of the year can't"*, the other answering *"which night
> should I go out?"* from a score that has never heard of a season ending. Ask of
> the block it now prints: **do these point at the same night and the same
> target, and if not, does the page say which wins?** Note it is silent without an
> observing site — a normal pass sets one (v0.436.1), `--no-site` and `--empty`
> do not.
>
> **The sweep now reaches `/compare`, and its Split and Blink modes** *(added
> 2026-09-14 with v0.440.2)*. That page was never in the route table because it
> is the only one whose URL carries data — two `<safe>:<run_id>` refs — so the
> screen whose entire job is weighing two pictures against each other had never
> been photographed at all; the route is now built from the running app's own
> `/api/gallery`, and on a `--mosaic` pass the pair is the mosaic *and* the
> single field, which is the comparison where a per-pixel figure and a total are
> different numbers. Its other two comparators are behind a `SegmentedControl`
> and carry a **provenance strip "Side by side" does not have**, so navigating
> alone could never see them — the same blind spot `--editor` exists for, and
> where v0.440.0 lived. Each mode is clicked and held to the identical overflow /
> squeeze / clipped-label / console checks. The lesson generalises: **a view you
> can only reach by clicking is a view no route table will ever probe**, so when
> you add one, add it here too.
>
> **And the editor's shrunk preview has never been drawn at all — `--big`**
> *(added 2026-09-14 with v0.446.0)*. Both other samples fit *inside* the
> editor's proxy: `seestack/edit/proxy.py` strides only above `PROXY_MAX_PX`
> (1500), the field sample is 480 px wide and the mosaic's union canvas ~907, so
> `get_proxy` hands each back at `proxy_scale == 1.0`. Everything gated on a
> **decimated** preview was therefore structurally unreachable by this tooling —
> the five preview↔export advisories (sharpen, deconvolution, denoise, hot
> pixels, star reduction), the preview-scale caption, and the **whole** of "Check
> it at full size": its button, its modal, its navigator, its `X-Loupe-Window`
> marker and its split comparison, ~250 lines of the priority-1 screen, pinned by
> jsdom alone. Even `--editor`, which clicks every op in the Add menu, could not
> reach one of them; the owner's own mosaics are ~3494×2470 and up, i.e. that is
> his everyday state. `--big` loads a third sample: the same 2×2 mosaic — same
> grid, same 82 % step, same uneven depth, same hazy panel, same ragged corners —
> shot with 900×600 panels, so its union canvas is **1694×1150** and the preview
> is decimated by exactly **2**. That is the *smallest* canvas that reaches the
> surface at all, chosen deliberately: stacking cost grows with the pixels and a
> pass nobody runs finds nothing (measured, ≈ 60 s of stack on top of
> `--mosaic`). It prints what `/editor/loupe-info` answers — canvas, the shrink
> factor, and whether the full-size check is offered — so a sample that drifted
> back under the cap cannot pass for a clean pass, and writes its shots to
> `$SHOTS/big/`. **Use it on any run that touches the editor's preview**, and
> combine with `--editor` to drive the ops on the one run whose preview is not
> 1:1.
>
> **And the drop folder itself has never held a file while a browser was
> looking — `--incoming-lag`** *(added 2026-09-14 with v0.442.0)*. The scratch
> install's `incoming/` is **empty on every pass**, because the sample arrives
> through `POST /api/sample`, which writes straight into the library. So every
> surface that reads that folder is structurally invisible to this tooling — the
> same hole as the missing observing site and the click-only Compare modes, a
> third time. `--incoming-lag` writes a few subs there with the app's own sample
> writer, dates them eleven days ago, and stretches the watcher's quiet period so
> the batch is not imported mid-pass; it then prints what `/api/incoming-lag`
> answers. **It is a flag and the default pass stays healthy on purpose**: an
> observing site is data a real install *has*, whereas unimported subs are a
> **fault**, and seeding one by default would put a warning banner into every
> Dashboard screenshot and every page-height baseline — making "CLEAN" mean less
> rather than more. Run it on any run that touches ingest, the watcher, or the
> Dashboard's notice board.
>
> **And no pass has ever held a master dark — `--calibration`** *(added 2026-09-17
> with v0.455.1)*. The scratch install's calibration registry is **empty on every
> run ever recorded**, so the Calibration page's masters list,
> `/api/calibration/incoming`'s one-click "you already have darks, shall I build
> one?" offer, `/api/calibration/defects` and its repair offer, the per-target
> `calibration-suggestions`, `auto_bind_calibration` and the **"darks were
> applied"** half of the stack-health vocabulary have only ever been photographed
> in their empty state — on an app whose health card tells the owner, on *every*
> stack, that adding master darks is "the single biggest cleanup for a noisy
> image". The app has been pushing him toward a state its own tooling had never
> once occupied: the same hole as the missing observing site, the empty
> `incoming/` and the click-only Compare modes, and like all three it paid
> immediately — **v0.455.0 was found while building it**, before the flag itself
> was finished (a folder of darks under `incoming/` was being ingested as a target
> of lights, in the one place the Calibration page's own build form asks the owner
> to put them). It seeds generated darks and flats into the scratch `incoming/`
> and then makes the app **discover and build them itself** through the endpoints
> a beginner would use, turns on `auto_bind_calibration`, and stacks after that so
> the calibrated branch is the one on screen. **Read its one caveat before
> believing a calibrated picture:** the samples' *lights* carry no hot pixels and
> no vignette (their pixels are pinned bit-identical by every earlier baseline),
> so the masters reach the *surfaces* without improving the *picture*. Run it on
> any run that touches calibration, the scanner's folder classification, or the
> health card's vocabulary.
>
> **And no pass had ever held the owner's *scale* — `--deep`** *(added 2026-09-17
> with v0.455.3)*. Every sample here is **six subs per pointing**; his library has
> **5,477** subs on one target and **35,894** on another. So every surface whose
> cost is a function of *how much he has* had only ever been exercised where
> nothing can go wrong — and this probe could not see it either, because it
> measures **page height**, and the frames table sits in a `mah="65vh"` scroll
> container whose height is by construction independent of its rows. A table
> rendering one DOM row per sub measured exactly the same as one rendering six,
> which is how **v0.455.2** (28,266 nodes and 4.5 s to first paint on 1,200 subs
> in Chromium) survived every clean pass and had to be found by reading the
> route. This is the missing-site / empty-`incoming/` / click-only-Compare /
> no-master-dark hole **one layer down: a magnitude, not a state.** `--deep`
> loads a fourth sample — one ordinary field shot **1,200 times** — and
> `scripts/dogfood_deep.mjs` prints the three numbers that move with the rows
> (rows rendered against the app's own sub count, DOM nodes, first paint) and
> then **scrolls the table's foot** to check the window grows, which is the one
> path jsdom can never cover (it has no `IntersectionObserver`). Two caveats,
> both load-bearing: it is **not stacked** (1,200 subs is a stack nobody in a
> run waits for, and nothing here needs a picture), and its sensor is
> **160×120** because generation + QC is per-frame — so the surfaces that scale
> with the frame **count** are exercised and the ones that scale with *pixels*
> are not. Use it on any run that touches the frames table, a per-sub list, or
> anything whose cost grows with a target's depth; use `--big` for pixels. **One
> side effect to expect rather than investigate:** the deep target is by far the
> deepest thing in the scratch library, so every prescriptive card on `/tonight`
> names it — which is them working, but it makes a `--deep` pass a poor one on
> which to read that column as one paragraph. Read that block on an ordinary or
> `--mosaic` pass.
>
> **And nothing here had ever *arrived* the way his data arrives — `--combine`**
> *(added 2026-09-27 with v0.480.8)*. Every other shape reaches the app through
> `POST /api/sample`, which writes straight into the library, so the whole front of
> the journey had never been run by this script: a folder appearing in `incoming/`,
> a scan classifying it, a **second night of the same object**, the merge nudge,
> "Combine into one deep target", and the scan *after* it. The three Combine bugs
> fixed in v0.480.2–.4 therefore had to be checked with a hand-rolled server and
> four curls, and `--closing` does not cover it — its two targets are deliberately
> a degree apart *so the nudge does not fire*. `--combine` runs those nine steps
> against a real app on its own root and port (8814), loading no sample, and prints
> what the app **says** at each one: the scan's targets, the refused stack, the
> nudge, `POST /api/targets/merge`'s answer, the combined target's cover / notes /
> tags, and the two rescans.
>
> Four things about it are load-bearing, and each cost the hand-rolled pass time to
> find:
>
> - **There is no ASTAP in this container**, so a stack of synthetic subs is refused
>   (`error_kind=no_solved_frames`). The flag lets that happen *on purpose* at step
>   3 and prints the job's own sentence, then does what the test fixtures do —
>   writes `tests.synth.make_synth_wcs_text()` into every frame's `wcs_json`, plus a
>   centre and an fwhm, through `Library`/`Project` — and stacks for real.
> - **The log of the step that was meant to fail is where the bug was.** That is
>   exactly where v0.480.5 was sitting (every `log.exception` missing from
>   `/api/logs`, found in the traceback of this same refusal), so the flag prints
>   the server log's error lines at the end whether the journey succeeded or not.
>   *A pass that only asks "did the feature work?" scrolls straight past it.*
> - **`/api/targets/merge-suggestions` is checked AFTER the solve, not before.**
>   It clusters by each target's own **plate-solved centre**, so on unsolved frames
>   it correctly answers `[]` — the first version of this flag checked it at step 3
>   and printed that emptiness as a finding, which it is not. Solved, it names the
>   group ("Andromeda Galaxy, within 0.0 arcmin — M_31 (4 frames), M_31_night_2 (3
>   frames)").
> - **It measures AGENTS.md §10.** It fingerprints every file it writes into
>   `incoming/` (path, size, mtime) before the journey and compares afterwards, so
>   "nothing was moved, renamed, truncated or removed" is a printed result rather
>   than an assumption — and the one sub it drops in at the end is reported as an
>   *addition*, which §10 allows. This is the only place any of this tooling can
>   check the most important rule in the file.
>
> Run it on any change to the scanner's folder handling, `seestack/io/merge.py`,
> `Library.merge_targets`, the merge nudge, or anything that reads or writes
> `incoming/`. It costs about a minute (seven small subs, two short stacks) and the
> page probe then runs against a **just-combined** library, which no other pass has.
> Tune the two nights with `DOGFOOD_COMBINE_SUBS` / `DOGFOOD_COMBINE_SUBS_2`; keep
> them unequal, because the deep folder being the one with more frames and the
> shallow one the more recent is the shape v0.480.4 turns on.
>
> **Follow it with `scripts/agent-dogfood.sh --empty`** (≈1 min once playwright is
> installed): the same probe against an app with **no data at all**. Every
> measurement this script took before 2026-09-07 was of the *sample-loaded* app, so
> the screens a beginner meets first — an empty Dashboard, Library, Gallery, life
> list — had never been in front of a browser. It uses its own port and its own
> scratch, so it can follow a normal pass without disturbing it. The first-run
> baseline to compare against is in `docs/PROCESS-NOTES.md` (2026-09-07).

