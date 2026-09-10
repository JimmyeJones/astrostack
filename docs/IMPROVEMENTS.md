# AstroStack improvement backlog

The shared blackboard for autonomous development. Read
[`../AGENTS.md`](../AGENTS.md) first — it defines the loop, the decision
framework, and the guardrails. This file is *what* to build; AGENTS.md is *how*.

> **Current focus (re-cut 2026-09-07 to match AGENTS.md §1; the 2026-07 text below it was
> stale twice over).** The single-field stacking-engine core (`seestack/stack/*`,
> `seestack/calibrate/*`) has passed **twenty clean sweeps** and is **closed until a new bug is
> found there — do not re-sweep it**. The open frontier is **mosaic-scale and walk-away behaviour
> of the Auto/editor path**: every Auto/editor claim is judged on a tiled mosaic canvas at the
> owner's scale, never on the 6-frame sample (D1 hid there through three audits). After that:
> autonomy, friendliness and image quality (priorities 2–4). Fix any real editor regression first;
> favour these areas when picking *new* work. **Ready-to-build entries are marked `READY` — grep for it.
> Both `⭐ READY — GATE OPEN` items have now shipped (the editor auto-seed v0.390.0, the `auto_stack` default
> flip v0.391.0), so there is no starred queue left — pick from `READY` and from the priority sections.
> Every gate that needs the owner is in one list at the top of "Needs owner sign-off".**

**Conventions**
- **This file is the WORKING LIST. A run must leave it no longer than it found it,**
  unless it is filing a verified bug (AGENTS.md §2, "the three-file rule"). When an
  item ships or is closed, **cut the entry** and append it to
  [`SHIPPED.md`](SHIPPED.md), leaving a one-line `✅ v0.xxx.y <what>` under
  "Shipped" here. Process notes, collision diaries and QA sweep records —
  **including clean ones** — go to [`PROCESS-NOTES.md`](PROCESS-NOTES.md), never
  into a priority section. Delete an "In progress" claim when you release it.
  *(Added 2026-09-04. The file grows ~100 lines per merged PR — 18,757 on 08-01,
  34,934 on 09-02, 41,038 on 09-04 — so no agent can read it in a run, and every
  agent is necessarily skimming. That is the common cause behind stale entries
  surviving, ideas being re-derived, and items being built twice.)*
- Sections: **Bugs (fix these first)** → **In progress** → **Ideas** (roughly
  prioritised) → **Shipped** → **Needs owner sign-off**.
- Two kinds of agent share this list (see AGENTS.md "Agent roles"): the **Builder**
  *drains* it (implements + ships the top items), and the **Scout** *fills* it
  (files verified bugs, curates priorities, adds ideas). Claim any item you start by
  moving it to **In progress** with your branch name, in the same commit that starts
  it. Move it to **Shipped** (with the commit/PR) when done, or back to **Ideas** if
  you abandon it.
- **Scout — replenish and curate.** Each Scout run: file the bugs you verified into
  "Bugs (fix these first)" (symptom + location + repro + severity + confidence),
  reprioritise, prune done/stale/duplicate items, and add a few well-reasoned ideas
  (AGENTS.md §4) — but only ones that serve the **§1 priorities** (1 editor,
  2 autonomy, 3 friendliness, 4 image quality), each tagged with a size (S/M/L) and
  its priority. Do **not** log niche mono/LRGB/channel-combine/narrowband ideas.
- **Builder — bugs and leads only.** A Builder files a bug it verified itself and a
  lead it could not finish; it does not invent features to stay busy (AGENTS.md §4).
  If ready work is genuinely thin, dogfood the app (§2) and file what you find — an
  idle run that leaves `main` green is a success.
- **Priority order (from AGENTS.md §1) governs this list.** Work the top sections
  first. The editor is priority 1.
- **A shipped item's spec belongs in `SHIPPED.md`; until it is moved, keep it
  *indented*.** The cut above is the rule; this is the fallback for the inline
  "✅ SHIPPED" entries still sitting under "Ideas", and for the moment between
  shipping and moving. *(The "Bugs" half of that backlog is done — 227 resolved
  entries and 24 sweep records were cut on 2026-09-05; "Ideas" is what is left.)*
  Strike the headline,
  write the SHIPPED paragraph, and keep the original spec **as an indented
  continuation** (two spaces), never as a fresh top-level `- **…**` bullet. A
  top-level copy is indistinguishable from open work: every
  way an agent triages this file — reading a section, or grepping `^- \*\*` for
  unclaimed items — surfaces it as a live idea, and runs have been spent
  re-picking features that shipped months earlier. Indented, the "is this open?"
  question is answerable by shape alone.

---

## In progress

> **This section holds *live* claims only — nothing else.** Claim an item by adding
> one line here with your branch name, in the same commit that starts the work;
> **delete that line** when you release the claim (§11). Everything a finished run
> wants to say goes in `docs/PROCESS-NOTES.md`, not here.
>
> *(Emptied 2026-09-04. It had grown to 420 lines in which **every** header said "claim
> released" or "run finished" — a diary, not a claim board, and the one section
> whose whole value is being short. The diary moved verbatim to
> [`PROCESS-NOTES.md`](PROCESS-NOTES.md); nothing was deleted.)*

*No live claims.*

---

## Bugs (fix these first)

> **Open bugs and nothing else** (the three-file rule, AGENTS.md §2). The 227 resolved
> entries and 24 QA sweep records this section used to carry were cut to
> [`SHIPPED.md`](SHIPPED.md) and [`PROCESS-NOTES.md`](PROCESS-NOTES.md) on 2026-09-05,
> verbatim and in order — 12,375 lines down to under 1,000, so this section can be *read*
> rather than skimmed. **Grep those two files for anything older than v0.352.3**, including
> the target of any "see above" / "see below" in the entries below that no longer resolves
> here.

- **🟠 FIXTURES THAT CANNOT EXHIBIT THEIR BUG (fourth external audit, 2026-09-10 — both reproduced by reverting
  the fix in a scratch script; see PROCESS-NOTES).** (1) `tests/test_edit_curve.py::
  test_the_sky_stays_put_at_every_stack_depth[very-deep]` — at `noise=0.0006` the zero-clip spike is no longer
  the tallest bin of `_sky_mode`'s `[p0.5, median]` histogram, so the **pre-A1** `_sky_mode` reads the sky
  correctly (rel. error 0.048; 0.996 at the other three depths) and the test passes on the bug. The guard
  `clipped_fraction(st) > 0.005` (and `displayspace.MIN_CLIPPED_FRACTION`) asserts the clip is *present*, not
  *dominant*. **Fix:** make `assert_shadow_clip` histogram the finite values over `[p0.5, median]` (128 bins) and
  assert `argmax == 0`, or drop the deepest noise to ~0.001 where the spike still wins. (2)
  `tests/test_coverage_trim.py::test_a_ragged_mosaic_still_gets_its_fringe_trimmed` — with `panel_coverage_level`
  reverted to the **peak**, the `TRIM_KEEP_RATIO` ladder yields kept **0.902**, inside the asserted `0.90 < kept
  < 0.99` (fixed code: 0.975), so the "before the fix the same map was cropped to the overlap band" docstring is
  no longer what the assertion pins. **Fix:** assert the rect equals the border rule's answer
  `(5/400, 5/400, 395/400, 395/400)`, or raise the floor to 0.95. (3, note only) the v20/v21 fixtures in
  `tests/test_project_schema_drift.py` are today's `SCHEMA_SQL` minus one or two columns, which
  `_reconcile_table_columns` restores even with the migration steps deleted — the v9–v14 tests in
  `tests/test_project.py` hand-write the old tables and are the pattern to copy. (S each; Confidence: HIGH.)

- **🟠 CI CERTIFIES THE CHECKOUT, NEVER THE IMAGE (fourth external audit, 2026-09-10) — `READY`, infra, S.**
  `.github/workflows/ci.yml` has two jobs, both against the source tree; the artifact the owner installs has
  never been built or run by anything but his terminal (incident 2026-09-09). Add a third job that builds **from
  the Dockerfile's own file set**: `docker build --target frontend -f docker/Dockerfile .` (fast; no ASTAP
  download in that stage; fails on any import that reaches outside `frontend/`), then a Python smoke that copies
  only what the Dockerfile copies (`pyproject.toml README.md seestack/ webapp/`) to a scratch dir, `pip install
  "<dir>[web]"` **non-editable**, and from `cd /` runs `python -c "import webapp.main, webapp.sample_data;
  from seestack import nightplan"` (exercises package-data and CWD-independence, which `pip install -e` at the
  repo root never can). Verified in this audit's build that both would pass today. Batch with the same commit
  (each traced in PROCESS-NOTES 2026-09-10): `RUN npm install` → `npm ci` with `package-lock.json` copied
  unconditionally (CI uses `npm ci`; no drift today); **PySide6 is in the base `dependencies`, so `pip install
  .[web]` installs 650 MB of Qt into a 1.89 GB image that never imports it** — move it to a `gui` extra and update
  AGENTS.md §7 / `agent-setup.sh` / `ci.yml` to `.[dev,web,gui]`; `ENV ASTROSTACK_PORT` in the Dockerfile is dead
  (`CMD` hardcodes 8000 — drop the ENV or use it); in `docker-compose.yml` use the long volume syntax with
  `create_host_path: false` so a mistyped `ASTRO_DATA` fails loudly instead of booting on a fresh empty directory
  (reproduced: Docker creates the missing host path and the app comes up with an empty library).

- **🟡 THE EDITOR OFFERS A MODE THE IMAGE CANNOT RUN AND THE OWNER HAS DECLINED (fourth external audit,
  2026-09-10).** `color_calibration_mode` = `"gaia"` (`webapp/schemas.py` ~1127, `seestack/edit/ops/tone.py`)
  imports `astroquery.gaia` (`seestack/post/color_cal.py` ~387); `astroquery` is in no dependency list and is
  absent from the image (`ModuleNotFoundError`), and it is a SIMBAD/CDS network call — declined by the LOCAL
  rule (AGENTS.md §1). The broad `except Exception` at `color_cal.py` ~156 swallows it and falls back to
  gray-star with only a log line, so picking it does nothing and says nothing. **Fix:** remove the option from the
  schema and the op (keep the engine branch inert), and let a stored recipe that names it load as `gray_star`
  with the auto-note saying so. (S, friendliness; confidence HIGH — checked in the running image.)

- **⚪ A-MINOR — verified smaller items from the same audit, batch these into cleanup passes.** ~~No validator
  stops `library_root` being set **inside** `incoming_dir` (after which every correctly-scoped `rmtree`
  resolves inside the raw tree — *not* the owner's current state, but one settings edit away)~~ *(shipped
  v0.327.8, see above)*; ~~the scanner's
  bare-`<T>/` skip is **silent** even when the folder holds thousands of FITS (the owner's `NGC 6888` 4,815 vs
  `NGC 6888_SUB` 3,110 is exactly that shape)~~ *(shipped v0.329.2, see below)*; ~~the plate-solve-failed screen shows a
  blocking banner and, in the same row, a "?" popover calling unsolved subs "usually harmless"~~ *(shipped
  v0.328.1, see below)*; ~~the Stack
  page prints the **raw engine error** where every other page uses `friendlyJobError`~~ *(shipped v0.328.0,
  see below)*; ~~the frames table prints raw
  UTC under a hero that says "Shot &lt;local night&gt;"~~ *(shipped v0.328.5, see below)*;
  ~~"nights" means **6-hour sessions** on the Nights card
  but **calendar nights** in captions~~ *(shipped v0.329.1, see below)*;
  ~~three hand-mirrored "is this a genuine run" predicates~~ *(shipped v0.338.1 — and they **did** disagree;
  see the note directly below)*;
  `POST /api/targets` has **no frontend caller**; ~~share and print JPEGs use 4:2:0 chroma subsampling~~
  *(shipped v0.328.0, see below)*; the "full
  data" TIFF anchors its white point on the single brightest surviving pixel *(traced 2026-09-03 — the
  mechanism is confirmed, but read the note below before "fixing" it)*.

- **⚪ MEASURED RESIDUAL OF D1's FOURTH INSTALMENT (Builder 2026-09-09, filed with the v0.399.3/v0.399.4 fix
  that closed the rest) — the border rule still over-crops a **weighted** coverage map on a minority of fully
  tiled rasters, which only a **legacy** run can now hand it.** *(Severity: low — every run that writes
  `{stem}_framecov.fits` is measured on the frame count instead, where the same 147 rasters are 0/0/0 in all
  three outline shapes. Confidence: HIGH, same harness. Size: unknown.)*
  Over 147 rasters × 3 outline shapes (exactly tiled; four uncovered corners; a ragged perimeter), as how many
  keep under 95 % of what their own coverage allows: **frame counts 0 / 0 / 0** (worst 1.000), **weighted
  13 / 14 / 39 → 4 / 4 / 10** (worst 0.822 / 0.817 / 0.801). The mechanism is the one the fix already names: a
  weighted value is a sum of per-frame *weights*, so one panel occupies a *band* of values rather than a level,
  the panel-vs-ramp shape test sees speckle rather than blocks, and the reference itself wanders. **The reachable
  population is runs recorded before `_framecov.fits` existed**, which `_trim_rect_for_run` falls back to the
  weighted map for; a re-stack writes the sibling and moves the run into the fixed column.
  **Before starting, read the five rejected levers and the shipped rule in [`SHIPPED.md`](SHIPPED.md) (search
  `FRINGE_OUTSIDE_FRAC`)** — four scalar levers are measured and closed, and the answer here is unlikely to be a
  sixth. The honest next step, if this is ever worth it, is to make the *shape* test survive jitter (a local mean
  before the plateau/connectivity work) rather than to move a constant. **Probably not worth building**: the
  cheaper and more useful fix for a real install is a re-stack, and the whole population shrinks every night the
  owner shoots.

- **🟡 BROKEN-UX / AUTONOMY (Scout QA audit 2026-08-26 #4, traced + verified end-to-end) — PARTIALLY FIXED
  (misleading-copy half shipped v0.272.2; optional behavioural half open) — the `astap_timeout_s` setting bounds
  ONE solve *attempt*, not one frame, so an unsolvable sub can burn up to 3× the configured seconds; the Settings
  help text used to say the opposite and now says so honestly.** *(Severity was broken-UX / autonomy — it
  silently triples the wasted time on a cloudy walk-away night, the owner's exact workflow; not wrong-result.
  Confidence: traced against the code.)*
  `ASTAPSolver.solve` (`seestack/solve/astap.py:206`) runs a **3-rung** ladder (`_SOLVE_LADDER`, ~line 147:
  default → full-res `-s 1000` → bin-2×), and each rung calls `_solve_once` → `subprocess.run(timeout=self.timeout_s)`
  (~line 294). A timeout on a rung raises `ASTAPError`, which is caught and **falls through to the next rung**
  (~line 216–226) — each getting the *full* `timeout_s` again. So a frame that never solves (heavy cloud, star-poor
  sub) consumes up to `3 × astap_timeout_s` of wall clock: **180 s at the 60 s default**. Meanwhile the
  frontend tooltip (`frontend/src/routes/Settings.tsx:52`) reads *"Give up on solving a single frame after this
  many seconds."* — literally per-frame, which is false. On a clear night this is invisible (frames solve on rung 1
  in a second or two; only *timeouts* accumulate), but on a cloudy night with hundreds of unsolvable subs it can turn
  an expected ~100 min of wasted solve time into ~5 h, delaying the very auto-stack the owner walked away for.
  **Fix options (the ladder's multi-attempt rescue is load-bearing, so don't just cut it):**
  (a) ~~*Honest-copy, safe:* correct the tooltip.~~ — **SHIPPED v0.272.2** (Scout 2026-08-26, this run): the
  `astap_timeout_s` hint now reads *"Give up on each solve attempt after this many seconds. The solver tries up to
  3 strategies per frame, so a frame that never solves can take up to about 3× this before it's set aside (and
  retried on the next scan)."* with a `Settings.test.tsx` assertion pinning the per-attempt wording. So the setting
  is no longer *misleading*; the wasted-time behaviour itself is unchanged. **(b) is the remaining open half:**
  *Behavioural, careful:* budget the timeout across the ladder (e.g. full `timeout_s` on rung 1 where most frames
  solve, a fraction on rungs 2–3, or a shared deadline for the whole frame) so the setting bounds *per-frame* time as
  its name implies, without starving the coarse rescue rungs — needs a test that a hard frame still gets its rescue
  attempts and that total per-frame time is bounded. Only worth doing if the owner wants true per-frame bounding;
  the label fix above already removes the surprise.
  **Builder 2026-08-26 — considered and deliberately DECLINED this run; read this before picking it up.** I sized
  it against the real code and stopped, because every workable shape is a **blind threshold flip on the
  on-by-default hot path**, which AGENTS.md §1 tells an agent not to do. The ladder cannot be given a true
  per-frame bound without a per-rung floor (a shared deadline alone gives rungs 2–3 *nothing* on exactly the
  frames a timeout means they exist to rescue), and the floor's size *is* the tradeoff: at 25 % of `timeout_s`
  the worst case falls 3× → 1.5×, at 50 % it falls to 2×, and in both cases a hard frame that rung 3 would have
  cracked in, say, 20 s is now abandoned. Which frames that loses is unmeasurable from the repo — it needs a real
  cloudy night's subs, which no agent has. Meanwhile the cost of leaving it is now *bounded and honest*: the
  Settings hint says "up to about 3×" (v0.272.2), and as of **v0.276.4** a sub that burned the whole ladder is
  no longer silent — it lands in its own "Ran out of time being located" bucket on the Target page telling the
  owner to raise the timeout. So the surprise and the invisibility are both gone; only the wasted minutes
  remain. **Leave this for the owner to ask for**, and if they do, ship it with the floor as a named constant and
  the measured before/after on their own data — not on a synthetic frame.

- **⚪ HARDENING NOTE (Scout QA audit 2026-08-27 #8, traced — possibly by-design; low confidence) — the folder
  watcher's stability gate compares host wall-clock `now` to the source file's `mtime`
  (`(now - mtime) >= quiet_period_s`, `webapp/watcher.py` ~line 94), so if the NAS/SMB source filesystem's clock
  runs AHEAD of the host, completed files may never satisfy the age gate and never go stable → never ingested
  until the host clock catches up.** *(Severity: low — needs a genuinely skewed source clock, and a manual
  "Scan incoming" or app restart re-globs and picks the files up anyway; the mtime-age gate is a deliberate
  "has the write finished settling" heuristic, so this may be acceptable as-is. Confidence: traced, not
  reproduced; flagged so it isn't re-investigated.)* **If ever worth hardening:** gate on size-stability across
  two polls (already tracked) rather than absolute mtime age, or clamp a negative `now - mtime` to "treat as
  just-modified" so a skewed-ahead clock can't strand a file forever. Only worth doing if the owner reports
  files that never ingest until a rescan.

- **⚪ HARDENING NOTE (found incidentally, 2026-08-17 audit — not currently firing for the owner, no fix
  needed yet, just a landmine to know about) — the mosaic-canvas outlier-exclusion pass's rejections are
  PERMANENT with no reconcile path**, unlike auto-grade's post-v0.221.0 behaviour. Verified not to have fired
  for the owner's data (3° floor + median-separation term; the owner's ~3.6°-apart panels excluded nothing).
  If a future mosaic legitimately trips this exclusion, there is currently no path back for those frames the
  way `apply_grade_reaccepts` provides for auto-grade. Worth a reconcile pass eventually, same shape as the
  auto-grade fix, but not urgent — file only, don't build until it's someone's actual problem.

- **Follow-up to the v0.225.0 mosaic-Auto fix — bisect the rest of the v0.158→v0.220 colour chain on a synthetic
  mosaic.** The measured root cause (noise misread → `detail.chroma_denoise` at full strength) is fixed and the op
  no longer fires on a deep mosaic, but the original entry rated confidence only **medium** that it was the *sole*
  contributor to the owner's seam grid. **Do this only if the owner reports the grid persists on v0.225.0** — the
  synthetic 4-panel mosaic scene now lives in `tests/test_auto_noise_measure.py::_scene(mosaic=True)`, so the
  bisect is cheap: run `get_proxy → auto_recipe → apply_recipe` with SCNR, the per-frame flatten and
  `remove_final_gradient` individually disabled and measure the chroma step across a panel boundary vs within a
  panel. Note the shipped fix's own measurement found the *absolute* seam step is dominated by the injected panel
  offsets themselves (the smoother reduces it), so any further work should measure the **visible plateau/edge
  structure** the smoother creates, not the raw step. (M, image quality — PRIORITY 1/4.)

- **Minor / low-priority (traced, filed for completeness — fix only if touching these files):**
  - ~~`seestack/stack/output.py:654` (+400, 413, 428, 446, 525) every float→uint export **truncates**
    instead of rounding, biasing every exported pixel downward by ~½ a step.~~ — **FIXED v0.354.1** (all six
    sites now go through one shared `output.pack_unit`, which `np.rint`s; the entry, the measurements and the
    test re-reasoning are in [`SHIPPED.md`](SHIPPED.md)). **Two non-bugs from the same 2026-09-05 mosaic/output
    QA audit are kept here so they aren't re-investigated:** `output.py` `_write_coverage_fits` writes a **2-D**
    coverage map verbatim without the `.astype(np.float32)` its 3-D branch and `_write_frame_coverage_fits` both
    apply — a double-size FITS if a float64 2-D map ever reached it, which the production accumulators never
    emit; and `_same_map`'s `np.array_equal` returns False on identical-NaN maps, moot because coverage maps are
    0-filled, never NaN.
  - ~~**LEAD — the same truncating pack lives in `seestack/render/`, on the *display* side.**~~ —
    **FIXED v0.354.2**, and wider than the lead framed it: fifteen hand-spelled sites across
    `seestack/render/`, `seestack/printexport.py`, `seestack/stack/stacker.py`, `webapp/routers/`,
    `webapp/pipeline.py` and `webapp/video.py` now go through `output.pack_unit`, with a drift test that
    greps the tree so a sixteenth can't appear silently. Two of them — `printexport.render_print` and the
    Moon still's 16-bit TIFF — were *exports* the v0.354.1 sweep had missed because they live outside
    `stack/output.py`. Entry in [`SHIPPED.md`](SHIPPED.md).
  - `seestack/stack/weighting.py:97` the FWHM factor computes `(best_fwhm / f.fwhm_px) ** 2` with a Python float, so a
    pathologically tiny `fwhm_px` would raise `OverflowError` (before `np.clip` can clamp it) rather than saturate.
    **Unreachable on real data** — every writer of `fwhm_px` traces to `median_fwhm`, which persists only values in
    (0.5, 20) or None, and overflow needs `fwhm_px < ~1.5e-154` (a crash reproduces only at ~1e-300). Defensive-only:
    cast to `np.float64`/guard the ratio if the file is touched. (Cosmetic — unreachable; confidence: traced + repro'd
    at the unreachable boundary.) — **FIXED v0.367.1**: the ratio is computed in `np.float64` under
    `errstate(over="ignore")`, so it saturates to `inf` and clips to the 1.0 the formula already wants.
    Regression `tests/test_engine_defensive_guards.py::test_a_pathologically_tiny_fwhm_saturates_instead_of_crashing_the_stack`. _(Found by the 2026-07-24 weighting audit.)_
  - `seestack/stack/align.py` (subpixel-refine cap, ~line 400/490) the guard `|dy| > CAP or |dx| > CAP` does **not**
    reject a NaN shift (NaN fails both comparisons → the shift is applied). **Unreachable** — the correlation patches
    are NaN-filled to finite before `phase_cross_correlation`, and finite inputs never return a NaN shift (a featureless
    overlap returns a finite spurious `(-0.7,-0.7)` whose ≤5px NaN edge-ring is exactly consumed by the
    `pad=SUBPIXEL_SHIFT_CAP_PX=5` window). Defensive-only: rewrite as `not (abs(dy) <= CAP and abs(dx) <= CAP)` so a NaN
    is treated as "too large" and skipped, belt-and-suspenders, if the file is touched. (Cosmetic — unreachable;
    confidence: traced.) — **FIXED v0.367.1**, at *both* sites (`_apply_subpixel_shift` and the windowed one).
    Regression `tests/test_engine_defensive_guards.py::test_a_nan_subpixel_shift_is_refused_rather_than_smeared_over_the_frame`
    (patches `skimage.registration.phase_cross_correlation` to return a NaN shift; fails before — `nd_shift`
    wiped the whole frame to NaN). _(Found by the 2026-07-24 align audit.)_
  - `seestack/stack/align.py::extract_reference_patch` fills NaNs with `np.nanmedian(luma)`, which on an **all-NaN**
    patch emits a RuntimeWarning and returns NaN — so the shared reference patch would be entirely NaN and every
    frame's sub-pixel refine would silently correlate against nothing (each `phase_cross_correlation` returning a
    meaningless shift, or the call failing and the frame stacking unrefined). **Unreachable in practice** — the
    patch is the *centre* of the reference frame's own aligned array, which is finite by construction; a fully
    uncovered centre would mean the reference didn't land on its own canvas. Defensive-only: fall back to `0.0`
    when the median isn't finite, if the file is touched. (Cosmetic — unreachable; confidence: traced.)
    — **ALREADY FIXED** (found done while sweeping this batch, v0.367.1): `extract_reference_patch` computes
    `fill = float(np.median(luma[finite])) if finite.any() else 0.0`. Struck so nobody re-picks it.
    _(Found by the 2026-08-07 align/accumulator audit, which otherwise traced clean: the windowed and full-canvas
    accumulator adds, the min/max k-set insertion and its ±inf identities, the mosaic canvas RA-unwrap and outlier
    passes, the photometric scale/weight composition, and the reproject inset/pad arithmetic all held.)_
  - `webapp/routers/storage.py:193` `prune_stack_runs` closes `proj` then `lib` in a **single** `finally` (not
    nested like `gallery.py`/`storage.py::get_storage`), so if `proj.close()` itself raised, `lib.close()` would
    be skipped and the Library handle would leak. Trigger is essentially unreachable (`sqlite3.Connection.close()`
    does not raise in practice), so this is a consistency nit, not a live leak — nest the two closes if the file is
    touched. (Cosmetic; confidence: traced.) — **FIXED v0.367.1**: nested, matching `get_storage`/`gallery.py`.
  - `seestack/solve/runner.py:204-218` the "unreadable plate solution" self-heal branch's comment claims recording a
    `reject_reason` makes the frame "stop being re-offered," but `build_solve_arglist` (`runner.py:166`) skips frames
    only on truthy `wcs_json` — nothing gates on `reject_reason`, so a consistently-unparseable `.wcs` sidecar is
    re-solved every scan (identical to the ordinary transient-failure branch it says it "mirrors"). The re-offer
    behaviour is itself harmless/safe (a transient corruption recovers on retry); only the comment over-promises. Fix
    the comment (or, if genuinely un-recoverable, gate the skip on the stored reason) if the file is touched.
    (Cosmetic — comment vs behaviour; confidence: traced.) — **FIXED v0.367.1** the comment, not the behaviour:
    re-offering is deliberate and correct here (an unreadable sidecar is usually transient), and
    `build_solve_arglist` says so explicitly — so the comment now states what the branch actually buys (the frame
    is no longer stored as *solved-yet-unusable*) instead of promising a skip nothing implements.
  - `seestack/stack/reference.py:42-44` `pick_reference_frame` filters candidates on `ra_center_deg is not None` but,
    unlike `pointings.py:78-80`, does not also require `math.isfinite` — so a hypothetical NaN centre would propagate
    into the unwrap/median/score and pick an arbitrary reference. Effectively unreachable (a successful solve writes a
    finite `wcs_json` + centre; a failure leaves `wcs_json` NULL and is filtered by the `f.wcs_json` clause), so this
    is a defensive consistency nit, not a live bug — add the `isfinite` guard to match `pointings.py` if the file is
    touched. (Cosmetic; confidence: traced.) — **FIXED v0.367.1**. Regression
    `tests/test_engine_defensive_guards.py::test_a_nan_pointing_never_becomes_the_reference_frame` (fails before:
    the NaN frame was picked, and a NaN-only list returned a frame instead of `None`).
  - `seestack/post/skymap.py:266` the **offline** galactic-plane fallback (astropy absent) draws the Milky Way
    curve with a linear-in-sin approximation that is up to ~29° off in declination. In this deployment astropy is
    a hard dependency, so the exact `except` branch is dead code and never renders — noted only so a future
    dependency change doesn't ship a wrong overlay. (Cosmetic/dead-code; confidence: traced.)
  - `seestack/io/merge.py:88-99` `MergeResult.n_skipped_missing_file` mislabels *added* frames: a frame is
    counted `added` (L84) before the cache block, and when `old_cache.exists()` is False it does `missing += 1`
    while the frame is **still merged** (usable via `source_path`, `cached_path=None`). So the counter reports
    "added-but-cache-missing", not "skipped". Reporting-only; no data loss. (Cosmetic; confidence: traced.)
  - ~~`seestack/io/ingest.py:93-103` `_cache_stale` refreshes on source *shrink* too, not just growth: the
    docstring justifies it as "source grew after it was cached" but the `st_size != st_size` test is symmetric,
    so a source later truncated/replaced smaller than its cache overwrites a good Stage-1 cache and resets that
    frame's QC.~~ — **CLOSED as already-defended, not fixed; re-traced 2026-09-07 so nobody spends a slot on it.**
    `_cache_stale` is symmetric and stays that way, because the harmful half is caught **before** it is reached.
    A shrunk source means `fp_changed` → `content_changed`, and `_source_incomplete(src)` (`ingest.py:338`) runs
    first: it *loads the pixel data*, so a mid-rewrite truncation fails to read and the whole frame is skipped
    with `skip_reason="still copying (incomplete rewrite)"` — nothing touched, cache intact, re-checked once the
    source settles. A source that shrank and is still a **complete, readable** FITS is a genuinely different,
    smaller capture at a reused path, and refreshing the cache is then the *right* answer (it is the second case
    `_refresh_frame_metadata`'s docstring names). The only residue is a pre-fingerprint row from a library
    upgraded and not yet re-scanned, where `stored_fp is None` skips the guard for exactly one scan before the
    fingerprint is backfilled — and its worst outcome is a re-QC. Do not "fix" the symmetry: making it
    growth-only would strip the content-swap refresh that keeps a new capture from stacking at the old sky
    position. (Confidence: re-traced against the current code.)
  - `seestack/io/scanner.py:123` + `ingest.py:143` a symlinked duplicate subdir double-ingests: if `root`
    contains both a real subdir and a symlink to it, both pass `is_dir()` and become separate targets/projects,
    and the per-project `realpath` dedup (built only from that project's own frames) doesn't catch the same
    physical raws landing in a second project. Only harmful if the user later stacks both. (Edge case; traced.)
  - ~~`seestack/bg/per_frame.py:289-297` `_subtract_background_cpu` on the **stack path** (`errors=None`): if one
    channel's `Background2D` fit fails it's skipped while the others subtract, then `_zero_sky_per_channel` runs —
    a per-channel-asymmetric result that could introduce a faint colour cast.~~ — **FIXED v0.173.2** (Builder
    2026-07-23, branch `claude/pensive-faraday-tfvkyx`; regression-tested). The stack path now fits all three
    channels *before* subtracting and, if any channel's ladder fit fails, degrades to **no** subtraction (leaves
    the gradients) rather than a per-channel-asymmetric one — matching the editor path's already-documented
    reasoning ("don't leave a partial per-channel subtraction that would colour-shift the image"). A per-frame
    colour cast is coherent and does not average out in the stack, so all-or-nothing is the correct degradation.
    Regression `tests/test_bg_modes.py::test_stack_path_bails_on_a_single_channel_fit_failure_no_colour_cast`
    (monkeypatches the ladder to fail on channel 0 only; asserts the frame is returned unchanged — fail-before it
    partial-subtracted G/B). Additive; no config/DB/API/on-disk change. Severity: image-quality/correctness, Low
    (only on a degenerate fit, now rare given the robust ladder). (Confidence: traced + regression-tested.)
  - `seestack/qc/streaks.py:107-112` `streak_count` **over-reports** a single continuous trail as 2–5 (one
    satellite/plane trail fragments into several collinear `probabilistic_hough_line` segments; `line_gap=8` +
    `disk(1)` dilation don't re-merge them). Reproduced (Scout 2026-07-23, adversarial QC audit): a clean diagonal
    trail → count 2 (width 1) / 5 (width 2–3). **Not surfaced in the live web app** — `streak_count` is displayed
    only in the historical desktop GUI (`seestack/gui/preview.py:209`, `frame_table.py:60`), which is
    deprioritised; it *is* persisted to `project.sqlite`. **Does NOT affect stacking or auto-reject** — the
    `streak_detected` boolean that drives `auto:streak` is correct in every tested case. The docstring's primary
    definition ("number of distinct line segments") is technically accurate; only the "N satellites" framing is
    optimistic. Fix only if this count is ever surfaced in the web UI (then post-merge collinear segments into
    trails). (Broken-UX but web-invisible today; confidence: reproduced.)

- **Sky-atlas overlay WCS uses a rotation sign that deviates from the FITS/AIPS `CROTA2→CD` convention
  (display-only; needs a real solved frame to validate before flipping — NOT a blind Builder change).**
  **⚠ LARGELY SUPERSEDED by the v0.142.4 Sky-map placement fix (Bug 2 above):** `get_sky` now places
  the overlay from the stack's **stored canvas WCS** (`wcs_dict_rescaled_to_preview`), so `_tan_wcs` is
  only reached as the **fallback for a run whose master FITS is missing/headerless** (older/edited runs) —
  the ordinary path never hits the suspect sign anymore. The remaining sign issue affects only that
  fallback, so it's now low-impact; still real-data-gated (validate ASTAP's CROTA2 sign on a real solved
  frame before flipping). Original trace kept for the fallback fix:
  *(Traced, Builder audit 2026-07-10; high confidence it deviates from the convention, low confidence it
  visibly matters.)* `webapp/routers/sky.py::_tan_wcs` (~L92) builds the derived TAN WCS for the sky-atlas
  preview overlay with `CD1_2 = +scale·sinθ`, `CD2_1 = +scale·sinθ`. With the RA axis flipped
  (`CD1_1 = −scale·cosθ`, i.e. `CDELT1 < 0`), the standard AIPS `CROTA2` convention wants **both** off-diagonals
  **negated** (`CD1_2 = CD2_1 = −scale·sinθ`) — the current signs are equivalent to using `−θ`, so on a frame
  with non-zero field rotation the Aladin overlay is rotated by `2θ` from correct (a mirrored rotation). It is
  **display-only**: it never touches the stored `wcs_json` or any stacking/science result (the built-in viewer
  is unaffected), and the code comment already flags "Sign of the rotation is a best-effort starting point."
  **Why NOT a blind fix:** whether ASTAP's `CROTA2` follows the same sign sense as the AIPS convention decides
  which way is right, and some solvers differ — flipping the sign without checking could just rotate it wrong
  the *other* way. Validate against a **real** Seestar frame solved with a known non-zero field rotation (compare
  the overlay placement to the true sky) before changing it; a synthetic can't stand in for ASTAP's convention.
  (S code / S validation, display-only/friendliness — low priority, deprioritised sky-atlas surface.) Found by an
  adversarial audit of the plate-solving path (`solve/*` + its persistence/consumers), which otherwise traced
  clean — WCS parse, solve-success detection (returncode + sidecar), RA-wrap in the center consumers, hint
  unit conversion, and setup-error classification all held.
  _(Scout 2026-07-21 — **reproduced the 2θ divergence + pinned the provenance**, strengthening confidence the
  code (not the convention) is wrong, while the fix stays real-data-gated. (1) **Provenance:** the
  `rotation_deg` fed to `_tan_wcs` is, by definition, ASTAP's **`CROTA2`** keyword — `solve/astap.py:359`
  reads `rotation = values.get("CROTA2", 0.0)`, carried unchanged through `runner.py`→`project.py`→`sky.py`
  (`_representative_pixscale_rotation`). So the code is converting a genuine CROTA2 with a hand-rolled matrix,
  and the correct target is the **FITS-standard** CROTA2→CD conversion (which is exactly what `astropy.wcs`
  applies when you set the `CROTA2` keyword). (2) **Reproduced** (astropy `WCS`, run under `.venv`): comparing
  the code's CD matrix against the FITS-standard conversion (`CDELT1=−scale`, `CDELT2=+scale`) by the on-sky
  position angle of the image "up" axis — at `CROTA2=30°` the code places the overlay at PA **30°** vs the
  standard **330°** (a **60° = 2θ** error); at `CROTA2=0°` the two agree **exactly** (diff 0.0) and the CD
  determinant is `−scale²` (correct RA-left celestial parity), so there is **no hidden global y-flip masking
  the sign** — the divergence is purely the rotation term, genuinely reversed. (3) **Still NOT a blind fix,
  same gate as before:** whether ASTAP actually emits a FITS-standard-signed CROTA2 on a real Seestar solve is
  the one thing a synthetic can't settle; astropy's standard conversion assumes it does. So validate on one
  **real** solved Seestar frame with a known non-zero field rotation before flipping both off-diagonals to
  `−scale·sinθ`, and pin the sign with a known-orientation regression test. This is the same underlying bug as
  Sky-map placement Bug 2 (the ⭐ owner-reported entry above) — fix them together. Repro kept in the session
  scratchpad (`wcs_repro.py`).)_

---

## Ideas (priority order — work top sections first; AGENTS.md §1)

> **⚠ Scout — the Ideas list is running stale: several entries below were already
> fully implemented in code but never struck through.** In a single 2026-07-22
> Builder run, five "open" ideas were found already shipped (SExtractor sky-mode
> guard across all 4 sites; plate-solve per-rung timeout fall-through in
> `astap.py`; the "Clouds & haze" transparency-trend card; the Stack-form
> photometric-normalize nudge; the √N "should I keep shooting?" text via
> `readiness.ts`) — each cost real investigation time before being ruled out.
> They've been curated to Shipped this run, but **please do a full sweep**: grep
> the codebase for each open Idea before leaving it open, and strike through
> anything already built. A stale backlog makes every Builder run start by
> re-discovering finished work.

### Autonomy & friendliness (PRIORITY 2–3)

- **NEW IDEA (Builder 2026-09-03, the cost the v0.335.0 endpoint knowingly accepted) — `/rejection-outlook`
  pays for a whole `estimate_stack` to learn two numbers.** *(Pillar: performance — size XS; **only if the
  note is ever un-gated**, see the entry two above.)* It needs the accepted+solved count and the mosaic's
  per-pixel depth, and takes both off `estimate_stack`, which also picks a reference frame and computes the
  union canvas. That is the right call today — one definition of `panel_depth`, and the query is only issued
  when a streak is present, so a target page normally never asks. But if the note is ever shown unconditionally
  it becomes a per-page-load canvas computation across the library's biggest targets, and the cheap
  equivalent already exists: `auto_reject_depth(_frame_radecs(frames))` (grid-snapped, sub-millisecond — see
  the measurement above) plus a plain count, no canvas at all. **Care:** the two are not identical —
  `estimate_stack` drops the gross plate-solve outliers `compute_mosaic_canvas` excludes before counting, and
  the cheap path would not, so a target with a few wild solves would report a slightly higher `n_frames`.
  Pin that difference in a test before swapping, or the "reaches" answer moves for a reason nobody can see.

- **NEW IDEA (Builder 2026-09-02, spotted while building the v0.323.1 print button) — sweep the app for
  sentences that *name* a number the form could just set, and give each one the button.** *(Pillar: autonomy —
  PRIORITY 2; size XS per site once found. Confidence: two live sites already have the button, the rest are
  unenumerated.)* The Stack form now has two: the `memoryFix` button ("Use drizzle ×1.4 instead — fits at ~2.1
  GB") and, as of v0.323.1, the print one ("Use drizzle ×1.4 — prints at A3"). Both existed first as a
  *sentence* naming a machine-actionable value, and in both cases the knob was inside the collapsed advanced
  disclosure — so the sentence was advice a beginner could read and not act on. **The identifying test:** does
  the copy contain a concrete value (a scale, a κ, a count, a mode name) that some control on a screen the user
  can reach would accept? If yes, it is a candidate. **Named starting points, none checked yet:**
  `drizzleTooFewHint` ("consider turning Drizzle off" — a boolean, so trivially actionable),
  `drizzleClipHint` (names `drizzle_reject` outright), `backgroundModeNudge` (names a mode), and the
  calibration-suggestion copy. **Care, and the reason this is a sweep rather than a rule:** a button is a second
  element on a dense form, against the owner's standing "extremely busy" priority — so each site has to justify
  itself the way the print one did, by being *conditional on something rare* rather than always-on. An advisory
  that fires on most stacks should stay a sentence. And check the query-key trap the print button hit: a fix
  that sets two form keys must land them in **one** state update, or the panel re-queries through an
  intermediate state and flickers between two verdicts.

  **⚪ SWEPT AND CLOSED — every named starting point already has its button (Builder 2026-09-04, read in the
  code, not assumed). Do not re-pick this.** All four candidates the entry names were checked in
  `frontend/src/routes/Stack.tsx` as it stands: `drizzleTooFewHint` has *"Turn off Drizzle"*, `drizzleClipHint`
  has *"Turn on drizzle outlier rejection"*, `backgroundModeNudge` has *"Use <mode> background flatten"*, and
  the calibration-suggestion copy has **"apply recommended"** (`applyRecommended`, which sets every
  recommended master *and* `scale_dark_to_light` in one go, precisely because applying half of a
  scaling-dependent pairing would mis-subtract the pedestal). The neighbours are done too — the min/max
  weighting hint, the transparency hint, the quality-weighting and photometric nudges, the drizzle nudge and
  the two memory fixes all carry theirs. **The identifying test still stands for anything newly written**
  (does the copy name a concrete value some reachable control would accept?), and so does the entry's care
  note — a button earns its place by being *conditional on something rare*; an advisory that fires on most
  stacks stays a sentence. But there is no backlog of un-actioned sentences left on the Stack form to sweep.

- **NEW IDEA (Builder 2026-08-30, the generalisation of the v0.311.3 "First light" bug) — sweep every date the
  app shows a beginner and ask whether it means *when you shot this* or *when the app did something*.**
  *(Pillar: understand / trust — PRIORITY 3; size S per surface, M for the sweep. Confidence: the class is
  confirmed — one instance was reproduced in a running app and fixed this run.)* "First light" quoted the
  target-row **creation** stamp and so told a Seestar owner with a back catalogue that they took up the hobby
  the week they installed AstroStack. The bug is fixed; **the class is not swept.** The owner's mental model of
  a date on a picture is *the night I shot it*, and several surfaces show a **processing** date in a place that
  reads like a capture date — the clearest is the Dashboard's **Recent stacks** strip, whose tile reads
  `Sample: Orion Nebula (M42) · 6 FRAMES · Aug 30, 2026` where the 30 Aug is when the *stack ran*, while the
  subs under it are dated 2024-11-15. On a re-stack of old data that is off by years, on the app's front page.
  **Shape:** enumerate the surfaces (Dashboard recent strip, Gallery cards, History rows, the Library tile, the
  keepsake/poster) and for each decide which date the *reader* means, rather than which one is cheapest to
  reach — a stack run's own timestamp is right for "which run is newest", and wrong as the caption on a
  picture. `Project.earliest_frame_utc()` (new this run) and the existing per-night rollups already answer the
  capture side, so most of this is a decision plus a label, not new data. **Care:** don't flip a *sort* to
  capture time — "newest run" is the right ordering for History — and where both dates matter, say both
  ("shot 15 Nov 2024 · stacked 30 Aug 2026") rather than silently swapping one for the other.

  **✅ THE LAST TWO NAMED SURFACES ARE DONE (Builder, v0.321.2, branch `claude/wizardly-feynman-be4ubk`) — the
  Gallery card and the History row, which were the two still printing a *raw machine stamp* with no label at
  all.** The entry names five surfaces; the Dashboard strip, the keepsake and the Target hero were closed by
  earlier runs, and **the Library tile turns out to show no date at all** (`Library.tsx` reads
  `last_activity_utc` only to *sort* by it, which is the right use and the Care note's own exception) — so these
  two were the whole remainder, and the sweep is finished. Both printed `run.timestamp_utc` sliced with `.replace("T", " ")`
  — `2026-08-30 14:32` on the Gallery card, `2026-08-30T14:32:05` on the History row — which is (a) the moment
  the *stack ran*, years out from the capture on a re-stack of a back catalogue, and (b) not a date format the
  app uses anywhere else a person reads.

  **Gallery card → `pictureDateLabel`**, the same helper the Dashboard strip and the Target hero already use, so
  it says *"Shot 15–18 Nov 2024"* and falls back to a **labelled** *"Stacked 30 Aug 2026"* when the run predates
  the capture window (schema < 18 — i.e. almost everything in the owner's library today). The night count is
  deliberately **not** passed: the card's line is already five segments long, and "over 4 nights" belongs on the
  caption, not the tile. The run's identity there is its `output_basename` printed beside the date, so the clock
  time was not needed.

  **History row → both dates, each labelled** — *"Shot 15–18 Nov 2024 · Stacked 30 Aug 2026, 14:32"* — because
  this is the one list where they answer different questions: which run this row *is*, and what the picture is
  *of*. That is the entry's own "where both dates matter, say both" rule, and the sort is untouched (still newest
  run first, as the Care note requires). **The clock time is load-bearing here and is why this needed a new
  helper:** `output_basename` is reused across a re-stack, so two re-stacks made the same afternoon are
  distinguished by nothing else — a date-only label would collapse two rows into identical text.
  `formatStampDateTime` is `formatStampDate` plus `HH:MM`, keeping the never-a-numeric-month rule and the same
  empty-string-on-junk contract.

  **Frontend-only:** no API, schema, config, on-disk or default change; both fields were already on the payloads
  (`GalleryItem`/`StackRun` have carried `capture_night_start`/`_end` since schema 18) and an older backend
  omitting them lands on the labelled "Stacked" form, which is exactly right.

  **Tests (+6; the 4 component ones fail before):** `format.test.ts` (+2 — the clock time added to the same named
  month, and the junk contract), `Gallery.test.tsx` (+2 — a 2024 capture window shown as *Shot* with the 2026
  processing stamp gone from the card, and the labelled fallback with no "Shot" on a run that has no window) and
  `History.test.tsx` (+2 — both labels on one line with no raw ISO stamp, and two same-afternoon re-stacks whose
  lines stay distinct while neither claims a shoot date).

  **✅ AND THE SKY FOOTPRINT LINE, THE LAST ONE ON THE LIST (Builder, v0.321.3, same branch).** The Sky Map's
  selected-footprint caption read `RA 83.822° · Dec −5.391° · 17 Aug 2026` — a bare, unlabelled date beside a
  picture, i.e. the exact shape of this whole entry, and the leftover the v0.313.0 run explicitly named. It now
  goes through the same `pictureDateLabel`. The field it needed was genuinely missing (unlike the Gallery and
  History, which already had it): `SkyImage` gained **additive optional** `capture_night_start`/`_end`, bucketed
  with the same `capture_night_range` and the same `Settings.site_lon` the Gallery card and the Nights card use,
  so all three can't name one session differently. `timestamp_utc` stays on the payload untouched — the viewer
  draws newer tiles on top by it, which is the right use of a processing stamp and the Care note's own exception.
  **Upgrade-safe:** two optional response fields (an older frontend ignores them; an older backend omitting them
  reads as "no capture window", which lands on the labelled "Stacked …" form). **Tests (+5, 4 failing before):**
  `tests/webapp/test_sky.py` (+2 — the window carried through as observing nights with the stack stamp intact,
  and a pre-schema-18 run reporting null rather than borrowing it) and `Sky.test.tsx` (+2 new, +1 updated — a
  capture window shown as "Shot 15–18 Nov 2024" with no 2026 anywhere in the line, and the labelled fallback; the
  existing "dates it like every other surface" assertion gained the label and keeps its no-raw-ISO check).

- **NEW IDEA (Builder 2026-08-30, the one case the v0.312.1 tint fix deliberately fenced off rather than
  solved) — a many-sub stack whose canvas is no bigger than its preview still gets the cyan wash.**
  *(Pillar: trust — PRIORITY 3; size S–M; **low urgency, and check the case is reachable before building**.)*
  The fix subtracts the map's own uniform noise floor only where the resize *averaged*, because at 1:1 a trail
  pixel and a noise-tail pixel are both "one sample lost here" and nothing pointwise separates them — measured,
  a floor there zeroed every count-1 pixel of the planted trail. So a dense map rendered 1:1 is deliberately
  byte-identical to the old, washed behaviour. **That needs a canvas no bigger than the stored preview (capped
  at 1024 px on its long edge), which for a Seestar stack means a small crop** — so it may not be reachable at
  all, and the *first* thing to do is find a real run where it fires. **If it is reachable, the honest fix is a
  genuine local density**: area-average the counts over a small neighbourhood before thresholding, instead of
  relying on the output resize to do it. **Care:** that would dim a lone hot pixel, which
  `test_pixels_that_lost_nothing_stay_fully_transparent` and `test_a_lone_hot_pixel_does_not_hide_the_trail`
  both pin — so it needs a shape that keeps a single high-count pixel opaque while spreading a count-1
  neighbourhood, not a plain box filter.

- **🟡 SWEPT ONCE, ONE UNTRUTH FIXED (Builder, v0.309.1, branch `claude/compassionate-galileo-x2nj2o`); the
  colour-space axis is still open below — QA LEAD (Builder 2026-08-30, generalised from the v0.308.1 copy fix)
  — sweep every download control's *copy* against what its endpoint actually serves.** *(Pillar: trust.)*

  **Found and fixed: "Full-res PNG (native size)" is not native size on a big mosaic — and History printed the
  exact dimensions the file misses.** `download_full_res_png` renders through
  `_FULL_RES_PNG_MAX_LONG_EDGE = 8000`, a deliberate ceiling that bounds the render's memory and the response
  on a RAM-capped NAS. Four surfaces described that file and none of them knew: the Target page's and the
  Dashboard strip's menu items said *"(native size)"*, the shared `ImageLightbox` menu said it on **three more**
  surfaces (Gallery, My best pictures, History's viewer), and History's artifact menu went furthest —
  *"Same look, full size (12000×9000 px)"*, quoting a number the download demonstrably does not have. Exactly
  the size axis this entry named, on exactly the picture where it matters: the owner's union mosaics, and
  discovered at the worst moment (trying to print from a backup). This is also the *destination* the v0.308.1
  fix redirected people to — the wall card now says "to print one, open it and choose Full-res PNG" — so the
  two lies were chained.

  **The fix is one sentence in one place.** New `frontend/src/fullres.ts` owns the wording
  (`fullResPngCapped` / `fullResPngLabel` / `fullResPngHint`), so five surfaces cannot drift into five claims
  about one file. Wording is **unchanged for every canvas the render really does serve whole** — the point was
  never to hedge everywhere, only to stop claiming native size where it is false; a capped picture gets
  *"Full-res PNG (up to 8000 px)"* and, where there is room for a hint, the canvas it was capped **from** plus
  the pointer to the FITS/TIFF that do hold those pixels. `ImageLightbox` takes an optional `fullResCanvas`
  (a surface that doesn't know the dimensions keeps the common wording, which is right under the cap), and
  `/api/stats`'s `recent_stacks` gained additive `canvas_w`/`canvas_h` so the Dashboard strip can answer too.

  **Upgrade-safe (§9):** two additive response fields with `0` defaults that read as "unknown" (an older
  frontend ignores them; an older backend omitting them gets the common wording). No config, schema, on-disk,
  default or API-shape change; the endpoint's behaviour is untouched — only what we *say* about it.

  **Tests (+11).** The claim is pinned to **bytes, not strings**, as the entry demanded:
  `tests/webapp/test_full_res_png.py` renders a canvas past the *production* ceiling (not an injected one) and
  asserts the served PNG is `!= native` and capped exactly at it, plus the boundary case *at* the cap coming
  back whole. `tests/test_fullres_cap_mirror.py` is the drift guard — the hand-mirrored TS constant against
  `_FULL_RES_PNG_MAX_LONG_EDGE`, same shape as `test_pace_constants_mirror.py`, because a stale copy would put
  the untruth straight back with nothing failing. Then `fullres.test.ts` (5) over the wording itself, and one
  test each on `ImageLightbox` and `History` that the capped picture stops claiming native size while an
  ordinary one still quotes its exact dimensions.

  **What the sweep found *not* to be wrong** — recorded so it isn't re-walked: the pictures zip (fixed in
  v0.308.1, and its "open it and choose Full-res PNG" pointer is now true too); "Quick preview PNG (up to
  1024px)" (`PREVIEW_MAX_WIDTH = 1024` is a *width* cap and History words it "up to 1024 px wide", which is
  exact); the JPEG, nameplate, scale-bar and keepsake items, which describe what they bake rather than a size;
  and the FITS, whose "Raw data — for re-processing, not sharing" is right.

  ~~**Still open, filed as its own item below:** the **colour-space** axis — the TIFF download carries *no*
  description at all, and a plain stack's TIFF is written **linear**, so it opens looking black.~~ — **DONE, and
  this line was stale** *(struck 2026-09-08 by a Builder that grepped before building)*: `frontend/src/tiffDownload.ts`
  owns the wording (`tiffOpensAsShown` / `tiffDownloadHint`) and every TIFF item renders it through the shared
  `SavePictureMenu` — *"16-bit raw levels — opens dark until you stretch it in another app"* for a linear stack,
  *"16-bit — the finished picture, at full depth"* for one saved in display space, with `tiffDownload.test.ts`
  pinning both. The
  **geometry** axis (cropped/rotated vs the stored canvas) was not swept.
  **▶ The geometry axis was then swept by the `…-e1p1x8` Builder and turned up a real one straight away:**
  "Full-res PNG (native size)" served a picture **rotated away from the one on screen** on any run saved North
  up — fixed as **v0.311.1**, entry at the top of "Bugs (fix these first)". The *crop* half of that axis (a
  preview that shows only part of the canvas) is still unswept.

  **▶ Swept independently in the same hour, on the SAME axis, by the `…-e1p1x8` Builder — and the two halves
  are complementary, not duplicates: that run fixed the FILE where this one fixed the COPY.** The wallpaper
  and the share JPEG were both *made out of* the 1024 px preview, so no wording could have made them honest —
  the presets name real device resolutions (1170 × 2532 …) and the endpoint fed the crop a third of that.
  Fixed as **v0.310.0** (wallpaper) and **v0.311.0** (share JPEG, keepsake and scale-&-compass), both entries
  filed below. So on the **size** axis the sweep now stands at: full-res PNG copy corrected (v0.309.1),
  pictures zip corrected (v0.308.1), wallpaper and share JPEG *re-sourced* (v0.310.0 / v0.311.0). Also swept
  and cleared by that run: the share JPEG's own "served at the same resolution" docstring, which was true and
  is now obsolete rather than wrong. ~~**Still open on size:** the **zoom clip** (built from the same preview,
  and the cap sets its resolution directly — 569 px where 640 was available)~~ — **SHIPPED v0.400.0**: the clip is
  now cut from the same cached share render every other hand-out already uses, so it comes out at the
  `CLIP_LONG_EDGE` it always asked for and its deepest frame is supersampled rather than the preview at 1:1
  (`_zoom_clip_source`, `zoom_clip_min_source_long_edge`, `ZOOM_CLIP_SOURCE_OVERSAMPLE`); entry in
  [`SHIPPED.md`](SHIPPED.md). **Still open on size:** the wallpaper/share on a
  **"Process target"** run, which both deliberately decline. Untouched on any axis: the montage, the wall, the
  print export and the imaging log.

  Original spec, for the record:

    *(Pillar: trust — PRIORITY 3; size S per surface, and the sweep
    itself is one run.)* "Download all my pictures" promised **"the full-size pictures themselves"** and handed over
    1024 px previews; nothing failed, no test caught it, and it would have been discovered by a user at the moment
    it cost them most (trying to print from their backup). That is a **bug class**, not one slip: a download's copy
    is written once, next to the button, and then the endpoint underneath it evolves — the picture it serves gets
    capped, re-rendered, cropped, tone-mapped or renamed — with nothing tying the two together. **The sweep:** for
    every control that hands over a file (the pictures zip, the montage, the wall, the keepsake, the print export,
    the wallpaper, the zoom clip, the share JPEG, the full-res PNG, the imaging log, each artifact kind on
    History's menu), read the sentence beside it and then read what the handler actually writes, and reconcile the
    two — **fixing the copy where the file is right, and the file where the copy is right.** The properties that
    keep drifting are **size** (capped preview vs native), **colour space** (linear TIFF vs display-space), and
    **geometry** (cropped/rotated vs the stored canvas). Where a claim is worth keeping true, pin it with a test
    that reads the served bytes rather than the string — `tests/webapp/test_north_up.py` is the shape.

- **PERF WATCH ITEM (Builder 2026-08-30, introduced knowingly by the v0.301.0 recipe-matched reveal) — the
  reveal's "before" is now a full edit pipeline per request, and nothing caches it.** *(Pillar: friendliness —
  PRIORITY 3; size S; measure before building.)* `reference-sub` has always debayered a full sub per request
  and answered `Cache-Control: no-store`; on an auto-edited run it now *also* runs the whole Auto recipe
  (gradient fit → colour calibrate → STF stretch → SCNR → saturation → auto curve, plus denoise/sharpen when
  the recipe carries them) over that sub, at the 1024-wide proxy scale. That is comparable to one live-preview
  render, in a threadpool, and only when the card is revealed — so it is very unlikely to matter, and it was
  shipped without a cache deliberately rather than guessing at one. **But measure it on the owner's box before
  assuming:** if a reveal on a big target is visibly slow, the pattern to copy is already in the same file —
  the noise-ratio endpoint's fingerprinted meta stamp (`NOISE_RATIO_META_PREFIX`, keyed on the master and the
  representative sub), which would key here on the sub *and* the recipe look, so a re-edit invalidates it.
  Don't add a cache on speculation; a stale "before" is worse than a slow one.

- **NEW IDEA (Builder 2026-08-27, spotted while fixing the v0.286.1 stack-time-crop sharpen bug) — the video
  still's stack-time crop *knows* its box and then throws it away, so every later operation has to infer the
  picture's shape from file sizes.** *(Pillar: trust / maintainability — PRIORITY 3. Size: S. Confidence:
  certain — this is the code the bug lived in.)*
  `_video_stack_body` computes `framing.box`, crops with it, and writes `crop_applied=True, crop_box=[]` —
  the empty list meaning "the *stack* did this, not an in-place edit". That overload is what made the
  v0.286.1 bug possible: two genuinely different on-disk shapes (a cropped soft backup vs a full-frame one)
  both present as "cropped, no box", and the fix had to recover the distinction by comparing PNG dimensions.
  That check is correct and now tested, but it is *inference where a fact was available*.
  **Shape:** record the stack-time framing in its own additive field (e.g. `stack_crop_box`, defaulting to
  `[]` so every existing `meta.json` reads exactly as it does today), leaving `crop_box` to mean only what it
  has always meant. The size test stays as the fallback for the stills already on disk — this is not a
  migration, it is making *new* stills self-describing. **Only worth doing alongside another change in
  `webapp/video.py`**, and only if the field earns its keep: if nothing but a comment would read it, the
  dimension check is already the honest answer and this should be closed rather than built. Explicitly do
  **not** rewrite the four in-place operations around it.

- **NEW IDEA (Builder 2026-08-17, the one thing deliberately left out of "Finish them all" v0.265.0) — put a real
  byte figure in the batch-export confirmation, without making the Dashboard's note expensive.** *(Pillar:
  friendliness / trust — PRIORITY 3; size S; **only worth doing if someone actually wants the number**.)* The
  confirmation currently says "N new sets of files, each about the size of the stack it came from" and points at
  Storage. That is true and enough to decide with, but it is a description rather than a measurement. **Why it
  wasn't just added:** `GET /api/gallery/unexported-edits` is read on every Dashboard visit and its stated design
  is that it does **no file stats at all** (`test_unexported_edits_never_lists_a_never_edited_targets_runs` pins
  the harder half of that), so summing each flagged run's existing outputs there would trade a cheap poll for a
  disk walk on every visit — the wrong side of the trade for a number nobody has asked for. **Slice, if it is ever
  wanted:** a separate `GET /api/gallery/unexported-edits/estimate` that the confirmation fetches **when the
  dialog opens**, summing the flagged runs' recorded `fits`/`tiff`/`preview` sizes (an editor export writes about
  the same set), so the cost is paid exactly when the user is deciding and never on the poll. **Care:** it is an
  estimate, not a promise — say "about", and don't block the button on it if the read fails.

- **PERF WATCH ITEM (Builder 2026-08-13, introduced knowingly by the ingest mtime fix v0.254.2) — a mass re-sync of
  `incoming/` now costs one FITS *header* read per touched frame, where it used to cost a QC reset.** *(Not a bug;
  recorded so a future run doesn't rediscover it as a mystery.)* `_same_capture()` only runs on the
  size-equal/mtime-moved path, so an ordinary re-scan of untouched files reads nothing extra and the hot path is
  unchanged. But the case it exists for is exactly the *mass* one: re-copy 8 000 subs without preserving
  timestamps and the next scan opens 8 000 headers. That is far cheaper than what it replaces (nulling QC on all
  8 000, re-QC'ing and re-solving them, plus the risk of an auto-stack firing in the gap), and it happens **once**
  per touch because the new mtime is adopted either way. **If it ever does show up as slow,** the cheap next step
  is to short-circuit on the *first* mismatch across a batch (if the first N touched frames all confirm as benign,
  the whole re-copy almost certainly is) — but measure before building that; a header read is milliseconds and the
  scan is already I/O-bound on the same files.

- **NEW IDEA (Builder 2026-08-08, the sibling question raised by shipping the walk-away quality weighting v0.251.0)
  — should the walk-away path also turn on `photometric_normalize`? NOT blind-shippable; needs a Scout vet on real
  data first.** *(Pillar: autonomy + image quality, PRIORITY 2/4; size S to build, M to justify.)* Weighting and
  photometric normalization answer the same complaint — *thousands of subs across nights of different transparency*
  — and the engine says they "compose cleanly" (`combine_weights_with_photometric`). Having just auto-enabled the
  first on the `auto=True` path, the obvious next question is whether the second belongs there too. **Do not treat
  this as a done deal, because the two are not equally safe.** Quality weighting only changes how much each frame
  *counts*, is floored at 0.1, falls back to a neutral 1.0 for any metric it couldn't measure, and is provably inert
  on the min/max path — worst case it does nothing. Photometric normalization *multiplies frame values* before they
  combine, so a mis-estimated scale changes pixels, and the "neutral fallback" only covers a frame with no
  `transparency_score` at all, not one with a bad score. It is also correctly off by default for that reason.
  **What a vet needs to establish, on the owner's real multi-night data:** (a) that the per-frame scales land in a
  sane band on an ordinary clear-night set (i.e. it's ~inert when transparency really is uniform, so we're not
  paying pixel risk for nothing); (b) that a genuinely hazy night is scaled *up* by a plausible factor rather than
  amplified into noise; and (c) that the rejection spread narrows rather than widens. **Related and already filed:**
  the "nudge the user on the Stack form when the transparency spread is wide and `photometric_normalize` is off"
  idea (search `suggest_photometric_normalize`) — that nudge is the *lower-risk half* of this and could ship first,
  since it asks the user rather than deciding for them. **If it does get built, mirror v0.251.0 exactly:** inject
  only on `auto=True`, only when the merged options carry no explicit key, and leave the engine default False.

- **NEW IDEA (Builder 2026-08-06, MEASURED while building the highlight suggestion v0.240.0) — "Hold back
  highlights" is close to a *no-op* on the very frames it is most needed for, because the shoulder runs
  **before** the midtones transfer squashes it back together.** *(Editor quality / image quality — PRIORITY 1/4;
  size M; **measured, not yet filed as a bug** because the current behaviour is a limitation of where the knee
  sits, not a regression.)* `autostretch` applies `_highlight_rolloff(xr, knee)` and *then* `_mtf(x, m)`, with `m`
  solved so the sky median lands on `target_bg`. On a high-contrast frame the sky sits at a tiny fraction of the
  99.5th-percentile normalization ceiling, so `m` goes very small and the MTF becomes near-vertical at the top of
  its range — which undoes the shoulder. **Measured** on a synthetic bright-core scene (sky at 0.036 % of the
  ceiling → `m = 0.00144`): walking the knee its whole range, 0.70 → 0.25, moved the post-shoulder core from
  0.850–0.903 to 0.625–0.692 — but *after* the MTF both render as **0.999–1.000**, i.e. the slider changes the
  finished picture by less than a thousandth and the core stays flat white. On an ordinary compact-core frame
  (`m` ≈ 0.3) the same slider works exactly as advertised, which is why v0.237.0's tests pass. **Consequence
  today:** the v0.240.0 "from your image" button correctly self-hides there (it refuses to offer a strength that
  can't help — pinned by
  `test_highlight_suggestion.py::test_no_suggestion_when_the_knob_cannot_meaningfully_help`), so nobody is misled;
  but the owner also has no fix for a genuinely blown core on such a frame. **Shape of a fix:** make the shoulder
  act on the *rendered* tone rather than the pre-transfer one — e.g. apply the rolloff after `_mtf` (in display
  space, where the knee means what the user thinks it means), or fold the protection into the `m` solve so the
  transfer is shoulder-aware. **Care — this is the on-by-default render path** (`autostretch` is the fallback
  stretch for *every* preview and thumbnail): the knee's default must stay byte-for-byte, so any change has to be
  gated on `highlight_protect > 0` and re-measured against `tests/test_stf_highlight_rolloff.py`'s
  sky-unchanged/monotone invariants. Worth doing with a before/after on the same scenes the suggestion tests use.
  _(**Builder 2026-08-06, `claude/gallant-galileo-gv2vcx` — PROTOTYPED AND MEASURED, then deliberately NOT shipped.
  Read this before spending a run on it.** Built the entry's own "fold the protection into the `m` solve" shape: pick
  the shoulder's knee in **display** space (sweep 1.0 → 0.85 as `protect` goes 0 → 1) and map it back through
  `_mtf`'s closed-form inverse, taking `min()` with today's linear knee. It is exactly gated as the entry asks —
  `_mtf_inverse(1.0, m) == 1.0` for every `m`, so `protect=0` is byte-for-byte the historical render and an ordinary
  frame (`m` ≈ 0.3, where the linear knee is already the lower of the two) is unchanged at every strength.
  **The measurements are the reason it didn't ship.** On the pathological frame the entry describes (`m` clamped at
  its 1e-3 floor) it halves the pure-white plateau — flat-at-1.0 core pixels **741 → 385** — but the core's rendered
  span barely moves (18 → 19 distinct 8-bit levels, std 0.0174 → 0.0173), because the display knee only fixes *where*
  the shoulder starts: above it the MTF is still near-vertical, so the shoulder's own top two-thirds still crowd into
  the last 0.15 % of the display range. **And that regime looks unreachable from real data:** a Seestar stack is
  derived from a 16-bit sensor, so max/sky ≲ 65 and the 99.5th-percentile ceiling can't sit ~2800× the sky the way
  the synthetic scene needs. Swept realistic scenes (sky 1000 ADU, core peaks 20 k–1 M, three core widths, with a
  disk): `protect=1` already leaves **zero** flat-white pixels today, and the change buys **~10 %** more core
  contrast (e.g. std 0.01191 → 0.01324) — a marginal gain that would still change pixels for anyone who has moved
  the slider or tapped "Core blown out". Per AGENTS.md §2 that is not worth shipping. **What would actually be
  needed** is the *data-referred* (log-scaled) shoulder from the sibling entry above — a genuinely different curve,
  not a repositioned knee — and that one is real-data-gated on the owner's own M31/M42 stack. So: don't re-derive
  the display-knee prototype; if this is picked up again, start from the log shoulder and get owner data first.)_
  ~~**NEW IDEA (Builder 2026-08-06, follow-on to v0.240.0) — the highlight suggestion is a ready-made way to
  collect the real-data evidence the *automatic* highlight-clip cue is gated on.**~~ — **SHIPPED v0.382.0**
  (`AUTO_EDIT_HIGHLIGHT_PREFIX` + `editor.solve_highlight_protect` + `pipeline.auto_highlight_summary`).
  Entry in [`SHIPPED.md`](SHIPPED.md).
- **NEW IDEA (Builder 2026-08-04, spotted while shipping "Point here right now" v0.231.0) — say "another hour
  would cut its noise about N%" in *one* voice across the app.** *(Friendliness / trust — PRIORITY 3; size S;
  pure dedup with a real user payoff.)* The new `nightplan.noise_gain_from_more_time(t)` = `1 − √(t/(t+1))` is the
  honest, beginner-legible answer to "would more subs help?", and the best-tonight card now says it in plain
  words. But the app has **several other places that answer the same question in different currencies** — the
  per-target integration goal / "is it enough yet?" readiness verdict, the `integrationTrend` line, and the
  "cut your noise ~N×" at-completion badge — each with its own framing. A beginner reading two of them shouldn't
  have to reconcile them. **Slice:** reuse the one helper (or its frontend mirror) so the readiness surface can
  add the same sentence, and check the wordings agree on the *direction* and *magnitude* of the claim. **Care:**
  don't collapse genuinely different questions into one — "have I shot enough?" (a goal) and "would another hour
  help?" (a marginal return) are related but not the same; this is about the *marginal-return* sentence only.
- **NEW (Builder 2026-07-30, found while shipping the Check & locate outcome line v0.222.2) — the legacy desktop
  dialog reports "solved N/M" from a *progress counter*, so it claims a perfect solve on a field where nothing
  located.** *(Correctness of a user-facing figure — but in the **deprioritised** desktop GUI, so low priority;
  size XS.)* `seestack/gui/library_dialog.py:147` prints
  `f", solved {summary['solve_done']}/{summary['solve_total']}"`. `solve_done` is `_map_jobs`' progress counter —
  frames *attempted* — so it reaches `solve_total` even when every solve failed; the line reads "solved 40/40" on a
  star-poor field that located nothing. This is the exact defect the web Jobs page just avoided: `run_qc_and_solve`
  now also returns an honest **`solve_ok`** (results that came back with a usable WCS), so the fix is to read that
  instead and fall back to omitting the clause if it's absent. Left unfixed here deliberately — the desktop GUI is
  historical (`PLAN.md`-era) and its only tests are the three Qt ones, so a drive-by change at merge time wasn't
  worth it; take it if you're already in that file. Confidence: traced (the counter semantics are proven by
  `tests/test_solve_runner.py::test_run_qc_and_solve_reports_the_frames_it_actually_located`).
- **If a same-sky-area auto-merge is ever wired up, gate it on same-framing.**
  *(S, correctness — PRIORITY 2; latent, no live caller today.)* `library.
  find_target_within()` exists but is currently unused, so nothing folds a mosaic
  target into a single-field one by proximity. If a "merge by sky position" feature
  is built, it must **not** merge a mosaic target (`"<T> (mosaic)"`) into a
  single-field `"<T>"` (or vice-versa) just because they solve to the same region —
  their footprints/canvases differ. Gate on both-single-field or both-the-same-mosaic,
  not proximity alone. (Recorded here so the guard isn't forgotten when the merge
  lands.)

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
  **▶ RESPONSIVENESS, FIRST BITE — ✅ v0.382.2 (`webapp/edit_fit_cache.py`):** the
  measurements an op makes before it touches a pixel (the stretch's stats, the
  curve's points, colour calibration's star solve) are now carried from one
  live-preview render to the next for the **longest common prefix** of enabled
  ops. Measured on a 1500×1000 proxy carrying the one-click Auto recipe: **4.25 s
  a render → 2.39 s (1.78×)**, output **bit-identical**. Full entry, and the
  measured next slice, in [`SHIPPED.md`](SHIPPED.md).
  **▶ SECOND BITE — ✅ v0.382.3 (`seestack/edit/proxy.py::_load_map`):** and the
  bigger half was not in the ops. Each render also read the run's **full-resolution**
  coverage *and* frame-coverage canvases whole (`np.asarray(fits.getdata(…),
  float32)` materialises despite the memmap) before striding them to the proxy —
  two maps × two requests = four full-canvas reads and allocations per edit, on
  canvases that are hundreds of MB at this owner's mosaic sizes. Slicing before
  the cast: **2.65 s cold / 0.21 s warm → 0.011–0.021 s** per read on a 480 MB
  map, identical values.
  _(Builder note 2026-07-10: closed the big proxy↔export gap in the mosaic
  "Coverage leveling" op — its per-level pixel-count floor is now scaled by
  proxy_scale so the same panels are leveled in preview and export, v0.103.16
  (see Bugs → fixed). A **smaller, second-order parity nuance remains in the same
  op** and is filed here rather than blind-fixed: `level_by_coverage`'s object-mask
  dilation (`dilate_object_mask_px=4`) is a **fixed pixel count applied at both
  resolutions**, so on a ×N proxy it grows the star/nebula mask by 4 strided px ≈
  4·N full-res px — a wider sky exclusion than the export's 4 full-res px, which
  can shift a per-level sky median slightly between preview and export. Low
  severity (the median is robust to a few extra masked edge pixels, and the offset
  it shifts is tiny), so it didn't clear the bar for churn this run. If a future
  run touches this op, scale the dilation like the other pixel params
  (`round(4/step)`, matching `ctx.scaled_px`), guarding the step≥8 case where it
  rounds to 0. (S, editor/parity))_
  _(Builder note 2026-07-10, second addendum — verified while dogfooding a real 2×2 mosaic editor path
  (parity p99 1.5%, healthy): **measured the dilation nuance above and it is genuinely negligible** — on a
  ×4 proxy the far-sky per-level median it shifts moved only ~1e-4 of range (−4e-5 export vs −1.6e-4 proxy),
  well below the documented ~2% decimation-parity floor, confirming the "didn't clear the churn bar"
  disposition. **A distinct, symmetric floor nuance in the same op is worth folding into the same eventual
  fix:** the `_MIN_STRIDED_PIXELS = 12` safety floor makes `effective_min = max(12, round(200/step²))`, so on a
  *heavily*-strided proxy (step≥5 — reachable only on a very large mosaic canvas >7500px) the proxy requires
  **more** full-res-equivalent sky pixels than the export (step5→300, step6→432, step8→768, vs the export's
  200), so a thin panel with 200–768 full-res sky pixels is leveled in the export but *skipped* in the preview
  — the same preview≠export class the v0.103.16 fix closed at moderate stride, re-opening at heavy stride.
  Both are the *same* op and would be fixed together; both are low-severity edges (the floor is a deliberate
  "never median over a handful of pixels" guard, so any fix must keep a sane absolute minimum rather than let
  the proxy median run over <12 pixels). Neither cleared the churn bar alone; recorded so a future run in this
  op resolves the dilation scaling **and** the heavy-stride floor in one pass. (S, editor/parity))_
  **— BOTH NOW RESOLVED (Builder 2026-08-06, branch `claude/relaxed-turing-6zdskv`).** The **dilation
  scaling** turned out to have been done already: `edit/ops/background.py::_level_coverage` passes
  `dilate_object_mask_px=_scaled_box(ctx, 4, minimum=0)`, so the preview's object-mask halo is already a
  full-res-equivalent measure. The **heavy-stride floor** is fixed in **v0.237.2** — see the Shipped entry
  "Level a big mosaic's thin panel the same way in the preview and the export". Reproduced and measured on a
  ×6 proxy: the preview left a small overlap panel's **entire 162.7 ADU** offset in place while the export cut
  it to 30.0 (a **132.6 ADU** preview↔export divergence); the preview now lands on **30.7**. The floor is
  *not* loosened — `_MIN_STRIDED_PIXELS` still gates *measuring* a median — it is only no longer allowed to
  drop the level out of consideration, so a level it can't measure takes the neighbour-interpolated offset the
  export already gives its own unmeasurable levels.
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
  _(Builder note 2026-07-14, found dogfooding the beginner editor flow — **SHIPPED v0.121.6**
  (branch `claude/pensive-faraday-47ditq`): the editor showed an **endless spinner with no error**
  when its run was missing/deleted (a stale "View result" link, or the stack run deleted from
  History). `EditorView`'s render guard checked only `saved.isLoading`; on a `getRecipe` 404
  `isLoading` is false but `saved.data` is undefined, so the chrome rendered while the preview
  never seeded (the seed effect needs `saved.data`) — the panel fell through to a `<Loader/>`
  forever. There was no `saved.isError` branch anywhere, unlike the sibling `Target.tsx` route
  (which shows a `QueryError` + Retry for exactly this deleted/stale-link case). Fix: after the
  loading guard, show the shared `QueryError` (Retry) when `saved.isError && !saved.data` — and
  the same for `opsSchema` (the editor can't function without the op schema) — each gated on
  `!data` so a background-refetch blip never blanks a working editor. Frontend-only, additive; no
  backend/schema/API/default change. Regression `Editor.test.tsx::"shows a recoverable error, not
  an endless spinner, when the run is missing"` (getRecipe rejects → asserts the error card + Retry
  appear and the editor chrome does not; fails before as it spins). (S, editor/error-handling —
  PRIORITY 1.))_
  _(~~Builder note 2026-07-12, found in an adversarial frontend-editor-route audit: "Compare a
  look" → "Switch to this look" (`adoptLook`) silently dropped the user's crop/geometry — it set
  the look's **raw** ops, while the split preview the user was judging renders the look on the
  current edit's framing via `lookCompareOps(lookSel.ops, baseGeometryOps)`. So a user who cropped,
  compared a look, then switched to it got the **uncropped** frame — a different image than the
  split they'd just evaluated (WYSIWYG violation on the PRIORITY-1 editor compare→adopt loop).~~ —
  **SHIPPED v0.109.20** (Builder 2026-07-12). `adoptLook` now adopts exactly what the divider showed
  — `lookCompareOps(lookSel.ops, baseGeometryOps)` (the look's tone/colour/detail on the current
  recipe's enabled geometry ops) — so the adopted recipe renders identically to the compared split.
  A no-op when the current recipe has no geometry op (the look's ops verbatim, exactly as before), so
  the common case is byte-for-byte unchanged. Frontend-only, additive, one undoable step; no
  backend/schema/API change. Regression `Editor.test.tsx::"preserves the current crop when adopting
  the compared look (WYSIWYG)"` (crop in the recipe → compare a Curves-only look → Switch → assert
  both Curves **and** Crop survive; fails before as the crop is dropped / passes after). (XS,
  editor/consistency — PRIORITY 1.))_
  _(Builder note 2026-07-10: the `edit/ops/detail.py::_hot_pixels` NaN-fill/restore band-aid
  (the `_with_nan_filled` wrapper) is now **redundant** — v0.103.23 made
  `bg/hot_pixels.py::suppress_hot_cold_pixels` NaN-aware at the root, so the op no longer needs a
  caller-side shim to avoid no-oping on a mosaic/partial-coverage image. Low priority and not worth
  churn on its own: the shim is harmless (it feeds NaN-filled input to an already-NaN-safe function).
  If a future run is already in `detail.py`, it could drop the wrapper for `_hot_pixels` and call
  `suppress_hot_cold_pixels` directly — but only after confirming byte-for-byte parity (the shim
  repairs a hot pixel *at* a coverage boundary using a median-fill neighbourhood, where the root
  function leaves it, so verify that edge doesn't matter on a real mosaic before simplifying). (S,
  editor/maintainability))_
  _(~~Builder note 2026-07-11, found during the frontend editor-logic audit that shipped v0.109.6/v0.109.7:
  the editor's **histogram** query (`Editor.tsx` `hist = useQuery(["edit-hist", …])`) is **not** gated on
  `seeded`, unlike the `preview` query right above it…~~ — **SHIPPED v0.109.19** (Builder 2026-07-12). The
  `hist` query is now gated `!!opsSchema.data && !saved.isLoading && seeded`, mirroring the live preview, so it
  no longer fires against the empty pre-seed recipe before the saved recipe loads — removing a wasted request
  and the brief pre-seed histogram/clipping-advisory flash on first open (most visible on the walk-away
  Process-target deep-link, which opens on a saved auto-edit recipe). Frontend-only, additive; no
  backend/schema/API change. Regression `Editor.test.tsx::"does not fetch the histogram until the saved recipe
  has loaded"` (holds the recipe query pending and asserts `getHistogram` isn't called until it resolves —
  fails before / passes after). Upgraded from "too low-value to ship standalone" because it's on the PRIORITY-1
  editor default surface and the north-star walk-away flow lands there with a saved recipe, so the flash is
  genuinely user-visible there. (XS, editor/polish.))_
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
  _(Builder note 2026-07-11 — re-traced this after the v0.109.0 change and it is **not a clear win; do
  not blind-take it.** Two things have shifted the premise: (1) the empty-recipe "Original" render no longer
  uses the fixed asinh 0.5/0.35 — since v0.109.0 both editor fallbacks call `render.thumbnail.autostretch`
  (STF) at the **preview** `target_bg≈0.20`, so it already resembles the stored thumbnail's algorithm. (2) But
  the stored `preview_path` uses `_autostretch_for_export`, which is deliberately a **much milder** stretch —
  `target_bg=0.06, sigma_factor=-2.8` (`stack/output.py::_autostretch_for_export`, "sky at ~6% grey … deeper
  shadows clipped") vs the editor proxy's ~20% grey. So serving the stored preview as "Original" would make the
  A/B *baseline* markedly **darker** than the edited image on screen — arguably a **worse** before/after
  reference than the current same-exposure empty-recipe render, not a better one. The editor's Compare is an
  interactive same-view A/B, not an attempt to reproduce the History thumbnail; matching the thumbnail's
  exposure isn't obviously the right goal. If a future run still wants "literally what the user saw", it should
  first decide whether the darker export exposure actually reads better in the A/B (needs a real-image look), and
  handle the ≤1024 px vs ≤1500 px size mismatch under the Split divider. Left filed but **down-weighted** — this
  is a judgment call, not a blind fix.)_

### Autonomy — "just works" (PRIORITY 2)

- Auto-suggest stack settings from the data (frame count, FWHM spread, streaks)
  so the user rarely needs to touch the Stack form. (S–M, autonomy)
  _(Progress: the Stack form already carries a rich set of data-driven nudges
  (calibration picks, sigma/min-max frame-count guards, streak→min-max-k, transparency
  → quality-weight, transparency-spread → photometric-normalize, auto-grade drop-outliers,
  memory sizing). As of v0.84.6 every one of them is now one-click. A proactive **drizzle**
  nudge shipped v0.87.0 (see Shipped): on a large single-field set (≥200 accepted, solved
  frames — matching the field help's "200+ dithered frames") whose drizzle-*on* dry-run sizing
  fits the memory budget, the Stack form now suggests Drizzle with a one-click "Turn on
  Drizzle", so a beginner sitting on thousands of subs reaches the biggest resolution win
  without hunting the advanced knobs — gated on a feasibility estimate so it never nudges
  toward an OOM-refused run. Remaining genuine gaps a future run could pick up, each needing a
  careful classifier: **lucky_fraction** from FWHM spread (contentious — it drops signal, so
  weigh against quality-weighting); a background/gradient flatten nudge from a measured sky
  gradient.)_

- **NEW IDEA (Scout 2026-08-27 #17) — surface calibration *match confidence* on the interactive Stack form, so a
  watching beginner gets the same smart dark/flat matching the walk-away path already does — and understands why
  calibration is or isn't applied.** *(Pillar: autonomy + friendliness + image quality — PRIORITY 2/3. Size: S.)*
  **Why (real gap).** The unattended chains already auto-bind the library's best *confidently-matching* master
  dark/flat/bias when a walk-away stack has no calibration chosen — the whole `_confident_master_binding` →
  `calibration.auto_bind_master_paths` machinery exists and compares the target's median exposure/gain/temp and
  modal frame dims against every master (`webapp/pipeline.py:2122`, `2299`). But the **interactive Stack form**
  gets none of that intelligence: today its Calibration box only says either *"No masters built yet"* or shows a
  raw picker, and a beginner who *has* built a master has no idea whether it actually fits these subs. A 10s dark
  bound to 30s lights makes the picture **worse**, silently. **Proposal:** when masters exist, run the same
  read-only confidence check for the target being stacked and show a one-line verdict in the Calibration box —
  green *"Your darks & flats match these subs (30s · gain 80)"* when auto-bind would confidently pick them, amber
  *"Your only dark is 10s but these subs are 30s — it may not help"* when nothing matches, and offer the
  confident pick as the default selection so the interactive path lands on the same masters the walk-away path
  would. Pure surfacing of logic that already exists and is already tested engine-side; no new matching rules, no
  default flip (the user still chooses), no schema/config change. Fits the "reduce the number of decisions"
  mandate: the beginner stops having to *know* what a matching dark is. **Grep first:** `routers/stack.py` /
  `get_stack_defaults` — confirm the form doesn't already thread a confidence hint before building; reuse
  `_confident_master_binding` rather than re-deriving the match.
  **Builder 2026-08-29 — did that grep, and the premise is largely already false. RESHAPE BEFORE BUILDING.**
  The entry's claim that the Calibration box "only says either *No masters built yet* or shows a raw picker" is
  not what `routes/Stack.tsx` does. It already queries `calibrationSuggestions(safe)` and, via
  `src/calibrationFit.ts`, already renders: a **per-option misfit suffix** on every master in the picker
  (`masterOptionSuffix`, so a wrong-size master is visibly unusable), an **exposure-mismatch caution** naming
  both numbers and the fix ("This dark was shot at 10s but your subs are 30s — …"), a **temperature-mismatch
  caution**, a **bias-size warning**, a **"scale it with a master bias" nudge** when the library holds one, a
  **dark-already-contains-bias** note, and a prominent **"you have masters but aren't using them"** advisory
  with a one-click **apply-recommendation** button. So "a beginner has no idea whether it fits" is not the live
  behaviour, and a green/amber verdict on top of that would be a *sixth* piece of calibration copy on a form the
  owner already calls too busy.
  **What is genuinely left, and it is small:** the form's recommendation follows `recommend_masters` (best
  *available*), while the walk-away path follows the stricter `auto_bind_master_paths` (best *confident*) — so
  the two paths can pick differently, and the form never says "this is what the unattended stack would have
  chosen". The worthwhile slice is therefore **agreement, not more copy**: surface the confident binding as the
  pre-selection / one-click recommendation so the interactive path lands where the walk-away path would, and let
  the *existing* cautions keep doing the explaining. Do not add another advisory line.

  **✅ SHIPPED — that remaining slice (Builder, v0.321.0, branch `claude/wizardly-feynman-isps6l`).** Built exactly
  as the reshape asked: **agreement, and not one new line of copy.**

  **What the disagreement actually was.** `recommend_masters` ranks a dark by *combined* distance
  (exposure ×3 + gain + temp) and returns the single closest, so an **exposure-perfect but gain-mismatched**
  dark out-ranks a **gain-matched** dark that only needs bias-scaling. The unattended binder already knows
  better — it tries every dark in ascending distance and takes the first that clears a confidence gate — so on
  that library the Stack form recommended one dark and a walk-away stack of the same subs used another, and
  nothing on screen said so.

  **One function now answers "which masters for these subs?".** `auto_bind_master_paths` is refactored into a
  new `auto_bind_master_ids` (the decision) plus a thin path-resolving wrapper (what a run needs), sharing one
  `_BOUND_ID_TO_PATH_KEY` table, and `/calibration-suggestions` serves the ids as an additive `confident` key.
  A test pins the two forms as **one decision by construction** — every id resolves to exactly the path the
  unattended binding produces, and a kind absent from one is absent from the other — so they cannot drift
  apart again. The coverage roll-up (`master_coverage`) now reads the ids directly instead of resolving each
  binding to a file and looking the id back up in the registry.

  **The form prefers the confident pick where there is one, and is never *less* helpful than before.** The
  reconciliation is a pure `masterRecommendation` in `calibrationFit.ts`, with two deliberate couplings rather
  than a per-field merge: a **flat-dark travels with its flat** (the best-available flat-dark was matched to a
  different flat, so it is stale the moment the confident binding picks another), and a **bias is only offered
  beside a dark when it is there to *scale* that dark** — in which case "Use recommended" turns
  `scale_dark_to_light` on with it, because half of that pairing leaves the pedestal mis-subtracted. Where the
  binder is silent (nothing confident, or an older backend), every field falls back to today's best-available
  answer and the existing cautions explain it — which is the right behaviour with a human watching.

  **Upgrade-safe (§9):** one additive response key, one additive optional client field, no config, schema,
  on-disk, default or existing-response-shape change; `auto_bind_master_paths` returns exactly what it did
  (its 78 existing tests pass untouched), so the unattended path is byte-for-byte unchanged.

  **Tests (+5 python, +8 frontend; the two Stack-form ones fail before).** Python: the ids-and-paths
  agreement-by-construction, the scaling triple carried in id form, an empty answer when nothing is confident,
  and the endpoint serving `confident` — asserted **against the binder itself** rather than a copy of its
  answer — plus the wrong-camera case where the best-available recommendation still names a master and the
  confident one says nothing. Frontend: six `masterRecommendation` cases (fallback, preference, the flat-dark
  pairing, the bias+switch pairing, never half a pairing, bias-only-without-a-dark) and two on the real form —
  the badge and one-click landing on the gain-matched dark *with* its bias and the scaling switch, and the
  no-confident-pick case keeping today's recommendation and its warning.

- **IMPROVEMENT IDEA (Scout 2026-07-24) — a WCS-free star-registration *fallback* so a faint field whose subs mostly
  fail to plate-solve can still stack from all its frames, instead of collapsing to a ~1–3-frame gibberish stack.**
  *(Autonomy + image quality — priorities 2/4; a direct attack on the remaining root of the ⭐⭐ thin-stack/gibberish
  top bug. Size L — file as a scoped Builder slice, and flag the dependency question below for owner sign-off before
  any new package lands.)* **Why this is the highest-value autonomy gap:** the whole engine registers frames via ASTAP
  WCS + reprojection, and `run_stack` combines **only accepted *and* solved** frames. On a faint / sparse-star target
  ASTAP fails on most subs (the documented root cause the sibling-hint seeding v0.180.0, unsolved-surfacing, and the
  relaxed-retry idea all *mitigate* but can't fully cure — a genuinely star-poor field may be unsolvable no matter the
  hint). So hundreds of accepted subs sit unsolved and never stack, and the "stack" is the handful that did solve →
  per-pixel colour speckle. **The idea:** when a run would stack far fewer frames than were accepted (e.g.
  `solved << accepted` and `solved < auto_stack_min_frames·k`), fall back to registering the *unsolved* accepted subs
  to the solved reference (or to the best sub) by **star-pattern matching** — the classic astro fallback DSS/Siril use
  when there's no plate solution. **Non-trivial, be honest about it:** the Seestar is alt-az, so field *rotation*
  accumulates over a night — a translation-only phase-correlation (what `align.py` already uses for subpixel refine)
  is **not** enough; this needs a **similarity transform** (translation + rotation + modest scale) from matched star
  triangles. Options: an in-house triangle-hash matcher over the QC star centroids we *already* detect (no new dep,
  more work), **or** the small pure-Python `astroalign` package (fast to build, but a **new dependency → per §9/§10
  record the sign-off** before adding). **Shape / guardrails:** additive and **opt-in / automatic-only-as-a-fallback**
  (never replaces a good WCS solve; engages only when solved-frame count is pathologically low), memory-bounded like
  the existing path (register→reproject one frame at a time, no unbounded accumulation), and must degrade safely
  (a frame that fails star-matching is simply left out, exactly as an unsolved frame is today — never corrupt).
  Surface it honestly on the result ("N of M frames stacked by star-matching — plate-solving couldn't locate them").
  **Tests:** synthetic faint few-star subs with a known rotation+shift, most WCS-unsolvable → the fallback recovers
  ≥K frames and output noise falls ~√N (vs single-frame today); a normal solved night is untouched (fallback never
  engages). **Why it's an *idea* not a fix:** it's a new registration path on the hot path + a possible dependency, so
  it needs a careful Builder slice (and the astroalign-vs-in-house/dependency call belongs to the owner). But it is the
  single most direct cure for the owner's real "gibberish on faint targets" report — worth prioritising once the
  cheaper solve-side mitigations are exhausted.
  **▶ VALIDATED IN PART (Audit 2026-07-24, real ASTAP CLI + d05):** the companion stack-then-solve bootstrap
  measured out — a plain mean of 8–16 subs at a faintness where a single sub detects 0–2 stars detects 6–12 (solvable),
  robust to ±2 px uncompensated drift, so the "solve the deep image, propagate WCS by registration" plan is sound and
  integer-shift-level registration is enough for a short tracked burst. See the ⭐⭐ thin-stack entry's ▶ block for
  numbers.
  **▶ PARTIALLY DELIVERED by the stack-then-solve bootstrap (v0.210.0).** The shipped bootstrap
  (`seestack/solve/bootstrap.py`) already recovers the common tracked-burst case with **translation-only** integer
  registration (phase correlation) — enough for the short sharpest-N window it integrates, per the ±2 px jitter
  measurement. This idea (a full **similarity** transform tolerant of accumulated alt-az **field rotation** across a
  whole night, and/or registering *every* unsolved sub rather than just bootstrapping the deep image) remains the
  more general L attack for long sessions where rotation between the first and last sub exceeds what a translation can
  absorb. Still gated on the astroalign-vs-in-house dependency call (owner sign-off). Reassess after the bootstrap has
  been validated on real faint-field data — the bootstrap may cover enough of the owner's cases that the full-rotation
  path isn't needed.

- ~~**IMPROVEMENT IDEA (Builder 2026-07-25) — let the bootstrap anchor on an already-solved sub when a few
  (but < min_frames) subs did solve, instead of always re-solving the deep image.**~~ — **✅ SHIPPED v0.412.0**
  (`solve/bootstrap.pick_solved_anchor` + `BootstrapResult.anchored_on_solved_sub`). Entry in
  [`SHIPPED.md`](SHIPPED.md).
- **IMPROVEMENT IDEA / SCOUT TASK (Builder 2026-07-25) — validate the stack-then-solve bootstrap on real
  faint-field data, then consider promoting `astap_bootstrap_solve` to on-by-default.** *(Autonomy — PRIORITY 2;
  size S for the Scout.)* The v0.210.0 bootstrap ships **off by default** because its gain was measured on
  *synthetic* subs; the propagation math is ground-truth-tested but the end-to-end "does it actually rescue the
  owner's real faint targets" gain needs confirming on real Seestar data (the audit harness in the plate-solve
  audit's scratchpad — `detect_exp.py`/`bootstrap_exp.py` — plus a real faint-field sub set). If it reliably lifts
  real un-located fields into a clean stack with no mis-placement, promoting it to on-by-default would make the
  owner's #1 pain "just work" without a settings trip. Until then it stays opt-in per §9.
- **▶ PARTIAL — refusal message half SHIPPED v0.184.13** (Builder 2026-07-24, branch `claude/pensive-faraday-xok0ew`;
  regression-tested). The `_guard_stack_memory` `MemoryError` (surfaced verbatim on the failed stack job) now names the
  **single least-destructive concrete lever** that brings the run within budget, with the memory it lands at — instead
  of the generic four-lever dump. New pure `_best_memory_fix(dst_shape, ref_shape, …)` (`seestack/stack/stacker.py`)
  reuses `_estimate_peak_bytes` (so the named "~X GB" can never disagree with the refusal threshold) and mirrors the
  levers `estimate_stack` already surfaces pre-submit: drizzle on → "lower the drizzle scale to ×N"
  (`_largest_drizzle_scale_within_budget`); non-drizzle, least-destructive first → "lower Extra outlier passes to 1"
  (k>1 min/max) then "switch Canvas mode to 'reference'" (mosaic union whose ref frame fits). When no single lever
  obviously fits, it keeps the generic guidance. `run_stack` now threads `ref_shape`/`is_mosaic_canvas`/effective
  `min_max_reject_count` into the guard. Engine-only, additive (new optional guard kwargs default to the old behaviour),
  **no change to *what* is refused** (same threshold) — upgrade-safe, no config/DB/API-shape/default change. Tests:
  `tests/test_stack_memory_guard.py` (+4 — drizzle-scale/reference-canvas/drop-extra-passes each named with its GB;
  generic fallback when nothing single fits). **Remaining (smaller follow-up): the pre-submit UI half** — add the
  ranked fitting options + their resulting peak to `StackEstimate` (it already computes `suggested_drizzle_scale`/
  `suggested_reference_canvas`) and render them as one-click actions on the Stack form, so the fix is offered *before*
  the run is even submitted, not only on the refusal. *(Original idea kept below for provenance.)*
- **IMPROVEMENT IDEA (Scout 2026-07-23, targets the ⭐⭐ top bug's root cause) — auto-retry a failed plate-solve with
  progressively relaxed ASTAP parameters on faint/sparse fields before giving up, so more subs get located and the
  auto-stack combines more frames instead of shipping a thin/gibberish result.** *(Autonomy + image-quality pillar,
  PRIORITY 2/4; size M; additive — no new deps, ASTAP is already bundled.)* **Why:** the top open bug is that faint,
  few-star fields yield single-frame speckle because most subs *fail plate-solve* and are silently dropped from the
  stack. v0.180.0 already borrows a solved sibling's centre as a hint; a complementary lever is that ASTAP itself
  often solves a faint field on a **second pass with a wider search radius, a lower star-detection threshold, or a
  larger max-star count / longer timeout** — the defaults are tuned for a typical field and are too strict for a
  sparse one. **Shape:** in `seestack/solve/runner.py`, when a solve fails with a "no match / too few stars" class of
  error (not a "no star database" setup error — that needs the banner, not a retry), retry once or twice with a
  relaxed parameter set (widen radius, lower the star threshold, raise the timeout modestly) before recording
  `solve_failed`. Keep it bounded (retry budget + a hard timeout cap) so it can't blow up ingest latency on a
  genuinely un-solvable frame, and log the relaxed-solve success rate so the effect is measurable. **Sane default:**
  the relaxed retry is automatic and invisible when the first pass already succeeds (the common case), so no behaviour
  change on bright fields; it only adds attempts where a frame would otherwise be dropped. **Validate** on a real
  sparse-star field (or synthetic few-star subs) that the relaxed pass recovers solves the strict pass misses without
  a flood of false/wrong solutions (guard on the solve's own residual/match quality). Tests: a `solve_failed`
  no-match path triggers the relaxed retry; a "no star database" path does **not** (still surfaces the setup banner);
  the retry budget is honoured. *(Feasibility: uses the already-bundled ASTAP, additive, bounded, testable — passes
  §4's filter. Ties directly to the highest-priority owner-reported issue.)*
  **▶ MEASURED (Audit 2026-07-24) — scope this DOWN before building:** most sensitivity levers this entry guesses at
  measured as **non-levers** on realistic faint Seestar frames (real ASTAP CLI + d05): `-check`, `-m 1`, `-speed slow`
  → zero detection change; a wider radius / longer timeout is irrelevant (a failed search costs ~4 s at the 30°
  default, 0.2 s at 5°); a deeper star database is unnecessary (d05 census: ≥124 catalog stars per Seestar FOV in the
  sparsest sky area, median ~490). What DOES move the needle: never escalate binning past 2 (the bin-4+`-s 200` rung
  detects ~0 of 25 stars even on bright frames), keep/boost the bin-1 rung (raise `-s`), and the stack-then-solve
  bootstrap (validated). Full numbers: the ⭐⭐ thin-stack entry's ▶ ROOT CAUSE MEASURED block.

- ~~**NEW (Builder 2026-07-23, slice (c) follow-on to the shipped sibling-hint fill-in v0.180.0) — a *second*
  solve pass that retries first-round failures with the sibling hint at the tight radius.**~~ — **✅ SHIPPED
  v0.411.0** (`solve/runner.build_sibling_retry_arglist` + `scanner.run_qc_and_solve`'s
  `retry_unsolved_with_sibling_hint`). Entry in [`SHIPPED.md`](SHIPPED.md).
- **NEW (Builder 2026-07-23, filed while fixing the ⭐ stale-cache bug) — decide whether a cleared/missing Stage-1
  cache should self-heal on the next scan.** *(Autonomy / friendliness; PRIORITY 2–3; size S; NEEDS a product call
  before building — that's why it's an idea, not a bug.)* The stale-cache fix (v0.174.2) makes every consumer fall
  back to `source_path` via `readable_frame_path`, so correctness is fully restored — a target with a cleared cache
  keeps working from source. But the cache is **never rebuilt**: `_cache_stale(cached_path, src)`
  (`seestack/io/ingest.py`) catches the `OSError` from stat-ing a *missing* cache file and returns `False` (not
  stale), and `ingest_files` only re-copies when `not prior.cached_path` (still truthy), so the frame runs off the
  (possibly slow NAS) source on every future scan. Rebuilding it on the next scan would restore the fast local path
  — but there's a **real tradeoff**: users often clear Stage-1 to *reclaim disk*, and auto-refilling it (Stage-1 is
  just a source copy) would silently undo that. **Options:** (a) treat a *missing* (not just size-mismatched) cache
  file as needing re-copy in `_cache_stale`/`ingest_files` — simplest, but re-fills after a deliberate clear; (b)
  have `clear_cache` null the `cached_path` column in the same transaction so the intent ("I cleared it") is
  explicit and only *then* does a scan re-copy — cleaner separation, but a small additive DB write on a path that
  currently touches no DB; (c) leave it as-is (source fallback only) and add a UI hint that clearing Stage-1 trades
  disk for slower reads. Pick one with the owner's disk-vs-speed preference in mind. Not blind-shipped because the
  "right" default is a product call. *(Found while routing the six read-sites through `readable_frame_path`.)*
- **NEW (Scout 2026-07-23) — "Try harder to locate these": a more-sensitive plate-solve re-pass for the
  *accepted-but-unsolved* subs, so a faint/sparse-star field's subs actually reach the stacker.** *(Autonomy +
  trust; PRIORITY 2; size M. Directly attacks the ROOT CAUSE half of the ⭐⭐ top owner bug — thin auto-stacks on
  faint fields — that is still open.)* **Why:** on a faint / sparse-star target ASTAP's normal ladder
  (`seestack/solve/astap.py::_SOLVE_LADDER` = downsample `None → 2 → 4`, `timeout_s=60`, `search_radius_deg=30`)
  fails on most subs; those subs stay **accepted-but-unsolved** and `run_stack` silently combines only
  accepted **AND** solved frames, so the "stack" is a handful of subs = the owner's single-frame speckle. The
  honest thin-stack + "N not located yet" surfacing already shipped (see the ⭐⭐ entry), and the existing nudge
  says *"Run Plate Solve"* — but re-running the **same** ladder that already failed won't help. **The missing
  lever is a genuinely more-sensitive re-solve**, applied **only to the unsolved-accepted subs** (identified by
  the already-present `Project.count_accepted_unsolved()` / `accept=1 ∧ wcs_json IS NULL`): e.g. add coarser
  downsample rungs and/or raise ASTAP's star-detection sensitivity, lengthen the timeout, and widen the search
  radius — a "faint-field" solve profile tried as a second chance. Distinct from `_solve_setup_problem`
  (frames.py:150), which only catches **ASTAP-missing / no-star-database** setup failures; the owner's case is
  ASTAP *present and working* but unable to lock a faint frame, so no setup hint fires. **Beginner bar / trust ✔:**
  one-click "Try harder to locate these N subs", plain-language, no knobs; a sub that solves on the retry then
  flows into the stack automatically, thickening it. **Guardrails / needs real data:** additive and opt-in (a new
  action + optional second ladder tier; **do not** change the default first-pass ladder or timeouts on the hot
  path). The exact ASTAP flags (sensitivity, extra `-z` rungs, radius) and where the sensitivity/speed knee sits
  **must be validated against the owner's real faint-field subs** before shipping — a blind sensitivity bump can
  cost solve time on every sub or mis-solve a sparse field, so tune with real data (extend the ⭐⭐ repro scaffold
  `scratchpad/repro_thin.py`). **Builder slices — (a) engine (S–M):** a `faint_field=True` variant of the solve
  ladder (extra rungs / higher sensitivity / longer timeout) in `astap.py`, unit-tested for arg assembly.
  **(b) webapp (S):** an endpoint that re-solves only the accepted-unsolved subs with the faint profile, wired to
  the existing solve job machinery. **(c) frontend (S):** a "Try harder to locate these N subs" button on the
  Target page, shown only when accepted-unsolved subs materially outnumber what stacked (reuse the existing
  `n_unsolved` the reject-summary already returns).
- **NEW (Scout 2026-07-21b) — auto-detect a master-dark ↔ light *exposure* mismatch and guide the fix, so a
  beginner reusing a dark library doesn't silently get a wrong calibration.** `CalibrationMasters.validate`
  (`seestack/calibrate/apply.py`) only checks the master's *shape* against the frames — it never compares the
  dark's exposure to the lights'. A dark master carries dark-current that scales with integration time, so
  subtracting a 30 s dark from 10 s subs over-subtracts (crushed shadows / dark halos), and a 10 s dark from
  30 s subs under-subtracts (residual amp-glow / hot-pixel trails) — a *wrong image*, with no warning. The app
  already has the machinery to fix it: `scale_dark_to_light` + `_effective_dark` rescale the dark to the
  light's exposure **when a master bias is also present** (`dark = bias + (dark − bias)·t_light/t_dark`), but
  it's **off by default** and silent, so a beginner never discovers it. **Idea:** at stack setup (and in the
  auto-calibration bind path), when the chosen dark's `dark_exposure_s` and the reference light's `exposure_s`
  are both known and differ by more than a small tolerance (say >10%), surface one plain-language line — *"Your
  master dark is 30 s but these subs are 10 s. Mismatched darks can over- or under-correct. Best: shoot darks
  at 10 s. Or add a master bias and turn on 'scale dark to exposure' and the app will match them for you."* —
  and, when a bias **is** available, offer a one-click enable of `scale_dark_to_light` (or auto-enable it on
  the fully-unattended auto-stack path, since with a bias present the scaling is strictly more correct than a
  mismatched raw subtraction). **Beginner bar ✔:** plain language, actionable, a sane default (silent when
  exposures match — the common case, byte-for-byte unchanged), and it prevents a real data-integrity foot-gun
  a non-expert can't diagnose. **Grounded / upgrade-safe:** exposures are already loaded (`dark_exposure_s`,
  `info.exposure_s`); the warning is read-only; the auto-enable is gated on a bias being present (never
  double-subtracts) and only fires in `auto`/unattended mode so no stored default flips on a running install.
  Split for the Builder: (a) a pure `dark_exposure_mismatch(dark_s, light_s, *, tol=0.1) -> str | None` helper
  + tests; (b) surface it as a stack-setup / result advisory (reuse the existing advisory/notes surface); (c)
  optionally auto-enable `scale_dark_to_light` on the unattended path when a bias is bound. _(M, split as
  above; PRIORITY 2 autonomy / P4 image-quality — prevents a silently-wrong calibration; builds on the shipped
  `scale_dark_to_light` infra, so low-risk.)_
  _(Builder note 2026-07-21 — **slices (b) and (c) are already shipped; only (a) remains and is pure dedup —
  low value, do not build blindly.** While scoping this item I traced both surfaces and both already handle the
  mismatch: **(b) interactive stack setup** — `frontend/src/routes/Stack.tsx` already computes `darkExpMismatch`
  (>25% via `expMismatch`) and renders the plain-language warning *"This dark was shot at Xs but your subs are
  Ys — a mismatched dark leaves residual thermal signal or over-subtracts…"*, **plus a one-click "Scale this
  dark to your subs' exposure" button** that sets `scale_dark_to_light` (shown when a bias is selected), and a
  proactive nudge to add a bias when none is. **(c) unattended auto-bind** — `webapp/calibration.py::
  auto_bind_master_paths` already, when a dark's gain/temp confidently match but its *exposure* is off, binds
  `dark_path + bias_path + scale_dark_to_light=True` (the exposure-scaling recovery) if a confident bias exists,
  and otherwise **leaves the dark off** rather than risk an over/under-subtraction — i.e. the unattended path
  already never applies a mismatched raw dark. So the only unbuilt piece is **(a)** — extracting the duplicated
  threshold (frontend `expMismatch` 25% + backend `_AUTO_BIND_EXP_MISMATCH_FRAC` 0.25) into one shared pure
  `dark_exposure_mismatch()` helper. That's a **maintainability dedup**, not a new user capability, and the two
  copies don't currently disagree — so it doesn't clear the churn bar on its own. Left filed; a future run
  already touching these files could fold the helper in, but the beginner-facing value here is **already
  delivered**. Recommend closing this item as largely-shipped rather than treating it as ready feature work.)_
  **▶ CLOSED — slice (a) is shipped too; verified in the code, not assumed (Builder 2026-08-18,
  `claude/relaxed-franklin-i98kvb`). Do not re-pick this.** The "pure helper" the note above left open exists and
  goes further than the spec: `CalibrationMasters.calibration_warnings(light_exposure_s, light_temp_c)`
  (`seestack/calibrate/apply.py`) returns the plain-language sentences for an exposure mismatch **and** a
  temperature mismatch, plus a separate one for the case where exposure-scaling was asked for but a wrong-shaped
  bias silenced it. It is carried on `StackResult.calibration_warnings` (`stacker.py:1196`), stamped per run, and
  rendered on the **Jobs** card (`calibrationMismatchNote`), **History**, the **Stack** form and the **Editor**.
  Nothing in this item is open.
- **NEW IMPROVEMENT (Scout 2026-07-21) — when auto-reject resolves to min/max, also auto-scale the *number*
  of extremes it drops (`min_max_reject_count` k) to the frame count, so a long multi-night session with
  several trails crossing the same pixel is actually cleaned.** v0.143.0's `auto_reject` picks the *method*
  (min/max below the κ-effective frame count, κ-σ at/above it) but always leaves `min_max_reject_count=1` —
  the classic single min/max drop. That's correct for a *lone* trail, but the §1 owner routinely stacks
  **thousands of subs across many nights**, where 2–3 satellite/plane trails can cross the *same* output
  pixel over a session; a k=1 drop removes only the single brightest and leaves the rest as a residual
  streak. The engine already fully supports k>1 — `MinMaxRejectAccumulator(reject_count=k)` keeps k sorted
  min/max planes and degrades gracefully (`count≥2k+1` full k-trim → single drop → plain mean; verified
  clean in this run's audit) and the peak-memory guard already charges `2+2k` planes
  (`_min_max_reject_arrays`). **Idea:** inside `_resolve_auto_reject`, when it selects min/max, also set k
  from n on a gentle, conservative curve — e.g. `k=1` up to a few hundred frames, `k=2` into the low
  thousands, capped small (≤3) so a modest stack never over-trims (dropping 2k of n samples must stay a
  small fraction; keep k ≤ ~n/8). Purely a refinement of the already-opt-in `auto_reject` path — **off by
  default**, no effect unless the user turned auto-reject on and it resolved to min/max, so no default flip
  and byte-for-byte unchanged for everyone else. **Well-grounded / low-risk:** one small change to the
  existing `_resolve_auto_reject` (which already returns a `replace(options, …)` copy), the accumulator +
  memory guard already handle any k, and the resolved k is persisted in the run record like the method is.
  **Guardrails:** the k-vs-n curve must be conservative (never trim a meaningful fraction of a small stack —
  cap k so `2k ≤ n/4`); validate on a real long session that a genuine multi-trail pixel is cleaned while a
  clean stack is unchanged. Tests: extend `tests/test_stack_pipeline.py` — `_resolve_auto_reject` returns
  k=1 for small n and a capped k>1 for large n; a synthetic stack with two planted trails at one pixel and
  a high frame count clips both under the auto-scaled k (fail-before with k=1 one residual survives).
  _(S code / S–M validation; PRIORITY 2 autonomy + P4 image quality — extends the shipped auto_reject so the
  "just works" method-pick also gets the *strength* right for the owner's high-frame-count workflow.)_
  _(Builder note 2026-07-21 — **premise is self-defeating; do NOT build as specified.** `auto_reject` resolves
  to min/max only **below** `_auto_kappa_min_frames(κ)` — n<11 at the default κ=3 (`stacker.py::_resolve_auto_reject`);
  a "thousands of subs across many nights" session is n≫11, so it resolves to **κ-σ**, not min/max, and never
  reaches the k it wants to scale. Within the min/max regime (n<11) the idea's own conservative cap (`2k ≤ n/4`,
  i.e. `k ≤ n/8`) forces `k=1` for every n<11 (n/8 < 1.375), so the auto-scale curve would be a **no-op** exactly
  where it fires. To actually clean multi-trail pixels on a huge stack you'd need k>1 under **κ-σ** (a different
  change — κ-σ ignores min_max_reject_count entirely), or to raise the min/max→κ-σ crossover, both of which change
  the shipped v0.143.0 behaviour and need real-data justification. Left filed as a caution, not ready work.)_
- **Pre-flight "this batch looks like two targets" guard — catch mixed pointings *before* the
  walk-away stack wastes itself.** (S–M, autonomy/friendliness/trust) *(Scout-filed 2026-07-09, traced.)*
  **Interactive slice SHIPPED v0.101.0 (Target page) + v0.102.0 (Stack form):** the pre-flight detection +
  amber warning on both surfaces a user reaches before stacking. A new pure `detectMixedPointings(frames)`
  helper (`components/target/mixedPointings.ts`, mirroring `countQcUncheckable`/`countNewSubsSinceStack`)
  single-linkage-clusters the accepted+solved subs' RA/Dec at a 3° link distance (wrap/pole-safe via unit
  vectors; a contiguous mosaic stays one cluster, two well-separated targets split), and both the Target page
  (v0.101.0) and the Stack form itself (v0.102.0, right next to the Stack button) show an orange "This batch
  looks like N different targets" callout — with the majority/minority counts + their separation + guidance
  to reject the odd frames — *before* the user clicks Process/Stack. Frontend-only, read-only, additive (no
  backend/schema/default change). **Unattended slice SHIPPED v0.109.16** (Builder 2026-07-11; see Shipped): a new
  off-by-default `mixed_pointing_guard` setting makes the Process-target and watcher auto-stack chains cluster
  the pointings (Python mirror `seestack/stack/pointings.py::detect_mixed_pointings`) and **refuse-with-guidance**
  — skip the walk-away stack with a plain-language reason — on a clearly-bimodal batch, instead of burning the run
  combining one pointing. Chose refuse-with-guidance over auto-stacking just the majority to avoid touching the
  engine hot path (`run_stack` reads frames straight from the DB); the "auto-stack just the majority pointing"
  variant would need an engine frame-filter param and is left as a possible future refinement if refuse-only
  proves too blunt on real data. Off by default (§9). Original write-up kept below for provenance.
  _(~~Builder follow-up idea, spotted auditing the shipped v0.101–0.102 detection 2026-07-09: the warning
  currently only **tells** the user to "open the Frames table and reject the odd frames"…~~ —
  **shipped v0.103.0** (see Shipped). `detectMixedPointings` now also returns `minorityIds` — the ids of
  every accepted+solved sub outside the largest pointing (exactly what the stacker would silently drop) —
  and both surfaces that show the amber warning (Target page + Stack form) now carry a one-click **"Reject
  the N odd-target frames"** button that rejects just those subs via the existing `bulk` reject endpoint
  (`action:"reject"`, `reason:"user"`), leaving a clean single-target batch. Undoable like the auto-grade
  "Drop N" hint (the warning swaps to a teal "Rejected N — Undo — re-accept" confirmation), so a stray good
  frame is one click back; any lone strays outside the majority are rejected too (they'd be dropped anyway).
  Frontend-only, additive, no backend/schema/default change; the pure helper + button are unit-tested.)_
  The still-open *preventive* complement to the now-**shipped** post-hoc pair (v0.100.0: "Persist & surface
  honest per-run frame accounting" + "Proactively diagnose a large align-failure fraction", both in Shipped).
  Root cause (verified): in `stacker.py::_pass` a frame whose reprojected footprint doesn't intersect the
  reference canvas returns `None` from `align_one` and is dropped — v0.100.0 now *counts* those (NALIGNFL)
  and the History Info panel flags a large align-failure fraction after the fact, which closes the
  *visibility* gap. **What's still open is prevention:** for the "drop two targets in one batch" mistake, the
  unattended auto-stack still picks one pointing as reference and burns the whole walk-away run producing a
  half-complete stack the user only learns about *afterwards* from the amber count. Close the loop by acting
  **pre-stack**: in the Process / auto-stack chain, cluster the frames' already-stored
  `ra_center_deg`/`dec_center_deg`; if they split into two+ well-separated pointings that aren't a contiguous
  mosaic (gap ≫ the ~1° Seestar FoV between clusters), auto-stack just the majority pointing (flagging the
  rest) or refuse-with-guidance — instead of silently combining half the data. Purely local (RA/Dec are in
  the project DB), additive, off-nothing (only fires on a clearly-bimodal set), and testable on a synthetic
  two-pointing frame set. Distinct from the shipped diagnosis because it acts *before* the stack (no wasted
  run) and keys on the sky coordinates we already have, not on the post-hoc align-failure count. **Smallest
  safe first slice:** just the detection + an amber "your batch looks like 2 targets" pre-stack warning,
  leaving the actual split/auto-select for a follow-up.
- **NEW IDEA (Builder 2026-09-04, the generalisation of the v0.345.8 merge) — sweep the app for the other
  pairs of superlatives that can resolve to the same thing.** *(Pillar: friendliness / trust — PRIORITY 3;
  size XS per site once found; confidence: two instances fixed, the rest unchecked.)* v0.345.8 merged two
  such pairs — "biggest project" vs "most-imaged target", and "longest night" vs "sharpest night" — after a
  dogfood pass showed each printing one answer twice, side by side. **The identifying test:** two adjacent
  surfaces that each *rank* the same population by a different key, where the keys are correlated on this
  owner's data (fixed-length Seestar subs make exposure ≈ count; a short season's best night tends to be
  best at everything). **Unchecked candidates:** the Dashboard's "Your best night" card against the year
  page's sharpest night (different pages, so much weaker — probably leave it); `/best`'s ranking against the
  Library tile's "latest picture"; the Target page's "sharpest sub" against its "reference sub"; and the
  session-recap standouts. **Care:** the fix is a *merge that keeps both figures*, never a drop — and a pair
  that usually differs should stay two cards, because merging a coincidence would be as confusing as
  repeating one.

- **NEW IDEA (Builder 2026-09-04, the generalisation of the v0.345.3 export-panel fix) — sweep the app for
  the other trailing "what these buttons do" paragraphs, and check each against the per-control copy above
  it.** *(Pillar: friendliness — PRIORITY 3; size XS per site once found. Confidence: one confirmed instance,
  the rest unenumerated.)* The editor's Export panel ended with a four-sentence block recapping the three
  buttons four rows above it, of which the first sentence duplicated the line directly under the Export
  button. It survived every code-level read because each sentence is defensible alone — only the **rendered
  page** shows five grey paragraphs in a row, which is why `scripts/agent-dogfood.sh` found it and audits had
  not.
  **The identifying test, which is cheap and does not need a browser once you know the shape:** a
  `<Text size="xs" c="dimmed">` that is the *last* child of a panel and names two or more of the panel's own
  controls in quotes. **Named starting points, none checked:** the Stack form's foot, the Save/share menu's
  description block, the Calibration page's master-picker explainers, and the Storage page's cleanup copy.
  **Care — this is the owner's "nothing may be removed" constraint, so do it the way v0.345.3 did:** go
  clause by clause, move each sentence under the control it describes (the idiom several panels already use),
  and re-home any fact the paragraph carried that the per-control copy did not, rather than deleting the
  block wholesale. A paragraph whose every clause is genuinely new information is *not* a hit — leave it.

  **⚪ ALL FOUR NAMED STARTING POINTS ARE CLEAN — checked in the code, recorded so nobody re-walks them
  (Builder 2026-09-04).** The **Stack form's foot** ends in the sizing line and its conditional advisories,
  each of which sits with the control it is about and carries a number nothing else states. The
  **Save/share menu** (`Target.tsx` / `History.tsx`) has no trailing block at all — every item carries its
  own one-line `MENU_HINT` under its own label, which is the idiom the export-panel fix moved *towards*. The
  **Calibration page's** picker explainer is one sentence about the *source-folder input* beside it ("point
  at a server-side folder of raw dark/flat FITS…"), not a recap of the buttons. The **Storage page's** two
  closing paragraphs both carry facts stated nowhere else — what a cache is and that pruning is permanent,
  and the standing guarantee that nothing on the page touches `incoming/` (§10), which is the one paragraph
  on that screen that must never be trimmed for tidiness. **So the confirmed instance count stands at one
  (v0.345.3), and the remaining candidates are unenumerated rather than known.** If the sweep is ever
  reopened, look at panels *added since* v0.345.3 rather than re-reading these four.

- **NEW IDEA (Builder 2026-09-03, measured while sweeping the display-space statistics for A1's blindness) —
  Levels' "From your image" button silently leaves the black point at 0, and nothing says why.** *(Pillar:
  friendliness — PRIORITY 3; size XS; **copy, not arithmetic** — do NOT change the number, and read the
  swept-and-closed entry under "Image quality" before touching this.)* Measured on real `autostretch`
  output: the image entering Levels has **1.08 % of its pixels at exactly 0** (the STF's shadow clip), so
  `suggest_levels_points`' 1st percentile lands inside that spike and the button returns
  `black = 0.000, white = 0.892, gamma = 1.079`. That black **is the honest answer** — the function's job is
  "put black where 1 % of pixels fall below", and 1.08 % are already there, so the picture has the shadow
  clipping the button was asked for; excluding the zeros would clip roughly *twice* the intended share on the
  on-by-default path. But from the beginner's seat it reads as a half-broken button: two sliders move, one
  doesn't, and nothing accounts for it. **Shape:** one line beside the suggestion — *"your blacks are already
  where they should be, so only the white point moved"* — on the branch where the suggested black equals the
  current one. Not a banner; the other "From your image" buttons already name what they solved for
  (`gamma_target`, `target_bg`), so this is the same idiom rather than a new element. **Grep first:** the
  Levels control's existing suggestion copy in the editor, and check whether the button already renders
  anything on a no-change suggestion.

  **⚪ CLOSED AS MOSTLY-ALREADY-BUILT — CHECKED, NOT ASSUMED (Builder 2026-09-03, the same day it was filed).
  Do not build this as written.** The entry's own "grep first" was the whole answer: `OpParamPanel` already
  handles the no-change suggestion **generically**, for every op, not just Levels. When a param already sits
  at its suggested value (`matchesSuggestion`, which honours the field's own `step`) the button is
  **disabled**, is prefixed with a **✓**, and carries the tooltip *"Already set to the value measured from
  your data"*. So the premise — *"two sliders move, one doesn't, and nothing accounts for it"* — does not
  hold on the shipped UI: the black button never invited the click, and it already says why.
  **The measurement in the entry is still worth keeping** (1.08 % of an `autostretch` output's pixels sit at
  exactly 0, so the 1st percentile lands inside the STF's shadow clip and `black = 0` is the honest answer),
  and so is its warning that excluding those zeros would clip roughly *twice* the intended share on the
  on-by-default path — that half stands as a "do not fix the number" note. What is left is only the gap
  between the generic *"already set from your data"* and a Levels-specific *"because your blacks are already
  clipped there"*: one extra clause in a tooltip on a **disabled** button. That is below the bar, and adding
  it would be the already-shipped-item-re-filed churn AGENTS.md §1 warns about. **If a future run wants the
  specific wording anyway**, it is a conditional tooltip string on `OpParamPanel`'s existing `atSuggestion`
  branch — not a new element, and not a new branch.

- **NEW IDEA (Builder 2026-09-02, the other direction of the v0.326.8 "Edited from …" line) — the *original*
  stack says nothing about the edit made from it, so the pointer only works if you happen to look at the right
  row.** *(Pillar: understand — PRIORITY 3; size XS; **check the overlap with `unexported_edit` first, it may
  already be enough**.)* An export's card now names the run it came from and jumps to it. The source run's own
  card says nothing back — no "an edited version of this exists" — so a beginner scrolling History still meets
  the linear stack first and has no reason to think there is a finished picture two cards along. **The datum is
  already there:** `derived_from` is on every export's `options`, so the reverse index is one pass over the
  same list the page already holds (`derivedFromNote`'s neighbour, not a new query). **Why it is filed rather
  than built:** the source card is already the busiest one in the app (badges, two dates, notes, the noise
  delta), and `unexported_edit` already occupies exactly this slot for the *unfinished* case — so the honest
  question is whether a second edit-related label earns its place, or whether the right shape is to extend the
  existing badge's vocabulary rather than add a line. Decide that before writing code; if in doubt, leave it —
  one direction of a link is often enough.

> **⚠️ COLLISION — this was built twice in the same hour, and the version below (v0.323.0, branch
> `claude/zen-mccarthy-2rptmf`) is the one that ships.** *(Builder 2026-09-02, branch
> `claude/zen-mccarthy-v56oj1` — mine is dropped rather than re-litigated; theirs landed on `main` first.)*
> The two were indistinguishable in shape — same `hasAnythingToShow` name, same definition *against*
> `buildSlides`, same `["gallery"]` key shared with the show — which is itself evidence the entry's spec was
> unambiguous. **Theirs is strictly better on the one point the entry left open**, and it is worth carrying
> forward as the general rule: a **failed** query is *unknown*, not *empty*, so their gate keeps the button
> when the gallery errors. Mine treated a rejected query as "nothing to show" and would have hidden a working
> slideshow from anyone briefly offline — the exact failure mode the entry's own trap warns about, arrived at
> from the other direction. Nothing of mine is re-applied on top: their tests are a superset of mine (8 to my
> 6, including that error case).
> **What it cost, and the lesson:** I claimed nothing in the backlog before starting — the item was an XS
> dogfood finding and claiming felt like overhead. It is not: the claim is the only signal the other Builder
> could have seen, and this is now the **tenth** such collision. Claim even the XS ones, in the run's first
> commit, and push it immediately.

- **NEW IDEA (Builder 2026-09-01, the half the v0.322.5 label fix deliberately did not build) — tick the
  first-image solve step on frames that **actually got solved**, not only on ASTAP being installed.**
  *(Pillar: friendliness — PRIORITY 3; size S, but **read the cost note**; the label fix already removed the
  untruth, so this is polish, not a correction.)* The honest signal for *"your subs have sky coordinates"* is a
  count of frames with a WCS, and today nothing carries one: `library.campaign_stats` aggregates only the
  registry columns (`n_frames`, `n_frames_accepted`, `total_exposure_s`), and `wcs_json` lives in each
  **per-target** `project.sqlite`. **The cost is the reason this is filed rather than built:** `/api/stats` is
  the Dashboard's hot path, and its existing per-project work (`_rollup_stacks`) opens only targets that *have*
  stacks — a solved count would open **every** target, on every uncached stats call. **If it is built:** put
  the count behind the same `stats_cache` signature, and add it as an additive optional field that reads as
  "unknown" (never as zero) when an older backend omits it — the step must not un-tick itself on an upgrade.
  **Care:** don't let it *replace* the ASTAP check. Someone with pre-solved frames and no ASTAP still needs the
  setup before their own subs will solve, so the tick wants to stay the setup's, with the frame count as an
  extra reassurance line at most.

- **🟡 HALF (a) IS ALREADY BUILT — don't re-pick it (Builder 2026-09-02, checked in the code while sizing it).**
  The **"Save this map"** button exists on `routes/Sky.tsx` (top-right of the My-map panel, `href={api.myMapUrl()}`
  with a dated `download={myMapFilename()}` → `astrostack-my-map-YYYY-MM-DD.png`), exactly as this entry
  specifies, with its own exported filename helper and tests. **Only half (b) — the Dashboard preview card — is
  open**, and it is the half whose own Care note collides with the standing IA priority ("don't append one more
  always-on card"), so it needs a *grouping* to live inside rather than a slot at the top. Sized and left.

  *(Original spec follows.)* **NEW IDEA (Builder 2026-08-29, spotted finishing the v0.292.0 "My map") — let the
  owner *save* their
  universe map, and put it where they'd think to look for it.** *(Pillar: enjoy + share — PRIORITY 3.
  Size: S. Confidence: high — the picture already exists at a stable URL.)* "My map" is a pride object:
  the one image that says "here's everywhere I've pointed my scope this year". Right now it only exists
  inside the Sky page. Two cheap additions: (a) a **"Save this map"** button beside the mode switch —
  the PNG is already served whole at `/api/sky/my-map.png`, so this is a download link with a nice
  filename (`astrostack_my_sky_<date>.png`), not new rendering; and (b) a small **preview card on the
  Dashboard** ("Where you've been · N pictures") that links into the Sky page's My-map mode, so a
  beginner meets it instead of having to find a third segmented-control option. Careful with (b): the
  standing IA item says the Dashboard is already busy — put it *inside* an existing grouping rather than
  appending one more always-on card, and only show it once there are, say, three or more mapped pictures
  (below that the map is mostly empty sky and reads as a bug rather than a milestone).

- **NEW IDEA (Builder 2026-08-27, spotted while fixing the two "dataclass tolerates, Pydantic doesn't" list
  endpoints in v0.277.5) — a tiny test that pins the *rule* rather than the four instances: every list endpoint
  that reads a per-item file off disk degrades per item.** *(Pillar: trust / maintainability — PRIORITY 3.
  Size: S.)* v0.277.5 fixed the four boundaries that existed; nothing stops the fifth being written without a
  guard. The cheap version is not a clever meta-test but a documented convention plus one shared helper —
  e.g. a `degrade_per_item(items, build, what)` used by `/api/videos`, `/api/gallery` and the `stats.py`
  roll-ups alike, so the guard comes for free with the helper and a reviewer can see at a glance which loops
  have it. **Grep first:** the four fixed sites and the existing `stats.py` roll-ups are the population; if a
  shared helper would only ever have five callers, a comment in the house-style notes may be the better
  answer, and this idea should be closed rather than built. Explicitly *not* worth a framework.

- **NEW IDEA (Builder 2026-08-18, the pattern behind both v0.266.1 and the hints added in v0.267.0) — a Tooltip is
  invisible on the device the owner actually reads this app on, so every explanation that exists *only* as a
  tooltip is, on a phone, not written at all.** *(Friendliness — PRIORITY 3; size M; **measure first**.)* A phone
  has no hover: Mantine's `Tooltip` opens on hover or focus, and a tap on a button runs the button. v0.266.1 fixed
  the extreme case (the label itself was hidden behind a tooltip); v0.267.0's menu items each show their old
  tooltip sentence as a visible one-line hint, which is the same fix applied to a different surface — and both
  times the wording already existed and was simply unreachable. **Slice:** count the `<Tooltip label="…">` uses
  across the beginner-critical routes (Target, History, Stack, Editor, Dashboard) and split them into (a) the
  tooltip *is* the only explanation — promote it to visible text or a hint line; (b) it repeats what the control
  already says — leave it. **Care:** don't turn every tooltip into visible prose, or the pages get *taller*, which
  is the complaint this whole IA effort exists to fix; prefer the v0.267.0 shape, where the words become visible
  because the control moved somewhere that has room for them. Worth doing as a measured pass, not a sweep.
  **▶ FIRST SLICE SHIPPED — v0.270.0** (Builder 2026-08-19, branch `claude/relaxed-franklin-m1crsw`), taken as the
  entry asks: one surface, measured, not a sweep. **The frames table's column headings** were the clearest case in
  the app — `FWHM`, `Ecc.`, `Sky` and `Transp.` are four of the table's five numeric columns, each already carrying
  a good plain-language sentence, and each carrying it **only** as a `Tooltip`. A phone has no hover, and a tap on
  one of those headings *sorts the table*, so on the device the owner reads this app on there was no way at all to
  find out what they mean — on the page a beginner spends the most time on.
  **The shape is v0.267.0's, not a sweep's:** the tooltips are untouched for anyone with a mouse, and a
  `FrameColumnGuide` disclosure — *"What do these numbers mean? →"* — spells the same sentences out as text.
  **Same words, one array:** the columns moved out of `Target.tsx` into `components/target/frameColumns.ts`
  (`FRAME_COLUMNS`), which now feeds both the header tooltips and the guide, so the two cannot drift and a column
  added later gets an entry in both surfaces or in neither — pinned by a test that walks `FRAME_COLUMNS` rather
  than a hand-written list.
  **Measured, as the entry's "don't make the pages taller" caution demands:** the Target page at 420 px goes
  **2 939 px → 2 953 px (+14 px, +0.5 %)** closed, and **1 966 px → 1 966 px on desktop — no cost at all** (the
  guide sits in the left column beside a taller right one). Opening it adds 269 px, and only when asked. The body
  is mounted **only while open** (it is static text with nothing to refetch), which also keeps words like
  "trailed" off a page that is careful about when it says them — an existing `Target.test.tsx` assertion caught
  exactly that and passes unchanged.
  **Tests (+6):** `FrameColumnGuide.test.tsx` (**new, +5** — nothing on the page until asked for, every hinted
  column explained in one tap driven off `FRAME_COLUMNS` itself, the wording being the tooltips' own, open/close
  with its `aria-expanded`, and the toggle hugging its text rather than stretching) and `Target.test.tsx` (+1 —
  the real page's hints are readable without hover). The existing "gives the metric column headers plain-language
  hint tooltips" test passes unchanged, so the hover path was added to, not traded away.
  **▶ SECOND SLICE SHIPPED — v0.374.11**, and it turned out to be a **bug**, not only an unreachable
  explanation (Builder 2026-09-07, branch `claude/sweet-babbage-mg8isx`). Rather than pick one of the four
  remaining routes, the measurement pointed at the one component all of them share: `HintLabel`
  (`components/StackOptionControl.tsx`) is the *only* explanation surface for a descriptor-driven option, and
  it is used by the **Stack form**, **Settings**, the **editor's op parameter panel** (via `OpParamPanel`) and
  the editor's print-size control — i.e. every engine parameter the app offers, on the priority-1 surface
  included. Its `field.help` sentence lived on a hover `Tooltip` around a bare 14 px `<svg>`.
  **The bug, verified by probe before the fix:** `HintLabel` is passed as a `Switch`/`Select`/`NumberInput`'s
  `label`, which Mantine renders **inside a `<label>`** — so clicking the info icon activated the control.
  Driving the pre-change component directly, one click on the icon of a boolean option fired
  `onChange(true)`. On a phone that click is the *only* gesture available for "what does this do?", so the one
  way a beginner could ask changed their stacking option instead, and the answer never appeared.
  **Fix:** the icon is now a real control — `UnstyledButton component="span" role="button" tabIndex={0}` with
  a controlled tooltip opened by tap, hover *or* keyboard focus, and `preventDefault()` on the click so the
  surrounding `<label>` no longer forwards it. **A `<span>` and not a `<button>` is load-bearing:** a
  `<button>` inside that `<label>` is a *labelable* element, so the field's own label would name two controls
  at once — which broke seven `Settings.test.tsx` queries the moment it was tried, and would read the same way
  to a screen reader. Its `aria-label` is deliberately generic (*"What does this do?"*) for the same reason;
  the field's own label is announced immediately before it.
  **No page gets taller** — same 14 px icon, `lineHeight: 0`, no padding, no new visible prose — which is what
  the entry's own caution asks for, and hover is byte-for-byte what it was for anyone with a mouse. Keyboard
  users gain the hint for the first time. **Tests (+7, four fail-before):** `StackOptionControl.test.tsx` —
  the tap shows the hint *and* leaves the setting alone, tap-again dismisses, blur dismisses (there is no
  outside-click handler; losing focus is the dismissal, which is what a touch elsewhere does), hover and focus
  both open it, Enter and Space open it, a field with no help renders nothing at all, and the switch still
  toggles when you actually click the switch.

  **▶ THIRD SLICE SHIPPED — v0.402.0, the editor's preview toolbar** (Builder 2026-09-09, branch
  `claude/sweet-babbage-x2ai9f`). The route with by far the most hand-written tooltips is the editor (24, against
  Gallery's 9 and Target's 7), and the ones that matter are the eight-button row **directly under the picture** —
  the row that decides what the preview is showing. Four of them carried a good sentence each and carried it only
  as a `Tooltip`: `Coverage`, `Star mask`, `Drag to crop` and `Split`. A phone has no hover and a tap on one of
  those buttons *runs* it, so the one gesture available spends the question on the answer — and the answers are
  not guessable from what appears (a yellow-to-dark-blue heatmap, a white-on-black mask, a divider you are
  supposed to drag). Three more (`Compare`, `Refresh`, `Zoom`) had no explanation anywhere, of which `Compare` is
  the one that needed it: it is the twin of `Split` and its label never says what it compares *against*.
  **The shape is v0.270.0's `FrameColumnGuide`, deliberately** — a `PreviewToolGuide` disclosure
  (*"What do these buttons do? →"*) under the row, built from the same `PREVIEW_TOOLS` array the tooltips now take
  their labels from, so the two cannot drift and a tool added later gets an entry in both surfaces or in neither.
  `visiblePreviewTools({isMosaic, cropDrag})` takes the same two booleans the row itself renders from, so the guide
  can never explain a button that is not on the screen — the mosaic-only coverage heatmap and the crop handles are
  absent on an ordinary single-field stack, where naming them would send a beginner hunting for controls that do
  not exist. **Measured, as the entry's "don't make the pages taller" caution demands** (`agent-dogfood.sh
  --build --mosaic --editor`): the editor at 420 px goes **3,047 px → 3,072 px (+25 px, +0.8 %)** closed, desktop
  1,984 px; nothing overflowing, no console errors, and the mosaic trim still 7.9 %. The body is mounted only
  while open. Tooltips are byte-for-byte what they were for anyone with a mouse; nothing was removed.
  **Tests (+12):** `previewTools.test.ts` (+5 — the two conditional tools appear only under their own condition,
  the row order, every entry carrying a real sentence, and each entry keyed by its own name) and
  `PreviewToolGuide.test.tsx` (+5 — one line until asked for, every offered tool explained in one tap driven off
  the array itself, never explaining an absent button, open/close with its `aria-expanded`, and nothing at all for
  an empty row), plus 2 in `Editor.test.tsx` on the real page (the split hint readable without hover; the
  mosaic-only coverage hint absent on a single field) — both fail before.

  **▶ FOURTH SLICE SHIPPED — v0.402.1, and it is a *bug* rather than an unreachable explanation, exactly as the
  second slice was** (Builder 2026-09-09, same branch). v0.374.11 fixed the case where the hint icon sat inside a
  control's `<label>` and the tap activated the control. **The same defect exists one level up, wherever a
  `<Tooltip>` is wrapped around the control itself** — there the tap does not merely leak to the control, it *is*
  the control, and no icon exists to aim at. Enumerated rather than guessed at: exactly **five** sites in the
  whole frontend wrap a `Tooltip` around a `Switch`/`SegmentedControl`/input, and all five are now fixed —
  - the **editor's `Auto-crop edges` switch**, whose sentence is the only place the app says the library-wide
    default lives in Settings → Automation, and whose tap overrides that default for the picture in front of you;
  - the **Jobs page's `Notify me when done` switch**, where the tap also fires the browser's permission prompt —
    so reading what the control does was the same gesture as agreeing to it;
  - the **Gallery's three filters** (calibration, combine method, and the sort whose hint is the only place that
    page explains its σ) — on a segmented control the tap picks a segment, so asking the question re-sorted the
    page and never answered it.
  **The fix is the app's own affordance, not a new one.** `HintIcon` is the icon half of `HintLabel`, lifted into
  `components/HintIcon.tsx` (`HintLabel` now renders it, byte-for-byte the same behaviour — its own tests are
  untouched and pass). Beside a control rather than inside its `<label>`, it leaves the control's accessible name
  exactly as it was, so nothing that looks a switch up by its own name — a screen reader, or a test — has to know
  the hint exists. Hover and keyboard focus still open it; the hover target narrows from the control to the icon,
  which is the same trade v0.374.11 made. No page gets taller (14 px icon, `lineHeight: 0`, no padding).
  **Tests (+10):** `HintIcon.test.tsx` (+6 — tap opens, second tap and blur dismiss, hover and focus still open
  it, Enter/Space, it never operates the control beside it, and the control's own name is unchanged) and one
  fail-before regression at each of the three routes, each asserting the words appear *and* that the control did
  not move: `Editor.test.tsx` (the switch stays checked and `autoProcess` still gets `undefined`),
  `Jobs.test.tsx` (`requestPermission` not called), `Gallery.test.tsx` (still sorted by Newest).

  **▶ FIFTH SLICE SHIPPED — v0.413.0, the *other* half of the class: an anchor with no behaviour at all**
  (Builder 2026-09-10, branch `claude/sweet-babbage-w1qz43`). The four slices above are all about a tooltip on a
  **control** — where the tap does the wrong thing. **Enumerated rather than guessed at:** of the app's 105
  `<Tooltip>`s, **53 hang off an anchor that is not a control at all** — a `Badge`, a `Text`, a `Box` — where the
  tap does not do the wrong thing, it does *nothing*, and the sentence simply is not written on a phone.
  Mantine ships `events={{ hover: true, focus: false, touch: false }}`, so these open on `mouseenter` and on
  nothing else; **turning its `touch` on is not the fix** — floating-ui opens on `pointerenter` and closes again
  on the `pointerleave` a lifted finger fires, so the answer flashes and goes. New
  `components/HintAnchor.tsx` is the app's own controlled-tooltip affordance (`HintIcon`, v0.402.1) applied to
  an anchor with nothing of its own to collide with: it **clones the child** rather than wrapping it, so no row
  moves and no page gets taller, and it keeps the site's own handlers and role if it set any.
  **This slice is the verdict chips on a stack card** — the words a beginner meets in History and the Gallery
  whose whole meaning is the tooltip: `NoiseReadout` ("Noise 0.021"), `NoiseDelta`, `CleanestBadge`,
  `FocusChip` ×2 ("✨ sharpest yet" / "softer than usual"), `CalibrationBadge`, `HazyNightBadge`,
  `PanelSeamsBadge`, `RejectionBadge`, `FrameCountBadge`'s thin-stack warning, and History's own
  *"what's this?"* under Noise trend — which is the sharpest case of all, since those two words are an
  *invitation* and a hover-only reply to them is a dead link. Hover is byte-for-byte what it was; keyboard users
  gain the hints for the first time. **Tests (+9):** `HintAnchor.test.tsx` (+6 — tap opens, second tap and blur
  dismiss, hover still opens, Enter/Space, the anchor's own `onClick`/`role` survive, and no wrapper element is
  inserted) plus one fail-before regression each in `NoiseBadge.test.tsx`, `HazyNightBadge.test.tsx` and
  `History.test.tsx`.
  **▶ SIXTH SLICE SHIPPED — v0.413.1, the planning surfaces, which are the most phone-critical in the app**
  (same run, same branch). You read *Tonight* standing next to the scope, in the dark, on a phone — it is the
  one page whose *whole purpose* is answered away from a desk — and every verdict on it explained itself on
  hover and nowhere else: the score badge ("Higher = better placed tonight"), and the four per-target chips
  (`readyHint`, `difficultyRowBadge`, `framingRowBadge`, `recentreNudgeRowBadge`), each of which is a
  two-or-three-word verdict whose *reason* is the tooltip. Nine sites: `routes/Tonight.tsx` ×5,
  `SuggestTargetsCard` ×2 (the Dashboard's copy of the same two chips), `ContinueTonightCard`'s re-centre nudge,
  and `NextSessionCard`'s window line — whose hint is the honest **UTC** anchor behind the local wall-clock it
  prints, i.e. the same anchor its own `.ics` carries. Four now-wrong "shown on hover" comments in
  `components/nextSession.ts` refreshed with it. **Tests (+2, both fail before):** `Tonight.test.tsx` (a tap on
  "Needs mosaic" produces the sentence) and `NextSessionCard.test.tsx` (a tap on the window line produces its
  UTC).
  **▶ SEVENTH SLICE SHIPPED — v0.413.2, the two priority-1/2 pages, and it carries a *bug* like the second and
  fourth slices did** (same run, same branch). The Target page's header badges — `N integration`, **`N streaked`**
  and **`N trailed`** — each sit *beside a bulk-reject button*, and what a streak is (and that Auto outlier removal
  takes the trail out while **keeping** the frame) lived only in the badge's tooltip: on a phone the destructive
  button was the more reachable of the two. **The bug is in the editor:** `SlowPreviewChip` is a warning rendered
  *inside* the Add menu's `Menu.Item`, so the one gesture a touch user had for *"what does 'slower preview' mean?"*
  **added the very op it warns about** — the v0.402.1 defect one level out, and the same shape again in `OpList`'s
  three row chips (the edited dot, the heavy badge, the stage-conflict line), where the tap selected the op. That
  needed a new opt-in `stopPropagation` on `HintAnchor`, deliberately **off** by default: swallowing a click a page
  expects to receive is the worse failure of the two. Eight sites (`Target.tsx` ×3, `Editor.tsx` ×2, `OpList.tsx`
  ×3). **Left alone on purpose, with the reason:** the frames table's column headings (the tap *sorts*, which is
  the primary action, and v0.270.0 already gave those sentences a reachable home in `FrameColumnGuide`) and the
  per-frame `Rejected — …` badge (the tooltip repeats the badge's own text — category (b) of this entry).
  **Tests (+3, two fail before):** `HintAnchor.test.tsx` (the flag swallows the container's click and its absence
  does not), `Target.test.tsx` (a tap on "2 streaked" produces the sentence) and `Editor.test.tsx` (a tap on
  "slower preview" produces the sentence **and leaves the op list empty**).
  **Still open after all three:** the ~22 remaining non-control anchors — `NightsCard` ×3, `BestMonthsStrip`,
  `MosaicMapCard`, `BestPictures`/`Gallery`/`Calibration`/`LifeList`, and `ImageLightbox`'s bare-icon anchors.
  `HintAnchor` makes each a one-line swap; take them a coherent surface at a time, not as a sweep.

  **▶ EIGHTH SLICE SHIPPED — v0.414.0: the "still open" list above, and the guard that stops a ninth**
  (Builder 2026-09-10, branch `claude/sweet-babbage-bhkhl1`). **Read the collision note first
  ([`PROCESS-NOTES.md`](PROCESS-NOTES.md), 2026-09-10, collision #14):** two Builders swept this entry in the
  same hour, from opposite ends of the same measurement. `HintAnchor` and its 28 anchors landed on `main`
  first and are the record; my own component and its 33 anchors were **dropped rather than re-applied**, and
  what is here is only what theirs did not reach. On the one point where the two differed, theirs is better
  and is what ships: `stopPropagation` for an anchor inside something clickable, which mine did not have.
  **What this slice adds is the remainder of that list**, converted to `HintAnchor` one line each:
  `NightsCard` ×3 (a night's *"ended early"*, *"bright Moon"* and its verdict badge — the Target page's own
  per-night table), `Calibration` ×2 (the broken-pixel repair state and each master's defect note, the two
  sentences on that page that are not restatements of a control), `BestPictures` ×2 and `Gallery` ×1 (the
  *"why is this picture here"* and *"what is this count"* chips). `NightsCard`'s verdict badge **skips the
  anchor entirely when it has no sentence** rather than passing `disabled`: `HintAnchor` makes its child a
  tab stop with `role="button"`, and a verdict with nothing to say must not advertise itself as answerable.
  **And the guard, which is the durable half.** `components/hintAnchorDrift.test.ts` reads every non-test
  `.tsx` in the app through Vite's own `import.meta.glob` and fails if any `<Tooltip>`'s first child element
  is a `<Badge>`. Eight sweeps have each fixed the sites that existed on the day and nothing stopped the next
  one being written the old way — which is precisely how the badges survived the first four, since this
  entry lists its open work by *route* and they live in shared components no route owns. It is proven armed
  two ways rather than trusted: against a synthetic bad site, whose `file:line` it reports, and by asserting
  the sweep really walked the tree (>80 files, two named ones present) — an empty result is what a clean
  tree and a broken scanner both look like. It deliberately says nothing about a `Tooltip` on a *control*:
  that half is a judgement per site (a button that only previews something is a safe way to find out), which
  is not a guard's business. **It caught a non-defect on its first real run and the rule was narrowed
  honestly rather than quietly:** it flagged the frames table's `Rejected — …` badge, whose tooltip repeats
  the badge's own text — the site the seventh slice had already, correctly, left. So the rule is *a
  `<Tooltip>` around a `Badge` is a defect **when the tooltip says something the badge does not***, and the
  other case opts out with a `hint-anchor-exempt:` marker carrying its reason; a second test pins the
  exempt list **by file**, so a second exemption cannot be added silently.
  `frontend/tsconfig.json` gains `"vite/client"` to its `types` so
  `import.meta.glob` is typed; `vite` was already a devDependency and nothing new is installed.
  **▶ NINTH SLICE SHIPPED — v0.414.1, the one *interactive* site the same measurement said was worth
  doing** (same run, same branch). Stack's **"Save as defaults"** carried its sentence on a `<Tooltip>`
  wrapped around the button, and that sentence is the only statement anywhere that the button also decides
  what the *unattended* walk-away stack does for that target — a persistent effect, since the saved blob
  wins over `default_stack_options` in both readers (v0.372.0). So on a phone the one gesture available for
  "what does this do?" was the gesture that did it: the v0.402.1 defect on a button whose consequence
  outlives the page. (The explanation *does* exist — in the success notification, i.e. after the save.) Now
  a `HintIcon` **beside** the button inside a `Group gap={6}`, so its label, action and accessible name are
  untouched and the four existing assertions that find it by role and name pass unchanged. **The rest of the
  interactive half stays category (b), checked rather than assumed:** the editor's preview-tool row has had
  `PreviewToolGuide` since v0.402.0; `IncomingCalibrationCard`'s tip only names the file its own card
  describes; History's *"Reuse settings"* / *"Compare"* navigate, which is reversible, and would need one
  icon **per run card** — the "one more always-on element" the standing IA priority exists to prevent; and
  Stack's disabled *"Start stacking"* tip repeats, word for word, the yellow *"No plate-solved frames yet"*
  alert at the top of the same page (a disabled `<button>` receives no pointer events, so it was never
  reachable on a mouse either). Regression in `Stack.test.tsx`, failing before **by saving**.

  **Still open, unchanged from the list above:** `BestMonthsStrip`, `MosaicMapCard`, `LifeList` and
  `ImageLightbox`'s bare-icon anchors — each is a *chart cell or an icon button*, not a chip, so each wants
  its own judgement rather than the one-line swap; and the interactive half of the class generally.


- **IMPROVEMENT IDEA (Scout 2026-07-23) — surface calibration-master mismatches (and a *never-applied* wrong-shaped
  bias) at *bind time* in the calibration UI, not only buried in the stack log.** *(Friendliness + trust; size S–M;
  PRIORITY 3, adjacent to image-quality.)*
  **▶ PARTIAL — the two exposure/temperature mismatch advisories are now surfaced at pick-time on the Stack form.**
  The exposure-mismatch half shipped earlier as the inline `darkWarning`/`flatDarkWarning`/`darkScaledNote`/
  `biasIgnoredForLights` cautions the Stack form renders beside each master `Select` (with a one-click "scale this dark"
  fix). The **temperature-mismatch** half shipped **v0.208.1** (Builder 2026-07-25, branch `claude/pensive-faraday-jqlh52`;
  frontend-only, tested): a new inline `darkTempWarning` warns whenever the chosen light-dark's `sensor_temp_c` and the
  target's median sub temperature (`calibrationSuggestions().params.sensor_temp_c`) are both known and differ by ≥5°C —
  mirroring the engine's `CalibrationMasters.calibration_warnings` temperature advisory (`_TEMP_MISMATCH_TOL_C=5.0`),
  which until now reached only the stack log. It's independent of the exposure warning (a dark can match on exposure yet
  be temperature-mismatched — and, unlike an exposure gap, bias-scaling can't correct it), so it fires even on an
  exposure-matched dark. Regression: `frontend/src/routes/Stack.test.tsx` (+1 — an exposure-matched 30 s dark shot 15°C
  warmer warns on temperature with *no* exposure warning). Upgrade-safe: frontend-only, additive, reuses data already in
  the suggestions payload; no API/schema/default change.
  **▶ SLICE (c) — the wrong-camera/binning half SHIPPED v0.215.0** (Builder 2026-07-30, branch
  `claude/relaxed-turing-m9ayja`; tested). A master whose dimensions don't match the target's frames is not merely a
  poor match — `CalibrationMasters.validate` **refuses** it, so the whole stack job dies with an error a beginner
  can't decode (and, since v0.214.0, the walk-away auto-stack silently *skips* it, so "I added darks" quietly isn't
  true). Both now get said out loud at pick time. **Backend:** `GET /api/targets/{safe}/calibration-suggestions`
  gained `params.width_px` / `params.height_px` — the target's **modal** raw frame size via a new shared
  `webapp/calibration.py::modal_dim` (lifted out of `pipeline._confident_master_binding`, so one mis-ingested frame
  from another camera can't move the size every master is judged against). Additive keys; the masters payload already
  carried each master's own dims, so that's all the frontend needed. **Frontend:** a pure, unit-tested
  `frontend/src/calibrationFit.ts` (`masterFitsFrames` / `masterSizeWarning` / `masterOptionSuffix`) drives (i) a
  **red** inline alert under each of the four master selects naming both sizes and saying the stack would fail, and
  (ii) a "— wrong size for this target" suffix in the picker itself, so a mismatched master reads as unusable
  *before* it's chosen (and never carries the ★ recommended badge). Deliberately one-sided, mirroring the server-side
  gate: an older master that recorded no size, or a target whose frames never recorded one, can't be disproved and is
  never flagged. Tests: `calibrationFit.test.ts` (+7), `Stack.test.tsx` (+2 — a 1080×1920 dark on 480×320 subs warns
  *and* is marked in the picker; a matching dark stays silent), `tests/webapp/test_calibration.py` (+3 — the frame
  size is reported, is `None` when unrecorded, and `modal_dim` ignores strays/unknowns). Upgrade-safe: two additive
  response fields + display-only frontend; no config/DB-schema/on-disk/default change and no API-shape break (an
  older client ignores the new keys; a newer client against an older backend simply can't disprove anything and flags
  nothing). ~~**Still open:** the narrower *bias-shape-vs-dark* inert case (a bias whose shape doesn't match the
  **dark** it's paired with, rather than the frames) — same idea, different comparison.~~
  **▶ SLICE (d) — the bias-shape-vs-dark case SHIPPED v0.245.4** (Builder 2026-08-07, branch
  `claude/gallant-galileo-hyz6ug`), and chasing it turned up **a real engine bug** in the same predicate.
  `_dark_scaling_applies` correctly requires the bias to be the **dark's** shape (it holds the readout pedestal fixed
  while the dark current is rescaled), and falls back to subtracting the dark **unscaled** when it isn't — but two
  places tested only "a bias is loaded":
  **(1) the FITS provenance (the bug).** `_build_output_header_meta` (`seestack/stack/stacker.py`) stamped
  `DARKSCAL`/`DARKDEXP`/`DARKLEXP` on that looser test, so a run whose bias couldn't scale anything still told the
  owner *"Dark scaled to sub exposure · 30s → 10s"* in the run Info / History — about a dark the engine had
  subtracted untouched, at full 30 s pedestal, on every frame. The stamp now asks the bundle itself via a new
  `CalibrationMasters.dark_scaling_provenance(light_exposure_s)`, which returns non-`None` under exactly the
  condition `_effective_dark` scales under, so the claim and the pixels can't drift again. *(Regression test fails
  before / passes after.)*
  **(2) the Stack form.** It said *"Dark exposure-scaling is on — this 120s dark will be scaled to match your 30s
  subs"*, a promise the stack doesn't keep, and suppressed both the real exposure warning and the "your dark already
  contains the bias" note. `darkScalingActive` now also requires `darkScalingBlockedNote(dark, bias)` to be null, and
  a new yellow note names both sizes and says the dark goes in unscaled. The engine's own advisory got the same
  treatment: its exposure warning used to end *"or turn on dark exposure-scaling (needs a master bias)"* — advice
  the user has already taken — and now explains the shape clash instead.
  **Also fixed alongside:** the bias slot's red *"Stacking with it will fail"* size warning was simply untrue once a
  dark was chosen — `validate` only refuses a wrong-sized bias when it is the calibration (no dark), so the stack
  runs and quietly ignores it. `biasSizeWarning(bias, frames, dark)` now stays silent there and lets the scaling note
  say what the size actually decides. **Not affected:** the unattended auto-binder, which gates dark *and* bias
  against the subs' dimensions, so anything it binds already matches. Upgrade-safe: no config/DB/on-disk/API-shape
  change, no default flipped, and the stamp is only ever *withheld* where it was previously wrong. Tests:
  `tests/test_output_header_meta.py` (+1 fail-before, and its fixture now builds a **real** `CalibrationMasters`
  instead of a hand-rolled stand-in — the mock is how the stamp drifted from the pixel path in the first place),
  `tests/test_calibrate.py` (+2 — the warning names both sizes and stops asking for something already done;
  `dark_scaling_provenance` agrees with `_effective_dark` on all four outcomes), `calibrationFit.test.ts` (+6),
  `Stack.test.tsx` (+1 fail-before).
  **▶ THE AFTER-THE-FACT HALF SHIPPED TOO, v0.215.1** (Builder 2026-07-30, same branch; tested). Pick-time is only
  half the story: the walk-away user never opens the Stack form, so they meet the problem as an uncalibrated result
  in History next to a library that visibly *holds* a dark. `calibration.diagnose_uncalibrated` — the
  "why was my stack uncalibrated?" advice already rendered on the run's History card via
  `calibrationSummaryText(cards, calibration_advice)` — only recognised **one** signature (a gain/temp-matching dark
  at the wrong exposure with no bias to scale it) and fell back to the generic "build or pick a master" copy for
  everything else, which reads as a bug when a master is sitting right there. It now takes the target's
  `width_px`/`height_px` and detects the **wrong-camera/binning** signature first (`_wrong_size_advice`): *"Your
  master dark was built at 1080×1920, but this target's frames are 480×320 — a different camera or binning mode, so
  it can't be applied. Build a master dark from frames shot the same way as these subs."* (plural variant when
  several all conflict). Checked **before** the exposure signature, since advising "build a bias to scale it" is
  false while the dark can't be applied at all; and only when **every** master of that kind conflicts — with one
  usable master left, size isn't why the stack was uncalibrated. The three size gates (unattended auto-binder, saved-
  pick binder, this diagnosis) now share one `calibration.dims_conflict` rule so they can never disagree.
  `_uncalibrated_advice` (`webapp/routers/stack.py`) passes the modal frame dims. Tests:
  `tests/webapp/test_calibration.py` (+6 — the advice fires, outranks the exposure advice, needs *every* master to
  conflict, stays silent when either side's size is unknown, the plural flat wording, and `dims_conflict`'s
  one-sidedness), `tests/webapp/test_stack_render.py` (+1 endpoint — a wrong-size dark yields the new advice). One
  pre-existing endpoint test registered its "mismatched dark" as a **4×4** master against 480×320 frames — an
  unrealistic fixture that the new (correct) signature now pre-empts; it was re-registered at the target's real frame
  size so it still exercises the exposure signature it was written for. Upgrade-safe: additive keyword args with
  `None` defaults (an omitted size skips the new signature entirely), advisory string only, no
  config/DB/API-shape/default change.
  `CalibrationMasters.calibration_warnings()` already produces the right
  plain-language advisories ("Master dark is 30s but your subs are 10s — its pedestal will be over-subtracted on every
  frame…"; the temperature-mismatch line), and this run's fix keeps them honest. But they only reach the *stack log* —
  a beginner binding a dark/flat/bias to a target never sees them until (if ever) they read a log, so they ship a
  silently mis-calibrated stack. Idea: when a user binds masters (the calibration bind dialog / `POST` bind endpoint),
  compute and return these warnings against the target's representative sub exposure/temperature and show them inline
  ("this dark was shot at a different exposure — turn on exposure-scaling or use a matched dark"). Also flag a
  **loaded-but-inert** master: a bias whose shape doesn't match the dark (never applied — the case behind this run's
  bug) or a master whose dimensions don't match the target's frames, with a plain "this master won't be used because it
  doesn't match your camera/binning" note — so the user isn't misled into thinking calibration is happening when it
  isn't. Read-only/additive: reuses the existing `calibration_warnings` + `validate` logic at a new (bind-time) call
  site; sane default is simply *showing* what the engine already computes. Ship as a slice: (a) return warnings from the
  bind/preview endpoint; (b) render them in the bind dialog; (c) add the inert-master notice. Serves the OSC beginner
  who "added darks" and expects them to just work.
- Guided "getting started" / empty states that tell a first-timer exactly what to
  do next; audit every screen for jargon and add plain-language "why" tooltips;
  reduce visible option clutter (progressive disclosure). (M, friendliness)
  _(Progress: the **Jobs page** — the very first screen a beginner lands on after
  clicking "Scan incoming" — was the last route showing raw engine jargon; its
  snake_case job kinds (`pipeline`, `qc_solve`, `editor_png`…) are now translated
  to plain language and its empty state guides to "Scan incoming" — shipped
  v0.84.2. A Builder dogfood of the other five routes (Dashboard/Library/Target/
  History/Editor) found them already well-handled with icon+prose+next-step empty
  states, beginner tooltips, and translated reject/combine labels.)_
- Better long-job feedback and clearer error messages. (S, friendliness)
  _(~~Idea: map the handful of known fatal `job.error` messages to plain language~~ —
  **shipped v0.84.3** (see Shipped). A `friendlyJobError` helper now translates the
  memory-budget refusal, "nothing plate-solved to stack", empty-alignment, and
  missing-reference-WCS failures into a plain sentence + next step, falling back to the
  raw text verbatim for anything unrecognised. Remaining long-job-feedback ideas welcome.)_
  _(~~Follow-up idea, found while shipping v0.84.3: `friendlyJobError` matches on the raw
  exception *string*, which is brittle if an engine message is reworded. Stamp a stable
  canonical `error_kind` server-side and prefer it in the frontend.~~ — **shipped v0.84.4**
  (see Shipped). `JobManager` now classifies a fatal exception into a canonical `error_kind`
  (`memory_budget`/`no_solved_frames`/`no_alignment`/`no_reference_wcs`) at the catch point,
  persists it (additive `error_kind` column, in-place migration), and exposes it on the job;
  `friendlyJobError(raw, kind)` prefers it and falls back to the string matcher on an older
  backend.)_
  _(~~Follow-up, found while shipping v0.84.4: the calibration **Build-master** job raises a
  bare `FileNotFoundError: No FITS files found in {dir}` when pointed at an empty/wrong
  folder — a common beginner mistake in the darks/flats workflow that showed a raw Python
  exception on Jobs.~~ — **shipped v0.84.5** (see Shipped). Added a `no_fits_in_folder` kind +
  translation ("No FITS frames were found in that folder" + point-at-the-right-folder next
  step), matched on the specific phrase so internal FileNotFoundErrors aren't mis-dressed.)_

### Image quality — for the OSC Seestar workflow (PRIORITY 4)

- **NEW IDEA (Builder 2026-09-04, the *behavioural* consequence of the v0.340.0 measurement — read the caution
  before touching this) — an unattended drizzle run could skip a rejection pass that provably clips nothing,
  and get 1.75× of its canvas memory back.** *(Pillar: autonomy + image quality — PRIORITY 2/4; size S to
  write, **L to be sure of**; the on-by-default hot path, so measure or leave it.)* v0.340.0 measured that the
  two-pass drizzle clip removes **nothing at all** below `kappa_min_frames` samples on a pixel — the block in
  the sweep came out at the naive average to a part in 1e-3 at every depth up to 10. `_afford_drizzle_reject`
  nonetheless takes the pass whenever `n >= 4` on the *target's* frame count, and the pass costs
  `_PEAK_CANVAS_ARRAYS_DRIZZLE_REJECT` (7) full-canvas RGB planes against the single pass's 4 — the 1.75×
  jump that `_guard_stack_memory` refuses on, and the exact reason the unattended path already forgives it
  when the budget is short. **So on a thin drizzled mosaic the app is paying its largest memory premium for a
  pass whose output is bit-identical to not running it** — and the owner's union mosaic canvas is the largest
  canvas this app builds. Declining it there would make some runs fit that today are stepped down to a smaller
  `drizzle_scale`, i.e. *better* pixels from a smaller footprint.
  **Why this is filed, not built.** "Bit-identical" is a claim about the sweep's fixture, not a theorem: the
  clip's own Bessel correction and the per-pixel `neff` gate mean the honest bound is per-*pixel*, and a
  mosaic has a deep centre and thin edges — a canvas whose peak coverage clears 11 must keep the pass even if
  its thinnest panel does not. So the gate would have to be the **coverage plane**, which is not known until
  the canvas is built, where `_afford_drizzle_reject` is priced. And the failure mode is silent: get it wrong
  and a satellite that *would* have been clipped is baked into the owner's picture with no note anywhere. Do
  it only with a before/after showing bit-identical output on a real mosaic at several depths, and with the
  skip stamped in the provenance the way `DRZREJSK` already stamps the memory case.

- **Let a mosaic choose its rejection method *per pixel*, not once for the whole canvas.** *(Pillar: image
  quality — PRIORITY 4; size L; opened by the A6 fix, v0.326.7.)* A6 fixed `auto_reject` reading the target's
  frame count where the honest number is a panel's depth, and it now sizes the method from the **thinnest
  substantial panel**. That is the right global answer, but it is still *one* answer: on a mosaic carrying a
  3-sub panel beside a 200-sub panel, the deep panel is stacked with min/max and loses κ-σ's multi-outlier
  reach and its quality weighting, purely because a thin neighbour exists. The coverage plane already knows
  each pixel's true sample count (`frame_coverage`), and both accumulators already degrade per-pixel, so the
  shape is "dispatch from the coverage plane" rather than "pick one and hope". **Why it's L and not M:** it
  touches the combine hot path and its memory bounds (two accumulators live at once, or one that switches
  rule per pixel), and the provenance card / `REJMODE` / `stackhealth` all currently assume a single method
  per run. Wants a measurement first: how often does the owner's real library actually have a mosaic whose
  panel depths straddle `kappa_min_frames`? If the answer is "rarely", the global choice is good enough and
  this should be closed rather than built.

- **Re-measure the panel floor against real mosaic data once there is any.** *(Pillar: image quality —
  PRIORITY 4; size S; opened by the A6 fix.)* `AUTO_REJECT_PANEL_MIN_FRAMES` is 3 because that is the smallest
  population *either* method can act on, which makes it un-arbitrary — but it also decides when a stray
  mis-solved sub counts as a panel. It has only ever been exercised on synthetic pointings. When a real
  mosaic's per-panel counts are to hand (the Scout has pulled the owner's folder listing before), check that
  the clustering separates his panels the way the synthetic fixture does, and that no panel of his lands on
  the wrong side of the floor.

- **NEW IDEA (Builder 2026-08-31, the anchoring question the v0.320.1 per-panel patches deliberately left
  measured-but-unaddressed) — chain each mosaic panel's refine reference to a neighbour it overlaps, so the
  whole mosaic keys off *one* plate solve instead of one per panel.** *(Pillar: image quality — PRIORITY 4;
  size M; **do not start this without a measurement that says it is needed** — see below.)* Every panel now
  cuts its reference patch from its own central sub, and every patch is aligned to the same canvas WCS, so the
  panels are tied together only as tightly as their two reference frames' *plate solves* agree. In principle a
  panel can therefore sit a fraction of a pixel off its neighbour where before it sat wherever its solve put
  it. **The measurement says this is not currently costing anything:** on the four-panel fixture the finished
  seam step went **down**, 0.052 → 0.039 sky sigma, because individually-sharper panels beat the notional
  drift. So this is filed as a *lead*, not a defect.
  **The shape if a real mosaic ever shows it:** mosaics overlap by design (a Seestar steps ~0.8 of a field, and
  the 512² patch is wider than a 480 px panel — measured overlap ~116 px, well over the 64 px correlation
  floor), so a panel's reference frame can itself be refined against an already-built neighbouring patch
  *before* its own patch is cut, walking one anchor outward from the reference panel. **What would justify it:**
  `SEAMRES` measured on a real multi-panel Seestar mosaic with `subpixel_refine` on, compared against the same
  subs stacked with refine off. If the seam is not worse, leave this alone — it adds an ordering dependency
  between panels for no measured gain.

- **IDEA / GPU-ONLY HARDENING (Scout QA audit 2026-08-27 #18, traced — NOT a verified bug; unreproducible
  without cupy, nil-impact on fully-NaN tiles) — `per_frame._subtract_background_gpu` (`seestack/bg/per_frame.py`
  ~line 604) fills a *fully-masked* background tile with the global **luminance** median (`luma_med`) rather than
  with neighbouring-tile values as the adjacent comment claims. For a low-sky channel (e.g. blue) that is the
  wrong per-channel scale, and the bicubic tile-grid interpolation could bleed it into coverage-edge tiles,
  faintly tinting a mosaic panel's edge.** *(Pillar: image quality — PRIORITY 4; size S; GPU path only.)*
  **Why it's not filed as a bug.** The direct effect on a *fully-NaN* tile is nil (`NaN − x` stays `NaN`, so the
  gap survives); the concern is only the interpolated bleed into *adjacent partially-covered* tiles, and it could
  not be executed/measured (no cupy in the audit env). The **CPU path is clean** (the bg audit reproduced it).
  So this is a hardening lead for a GPU-capable follow-up, not a known-wrong result. **Fix direction (when a GPU
  box is available to test on):** fill a fully-masked tile from its nearest covered neighbours in the *same
  channel's* tile grid (or leave it NaN and let the existing coverage-edge handling own it), matching what the
  comment says and the CPU path does — then verify on a real mosaic sub with a low-signal channel that no panel
  edge picks up a tint. Confidence: traced (single read; GPU path not executed). Do NOT blind-flip this on the
  hot path without a GPU repro.

- **NEW IDEA (Builder 2026-08-30, the one limitation deliberately accepted by the v0.304.1 panel-levelling fix (main's))
  — tell "this panel is sparse" from "this panel was hazy" using the panel's own *history*.** *(Pillar: image
  quality / trust — PRIORITY 4; size M; do NOT start it without deciding the cross-night comparability question
  below.)* `session_recap._level_panels` levels a mosaic's panels against each other **within one session**,
  which is the only signal available there — so a sky that closes in exactly at a panel boundary of a strictly
  sequential single-pass mosaic is levelled away with the panel step. It costs nothing on the common case (a
  Seestar revisits its panels, so real haze shows up *inside* each panel and survives), which is why the fix
  shipped as-is. The disambiguator is each panel's **own median over the target's whole history**: a panel
  scoring well below what that same panel usually scores was hazy, not sparse. `_compute_transparency_ratio`
  already does exactly this per panel, so the machinery exists. **The question to settle first:** the raw
  `transparency_score` is not comparable across gain/exposure changes, and a target's history can span a
  settings change — so a historical baseline needs either a gain/exposure guard or a fallback to today's
  within-session levelling. Fail back to the current behaviour whenever it can't be established; never guess.

- **LEAD (Builder 2026-09-08, filed with v0.387.0 because it is the one thing that shipped unmeasured) — how
  long does the overlap gain pre-pass actually add to the owner's mosaic stack?** *(Pillar: performance —
  size XS to measure, and **do not "optimise" it before measuring**.)* `overlapgain` runs up to
  `MAX_FRAMES_PER_PANEL = 5` subs per panel through `align.align_one` **sequentially** at stack setup — nine
  panels is 45 loads, each paying a debayer plus the per-frame `Background2D` fit, which is the expensive
  half. On this repo's fixtures it is seconds; on the owner's 1080×1920 subs it is plausibly 1–3 minutes,
  against a mosaic stack that runs for hours. That is very likely fine, which is exactly why it should be
  *measured* rather than pre-emptively parallelised: the obvious change (feed it the stacker's own
  `max_workers` pool) multiplies the pass's peak memory by the worker count on the one path §6 calls out for
  its OOM history. If a measurement ever says it matters, the cheaper lever is `MAX_FRAMES_PER_PANEL` — the
  ratio is a median over thousands of coarse cells, so 3 subs a panel would cost little accuracy — not
  threads. **Measure on real subs; the synthetic ones are 480×320 and prove nothing about this.**

- **NOTE for the "bisect the v0.158→v0.220 colour chain on a synthetic mosaic" follow-up above (Builder
  2026-08-05).** That entry asks a future run to measure "the visible plateau/edge structure" across a panel
  boundary with SCNR / the per-frame flatten / `remove_final_gradient` individually disabled — and warns that the
  raw seam step is dominated by the injected offsets, so a bespoke measurement is needed. `measure_seam_residual`
  (v0.233.0) **is** that measurement, already calibrated and tested: one unit-free number per configuration,
  measured on the finished image with the grain as its yardstick. Whoever picks that bisect up should run it
  rather than build a fresh harness.

- **IMPROVEMENT IDEA (Scout 2026-07-23) — a small (3-frame) default stack gets *no* outlier rejection at all, so a lone
  satellite/plane trail or cosmic-ray/hot pixel in any one of those 3 subs lands straight in the final picture.**
  *(Image-quality + autonomy pillar, PRIORITY 2/4; size S; **default-behaviour change — flag for care/owner judgement,
  see caveat**.)* **What's happening (traced this run):** the stack dispatcher gates κ-σ on `n >= 4`
  (`stacker.py:1177`) and min-max on `n >= 3` (`stacker.py:1144`); below those it silently runs plain **mean** with no
  rejection pass. With the *default* options (`sigma_clip=True`, `min_max_reject=False`, `auto_reject` off), a **3-frame
  stack** therefore falls through to plain mean — κ-σ genuinely can't bite at n=3 — and any transient outlier in one
  sub survives into the result. The owner's target user often stacks small first-light sessions; a single passing
  satellite is exactly the kind of thing they'd expect the stacker to remove. **Idea:** when the resolved method would
  fall to plain mean *purely because the frame count is below the κ-σ threshold* but `n >= 3`, auto-substitute a single
  **min-max reject** pass (drop the lone per-pixel extreme, mean the survivors) — the one rejection method that *does*
  work at n=3. This is what `auto_reject` already does deliberately for small stacks (`_resolve_auto_reject`); the
  proposal is to extend that safety to the *default* small stack too, so a beginner who never touched the Stack form
  still gets trail/hot-pixel protection on a 3–4 frame night. **Caveat (why it's an idea, not a fix):** this **changes
  the pixels** of an existing 3-frame default stack (mean → min-max-mean), i.e. a default-behaviour change on a live
  install (§9). It is arguably strictly *better* (min-max of 3 = the median-ish middle sample, robust to a single
  outlier, only marginally noisier than the 3-sample mean), but a default change wants a deliberate call. Ship it
  behind the existing `auto_reject`-style resolution rather than an unconditional flip if that keeps it opt-in-safe, or
  file for owner sign-off if it must change the bare default. **Tests:** a synthetic 3-frame stack with a bright
  trail/hot pixel in one sub → assert the trail is gone from the result and `STACKER`/`REJMODE` reflect min-max (pairs
  cleanly with the STACKER-label fix shipped v0.179.2). Confidence: traced.
  **▶ LARGELY OVERTAKEN BY EVENTS — re-check before spending a run on it (Builder 2026-08-17, verified in the
  code, not assumed).** This was filed in July, and the two paths a beginner actually reaches have both been
  given `auto_reject` since: **(1)** the *manual* Stack form seeds `auto_reject=True` for a never-configured
  target (`webapp/routers/stack.py::get_stack_defaults`, v0.149.0), and **(2)** the *walk-away* auto-stack injects
  `auto_reject=True` whenever the merged options carry no explicit rejection key
  (`webapp/pipeline.py::_stack_target`, ~L2101). `_resolve_auto_reject` then picks order-statistic min/max below
  `kappa_min_frames`, which is exactly the protection this entry asks for. **What is genuinely left is only the
  case the entry's own caveat says needs care:** a user who has *explicitly saved* `sigma_clip` defaults and then
  stacks 3 frames — i.e. someone who took control of the setting. Changing the pixels for them would be a default
  flip on a live install (§9) to override a choice they made, which is the wrong trade. **So: don't re-pick this
  as filed.** If anything is worth building here it is *advisory* — say on the Stack form that κ-σ can't remove a
  lone trail at this sub count and offer the one-click switch, the same shape as the shipped photometric-
  normalization nudge — not a silent change to their combine.

  **✅ THE ADVISORY HALF SHIPPED (Builder, v0.323.1, branch `claude/zen-mccarthy-v56oj1`) — and building it found
  that the form was giving the *opposite* advice, not merely no advice.** Nothing about anyone's combine changed;
  no threshold moved; no default flipped.

  **What was actually wrong.** The Stack form's low-frame caution fired below a hard-coded `SIGMA_CLIP_MIN_FRAMES
  = 5`, said sigma clipping *"can reject real signal as an outlier"*, and offered one button: **"Turn off sigma
  clipping."** At the default κ=3 every count it fired at (1–4) is a count at which κ-σ **cannot clip anything at
  all** — a lone point's z-score against statistics that still include it maxes out at `(n−1)/√n`, which does not
  reach κ=3 until `kappa_min_frames(3.0)` = **11 frames**, and below 4 the dispatcher does not even run the pass.
  So the app was telling a beginner with a 3-sub first light that their rejection was too aggressive, and offering
  to swap no rejection for no rejection — while `seestack.stackhealth` told the *same user* on the *finished
  picture* that sigma clipping "couldn't drop anything" and to re-stack with Auto outlier removal on. Two shipped
  surfaces, one fact, opposite answers.

  **The fix is a shared answer, not a second opinion** — the shape this project keeps converging on.
  `rejection_reach(options, n)` (`seestack/stack/stacker.py`) resolves `auto_reject`, asks the new public
  `combine_method` which combine the dispatcher will *actually* run, and reads the same `kappa_min_frames`
  `stackhealth` reads. A test asserts the two agree at every frame count: the form's pre-run warning and the note
  on the finished picture are now mathematically incapable of disagreeing. `combine_method` also replaced the
  fourth copy of the dispatcher's gates, in `_build_output_header_meta` — so the `STACKER` card and the form's
  warning can't name different methods either.

  **The copy now says what will happen and points at what helps**, in three shapes decided by the engine, not by
  the browser: κ-σ on but blind (*"…can't actually drop a passing satellite… a lone outlier only stands out far
  enough from the average to be clipped from about 11 frames up"*), the sub-4-frame fall-through (*"will combine
  as a plain average"*), and below min/max's own 3-frame floor, where the honest answer is that **no setting can
  help** and the button is withheld. The action is **"Turn on Auto outlier removal"** — `stackhealth`'s own
  advice, verified by a test to actually reach a lone outlier at every count from 3 up. It fires only when the
  user *asked* for rejection, so it is never a nag at someone who opted out, and it stands down while the
  streak-specific `minMaxRejectHint` is up rather than stacking a second yellow alert.

  **The old caution is kept, not deleted** — narrowed to the counts where its sentence is true (the clip really
  will bite), which at the default κ is the empty set and at a user-loosened κ=1 is frames 4. Its "Turn off sigma
  clipping" button is untouched there.

  **Upgrade-safe (§9):** one additive query param on `stack-estimate` defaulting to `StackOptions`' own
  `sigma_clip=True` (so an older frontend sees byte-identical answers), one additive response field, and the
  param provably cannot move `peak_bytes` — the only plane it gates needs `record_rejection_map`, which this dry
  run never sets, and a test pins the three peaks equal. No config, schema, on-disk, default or engine-behaviour
  change.

  **Tests: +17 engine (`tests/test_rejection_reach.py`), +2 endpoint (`tests/webapp/test_stack_estimate.py`),
  +10 unit and +4 rendered frontend.** The two existing tests that pinned the *wrong* advice were rewritten to
  pin the corrected advice on the same paths. One unrelated print-plan test was matching "2 accepted, solved
  frames" from the sigma-clip caution rather than the sizing line it was written for; it now asserts the sizing
  line's own text.
- **VALIDATION FOLLOW-UP (Scout 2026-07-23) — confirm on real nebula data that the now-live SExtractor skew
  guard (`abs(mean − median) > 0.3·σ → revert to median`) doesn't over-revert on heavy diffuse nebulosity.**
  *(Image-quality / correctness; PRIORITY 4; size S — one real-data check, no blind code change.)* The
  formerly-dead skew fallback in the four sky-mode estimators (`bg/per_frame.py` CPU L378 + GPU L469,
  `bg/final_gradient.py` L231, `bg/coverage_leveling.py` L178) is now **live** with the `0.3·σ` criterion (see the
  struck bug in "Bugs"). An earlier Builder audit flagged that a heavy diffuse nebula reads `|mean−median|/σ ≈
  0.32` on a *raw* region and could trip the 0.3 rail — but every site measures the guard on the **object-masked +
  3σ-clipped sky sample**, where the in-code note says the skew stays well inside the band, and the suite is
  green. **What's left is a confidence check, not a fix:** on a real heavy-nebulosity OSC stack (e.g. North
  America / Rosette), log per-site how often the guard fires and confirm (a) it does **not** fire on genuine
  diffuse-sky tiles (so the intended mode is kept where `final_gradient` deliberately wants it), and (b) it still
  reverts on a truly pathological skew. If it does over-revert on real nebula, raise the site-specific threshold
  (or gate it on `sc_std` magnitude). No change unless (a) fails on real data — same real-data-gating as the
  SCNR / `sky_sigma` items below.
- **NEW (Builder audit 2026-07-16) — engine-audit residue: two low-confidence, NOT-currently-reachable
  notes to keep a future audit from re-flagging them.** (XS each, image-quality/correctness — PRIORITY 4.)
  *(From two independent adversarial stacking-engine audits this run — both otherwise verified the core
  reduction/rejection/mosaic/drizzle/calibrate math correct, backed by numerical repros; the one provable bug
  they found, the non-finite dark/bias poisoning, shipped v0.135.1.)* **(1) GPU vs CPU reproject `cval`
  asymmetry** — `align.py` uses `cval=0.0` on the GPU reproject and `cval=nan` on the CPU one (~L498 vs L523).
  Confirmed *not reachable for real data*: `FRAME_EDGE_INSET_PX=3` guarantees the bilinear stencil never
  touches out-of-bounds within the valid mask for any frame ≥13 px, so GPU and CPU agree; it could only differ
  on ≤12 px synthetic frames, GPU-only. Harmless, but making both `nan` would remove the latent divergence and
  a foot-gun for future edits. **(2) `level_by_coverage` docstring imprecision** — `stacker.py` (~L1175) runs
  it unconditionally and its docstring calls the single-coverage-level case "effectively a no-op", but it
  actually subtracts a per-level sky-mode *constant* (a pedestal shift, brightness-relative-preserving, which
  is intended) — so the wording is misleading, not the behaviour. A one-line docstring correction only; judging
  whether the sky estimate itself is *good* needs real data (see the SExtractor-skew and `sky_sigma` items).
  Neither cleared the churn bar to change this run; recorded so they aren't mistaken for new findings later.
- **"How's my stack?" highlight-clip cue — needs REAL-data threshold tuning before shipping (NOT a blind
  change).** (M, image-quality/trust — PRIORITY 4) *(Builder-filed 2026-07-14, deferred slice-(b) part of the
  "How's my stack?" health check; slices (a) v0.120.0 + actionable/History (b) v0.121.0 shipped.)* The original
  health-check idea listed a "bright core is clipping — the editor's highlight rolloff will recover it" cue that
  reads the **stacked pixels** (the other cues read only stamped run fields + the frames table, so `stack_health`
  stayed pure/offline). Deferred deliberately: (1) it needs loading `master.fits` pixels, so it can't live in the
  pure `stack_health(run, frames)` helper — it must be computed webapp-side (where the master is loaded) and
  passed in as an optional pre-computed cue, and gated so it doesn't load pixels on every Target-page render;
  and (2) **detecting genuine clipping in a *linear, background-subtracted* master needs a real-data-validated
  threshold** — a saturated core shows as a flat plateau of near-max pixels, but the master's max/scale varies
  per target and the background subtraction shifts values, so any "fraction of pixels within ε of max" rule
  risks false-positives (or misses) without validating on real Seestar stacks of both a clipped bright-core
  target (e.g. M42's trapezium / M31's core) and an unclipped faint target. Same real-data gating the SCNR /
  `sky_sigma` / streak-detector items carry. When built: a conservative plateau detector (many finite pixels at
  the exact global max with ~zero local spread = saturation), a `HealthNote(kind="highlight_clip")` that is
  reassuring not alarming (the editor's v0.119.1 rolloff already recovers it in the display), and a webapp-side
  computation behind the existing endpoint. Additive; the note only ever *adds* guidance, never gates.
- **Scout to vet on REAL data: does the STF `_highlight_rolloff` (v0.119.1) mildly *desaturate* bright
  coloured highlights?** (S, image-quality — PRIORITY 4) *(Builder-audit-noted 2026-07-14, from an
  adversarial numeric audit of the v0.119.1/.2 highlight-rolloff fix — which otherwise verified clean:
  monotonic, bounded <1, C¹ at the knee, neutral saturated stars stay neutral, background bit-for-bit
  unchanged.)* The rolloff soft-shoulders each channel **independently** in that channel's own
  shadow-normalized space, so on a bright *coloured* region where some channels sit above the knee (0.7) and
  one below, only the above-knee channels are compressed while the below-knee one is untouched — which mildly
  **desaturates** the highlight. Measured on a synthetic warm core at r≈14 px: old `[0.923, 0.865, 0.806]` →
  new `[0.867, 0.846, 0.806]` (R u8 235→221, B unchanged). It only touches already-bright (>0.8) pixels, is
  a large net improvement over the old hard-clip (which blew the core to featureless white), and doesn't
  violate the code's invariant (below-knee pixels are exactly unchanged) — so it's **not** a regression to
  fix blind. But whether a **luminance-coupled** rolloff (scale all three channels by the *luminance*'s
  shoulder factor, preserving hue/sat while still taming the peak) reads better on a real bright galaxy core
  (M31/M42) is worth a real-data A/B before any change — synthetic can't judge "looks better". Testable on
  `_highlight_rolloff`/`autostretch` in isolation; additive; changing it touches the default view + Auto, so
  real-data-gated like the SCNR / `sky_sigma` items below.
  ~~**Scout to vet on REAL data: does the Auto denoise↔sharpen crossfade over-read a *sky gradient* as
  noise?**~~ — **CLOSED BY MEASUREMENT, v0.382.1** (Builder 2026-09-07). Deferred three times as
  real-data-gated; the v0.225.0 *local* `sky_sigma` estimator had already closed it by construction, and
  running the entry's own gradient ladder says so: at σ=0.003, gradient 0.00→0.05→0.10→0.20 now moves
  `sky_sigma` **0.0042→0.0039→0.0035→0.0030** (it drifts *down*, not up), `_noise_fraction` stays 0
  throughout, and Auto keeps the same sharpening with no denoise pass added — against the entry's recorded
  pre-fix 0.015→0.028→0.054→0.098, which flipped Auto to *sharpen 0.0 / full denoise* by a gradient of
  0.05. Pinned by `test_a_strong_gradient_never_costs_a_clean_stack_its_sharpening`. Entry, numbers and
  the original trace in [`SHIPPED.md`](SHIPPED.md).
- **Scout to vet on REAL data: does Auto's SCNR tint an already-neutral *background* magenta?**
  (S–M, image-quality) `tone.scnr` (`seestack/edit/ops/tone.py::_scnr`) is a one-sided clip — it
  can only ever pull green *down* toward the `0.5·(R+B)` neutral, never up. On data that already
  carries a real green cast (light pollution, OSC green bias) that's exactly right and wanted. But
  on a background that is already colour-balanced and noisy, the clip is asymmetric on the green
  *noise*: positive green excursions get clipped, negative ones are kept, so it **rectifies the
  noise and biases the background median magenta**. Auto applies it at `amount=0.8` after
  `tone.color_calibrate` (gray-star, which has already neutralised the background), so the residual
  it clips is largely noise. **Verified numerically (Builder dogfood 2026-07-08, no change shipped):**
  on a perfectly neutral background (R=G=B=0.30, independent σ=0.03 per-channel noise), `_scnr(amount=0.8)`
  shifts the green median −0.010 and the mean −0.012 (≈0.34σ) — R/B untouched — i.e. a faint magenta
  cast. In the full stack→Auto→export dogfood (realistic 1920×1080 12-sub dithered stack) the export's
  background medians came out R/G/B **0.243 / 0.209 / 0.243** (green ~14% low); a prior audit note
  recorded the same signature (0.196 / 0.174 / 0.196) and read it as "balanced", so this has been live
  and accepted for a while. **Why it's a Scout/real-data item, not a headless Builder change:** it
  touches the most-used one-click Auto path, and whether the clip is a net win depends entirely on how
  much *real* green cast a genuine Seestar background carries (which a headless synthetic can't stand in
  for) — same reasoning as the `sky_sigma` item above. If it reproduces on real neutral-background OSC
  stacks, candidate mitigations to weigh: lower Auto's SCNR `amount`; or protect the background (only apply
  SCNR where signal is above a sky-relative threshold, so the noise floor isn't rectified); or run SCNR
  on the post-denoise image only. Each must be validated so a real green-cast stack still gets its cast
  removed. Testable on `_scnr` / `auto_recipe` in isolation; additive.
  _(Builder dogfood 2026-07-09, v0.99.2 baseline — re-confirmed the artifact and, more usefully, gathered
  a new data point that leans the disposition toward "leave Auto's SCNR as-is." Two synthetic runs through
  the real `auto_recipe`→`apply_recipe` chain: **(1) truly-neutral noisy sky** (R=G=B=0.168 after STF
  stretch, no cast) → `_scnr(amount=0.7)` drops the sky green median 0.168→0.145 (**−14%, a visible magenta
  tint**) while leaving R/B untouched — the pure one-sided-clip-rectifies-noise mechanism, exactly as filed.
  **(2) A green-cast sky** (OSC green bias + gradient), full Auto chain **with vs. without** the SCNR op,
  measured on the background population: *without* SCNR the sky keeps a residual **green excess** (G 0.145 vs
  R/B ~0.127, i.e. +0.017 green) — i.e. `tone.color_calibrate` (gray-star) balances on the *stars* and
  leaves the *diffuse background* green cast **in place**; *with* SCNR the background lands near-neutral
  (G 0.168 vs the 0.172 R/B neutral, only −0.004 magenta). So on a background that carries any real residual
  cast — which post-gray-star OSC backgrounds typically do — SCNR is a **net win** (removes a +0.017 green
  excess for a −0.004 magenta overshoot), and the −14% magenta failure mode needs a background that is
  *already truly neutral*, which gray-star does **not** produce on cast data. This strengthens the existing
  "net value depends on real cast magnitude" reasoning with direct evidence that the common case is
  net-positive, so the safest read is still: **don't blind-change the most-used Auto path**; if a future
  agent does touch it, prefer a **noise-symmetric** mitigation (a soft-clip whose transition width tracks
  the measured background green-noise σ — removes a genuine cast ≫σ as fully as the hard clip while not
  rectifying within-noise excursions) over uniformly lowering `amount` (which would under-remove real
  casts), and gate on a real neutral-vs-cast OSC background sample. No change shipped — the deferral holds.)_
  **▶ THE SAMPLE THIS IS GATED ON IS ALREADY BEING COLLECTED — read it before deferring again (Builder
  2026-09-07).** Every unattended auto-edit stamps the finished picture's residual background cast
  (`editor_auto_skycast:{run_id}`), and `GET /api/auto-cast-summary` reports the neutral/cast split, the
  counts **by dominant tint** and the median deviation across the owner's real runs. That is precisely the
  neutral-vs-cast OSC background sample the deferral asks for: a magenta-dominated `by_cast` on real data is
  the evidence for this entry, and a green-dominated or neutral one is the evidence against it. So the next
  run to pick this up should **read that endpoint's answer on the live install first** rather than measuring
  another synthetic — and still not blind-change the most-used Auto path.
- First-class session/night dimension in the project schema (frames only have
  `timestamp_utc`): per-session sky levelling before combine, per-session
  calibration binding, per-night QC roll-ups. Coverage-levelling's docstring
  already names "between sessions" as motivation but keys on coverage count.
  Large but high value for the multi-night Seestar workflow. (L, correctness)
- **Root-cause fix for the streak/edge-on-galaxy false positive: make the streak detector distinguish a
  trail from a stationary object *per frame* (needs REAL data to tune — NOT a blind change).** (M,
  image-quality/autonomy — PRIORITY 4) *(Builder-filed 2026-07-10, follow-up to the v0.106.2 population
  guardrail.)* v0.106.2 stopped the *catastrophic* case (a bright edge-on galaxy / elongated nebula flagged as a
  "streak" on a majority of subs → whole-target auto-reject) with a safe population rail
  (`qc/runner.py::reconcile_streak_rejections`: re-accept when >½ the target is auto:streak). That's a symptom
  guard: a bright galaxy that flags on only a *minority* of subs (the best-seeing ones) still gets those subs
  wrongly rejected, under the rail. The real fix is to teach `qc/streaks.py::detect_streaks` to tell a transient
  trail from a stationary extended object *on a single frame*. Candidate signals: **absolute minor-axis
  thinness** (a satellite/plane trail is ~1–3 px wide near the PSF; a galaxy core is many px thick, so require a
  small `axis_minor_length` in addition to the elongation ratio); **straightness/fill** (a trail is a near-perfect
  straight ridge — a high Hough-line-length ÷ component-length ratio — while a galaxy's disk is fatter and
  curved); or **cross-frame persistence** (a component at the same sky position across subs is stationary, i.e.
  the target, not a trail — the strongest discriminator but needs the frames' WCS/registration, so it's a bigger
  change). **Why real-data-gated:** any threshold that excludes galaxies risks also missing genuine (thin, faint)
  trails, so it must be tuned/validated on **real** Seestar subs of both an edge-on galaxy *and* a real satellite
  trail before shipping — a synthetic can't stand in for the true width/brightness/straightness distributions.
  Additive, testable on `detect_streaks` in isolation; keep the v0.106.2 rail as the belt-and-braces backstop
  even after the detector improves.

### Features that serve real workflows

*(The Scout's 2026-09-09 "shareable labelled picture" entry shipped as v0.407.0 and was cut to
[`SHIPPED.md`](SHIPPED.md) — the engine render and the endpoint flag already existed; only the download was
missing. Don't re-file it.)*

- **NEW IDEA (Builder 2026-08-29, the two halves deliberately left out of "See what stacking removed"
  v0.299.0) — put the overlay where people actually *look* at a picture, and count what it removed.**
  *(Pillar: trust + understand — PRIORITY 3; both small, both purely additive on machinery that now exists.)*
  (a) ~~**The Gallery lightbox and the Target hero.**~~ — **✅ SHIPPED v0.312.0** (Builder 2026-08-30, branch
  `claude/compassionate-galileo-6jgh4j`), on both surfaces, with the entry's "ship the gate before the feature"
  taken seriously and then found to be **unnecessary** — which is the design call worth carrying forward.

  **The stand-down the entry demanded doesn't apply here, and checking that first is what kept this small.**
  The History card has to withdraw the tint because *its* picture can become something else: opening **Adjust**
  swaps in a live render of the linear master at full canvas, which the tint was never measured against. Neither
  of these two surfaces has such a state — both show the **stored preview bytes** and nothing else, and the one
  variation they do offer (the v0.308.0 North-up *view*) is a turn the overlay endpoint already composes, since
  v0.308.2, from the same `preview_north_up_remainder_deg` the picture itself goes through. So the tint follows
  the picture instead of standing aside, and a test on each surface pins that both URLs pick up `north_up=true`
  together. The share JPEG and the full-res PNG the entry worried about are **downloads**, not what the viewer
  draws.

  **The one real piece of work was the geometry, and it is a CSS trap worth recording.** `ImageLightbox` fits its
  picture with `max-width/max-height: 100%` inside a flex-centred surface and then applies the zoom/pan transform
  to the `<img>` itself. Wrapping the picture and the overlay in a shared positioned box — the obvious way to
  make two images move together — makes the picture's `max-height: 100%` resolve against an **auto-height**
  ancestor, i.e. indefinite, i.e. no cap, and a tall picture then overflows the viewer. The overlay is therefore
  a **sibling**, absolutely positioned with `inset: 0` + `margin: auto` (which centres a replaced element on
  exactly the box `align-items/justify-content: center` puts the picture in), sharing one `imgFit` object and one
  `transform` string with the picture so the two cannot be fitted or moved differently. A test asserts the fitted
  style *and* the transform are byte-identical on both elements, **after a zoom** — the case a separately-computed
  transform would silently get wrong.

  **The gate, and what it cost.** The Target hero needed no new request: `StackRun.has_rejection_map` is already
  on the run it draws. The Gallery drew its cards from `/api/gallery`, which didn't carry the fact — so
  `GalleryItem` gained `has_rejection_map`, computed by the *same* one-line stat beside the
  `has_fits`/`has_preview`/`has_tiff` sweep the item already does (additive, `False` default), rather than a
  per-picture run-info fetch on every lightbox open. That matters because `record_rejection_map` is **off by
  default**: on an ordinary library the control is simply absent, and opening a picture costs nothing extra. The
  run-info fetch that supplies the caption's measured fraction happens only once the tint is actually switched
  on, and the caption's lead sentence never depends on it — an uncaptioned cyan speckle reads as damage, so it is
  captioned even when the number can't be read.

  `removedOverlayCaption` moved out of `routes/History.tsx` into a shared `frontend/src/removed.ts` (the
  `fullres.ts` pattern: one place owns the wording so three surfaces can't drift into three claims about one
  picture), re-exported from History so its existing readers are untouched. The toggle itself is a shared
  `ShowRemovedToggle`, so the two lightboxes offer the identical control.

  **Upgrade-safe (§9):** one additive, defaulted response field; no config, schema, on-disk or default change;
  an older frontend ignores the field and an older backend omitting it reads as "no overlay for this one", which
  is the right answer for every run that never recorded a map.

  **Tests (+12):** 5 in `ImageLightbox.test.tsx` (no overlay unless given; decorative — `aria-hidden`, empty
  `alt`, `pointer-events: none` so it can't eat a drag; identical fit *and* transform at 100 % and after a zoom;
  the caption shown, and not shown when there are no marks), 4 in `LatestPictureCard.test.tsx` and 2 in
  `Gallery.test.tsx` (nothing offered and nothing fetched on a run with no map; the tint and the measured caption
  on request; the tint turning with the picture; and — hero — the caption still appearing when the run-info
  fetch fails), and 1 in `tests/webapp/test_rejection_overlay.py` asserting the Gallery listing's answer both
  ways *and* that it agrees with the run listing's on the same run.
  (b) **"N spots", instead of a percentage (S–M, engine + one response field).** The caption today reuses the
  run's `REJFRAC` — *"that was about 0.4% of your samples"* — because that number already exists. What the
  Scout's entry actually asked for is more human: *"stacking removed 14 streaks and hot spots"*. That needs a
  connected-component pass over the `_rejected.fits` map (scipy's `ndimage.label`, already a dependency), with
  a minimum blob size so the noise-tail speckle isn't counted as 8,000 "spots" — which is the whole difficulty,
  and the reason it was left out rather than guessed at. Compute it **once, at write time**, into a header card
  beside `REJMAP` (not per-request over a canvas-sized file), and surface it on the run-info the caption already
  reads. Measure the threshold against a real map before picking it.

  **⚠️ MEASURED AND STOOD DOWN (Builder 2026-08-30, branch `claude/compassionate-galileo-6jgh4j`) — do NOT
  build this from the summed map; the threshold this entry asks for does not exist.** I did exactly what it
  demanded — measured against real `run_stack` output before picking anything — and the measurement closes the
  idea rather than sizing it.

  **What a blob count actually reads on real maps.** Connected components (8-connectivity) over the planted
  satellite-trail scene at 16 subs: **1,296 blobs**, of which the trail is one (1,453 px). The *same scene with
  no trail at all*: **1,323 blobs**. So counting blobs would tell a user with a perfectly clean night that
  stacking removed 1,323 things. A minimum area does separate them at 16 subs — the largest pure-noise blob was
  4 px against the trail's 1,453, and area ≥ 5 px gives **1 blob on the trail scene and 0 on the clean one**.

  **And that separation dies with the sub count, which is the killer.** A pixel is marked if it lost a sample in
  *any* frame, so the map densifies: non-empty share **1.9 % at 16 subs → 11.5 % at 32 → 31.2 % at 64**, and
  blobs of ≥ 5 px go **1 → 532 → 2,013**, all noise, with the trail starting to percolate into the speckle
  (largest blob 1,453 → 2,762 px). Extrapolated to the owner's 500–800-sub stacks the map is effectively
  saturated and the honest count is a five-figure number. **No minimum area works across the sub counts this app
  is for**, because the discriminator the entry assumes — a mark is dense, noise is sparse — is a property of the
  *per-frame* rejection, and the summed map has thrown it away: a satellite crossing one sub contributes a drop
  count of **1** along its path, pointwise indistinguishable from a noise-tail clip.

  **If anyone ever wants this, the only honest shape is to count it where the information still exists** — at
  combine time, per frame, before the counts are summed — which is a change inside the memory-bounded hot path,
  not "a connected-component pass over the sibling". That is an L with real OOM risk, for a caption tweak. **The
  percentage stays.**

  **The measurement was not wasted:** applied to the *tint* rather than to a count it found a real bug — the
  overlay washed the whole picture cyan on exactly these dense maps — fixed as **v0.312.1**, at the top of
  "Bugs (fix these first)".

- **NEW IDEA (Builder 2026-08-29, the follow-ups deliberately left out of "Your universe" v0.296.0) — "fly to
  it", and tell the reader what they're looking at.** *(Pillar: enjoy + understand — PRIORITY 3; size S each;
  frontend-only, no new data.)* Three cheap taps on the shipped page, in value order:
  (a) ~~**Fly to this object.**~~ — **✅ SHIPPED v0.302.0** (Builder 2026-08-30, branch
  `claude/compassionate-galileo-lcagow`), with the filed caution honoured exactly: OrbitControls' target stays
  at the origin and only the camera position moves. The trick that makes those two compatible is that the
  destination sits on the object's **own radial line**, just outside it (`flyToCameraPosition` in
  `sky/universe.ts`) — with the object *between* camera and origin, looking at the origin frames it dead
  centre anyway. A `<FlyTo>` component eases the camera there (a fixed fraction of the remaining gap per
  second, `delta` clamped so a backgrounded tab doesn't teleport on its first frame back) and stands down the
  instant someone grabs the controls. The controls' own `update()` runs at frame priority **-1**, i.e. before
  this write, so they follow the camera rather than fight it; the destination is clamped to their own
  `min`/`maxDistance` so the arrival can't visibly snap.
  **Tests (5, in `sky/universe.test.ts`):** the destination is on the object's line and outside it; the
  camera-past-object property on an off-axis object (a unit-dot check, not just an axis case); every placed
  depth **and** both extremes land inside the orbit limits; a degenerate/non-finite position declines with
  `null` rather than flying to NaN; and a further object really does end up further out. The `<FlyTo>`
  component itself is untested, like the rest of the WebGL scene — the maths it runs on is not.
  (b) ~~**The blurb is already there.**~~ — **✅ SHIPPED v0.302.0** (Builder 2026-08-30, branch
  `claude/compassionate-galileo-lcagow`), exactly as filed and at the filed size. `UniverseObject` gained a
  `blurb: str = ""` carried straight off `identify_object`'s `ObjectInfo.blurb` (grepped first — the lookup
  already loads it), `UniverseObjectOut` an additive field defaulting to `""`, and the object card one
  `<Text>` rendered only when the sentence is non-empty. So the read-out is now *about the object* rather
  than two numbers about something the reader may not recognise. **Tests:** three in
  `tests/test_universemap.py` (the blurb travels; a catalog entry without one yields `""`, never `None`, so
  no read site needs a guard; and — the measurement, not an assumption — the **real bundled catalog** does
  carry blurbs for the popular targets), one in `tests/webapp/test_sky_universe.py` pinning the field on the
  response, and two in `Universe.test.tsx` (shown when present; nothing at all for `""` *and* for a missing
  field, so an older backend degrades cleanly).
    *(Original spec: `CatalogObject.blurb` — the plain-language "what am I looking at?" one-liner the object
    card on the Target page already shows — is loaded by `identify_object` and simply not carried onto
    `UniverseObjectOut`. One additive field and one `<Text>`. **Grep first**, don't re-derive the lookup.)*
  (c) **Constellation lines at the backdrop radius.** The star backdrop is a bare point cloud at r=420; the
  offline Sky viewer's recognisable-star labelling is the precedent. Only worth it if a constellation-line
  dataset is already bundled — check before scoping, and do **not** add one as a dependency for this.

- **NEW IDEA (Builder 2026-08-06, same run) — a beginner can crop the Moon, but there is no way to crop anything
  else.** *(Friendliness — PRIORITY 3; size M; **think before building**.)* The framing crop is disk-shaped by
  design (`measure_framing` finds "the one bright thing"), which is right for the Moon and Sun and useless for a
  deep-sky stack — where the framing problem is different anyway (ragged dithered borders, already handled by
  `auto_crop_border`). Filing it only so a future run doesn't read "crop" as a generic gap and build a manual
  crop tool for the editor: that would be pro tooling by the §1 bar unless it answers a beginner question the app
  doesn't already answer. Probably **not** worth building; recorded so it can be declined once rather than
  re-litigated.
  **⚠ Read this alongside v0.379.0, which is NOT what this entry declined (added 2026-09-07 by the run that
  shipped it).** v0.379.0 added no crop *tool*: `geometry.crop` was already in the registry and already in the
  Add menu, and all that shipped was a way to *aim* it — a draggable rectangle over the preview, replacing four
  typed fractions. That is the "make the controls obvious" half of priority 1, not new surface. **What this entry
  still declines stands:** a *disk-shaped* / subject-finding crop for deep-sky, and any new expert framing
  tooling. Don't build either; and don't read v0.379.0 as re-opening this.

- **NEW IDEA (Builder 2026-08-04, follow-on to the v0.229.0 `.zip` upload) — unpack a big archive as a *job*
  rather than inside the request.** *(Autonomy/friendliness — PRIORITY 2–3; size M.)* The zip upload streams to
  disk and then unpacks **synchronously inside the POST**, so a multi-GB night is a long silent wait after the
  browser's progress bar has already hit 100 % (the card does say "Uploaded — processing on the server…", which is
  honest, but it's a blind wait) — and on a slow NAS it could out-live a reverse proxy's request timeout, which
  would read to the user as a failed upload even though every sub landed. **Slice:** keep the streaming-to-`.part`
  half in the request (that's the part the progress bar measures), then hand the temp archive to the existing
  single-worker `JobManager` and return `{job_id}` immediately; the job unpacks, reports per-member outcomes as
  job text, deletes the archive, and kicks the usual scan. The Jobs page then shows real progress instead of a
  stalled bar. **Care:** the temp `.part` must be cleaned up by the job on *every* path (including cancel), and the
  response shape must stay backward-compatible — an older frontend reads `saved`/`skipped`/`rejected`, so either
  keep unpacking inline below a size threshold or return an empty-but-valid summary plus the job id. Worth doing
  only once someone actually uploads a big archive; a few hundred MB unpacks in seconds today.

- **NEW IDEA (Builder 2026-07-25, follow-on to the v0.207.0 `integrationTrend` verdict) — when a target reads
  "sky-limited / plateaued", nudge the "What should I shoot next?" surface toward a fresh target.** *(Pillar: 2
  autonomy, PRIORITY 2–3; size S — frontend-only.)* **Why:** the most useful thing to *do* with a "more subs won't
  help this one much" verdict is move on — but nothing connects that verdict to the existing
  `SuggestTargetsCard` / "Try something new tonight" surface. **The feature:** when `integrationTrend(runs).level`
  is `"plateaued"` for a target the beginner is viewing, add one soft line to (or highlight) the what-to-shoot-next
  suggestion ("You've got this one about as clean as your sky allows — a fresh target would pay off more tonight").
  Purely additive copy tying two shipped surfaces together; self-hides otherwise. Validate the plateau threshold
  reads sensibly on a real multi-night target before making the nudge loud. (S, autonomy — PRIORITY 2–3.)
  **Note (Builder 2026-07-25, `v8z2rz`): partly delivered by v0.209.0's `IntegrationTrendBadge`** — the plateau
  sentence it renders on the Target page already says "*A darker sky or a brighter target will do more than extra time
  on this one*", so the core "move on" nudge is now shown where a beginner decides. What remains here is only the
  *cross-page* tie-in: highlighting the Dashboard `SuggestTargetsCard` when a viewed target is plateaued — which needs
  per-target plateau computation on the Dashboard (extra run fetches), not "purely additive copy". Lower value now that
  the on-page nudge exists; keep the real-data threshold-validation caveat before making anything loud.

- ~~**Data-driven target difficulty** (optional `mag`/surface-brightness in the catalog instead of the curated
  table).~~ **⚪ CLOSED — measured at zero, do not build** (Builder 2026-09-07; full write-up moved to
  [`SHIPPED.md`](SHIPPED.md), search "data-driven target difficulty"). The gap it fills is empty: 157/157 bundled
  objects already get a verdict from `_CURATED` + the cluster type-rule, pinned by
  `tests/test_target_difficulty.py::test_the_bundled_catalog_is_covered_end_to_end_today`. Reopen only with a real
  magnitude source, never from recall.
- **NEW (Builder 2026-07-21, follow-up to shipped "Set as cover" v0.145.0) — let the cover also be an *edited*
  export, not only a raw stack run.** v0.145.0 pins a **`stack_runs` row** as the target's cover (`cover_stack_run_id`
  resolved through the run's `preview_path`). But the #7 spec's motivating case — "a beginner who *edited* a stack
  into a lovely picture" — isn't fully served: an editor export is **not** a `stack_runs` row, so an edited picture
  can't be pinned yet. **Idea:** extend the cover to accept an edited result. Two shapes to weigh: (a) when the
  editor exports/saves, record the edited render as its own light-weight "result" the cover can point at (a new
  nullable `cover_preview_path` alongside `cover_stack_run_id`, set directly to the edited PNG — the thumbnail
  resolver already falls back gracefully if the file is gone); or (b) have the editor "Save as preview" flow (which
  already re-renders a run's `preview_path`) offer a "★ Set as cover" in the same step, so the *edited* pixels
  become the pinned run's preview and the existing run-id cover just works. (b) reuses everything already shipped and
  needs no new column — likely the smaller, safer slice. Beginner bar ✔ (same one-button affordance, extended to the
  place a beginner most wants it — their finished edit). Additive/upgrade-safe (nullable/new surface, off by default).
  _(S–M; PRIORITY 3 friendliness / enjoy-share — completes the "pin my favourite picture" story for edited results.)_
  **⚠ Builder note (2026-08-05, `claude/relaxed-turing-iv0w1h`) — MOSTLY MOOT; verify before starting.** The
  editor's **Apply & save** path (`submit_editor_export` → `_apply_editor_to_run`) does not produce a loose PNG: it
  records the edited result as a **real `stack_runs` row** of its own (`notes="edited"`, its own `preview_path`), so
  an edited picture *can* already be pinned with the existing v0.145.0 "Set as cover" button on that run's History
  card. What is left is only the narrower case of an editor **download/share** export (PNG/JPEG, no run recorded) —
  shape (a) — and the shortcut of offering "★ Set as cover" inside the export step rather than one click later on
  History. Both are marginal against the shipped path, so this is **deprioritised**; don't rebuild the covered part.
- **NEW (Builder 2026-07-21, follow-up to "Your sky, so far" v0.142.0) — add the "clearest night" stat + a
  compose-to-one-image share button.** The v0.142.0 first slice is registry-only, so it omits two nice-to-haves from
  the original idea: **(a)** a "your clearest night" tally (best median FWHM / lowest sky background) — needs a
  per-target frame read (open each `project.sqlite`), so add it as a *separately-cached* enrichment behind the same
  endpoint (or a sibling `?deep=1`), guarded so it never opens every project on a hot render; **(b)** a single
  **"Share this summary"** button that composes the tallies + hero grid into one social-ready PNG, reusing the
  existing share-card/PNG export path (`seestack/sharecard.py`) so the whole "year in review" can go out as one
  image. Both additive/read-only. *(S–M each, friendliness/enjoy-share — PRIORITY 3.)*
  **▶ BOTH SLICES ARE NOW DONE — (b) was already shipped, (a) SHIPPED v0.268.2** (Builder 2026-08-18, branch
  `claude/relaxed-franklin-i98kvb`).
  **(b), verified in the code rather than assumed:** `GET /api/recap.jpg` (`webapp/routers/stats.py`) already
  rendered exactly the filed idea — the recap's own figures drawn over the user's best picture by
  `seestack.recap.draw_recap_poster`, downloaded as `my-sky-so-far.jpg`, with `GET /api/recap` serving the same
  numbers plus a copy-paste caption, and nothing written to the library.
  **(a) "your best night", shipped — and the entry's own caution ("needs a per-target frame read… guard it so it
  never opens every project on a hot render") is answered by not adding a walk at all.** The trick is that
  `/api/activity-calendar` **already** opens every project and reads every accepted frame row for the Dashboard
  heatmap, behind an app-level cache. So the star size rides along as an **optional 4th element** of the tuples
  the webapp already streams into `accumulate_nights` — same walk, same cache, no second pass and no new
  endpoint. Every existing 3-tuple caller folds byte-for-byte as before.
  **What it says.** A new self-hiding card on "Your sky, so far": *"Your best night · 12 Jan 2026 — 2.4 px
  stars — Your steadiest sky yet on M 42 — 1.5 h captured, 180 subs measured."* It is the first thing on that
  page that **ranks** a night rather than adding it up, which is the question a beginner actually asks after a
  few sessions. It ranks by **median star size in pixels** — the same measure the session recap's sharp/soft
  verdict and the Target page's Nights card already use, so the app speaks in one voice rather than inventing a
  second definition of "a good night". (Sky background, the entry's other suggestion, was deliberately left out:
  it tracks the Moon and light pollution as much as the night, so "lowest sky" would rank a new-Moon night above
  a genuinely steadier one.)
  **Honest by construction, silent rather than wrong** (`seestack/activity_calendar.py::sharpest_night`): a night
  needs `SHARPEST_MIN_MEASURED` (5) measured subs to qualify — a one-frame median describes the frame, not the
  night — and at least `SHARPEST_MIN_NIGHTS` (2) nights must qualify, because naming the best of one is not a
  fact about the sky. A failed measurement stored as 0, a negative or a NaN is not counted as a measurement (a
  fabricated 0 px would win every comparison). Ties break on the earlier date. Only nights inside the window are
  considered, so a brilliant night two years ago isn't "your best night" on a 12-month page.
  **Upgrade-safe:** additive optional response fields (`median_fwhm_px`, `n_measured`, `sharpest_night`) on an
  existing endpoint; the frontend types them optional and the card renders **nothing** against a backend that
  doesn't send them, so old/new mix in either direction. No config, DB-schema, on-disk or default change, and no
  new endpoint. **Verified in a real browser as well as jsdom** (`scripts/agent-dogfood.sh` + a probe that serves
  the card a sharpest night): it renders inside the viewport at 1440 px **and** 420 px with no console errors.
  **Tests (+21):** `tests/test_activity_calendar.py` (+8 — the sharpest night is the smallest-star one, a thinly
  measured night can't win, silence on one qualifying night, silence with nothing measured, unmeasurable values
  aren't counted, 3-tuple callers fold exactly as before, ties break earlier, and the window is respected),
  `tests/webapp/test_activity_calendar.py` (+3 — per-night medians on the wire, silence without measurements,
  and the sharpest night serialised whole), `bestNight.test.ts` (+5) and `BestNightCard.test.tsx` (+4 — named,
  silent on null, silent against an older backend, silent on a failed fetch), plus `SkySoFar.test.tsx` (+1 —
  the card is on the page).

### UX & polish
- Mobile layout polish across the newer pages (Calibration, Combine). (S)
- Better empty-states and error messages on long-running jobs. (S)

### Performance (only with a measurement)

- **LEAD, MEASURED (Builder 2026-09-07, the residue v0.374.8 deliberately left) — `/stack-estimate` and
  `/rejection-outlook` are still **~4.7 s** on the owner's 5,477-sub target, and it is now *all*
  `wcs_from_text`.** *(Pillar: friendliness / performance — PRIORITY 3; size M; **do not blind-pick either
  option below**.)*

  **▶ SHAPE (a) IS SHIPPED — v0.374.9, `wcs_io._wcs_from_plain_tan_text`. Shapes (b), (c) and (d) are still
  open; read their care notes below before picking one.** Measured on this entry's own shape (a 9-panel
  mosaic of **5,477** synthetic solved subs, this box): `compute_mosaic_canvas` **6.02 s → 0.89 s** (6.8×) and
  `estimate_stack` — what `/stack-estimate` spends its time in — **6.04 s → 1.06 s** (5.7×), i.e.
  **0.94 ms a sub** removed, the whole `wcs_from_text` share this entry identified. The fast path is
  a hand-rolled 80-column card scan plus assignment onto a bare `WCS(naxis=2)`: **0.85 ms → 0.07 ms** a
  header, 12×. Both halves of the entry's diagnosis were confirmed on the way — `Header.fromstring` is
  **0.047 ms**, and the expensive half is `astropy.wcs.WCS()` *plus* every subsequent `key in header` lookup
  (a `Header` re-verifies cards on each one, which is why an "astropy `Header` + fast assignment" hybrid
  measured 0.47 ms and the raw card scan measures 0.07 ms). **It is a pure optimisation, and the tests are
  what say so:** the fast WCS must re-serialise **byte-identically** through `to_header(relax=True)`, record
  the same `pixel_shape` and transform a pixel grid to **bit-identical** RA/Dec, across ten header shapes
  (our own CDELT and CD serialisations, an ASTAP sidecar carrying CD *beside* CDELT+CROTA, the legacy
  CDELT+CROTA2 convention, half-written CD/PC matrices, a seam frame, a near-pole frame); and
  `test_mosaic.py` pins that the union canvas is identical with the fast path disabled. `CROTA` is **not**
  re-implemented — it is handed to wcslib via `wcs.crota`, exactly as the header path does. Anything the
  scan does not fully understand (SIP, `PV`, a non-TAN or galactic projection, a third axis, non-degree
  units, a duplicated keyword, a length that is not a whole number of cards) returns `None` and falls
  through to astropy's own read, so an unrecognised keyword can never be silently dropped.

  v0.374.8 took `mosaic.compute_mosaic_canvas` from 13.87 s to 4.75 s by vectorising the
  footprint transform. What is left is measured and is one thing: `wcs_from_text` costs **0.755 ms** a frame
  and is called once per sub, so **5,477 × 0.755 ms ≈ 4.1 s** of the remaining 4.75 s. It is not the parsing
  — `Header.fromstring` alone is **0.042 ms** — it is `astropy.wcs.WCS()` construction, which re-serialises
  and verifies the header (257,434 `Card._verify` calls across one canvas computation). `WCS(..., fix=False)`
  buys 4 %; `relax=False` buys 20 % and changes what keywords are accepted, so neither is the answer.
  **This matters because of where it runs:** the Stack page fires `/stack-estimate` **twice** and both queries
  carry the drizzle and canvas-mode options in their query key, so every toggle of those controls re-pays it,
  and `/rejection-outlook` runs on every Target-page load.
  **Four shapes — (a) and (b) touch the engine and need care; (c) and (d) are frontend-side and smaller:**
  ~~(a) *Fast construction.* Build the WCS by assigning `ctype`/`crval`/`crpix`/`cd` onto a bare `WCS(naxis=2)`
  — which is exactly what `mosaic.compute_mosaic_canvas` already does for the output canvas — for the headers
  **we ourselves wrote** (`wcs_to_text`), falling back to the full parse for anything carrying SIP, `PV`
  distortion, a non-TAN projection or extra axes. Needs the fallback to be conservative and a test that both
  paths agree on a real ASTAP sidecar, not only on a synthetic. Measure it before committing: if a bare
  `WCS(naxis=2)` plus assignment is not markedly cheaper than `WCS(header)`, this shape is worthless.~~ —
  **SHIPPED v0.374.9; the numbers are in the ▶ block above. One correction for the record: the entry framed
  it as "for the headers we ourselves wrote", but the gate that matters is the header's *shape*, not its
  author — an ASTAP sidecar is a plain TAN header too, and it is the one the owner's 5,477 subs actually
  carry, so gating on provenance would have bought nothing on real data.**
  **Read (b)–(d) with the new number, not the old one: the problem they were sized against is now ~1 s, not
  ~4.7 s.** A Stack-page load costs ~2.1 s of canvas work rather than ~9.3 s, and a κ-slider nudge ~1 s rather
  than ~4.7 s. None of them is wrong, but none is worth the staleness or API risk it carries at that size —
  **profile before picking one**, and expect to conclude that (b) in particular is no longer worth its trade.
  (b) *Memoise the canvas per target*, keyed on a frame-set fingerprint (count + max rowid + accept/solve
  state). Cheapest by far, but it is the staleness trade **v0.374.6 explicitly warned about** for the Library
  page — a stale canvas estimate after a scan is its own bug — so it needs the fingerprint to be genuinely
  complete, not "good enough".
  ~~**(c) is the smallest and was checked rather than guessed** — `Stack.tsx` runs two queries and they
  *do* legitimately differ (`stack-estimate` uses the user's current options; `stack-estimate-drizzle` asks a
  fixed `drizzle: true, scale 1.5` feasibility question, enabled only when drizzle is off and ≥200 frames are
  accepted). For the owner — thousands of subs, drizzle off by default — **both fire**, so the Stack page
  pays ~9.3 s on load. Folding them into one request that answers both sizings from **one** canvas
  computation halves that without touching the engine.~~ — **SHIPPED v0.376.1**
  (`stacker.StackCanvasBasis` + `estimate_stack_basis` / `estimate_stack_from_basis`, and
  `/stack-estimate`'s additive `drizzle_probe`). It *did* touch the engine, and that turned out to be the
  right place: the split makes "the canvas depends on `mosaic_canvas` alone" a thing the code states and a
  test enforces, rather than a fact a router has to remember. Measured on the entry's own shape (9-panel,
  **5,477** synthetic solved subs, this box): a Stack-page load's sizing work **2.18 s → 1.13 s**, and a
  second sizing off a held basis costs **44 µs**. Entry in [`SHIPPED.md`](SHIPPED.md).
  **(d), and the sharpest of the four:** the first query's key carries `sigma_kappa`, `sigma_clip`,
  `min_max_reject`, `min_max_reject_count` and `auto_reject` — **none of which affect the canvas**; only
  `drizzle*` and `mosaic_canvas` do. They are in the key because the same endpoint also answers
  `rejection_reach`. So nudging the κ slider re-pays a 4.7 s canvas computation purely to refresh a rejection
  note. Splitting the *rejection* answer out of `/stack-estimate` (or memoising the canvas half on the
  canvas-affecting options alone) would make those toggles instant and is independent of (a) and (b).

- **NEW IDEA (Builder 2026-08-06, MEASURED while auditing the stack path) — `detect_mixed_pointings` is a pure-Python
  O(n²) pair loop with no cap, so the mixed-pointing preflight grows quadratically with a target's sub count.**
  *(Performance — size S; **off-by-default setting, so this is a latency note, not a live problem**.)*
  `seestack/stack/pointings.py::detect_mixed_pointings` single-linkage-clusters every accepted+solved sub against
  every other one. The inner loop never short-circuits (a single tight target means *every* pair links), and
  `webapp/pipeline.py::_detect_mixed_pointings` passes the full frame list with **no cap** — unlike the frontend
  mirror (`frontend/src/components/target/mixedPointings.ts`), whose comment notes it is "bounded by the 2000-frame
  list cap". **Measured** (one tight cluster, the ordinary single-target case): 0.17 s at 1 000 subs, 0.70 s at
  2 000, 2.7 s at 4 000, **10.8 s at 8 000** — and 4× again per doubling, so the §1 owner's "thousands of subs"
  target is a tens-of-seconds stall inside a stack job. **Only reachable with `mixed_pointing_guard` on** (it is
  **off** by default), and it runs in a background job rather than an HTTP request, which is why this is filed as
  perf rather than a bug. **Care:** any speed-up must be **exactly** verdict-preserving (a grid/KD-tree prefilter
  is only exact if the neighbour radius is the chord `2·sin(d/2)`; naive cell-representative merging is *not*).
  Cheapest honest option is simply to vectorise the pair test in NumPy in blocks (same O(n²), ~100× the constant)
  or cap the input with a deterministic subsample — a cap changes the verdict, so it needs its own argument.
  **Gate:** only worth doing if the owner turns the guard on.
- Profile the stack hot path on a large synthetic target; find a safe win that
  doesn't touch memory bounds or correctness. (M)

### Infra / maintainability

- **NEW IDEA (Builder 2026-09-04, after losing three separate slots to it in one run) — when an entry ships,
  strike the "the half X deliberately did NOT build" follow-ons the same commit closed, not just the entry
  itself.** *(Pillar: maintainability in service of not wasting runs — size XS per sweep, and it is a **Scout**
  job. Confidence: measured on this run.)* Three entries this run were picked as open work, greped, and turned
  out to be fully on `main`: the loupe's **preview-space marker** (filed 09-03 as "the half v0.329.5
  deliberately did NOT build", shipped v0.329.6 *an hour later by the same run*), the Target page's
  **early-stop night marker** (filed 09-04, shipped v0.342.0), and **"the other two exports still made out of
  the 1024 px preview"** (both halves shipped — `SHARE_JPEG_MAX_LONG_EDGE` and `wallpaper_source_long_edge`).
  Two of the three were already correctly *indented* under their shipped parents and cost only a read; the
  third was a live top-level bullet and cost a full trace. **The pattern is specific enough to act on:** an
  entry of the form *"the half N deliberately did NOT build"* is the single likeliest thing the **next** run
  builds, and the run that builds it strikes the parent it was working from — not the follow-on it never
  read. **Shape:** when curating, for each newly-Shipped entry, grep the file for the sibling phrases
  ("deliberately left out", "deliberately did NOT build", "the half", "the other two") naming the same
  version, and strike or indent what that commit closed. **Do NOT** turn this into a code check: the
  relationship is editorial, and the existing "keep a shipped item's spec *indented*" convention already
  makes the answer visible by shape once someone applies it.

- **NEW IDEA (Builder 2026-09-03, spotted while adding the sibling channel in v0.328.2) — `EditContext.op_notes`
  is keyed by op **id** where its new sibling `fitted` is keyed by op **uid**, so a recipe carrying an op twice
  reports only the last one.** *(Pillar: editor correctness — PRIORITY 1; size XS; latent, low severity.)*
  `seestack/edit/ops/tone.py` writes `ctx.op_notes["tone.color_calibrate"] = {…}` and
  `seestack/edit/ops/detail.py` does the same for its advisories. A recipe is a *list*, and nothing stops two
  instances of one op with different params — at which point the editor's caption ("the saved picture's colour
  will differ a little from this preview", the deconv/star-reduce advisories) describes whichever ran last and
  silently discards the other. `fitted` was keyed by uid from the start for exactly this reason, and
  `EditContext` now carries `op_uid` through the pipeline, so the fix is available: key by uid and have the
  webapp layer resolve uid → op id when it builds the histogram payload. **Care:** the histogram endpoint's
  JSON shape is what the frontend reads (`color_cal`, `star_reduce_differs_on_proxy`, …) and per §9 must not
  change — so this is an internal re-key with the same payload out, not an API change. Worth confirming a
  double-op recipe is actually reachable from the UI before spending a run on it; if it is only reachable by
  hand-editing a recipe JSON, it stays an XS tidy-up rather than a bug.

- **NEW IDEA (Builder 2026-08-30, the shape the v0.311.1 bug had, and the reason it existed) — there are now
  **two** answers to "render this run's picture at size N, exactly as it is shown", and the bug was the gap
  between them.** *(Pillar: correctness by construction / maintainability — PRIORITY 3; size S; pure
  consolidation, no behaviour change intended.)* `stack._native_picture_source` (v0.310.0) knows the full list
  of ways a stored preview can differ from a fresh FITS render — a baked North-up turn, a display-space
  "Process target" edit, an auto-crop trim, a missing master — and **declines** when it can't reproduce the
  picture faithfully. `download_full_res_png` answers the same question independently: it handles the recipe
  and the saved `stretch`/`black`, silently didn't handle the baked turn (that was v0.311.1), and does not
  consider the crop at all. Two implementations of one question is exactly how the rotation went missing from
  one of them. **Shape:** one function — `run_picture_png(run, recipe_json, *, max_long_edge)` — that returns
  the render *and* what it could not reproduce, with `_native_picture_source` becoming "call it, and decline
  when it reports anything unreproduced" and the full-res endpoint becoming "call it, and serve what comes
  back". **Do it as a pure refactor with the existing tests as the gate** (`test_full_res_png.py`,
  `test_share_native_resolution.py`, `test_wallpaper.py` between them pin every branch), and check the **crop**
  case explicitly while there: a plain run should never carry a `preview_crop_json` (only the auto-edit writes
  one, and it sets `preview_display_space` too), but nothing asserts that, and if it can happen the full-res
  download is showing a differently-*framed* picture the same way it was showing a differently-rotated one.
  **↳ THE CROP HALF IS ANSWERED — a non-finding; don't re-trace it (Builder 2026-09-06).** Both writers of
  `preview_crop_json` set the display-space marker in the same block (`pipeline.py:3199` → `:3208`), and the
  North-up "Adjust → Save" endpoint refuses a non-display-space run with a 400 *before* it writes either — so
  the crop is fenced off where it could be created, unlike the rotation, which was simply forgotten in one of
  the two renderers. The remaining consolidation is a **pure refactor with no known defect behind it**; it was
  sized and deliberately not taken. Full working in [`PROCESS-NOTES.md`](PROCESS-NOTES.md), 2026-09-06.

- **PERF WATCH ITEM (Builder 2026-08-30, introduced knowingly by v0.310.0 / v0.311.0) — the wallpaper and the
  share JPEG are now real renders, and nothing caches them.** *(Size S if it ever bites; **do not build it on
  spec** — AGENTS.md §6 says optimise a *measured* hot spot.)* Both were a file read plus a re-encode; each is
  now a decimated FITS load and stretch (≤ 2560 px for a share, ≤ the device size for a wallpaper) on every
  request, and the browser has no way to revalidate — the responses carry no `ETag` or `Last-Modified`. A
  beginner tapping Share three times pays for three renders. The cheap fix if it is ever felt is a validator
  keyed on the master's `(mtime_ns, size)` plus the request's own parameters, exactly as
  `_zoom_clip_signature` already keys its cache; the expensive one is a stored derivative, which is what the
  "Process target" half of the same feature would need anyway. **Measure first:** on the owner's box the
  interesting number is a share tap on their largest mosaic, not a synthetic frame.

- **QA LEAD (Builder 2026-08-27, generalised from three fixes of the same bug in one run) — sweep every
  consumer of a run's *stored preview bytes* that derives geometry from the FITS.** *(Pillar: image quality /
  correctness — PRIORITY 4; size S to audit, unknown to fix; a good Scout run.)* Three separate surfaces shipped
  the identical mistake and each was found only because the previous fix made it obvious: the Sky-map overlay
  (alpha + tile placement, v0.288.1), History's object pins and scale bar (v0.289.2), and the share JPEG /
  wallpaper (filed as a verified bug at the top of "Bugs"). The shape is always the same — **the stored preview
  PNG is not necessarily the un-rotated FITS grid**, because History's "Adjust → North up → Save" can bake a
  rotation into it, and until v0.288.1 nothing recorded that. Anything that draws on those bytes, re-orients
  them, or builds a WCS/pixel coordinate for them from the master FITS is suspect. **The fact now exists**
  (`stack_runs.preview_north_up_deg`, exposed on `StackRunOut`), so the audit is mechanical: grep for readers of
  `run.preview_path` and for `celestial_wcs_from_fits`/`wcs_dict_rescaled_to_preview`/`stack_coverage_mask`/
  `wallpaper_target_pixel`/`objects_in_field`/`_scale_bar_from_wcs` used *alongside* a preview, and decide each
  site explicitly (follow the rotation, or refuse). A structural answer worth considering while sweeping: one
  helper that hands a caller "the geometry of the bytes you are about to draw on" (angle + size), so a future
  consumer can't silently assume the FITS grid again.

- **IDEA (Scout 2026-08-27 #21) — extract the shared "resolve frames → build mosaic canvas → drop
  gross-outlier subs" prologue that `estimate_stack` and `run_stack` each re-implement, so the two can't drift
  apart again.** *(Pillar: trust — the pre-run estimate should match the run; size S–M; pure refactor, no
  behaviour change.)* The cosmetic `estimate_stack` bug filed at the top of "Bugs" this run (the estimate not
  dropping `canvas.excluded_frame_ids` before counting frames) is a *symptom*: both functions independently
  pick the reference, call `compute_mosaic_canvas`, and decide the canvas — but only `run_stack` also removes
  the outliers, because the prologue is copy-pasted rather than shared. Factor the common prologue into one
  helper (`(frames, dst_shape, is_mosaic, ref_shape)` after outlier exclusion) that both call, so a future
  change to canvas/frame resolution lands in both by construction. Keep it a **pure refactor** with the
  existing tests as the guard, plus one new test asserting `estimate_stack` and `run_stack` agree on the frame
  count for a target with a gross-outlier sub (which also closes the filed bug). Do this only when already in
  `stacker.py` for something else — not worth a dedicated slot, but it retires a whole drift class.

- **NEW IDEA (Builder 2026-08-26, found the hard way while rendering the first montage) — one shared guard
  that burned-in text stays inside Pillow's built-in font's glyph coverage.** *(Pillar: friendliness / trust —
  PRIORITY 3. Size: S.)* Every server-rendered shareable — the recap poster, the deepening reel's frame
  labels, the nameplate, and now the montage — draws text with `ImageFont.load_default`, which has **no glyph
  for an em dash** (and none for a great many other characters we write freely in prose). It renders as a tofu
  box, on an image the user is about to post, and no test catches it: the string is correct, the *pixels* are
  wrong. The montage's title hit this on its first render and now avoids `—` by hand, with a local test —
  but `recap.py`'s lines, `deepening_frame_label`, and the nameplate all build strings from user data
  (target names!) with no such guard, and a target the owner named with a typographic dash would print a box
  today. **Shape:** a tiny `seestack/render/glyphs.py` with `safe_for_default_font(text) -> str` that
  transliterates the handful of characters this app actually produces (— – ‘ ’ “ ” … ×) to ASCII-safe
  equivalents, called at the one place each renderer draws text; plus a shared test that asserts every
  rendered-string helper's output survives it unchanged. **Care:** transliterate, never strip — a target
  named in a non-Latin script must still draw *something*, and dropping characters silently would be worse
  than a box. Small, additive, no behaviour change on any string that is already safe.

- **NEW IDEA (Builder 2026-08-15, filed the moment after a wall-clock test cost this run its first task) — a guard
  that no test may read the real clock, so a date-bomb can't quietly go red on a future date.**
  *(Pillar: infra / trust — PRIORITY 3 in effect, because a red baseline outranks everything an hour later; size S;
  test-only.)* This run opened on a **red frontend suite**: `Tonight.test.tsx` had hard-coded `"2026-08-15"` as
  "a future night", and 2026-08-15 arrived (fixed in v0.258.1). It was green in CI for weeks and would have gone
  red on a day nobody was looking — and it burns a whole Builder run's first task every time. **The class matters
  more than the instance:** a test that mixes a literal date with the *real* clock is deterministic today and
  broken later, and no amount of care at review time catches it. **Slice:** a meta-test that reads every
  `*.test.ts(x)` (and, on the Python side, every `tests/**/*.py`) and fails on an unannotated wall-clock read —
  `new Date()` with no argument, `Date.now()`, `datetime.now()`, `date.today()`, `utcnow()` — with an explicit
  opt-out comment (`// wall-clock: <why>`) for the handful of tests that legitimately need one (`futureNight()` in
  `Tonight.test.tsx` is exactly that case, and would carry the marker). Today the frontend has **one** such file
  and the Python date tests all inject `today=`/`now=`, so the guard lands green with a single annotation — which
  is the right time to add it. **Care:** grep-based guards rot into noise if they over-fire; scope it to test files
  only, keep the message explanatory ("a literal date + the real clock is a test that fails on a future date"), and
  prove it fires by mutation (add a wall-clock read, watch it fail) exactly as the `incoming/` guard does.

- **NOTE / WATCH ITEM (Builder 2026-08-13, left deliberately undone while shipping v0.254.0) — `routers/stats.py`
  still holds three hand-rolled `{sig, at, data}` caches now that a fourth moved to the shared
  `webapp/registry_cache.py`.** *(Infra — PRIORITY 3; size S; **do not do this on a hunch**.)* The library-progress
  roll-up now goes through `cached_for_registry`, but the "Your sky, so far" summary and two others still inline the
  same six lines. They were left alone on purpose: each keys on a **different** signature (the summary folds in each
  target's latest preview `stat`, which the shared `registry_signature` deliberately doesn't), so folding them in
  would mean either widening the shared signature for everyone or growing a parameterised key-builder — more
  machinery than three copies of six lines justify today. **Revisit if a fifth cache appears, or if one of the
  existing ones grows an invalidation rule** (the shared helper's `invalidate_registry_cache` is where that belongs).

- **NEW IDEA (Builder 2026-08-13, the sibling of the tooltip shipped in v0.254.0) — the Dashboard's "~2 more
  nights" badge has no hover explanation, unlike the planner's now does.** *(Friendliness — PRIORITY 3; size XS;
  frontend-only.)* `LibraryProgressCard`'s `ProgressRow` renders `nightsToGoLabel(r)` as a bare chip. The planner's
  equivalent now explains itself on hover (the readiness verdict plus the sentence naming the measured pace it
  divided by), and the same two sentences are already computable here — `r.readiness.verdict` is in hand and
  `clearNightsFromPace` returns the `text` alongside the count that `rankLibraryProgress` currently discards.
  **Lower value than it was on the planner, which is why it wasn't done in the same pass:** this card already prints
  "2.0 h of ~6h" inline on the row *and* the `finishFirstHint` sentence above it, so the chip is far better
  contextualised than a lone chip in a dense plan table. Worth one line if someone is in the file; not worth a trip.

- **NEW (Scout 2026-07-23) — remove or parity-pin the caller-less non-windowed `reproject_rgb` in `align.py` (latent
  CPU/GPU `cval` divergence).** *(Maintainability / latent-correctness; size S; from this run's align audit.)* The
  2026-07-23 adversarial align audit re-confirmed that the production stack uses only the **windowed** reproject path,
  where the CPU (`cval=NaN`) vs GPU (`cval=0`) boundary-fill difference is proven un-reachable by the
  `FRAME_EDGE_INSET_PX=3` interior-stencil argument. The **non-windowed** `reproject_rgb` is the one site that carries
  the exact-integer-boundary `valid` edge (`src_x <= w_src-1`, no inset) — and it has **no production caller**: the hot
  path uses `reproject_rgb_windowed` (`align.py:158`); the only user of the full-frame `reproject_rgb` (`align.py:286`)
  is `tests/test_windowed_stack.py:95`, purely as an *oracle* to prove the windowed path matches a full-frame
  reproject. Mild foot-gun: a future change that wired the full-frame version into production would bypass the windowed
  path's interior-stencil safety and lean on the edge boundary instead. **Fix directions (pick one — do NOT just delete
  it, the parity test depends on it):** (a) keep it but harden the two branches to identical fill semantics (both
  `cval=NaN` + valid-mask, mirroring the windowed path) and extend a CPU-vs-GPU parity assertion to this wrapper (the
  existing `tests/test_align_gpu_parity.py` covers the `_cpu`/`_gpu` kernels but not this wrapper's boundary handling);
  or (b) mark it explicitly test-only (underscore/rename + a docstring note) so nobody wires it into production by
  mistake. Either way documents intent and removes the latent divergence. Additive/safe (tightening an off-hot-path
  function + a test); no config/DB/API/on-disk/default change. Confidence: traced (no production caller +
  parity-hazard, not a live bug — the hot path never reaches it).
- **NEW (Scout 2026-07-21 #2) — `wcs_io.wcs_from_text` returns a *default* WCS instead of `None` for non-FITS
  garbage — a docstring/contract mismatch (cosmetic, unreachable with real data).** `io/wcs_io.py::wcs_from_text`
  (~L34) documents "Returns None on failure", but `astropy.io.fits.Header.fromstring` tolerates arbitrary garbage
  and yields a *valid-object* WCS with empty `ctype` / `crval [0, 0]`, so the None path never fires for malformed
  input. Harmless in practice — stored `wcs_json` is always machine-generated valid FITS (the garbage path is
  unreachable), and downstream `footprint_radec_deg` returns `None` for such an empty WCS anyway — so this is a
  contract/robustness tidy, not a live bug. **Fix (small):** after parsing, treat a WCS with no celestial ctype
  (or all-zero crval + no CD/CDELT) as a failure and return `None`, so the function honours its own docstring;
  add a unit test that non-FITS text → `None`. (XS, infra/robustness — very low priority; file only if a run is
  already in `wcs_io.py`.) Traced, unverified-as-user-impacting (correct-by-luck today).
- **NEW (Builder 2026-07-14) — consolidate the Dashboard's three per-project roll-ups into one cached pass
  (only with a measurement).** *(spotted shipping the v0.119.0 "Target progress" card.)* The Dashboard now
  triggers up to **three** independent passes that each open *every* project once: `/api/stats`'s stack
  roll-up (`_rollup_stacks` → `iter_stack_runs`), `/api/last-night` (`_collect_last_night` → `iter_frames`),
  and the new `/api/library-progress` (`_collect_progress` → the goal meta read). Each is separately cached
  (registry-signature + TTL), so steady-state a warm Dashboard is cheap — but a cold load (or a fresh scan
  that invalidates all three signatures at once) opens each project three times. A single combined roll-up
  that opens each project **once** and returns stacks + last-night + progress together would cut that to 1×.
  Gate on a real measurement (§3 / Performance) — on a small library the cost is negligible and the current
  separation keeps each endpoint independently cacheable and testable, so this is only worth it if a large
  library shows a real cold-load cost. Additive refactor, no behaviour change. (M, infra/perf — low priority.)
- **Low-priority (editor/consistency, spotted shipping v0.93.1): the bulk "Set all suggested
  values" button still uses the *raw-proxy* denoise strength.** Now that the per-op denoise
  "From your image" button is recipe-aware (v0.93.1), the bulk apply (`dataDrivenDefaults`, driven
  by the eager recipe-independent `denoise` query) can set a denoise strength that differs from what
  the per-op button suggests once a linear gradient/colour op precedes denoise. Defensible as-is —
  bulk apply is a from-scratch "quick start from your data" convenience and the raw stack noise is a
  reasonable seed there — so this is a consistency nicety, not a bug. Only worth aligning if a future
  run is already in that button's wiring. (S, editor/consistency)
- Chip away at the ~127 pre-existing `ruff check .` findings (don't add new ones);
  consider wiring ruff into CI once the count is low. (L, correctness/maintainability)
- **Scout to vet: two latent (not-yet-active) robustness traps flagged by the 2026-07-10 engine audit
  that shipped the v0.103.2 drizzle-reject fix — filed, not blind-fixed, because neither is traceable
  to a concrete wrong result *today*.** (S each, correctness/robustness)
  ~~(1) `seestack/edit/ops/background.py` `_subtract`/`_final_gradient` re-raise a `RuntimeError` when their
  errors collector is non-empty … the *per-frame* `bg/per_frame.py::_subtract_background_cpu` path uses a fixed
  `exclude_percentile=80` with **no** ladder.~~ — **FIXED v0.103.3** (Builder 2026-07-10; reproduced
  end-to-end before fixing, then vetted per the note). Trap (1) *is* reachable: a **sparse mosaic proxy** —
  a covered strip that's <20% of its bounding canvas, the rest uncovered NaN — makes the object mask
  (`| ~finite`) cover >80% of every box, so the strict `exclude_percentile=80` fit raises and the editor's
  `background.subtract` op **hard-failed** ("background fit failed: All boxes contain <= … unmasked or finite
  pixels") while its sibling `final_gradient` (which got the ladder in v0.89.2) degraded fine — a real
  editor inconsistency, not just the dense-field case. (The per-frame **box clamp** already prevents the
  *too-few-boxes* failure on any real ≥1080 px frame; it does **not** prevent this *too-much-masked* one.)
  `_subtract_background_cpu` now fits through the same `exclude_percentile` ladder (80 → 95 → 100, then a
  half-size box) via a new `_fit_bg2d_ladder` helper mirroring `final_gradient._fit_background_2d`. The
  strict 80 stays the first rung, so a normal frame's result is byte-for-byte unchanged (covers per-channel
  *and* luminance mode, and the stack path — which merely stopped silently skipping every channel). Regression
  tests `tests/test_bg_modes.py::test_sparse_mosaic_canvas_degrades_instead_of_failing` (asserts the strict-80
  fit really raises, then that the op surfaces no error and flattens the covered strip while preserving NaN)
  + `test_ladder_first_rung_matches_strict_fit` (byte-for-byte parity on a normal frame). Additive,
  upgrade-safe (no config/DB/API/on-disk change).
  ~~**(2)** `seestack/calibrate/apply.py::apply_raw` returns the
  *caller's own* float32 array when `is_empty` (no masters apply) — `asarray(...).astype(copy=False)` is a
  no-op, so the documented "returns a new array" contract is violated by aliasing.~~ — **FIXED v0.121.5**
  (Builder 2026-07-14, branch `claude/pensive-faraday-irqhx4`; regression-tested). `apply_raw` now copies at
  the return **only when the result would alias `raw`** (`if result is raw: result = result.copy()`) — the
  otherwise-aliasing empty-bundle-on-float32 path. Any applied master already yields a fresh array (subtraction/
  division), so `result is raw` is False on every real calibration path and no hot-path double-copy is taken;
  the stacker also sets `calibration = None` when `is_empty` so the empty branch is off the stack hot path
  entirely. Closes the latent contract violation so a future in-place consumer can never corrupt a shared source
  frame. Regression tests `tests/test_calibrate.py::test_apply_raw_empty_bundle_returns_a_fresh_array`
  (fails-before: `out is raw`; passes-after: distinct buffer, mutating the result leaves the input untouched)
  and `test_apply_raw_with_masters_does_not_double_copy` (a master path still returns a fresh, correct array).
  Additive, upgrade-safe (no config/DB/API/on-disk change).
- **Scout to vet: four low-severity latent gaps flagged by a fresh three-front stacking-engine audit
  (Builder 2026-07-16) — filed, not blind-fixed, because none is triggerable by real inputs today.** The audit
  swept `stack/stacker.py` + `stack/align.py`, `stack/drizzle_path.py` + `stack/mosaic.py`, and
  `calibrate/apply.py` + `calibrate/masters.py`; the hot paths (weighted-sum / Welford / min-max accumulation,
  σ-clip keep-mask polarity + NaN-widened tolerance, photometric multiply, reproject valid-mask insetting,
  drizzle super-res WCS scaling + two-pass clip statistics, dark/bias pedestal selection + exposure scaling,
  flat normalization + floor, sigma-clip master combine) all verified **correct and NaN/coverage-aware** — no
  pixel- or coverage-corrupting bug found. The four latent observations, each low-confidence-of-reachability:
  (S each, correctness/robustness — focus #1)
  - ~~**(1)** `calibrate/masters.py:203-205` — the `median` and `mean` master-combine methods use plain
    `np.median`/`np.mean`, **not** NaN-aware, unlike the `sigma_mean` sibling (`nanmedian`) and the flat path.
    A single NaN/inf pixel in an input frame would silently propagate into the master (and thence every
    calibrated light at that pixel).~~ — **FIXED v0.134.2** (Builder 2026-07-16, branch
    `claude/pensive-faraday-h477bm`; regression-tested). Judged **more than churn**: the combine sits on the
    calibration data-integrity path (focus #1) and the input is a *user-supplied* file, so it is not strictly
    "not triggerable" — a float FITS calibration frame carrying a NaN/inf pixel (an exported master re-used as
    an input, a partially-corrupt file) does reach `np.stack` and, for `mean`, a single NaN at a pixel poisons
    that pixel in the master → every calibrated light. **Fix:** mask any non-finite sample to NaN once
    (`finite_stack = np.where(np.isfinite(stack), stack, np.nan)` — handles inf too, which `nanmean` alone does
    not) and run all three methods over it (`nanmedian`/`nanmean`; `_sigma_clip_mean` now also gets the masked
    stack and its `full_med` fallback uses `nanmedian`), so a non-finite sample is ignored and the finite ones
    still combine, matching the engine's "NaN = no data" invariant. An all-non-finite pixel stays NaN =
    genuinely no data. **Byte-for-byte identical on every real integer-readout calibration set** (`np.isfinite`
    is all-True there, so the mask is a no-op). Additive, upgrade-safe (no config/DB/API/on-disk change).
    Regressions in `tests/test_calibrate.py`: `test_build_master_is_nan_aware` (parametrised over
    median/mean/sigma_mean — a NaN + an inf pixel in one input frame no longer poison the master;
    fail-before under mean/median) and `test_build_master_all_nan_pixel_stays_nan` (an all-non-finite pixel
    stays NaN, not folded to 0). Severity: data-integrity on a non-finite user input (low reachability).
  - **(2)** `stack/drizzle_path.py:300-303` — `frame_coverage` (`self._count`) is derived from **channel-0's**
    `out_wht` only, while the finite-mask and clip-reject masks are computed per channel; a pixel kept in
    channels 1/2 but NaN/clip-rejected in channel 0 is undercounted. **Diagnostic-only** (`coverage_min`/
    `coverage_max` "frames per pixel"), never the image or the weight maps — and consistent with
    `WeightedSumAccumulator`'s own `valid[..., 0]` count. Same disposition as the accumulator's documented
    channel-0 count.
    **⚠ Justification is now STALE (Builder 2026-08-04, spotted in a stacking-engine read):** the
    "consistent with `WeightedSumAccumulator`" half no longer holds — that accumulator was since changed to count a
    frame when it contributed to **any** channel (`valid.any(axis=2)`, `accumulator.py`), precisely so per-channel
    κ-σ rejection can't understate coverage. `drizzle_path.py`'s `frame_coverage` still reads channel 0 only, so
    the drizzle and standard paths now report "frames per pixel" by **different rules**. Still diagnostic-only
    (never the image or the weight maps), so the severity is unchanged and this is not worth a run on its own —
    but if anyone is already in `drizzle_path.py`, make it `any`-channel in the same commit and the two paths agree
    again. Confidence: traced (both call sites read).
    **⚠ STRIKE — already done (Builder 2026-08-06, re-read of `drizzle_path.py`).** `add_frame` now ORs each
    channel's strict post-add `out_wht` increase into one `deposited` plane (`deposited |= ...` over `c in
    range(3)`) before `self._count += deposited`, and the `frame_coverage` docstring says so. The two paths
    already agree on the `any`-channel rule; nothing left to do here.
  - ~~**(3)** `stack/align.py:407,466,161` — `_apply_subpixel_shift_windowed` shifts a window padded only `pad=2`
    px while the sub-pixel correction is capped at ±5 px, so a frame legitimately needing a 3–5 px shift can
    lose a thin strip of real edge data (coverage reduction at frame edges, **not** wrong pixel values).~~
    — **FIXED v0.135.3** (Builder 2026-07-16, branch `claude/pensive-faraday-5rsa35`; regression-tested).
    Took the filed remedy ("widen the window pad to ≥ the shift cap"). The ±5 px cap is now a named module
    constant `SUBPIXEL_SHIFT_CAP_PX = 5` (used by both `_apply_subpixel_shift` and `_apply_subpixel_shift_windowed`
    in place of the two magic `5.0` literals), and `reproject_rgb_windowed` gained a `pad` parameter (default 2,
    threaded to `_footprint_bbox_on_canvas`). `align_one` computes `will_refine` once and, when a sub-pixel
    refine will actually run (`subpixel_refine` **and** a ref patch is present), reprojects the window with
    `pad=SUBPIXEL_SHIFT_CAP_PX` instead of 2 — so a shift up to the cap only *translates* the footprint inside
    the (uncovered/NaN) pad border rather than pushing its trailing rows off the window edge. When refinement
    won't run, the pad stays 2, so the default install (`subpixel_refine` off) is **byte-for-byte unchanged**
    (window size, origin, and pixels identical). Additive, upgrade-safe: no config/DB/API-shape/default change,
    off the memory-bounded concern (a 3-px-wider window is a handful of NaN pixels). Regressions in
    `tests/test_subpixel_align.py`: `test_reproject_windowed_honours_pad` (the pad param widens the window +6 px
    each dim, moves the origin out 3 px, and the extra border is NaN), `test_align_one_widens_the_window_when_refining`
    (drives the real `align_one` end-to-end: refine-active window is +6 px each dim vs the plain window —
    fail-before both were pad=2 so identical), and `test_windowed_refine_pad_preserves_trailing_edge_coverage`
    (a ~4 px shift clips the footprint's trailing bright band off a 2-px-padded window but preserves it on a
    5-px-padded one). Severity: coverage loss at frame edges (image-quality/data-integrity), only with the
    off-by-default refine on and near-cap shifts, well-mitigated in a dithered stack. Confidence: reproduced
    (via the windowed-shift repro) + fixed. Latent gap (4) (test-only CPU↔GPU `cval` at `inset=0`) left as
    informational — the production windowed path never samples out-of-bounds inside the valid region.
  - **(4)** `stack/align.py:261` / non-windowed `reproject_rgb` — a CPU(`cval=nan`)↔GPU(`cval=0.0`) boundary-pixel
    discrepancy at `inset=0`. **Test-only path** (`reproject_rgb`/`_apply_subpixel_shift` are exercised only by
    `tests/`); the production windowed path uses `inset=3` and never samples out-of-bounds inside the valid
    region. Informational.
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
### The owner's one-sitting list (consolidated 2026-09-08 — every gate in this file, in one place)

> ## ✅ OWNER ANSWERED FOUR OF THESE — 2026-09-08. Read before picking anything from the list below.
>
> **Q1 — Auto-edit the walk-away picture too? → YES, _with a condition_.** The owner's words:
> *"yes, but should be easy to override with manual settings."* So `auto_edit_on_autostack` may default
> **on** once its prerequisites have shipped — **but the override is part of the feature, not a follow-up.**
> Do not ship the default flip without it. Concretely, before it goes on: a plainly-labelled Settings switch
> that turns it off; a per-target way to opt out that survives the next night (the walk-away chain must
> honour a target's saved preference, the way `_stack_target` already honours saved stack options); and a
> saved/edited recipe must **never** be overwritten by the unattended pass. The owner has been bitten by
> an on-by-default reframing before (the v0.226.0 auto-crop), so the switch must be findable **before** the
> first surprise, not after — name it in the Settings copy alongside Auto-stack's three guards.
>
> **Q3 — "Do you still see a multicolour grid?" → CANNOT ANSWER YET: he has not deployed.** He is running a
> build older than the mosaic/colour fixes. **Do not treat silence as "clean" and do not close the colour-chain
> bisect** — it stays gated, and the question gets re-asked after he next deploys. Anything that claims the
> colour chain is verified on his real data is claiming something nobody has checked.
>
> **Q4 (list item 15) — Dependencies and network → RESOLVED, PERMANENTLY: the app stays LOCAL.** Owner:
> *"let's stick with it being local."* **This is now a standing rule in `AGENTS.md` §1 Owner Facts, not a
> gate** — stop asking. Declined outright: outbound weather for Tonight, SIMBAD identification from the
> webapp, satellite-pass forecasts, a StarNet-class model, and anything needing a periodic data refresh.
> **Strike those entries rather than leaving them gated** — a gated entry invites a future run to re-ask a
> settled question. Bundled offline data remains fine. **Not settled by this:** `astroalign` for the
> WCS-free fallback, which is an offline *dependency* question and still needs its own sign-off per §10.
>
> **Q5 (list item 9) — Skip folders named `batch_stack_tmp` at scan time? → YES, skip.** This is the stray
> folder from the owner's real `\\TRUENAS\astro` listing — another program's scratch directory, confirmed
> not created by this app. Implement it as the **name-pattern skip the earlier entry deliberately did not
> blind-add** (`classify_seestar_junk_target` already grew a `temp_folder` verdict in v0.319.6 for the
> *cleanup* side; this is the *scan-time* half). Keep it conservative and evidence-based: skip the folder,
> say so in the scan's skipped-folders report (v0.381.0 already surfaces those on the Library page with a
> one-click "bring it in"), and make it recoverable — the owner must be able to ingest it anyway if a future
> folder happens to share the name.
>
> **Still unanswered and still worth asking** (unchanged below): the Settings → Maintenance screenshot,
> which alone unblocks three image-quality gates (list item 5) — it was asked in a way the owner found
> unclear, so **re-ask it plainly: "open Settings → Maintenance and screenshot the two self-check lines"**,
> and note it only carries information after a week or so of Process runs.

> Everything below is waiting on **one** thing only the owner can supply: a decision, a screenshot, a
> command's output, or a folder name. He has answered every gate put to him so far (a folder listing, an
> `ffprobe`, two decisions); the constraint was that they were scattered. Answer in any order; each answer
> unblocks the named entry. Ranked by what the answer is worth. *(Curated by the backlog-readiness run; a
> Scout keeps this list current — when a gate is answered, move the answer into the entry and strike the row.)*

1. ~~**Auto-edit the walk-away picture too?**~~ — **ANSWERED YES 2026-09-08 and SHIPPED in v0.395.0,
   with the condition, not after it.** `auto_edit_on_autostack` defaults **on** for fresh installs (an
   existing `config.json` keeps its stored value, per §9 — so this is item 2's sibling: the owner flips his
   own switch). The condition ships in the same commit: a per-target override stored in `project_meta`
   (`webapp/auto_edit_pref`) that the unattended pass honours and that survives the night, offered as a link
   under any picture the app finished; a guard that never writes over a saved recipe; and Settings copy that
   names every way out. Nothing left to ask.
2. **Flip Auto-stack on yourself — the default flip has now shipped (v0.391.0), and as of v0.404.0 the app
   *asks* you to.** The Dashboard's notice board now carries "Your subs came in, but nothing was stacked"
   with a one-click **Turn on auto-stack** button, on any night it captured and stacked nothing — so this no
   longer depends on the owner reading this list. It is still his click to make; the row stays until he makes
   it. Settings → "Auto-stack".
   A *new* install gets it on; yours cannot, because `state/config.json` carries an explicit
   `"auto_stack": false` that no upgrade may overwrite (the file cannot tell a value you set from a value the
   app dumped, so flipping it would be the AGENTS.md §9 breach). This is a one-click job and nothing else is
   waiting on it. Worth: the whole walk-away path. *(The one item under "REQUIRES MANUAL OWNER ACTION".)*
3. **Do you still see a multicolour grid on any mosaic on a current build?** The v0.225.0 fix rated its own
   root cause "medium confidence as the *sole* contributor". **Answer:** yes/no, and the target's name.
   Unblocks: "bisect the rest of the v0.158→v0.220 colour chain" under "Bugs". Worth: closes or reopens the
   oldest mosaic complaint.
4. **One real solved sub's `.wcs` sidecar, or the `wcs_json` of any solved frame.** Unblocks the sky-atlas
   `CROTA2 → CD` sign check under "Bugs" (fallback path only; low impact). **Command:** on the NAS,
   `sqlite3 <library>/targets/<any target>/project.sqlite "select wcs_json from frames where wcs_json is not
   null limit 1"`, or paste one ASTAP `.wcs` file. Worth: one sign flip, or one entry closed.
5. **Settings → Maintenance: a screenshot of the two self-check lines** (the Auto colour self-check,
   v0.36x, and the highlight line, v0.382.0) after a week of Process runs. Unblocks *three* real-data gates
   at once: "does Auto's SCNR tint a neutral background magenta?", "Hold back highlights is near a no-op
   on the frames that need it", and the "How's my stack?" highlight-clip cue — all under "Image quality".
   Worth: the three oldest image-quality deferrals, answered from numbers the app already collects.
6. **Your M42 (or M31) stack, or a screenshot of its core in the editor with "Hold back highlights" at
   max.** Unblocks the highlight-knee redesign ("Image quality", the v0.240.0 measurement). Worth: blown cores
   on the brightest targets a beginner shoots first.
7. **On a cloudy night, does the "locating" stage run unreasonably long?** ASTAP's 3-rung ladder can spend
   3× `astap_timeout_s` per unsolvable sub. **Question:** *would you trade fewer rescue attempts on hard
   frames for a hard per-frame time limit (yes/no)?* Unblocks the ladder-budget half under "Bugs".
8. **Have you ever seen new subs sit un-ingested until you pressed Scan?** Unblocks the watcher clock-skew
   hardening note under "Bugs" (a NAS clock ahead of the app's). **Answer:** yes/no.
9. ~~**Skip folders named `batch_stack_tmp` at scan time?**~~ — **ANSWERED YES 2026-09-08 and SHIPPED in
   v0.393.0.** The scanner skips it, the skipped-folders report says so in its own words, and the report's
   "bring it in" still ingests it — the owner's condition. Nothing left to ask.
10. **The mixed-pointing guard (`mixed_pointing_guard`, off): do you want it on?** Unblocks the O(n²)
    preflight speed-up under "Performance", which only matters if the guard runs. **Answer:** yes/no.
11. **A target with an edge-on galaxy or a bright elongated nebula (NGC 891, NGC 4565, M82), and whether
    any of its subs were flagged "streak".** Unblocks the per-frame trail-vs-object detector under "Image
    quality" (needs real data to tune). **Command:** the target's Frames table filtered to "rejected" —
    a screenshot is enough.
12. **A faint target ASTAP struggles with** (the "only N of M located" case) — its name, and a yes/no to
    trying the off-by-default `astap_bootstrap_solve` on it. Unblocks "validate the stack-then-solve
    bootstrap on real faint-field data" and "Try harder to locate these" under "Autonomy". Worth: the #1
    thin-stack complaint, answered on real subs.
13. **A heavy-nebulosity stack (North America, Rosette).** Unblocks the SExtractor skew-guard confidence
    check under "Image quality" — a log read, no code change unless it fails.
14. **Three yes/no's on residue from shipped features:** a 9:16 portrait zoom clip for Reels/Shorts? A
    noise-delta *picture* beside the "Did it get better?" sentence? Auto-*apply* the classified object
    preset instead of offering it as a chip? Each is small; none is built until wanted.
15. **Dependencies and network (sign-off, below this list):** an outbound weather lookup for Tonight; a
    SIMBAD lookup for target identification; a StarNet-class model; satellite-pass forecasts; a
    star-registration package (astroalign) for the WCS-free fallback. Each is a yes/no plus "is outbound
    allowed on the NAS?".

- **Satellite/aircraft-trail forecast for the Tonight planner (opt-in; needs a data source).** *(Pillar:
  plan + understand — would be a genuine beginner feature: "the trails in your subs weren't a mistake — three
  Starlink passes crossed this field between 21:40–22:10; the stack's rejection removed them." Scout 2026-09-01,
  verified absent from the backlog and code.)* A beginner shooting near a Starlink train sees streaks and
  assumes their gear or their stacking is broken; naming the cause turns a worry into a "the app handled it"
  moment, and (plan side) could steer a session away from the worst pass windows. **Why it's here and not in
  Ideas:** predicting passes needs current orbital elements (TLEs from CelesTrak/Space-Track), i.e. a
  **networked dependency and a periodic data refresh** — exactly what §9/§10 say an agent must not add on its
  own. It also risks staleness/liability if the ephemeris is old. If the owner wants it, the safe shape is: a
  bundled/opt-in TLE fetch behind an explicit setting (off by default), a cache with an honest "elements are N
  days old" disclosure, and a plain-language post-hoc note on a finished stack ("N bright passes crossed this
  field during your session") rather than a real-time overlay. File the network-policy check and refresh cadence
  before building.
- AI star removal (StarNet-class ONNX): high wow-factor but adds a heavy ML
  runtime + model download that may hit the network policy. Needs an explicit OK.
- Anything that exposes the app publicly, changes auth defaults (e.g. turning auth
  on by default), or is otherwise hard to reverse.
- Live capture / real-time Seestar streaming integrations (explicitly de-scoped).
- **Surface SIMBAD target identification in the headless webapp (opt-in).** The engine
  already has `seestack/post/target_id.py` (`identify_target` → name + friendly object type +
  bg-flatten hint from a target's median plate-solved RA/Dec), but it is **GUI-only** — the
  headless webapp never calls it, so a beginner on the web app never learns "you're imaging
  M42, an emission nebula → use luminance background flatten." Wiring it into the Target page
  (show the identified object + friendly type, and pre-select the bg-mode hint / feed the
  existing "nudge luminance for extended-emission" Stack-form idea) would directly serve
  autonomy + friendliness + image quality. **Why sign-off, not a free build:** it makes an
  **outward network call** from the live install to CDS/SIMBAD (via `astroquery`), which is an
  outward-facing change the owner must OK against the deployment's network policy (guardrail
  §10). If approved it should be **opt-in / off by default** with a cached result per target,
  never blocking the pipeline. (S–M, autonomy/friendliness/image-quality — owner: OK to let the
  server query SIMBAD?)

_(Normal, tested changes merge to the default branch automatically — see
AGENTS.md §8. Only the items above need a human's OK first.)_

---

## Shipped
_Newest first. One line each: what + commit/PR. Entries that had grown to paragraphs were cut to one line on
2026-09-08; their full text is in [`SHIPPED.md`](SHIPPED.md) under that date's heading — search the version._
- **v0.417.0** — ⭐ 🔴 PRIORITY 1, the **remaining two halves** of the fourth external audit's "owner hits this first" entry, closing it: the same over-trim note on the **Target page** (`OverTrimmedTargetNote`) and the **library-wide count on the Dashboard** (`OverTrimmedNote` over a new `GET /api/over-trimmed-pictures`), so the question "*which* of my pictures is this?" has an answer without opening every target. Both read one server-side verdict — new `webapp/stale_crop.py` + `…/editor/crop-health`, factored through `editor.crop_health_for_run` so the scan and the per-run answer cannot name different pictures — and that verdict adopts the editor's shipped rule verbatim (`STALE_CROP_KEEP_RATIO` 0.25, silent when the border rule proposes no trim), with a drift test grepping `mosaicTrim.OVER_TRIM_KEEP_RATIO` so the two copies can't diverge. `sharePctLabel` is now shared, so all three surfaces round one measurement the same way. Read-only throughout: a saved recipe is never rewritten. Tests +27. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.416.0** — ⭐ 🔴 PRIORITY 1 (the editor), the **editor half** of the fourth external audit's "owner hits this first" entry, filed the same day and reproduced in the shipped image: **a mosaic Auto-edited before the D1 fixes keeps the old over-trim in its *saved recipe*, and every surface shows the sliver.** The fixes re-derive the trim; nothing compared a stored crop against it. New `mosaicTrim.overTrimmedVerdict` weighs the recipe's live enabled crops (`cropCoverageFraction`) against the rectangle `/editor/trim-suggestion` already fetches, and under `OVER_TRIM_KEEP_RATIO` (0.25) of what the canvas offers says so — *"cropped down to about 3% of the stack, but about 92% of it is well covered"* — with **Re-trim border**, which is the existing trim *preview*, so the user sees the rectangle before `applyTrimCrop` replaces only the Crop op. Where the stored "what Auto did" note is on screen the Alert also says its trim figure describes the crop being replaced, closing the gap between two sentences a beginner reads together. A quarter rather than the entry's suggested half, because at 0.5 a deliberate crop to the middle 40 % of a mosaic gets accused while the measured case is 3.4 % against 92.4 %. Frontend-only, no new endpoint and no new request; the Target-page note and the Dashboard library-wide count stay open on the entry. Tests +9, two fail before. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.415.1** — PRIORITY 4 (image quality, on the mosaic path that is on by default), a bug verified by reproduction and fixed in one run: **a mosaic panel that nothing could measure was dimmed anyway.** `overlapgain`'s own module docstring promises *"a panel that loses every pair keeps 1.0"*; `_solve_log_scales` ended with `solution - np.median(solution)`, and `lstsq`'s minimum-norm 0 for an unpaired panel only *means* 1.0 while that median is itself 0. Minimum-norm zeroes each connected component's **sum**, not its median, so a lopsided graph (three panels each reading 1.2× against a fourth, plus one sharing nothing) put the unpaired panel at **0.9554** — a 4.5 % dimming of a whole tile from an overlap that does not exist. Reachable on a star-poor overlap strip, i.e. the faint-field case. New `overlapgain._normalise` centres only the panels carrying a *surviving* pair (read at the point the fit is accepted, since the drop-and-refit loop can strand a panel that started out paired) and pins the rest to exactly 1.0. A fully-measured mosaic is byte-for-byte unchanged, pinned at `atol=0, rtol=0`. The existing `test_a_lone_panel_is_left_at_one_rather_than_dragged_along` passed throughout — its single symmetric pair makes the whole-solution median 0 by coincidence — and is kept, with the new test beside it saying what it cannot. Tests +2, one fails before. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.415.0** — PRIORITY 2/4 (autonomy + image quality), a bug verified and fixed in one run: **the walk-away minimum-frames floor counted a mosaic's subs, not its depth.** `auto_stack_min_frames` exists to stop the hands-off scan publishing single-frame colour speckle, and asked the question of the target's *frame count* — right on a single field, wrong on a mosaic, where a 3×3 one pass in has nine subs and a picture one sub deep everywhere, so `9 >= 3` waved it through on exactly the canvases the owner shoots. New `stacker.panel_frame_counts` + `typical_panel_depth` (the **frame-weighted** median panel depth — stray-proof, and it does not strand a mosaic for one thin corner the way the thinnest panel would); the hold reuses the existing `auto_stack_held_thin` discipline (no attempt marker, self-clearing) and `auto_stack_min_frames = 1` stays the opt-out. Plus the three sentences that would then have argued with their own numbers — Jobs, the Dashboard's overnight digest, and the Target page, which could not see this hold at all until the new read-only `GET /api/targets/{safe}/autostack-thin-hold`. Single field byte-for-byte unchanged. Full entry in [`SHIPPED.md`](SHIPPED.md). Tests +30, three fail before.
- **v0.414.2** — 🐛 VERIFIED BUG (upgrade-safety, AGENTS.md §9 "the container still builds and boots"; Builder-reproduced 14 times by accident this run): **the app refused to boot over a missing *frontend*.** `main._mount_spa` read "is the frontend built?" off `STATIC_DIR.exists()` — the *directory* — then mounted `static/assets` unconditionally, and `StaticFiles` raises in its constructor when the directory is absent. So an **empty** `webapp/static/` took the "built" branch and raised out of `create_app()`: no API, no Settings page, no job queue, over a missing frontend the placeholder branch one line above already knows how to survive. Reachable because `vite build` sets `emptyOutDir` on `../webapp/static`, so **every build deletes that tree before writing it** — an interrupted build, a half-copied image layer, or (here) a pytest session overlapping one. Fixed by testing `index.html` rather than the directory, and mounting `/assets` only when it is there — nothing is lost, since the SPA catch-all already serves any file under the static root with the same resolved-path confinement. A complete build is served byte-for-byte as before. No config, schema, on-disk, endpoint, response-shape or default change. Tests +6, five fail before. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.414.1** — FRIENDLINESS (PRIORITY 3, the ninth slice of the phone-invisible-Tooltip entry — the one *interactive* site the measurement said was worth doing): **asking what "Save as defaults" does no longer saves your defaults.** Its `<Tooltip>` wrapped the button, and its sentence is the only place the app says the button also drives *auto-stacking for this target* — so on a phone the one gesture available for "what does this do?" performed the persistent save. Now a `HintIcon` beside the button; label, action and accessible name untouched, hover unchanged. Frontend-only. Tests +1, fails before by saving. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.414.0** — FRIENDLINESS (PRIORITY 3, the eighth slice — the "still open" remainder of v0.413.0–2's own list, **shipped after a collision in which the other Builder's `HintAnchor` landed first and mine was dropped**; see `PROCESS-NOTES.md`, collision #14): **the last chips whose meaning a phone could not ask for** — `NightsCard` ×3, `Calibration` ×2, `BestPictures` ×2, `Gallery` ×1, converted to `HintAnchor` one line each, with `NightsCard`'s verdict badge skipping the anchor entirely when it has no sentence rather than passing `disabled` (an anchor makes its child a tab stop with `role="button"`). **Plus the durable half: a drift guard.** `hintAnchorDrift.test.ts` reads every non-test `.tsx` through `import.meta.glob` and fails if any `<Tooltip>`'s first child is a `<Badge>` — eight sweeps have each fixed the sites of the day and nothing stopped the next being written the old way, which is exactly how the badges survived four of them. Proven armed against a synthetic bad site *and* proven to have walked the tree. Frontend-only; `tsconfig.json` gains `"vite/client"` so the guard is typed. Tests +3. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.413.2** — PRIORITY 1/3 (the editor and the Target page), the seventh slice of the same entry and the one that carries a **bug**: **asking what "slower preview" means no longer adds the slow op.** `SlowPreviewChip` renders *inside* the Add menu's `Menu.Item`, so on a phone the only gesture for "what does this mean?" added the very op being warned about — the v0.402.1 defect one level out, and the same shape in `OpList`'s three row chips, where the tap selected the op. New opt-in `stopPropagation` on `HintAnchor` (off by default: swallowing a click a page expects is the worse failure). Also the Target page's `N integration` / **`N streaked`** / **`N trailed`** badges, each of which sits beside a bulk-reject button while what a streak *is* — and that Auto outlier removal keeps the frame — was hover-only. Eight sites. The frames table's column headings and the per-frame `Rejected — …` badge are deliberately left (the heading's tap *sorts*, and `FrameColumnGuide` already gives those sentences a reachable home; the reject badge's tooltip repeats its own text). Frontend-only; no config, schema, on-disk, endpoint, response-shape or default change. Tests +3, two fail before.
- **v0.413.1** — PRIORITY 3 (friendliness), the sixth slice of the same entry and the one that reaches the **most phone-critical page in the app**: **the Tonight page's planning verdicts now answer a tap.** You read Tonight standing next to the scope, in the dark, on a phone — and its score badge and four per-target chips (`readyHint`, `difficultyRowBadge`, `framingRowBadge`, `recentreNudgeRowBadge`) each printed a two-word verdict whose *reason* opened on `mouseenter` and on nothing else. Nine sites through `HintAnchor`: `routes/Tonight.tsx` ×5, `SuggestTargetsCard` ×2 (the Dashboard's copy of the same chips), `ContinueTonightCard`'s re-centre nudge, and `NextSessionCard`'s window line — whose hint is the honest **UTC** anchor behind the local wall-clock it prints, the same one its `.ics` carries. Four now-wrong "shown on hover" comments in `components/nextSession.ts` refreshed with it. Frontend-only; no config, schema, on-disk, endpoint, response-shape or default change. Tests +2, both fail before.
- **v0.413.0** — PRIORITY 3 (friendliness on the device the owner reads this app on), the fifth slice of the "a Tooltip is invisible on a phone" entry and the first to take its *other* half: **a stack card's verdict chips now explain themselves on a tap, not only on a hover.** Mantine's `Tooltip` ships `events={{ hover: true, focus: false, touch: false }}`, so of the app's 105 tooltips the **53 hanging off a non-control anchor** — a `Badge`, a `Text` — open on `mouseenter` and on nothing else: on a phone the sentence is not written at all. Enabling Mantine's `touch` is not the fix (floating-ui opens on `pointerenter` and closes on the `pointerleave` a lifted finger fires). New `components/HintAnchor.tsx` is the app's own controlled-tooltip affordance (`HintIcon`, v0.402.1) applied to an anchor with no behaviour to collide with; it **clones the child** rather than wrapping it, so no row moves and no page gets taller, and it keeps the site's own handlers and role. Applied to the eleven verdict chips of a stack card — `NoiseReadout`, `NoiseDelta`, `CleanestBadge`, `FocusChip` ×2, `CalibrationBadge`, `HazyNightBadge`, `PanelSeamsBadge`, `RejectionBadge`, `FrameCountBadge`'s thin-stack warning, and History's own *"what's this?"*, which is the sharpest case (two words that *invite* a question, answering only a hover). Hover is byte-for-byte what it was; keyboard users gain the hints for the first time. Frontend-only: no config, schema, on-disk, endpoint, response-shape or default change. Tests +9, three fail before.
- **v0.412.0** — AUTONOMY (PRIORITY 2, the 2026-07-25 backlog item, opt-in `astap_bootstrap_solve` path): **the faint-field rescue now anchors on a sub that already solved, instead of always re-solving a deep image.** The bootstrap engages when fewer than `min_frames` subs solved — a band that includes "a handful did" — and in that band it still built a deep image and asked ASTAP to solve *that*: a synthetic frame with no optics headers, on the field that had just defeated the solver sub by sub, while 1–7 real verified solutions of the same pointing sat unused in the DB. New `bootstrap.pick_solved_anchor` picks one (usable WCS by `wcs_text_is_usable`, same pixel shape as the members, star-richest first, at most `ANCHOR_LOAD_ATTEMPTS`=3 loaded since a load is a debayer) and the burst registers against it and takes its WCS — same phase-correlation shifts, same `propagate_wcs` CRPIX offsets, but no integration, no temp FITS, no extra ASTAP call and none of that call's failure risk. The deep-image path is untouched for the zero-solved case it was measured for, and for a target whose solved subs are unreadable or the wrong shape. The anchor is member 0 and every count below it (readability, registration, `n_members`, `n_registered`) counts only the **unsolved** members, so it cannot inflate the engagement gate; it is skipped in the propagation loop, because an already-solved sub is never touched. `BootstrapResult.anchored_on_solved_sub` / `bootstrap_anchored` say which path ran. Engine-only, additive, off-by-default path — no config, schema, on-disk, endpoint, response-shape or default change. Tests +5, four fail before, including a ground-truth CRPIX check with a deep solver that raises if it is called at all. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.411.1** — 🐛 BUG (trust / logging, found while writing v0.411.0 in the same block; reproduced by test): **a *successful* stack-then-solve bootstrap rescue logged itself as a failure.** `Project` has no `.name` attribute (the target's name lives in its meta table), and the bootstrap's credit line read it **inside** the block's own `except Exception` — so the one branch that fires when the bootstrap actually rescued subs raised, and the walk-away log said *"stack-then-solve bootstrap failed: 'Project' object has no attribute 'name'"* about a run that had just worked. The summary keys are written before the raise, so the Jobs page's rescue note was right all along — which is why nothing on screen ever disagreed. Fixed to `project.get_meta("name")`, the accessor the rest of the codebase uses. One line; no config, schema, on-disk, endpoint, response-shape or default change. Tests +1, fails before. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.411.0** — AUTONOMY (PRIORITY 2/4, the 2026-07-23 backlog slice (c) of the v0.180.0 sibling-hint fill-in): **a second solve pass now reaches the subs a Seestar's own header hint kept blind.** v0.180.0 offers the solved siblings' centre at the tight `SIBLING_HINT_RADIUS_DEG` (5°) only to a frame with **no** header hint — and a Seestar writes `RA`/`DEC` into every sub, so on the owner's data that rescue never fires: each unsolved sub is searched blind-wide at 30° even after a dozen siblings pinned the pointing to within a degree, and an unlocated sub is silently left out of the stack. New pure `solve/runner.build_sibling_retry_arglist` re-offers **only this round's failures** around the now-known centre at the tight radius — a smaller *correct* search than the one that just failed, which is what the 2026-07-24 ASTAP measurement said moves the needle (~4 s failed at 30°, ~0.2 s at 5°); ASTAP still verifies the pattern, so it can only ever **add** solves. Bounded to one extra attempt and skipping the four cases it cannot help — a **setup** failure (no star database costs zero extra attempts), a **timeout** (already 3× the configured seconds, and it keeps its own "ran out of time" bucket), a job that **raised**, and a frame that already searched exactly there — plus standing down entirely when nothing has solved yet **or** when `use_solve_hints` is off (a blind solve was asked for, and this pass is nothing but a hint). `scanner.run_qc_and_solve` gains `retry_unsolved_with_sibling_hint=True`, running before the opt-in bootstrap so a real per-sub solve beats a propagated one. A rescued sub counts in `solve_ok`, so the Jobs page's existing "Located N of M" sentence improves with **no frontend change**; `solve_done`/`solve_total` stay the progress counters. Engine-only, additive — no config, schema, on-disk, endpoint, response-shape or default change. Tests +8, three fail before. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.410.1** — 🐛 VERIFIED BUG (PRIORITY 1/3, the editor's preset chip and Adaptive-Auto's archetype routing; Builder-reproduced in both directions), **found by taking v0.410.0's bug class to the other cue `auto_recipe` consumes — exactly as v0.409.1 was found from v0.409.0**: **the same panel steps decided what your target *was*.** `classify_target` thresholds its geometry at `sky + max(0.06, 6·sky_sigma)` off a global level median; v0.409.1 made that blind to a *gradient*, and a mosaic's **steps** break it the same way and worse (a degree-2 surface barely touches a step). Measured on the four-panel scene, the identical stack with only the layout differing: `ext_frac` **0.0215 → 0.0030**, `star_share` **0.597 → 0.889**, verdict **`None` → star cluster at 0.89** (0.86–0.92 on four seeds); on the classify file's own star-field-with-nebulosity at residual steps of 0.024/−0.016/0.032, **cluster at 0.98**. It drives the editor's one-click preset chip and `auto_recipe`'s `object_type`, so a taste bias learned on one archetype could be spent on a stack the layout had renamed. **Same line, same place:** the geometry is read off `_detrended_luminance(_delevelled_luminance(lum, coverage))` — v0.410.0's de-stepper — while the **colour** cue still reads the untouched `arr`, so no threshold or floor moves. After: `None` on all four seeds, matching the single field. A coloured nebula, a galaxy and a cluster all keep their verdicts under the same steps and the same map (the nebula survives on v0.410.0's grain stand-down, not on luck). Wired at all three call sites via `editor._auto_measure_coverage`'s `is_mosaic` gate, so a single-field run reads no sibling and is classified exactly as today. Engine + one webapp gate, additive — no config, schema, on-disk, endpoint, response-shape or default change. Tests +3, **1 fails before**; three existing `classify_target` stubs gained the new keyword, assertions untouched. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.410.0** — 🐛 VERIFIED BUG (PRIORITY 1, the one-click editor path on the shape the owner actually shoots; Builder-reproduced against `origin/main`'s own `analyze_proxy`), **closing the residual v0.409.0 filed rather than guessed at**: **a mosaic's per-panel steps darkened the finished Auto picture — by steps Auto removes itself.** v0.409.0 made the sky *level* blind to a light-pollution gradient and said what it had not answered: panel offsets are **steps**, not a degree-2 surface, so the identical stack read **0.075** as a mosaic against **0.024** as a single field, `target_bg` **0.2100 vs 0.2304**, and the finished picture's sky came out **11.2 % darker** (p30 0.1687 vs 0.1899) — a property of the *layout*, not of the data. `auto_recipe` prepends `background.level_coverage` on every mosaic, so those steps are gone before `tone.stretch` sees a pixel: same mistake, other structure. New `presets._delevelled_luminance(lum, coverage)` removes them **the way the recipe does** — bin by the integer coverage value, shift each bin by its own robust sky median (`coverage_leveling`'s `rough_sky`, measured with that module's own `_robust_stats`), canvas median put back so the plane gets flatter and never brighter — and runs **before** `_detrended_luminance`, matching the recipe's own order. After: 0.0240 / 0.2304 / −1.1 % (same at seeds 5 and 21). **A measurement fix, not a threshold flip:** every constant untouched, σ still on the raw pixels. The map is asked for **only where the recipe carries the pass** (`is_mosaic` decides both, in one place), so a single-field stack's Auto is byte-for-byte what it was whatever map is handed in — pinned as recipe equality, and not merely conservative, since a single field gets no leveling pass to measure out. New `webapp/routers/editor._auto_measure_coverage` supplies it with the border trim's own precedence: the honest `_framecov.fits` frame count, falling back to the weighted map for older runs. A canvas the **object** fills is refused outright rather than flattened — each level's retained sample checked against 3× the image's own **grain**, measured structure-blind because on that very image a sigma-clipped canvas spread *is* the object (measured 0.24–0.36 across six scenes that are sky with an object on them, 5.1–12.5 across ones that are object). Correctly inert on the bundled samples (mosaic 0.00309 → 0.00312; field unchanged to five decimals even when handed its own map). Not over-claimed — two equally-deep panels are one bin here exactly as they are in the op, and there is a test named for it. Engine-only plus one webapp helper, additive: no config, schema, on-disk, endpoint, response-shape or default change. Tests +14 collected (11 engine, 3 webapp), **7 fail before**. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.409.1** — 🐛 VERIFIED BUG (PRIORITY 1/3, the editor's preset chip and Adaptive-Auto's archetype routing; Builder-reproduced in both directions), **found by taking v0.409.0's bug class to the other cue `auto_recipe` consumes**: **the same light-pollution gradient decided what your target *was*.** `classify_target` thresholds its geometry at `sky + max(0.06, 6·sky_sigma)` — a **global** level median plus the MAD of the levels beneath it, exactly the estimator v0.225.0 removed from `analyze_proxy` — so a tilt inflates the σ, the threshold climbs, and the faint diffuse half of the picture vanishes under it. Measured on a star-rich field with broad faint nebulosity at a 0.10 sky: `ext_frac` **0.0589 → 0.0010** and `star_share` **0.671 → 0.989** between tilt 0.02 and 0.05, turning "nothing clear" into **globular cluster at confidence 0.99** (1.00 at 0.08; same flip on three seeds of the other file's scene). And the other way: a real coloured nebula reads *nebula* at tilts 0/0.05/0.08 and is **lost entirely** at 0.15. It is read by the editor's one-click "try this preset?" chip and by `auto_recipe`'s `object_type`, so a taste bias learned on one archetype could be spent on a stack the tilt had renamed. **One line, same principle:** the geometry cues are read off `_detrended_luminance(lum)`; the **colour** cue still reads the untouched `arr` (`_extended_chroma` is scale-invariant by construction), so only the geometry moves and no threshold or floor changes. Every verdict on the file's gradient-free fixtures is byte-identical and all thirteen existing tests pass untouched. Engine-only, additive — no config, schema, on-disk, endpoint, response-shape or default change. Tests +3, **2 fail before**. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.409.0** — 🐛 VERIFIED BUG (PRIORITY 1, the one-click editor path, on by default; Builder-reproduced against `origin/main`'s own `analyze_proxy`): **a light-pollution gradient darkened the finished Auto picture — by a gradient Auto removes itself.** v0.225.0 made the sky *noise* structure-blind and never carried the same property to the **sky level** beside it, which stayed the median of the whole-image-normalized luminance and is the only input to Auto's stretch target (`0.24 - sky*0.4`). `background.final_gradient` is the recipe's **first** op, so the stretch's real input is the same picture whatever tilt the proxy carried — measured **0.1749 / 0.1751 / 0.1751** at gradients 0 / 0.03 / 0.08 — while Auto measured **0.047 / 0.195 / 0.357** of that stack, a 7.6× spread: it chose the goal for one image by measuring another. On the fixture this file's noise tests already ship, gradient 0.08 took the level 0.024 → 0.153, `target_bg` 0.230 → 0.179, and the **finished picture's sky 23 % darker** (p30 0.190 → 0.147). New `presets._detrended_luminance` reads the level off the plane with its frame-scale sky shape removed, via the same `bg/sky_poly.fit_sky_poly` both background passes detrend with (~40 ms, against 2.5 s to run the real gradient op) — subtracting only the *shape*, the surface's own median kept, so the plane gets flatter and never brighter. **A measurement fix, not a threshold flip:** every constant is untouched, and the σ stays measured on the raw pixels on purpose (its own estimator is already gradient-blind and its band is calibrated in those units; re-measuring it would move 0.007 → 0.023 and swing the denoise/sharpen crossfade on every image). Inert where there is nothing to fix: sky 0.0240 → 0.0240 synthetic, **0.00298 → 0.00298** on the bundled sample's real proxy, largest pixel changed 0.17 % of the image's robust range vs 13.6 % on the tilted one; declines wherever `fit_sky_poly` does. Engine-only, additive — no config, schema, on-disk, endpoint, response-shape or default change. A mosaic's panel *steps* are only partly answered (not a smooth surface) and are filed as the residual under "Bugs", not guessed at. Tests +8 collected, **6 fail before**. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.408.2** — 🐛🔴 VERIFIED BUG (wrong picture on a shipped feature the owner was actively looking at; MEASURED on his own file): **the Sun came back green and still meshed, because the video path debayered in the deep-sky path’s CFA phase.** v0.347.0 was right that a raw solar/planetary capture reaches the stack as an undebayered mosaic and wrong about *which pattern*: it took `RGGB` from `fits_loader.py` — where that name is the **fallback** for a `BAYERPAT` header the deep-sky path actually *reads* — and hard-coded it as `video/ffmpeg.CFA_PATTERN`. Video has no header, so it was an assumption. Measured on `2026-06-19-175558-Solar-RAW.avi`, the 2×2 sub-lattice means inside the disk are 40.7 / 10.2 / 131.7 / 40.7: the two **matched** values are the two green photosites and they sit on the **main** diagonal, where `RGGB` puts red and blue — here **13:1 apart**. Reproduced through the real `bilinear_debayer` from those four numbers alone: `RGGB` → R:G:B 40.7:**71.0**:40.7, **green**, mesh residual **40.50**; `GBRG` → **131.7**:40.7:10.2, red/orange, residual **0.00**. **Not fixed by swapping one guess for another:** new `ffmpeg.detect_cfa_pattern` reads the green *diagonal* off the stream’s first frame (the matched pair is green by construction), latched for the whole capture beside the existing "is this really a mosaic" decision, with `_CFA_DETECT_MIN_SPREAD_DN` / `_CFA_DETECT_MATCH_RATIO` falling back to the **measured** `GBRG` on a frame with nothing to read. R-vs-B stays the device fact the measurement establishes (a mosaic cannot distinguish `GBRG` from `GRBG`). **Second half, or the owner keeps the green Sun forever:** `colour_is_stale` short-circuited on `colour_current`, a boolean meaning "a build that knew about colour made this" — which v0.347.0 stamped True. It is now joined by an additive `colour_build` generation number (`_COLOUR_PIPELINE_BUILD`), so a still from the wrong-phase build is offered the re-stack, while an ordinary colour capture is re-probed once and never nagged. Alert copy follows (it said "grey"; those stills are green). **CFA phase and frame orientation are one coupled invariant** — `RGGB` row-flipped *is* `GBRG`, which is why AVI’s bottom-up storage split the two paths — pinned by `test_the_two_patterns_are_one_row_flip_apart` so neither constant can move alone. Additive/upgrade-safe: an old `meta.json` reads as generation 0 (tested); no config, schema, on-disk, endpoint or response-shape change. Tests +11 collected (7 engine, incl. one parametrized ×2; 4 webapp), five failing before on behaviour. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.408.1** — 🐛 VERIFIED BUG (image quality / autonomy, PRIORITY 2/4; Builder-reproduced against `origin/main`'s own `grade_frames`): **a mosaic panel too thin to be its own population was graded against the whole target and condemned wholesale as "likely cloud".** v0.270.2 made the flux-like metrics per-panel; a panel below `MIN_FRAMES_FOR_GRADING` (10) is not a population, so `pointing_groups` labels it `-1` and its frames fell back to the target-wide yardstick — the very reading the split exists to refuse — and because a thin panel's subs are alike it flags **all** of them. Measured on 3×12 healthy panels plus a 6-sub panel at a star-poor pointing with a **perfectly normal sky level and star flux**: **6 of 6 rejected, on `star_count` alone**, reason *"far fewer stars than typical (120 vs 404) — likely cloud"* — verbatim the sentence AGENTS.md §1 quotes as the v0.270.2 bug. This is the owner's shape (the bundled mosaic sample is 6/6/6/**3**; a panel cut short by cloud is thin by definition). **The fix is narrow, and physical rather than statistical: cloud raises the sky level, a different pointing does not.** Over one mosaic's few degrees `sky_adu_median` is a property of the *night*, while star count and median star flux are properties of *what you framed* — so a new `_MetricSpec.pointing_scale` marks those two only, and they may never borrow another panel's population (a frame with no yardstick of its own is left ungraded on them). `sky_adu_median` keeps its target-wide fallback, which is what the existing `test_a_panel_too_thin_to_grade_falls_back_to_the_whole_target` clouded panel actually trips — **no test weakened**; that test now also asserts the reason set is exactly `{"sky_adu_median"}`. Post-fix: star-poor thin panel **0 of 6** flagged, merely-fainter 0 of 6, genuinely clouded still **6 of 6** on the sky level alone. A panel with its own population still grades on every metric; a single-pointing target is untouched; `bulk_select` already used this pattern. Engine-only, additive — no config, schema, on-disk, API-shape or default change. Tests +5, three failing before. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.408.0** — 🐛 VERIFIED BUG (image quality / trust, PRIORITY 2/4; Builder-reproduced against `origin/main`'s own function): **the streak guard's position half anchored on ONE median, so a mosaic whose panels each carry the extended object rescued NOTHING — a second stationary object made the detector strictly worse than one.** `qc/runner.stationary_streak_frames` is what gives back the subs a shape-only Hough detector wrongly calls trails when a bright elongated object (edge-on galaxy, elongated nebula) trips it on essentially every sub; the fraction tiers above it cannot see a minority-flagged object at all. It asked "are the flagged components at *this* one place?" of the median of the whole flagged set — right on a single field, and on a **mosaic** (§1: the owner is a heavy mosaic user) the panels point at different sky, so one object spanning the mosaic lands at a *different* place in each panel's frames and the median falls **between** the clusters, within `STATIONARY_CLUSTER_RADIUS` of nothing. Measured on main's function verbatim: one panel of 8 → 8 rescued; **two panels of 8 → 0**; a 2×2 of 6 → 0; two panels of 60 (the owner's scale) → **0**. Every one of those subs stays out of the stack, silently, on the by-default path. Now the clusters are **found, not assumed**: each candidate centre re-centres on the median of its own neighbours (so an accepted set is still the same median-centred one), the largest qualifying cluster is taken and removed, repeating up to `STATIONARY_MAX_CLUSTERS` (16, largest-first — a work bound above any Seestar mosaic's panel count). A set holding exactly one cluster is byte-for-byte the old answer, and all 21 existing tests pass unchanged. **The price of searching is paid explicitly:** asking once per candidate instead of once turns the radius's own coincidence budget into an event (measured: 20 scattered trails threw a chance four in 13 % of sets), so each cluster is scored against the null that describes real trails — Poisson within the radius, multiplied by the centres tried (`_chance_cluster_p`, `STATIONARY_CLUSTER_MAX_P = 0.05`) — re-measured at **2 false verdicts in 1,800 scattered sets (0.1 %)** while a 60-per-panel mosaic cluster sails through. Vectorised and memoised on the re-centred centre: 0.37 s for 3,000 flagged frames. Contract unchanged (un-reject-only, per frame, never a user override, no verdict without a position and a date); engine-only and additive — no config, schema, on-disk, API-shape or default change, and nothing about *what* is flagged moved. Tests +8, every multi-cluster one failing before. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.407.1** — 🐛 BUG (friendliness / trust, PRIORITY 3), Builder-verified by reproduction on the running app (`agent-dogfood.sh --build --mosaic --editor`, step 4c): **the panel map and the health panel gave opposite instructions about the same panel of the same run.** Printed one line under the other on the bundled mosaic sample: the map's *"It's only a few minutes' difference at this stage, so it evens out on its own as you keep shooting"*, and `grain_uneven`'s *"another night on that panel is what evens it out"*. The map asks two questions of a thin panel — thinner by `THIN_FRACTION`, **and** behind by `THIN_MIN_SHORTFALL_S` (300 s, whose docstring exists to "stop a brand-new mosaic from being nagged about noise in its first half hour"); the grain note asked neither, firing on `grain_ratio ≥ 1.25` alone. **A depth cannot answer the second question**: 3 subs against 6 reads 1.4× grainier whether it is 30 s or 3 h behind (1/√2 either way), and the small case genuinely closes itself — ten more minutes on every panel takes 30 s vs 60 s to a grain ratio of 1.02. So the note was sending a beginner out for a targeted night to recover half a minute. `stack_health` now converts the shortfall to *time* (`(deep − thin) × median accepted sub exposure`, new `_median_sub_exposure` mirroring `recommended_dark_spec`) and reads it against the **imported** `mosaicmap.THIN_MIN_SHORTFALL_S` — one threshold, not a second opinion — keeping the whole measurement and swapping only the closing clause, quoted through the map's own `format_duration` and ending in the map's own words. Exactly the shape v0.406.2 gave the map's `behind` branch. At or above the threshold the sentence is byte-for-byte what it was (pinned whole, not by substring); `grain_verdict` untouched, so v0.406.1's `PanelSeamsBadge` tooltip is unaffected; `action` still `None`; no threshold, column, schema, config, API-shape or default change; an unrecorded sub exposure keeps today's wording. Tests +7 collected (three new cases plus a four-case parametrize), three fail-before, including a parametrized **agreement** pin that runs `mosaic_depth_map` and `stack_health` on the same mosaic at four shortfalls and asserts "go and shoot that panel" is said by both surfaces or by neither. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.407.0** — NEW BEGINNER FEATURE, PRIORITY 3 (enjoy / share / understand), the Scout's 2026-09-09 "shareable labelled picture" filed the same day: **the names of what's in your picture can now be downloaded on their own.** The entry asked for a new `annotate_render.py` and an `annotated.jpg` endpoint; **a grep found the whole engine half already shipped** — `seestack/objectlabels.py` (v0.293.0: `place_labels` as pure fraction geometry, `draw_object_labels` for the budget and deconfliction, `MARK_RGB`/`HALO_RGB` shared with `skymarks` so both overlays read as one set), baked by `png_bytes_to_jpeg` and reached by `download_stack_run`'s `label_objects=true`, crop- and North-up-aware via `_object_labels_for_run`, saved as `_labelled.jpg`, covered by seventeen cases in `tests/webapp/test_share_object_labels.py`. What was missing was the **download**: the only caller that ever set the flag was *"Share the keepsake"*, which sets it together with `keepsake` and `scale` — so the names could leave the app only wrapped in the matte, the caption and the scale bar, while the Target hero's own *"What’s in it?"* answer vanished the moment the picture was saved. `SavePictureMenu` now offers **"With object names"** beside *"With scale & compass"*, asking for `label_objects` and deliberately **not** `scale` (two downloads, not one item growing a second flag), following the page's North-up toggle and degrading to the plain picture on an unsolved run exactly as its sibling does. Frontend-only; no config, schema, on-disk, default, endpoint or response-shape change. Tests +4 assertions inside two existing cases (no new `it()`, so the frontend count stays 3,550), both failing before; the href is pinned three ways because `label_objects` is the last of five positional booleans. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.406.2** — 🐛 BUG (trust / friendliness, PRIORITY 2–3; Builder-verified by reproduction on the `--mosaic` sample): **the mosaic panel map dropped the thin panel and then reassured the owner that nothing was being held back.** `mosaic_depth_map` discards every `pointing_groups(min_members=`MIN_PANEL_FRAMES`=5)` cluster labelled `-1` — right for *strays*, wrong for a panel that is thin **because it is thin** — so on the 6/6/6/**3**-sub sample it drew a **hole exactly where the grain is** and wrote *"All 3 panels of your 2×2 mosaic … no part of the picture is being held back"* over it, while `stack_health` on the same run said 23 % of the picture was 1.4× grainier (and `stackhealth.py` justifies that note's `action=None` with "the panel map already says which panel is behind"). New `_thin_panels_on_the_grid` + `_axis_lines` give the dropped clusters **one** more hearing against the *geometry*: admitted only on an existing row line **and** column line, into an **empty** cell — so a stray (not on a grid line) stays out, a thin cluster can never *extend* the grid, and no panel that exists today moves a single figure. `_verdict_text` also stops calling a grid "2×2" unless the panels fill it, and gains a third branch so a mosaic that is thinner by the fraction but only minutes behind stops being called "similar" under a visibly paler cell — still with no highlight, no `aim_hint` and no nag. `THIN_MIN_SHORTFALL_S` deliberately untouched. Engine-only, additive. Tests +7, two fail-before. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.406.1** — 🐛 same bug, the two surfaces v0.406.0 left: **the History / Gallery / Compare `PanelSeamsBadge` tooltip still promised *"you shouldn't see seams between them"*** on a mosaic showing a grainier rectangle. `seamsLabel(verdict, grain)` now reads both verdicts and says *"…where the picture looks grainier that's a difference in depth (fewer subs on that panel), not a step in the sky"*; the chip stays green, keeps "Panels even", and a `"check"` verdict is untouched. `grain_verdict` rides on `StackRunOut`/`GalleryItem` as an additive optional field from the same shared `stackhealth.grain_verdict`, read off the column so neither listing opens a file. An older backend omitting it gives today's tooltip character-for-character (pinned). Tests +6. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.406.0** — 🐛 BUG + NEW MEASUREMENT (trust / friendliness, PRIORITY 3; found by measuring a `--mosaic` dogfood pass's pixels, which the pass itself reported CLEAN): **a mosaic can be perfectly levelled and still show an obvious rectangle, and the app said it couldn't.** On the mosaic sample (4 panels, 6/6/6/3 subs — §1's shape) the finished picture shows a visibly grainier quadrant over **23 %** of the canvas, while `seam_residual` reads **0.70** → *"the sky matches across the joins, so **you shouldn't see seams between them**"*, and the same panel praises the run for **"even coverage"**. Both statements were true and both were answering the wrong question: a panel differs from its neighbours in **level** (0.478 ADU here, **0.09× the grain** — levelling worked) or in **grain** (σ **7.79 vs 5.20 = 1.43×** — nobody measured it). New `measure_coverage_grain` compares each substantial coverage level **below the modal one** against the mode — anchoring on the *deepest* level would fire on every mosaic ever shot, since overlap strips are always deeper — and stamps `GRAINRAT/THN/DEP/SHR` plus four additive `stack_runs` columns. `stackhealth` now says *"about 23% of the picture has 3 subs on it where most of it has 6, so that part looks about 1.4× grainier … another night on that panel is what evens it out"*, with `action=None` because there is no in-app fix, and the two over-claims stand down (nothing removed — the flat note still says the panels evened out). σ is **sigma-clipped, not adjacent-difference**, so the same number survives the decimated read `backfill_coverage_grain` heals an existing library from — no re-stack needed. No `SCHEMA_VERSION` bump (rollback-safe), no frontend change. Tests +24, one fail-before. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.405.1** — 🐛 BUG (friendliness / trust, PRIORITY 1 editor), found by *looking at* a `--mosaic --editor` dogfood pass rather than by reading its exit code: **the editor told a mosaic's owner to "shoot it in mosaic mode".** The Target page says *"It's bigger than **this mosaic** — only about 55% of it is in this picture. Adding more panels next session would capture the rest."*; the editor of that same run said *"is bigger than the Seestar's single frame — shoot it in mosaic mode to capture all of it."* — the pre-capture *catalogue prediction*, which cannot know what was shot. `ObjectInfoCard.hideFraming` and its own docstring have carried the rule since the measured verdict shipped (*"on a page carrying both, the prediction is the copy to drop"*); Target passes it and History renders no card, so **the editor was the third surface nobody listed**. It now reads the verdict through the shared `useStackFraming(safe, rid)` — the query key the editor was *already* fetching for its re-centre offer, so **no new request** — passes `hideFraming`, and renders `FramingVerdictNote` for the run it is editing. Where nothing measured the picture the verdict self-hides and the catalogue line stays exactly as it was: nothing removed, single-field editors unchanged. Frontend-only. Tests +2 (1 fails before). Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.405.0** — NEW BEGINNER FEATURE, PRIORITY 2–3 (autonomy / friendliness): **the Dashboard now says which targets you've shot more of since their picture was made.** The per-target *"N new subs since your last stack"* nudge has existed since v0.90.0, but with `auto_stack` off and a target per object across many nights, the question after a night's capture is *which* target to open — and the only surface that knew was the one you had to open to find out. New `GET /api/new-subs-waiting` + `NewSubsWaitingNote` answer it library-wide, on the Dashboard's existing `NoticeBoard` at `advisory` priority, self-hiding at zero. **One definition, two surfaces:** accepted **and** plate-solved subs dated after the newest *genuine* run (`run_has_reusable_options` — the Target page's own `reusable` flag), pinned by a test that re-derives the Target page's number from the payloads that page reads. Cheap by construction: per target one `stack_runs` read that stops at the newest genuine row, then one indexed `COUNT` (`Project.count_accepted_solved_after`); a never-stacked target is skipped. **It offers and never acts** — no batch button (re-stacking is hours of CPU on a NAS); each target links to its own Stack form. Additive/upgrade-safe. Tests +18. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.404.0** — NEW BEGINNER FEATURE, PRIORITY 2 (autonomy) — Builder-found while reading the owner's one-sitting list: **the app finally mentions the one switch the whole walk-away path waits on.** `auto_stack` has shipped **on** since v0.391.0 but reaches only *fresh* installs (a box that has ever run carries an explicit `"auto_stack": false` no upgrade may overwrite, §9) — so on the owner's install the entire "drop your subs in and come back to a picture" chain sits behind a Settings switch **nothing in the app had ever mentioned**, while every morning it ingested, QC'd and located a night and made nothing of it. One self-hiding `AutoStackOffNote` in the Dashboard's existing `NoticeBoard` now says so and offers the switch; one click PUTs `{auto_stack: true}` (a *patch* — nothing else in the config moves) and the note is replaced by what happens next, not merely gone. Silent unless it would be true: settings unknown or on, a picture *was* made in the window, or no single target kept enough subs to clear `auto_stack_min_frames` (judged **per target** — four targets of two subs is eight subs and still no picture). It promises the *behaviour*, never the outcome, because the recap counts **kept** subs and auto-stack counts **located** ones. **A browser moved it:** the first draft lived in `LastNightCard`, passed every jsdom assertion, and rendered **hidden** at 420 px — that card sits in the `InsightTabs` "Recent" panel, `display: none` until clicked. Verified in a real browser end to end (above the fold at 420 px, one click really flips the real server, gone after reload; +238 px, only where it applies). Frontend-only; tests +18. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.403.1** — PRIORITY 1 (editor) test infra: **one-click Auto's preview is now measured against its own export end to end, on a mosaic.** `test_edit_proxy_parity.py` measures the A2 class one op at a time; nothing rendered the eleven-op recipe Auto actually builds, where an op can scale its own parameter correctly and still be handed a differently-*fitted* input. `tests/test_auto_recipe_proxy_parity.py` builds the recipe from the proxy (as the editor does), renders it on the proxy at `proxy_scale=5` **and** natively, and compares the two as pictures. **Measured: worst statistic 0.0034** (and 0.0043 at step 4, 0.0076 at step 8 on larger strips scoped-and-recorded rather than run every time) — inside the ~2 % decimation floor it asserts. **The trap is armed on every run:** patching `EditContext.scaled_px` to the identity *is* the A2 defect and moves the same number to **0.1085**, a 32× separation, so the passing test is a gate rather than a tautology. Fixture states its own shape via `tests/shapes.py` — and `assert_reference_is_the_thinnest_panel`, not `assert_panels_thinner_than_the_reference`, which the first draft got wrong and `shapes.py` caught. Test-only; +4. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.403.0** — NEW BEGINNER FEATURE, PRIORITY 2–3 (autonomy / friendliness), the “in-UI destination target picker” residue of the 2026-07 bulk-upload block (slice (c), open since v0.115.0): **the upload box knows which targets you already have — and says so before the two mistakes that live in a blank one.** Typing `M31` when the library holds *M 31* splits an object across two thinner stacks; worse, typing the target's own name lands the subs in the bare `M 31/` beside `M 31_sub/`, which `scanner._apply_seestar_convention` skips as the Seestar's *own* finished picture — so the upload succeeds and nothing ingests. The field is now an `Autocomplete` of the folders that already hold subs, with one sentence under it saying what the typed name will do and a one-click fix where there is exactly one right answer. **The folder is read, never reconstructed**: new pure `Project.source_folders_under(prefix)` groups the `frames` rows by the directory their `source_path` sits in, so nothing under `incoming/` is walked, opened or `stat`ed (AGENTS.md §10, trap armed *and proven armed* in a test) — and it reports the **whole** relative folder, because a test caught the first version collapsing `MyWorks/M 31_sub` to `MyWorks`, which reads exactly like a folder you could upload into. The skip warning compares **exactly**, like the scanner does (a `_mosaic_sub` sibling does *not* trigger the skip, and a test pins that the copy does not claim it); only the “did you mean” nudge folds case and spaces. Withheld for a folder drop or a `.zip`, where the typed name is a *parent* and `folderPreserveNote` already says the true thing. A 420 px browser pass found the fix button clipped to `Use “N` and the row wraps now. Additive: one read-only endpoint, no config/schema/on-disk/API-shape/default change; no destinations ⇒ exactly the old behaviour, which is its own test. Tests +37 (16 Python, 21 frontend), including a scanner-constants drift guard TypeScript cannot import. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.402.1** — 🐛 BUG (friendliness / trust, PRIORITY 3), Builder-found by enumeration while shipping v0.402.0: **five controls in the app answered "what does this do?" by doing it.** Wherever a `<Tooltip>` is wrapped around a `Switch` or a `SegmentedControl`, the only gesture a phone has is the one that operates the control — so the editor's `Auto-crop edges` switch (whose sentence is the only place the library-wide default is named), the Jobs page's `Notify me when done` switch (whose tap also fires the browser permission prompt) and the Gallery's three filters (including the sort whose hint is the only place that page explains its σ) each hid their explanation behind the act of using them. This is v0.374.11's defect one level up, and the sweep is exhaustive: those five are every such site in the frontend. `HintIcon` — the icon half of `HintLabel`, lifted out so `HintLabel` renders it unchanged — now sits *beside* each control, which also leaves the control's own accessible name alone. Hover and keyboard focus still work; no page gets taller; nothing removed. Tests +10, four of them fail-before regressions at the three routes asserting the words appear *and* the control did not move. Full entry under the tooltip idea above.
- **v0.402.0** — PRIORITY 1 (editor) × PRIORITY 3 (friendliness), the third slice of the "a tooltip is invisible on the device the owner reads this app on" entry: **the editor's preview toolbar now explains itself in text.** Four of the eight buttons directly under the picture (`Coverage`, `Star mask`, `Drag to crop`, `Split`) carried a plain-language sentence each and carried it *only* as a hover `Tooltip` — and a tap on one of those buttons runs it, so on a phone the one gesture available spends the question on the answer. New `PreviewToolGuide` disclosure (*"What do these buttons do? →"*), built from the same `PREVIEW_TOOLS` array the tooltips now take their labels from, and shown for exactly the tools `visiblePreviewTools({isMosaic, cropDrag})` says are on the screen. `Compare` gains the sentence it never had (it is `Split`'s twin and its label never says what it compares against). Measured with `agent-dogfood.sh --build --mosaic --editor`: editor at 420 px **3,047 → 3,072 px** closed, nothing overflowing, no console errors. Tooltips unchanged for anyone with a mouse; nothing removed. Tests +12, two fail-before. Full entry under the tooltip idea above.
- **v0.401.1** — PRIORITY 3 (friendliness), found by **running** the app right after shipping v0.401.0 and invisible to every code read of it: **the new field-fill diagram's overflow case could not be read.** On that branch the card suddenly shows *two* shapes, the object covers the frame, and the caption said "the outline" — which names neither. Two fixes: `FieldFillDiagram` now paints the `ellipse` **before** the `rect` (SVG paints in document order, and a dashed grey edge under a translucent indigo wash reads as a smudge, not as the edge of your field), and `field_fill`'s overflow text names the frame — *"Bigger than one frame — it spills over the dashed edge of your field."* Both pinned by tests. The geometry was already correct and measured so off the screenshot's own pixels; the defect was purely "which shape am I looking at?", which is not a question that occurs to you while writing the shapes. Dogfood record and the generalisation in [`PROCESS-NOTES.md`](PROCESS-NOTES.md) (2026-09-09).
- **v0.401.0** — NEW BEGINNER FEATURE, PRIORITY 2–3 (plan/understand), the Scout's 2026-09-09 idea filed the same day: **the "will it fit?" sentence gets a picture.** The identity card now draws the object to scale inside one frame, under the sentence it illustrates — because "fits comfortably in a single Seestar frame" is true of a nebula filling two thirds of the frame *and* of a planetary that is a dot in the middle of it, and those are different shots to plan (a test pins that pair: 3′ and 70′ through an S30 field, both `fits`, one captioned "expect to crop in close"). New pure `seestack.framing.field_fill` returns the object's axes as fractions of the frame's edges plus the field's own edges and one sentence; `objectinfo._to_info` fills it from the **same** catalogue size, the same square-box convention for a missing minor axis and the same *derived* field `framing_hint` and `mosaic_plan` already read, so the picture and the words cannot disagree. Three decisions worth keeping: the fractions are **not clamped** (`fieldFillGeometry` grows its `viewBox` instead, so an overflowing object is drawn whole outside the dashed frame — clipping it would hide the one thing the picture exists to show); the **field travels in the payload** rather than being re-derived in the frontend, pinned on both the derived-S30 and S50-fallback paths; and `_fill_pct` rounds to fives only above 20 %, because the app's usual idiom turns a 3 % object into "5 %" and a 0.2 % one into "0 % of the width". Additive: one optional response field, one optional engine dataclass, one component; `hideFraming` hides the drawing with the sentence, and an older backend draws nothing. Tests +24. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **CLOSED, not built (no version)** — the 2026-08-30 idea *"a corner target can't be centred in its own zoom clip"*: **the observation is right and the fix it names is backwards.** It asked for the largest zoom in [1.3×, 1.8×] at which the focus can be the crop's true centre — "a **gentler** push-in that genuinely lands on it" — but the crop is `W/s` wide, so centring on `cx` needs `W/(2s) ≤ min(cx, W−cx)`: the further out the object, the **more** zoom, not less. Measured on `crop_box_for_scale` itself at W=1000: today's 1.8× already lands exactly on anything inside [0.278 W, 0.722 W]; 0.90 W needs 5×, and the entry's own 0.96 W case needs **12.5×** — an 80 px crop blown up to the clip's 640 px edge, the 3.5× upscale `zoom_clip_size`'s never-upsample rule exists to prevent. So the bounded-zoom shape is closed; reopening it needs a different idea (re-aim the whole move, or accept a margin). Table and reasoning in [`SHIPPED.md`](SHIPPED.md).
- **v0.400.1** — 🐛 BUG (trust / share, PRIORITY 3), Builder-verified by reproduction while wiring v0.400.0: **v0.384.0's "your Process-target picture now shares off the master" did not reach the owner's main path, because Auto trims the border.** An auto-edit records a `preview_crop_json`, and `_native_picture_source` declined outright on *any* recorded crop — so the JPEG, keepsake, scale-&-compass, all three wallpapers and the zoom clip of every auto-edited picture were still re-encodes of the 1024 px preview. `auto_crop_border` is on by default, so this is what a "Process target" run *is*, not an edge case. The decline's stated reason ("the render is of the whole canvas") is true for a **linear** run and false for a display-space one: Auto's trim is a `geometry.crop` op **inside the very recipe** `render_run_full_res_png` replays, expressed in fractions, so the render reproduces the same rectangle of sky. `_render_reproduces_the_crop` now allows exactly that case — display-space, a saved recipe, and `preview_crop_of_recipe` (the same function that *recorded* the value, so they cannot drift) equal to it; `UNKNOWN` or any disagreement stays a no, because a big wrongly-framed picture is worse than a small honest one — and `_visible_canvas` makes the sizing decisions against the rectangle the render actually hands back. Nothing downstream needed changing, checked rather than assumed: `wallpaper_target_pixel` shifts into the cropped rectangle *before* rescaling, and the scale bar's `fraction` is already a fraction of the cropped canvas. Measured: the share JPEG goes **400×400 → 1280×1280** on a 1600² canvas trimmed to 80 %, same framing (max 12/255 against the same scene served the old way). Tests +4, two fail-before, including two that pin the *unchanged* declines; nothing loosened. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.400.0** — PRIORITY 3 (enjoy / share), the last open **size** item of the 2026-08-30 download-copy sweep: **the zoom clip stops being a 1024 px preview blown into a share.** It was cut out of `run.preview_path`, and because `zoom_clip_size` never upsamples that cap did not soften the clip, it *sized* it — `CLIP_LONG_EDGE` is 640 and the clip came out at `1024 / CLIP_ZOOM` = **569 px**, deepest frame the preview at 1:1, with `…/zoom-clip/info` reporting that smaller number as if it were the ask. `_zoom_clip_source` now cuts it from the **same cached share render every other hand-out already uses** (`_native_picture_source`, which declines on exactly the cases where a re-render would be a different picture — baked North-up, display-space with no recipe, a trimmed preview, no master, a canvas no bigger than the preview) and falls back to the stored bytes otherwise, so an ordinary run is byte-for-byte the clip it was. Focus re-measured against whichever bytes win, as the wallpaper already does. Size asked for is `min(_share_source_long_edge, 2 × zoom_clip_min_source_long_edge())`: past 1152 the output stops growing and the extra pixels are **supersampling**, which is worth having but is paid 24 times over (the move is 24 crop-and-resize passes) — so `ZOOM_CLIP_SOURCE_OVERSAMPLE = 2` takes the 2×2 average and stops, and **no render happens that the share JPEG and wallpaper were not already paying for**. The cache grew with the source (`_zoom_clip_signature` now carries the master stamp, the recipe hash and the app version; tag `v1`→`v2`, so cached clips rebuild). `info` cannot drift from the file by construction: `_native_picture_source`'s cheap gates are now `_native_picture_gate`, which it *is* plus the render, and `_native_picture_size` reads the size through the same gate — pinned by decoding the served animation, not by comparing strings. Measured: 222×167 → **640×480** on a 1600×1200 canvas with a 400 px preview, and >1.5× the high-frequency energy in the deepest frame against the same scene served the old way, compared at one size. Tests +4, three fail-before; nothing loosened. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.399.3 + v0.399.4** — 🐛 BUG (image-quality, PRIORITY 1), **D1's fourth instalment, closed**: **Auto's on-by-default border trim no longer crops a *fully tiled* mosaic** — up to 19.8 % of a canvas with no ragged edge anywhere, silently, on the owner's 3x3–12x8 shooting shape. v0.391.1's coverage bound could not reach it: on a fully tiled canvas that bound is **1.0 by definition**, so a rectangle keeping 0.80–0.91 cleared `TRIM_KEEP_RATIO` and was accepted. The discriminator is spatial and is two facts rather than a tuned number — `_outline_mask` says where the data *runs out* (uncovered pixels, plus the nearly-empty band along the union outline, since a bounding-box canvas often has no NaN at all), and `_thin_labels` says a ramp is a **band** while a panel is a **block** (nowhere thicker than a quarter of its own longest extent — ~0.02 for a ramp, ~1.0 for a panel, at any canvas size). `_border_trim_rect` then removes only what is *attached* to that outline and is itself a band; everything else a depth threshold calls poor is a panel, wherever it sits. It is a **second** answer and the more generous of it and the depth ladder wins, so it can only ever keep more — pinned as a property, and true of every one of the 441 measured maps. v0.399.4 then feeds it the **frame count** (`_framecov.fits`) instead of the sum of per-frame weights, falling back to the weighted map for runs that have no sibling; that was lever (b) of the filed entry, "arguably the more honest input" that "could ride along with a real one". Measured over 147 rasters × 3 outline shapes, as how many keep under 95 % of what their own coverage allows: on the frame-count map **4 / 0 / 34 → 0 / 0 / 0**, worst case 1.000 in all three; on the weighted map 13 / 14 / 39 → 4 / 4 / 10. Tests +4 engine / +2 webapp, all fail-before; `well_covered_mask` (the all-sky map, the sky-area tally) untouched. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.399.2** — 🐛 BUG (image-quality/trust, PRIORITY 3–4), Builder-verified by reproduction: **a mosaic panel that is merely thinner than its neighbours is no longer faded off the all-sky map, or left out of the "how much sky have I photographed?" tally.** `well_covered_mask` asks `panel_coverage_level` which coverage level counts as "one panel", and *substantial* there is 8 % of the canvas — one panel of a **twelve**-panel mosaic. On the owner's 5x5/10x10/12x8 rasters a panel is 1–4 %, so the search walks past every thin panel and settles near the **mode** of the depth distribution; everything below half of that is called fringe. Measured on the integer frame-count maps this path actually reads: **90 of 147 fully tiled rasters fade something, the worst 26.3 % of a canvas covered edge to edge** — and because `seestack.skyarea` counts the same mask, the owner's photographed-sky figure was short by the same fraction (7.0 % on the 6x4 regression). The trim had a second line of defence (v0.391.1's coverage bound); a per-pixel mask has no rectangle to compare against, so its only lever is the reference — hence a mask-only `MASK_LEVEL_MIN_FRAC` (0.03), leaving `largest_covered_rect` bit-for-bit unchanged. **0 of 147 after**, while every honest fade survives to the digit (a single field's dither ramp 2.50 % before *and* after, a ragged 2x2 8.17 % likewise; a raster that is both many-panelled and ragged still loses its border, 11.2 %). Safe by construction: `panel_coverage_level` is monotone in that fraction, so the reference can only fall and the mask can only grow. Tests +6, three fail-before. **The same run verified and filed D1's fourth instalment** — the trim still cropped fully tiled rasters by up to 19.8 %, with five candidate fixes measured and rejected; *closed in v0.399.3/v0.399.4 above, entry in [`SHIPPED.md`](SHIPPED.md)*. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.399.1** — 🐛 BUG (broken-UX/trust, PRIORITY 1–2), found by **running** the app during the v0.399.0 live check: **the Stack form named the outlier method the run would *not* use, on a mosaic.** `/stack-estimate`'s `auto_reject_resolved.method` re-derived the answer from the target's *frame count* while the engine's `_resolve_auto_reject` sizes it from the mosaic's **per-pixel panel depth** — reproduced on the 2×2 sample: 21 subs, depth 3, endpoint said `sigma_clip`, the run that had just finished recorded min/max. The A6 class (v0.326.7) surviving in the reporting path, on the owner's dominant shape. Not just a sentence: `Stack.tsx` drives `sigmaClipEffective`/`minMaxEffective` off this field, so the form greyed the wrong toggle and coached about the wrong method. Fixed by reading the method off the **resolved** options the endpoint already computes (one definition, cannot drift), plus an additive `panel_depth` so the copy can give the reason; `autoRejectMethodNote` extracted to `frontend/src/autoRejectNote.ts` with a depth voice, frame wording byte-for-byte unchanged wherever depth says nothing new. Tests +9, three fail before. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **CLOSED, not built (no version)** — Performance: **`GET /api/gallery/best` does not need the cache the 2026-08-04 entry proposed.** That entry set its own gate ("time the endpoint on a realistic library first"); measured at **97 ms** on 40 targets × 20 runs and **235 ms** on 80 × 40 — under CPU contention, so upper bounds — i.e. the same band as `/api/gallery` beside it and two orders off the 13.8 s endpoints that justified v0.374.7–v0.374.9. A cache would buy ~0.1–0.25 s twice per Dashboard path and pay in staleness on the one wall whose point is "the picture I pinned". Entry, numbers and the safe shape if it is ever reopened are in [`SHIPPED.md`](SHIPPED.md).
- **v0.399.0** — NEW BEGINNER FEATURE, PRIORITY 2–3 (autonomy/friendliness): **the Stack form says about how long the run will take.** The Jobs page could say how much longer a *running* stack had to go; nothing answered "start it now or in the morning?" before the button, next to the size and the memory verdict the same panel already gives. Measured, never modelled: new additive `stack_runs.duration_s` stamped by `run_stack` — added **without** a `SCHEMA_VERSION` bump, through `_reconcile_table_columns`, because a bump would make an older build refuse to open the DB (a red rollback test said so) — and new `seestack/stacktime.py` takes the **median seconds-per-sub of this target's own comparable past runs**. "Comparable" is strict on purpose — same `stack_cost_class` (which *is* `stacker.combine_method` plus the two-pass-drizzle split, asserted equal to it in a test, so the two cannot drift), canvas within ×2, and at least 8 subs — and it returns nothing at all on a first stack, on unseen settings, and on every library the moment it upgrades. `/stack-estimate` resolves `auto_reject` through the engine's own picker before matching, so a run about to combine with min/max is not timed from κ-σ history. The wording says what it stands on ("from your last 2 stacks of this target") and softens to *Roughly* on a ×4 extrapolation, formatted through the running job's own `formatEtaSeconds`. Tests +35. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.398.1** — PRIORITY 3 (friendliness), the Scout's 2026-08-26 #3 entry that v0.272.1 left open: **the Lucky-imaging knob is typed as the percent the finished picture is badged with.** It asked a beginner for 0.05–1.0 while the Gallery says "Lucky 50%". New optional `StackOptionField.unit` (`"percent"`, carried only by `lucky_fraction` today) makes `StackOptionControl` show and accept 0–100 with a `%` suffix — value, min, max and step scaled together, so the typed input and the editor slider speak one unit — while the engine field, its `(0, 1]` contract and the stored value are untouched; `show`/`store` are the identity for every other field. The round-trip rounds in both directions, so a stored 0.35 renders `35 %` and stores back exactly 0.35 rather than 0.35000000000000003. Tests +8, including the invariant that a `percent` unit may only sit on a float whose bounds really are a fraction. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.397.0** — PRIORITY 2–3 (autonomy/friendliness), the LEAD filed with the v0.396.0 rename offer: **a mosaic is offered its object's name.** The offer was gated on a 0.25° cone against the *union canvas* centre, so the bundled 2×2 sample sits 0.3223° from M 42 and got nothing while a single field of the same object got an offer — on the owner's own dominant shooting shape. Not fixed by a bigger radius (which would claim neighbours for single fields too) but by the object's **own extent**: `objectinfo._object_containing` accepts a centre inside the object's minor half-axis, capped at 1.5°, consulted **only** when the cone found nothing, and only for a mosaic-suffixed name (`confident_object_title(allow_extent_match=)` is off by default, so the shared-caption path is untouched). Measured over the whole real catalog before believing it: **exactly one** containment exists beyond the cone in all 157 objects (M 31 contains M 32, 0.403° against 0.525°). Tests +5, four fail-before. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.398.0** — NEW BEGINNER FEATURE, PRIORITY 3 (friendliness/plan): **"Add tonight to calendar" on the constellation nudge.** The "you're one object away from finishing Lyra, and M57 is usable until 02:10" card ended on a sentence; `GET /api/life-list/nearly-there/calendar.ics` now hands that window to the beginner's own calendar as a plain offline `.ics`. It **names no id** — it re-asks the endpoint the card read and calendars the object *it* picked — so the `_SHOWPIECE_IDS` guard the idea warned about is neither widened nor needed, and the file can never describe a different night from the card. The body comes from the new shared `plan.catalog_object_ics_response` (extracted from `get_suggest_ics`, takes an object and never an id), so the two reminders cannot drift. 404 rather than a blank calendar on every empty case. Tests +8. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.396.0** — NEW BEGINNER FEATURE (the last open slice of the Scout's 2026-08-27 #10 entry, and the **🛑 BLOCKED** premise it was stuck on): **a target still named after its folder can be renamed to what the plate solve says it is, in one click.** The identity card gains "this target is still named after its folder — call it *Crescent Nebula*?" (opt-in `allowRename`, Target page only), backed by new `Library.rename_target` (display name only — the safe name, folder, project and every stored path stay put) and `objectinfo.suggested_target_rename` (the **title-grade** 0.25° cone, not the card's looser one, because a rename outlives the session; silent when the stored name already identifies something). **The blocker was real and is now fixed:** the scanner resolves a folder *by display name*, so a rename would have made the next scan allocate `NGC_6888_SUB-<sha1>` — a second target, same sky. New additive nullable `targets.folder_name` (no `SCHEMA_VERSION` bump; the existing `_ensure_columns` self-heal adds it) is the alias row that entry asked for, and `_names_owning_safe` lets a folder answer to both names. A test caught the split live before the column existed. `scanner.preserve_mosaic_suffix` keeps a mosaic a mosaic. Tests +16. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.395.0** — PRIORITY 2 (autonomy) and the last step of the north star, the owner's 2026-09-08 answer to gate Q1 shipped **with its condition rather than after it**: **an unattended night now comes back as a picture, and any one target can be told to stop.** `Settings.auto_edit_on_autostack` ships `True` — fresh installs only, the same §9 argument as v0.391.0's (`SettingsStore` re-saves the whole model, so every install that has booted carries an explicit `false` and no migration may flip it). The owner said *"yes, but should be easy to override with manual settings"*, and the backlog's own note said not to ship the flip without it, so all three halves are here: new `webapp/auto_edit_pref` stores a **tri-state per target** in the existing `project_meta` kv table (no schema change) — `None` follows the setting, `True`/`False` override it — which `pipeline._wants_auto_edit_for` consults before finishing a fresh stack, so it survives the night rather than a page; `_auto_edit_process_run` now refuses to write over a recipe **the user** saved — which is not the same as "a recipe exists", since the pass legitimately re-runs over its own output, a distinction an existing test found rather than reasoning did; it is separated by the baked-look stamp the run already carries; and the control is a link under **any picture the app finished** (`StackRunOut.auto_edited`, one more meta read in a loop that already does three) rather than a standing switch on every target page — it writes an explicit `false` to turn off, and clears vs. sets `true` to turn on depending on which one would actually work. A garbled or hand-edited value reads as *unset*, never as "off". Settings copy names the fresh-install caveat and all three ways out. "Process target" is deliberately untouched — an explicit click has always auto-edited. Tests +19 (5 pref unit, 5 pipeline/API, 2 config-upgrade incl. a stored-`false` that asserts it *differs from the fresh default*, 5 card, 2 copy). Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.394.0** — PRIORITY 3 (enjoy + share), slice (iii) of the life-list follow-ups filed 2026-08-27 and the last one open: **"My life list" becomes one shareable picture.** New pure engine module `seestack/lifelistcard.py` composes all 110 Messier squares in catalog order — your own picture cover-cropped into the ones you have, a faintly lit square for one captured but not stacked yet, a dim numbered square for the rest — under a strip saying how far along you are. **The empty squares are the point:** the montage wall (`/api/gallery/montage.jpg`) shows only the pictures you have, which makes it a gallery; a life list has to draw the whole list. Three drawing calls are deliberately the opposite of the wall's and are explained in the full entry (cover-crop not letterbox; its own label drawer, because `_draw_corner_label` clamps to 9 px on a 114 px tile and would make the captured ids smaller than the to-shoot ones; left-aligned catalog order, so the counting survives a short last row). `GET /api/life-list/grid.jpg` renders it on demand from the previews the app already keeps and writes nothing, resolving each picture through the shared `targets.current_picture_path` so the poster cannot disagree with the page it was shared from; it **404s until one object is captured**, which is exactly where the new self-hiding "Share my grid" button inside the page's existing header card stops being offered. Previews are downscaled to `TILE_SOURCE_MAX_PX` on the way in and each target is loaded once, so filling 110 squares is tens of megabytes, not hundreds. Additive: one module, one read-only GET, one button; no config, schema, on-disk, API-shape or default change. Tests +18 (13 engine, 5 endpoint, 2 vitest). Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.393.0** — the owner's 2026-09-08 answer to gate Q5 ("skip folders named `batch_stack_tmp` at scan time? → YES"), which was the one open **Bugs** entry nobody could start: **another stacking program's working folder is walked past instead of ingested as a junk target.** `_apply_seestar_convention` now skips a folder whose name is in the existing `_TEMP_FOLDER_NAMES` (the entry's own condition — reuse the set the v0.319.6 *cleanup* verdict already uses, never a second list), before the bare-folder fallback that used to bring it in. **Exact names, not a `*_tmp` pattern**, so a real folder someone named badly is untouched. **Not silent, because a silent skip could never be undone from the UI:** it lands in `ScanResult.unvouched_skips` *whatever its files are named* — the device-output rule can be certain it is right and so stays quiet when every file is accounted for, a name-pattern guess about someone else's directory cannot — and the report is where the one-click "bring it in" lives. That override needed no special case: a scoped scan takes the folder as the unit without consulting its name, which is its documented meaning; pinned by a test either way. New shared `components/skippedFolderCopy.ts` owns the wording so the Jobs alert and the Library card cannot drift into two accounts of one folder, and neither now calls a scratch directory "your Seestar's own finished picture"; the card keeps its own "are some of my subs missing?" title, which is the right question for the old rule and the wrong one for this. Additive `reason` field on `SkippedOutputFolder`, the remembered record and `SkippedFolderOut`, defaulted so an older record/backend/frontend reads as the only case it could produce. Tests +18 (6 engine, 4 webapp, 8 copy/UI; the engine and webapp ones fail before). Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.392.0** — PRIORITY 1 (editor), the LEAD filed by the v0.390.0 run: **the editor asks before it drops a look you haven't saved.** Nothing in the editor persists a recipe on its own, so the nav bar, the in-page "History" button or the browser's back button silently threw the whole edit away — and there was no guard of any kind (`useBlocker`/`beforeunload` appeared nowhere in `frontend/src`). New `components/editor/UnsavedLookGuard.tsx`: `useBlocker` (a data router is mounted in `main.tsx`) raises a three-way modal — *Save and leave* / *Leave without saving* / *Stay here* — and `beforeunload` covers a tab close, registered only while there is something to lose. **The filed shape's baseline was deliberately not taken:** the entry proposed dirty = `recipeKey !== seedKey`, which on the v0.390.0 auto-seed path makes every first open dirty — the entry's own care note calls that worse than no guard. Dirtiness is measured instead against new `Editor.tsx::committedKey`, *the look the editor put on screen*: the Auto seed is not unsaved work (nobody asked for it and the next open reproduces it for free), while the first slider the user touches is. It moves forward on a successful Save **and** on Export, whose own notification sends the user straight to History. Both signatures are captured inside the mutation beside the recipe being sent, so an edit made while a save is in flight cannot slip past. Search-param-only navigations are not blocked (the editor rewrites its own query string). `seedKey` is untouched — the "What Auto-process did" note still needs it frozen. Frontend-only; no config, schema, on-disk, API or default change. Tests +10, and `Editor.test.tsx`'s harness moved from `MemoryRouter` to `createMemoryRouter`/`RouterProvider` (the router `main.tsx` actually mounts) so a navigation can be driven at all; all 113 existing cases pass unchanged. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.391.1** — BUG FIX (Builder-verified by reproduction, and by the READY fixture-shape entry that shipped with it): **a mosaic panel that is merely thinner than its neighbours is no longer cropped away as a ragged border.** On a dense raster with uneven panel depth — the owner's own 3x3 / 12x8 shooting shape — one-click Auto kept **25.6 %** of a 12x8 canvas, 34.8 % of a 6x4 and 17.6 % of an 8x6, all fully tiled with no ragged edge at all (AGENTS.md §1: a trim above ~15 % is a bug). **The second half of D1:** its fix made `panel_coverage_level` take the lowest *substantial* level instead of the peak, but substantial means 8 % of the canvas and 96 panels over two dozen depths hold ~1 % each, so the search walks past the thin panels and settles near the **mode** (19.1 where the thinnest panel is 8). The discriminator is not a threshold — 5 % of pixels *scattered* destroys the rectangle as thoroughly as 40 % around the rim — it is **what the discarded pixels are**: a border is *uncovered*, a thin panel is *covered*. So `largest_covered_rect` now also computes the rectangle the coverage alone allows, and when the depth threshold does worse than `TRIM_KEEP_RATIO` (0.8) of that bound it halves the threshold and asks again. Measured on fifteen shapes: every honest case byte-identical (including a **diagonal** mosaic, still 12.2 % — it is mostly uncovered, so its bound is small too), the three broken rasters → no crop, and a raster that is *both* uneven and genuinely ragged goes 34.2 % → **95.1 % kept** rather than standing down. Can only ever keep more, never less (pinned over 40 random maps). `well_covered_mask`, the all-sky fade and `coverage_thin_fraction` are untouched. Tests +5, two fail-before; no existing test weakened or rewritten. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.391.1 (same commit)** — the `READY` infra entry filed 2026-09-08: **`tests/shapes.py`, a vocabulary for stating what a "mosaic" fixture can and cannot vouch for**, measured with the *same* `panel_coverage_level` the rules under test measure with. `test_coverage_trim.py` now asserts its fixtures' shapes instead of describing them in a comment — and `assert_panels_thinner_than_the_reference` is what stops a "12x8 with uneven depth" test passing for the wrong reason. `test_photometric_mosaic_auto.py` also gains the assertion its whole file rested on unstated (both panels are drawn from the same seed, so a step between them is photometric and not sky). It found the bug above on its first run, which is the entry's own claim ("it is what finds the next D1") demonstrated rather than asserted. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.391.0** — PRIORITY 2 (autonomy), the ⭐ READY — GATE OPEN entry the owner approved 2026-09-07, with both prerequisites landed and nothing in front of it: **a fresh install now walks the whole chain — ingest → QC → solve → *stack* — without the owner finding a switch.** `Settings.auto_stack` ships `True`. **It reaches fresh installs only, deliberately:** `SettingsStore` re-saves the full model on every boot, so every install that has ever run carries an explicit `"auto_stack": false` and keeps it — and no migration flips it, because the file cannot tell "he turned it off in August" from "the app dumped the default", and flipping a setting someone turned off is the breach AGENTS.md §9 exists to prevent. The owner flips his own switch in Settings (still the one item under REQUIRES MANUAL OWNER ACTION). Safe on by default only because three guards landed first, all in the path: the readability preflight + thinner-than-best hold (v0.270.1), `auto_stack_min_frames`=3 (v0.256.0), and the settle window (v0.390.1). `auto_edit_on_autostack` stays **off** — that is question 1 on the owner's one-sitting list, not this entry's call. Settings copy now says both halves and names the three guards; the Walk-away master switch is unaffected (its other four keys still default off). Tests +3 Python / +2 vitest, **all five fail before the flip** — including the only test in `test_auto_stack_pipeline.py` that does not name `auto_stack`, and a stored-`false` upgrade test that asserts it *differs from the fresh default* rather than merely being `False`. Nothing loosened; one default value, no schema/on-disk/API change. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.390.1** — PRIORITY 2 (autonomy), the READY entry filed 2026-09-08 and the prerequisite the `auto_stack` flip is gated on (**so that flip is now unblocked**): **a target the sky is still filling is held until the night settles, instead of being re-stacked in full after every 5-minute poll.** `_auto_stack_frame_count` fires on "more solved subs than the last stack covered" and nothing asked whether subs were still *arriving*, so a night of shooting one target meant re-stacking every night it had, over and over, while the "newest picture" kept becoming a picture of a night that was not over. New `pipeline._auto_stack_settle_hold` holds while the newest accepted sub is younger than `auto_stack_settle_min` (default 20 — a named constant: longer than any poll, shorter than a meridian-flip pause; 0 = today's cadence exactly), **without stamping the attempt marker**, exactly like the thin and readability holds — so the stack happens once, on the whole night, at the first scan after the subs stop. Delayed, never stranded, never skipped; the Stack form and "Process target" are untouched. Time comes from new pure `Project.newest_accepted_sub_time()` (two `MAX()`s, no `FrameRow` — asked of every target on every poll), preferring `source_mtime` and falling back to `timestamp_utc`, whose error direction can only make a target stack *sooner*. A source clock running ahead costs one window plus the skew, never forever. The entry's "second face" (per-target `auto_stack_min_frames` publishing a one-panel mosaic on night one) is covered by the same hold, not by a second mechanism. Surfaced on the Jobs page in the same alert shape the other two holds use ("waiting on N still being shot"), and deliberately **not** in `overnight.needs_a_look` — a target still being shot is not something to go and check. Tests +10 Python / +4 vitest; seventeen existing auto-stack tests across five files now set the window to 0 explicitly (their fixtures write subs seconds before asserting), none loosened. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.390.0** — PRIORITY 1 (editor), the ⭐ READY — GATE OPEN entry the owner approved 2026-09-07: **the editor opens on the good picture instead of a nudge to press one button.** On a run with no saved recipe, first open runs `…/editor/auto` and opens on that, with the usual "What Auto-process did" note and *"Started you off with Auto-process — Undo to see the plain stack."* It stands aside for a saved recipe, and for either look of the user's **own** — the previous run's edit *and* their saved default; the entry named only the first, but both buttons live inside the nudge a seed replaces, and removing a feature is the owner's one hard constraint. `resetOps([])` then `setOps(built)` puts it exactly one Undo from the plain stack (the reset matters — navigating from another run leaves that run's recipe in `ops`); nothing is persisted without a Save; a failed seed falls through to the old empty pipeline and nudge with **no** red error, via its own `autoSeed` mutation sharing `fetchAuto`/`applyAutoResult` with the button. `seeded` still gates every preview query, so the decision is made once and there is no seed-then-reseed flash. **Gate re-measured, not trusted:** the mosaic sample stacked fresh and read through `_trim_rect_for_run` keeps **92.1 %** of the canvas. Tests +6 net; the old first-view test rewritten deliberately, never weakened. The entry's "unsaved-changes guard" does not exist anywhere in the frontend — filed back under Ideas. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.389.2** — BUG FIX (the 🟠 VERIFIED entry filed 2026-09-08, with its two named companions): **"thin coverage" is measured against a *panel's* depth, not the coverage map's peak — the same mistake D1 removed from the trim.** `coverage_thin_fraction` now references `coverage_trim.panel_coverage_level`, so "How's my stack?" can no longer tell a mosaic owner that 22–74 % of his picture is a ragged border while offering a "Trim border" that keeps the whole canvas (measured on seven shapes: the 2x2 sample 22 % → 0.0 %, a 12x8 raster with uneven depth and weight jitter 74 % → 0.0 %; the single field unchanged to the digit, since the panel level *is* its peak). The level comes off a strided sample capped at 2 M pixels, because `panel_coverage_level` sorts a float64 copy and this runs at stack time on the full canvas. Old runs heal without a re-stack: two additive columns (`coverage_shares_version`, `coverage_median_depth`, no `SCHEMA_VERSION` bump) let `backfill_coverage_shares` **re-derive** a stale share off the map the run already wrote — a single-field run is never marked stale, and a stale mosaic whose map is gone goes quiet in memory only, never losing the row. The κ-σ reach note gains the provable half of A6: `coverage_median_depth` fires it on a mosaic whose panels are shallow but whose four-way corner cleared the threshold, worded as the half of the picture it can prove. `coverage_is_mosaic`'s dense-raster false negative is documented, deliberately **not** widened (legacy-fallback only). Tests +26. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.389.1** — CLOSED BY MEASUREMENT (the Scout's 2026-08-26 #2 idea, unblocked by v0.387.0): **`photometric_normalize` stays off outside a mosaic — star-core SNR gains only +0.16 % on the realistic single-field case with quality weighting on** (+0.39 / +1.22 / +3.33 % as the haze gets extreme; +0.00 % and bit-identical when there is nothing to correct). On a single field every pixel gets the *same* subs, so the spatial step that makes the pass valuable on a mosaic is structurally absent and all it can change is the combine weight — which quality weighting's `transparency_factor` already approximates. Not a default flip on the hot path. **The first fixture inverted the answer to −9.7 %** by scaling the sky noise along with the signal; haze dims the stars, not the sky glow. `tests/test_photometric_single_field.py` (+2) pins the bit-identity and the never-hurts direction. No code changed. Full entry, table and fixture warning in [`SHIPPED.md`](SHIPPED.md).
- **v0.389.0** — NEW BEGINNER FEATURE (the Scout's 2026-08-26 #4 entry, unblocked by doing the data task its 2026-08-29 stand-down laid out): **"does my colour look right?" — the finished picture's colour, checked against what that object actually looks like.** A vetted `nebula_class` (`emission` / `reflection` / `both` / `unknown`) is curated onto all 28 bundled `type: "nebula"` entries and nothing else, pinned by the blurb cross-check v0.276.0's `distance_ly` pass used (22/2/3/1). `edit/histogram.py::measure_object_colour` is the sibling of `measure_sky_cast` on the *object* population — sky-subtracted, star-core-trimmed, read off the stretched display image — and `seestack/colourcheck.py::colour_expectation` is the pure join to one line, or `None`. **Built to stay quiet:** only two families speak, a nudge needs 3× the lead a reassurance does, there is a dead band of silence between them, `both`/`unknown`/planetary/SNR never speak, and the word "wrong" never appears. A test, not reasoning, caught the σ estimator: a lower-half MAD called 34 % of a pure-noise frame "object"; `median − p15.87` puts it back at ~2 %. Surfaced as the editor histogram's `colour_check` beside the sky-cast line, plus `ObjectInfoOut.nebula_class`. Tests +27. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.388.0** — NEW BEGINNER FEATURE (the Scout's 2026-09-08 "While you were asleep" entry, built as it instructed — the Dashboard *did* already fold most of it, so it shipped as a consolidation rather than a card): **the "Last night" card now says what the app *did* with the night, not only what the sky gave.** New pure `webapp/overnight.py` — `new_pictures_since` (one line per target, newest first, each carrying the frame count of the picture it replaced so "deeper than the 78 it had before" is only said when true) and `needs_a_look` / `newest_scan_summary` (the holds the scan already records — `auto_stack_held_unreadable` missing-files first, then `auto_stack_held_thin` — read from the **newest finished scan only**, so a resolved hold stops being news with no state to go stale). Stamps compared with `activity_calendar.parse_utc`, never as strings (the app writes UTC in two shapes). Additive `RecentStack.is_genuine`, set through the *shared* `pipeline._stack_options_from_run_json` predicate, keeps an editor export from reading as a second picture; `_rollup_stacks_cached` extracts the cache `/api/stats` already owned so the digest costs no second walk over every project. `LastNightCard` gains three pure wording helpers — a missing-files hold reads as something outside the app to go and check, a thin hold as patience. Both lists are empty on a night nothing was stacked (the owner's live `auto_stack` off), so the card renders exactly as before. Tests +17 Python / +13 frontend. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.387.0** — PRIORITY 4 (image quality, and the only ready one that reaches a heavy mosaic user), the READY entry left open by v0.271.0: **a mosaic panel shot entirely through haze is lifted to match its neighbours, measured in the sky the panels share.** New `seestack/stack/overlapgain.py::compute_overlap_gain_scales` runs as a pre-pass at stack setup — each panel's clearest few subs through the stack's own `align.align_one`, block-meaned to a ~400 px coarse map, a median signal ratio per overlapping pair, then one log-scale per panel by least squares, normalised to a median of 1.0 and clamped to `[1/2, 2]`, multiplied into the `{frame_id: scale}` map the accumulators already consume. **NOT `transparency_score`** — v0.271.0 removed that comparison after measuring a 2.23× panel-gain error, because it cannot tell "hazy panel" from "emptier patch of sky". **Measured: the star-flux step across the join goes 38.6 % → 2.3 % on a 0.6× hazy panel, and the recovered scales are 0.774/1.291 = 1.667 = 1/0.6.** The guard that makes it safe on by default was found by a test, not by reasoning: overlapping *footprints* only mean two WCS agree, so on a fixture whose panels overlap while holding unrelated stars the first implementation invented a 2.6× gain — a Pearson correlation across the strip (`MIN_OVERLAP_CORRELATION`) refuses that and cannot be fooled by a gain, which is exactly what correlation is blind to. Every other uncertainty resolves to "change nothing" too: too few shared/signal cells, a ratio outside the clamp, a fit whose pairs disagree, or any exception → `None` → today's stack byte for byte. Provenance stamped as `PANG*` and surfaced as History's "Mosaic panels matched to each other · N panels · brightness lo–hi× · measured in N overlaps". Tests +15 engine / +2 API / +3 vitest; `test_a_wholly_hazy_panel_is_deliberately_left_alone` deliberately rewritten (its fixture cannot carry the new claim). Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.386.2** — PRIORITY 3 (friendliness), Scout dogfood find on the **mosaic** target: **the "Is it enough yet?" goal chip printed a mosaic's per-panel-scaled goal as a raw float — `goal ~14.526171875 h (3.63-field mosaic)`.** The verdict sentence beside it already rounded via `readiness.ts::fmtGoal` ("~14.5 h"), but `Target.tsx` printed `readiness.goalHours` unrounded in the chip, so the two disagreed and the chip read like a bug. `fmtGoal` is now exported and used for the chip too (whole number as-is, else one decimal). Frontend-only, one-line behaviour change; verified by the `--mosaic` dogfood screenshot. Tests +1 fail-before (`Target.test.tsx`, a 3.63-field nebula mosaic → `goal ~14.5 h`, and the raw float absent). No config/schema/API/default change.
- **v0.386.1** — PRIORITY 3 (robustness on the RAM-capped NAS), the READY entry filed 2026-09-07: **the "Full-res PNG" download — and the "Full-size versions" archive that renders every target through the same call — stops holding about five copies of the picture at once.** `render_preview_png_full_res` owns every array it touches and never reads them again, so it now consumes rather than copies: `autostretch(copy=False)` (new opt-in flag; the default still copies for every other caller), an in-place normalise (`np.subtract/np.divide(out=img)` — that one line used to allocate two more full-size temporaries at once), `del rgb`, `nan_to_num(copy=False)`, `clip(out=)` and `pack_unit(copy=False)`. **Measured with `tracemalloc`, not estimated: 5.00× the decimated array before, 3.83× after** — ≈ 520 MB → ≈ 400 MB on the owner's 3494×2470 mosaic, ≈ 2.9 GB → ≈ 2.2 GB at the 8000 px cap, on a button a beginner presses to print while a stack job may be holding its own canvases. **Bit-parity, and pinned as such:** a new test renders linear, display-space and Adjust-stretched masters through an independent out-of-place copy of the old path and asserts the PNG bytes are identical. The robust percentile is left exact (a strided sample would move pixels), so what remains is the stretch's own working set. Tests +2, the ratio one failing before at 5.00×. Engine-only. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.386.0** — the READY infra entry filed 2026-09-07: **`scripts/agent-dogfood.sh --mosaic` — a second, opt-in sample target shaped like the owner's shooting, so an Auto/editor claim can finally be checked on a mosaic.** `webapp/sample_data.load_sample(lib, shape="mosaic")` builds a separate target from **one shared star catalog**: 2×2 panels stepping 82 % of a frame (so overlaps hold the *same* stars), per-panel pointing jitter, uneven depth (6/6/6/3) and one panel shot through haze (×0.85 signal on a +8 % sky). Measured on the real thing: a 907×615 union canvas, **4.8 % genuinely uncovered**, coverage plateaus at 3/6/12/21, `coverage_is_mosaic` True and four `pointing_groups` panels — every one of which is structurally invisible on the single-field sample, which is how D1 survived twenty sweeps. The script loads it, stacks it, prints the trim Auto would apply (**7.9 %** today; above ~15 % is D1-shaped) and probes/edits it into `$SHOTS/mosaic/` so the field sample's page-height baselines are untouched. Default unchanged everywhere: the Dashboard button, `POST /api/sample` with no body, and the field sample's generated pixels are **bit-identical** (verified against the old implementation). Tests +7. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.385.0** — PRIORITY 3 (friendliness), the READY entry filed 2026-09-07: **the "Save / share" menu was built twice and the two copies disagreed — now one `SavePictureMenu` component serves the Target page's hero and every History run card.** The item set is the *union* of the two (the hero gains FITS, TIFF and "Copy caption"; the History card gains "Share the keepsake"), the wording is History's label-plus-hint idiom on both, and the North-up / nameplate toggles still reach exactly the JPEG-family downloads they did. Nothing removed, no new surface, no page height changed (the menu is closed by default). Frontend-only; tests +7 new component cases, two Target assertions that fail before. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.384.0** — PRIORITY 3 (get / enjoy / share), the READY entry filed 2026-09-07: **the picture he shares of a "Process target" run comes off the master instead of the 1024 px preview — and every share of any run stops re-reading that master.** `_native_picture_source` declined every display-space run (his main path: "Process target", "Reprocess everything", and every walk-away run once `auto_edit_on_autostack` is on), so its JPEG, keepsake, scale-&-compass, share and all three wallpapers were re-encodes of a 1024 px preview; and for a *linear* run it re-rendered the master on **every** request — 104 MB off the NAS per tap on his mosaic, nine taps to a run. New `_build_or_get_share_source` renders once through `pipeline.render_run_full_res_png` (the one place that decides which render a finished run *means*, so the share, the Full-res PNG button and the pictures archive cannot drift) and caches it beside the run as `<basename>_share.png` + `_share.sig`, modelled on the zoom clip: signature = preview stamp | master stamp | recipe hash | size | app version, written `.tmp`-then-renamed. One render at the largest size any hand-out needs serves them all; the share JPEG decimates the decoded cache (`Image.BOX`), never a second FITS read. Both files are registered in `RUN_ARTEFACT_SUFFIXES`, so they are deleted and pruned with the run. **A display-space run with no saved recipe still declines** — the plain render of its linear master is the *un-edited* picture — as do the baked-North-up and cropped-preview cases, unchanged. Tests +8, four fail-before; the two existing tests that pinned the old blanket decline now pin the recipe-less case they were really about, renamed in the same commit. Additive files only; no config, schema, API-shape or default change. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.383.1** — PRIORITY 3 (friendliness — a felt wait on a beginner feature): **a Sun or Moon video stack stops debayering the frames it is about to throw away.** `video/ffmpeg.iter_frames` demosaics a raw (CFA) capture once per decoded frame — ~350 ms a frame on the owner's 4,487-frame solar file — and `lucky.stack_video`'s second pass paid it for *every* frame before dropping all but `keep_percent` of them one line later, so roughly a third of a half-hour stack was debayering discards. `iter_frames` now takes `wanted: Collection[int] | None`; a frame outside it is still decoded (the byte framing demands it) but not demosaiced, and is yielded as **`None`** rather than skipped — so the caller's `enumerate` still lines up with the `keep_idx` pass 1 built, and no caller can ever mistake an un-demosaiced mosaic for a picture. Pass 1 is untouched (it grades on the colour frame's luma). The "is this really a mosaic" latch stays on the **first frame off the wire**, wanted or not, so a capture whose first frame is discarded still debayers correctly. Tests +5: the demosaic count is `n_graded + n_kept` (18, where it was 24) on a real ffmpeg-encoded `pal8` capture, and the stacked image is `array_equal` to the same run with the old eager decode — this is a skip, not a change. Engine-only.
- **2026-09-08 (backlog-readiness run, docs only) — D4 closed: the working list cut from 13,052 to 3,950 lines.** 47 shipped or closed entries archived verbatim in [`SHIPPED.md`](SHIPPED.md) and 46 sweep records, dogfood baselines, process and collision notes moved verbatim to [`PROCESS-NOTES.md`](PROCESS-NOTES.md) (both under a 2026-09-08 heading). Open residue worth knowing from the archived partials: ~~an in-UI destination picker for bulk upload~~ *(shipped v0.403.0)*; a 9:16 portrait zoom clip; a noise-delta picture on "Did it get better?"; auto-applying the classified preset; raw-OSC video and drizzle-upscale for Stack video — the three that need the owner are on his one-sitting list. The "Shipped" list below was compressed to one line per entry in the same pass (400 entries; full text archived verbatim in `SHIPPED.md`).
- **v0.383.0** — PRIORITY 3 (trust / friendliness), the READY entry filed 2026-09-07: **the Storage page says, with the owner's own numbers, that the subs in `incoming/` are the only copy there is.** The largest risk to his pictures is not a bug in this app — his raws live in `incoming/` and nowhere else, `copy_to_cache` is off so the app holds no copy, and nothing said so; the page's closing aside called the folder "worth having a backup of" in the same breath as "you can rebuild your whole library from them". That aside is now one plain sentence built from his data: *"Your 8,542 subs (44 GB) in incoming/ are the only copy AstroStack knows of. It reads them where they are and never writes there, and it keeps no copy of its own — nothing this app does backs them up. Keep a copy somewhere else."* With `copy_to_cache` on it says instead that the cache copies are working files "Clear caches" deletes — not a backup. **The numbers come from the `frames` rows, never from the folder:** new pure `Project.source_frames_under(prefix)` sums `source_size_bytes` over rows whose `source_path` has that literal prefix (`substr`, no LIKE escaping; trailing separator so `incoming2/` can't match), called inside the per-target `try` `get_storage` already opens — so answering never walks, opens or `stat`s anything under `incoming/` (AGENTS.md §10), pinned by a test that makes those calls fatal *and* proves the trap armed first. Rows predating `source_size_bytes` are reported separately, so the figure is honestly "at least". Four additive response fields with defaults + `frontend/src/components/incomingCopyNote.ts` (pure, takes the page's own byte formatter). Nothing removed; no new card. Tests +11, two fail-before; `tsc`/`vitest`/`vite build` clean. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.382.5** — 🟡 PRIORITY 3 (friendliness / trust), the third audit's **D2**: **the "installing ASTAP's star database helps" note stops firing at a night that is merely still being solved.** A scan ingests every new sub *before* any is solved, and `seestack/stackhealth.py`'s `unsolved` note counted every accepted sub with no `wcs_json` as a plate-solve failure — so mid-pipeline, on a healthy night, it announced *"Only 36 of 120 subs could be located"* and pointed the owner at a setup problem that does not exist, for as long as the solve took. Both terms now count only frames whose solve has actually **run**: new pure `_solve_was_tried` reads the `reject_reason='solve_failed:…'` mark a failed solve leaves (a failure deliberately does not touch `accept`), which is the same predicate `Project.solve_failure_reasons` already uses, so the note and the reject breakdown cannot disagree. Side effect worth having: the ratio a beginner reads is now the true failure rate rather than one diluted by the queue — 6 located / 6 failed / 300 pending reads *"6 of 12"*, not *"6 of 312"*. Conservative by design (a frame keeping a concrete `qc_error` reason reads as untried — undercounting keeps the note quiet, overcounting is the bug). Engine + copy only; no config, schema, on-disk, API or default change. Tests +2 fail-before, plus four existing fixtures given the mark a real failed solve leaves. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.382.4** — 🔴🔴 **D1, the third audit's headline find: Auto's border trim cropped every mosaic down to its panel overlaps.** `coverage_trim.well_covered_mask` measured "well covered" as half the map's **peak** — right on a single field (the peak *is* the interior), catastrophic on a mosaic (the peak is where panels **overlap**, so the threshold sat above every panel interior). Reproduced before changing anything, with the audit's own shapes: 2x2 @15% kept **8.0 %** of the canvas, 3x3 @5% **1.7 %**, 12x8 raster 1.5 %, and a 1x2 with unequal depths **dropped the thin panel whole** — while the single-field control returned its correct `(0.02, 0.02, 0.98, 0.98)`. New pure `coverage_trim.panel_coverage_level` measures against **one panel** instead: the lowest coverage level a real share of the canvas sits at. That one sentence is right for both shapes — a single field has exactly one such level and it *is* the peak, so that path is **byte-for-byte unchanged**; a mosaic has several and the lowest is one panel; unequal panels give the *thinner* one. Levels are found by relative tolerance (weighted coverage reads as 30±jitter, and integer bucketing would shatter it) above an absolute pixel floor (on a tiny map 8 % rounds down to "one pixel is a plateau"). **The reference is always ≤ the peak, so the mask can only grow — the worst case is leaving fringe in, never trimming a panel away**, and that property is itself tested. Both consumers move together (`render/thumbnail.stack_detail_mask`, the "My map" fade). Half the commit is fixtures: six tests shared a "thin single-frame fringe" that was **62 % of the canvas** — the same shape as the bug — and now share one ramped 4 px border, with no assertion loosened. Tests +8, three fail-before. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.382.3** — PRIORITY 1 (editor responsiveness), the second bite out of the same clause and the bigger one: **the live preview stops reading a mosaic's whole coverage canvas, twice, on every render.** `seestack/edit/proxy.py::_load_map` did `np.asarray(fits.getdata(path), dtype=np.float32)` and strided *afterwards* — the cast copies, so the run's **full-resolution** map was materialised every time, and that map is hundreds of MB at this owner's mosaic sizes. The editor asks for two of them (coverage + frame coverage) per render and fires two renders per edit, so one slider drag was four full-canvas reads and four full-canvas allocations before any op ran. Now: open with `memmap=True`, slice `[::step, ::step]` first, cast last — measured on a 480 MB map at the proxy's own step of 8, **2.65 s cold / 0.21 s warm → 0.011–0.021 s**, with identical values (the decimation picks pixels, the cast rounds each one; neither order changes which or what). The defensive 3-D collapse moves after the stride for the same reason. Tests +2 (the memory contract as its two observable halves — a memmap is asked for, `fits.getdata` is monkeypatched to raise and never reached — plus the float64 and 3-D reorder cases); the 133 existing coverage/leveling tests pass unchanged. Same signature, same values, nothing persisted or defaulted differently. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.382.2** — PRIORITY 1 (editor), the first bite out of the only thing the "Live preview" entry still listed as open — *responsiveness*: **the live preview stops re-solving the star field it solved a moment ago.** Several ops measure the whole image before they transform it (the stretch's per-channel stats, the tone curve's points, "Neutralize background"'s sky medians, and by far the largest, colour calibration's star detection + white-balance solve), and every render redid all of it from the top — twice, since the preview PNG and the histogram are two requests over the same recipe and the same proxy. New `webapp/edit_fit_cache.py` carries those measurements forward through the `EditContext.fit` channel the loupe already uses, but **only for the longest common prefix of enabled ops**: the first op whose id or params differ ends the prefix, so an op either receives the number it would have measured anyway or measures it. Measured on a 1500×1000 proxy with the one-click Auto recipe: **4.25 s → 2.39 s per render (1.78×)**, `np.array_equal(before, after, equal_nan=True)` **True**. Position-not-uid matching is load-bearing (a recipe posted without uids gets fresh ones per request, which would have made the carry a permanent miss); proxy geometry is in the key so a windowed render can never share one. In-process, bounded to 8 slots of small scalars, nothing persisted — a miss is exactly today's behaviour. Tests +10, four of them through the endpoints. Full entry, and the measured next slice (`frozen_deltas`, another 1.8×, 4.2e-7 apart), in [`SHIPPED.md`](SHIPPED.md).
- **v0.382.1** — PRIORITY 4 (image quality), a three-times-deferred real-data gate closed with numbers instead of another deferral: **"does the Auto denoise↔sharpen crossfade over-read a sky gradient as noise?" — no, and it has not since v0.225.0.** The entry was filed 2026-07-08 against the *level*-MAD `sky_sigma`, where gradient 0.00→0.05→0.10→0.20 of range moved it 0.015→0.028→0.054→0.098 and flipped Auto to *sharpen 0.0 / full denoise* by a gradient of 0.05. The local adjacent-pixel-difference estimator (v0.225.0, shipped for the mosaic grid regression) is blind to structure slower than a pixel, so running the entry's own ladder on the current code gives **0.0042→0.0039→0.0035→0.0030** — *down*, not up, because the tilt lifts the normalisation ceiling — with `_noise_fraction` 0 throughout, no denoise op added, and an identical sharpen amount. No product code changed; what ships is the pin: `test_a_strong_gradient_never_costs_a_clean_stack_its_sharpening` holds the *decision* across the whole feared range, where the existing sibling test held only the σ at one gradient. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.382.0** — PRIORITY 2 (autonomy) + the unblocking of a PRIORITY 4 gate: **the app starts collecting the real-data evidence its own gated highlight cue needs.** The automatic "your core is blown out" cue is deliberately real-data-gated — nobody knows how often a genuinely blown core occurs on the owner's stacks, or how severe — and runs keep meeting that gate and standing down while nothing accrues the measurement. Now every unattended auto-edit asks the editor's own solver what "Hold back highlights" would offer on the picture it just made and stamps the answer (`editor_auto_highlight:{run_id}`), **including an explicit `strength: null`** so "measured and clean" never reads as "never measured"; `pipeline.auto_highlight_summary` + `GET /api/auto-highlight-summary` aggregate it, and one dimmed line joins the Auto colour self-check on Settings → Maintenance. `editor.solve_highlight_protect` is the endpoint's body lifted out, so the button and the passive record cannot drift (with `uid=None` it solves against the recipe's *own* stretch — pinned). No pixel moves, no default flips; the proxy it measures on is the one the editor builds anyway, so a fresh run now warms it. Tests +16. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.381.0** — PRIORITY 2–3 (trust / autonomy), closing the "LEAD, NOT FINISHED" filed the same day: **the folder your scan walked past now waits for you on the Library page.** A bare `<T>/` beside `<T>_sub/` holding files the Seestar's naming can't vouch for — the owner's `NGC 6888`, 4,815 files — has been *reported* since v0.329.2 and *actionable* since v0.378.0, but only on the **Jobs page**, attached to one scan's result, and the scan that finds it is the watcher's, fired while nobody is looking. New `webapp/skipped_folders.py` has the scan **write the finding down** (one JSON value in the registry's existing `library_meta` table — the lead's feared "schema decision" was not needed), `GET /api/targets/skipped-folders` serves it, and `SkippedFoldersCard` shows it on the Library page with the same one-click "bring it in" (`BringFolderInButton`, now shared with Jobs so the two can't drift). **The part a standing card needs and a per-scan alert never did:** the convention keeps skipping the folder, so a card mirroring the newest scan would still be shouting after the owner acted — a remembered folder is therefore dropped as soon as its target owns *any* frame from inside it, and one that has left `incoming/` is forgotten. Polling never walks `incoming/` (pinned by a test that makes a walk fatal); nothing writes to it. Upgrade-safe: one additive meta row, one additive endpoint. Tests +23. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.380.0** — PRIORITY 1 + 3 (editor / friendliness), the completion of v0.379.0's beginner path: **a "Crop" button in the editor header, beside the app's two automatic crop offers.** Cropping is the edit a beginner is most likely to want *and* know the name of, and the only route to it was **Add operation → More operations → Crop** — the op is not in the Add menu's Common group — followed by four typed fractions. One click now adds the op (or **re-opens the recipe's existing crop**, via the new pure `cropDrag.ts::existingCropUid`, rather than stacking a second one whose fractions would be relative to the first's output; a crop the user had switched off comes back on, since pressing Crop *is* the ask), selects it, and opens the drag rectangle. **Placed in a group that already exists** — "Trim border" and "Re-centre" both end in the same adjustable Crop op — so it is not one more always-on banner, and it is hidden while a crop *proposal* owns the preview. **Measured, as the IA rule requires:** page heights byte-identical on the running app (phone editor **2,887 px**, desktop **1,841 px**, both unchanged; on a 420 px phone it shares the Auto-process row rather than starting a new one), nothing overflowing, no console errors. Nine existing `Editor.test.tsx` queries that reached the pipeline's Crop row by its bare text are now addressed by its own `aria-label` ("Select Crop") — more precise, not looser, and the reason one of them failed first. Frontend only. Tests +7.
- **v0.379.1** — PRIORITY 1 (editor), two refinements the browser probe of v0.379.0 asked for (no logic change): the crop **handles' grab area is 22 px around a 12 px marker**, so a handle is hittable with a finger on the 374 px-wide phone preview without eight chunky squares sitting on the picture; and the *"Keeping 62% × 55%"* caption takes `pointerEvents: "none"`, because it is drawn over the **top-left corner handle** — the one control on that screen you must be able to grab. Verified end-to-end against a running app (`Editor.tsx`).
- **v0.379.0** — ⭐ PRIORITY 1 (editor), a new beginner-facing capability on an op that already existed: **you can aim a crop by dragging it on the picture instead of typing four fractions.** `geometry.crop` was only ever reachable through the descriptor form's Left/Top/Right/Bottom sliders — fractions of a canvas that is 10,000 px wide on this owner's mosaics, chosen while looking at a decimated proxy. Selecting an enabled Crop op now opens a draggable rectangle on the live preview (body slides, eight handles resize, outside dimmed, *"Keeping 60% × 80% of the picture"* live), plus one-click **"Back to the whole picture"** and a plain-language note before a crop under a quarter of the frame costs real pixels. The sliders stay and follow along. **The rectangle is drawn over the recipe with *this op bypassed*** — a crop's fractions are relative to the image entering it, so dragging on the ordinary (already-cropped) preview would compound against itself; new `cropDrag.ts::cropDragBlockedReason` therefore **declines, and says why**, when any enabled geometry op sits after this crop (a Rotate, a Resize, or a second Crop, whose bypassed render would show *its* output). The overlay box's aspect is measured off the loaded image, since no endpoint reports the bypassed render's dimensions, and the rectangle waits for that measurement rather than risking an offset. The drag is local until release: one undo step, no per-pixel re-render, and the bypassed render is now keyed on the *other* ops only (`withoutOpKey`), which also makes the existing per-op Compare/Split cheaper. Frontend only; no engine, schema, config, on-disk or default change. Tests +39. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.378.1** — Tooling (no product code): **`scripts/agent-setup.sh` stops printing "agent env ready" over a `.venv` that holds nothing but pip.** A PyPI read timed out mid-resolve, `pip install -e ".[dev,web]"` died, and the `source`d script's `set -e` did not stop it — so the run met `No module named pytest` and had to work out that a perfectly good checkout was not the problem. It now retries the install once at a longer timeout, decides readiness by **importing** (`pytest, fastapi, numpy, astropy`) rather than by an exit status it cannot trust, and on failure prints the retry command plus the diagnosis — *this is an install failure, the checkout is fine* — and returns 1. Success path byte-identical. `AGENTS.md` §7 carries the same tell. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.378.0** — Autonomy / friendliness (PRIORITY 2–3), and a latent defect in a public API: **a folder the scan skipped as "your Seestar's own picture" can now be brought in with one click, instead of by renaming it inside `incoming/`.** `POST /api/scan`'s `root` field always read like a "re-scan just this folder" shortcut and was not one — `scan_and_organize` derives each target's name from the file's path *relative to the scan root*, so a root pointed **at** a target's folder left nothing to derive from and filed every frame under `Unsorted`. New `scanner.target_name_for_folder` (the convention's naming half, now shared so a scoped scan cannot fork a target) + `scan_and_organize(single_target=True)` → `_scan_one_folder`, which ingests the folder itself as one target and leaves out only what is still knowable per file, a `Stacked*.fit`. Surfaced where the problem is reported: the Jobs page's skipped-folder alert now carries the folder's path and a **"Bring \"X\" in anyway"** button, and its old advice — *rename the folder* — is gone, because that rename would have to happen inside `incoming/`, where the owner's raws exist in one copy and nowhere else (AGENTS.md §10). Off-path by construction: no `root`, or `root` = the incoming folder, is the ordinary scan, byte-for-byte. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.377.2** — PRIORITY 1 (editor), found by looking at the phone screenshot the new `--editor` drive took: **a quarter of the live preview was hidden behind its own toolbar.** The preview controls (Star mask / Compare / Split / Compare a look / Refresh / Zoom) were a `<Group>` at `position: absolute; right: 8; top: 8` inside the black stage — tidy at 1440 px (one row, 588×30 over a 653×435 image = **6.2 %** of the picture), and at 420 px the same six buttons wrap to **two rows**, 366×66 over a 374×249 image = **25.9 %**, on the width the owner actually reads this app at; a mosaic renders a seventh button. The `<Group>` now sits **under** the picture in the normal flow (`justify="flex-end"`), at every width — a move, not a removal, per the owner's own IA constraint, and with no new mechanism (no `useMediaQuery`, no duplicated `visibleFrom`/`hiddenFrom` DOM). The transient overlays that *label* the picture — the "Star mask"/"Proposed crop" captions, the coverage legend, "Updating…" — stay on it. Measured after on the same running app: **the picture did not shrink** (652.7×435.1 / 374×249.3, identical), desktop page height **1,841 px unchanged**, phone **2,815 → 2,887 px (+72 px, +2.6 %)** — the stated cost for 25.9 % of the preview back. Tests +1, fail-before (and the first draft of that test was vacuous because `closest('[style*="position: relative"]')` stops at the image's own box; it now walks up to the stage by `overflow: hidden`). Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.377.1** — Tooling for PRIORITY 1 (no product code): **the dogfood pass can now *drive* the editor, not just photograph it.** `scripts/dogfood_probe.mjs` screenshots `/targets/<t>/edit/<run>` in the one state it opens in, but every complaint AGENTS.md §1 records about the editor is about what happens **after a click**, and nothing in this repo’s tooling had ever clicked one — while two consecutive runs have reported the backlog dry, i.e. the running-app method is the one still finding things and it could not reach the highest-priority surface. New `scripts/dogfood_editor.mjs` (`agent-dogfood.sh --editor`) adds **every op the Add menu offers**, waits for the debounced preview to settle, and checks it actually re-rendered with no console error and no failed request, removes the op again so op N is measured against the same recipe as op 1, then undoes and redoes. The op list is read from the open menu rather than hard-coded (expand *"More operations"* first, read the label off the item’s first `<p>`, address by index because Common repeats, then dedupe → exactly the **21** ops `registry.all_specs()` holds), and removal targets `[aria-pressed="true"]` because `addOp` inserts on the correct side of the stretch rather than appending. `--editor` is hoisted out of the page-probe block so `--editor --no-probe` works. Off by default (a few minutes); AGENTS.md §7 says to add it on any run that touches the editor. **First run clean:** 21/21 ops previewed, undo+redo applied, no errors. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.377.0** — Friendliness / trust (PRIORITY 3), and the measured quantity two earlier runs said it needed: **"How's my stack?" can finally say what the black around a mosaic is.** A beginner meeting a wide black band on an unedited mosaic had nothing telling them whether the picture was broken, and the existing coverage note *structurally could not* tell them: `stacker.coverage_thin_fraction` is `count((cov > 0) & (cov < 0.25·peak)) / count(cov > 0)`, so the uncovered pixels are in neither of its terms — measured at **0.00 % thin on a canvas that is 36.6 % black**. New pure `stacker.uncovered_fraction` (share of *every* canvas pixel no frame reached; NaN counts as absence; `None` when nothing is covered, since an empty canvas is not "a picture that is 100 % black"), persisted as `stack_runs.uncovered_frac`, and a new `uncovered` health note that **explains before it offers** — on a diagonal mosaic the largest well-covered rectangle is genuinely small, so Trim border is named as a choice, not as the fix. **No `SCHEMA_VERSION` bump, deliberately:** `Project._check_schema` raises on a DB newer than the build, so a bump would stop the *previous* Docker image opening the owner's projects; the column arrives through `_reconcile_table_columns` instead, additive in both directions. Old runs heal off the coverage map they already wrote — `backfill_coverage_shares` fills both shares from **one** read. Threshold measured, not chosen (`_UNCOVERED_SHARE = 0.12`): eight real `run_stack` geometries put the honest cases at 1.1–5.1 % (reprojection leaves a NaN margin, so "any black at all" would fire on every stack ever made) and the genuinely ragged ones at 19.8 % / 36.6 %. No frontend change (`kind` is a plain string; the card keys off `action`). Tests +21. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.376.2** — Friendliness / performance (PRIORITY 3), measured before it was built (no pixel changes): **the Sky map stopped re-reading every target's master FITS on every visit.** The map requests one `sky-overlay` per target with a stack, each of which runs `stack_coverage_mask` over the whole master cube — **14–23 ms warm on a 104 MB (3494×2470×3) mosaic master**, which is what **declines shape (b)** (a composed-RGBA cache would buy tens of milliseconds and own an invalidation bug), but those megabytes come **off the NAS** cold, per target, on every visit and reload — and `Cache-Control: no-store` forbade even keeping the copy a revalidation would refer to. New `_file_stamp` / `_derived_image_etag` / `_etag_matches` give the response a strong `ETag` over the preview's and the master's `mtime:size`, `preview_north_up_deg`, `preview_crop_json` and `webapp.__version__`; `private, no-cache` keeps it revalidated on **every** request (so a History "Adjust" re-save can never serve stale) while making revalidation possible at all, and a matching `If-None-Match` is answered **304** from two `stat` calls. Weak (`W/`) and `*` validators handled. Headers only — no body, endpoint, config, schema, on-disk or default change. Tests +2, both fail-before. Four sibling `no-store` image endpoints left open on purpose: same shape, different invalidation inputs, none measured. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.376.1** — Performance, measured on the owner's shape (no behaviour change): **the Stack page stopped building the same mosaic canvas twice per load.** `routes/Stack.tsx` ran two `stackEstimate` queries — the sizing for the options on screen, and a fixed `drizzle: true, scale 1.5` feasibility probe behind the proactive drizzle nudge — and both went through `estimate_stack`, whose whole cost is `mosaic.compute_mosaic_canvas`: one stored WCS read per **sub**. The second request re-derived the identical canvas because it asked about a different *drizzle scale*, a knob that multiplies the canvas's output and cannot move the canvas. `estimate_stack` is now split into `estimate_stack_basis` (the expensive, options-independent half → the new frozen `StackCanvasBasis`) and `estimate_stack_from_basis` (pure arithmetic), composed back into an unchanged `estimate_stack`; `mosaic_canvas` is the one option the canvas depends on, so a basis **refuses** options that disagree with it rather than silently sizing the wrong canvas. `/stack-estimate` gains an additive `drizzle_probe` sized off that shared basis at `DRIZZLE_PROBE_SCALE = 1.5`, built from a fresh `StackOptions` so the rejection knobs can't make the nudge flicker. Measured on a 9-panel **5,477**-sub mosaic: a Stack-page load's sizing work **2.18 s → 1.13 s**, a second sizing off a held basis **44 µs**. Upgrade-safe both ways — an older frontend ignores the key; a newer frontend against an older backend withholds the nudge rather than suggesting a run that might be refused. Shape (c) of the four-shape perf lead; (b) and (d) stay open. Tests +11, 4 fail-before. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.375.0 + v0.376.0** — ⭐ NEW BEGINNER FEATURE: **"My wishlist"** — save the objects *you* want to shoot (a `wishlist` table in the library registry, `Library.add_to_wishlist`, `seestack/wishlist.py`, `GET`/`POST`/`DELETE /api/wishlist`, `WishlistStar` on every life-list tile and on the Tonight page's catalog rows) and be told on the right night that one of them is up (`GET /api/wishlist/tonight` over the planner's own `nightplan.well_placed_tonight`, `WishlistTonightCard`). **No `LIBRARY_SCHEMA_VERSION` bump — deliberately:** the DDL lives in `_AUX_TABLES_SQL` and is re-run idempotently on every open (`_ensure_aux_tables`), because a bump would make the *previous* Docker image refuse to open the registry and turn a rollback into a bricked install. "Captured" is delegated to `lifelist.catalog_capture_status`, never re-derived, so the two screens cannot disagree. Self-hides on an empty list, no location, nothing up, an older backend, and while another night is picked. Tests +38. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.374.11** — Friendliness (PRIORITY 3) with a **verified bug** at its centre: **tapping "what does this do?" on a stacking option changed the option.** `HintLabel` — the *only* explanation surface for a descriptor-driven option, shared by the Stack form, Settings, the editor's op parameter panel and the editor's print-size control — hung `field.help` on a hover `Tooltip` around a bare 14 px `<svg>`. It is passed as a `Switch`'s `label`, which Mantine renders **inside a `<label>`**, so a click on the icon activated the control: driving the pre-change component directly, one click on a boolean option's icon fired `onChange(true)`. A phone has no hover, so that click is the only gesture a beginner has for "what does this do?" — it flipped their setting and showed them nothing. The icon is now a real control (`UnstyledButton component="span" role="button" tabIndex={0}`, controlled tooltip opened by tap, hover *or* focus, `preventDefault()` on the click). **A span and not a button is load-bearing:** a `<button>` inside that `<label>` is a *labelable* element, so the field's label would name two controls at once — it broke seven `Settings.test.tsx` queries the moment it was tried, and reads the same way to a screen reader; the `aria-label` is generic (*"What does this do?"*) for the same reason. **No page gets taller** — same icon, `lineHeight: 0`, no padding, no new prose — and hover is unchanged for anyone with a mouse, while keyboard users reach the hint for the first time. Second slice of the "a Tooltip is invisible on a phone" entry, taken at the shared component rather than one route. Frontend only; tests +7, four fail-before.
- **v0.374.10** — Friendliness / trust (PRIORITY 3), copy only: **the grainier-restack note stops saying "about 2400% more background grain".** A manual restack of a handful of subs against a 500-sub master really is that much grainier — arithmetically right, and it reads as a bug, on the one note whose whole job is to be trustworthy when the picture got *worse*. New pure `format.formatMoreThan` says a gap past a tripling as a multiple instead — *"about 25.0× as much background grain as your 14 May one"* — and returns the **joining word** with the number, because the phrasing change moves the preposition (*more … than* → *as much … as*) and that is exactly where a hand-assembled sentence breaks. The ordinary band is untouched, which is where nearly every real firing lands (the nudge's bar is ~17.6 % more grain), and 200 % itself still prints as a percentage — both sides of the crossover are pinned. A non-finite, zero or negative gap prints "about 1% more" rather than `NaN`. `percent_cleaner`, the mirror note's number, needed nothing: a fraction *less* is bounded below 100 % by construction. Endpoint and engine untouched; frontend only. Tests +7.
- **v0.374.9** — Performance, the residue v0.374.8 filed with its number (no behaviour change): **reading a sub's stored solution stops re-verifying a FITS header card by card.** `wcs_io.wcs_from_text` went through `astropy.wcs.WCS(Header.fromstring(text))` at **0.85–1.05 ms** a frame, and `mosaic.compute_mosaic_canvas` reads one per **sub** — the last ~4 s of the ~4.7 s `/stack-estimate` (fired **twice** per Stack-page load, and again on every drizzle/canvas toggle) and `/rejection-outlook` (every Target-page load). The cost is not the projection maths: it is `Card._verify`, paid building the `Header` *and* again on every `key in header` lookup. New `_wcs_from_plain_tan_text` scans the fixed-format 80-column cards itself and assigns onto a bare `WCS(naxis=2)`: **0.85 ms → 0.07 ms** a header (12×), `compute_mosaic_canvas` on a 9-panel **5,477**-sub mosaic **6.02 s → 0.89 s** (6.8×), `estimate_stack` on a real 5,477-row `project.sqlite` **6.04 s → 1.06 s** (5.7×), and every real stack and plate-solve read benefits too. **A pure optimisation, pinned as one:** across ten header shapes (our own CDELT and CD serialisations, an ASTAP sidecar carrying CD beside CDELT+CROTA, the legacy CDELT+CROTA2 convention, half-written CD/PC matrices, a seam frame, a near-pole frame) the fast WCS re-serialises **byte-identically** through `to_header(relax=True)`, records the same `pixel_shape`, and transforms a pixel grid to **bit-identical** RA/Dec; `test_mosaic.py` pins the union canvas identical with the fast path disabled. `CROTA` is handed to wcslib via `wcs.crota` rather than re-implemented. Anything the scan doesn't fully understand — SIP, `PV`, a non-TAN or galactic projection, a third axis, non-degree units, a duplicated keyword, a length that isn't a whole number of cards — returns `None` and falls through to astropy's own read, so no keyword can be silently dropped and a bare `END` sidecar still reads as an unsolved frame. Shape (a) of the four filed; (b)–(d) stay open with their care notes. Entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.374.8** — Performance, found by running the app at the owner's scale (no behaviour change): **two endpoints took ~14 seconds each on a 5,477-sub target.** Sweeping all 36 per-target read-only GETs (enumerated from the app's own OpenAPI schema) against a 9-panel, 5,477-sub mosaic found the distribution sane except for `/stack-estimate` (**13.8 s** — the Stack page fires it *twice* and refetches on every drizzle/canvas toggle) and `/rejection-outlook` (**13.3 s** — the Target page NoticeBoard, every load). Both run `mosaic.compute_mosaic_canvas`, which calls `wcs_io.footprint_radec_deg` once per **sub**, and that transformed the four corners with four separate `pixel_to_world` calls — each building a whole `SkyCoord`. One vectorised `all_pix2world` instead: **1.299 ms → 0.011 ms** a frame (118×), `compute_mosaic_canvas` **13.87 s → 4.75 s** for the identical `3494×2470` canvas, the two endpoints **→ 4.66 s / 4.77 s**, the whole 36-endpoint sweep **28.3 s → 10.6 s**. Deviation from the old path over 200 WCSs: **0.0**. Gated on a new `_is_plain_radec` so a galactic WCS is never read as RA/Dec (it keeps the old path, which declines it), and fast-path failures fall through so a frame with no size still answers `None`. Every real stack benefits too. Entry in [`SHIPPED.md`](SHIPPED.md); the residual `wcs_from_text` cost is filed below with its number.
- **v0.374.7** — Performance, measured on the owner's own shape (no behaviour change): **the shared mosaic-panel gate stopped clustering one row per sub.** `seestack/stack/pointings.py::cluster_pointings` is single-linkage union-find, **O(n²) in pure Python**, and `pointing_groups` — the one gate QC grading, quality weighting, photometric normalization, the transparency baseline, the session recap and bulk-select all delegate to — was handed a whole target's frame list, as was `detect_mixed_pointings` (the pre-flight of every unattended stack once `mixed_pointing_guard` is on). `mosaicmap` had already solved this for itself in v0.352.x by folding onto a 0.01° grid; the fold now lives in the engine as `fold_pointings` + `_cluster_distinct`, so all seven paths get it. On a 9-panel, **5,477-sub** mosaic (441 distinct cells): `pointing_groups` **1.152 s → 0.012 s** (96×), `detect_mixed_pointings` **2.650 s → 0.021 s** (126×) — ~3.5 s off a stack (three calls), and one call off every scan and two Target-page endpoints. **Nothing moves:** 0.01° is 25× below `PANEL_LINK_DIST_DEG` and 300× below `LINK_DIST_DEG`, every input index gets its own cell's label, `eligible`/`weights` are summed per cell, and the mixed-pointing verdict carries each cell's true sub count and true summed unit vector so `majority`/`others`/`separation_deg` stay the unfolded numbers. Verified by sweep — **664 configurations** with panel separations straddling both link distances exactly, zero mismatches against the rule spelled out on `cluster_pointings`. Two rails (a link distance near the grid, and an already-distinct set) fall back to the exact clustering. Entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.374.6** — Backlog curation, measured not guessed (no code change): **the standing "the Library page walks the library twice per refresh" perf watch item is closed — it costs ~196 ms, so caching it would buy nothing and risk a stale cleanup list.** The entry (filed with v0.319.3–4) asked for exactly this before anyone added a `registry_cache` layer. Built the owner's own shape — 6 targets / ~25k frame rows, the confirmed `M 3` + `M 3_SUB` duplicate pair at 5,477 + 5,455, the genuine `NGC 6888` two-folder pair at 4,815 + 3,110, and a mosaic pair, all plate-solved so both endpoints actually do their confirmation work — and timed the two endpoints the page polls together: **cleanup-suggestions ~106 ms, merge-suggestions ~105 ms, one refresh ~196 ms**, against `/api/targets` at 2 ms. Half of that is the duplicated walk, so the whole prize is ~100 ms on a page that is not polled in a loop — well under the staleness bug the entry itself warns the cache would introduce. Entry cut to [`SHIPPED.md`](SHIPPED.md) with the method, so nobody re-measures it.
- **v0.374.5** — Coverage gap, test-only: **every read-only endpoint is now pinned to *answer* on a brand-new install and on a target that has never been stacked.** Those two states are the ones a beginner meets first and the ones the suite tested least — nearly every `tests/webapp/` test builds, solves and stacks a library before it asks anything — so a divide-by-zero-frames or an `[0]` into an empty run list would have surfaced first on somebody's first evening. `tests/webapp/test_first_run_endpoints.py` sweeps **90** endpoints enumerated from the app's **own OpenAPI schema** (52 parameterless + 38 per-target), so a route added next month is covered the day it is added, and asserts only *no 5xx* — 404 and 422 are honest answers here, and each endpoint's own tests pin what it should say. Guarded against rotting into a vacuous pass: each sweep asserts a floor on how many paths it found, and a third test points the helper at a deliberately-crashing route and requires it to report exactly that one. All 90 answer on `main` today — a net, not a fix. Entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.374.4** — Friendliness / trust (PRIORITY 3): **the sensor-defect census stops printing a healthy sensor's share as "0.000%", and stops saying "1 hot or dead pixels".** `defect_note` formatted the share as `:.3f`, but the band a *healthy* sensor lands in is below what three decimals can show — `seestack.calibrate.defects` puts real sensors at 1e-5..1e-3 of the sensor (0.001 %–0.1 %), so ten broken photosites on the Seestar's 2 MP sensor (0.00048 %) printed as **0.000%**, which reads as a broken readout on exactly the masters worth reassuring about. New `_defect_share` says **"less than 0.001%"** below the cut — the same words and the same cut `skyCoverage.formatSkyFraction` already uses for the identical problem, so the app has one voice for "too small to print" rather than two. And the singular case is spelled out (*"1 hot or dead pixel"*, *"one of the camera's photosites is broken"*, *"repair it"*), because a sensor with exactly one bad photosite is a real and good outcome. Measurement, refused-map warning and the clean-sensor silence untouched; 2 tests fail before. Copy only. Entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.374.3** — Trust / friendliness (PRIORITY 3), honesty core: **the broken-pixel repair offer names its exception before the click, not one click after.** `calibration.defect_repair_offer`'s **on**-state carried a careful guard — a target that pressed *Save as defaults* between v0.367.0 and v0.374.0 has an explicit `repair_sensor_defects: false` in its own blob, and a blob wins over `default_stack_options` in both readers, so the copy counts those targets (*"…except 1 target"*). The **off**-state, the one the reader acts on, made the same universal claim (*"for every stack, including the hands-off ones"*) with no guard, and only revealed the exception *after* the button was pressed — the v0.374.2 shape again: two states of one fact, and the one read first was the wrong one. `n_overridden` now qualifies both, in each one's own tense (*"— 1 target would keep its own setting"*, with the why and the how-to-include in the tooltip), and the router's walk is gated on `_offer_wanted` alone rather than on the switch being on: a library with nothing repairable still never pays for it. Reachable on a live in-place upgrade precisely because v0.374.0 deliberately does not migrate existing blobs. Three tests fail before. No config/schema/on-disk/default/response-shape change. Entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.374.2** — Friendliness (PRIORITY 3) with a correctness core: **the Stack form's streaked-frames caution stops advising a setting that cannot work.** `Stack.tsx`'s hand-written `rejectionOn` — `(auto_reject && n>=3) || (sigma_clip && n>=4) || (min_max_reject && n>=3)`, a copy of the *dispatch* gates — meant that on a **1–2 sub** stack every term was false whatever was ticked, so the form told a user whose sigma clipping was on by default that *"this stack has no per-pixel rejection enabled"* and offered a button to turn on the setting that was already on and cannot run at two subs, while `rejectionReachNudge` said the opposite two inches away. The predicate is gone: `rejection_reach` gains an additive **`best_available`** (the same engine helper asked with `auto_reject`/`drizzle_reject` set — "could *anything* take a lone trail out at this depth?", sized by a mosaic's `panel_depth`), and the new pure `streakRejectionAdvice` decides the sentence from it. Where a method reaches it names **Auto outlier removal** (honest at every depth, unlike sigma clipping — the same correction v0.323.1 and v0.334.1 made on two other surfaces) with the one-click fix, or drizzle's own rejection on the drizzle path; where nothing reaches it names the sub count needed and offers **no button at all**. The two halves now split one question — `rejectionReachNudge` owns "you asked for rejection, will it reach?", this owns "you asked for none, should you?" — so they cannot contradict each other; `minMaxRejectHint` still supersedes on the 3–10 band, pinned by a test. Additive response key only; no config/schema/on-disk/default change and the peak is provably unmoved. Entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.373.0** — Friendliness / "enjoy + come back tomorrow" (PRIORITY 3), a **new beginner feature**: **the Dashboard finally says how many of the 110 Messier objects you've photographed, and links to the life list.** `/life-list` has existed since v0.279.0 and nothing on the home screen ever pointed at it, so the number that is its whole hook was one nobody saw. New read-only `GET /api/life-list/counts` serves *just* the tally through the same `life_list_summary` over the same `catalog_capture_status` the full route uses — a test asserts the whole counts block is byte-identical between the two, so the Dashboard sentence and the life-list page's header can never disagree — and it is a separate route because the Dashboard asks on every visit while the full response carries ~160 catalog rows plus a preview stat per captured target (a `Dashboard.test.tsx` case pins that `getLifeList` is never called). **The IA rule decided its shape:** not a seventh stat tile (the grid is `lg: 6`) and not another card, but one quiet line in the same grouping as the sky-coverage read-out, whose own comment already says *"a new fact joins a grouping instead of becoming one more block"*. Pure `components/lifeListLine.ts` owns the words and changes the tail with how far along you are — plain count → "over halfway" → "just N to go" → "the whole list" — and refuses a nonsense tally rather than printing one. **Self-hides at zero captured**, so a fresh install never meets a 0-of-110 scoreboard. Additive/read-only; no schema, config, on-disk or default change, and the line stays absent against a backend without the route. Ships slice (i) of the life-list follow-ups; (iii) share-the-grid stays open.
- **v0.372.1** — Maintainability in service of correctness (no behaviour change): **one shared *real* display-space fixture, `tests/displayspace.py`, plus the guard-on-the-guard that stops a fixture silently ceasing to test anything.** A1's sting was that the regression test written for that exact defect in v0.210.6 **passed while the bug was live** — its fixture was `clip(sky + noise)`, which has no hard shadow clip, and the shadow clip *is* the bug. `real_stretched_stack` / `sky_truth` / `clipped_fraction` / `assert_shadow_clip` now live in one place; `test_edit_curve.py` reads them instead of its own copy and `test_edit_levels.py` gained the real-fixture pair the entry asked for. **Measured on the way:** `suggest_levels_points` returns **black = 0.0** on genuine `autostretch` output (its 1st percentile lands inside the 1.08 % zero spike) where the synthetic fixtures return 0.05–0.13 — correct, but not what those fixtures describe, so it is now pinned; `measure_sky_cast` was probed on the same fixture (deviation 0.00035, neutral) and cleared rather than migrated. Degenerate/flat fixtures deliberately left alone. Ships the ⭐ maintainability idea filed 2026-09-02; working in [`PROCESS-NOTES.md`](PROCESS-NOTES.md).
- **v0.372.0** — Autonomy + trust (PRIORITY 2/3): **a target stops silently ignoring your global settings — the Stack form now names every saved option that overrides them.** "Save as defaults" persists the *whole* form, so a target saved months ago carries an explicit value for every option that existed that day (a string of `false`s for checkboxes nobody opened), and its blob wins over `default_stack_options` in **both** readers — the form's seed and `pipeline._stack_target(auto=True)`. A switch flipped globally afterwards therefore never reaches that target, for ever, with nothing saying so; v0.371.0 hit exactly this with `repair_sensor_defects`. New pure `walkaway.pinned_stack_options` + read-only `GET /api/targets/{safe}/stack-defaults/pinned` + a self-hiding note inside the form's existing flow (no new page, no banner) name each pinned option and both its values, with a one-click **"put my global settings back in the form"** that saves nothing — *Save as defaults* stays the reviewable moment. **The baseline is what makes it honest:** comparing against `default_stack_options` alone fired on *every* target that had ever pressed Save (`get_stack_defaults` seeds a never-configured form with `auto_reject: True` while the descriptor default is `False`), so it compares against `_merge_stack_defaults(settings, None)` — the seed this very form would have been given — extracted from `get_stack_defaults` so the two can't drift. `_same_option_value` keeps `False == 0` from glossing a type change as agreement while `3`/`3.0` still compare equal. Shape (a) of the ⭐ lead; (b) save-the-delta and (c) drop-stale-keys stay open with their care notes. No behaviour change to any merge. Entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.371.1** — Image quality / data integrity (stacking-engine-class per §1): **amp glow read as broken photosites — `find_sensor_defects` flagged healthy pixels wherever the sensor was legitimately noisier.** The threshold was `DEFECT_SIGMA` × the MAD of the residual over the *whole* CFA plane, but a master dark's noise is not stationary — amp glow is dark *current*, which carries shot noise, and the glow corner is a small fraction of the sensor, so the plane-wide MAD is set by the quiet bulk and the bar sits below the glow's own grain. Measured on a master built the way the camera builds one (mean of 20 Poisson+read-noise frames) with **every photosite healthy**: **133 flagged at 2,000 e⁻ of corner glow, 1,564 at 20,000** — each then overwritten from its neighbours on every sub of every stack, and reported by the v0.370.0 census as broken pixels in the owner's camera. It survived 20+ tests because the existing fixture adds read noise of *one fixed sigma everywhere*, so its glow is a change of level only; the new `_shot_noise_dark` fixture is what catches it. Fixed by `_local_robust_scale` — an upper percentile of |residual| per 16×16 block (a MAD under-reads it nine-fold, because in a steep gradient the local median lands on the centre sample itself) — with the threshold as `sigma × max(plane_wide, local)`, so it can only ever **rise**: the new map is a provable subset of the old, and a clean stationary master's answer does not move. **P80 and not higher is set by the refusal guard** — at P90 a master with a tenth of the sensor spiked stops being refused and starts being repaired. After: 0 false positives at every credible glow with all 12 planted defects still found. Opt-in feature, no default flipped. Entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.371.0** — Autonomy + friendliness (PRIORITY 2/3): **the v0.370.0 sensor-defect census gets its button — one click repairs the broken photosites on every future stack, including the hands-off ones.** The census named `repair_sensor_defects`, but naming is not reaching: it is a checkbox in the Stack form's *advanced* group, so acting on the line meant opening a collapsed disclosure to find a setting by name — once per stack — and the walk-away chain (`_stack_target(..., auto=True)`) sees no form at all. New pure `calibration.defect_repair_offer` + `POST /api/calibration/defects/repair` write the option into the **global `default_stack_options`**, the one place both `get_stack_defaults` (the Stack form's seed) and the unattended merge read — pinned by a test asserting it through `GET .../stack-defaults`, the reader itself. **Silent unless some master reports defects a repair could actually fix**, so a clean sensor and a *refused* map (where the switch would repair nothing) both offer nothing; and no count is quoted, because which master supplies the map depends on what is bound at stack time. **And the on-state stays honest about the one case that would make it false:** "Save as defaults" persists the *whole* Stack form, so a target saved before this existed pins `repair_sensor_defects: false` in its own blob and wins over the global — the copy counts and names those targets (*"…except 1 target"*) and says how to include one, and the per-target walk is only paid for when the switch is on *and* something is repairable. Exactly reversible from the same control — off *removes* the key, leaving the options blob byte-for-byte as it was. Read-modify-write is server-side, so a click cannot clobber another default. No pixel moves, no shipped default flipped. Entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.370.0** — Autonomy + friendliness + image quality (PRIORITY 2/3/4): **"does my camera have broken pixels?" — the Calibration page answers it, and names the one switch that fixes them.** `repair_sensor_defects` (v0.367.0) repairs exactly the broken photosites from the master dark, but it is an *advanced* Stack-form checkbox, off by default, and nothing anywhere told the owner either that their sensor has broken pixels or that the repair exists — so in practice it was invisible. New `defects.census_sensor_defects` (the per-phase measurement extracted into `_candidate_mask`, so `find_sensor_defects` is unchanged) reports the count **and** whether the map was refused — the two cases the repair path deliberately collapses — served by a read-only `GET /api/calibration/defects` over every *pedestal* master (dark/bias; a flat is never censused) and rendered as one self-hiding line inside each master's existing name cell: the count plus the switch's exact label, or a yellow "too many pixels read as broken to repair from this one". **A clean sensor says nothing** — no action, no line. The number is pinned equal to `CalibrationMasters.load`'s own `n_sensor_defects` on a master with a no-data patch, so screen and stack can't describe two sensors; cached per file identity (a master FITS is immutable once written). No pixel moves, no default flipped. Entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.369.4** — Calibration / data integrity (stacking-engine-class per §1): **a no-data hole in a master invented sensor defects around itself.** `defects.find_sensor_defects` filled every `exclude`d (sanitized-to-0) sample with the *whole plane's* median before taking the local median, so inside amp glow the fill read as a defect **and** dragged the 5×5 baseline of the real photosites beside it — 115 flagged pixels (48 inside the hole) on a believable master with an 8×8 hole, each overwriting a good sample on every sub. Now filled from `_local_fill` (local mean of valid samples over `_FILL_WINDOW`), the MAD is measured over valid samples only, and `flagged &= valid` enforces the docstring's promise; a genuine hot pixel beside the hole is still found. Gated (opt-in `repair_sensor_defects`, imported masters only) and bit-identical for a master with no non-finite pixels. Entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.369.3** — Editor / one-click Auto (PRIORITY 1): **Adaptive Auto's first type-scoped nudge moved one *bucket*, not one step.** `auto_prefs.record_feedback` started a fresh `by_type` override at neutral, so with a global `brightness=+2` one "too bright" tap on a galaxy landed at **−1** — a three-step jump past neutral — and `+1` was unreachable, the taste oscillating between `+2` and `−1` forever (a per-type 0 was dropped, handing the parameter back to the global set). Now a type-scoped tap seeds from the aged global bias and moves one step, and a per-type 0 is *stored* while a non-zero global sits underneath it (`_coerce_bucket`/`_bucket_biases` `keep_zero`, `by_type` only; a bias that merely *faded* to 0 still falls back as before). Found by auditing the brand-new v0.369.x code. Entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.369.1** — Data integrity / calibration trust (treated as stacking-engine-class per §1): **the one-click discover→build path stops combining the frames its 4-header sampling missed.** `discover.classify_folder` confirms a folder's kind from `SAMPLE_HEADERS` (4) evenly-spaced headers, but `masters.build_master` then combined *every* shape-matching FITS — so a twelve-file folder whose sampled positions all read "dark" but which also held two lights built a "master dark" out of both (reproduced: 4 darks at 10 + 2 lights at 900 → a master averaging >300), and a contaminated master is subtracted from every frame it is later applied to. The shape rule can't catch it (same camera, same shape) and `header_kind_note` only *captions* it. New `build_master(require_declared_kind=...)` drops a frame declaring a different slot (reason `"wrong kind"`, already rendered by the Jobs page's `skipped_buckets`), **keeps** a frame that declares nothing and a flat-dark in the dark slot (reusing the now-public `discover.KIND_TO_MASTER`), and runs **before** the majority-shape vote. Default `False` ⇒ the manual build a user aimed at a folder is unchanged. Entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.369.0** — Editor + autonomy (PRIORITY 1/2), the last remaining sub-part of the ⭐ owner-requested **Adaptive Auto** ask: **recency decay — "recent feedback weighs more", which the original spec asked for and no slice had built.** A bias was permanent: three "too dark" taps saturated `brightness` at `+3` for the life of the library unless the owner found the opposite chip three times or reset the whole profile. Now a bias fades **one step per `DECAY_DAYS` (90)** without reinforcement (`auto_prefs._faded`), never crossing zero into the opposite taste, reading a future stamp (clock skew) as "just now"; decay applies at read time *and* before a new tap, so a tap builds on the taste actually in force and restarts that parameter's clock. **The fade is never silent** — new `steps_faded`/`fade_note` and an additive `AutoPreferencesOut.fade_note`, rendered in `AutoFeedback.tsx`, explain both a partial fade and the full one (where the "why Auto shifted" note would otherwise just vanish). **Upgrade-safe by construction:** decay needs a `stamps` entry, and a profile written before this shipped has none — it never fades and reads byte-for-byte as today. Slice **(b) is now complete**; only the spec's *"optional later"* slice (c) remains. Entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.368.0** — Friendliness + autonomy (PRIORITY 3/2): **"Was last night off for you?" — the newest night's star size against the owner's own usual, so dew / a wrong focus / a bad-seeing night is caught the morning after instead of weeks later in a mushy stack.** The app only ever trended FWHM *within* a session (`session_recap.focus_trend`, early third vs late third), which is structurally blind to a night that was soft from the first sub. New pure `activity_calendar.off_night(nights)` sits beside `sharpest_night` and reads only what `finalize_calendar` already folded — the Dashboard heatmap's cached per-night median FWHM — so it costs no extra library walk and shares one definition of "that night's star size". Silent unless the latest night is ≥1.30× the **median of the per-night medians** of ≥4 *earlier* qualifying nights, and never a diagnosis (seeing is not a fault: it names causes and asks the owner to look). Self-hiding `OffNightCard` in the Dashboard's existing **Recent** group beside `LastNightCard`, on the shared `["activity-calendar"]` key. Slice (b), the season-long sparkline, deliberately not built. Entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.367.1** — Stacking-engine hardening (PRIORITY 1 current focus), the traced-but-unreachable batch under "Bugs" drained in one pass, each with a fail-before regression in the new `tests/test_engine_defensive_guards.py`: `align.py`'s sub-pixel cap rewritten as `not (abs(dy) <= CAP and abs(dx) <= CAP)` at **both** sites, so a NaN shift reads as "too large" instead of slipping through every comparison and letting `nd_shift` wipe the frame; `weighting.py`'s FWHM ratio computed in `np.float64` so a pathological `fwhm_px` saturates to the 1.0 the formula already wants rather than raising `OverflowError` and sinking the run; `reference.py::pick_central_frame` filtering on `math.isfinite` to match `pointings.py`, so a NaN centre can't be picked as the whole stack's reference; `storage.py::prune_stack_runs`'s two closes nested like `get_storage`'s; and `solve/runner.py`'s "so it stops being re-offered" comment corrected to what the branch actually does (`build_solve_arglist` deliberately keeps offering a `solve_failed:` frame, which is right — an unreadable sidecar is usually transient). `align.py::extract_reference_patch`'s all-NaN fallback was found **already fixed** and struck. No behaviour change on any reachable input.
- **v0.367.0** — Image quality (PRIORITY 4) + calibration autonomy (PRIORITY 2): **repair the sensor's broken photosites from the master dark, in the raw Bayer domain, instead of relying only on the blind post-debayer local-median filter.** New pure `seestack/calibrate/defects.py` — `find_sensor_defects` measures each **CFA phase** against its own local median (so amp glow, a gradient and a per-phase offset all flag zero) and refuses any candidate set past 2 % of the sensor; `DefectMap` precomputes the same-phase neighbour gather once at load so the per-frame cost scales with the *defects*, not the canvas. `CalibrationMasters.apply_raw` repairs after the pedestal subtract and before the flat divide, so a hot site is erased while it is still one pixel and **a star can never be touched** — the map is measured on the dark. `StackOptions.repair_sensor_defects` is **off by default** and off measures nothing (§9); `DEFECTPX` → `sensor_defects` → one History line when it did something. Still open: validate the map's population on a real Seestar dark before anyone proposes defaulting it on. Entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.366.1** — Autonomy + friendliness (PRIORITY 2–3): **the "you already have darks" answer reaches the screen where the gap is actually noticed.** `_uncalibrated_advice` (the History Info panel's "why did this come out uncalibrated?" line) was silent in exactly the beginner case — no usable master in the library at all — because `diagnose_uncalibrated` only explains a *near-miss* master. It now falls back to `calibration.incoming_calibration_advice`, which names the frames sitting in `incoming/` ("You already have 40 dark frames in your incoming folder (“MyDarks”)"). The folder walk is the shared `cached_incoming_folders`, run only when there is no master-derived advice; `folder_as_master` shapes a discovered folder like a registry entry so "would this cover my subs?" is answered by the same `existing_master_like` that answers "does a master I own cover them?" — one definition, so the advice can't send anyone off to build a 30s dark for 10s subs, and a folder already built into a master says nothing. Entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.366.0** — Autonomy + image quality (PRIORITY 2/4): **"you already have darks" — the app notices calibration frames sitting in `incoming/` and builds the master in one click.** `seestack/calibrate/discover.py` confirms a folder from the **frames' own `IMAGETYP` cards** (`frame_kind_from_header`), never from the folder name — the naming-convention gate the entry refused to guess at simply stops mattering, and a camera that writes no card gets silence rather than a guess. `GET /api/calibration/incoming` + `POST /api/calibration/incoming/{id}/build` (folder re-resolved server-side from a sanitised id), `existing_master_like` reusing the unattended binder's own confidence bar so a covered folder says "you already have this one", and a self-hiding `IncomingCalibrationCard` inside the existing Calibration page. Offers only; builds nothing until asked and applies nothing after. Entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.365.0** — Image quality/trust (PRIORITY 4): **a finished picture says whether its rejection pass could have clipped anything, and the History Info panel stops calling a blind pass clean.** The stacker stamps `REJDEPTH` (samples on the deepest pixel — the literal peak, so "no pixel could be clipped" is provable), `REJNEED` and `REJREACH` beside the existing `REJ*` block; `lone_outlier_min_depth(mode, sigma_kappa)` is now the one definition of that bound behind `rejection_reach`, `stackhealth`'s `rejection_blind` note and the cards, and takes both the `"drizzle"` and `"drizzle-reject"` spellings. `rejectionSummaryText` claims *"data was already clean"* only when the run's own header says the pass reached — a thin mosaic panel now reads *"not enough subs on a pixel for it to reach"*. Deliberately no second paragraph: `StackHealthCard` already carries the explanation and the cure on that same page. Entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.364.0** — Friendliness (PRIORITY 3): **the "why were some frames left out?" breakdown gets a home a phone can reach, and its advice gets a button** — `RejectionBreakdownCard` in the Target page's existing Quality insight group (the breakdown had only ever rendered in a `HoverCard.Dropdown`, which has no touch affordance at all), plus `rejectionActions.ts` turning each bucket/verdict into the thing its note names — `settingsLink("plate-solving")` or the page's own Plate Solve — keyed off a new additive `verdict.key` from `webapp/rejection_summary._verdict` rather than matched on the copy. Entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.363.0** — Autonomy/friendliness (PRIORITY 2/3): **"First look" reaches the Dashboard** — the sharpest accepted sub of the target that has kept subs but no picture yet (`FirstLookStrip` + `pickFirstLookTarget`, inside the existing Recent insight group, self-hiding on a settled library), so the "did tonight work?" glance is answered on the landing page and not only on the Target hub. Entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.362.0 + v0.362.1** — Friendliness/autonomy (PRIORITY 3): **the "Your first image" checklist carries the whole journey — finish it in the editor, then save that version.** The card walked a beginner to their first stack and stopped, congratulating them on a linear, flat, dark picture and *mentioning* the last two steps in a sentence, because nothing cheap reported them. `_rollup_stacks` now also counts runs carrying a saved editor recipe and runs whose edit was exported (one `project_meta` prefix scan each on a project it already opens), served as additive `n_edited_runs` / `n_finished_pictures` — the second one the **union** of the export marker and the in-place auto-edit's `preview_display_space`, because a hands-off "Process this target" finishes the picture without any export and the first cut of this asked a walk-away owner to go and do it again (caught by booting the app with `scripts/agent-dogfood.sh`, not by reading it). The filed care note was answered with a measurement: **1.11 ms for both scans on a 400-run / 1,400-meta-row target, against 11.15 ms for the run walk already being paid there**, behind the existing 30 s cache — and a target with no stack runs is never asked (test spies on `iter_meta_prefix`). The card's "never show on an established install" guard moved to a new `firstImageHasPicture` (the four first-picture steps only), so adding steps cannot make the owner's box look mid-journey and pop a card onto a Dashboard it has never appeared on. Full write-up in [`SHIPPED.md`](SHIPPED.md). Tests: +4 `tests/webapp/test_stats.py`, +5 vitest (8 updated).
- **v0.361.1** — The other half of v0.361.0, and the surface its follow-on actually named: **the Tonight page's "Worth more time" list carries the same mosaic aim clause.** "Plan a night" is where a beginner decides where to point, and it renders its own `WorthMoreTimeList` off the same `/best-tonight` answer the Dashboard card uses — so shipping only the Dashboard left the where-to-point hint off the where-to-point page. The pure helper and the query moved into one `hooks/useMosaicAim.ts` that owns the three decisions both surfaces must agree on: the shared `["mosaic-map", safe]` cache key (no second request, and no way to name a different panel), the **lead pick only** (this list runs to eight rows), and `retry: false`. The map fixture moved out of `useMosaicAim.test.ts` into `test/mosaicMapFixture.ts` — importing a test file was registering its suites in the importing file and running those assertions twice. Frontend-only; no engine, API, schema, config, on-disk or default change. Tests: +4 `WorthMoreTimeList.test.tsx`, 2 moved.
- **v0.361.0** — Autonomy/friendliness on the owner's dominant workflow, and the follow-on v0.355.0 deliberately left open: **"Point here right now" now also says *which corner* of the mosaic.** The Dashboard's one recommendation answers *which target*; for a heavy mosaic user that is half the question, because a 3×3 whose total looks healthy can still have one corner at a fifth of the others, and pointing at the mosaic again spreads the night evenly over panels that don't need it equally. New `seestack.mosaicmap.aim_hint` says the map's own fact in one clause — same `panel_position_words` and `sharecard.format_duration` the long card sentence uses, so the app keeps one vocabulary for where a panel sits and how long an integration is rather than growing a second spelling per surface. Served as an additive, defaulted `aim_hint` on `MosaicDepthMapOut`; `PointHereTonightCard` reads it for the **lead pick only** (three project reads to annotate rows nobody is being told to shoot is a cost with no reader) through the Target page's own `["mosaic-map", safe]` cache key, so the two surfaces share one entry and can never name different panels. Silent on a single field, on an even mosaic, on a failed request and against a backend too old to send the clause — the frontend never rebuilds the sentence locally. No config, schema, on-disk, default or existing-field change. Tests: +4 `tests/test_mosaic_map.py`, +2 `tests/webapp/test_mosaic_map.py`, +7 `PointHereTonightCard.test.tsx`.
- **v0.360.0** — Understand/enjoy/trust, and the one gap two independent greps agreed was all that was left: **the Target page now offers "Compare with my last one".** `/compare` has been a full bookmarkable A/B route — split slider, per-side provenance, plain-language verdicts on noise, panel flatness and night count — since v0.150-ish, with entry points from the Gallery and per-row in History; a beginner who never opens History never discovered any of it, and *"is my new picture actually better than last week's?"* is asked from the Target page. New `CompareWithLastCard` is one link and nothing more, and it joins the existing **Story** tab beside the deepening reel (which answers the same question as an animation and self-hides on the same condition), so the page gains no always-on control. Pure `pickCompareWithLast` skips a run with no picture and an **editor export** — pairing one of those with the stack it came from answers "did my edit change anything?", which the editor already answers, not "did another two nights help?" — with `undefined` counting as genuine so an older backend is unchanged. The URL moved into one shared `sameTargetCompareHref` that History's Compare button now delegates to, so the two surfaces can't disagree about where the link goes. Frontend-only; no API, schema, config, on-disk or default change. Tests: +6 `compareWithLast.test.ts`, +4 `CompareWithLastCard.test.tsx`, +1 `Target.test.tsx`.
- **v0.359.0** — Friendliness, and the closing half of the v0.308.0 North-up follow-on: **Compare can turn both pictures North-up at once, so a Split or a Blink actually lines up.** The Seestar is alt-az, so two nights on one object land at different field rotations — which is precisely why scrubbing the split divider between them can be hard to read. The Gallery lightbox half was already built; Compare needed a different predicate, because on a *pair* the question isn't "would the turn do something?" but "would the turn leave the two agreeing?". Pure `compareNorthUpOffer(a, b)` offers the toggle only when at least one side has a rotation to apply **and** neither side is a run with no usable orientation (`directions` null) — turning one side of a pair whose other side can't turn makes the two agree *less*, so that case stands down. Reuses the shared `NorthUpViewToggle`, its `localStorage` key (off by default, remembered per viewer) and the `["annotations", safe, run_id]` cache the Target hero and the lightbox already warm. A view, not a save: nothing on disk changes. Tests: +11 `Compare.test.tsx` (5 on the helper, 6 driving the page).
- **v0.358.2** — Process/leverage, the second and last half of **R2**: **446 resolved entries (16,223 lines) were cut out of "Ideas" and appended verbatim to [`SHIPPED.md`](SHIPPED.md)**, taking this file from 29,432 lines to 13,207 — under half, and a third of the 40,915 it stood at before R2 began. Same shape rule as the "Bugs" move (struck through, or "✅" in the entry's first three lines), plus one carve-out: an entry whose own text names an open follow-up was **left here**, so the move cannot hide live work behind a resolved header — 28 entries, each now a small, safe split job. Losslessness verified line-by-line before the cut. **Grep [`SHIPPED.md`](SHIPPED.md), not this file, for anything already built.** One pointer line rather than 446, for the same reason the "Bugs" move gave.
- **v0.358.1** — Verified bug (found and reproduced while shipping v0.358.0), image/trust correctness on the file a beginner shares: **a picture that was *processed* and then saved North-up mis-measured itself.** `_unrotated_preview_size` recovers "how wide was this preview before the turn?" from the **master FITS** — i.e. the *canvas's* preview grid — but a "Process target" preview is a **crop** of the canvas, rendered off the ≤1500 px edit proxy and then capped at 1024 px, so it is neither that grid nor a fixed fraction of it. Both states land on one run through `_save_processed_preview(north_up=True)`, which is the owner's own workflow. Measured on a 1000×800 canvas trimmed to 70 %: the **shared JPEG's scale bar was drawn 1.43× too long — 10.2′ of sky under a "5′" label** — and the **wallpaper/zoom clip re-centred by the same ratio** (target pixel at 14.3 where the object was at 10.0). New `_unrotated_stored_preview_size` stops guessing the grid: it takes the crop box's shape and the stored PNG's size, turns the box with the renderer's own `follow_north_up_turns`, and reads the decimation off the ratio — scale-free, and through the same transform the picture took, so the `rot90` snap can't make them disagree. Full write-up in [`SHIPPED.md`](SHIPPED.md). Tests: +4 `tests/webapp/test_preview_crop_geometry.py` (the wallpaper one fails before with exactly that pair).
- **v0.358.0** — Friendliness/trust, and the decision the entry demanded first: **the scale bar and the compass survive a "North up → Save".** The shared JPEG has baked both onto exactly those pixels since v0.284.0 while the card it was shared from said neither could be placed — a screen↔file disagreement, not a missing feature. **Decision recorded (option b): the Moon sentence answers for the *field* the telescope saw, not for the frame.** The crop precedent's mechanism is "measure the visible rectangle" but its stated harm was *overstating the field*; on a turn those diverge, and re-measuring on the grown canvas would overstate what the owner shot by the growth factor. So `frame_arcmin`/`moon_comparison` stay the kept rectangle's, only `fraction` is re-based, and History's line says which rectangle it means (*"…that's the sky you captured; the black corners the North-up turn added aren't counted."*). `_turned_preview_grid` gives the pins, the bar and the rose **one** geometry (still the renderer's `follow_north_up_turns`); the payload gains `preview_directions` and widens `preview_scale_bar`; `storedPreviewScaleBar` takes it, so the copied caption gets its scale clause back. Pinned against `_sky_marks_for_run`'s own `bar_px`/`directions`, so file and screen can't drift. Full write-up in [`SHIPPED.md`](SHIPPED.md). Tests: +8 `tests/webapp/test_stack_annotations.py`, +5 vitest (1 rewritten).
- **v0.357.1** — Friendliness/housekeeping, the follow-on v0.357.0 left: **the prepared full-size download is disk the Storage page can name, and delete.** The archive lives outside the library in `<data_root>/exports/` and is easily gigabytes, so the page whose whole job is "what is using my disk?" walked straight past it. `StorageResponse` gains an additive, defaulted `exports_bytes` (same best-effort `_dir_bytes` as every other figure) and `DELETE /api/gallery/pictures-archive` gives the space back — idempotent, sweeping a stale `.part` with it, and scoped to the two paths the module owns so it cannot reach the library or `incoming/` (§10). The row self-hides at 0, which covers every install that never presses the button and any older backend. Tests: +3 `tests/webapp/test_pictures_archive.py`, +2 `Storage.test.tsx`.
- **v0.357.0** — Get/share + trust, and the honest end of a limitation the app already admitted in its own copy: **"Full-size versions" — every finished picture at print size, in one archive.** `/api/gallery/pictures.zip` streams each target's stored *preview* (capped at 1024 px by `_write_preview_png`), which the card has said since v0.308.1 is *"right for a phone album, not for printing"* — leaving one route to a printable backup: open every target and press **Full-res PNG**. It cannot be a second query parameter, because a target's native-resolution picture has no file on disk (it is rendered from the master FITS plus the run's saved recipe), so `POST /api/gallery/pictures-archive` submits a **`pictures_archive` job** with progress and cancel and `GET …/pictures-archive/{job_id}` hands over what it built — the editor's own submit-poll-download shape. The *which render* decision moved into one shared `pipeline.render_run_full_res_png` used by both callers, so an archive member is byte-for-byte the PNG that run's own button serves (pinned by a test); member naming moved to `picturesarchive.unique_entry_name` for the same reason. A pruned master falls back to its preview and the archive **says so** in `_preview_size.txt`; an unreadable picture lands in `_skipped.txt`. One archive at a time in a new `<data_root>/exports/`, written `.part`-then-rename, cancel leaves nothing, peak memory one picture. Nothing the user owns is written — no run, no preview, nothing in `incoming/` (§10), pinned by a snapshot test. Full write-up in [`SHIPPED.md`](SHIPPED.md). Tests: +11 `tests/webapp/test_pictures_archive.py`, +2 `MyDeepSkyWallCard.test.tsx`, +1 `Jobs.test.tsx`.
- **v0.356.2** — Follow-through on v0.356.0, from driving `header_kind_note` adversarially rather than reading it: **the note stops relabelling the owner's own frames, and stops being able to 500 the Calibration page.** A folder of flat-darks in the dark slot is correct, but was confirmed as *"All 40 frames say they are dark frames"* — they said flat-dark; a tally whose kinds aren't exactly the slot's now echoes what they actually said, biggest group first, with the single-kind wording untouched. And the tally comes out of the registry's own JSON, which nothing validates on read: a hand-edited string or list raised `AttributeError` inside `list_masters` (the whole page, not one row), and an unrecognised key was echoed verbatim as *"3 say they are xyz frames"*. Both now degrade to silence, the same answer the function already gives for "no frame said". Neither was reachable from the app's own writes — the function was correct for its producer and brittle for its store. Tests: +3 `tests/webapp/test_calibration.py`.
- **v0.356.1** — Autonomy + image quality, the other half of v0.356.0: **the Stack form says it too, where the master is actually used.** The form already checks whether a master *can* be applied (size, colour phase, exposure, temperature) but never asked what it is made of — and a master dark built from a night's subs passes all four, then subtracts a picture of the sky out of every frame. One pure `pickedMasterContentWarnings` over the four picked slots renders the server's own `header_kind_note` sentence as **one** orange alert (red on this form means "stacking will fail", and this stack succeeds — which is the problem) above the size/phase blockers (not four), first, because it is the only one of them that ruins the picture silently instead of failing loudly. Conditional on something rare — a master whose frames declared a kind *and* disagreed — so a confirmed-good master, and every master built before v0.356.0, add nothing to the form; pinned by its own test. Frontend-only, no API/schema/default change. Tests: +4 `calibrationFit.test.ts`, +2 `Stack.test.tsx`.
- **v0.356.0** — Autonomy + image quality: **a master calibration frame now says what its own frames claimed to be.** The Calibration build form takes a folder path in a text box and a kind from a dropdown, and nothing checked the two agree — point it at a night's subs with "Dark" selected and the app built a "master dark" out of light frames, registered it as a success, and every stack it touched then had a picture of the sky subtracted out. New `seestack.io.fits_loader.frame_kind_from_header` reads the standard `IMAGETYP` card **one-sidedly** (an exact table, never a substring test — `'Dark Flat'` contains both needles and gets its own `dark_flat` answer; anything unrecognised or missing is `None` = *"this frame didn't say"*). `MasterMeta.header_kinds` tallies it over the frames that actually reached the combine, and one pure `calibration.header_kind_note` turns that into one sentence used by **both** the finished build job and the Calibration master list, so the two can't drift: *"All 40 frames say they are dark frames."* or *"…40 say they are light frames (your subs). This is not a dark master — delete it and point the build at a folder of dark frames."* Self-hiding when no frame carried a card we recognise, which covers a camera that doesn't write one **and** every master built before this version. Read-only: nothing gates a build, filters a folder, or classifies anything at ingest — that was step (3) of the lead and stays undone. Ships step (2) of the `IMAGETYP` lead; full write-up in [`SHIPPED.md`](SHIPPED.md). Tests: +3 `tests/test_fits_loader.py`, +4 `tests/test_calibrate.py`, +9 `tests/webapp/test_calibration.py`, +4 `Jobs.test.tsx`, +2 `Calibration.test.tsx`.
- **v0.355.1** — Friendliness / the owner's standing "extremely busy UI" priority: **the Dashboard stops recommending the same target twice, one card apart.** `PointHereTonightCard` and `ContinueTonightCard` sit directly above one another (`routes/Dashboard.tsx:390-391`), share a teal `IconTelescope`, and rank the **same** owned library by two different rules — best-placed-now × marginal noise gain (`/api/plan/best-tonight` → `rank_targets_now`) versus closest-to-its-goal (`pickContinueTonight`) — so on a beginner's library they routinely landed on the same target and printed it twice under two headings in two voices. `pickContinueTonight` gained an `alreadyRecommended` argument, filled from the sibling's own answer through the shared `BEST_TONIGHT_QUERY_KEY`/`MAX_SHOWN`/`REFRESH_MS` constants (a cache hit — no extra request, and the two can't drift). The pick moves **down to the next-best started target** rather than blanking, so a beginner with several targets gets a second, genuinely different suggestion; with one, the card hides and the Dashboard is a card shorter. Nothing removed. An older backend that 404s `/best-tonight`, and undefined/null/empty exclusions, all reproduce the previous pick bit-for-bit. Closes the *"Finish what you started"* idea as **already built** (that capability is `/best-tonight`); full write-up + the closed entry in [`SHIPPED.md`](SHIPPED.md). Tests: +3 `continueTonight.test.ts`, +3 `ContinueTonightCard.test.tsx` (all 6 fail before).
- **v0.355.0** — Friendliness/planning, on the owner's dominant workflow: **"Your mosaic, panel by panel" — a small map of where your mosaic is thin.** The readiness figure already scales a mosaic's goal by panel count, so it says *how much* is left; nothing said **where**, and a mosaic whose total looks healthy can still have one corner at a fifth of the others — grainier than the rest of the picture however good the total is. New `seestack/mosaicmap.py` clusters the accepted+solved subs with the engine's **existing** `pointing_groups` gate (so a single field, a tight dither and an unsolved target all show nothing, exactly as today), sums each panel's own integration, lays the panels out North-up/East-left from their real RA·cos(dec)/Dec offsets, and says one sentence: the thin panel named positionally ("thinnest at the bottom-right"), or a plain "nothing is being held back" when the mosaic is even. Median not mean, so two thin panels can't drag their own yardstick down; plus an absolute 5-minute shortfall so a young mosaic isn't nagged. `GET /api/targets/{safe}/mosaic-map` returns `null` for everything that isn't a mosaic and the card then renders nothing at all; it joins the Target page's existing **Planning** tab rather than adding a tenth stacked card. The card mounts with the page, so the O(n²) clustering was measured (2.2 s at the owner's 5,400-sub scale) and folded onto a 0.01° grid before clustering (0.06 s), with the fold's sizes carried into the gate by a new defaulted `pointing_groups(weights=…)` so there is still exactly one gate. Full write-up in [`SHIPPED.md`](SHIPPED.md). Tests: +15 `tests/test_mosaic_map.py`, +3 `tests/test_pointings.py`, +6 `tests/webapp/test_mosaic_map.py`, +11 `MosaicMapCard.test.tsx`.
- **v0.354.2** — Image-quality/parity: **the picture on screen stops being half a step darker than the picture you download.** v0.354.1 made the six exports in `stack/output.py` round; every *other* float→byte site still spelled `(x * 255).astype(np.uint8)`, which truncates — so from that version the editor's live preview, the gallery/History preview, the full-res preview render, the loupe, the star-mask overlay and the deepening reel were each up to a whole step darker than the PNG/TIFF written from the same display-space pixels. Fifteen sites now go through `output.pack_unit`, two of them *exports* the v0.354.1 sweep had missed because they live outside `stack/output.py`: `printexport.render_print` (the file that goes to a print lab) and `webapp.video._write_tiff16` (the Moon/Sun still). `THUMB_VERSION` deliberately **not** bumped — a ≤1/255 change does not justify re-rendering every cached thumbnail on the owner's install. Three test helpers that re-implemented the truncating pack in their own expectations were re-pointed at `pack_unit`, not loosened: each stays an exact `array_equal`. Full write-up in [`SHIPPED.md`](SHIPPED.md). Tests: +7 `tests/test_preview_rounding_parity.py` (all 7 fail before), including a grep drift guard over `seestack/` + `webapp/` so a sixteenth site can't appear silently.
- **v0.354.1** — Image-quality/correctness: **every file the app writes stops being half a step too dark.** All six float→uint packs in `seestack/stack/output.py` spelled `(x * MAX).astype(np.uintN)`, which truncates toward zero — a systematic ~½-step downward bias on every PNG, JPEG and TIFF, and a break of the reversibility the "full data" linear TIFF's own description sells (recovered float low by up to a whole DN where rounding is honest to ±½). One shared `output.pack_unit` now `np.rint`s for all six, matching what `render/thumbnail.py` already did for alpha. `test_linear_tiff_no_clip.py`'s two strict-equality anchors were **re-reasoned, not loosened** — stated against the half-step band and still exact, which a truncating or a clipping packer both still fail. The display-side twins in `seestack/render/` are filed as a lead, not swept. Full write-up in [`SHIPPED.md`](SHIPPED.md). Tests: +6 `tests/test_export_rounding.py` (5 fail before), 3 re-reasoned in `tests/test_linear_tiff_no_clip.py` and 2 in `tests/webapp/test_video_sharpen_still.py`.
- **v0.354.0** — Friendliness/understand: **the Nights card says which of your nights the Moon washed out, not just the newest one.** v0.278.0 put a retrospective Moon verdict on the "Last night" card; the question behind it ("so which of my ten nights were any good?") had no answer, and a sharp night under a 96%-lit Moon 20° away reads as a good night in the Nights table. Every row now carries the same reading (`NightSummaryOut.moon`) and a dimmed **bright Moon** marker appears on `poor` nights, sentence in the tooltip + `aria-label` like the verdict and `ended early` markers; `good`/`ok` say nothing and nothing is ever filtered on it. The filed cost note was measured, not reasoned about: 24.6 ms/row would have added 0.74 s to a 30-night page, so `seestack.nightplan.session_moons` does the table in one astropy pass (0.075 s at 30) for **bit-identical** floats — `_moon_geometry` now delegates to `_moon_geometry_many`, so scalar and batched cannot drift. Unknown site / unsolved target / ephemeris failure all read as `null`, never as "fine". Full write-up in [`SHIPPED.md`](SHIPPED.md). Tests: +4 `tests/test_session_moon.py`, +6 `tests/webapp/test_target_nights.py`, +5 `NightsCard.test.tsx`.
- **v0.353.3** — Autonomy/correctness: **the app stops *recommending* a flat-dark the flat can't use.** `recommend_masters` — the answer behind the Stack form's "Use recommended" button and its ★ — ranked a flat-dark on exposure/gain/temperature alone, with no dimension awareness, so with two cameras' masters in one library the exposure-perfect-but-wrong-size dark out-ranked the usable one and one click pre-filled the silent mismatch v0.353.2 had to warn about. `_recommend_flat_dark` now skips a dark that `dims_conflict`s with the **flat** it would calibrate. One-sided, so an unrecorded dimension changes nothing on upgrade; the unattended `auto_bind_master_ids` never had the hole (its `_bindable` gate covers both). Full write-up in [`SHIPPED.md`](SHIPPED.md). Tests: +3 `tests/webapp/test_calibration.py`.
- **v0.353.2** — Broken-UX + image quality: **a mismatched flat-dark is no longer silently dropped, and the Stack form stops predicting a failure that never comes.** The flat-dark is the one calibration pick that is neither refused nor applied — `CalibrationMasters.validate` never looks at it and `load` just skips the subtraction on a shape mismatch — so the stack succeeded with the flat's own pedestal still baked in (measured: a 40 % vignette corrected to 1.0000 with a matching flat-dark, **1.1333** without), while the form rendered the shared red *"Stacking with it will fail"* blocker. `CalibrationMasters.flat_dark_shape_mismatch` + a `calibration_warnings` line now say it on the finished run, and a dedicated `flatDarkSizeWarning` (amber, measured against the **flat**, which is the engine's own test) says it honestly at pick time. Same carve-out as `biasSizeWarning`, one slot along. Also closes the third silent flat-dark found on the way: clearing the **Master flat** left `flat_dark_master_id` set, submitted, ignored (the engine only loads one inside `if flat_path:`) and invisible — `flatPickPatch` now clears it with its flat. Full write-up in [`SHIPPED.md`](SHIPPED.md). Tests: +3 `tests/test_calibrate.py`, +5 `calibrationFit.test.ts`, +1 `Stack.test.tsx`.
- **v0.353.1** — Engine parity: **`reproject_rgb` now trims the same frame edge the production path does.** The whole-canvas variant validated on a bare `0 <= src <= size-1` while `reproject_rgb_windowed` — the one `align_one` actually calls — insets by `FRAME_EDGE_INSET_PX` to keep the debayer/reproject artefact ring out of the stack. No production pixel moves (`reproject_rgb` has one caller, a test); the point is that the simpler signature is no longer a trap. Tests: +1 `tests/test_windowed_stack.py` (fails before).
- **v0.353.0** — Data-integrity / image quality: **a master flat built on a different colour-filter phase is refused instead of tinting every frame.** `CalibrationMasters.validate` compared `arr.shape` only, so a flat whose CFA phase is one pixel out of step with the lights was divided into the raw Bayer mosaic per *colour* — correcting every red photosite with a green value. It now fails fast (the same shape as the dimension guard) when both sides declare one of the four real phases and they differ; a dark or bias corrects each physical pixel, so it is never refused and earns an advisory instead. The unattended binders (`calibration.bayer_conflict`, `auto_bind_master_ids`, `_bind_saved_calibration_masters`) skip such a flat so a walk-away stack can't turn into an error, `coverage_miss_reason` names the phase, and the Stack form warns at pick time (`flatBayerWarning`). Inert on every master built before `BAYERPAT` was read. Tests: +7 `tests/test_calibrate.py`, +3 `tests/webapp/test_auto_stack_saved_masters.py`, +5 `tests/webapp/test_calibration.py`, +8 vitest.
- **2026-09-05 — the R2 bulk move.** 227 resolved entries and 24 QA sweep/audit records were cut out of "Bugs (fix these first)" (12,375 lines → 991) and appended verbatim to [`SHIPPED.md`](SHIPPED.md) and [`PROCESS-NOTES.md`](PROCESS-NOTES.md). **Grep those two files, not this one, for anything that shipped before v0.352.3.** One line rather than 227 auto-truncated ones: re-adding a summary per entry would put a fifth of the cut straight back, and both destination files are the grep target by their own front matter (AGENTS.md §2, §4).
- **v0.352.2** — Friendliness: **"shoot it in mosaic mode" now says how big a mosaic.** With the measured framing verdict on screen the Target page hides `ObjectInfoCard`'s catalogue line — and the panel plan lives inside it — while History renders no such card at all, so the one number answering the beginner's next question had nowhere to appear. `FramingVerdictNote` now renders `mosaic.text` from the shared `["identify", safe]` query (one request, not two), on the `partial` verdict only. Found by re-running `scripts/agent-dogfood.sh`, which also closed the "coverage vs panel count" lead: at v0.352.0's derived field the sample reads 15 % ↔ 3×3 = 9 panels, which agree. Tests: +3 `FramingVerdictNote.test.tsx`.
- **v0.352.1** — Trust/friendliness: **a mosaic picture is no longer called "your frame", nor told to go and shoot the mosaic it already is.** `framing_result_verdict` measures everything against the run's *canvas*, but worded all four verdicts as if that canvas were one frame — so on the owner's dominant workflow the "did I frame it well?" card claimed a multi-panel canvas was a single frame and advised "Shoot it in mosaic mode". A `canvas=` kind (`CANVAS_FRAME`/`CANVAS_MOSAIC`) read from the run's own `stack_runs.is_mosaic` picks the wording; every number is unchanged, and a run from before schema 8 (`is_mosaic` NULL) keeps byte-identical sentences. Tests: +6 `tests/test_framing.py`, +5 `tests/webapp/test_stack_framing.py`, +3 `FramingVerdictNote.test.tsx`.
- **v0.288.0** — Share/back-up: **"Download all my pictures" now really means all of them.** The zip walked
- **v0.287.4** — Editor/export parity: **the full-res PNG download now keeps the look you saved.** Tuning a
- **v0.287.3** — Data-integrity: **a plate solve is only believed when its WCS actually locates the frame.**
- **v0.281.0** — Autonomy: **a walk-away stack whose drizzle canvas won't fit now makes a slightly smaller
- **v0.281.0** (same change, the half it rests on) — Correctness/autonomy: **`StackOptions.unattended` — one
- **v0.280.0** — Beginner feature / friendliness (Builder, branch `claude/compassionate-galileo-4maz3z`):
- **v0.279.1** — Autonomy/trust (Builder, branch `claude/compassionate-galileo-4maz3z`): **"Your cleanest shot
- **v0.277.3** — Memory/hardening (Scout, branch `claude/vigilant-knuth-yeeeim`; found by the calibrate-masters
- **v0.272.1** — Friendliness: the Stack form's **Lucky imaging** knob was labelled "keep best **%**" but its
- **v0.270.4** — 🟠 The editor levels a mosaic's sky by **frame count**, the way the stack that produced it
- **v0.345.4** — the `astropy.stats` "Input data contains invalid values" warning is no longer emitted per frame / per canvas (`bg/per_frame.py`, `bg/final_gradient.py`, `qc/metrics.py::estimate_sky`); measured to fire only on a NaN-bearing (mosaic) canvas. Full entry in [`SHIPPED.md`](SHIPPED.md) (cut from "Infra" 2026-09-07).
- **v0.310.0 + v0.311.0** — the wallpaper, share JPEG, keepsake and scale-&-compass exports come off the master at share size for *linear* runs (`stack._native_picture_source`, `SHARE_JPEG_MAX_LONG_EDGE`); display-space runs were declined on purpose — that half is the READY render-cache entry under "Features that serve real workflows". Full entry in [`SHIPPED.md`](SHIPPED.md) (cut 2026-09-07).
- **v0.270.2** — 🟠 A star-poor mosaic panel is no longer auto-rejected as "cloud". `grade_frames` built its
- **v0.270.1** — 🔴 The walk-away auto-stack can no longer publish a picture made worse by subs whose files
- **v0.237.2** — Level a big mosaic's thin panel the same way in the preview and the export.
- **v0.231.1** — "Point here right now" now respects the Moon: the whole-night plan's proximity penalty is
- **v0.231.0** — NEW beginner feature "Point here right now": a Dashboard card that picks, from the user's *own*
- **v0.230.2** — Honest accounting for subs that simply **weren't on disk**: a `count_unreadable_frames` preflight in
- **v0.219.0** — NEW beginner feature "Your first image": a self-checking four-step map of the journey (point at your
- **v0.218.0** — The master-coverage roll-up now *explains* itself: each missed target carries a plain-language
- **v0.217.1** — The skipped-calibration-master note now reaches the walk-away user: the same recorded
- **v0.213.0** — ⭐⭐ Fixed the PER-FRAME background flatten's starved object mask — the last stacking-engine source of
- **v0.212.0** — NEW beginner feature "Was last night's sky bright?": a relative, self-hiding read on the latest
- **v0.211.1** — Editor export/render job polling hardened into one tested helper (`pollJob.ts`): rides out up to 5
- **v0.211.0** — ⭐⭐ Fixed the one-click Auto colour split (purple one side / green the other) at its root: the
- **v0.210.20** — Click-path audit fix (f) + (d): `bulk_frames` now returns a `note` so "Reject worst" on a
- **v0.210.19** — Four frontend click-path/UX fixes from the 2026-07-26 audit: (g) `isNavActive` matches whole path
- **v0.203.0** — Fix the aliased/low-res interactive stack render: `load_stack_rgb` now downscales with a NaN-aware
- **v0.202.0** — ⭐⭐⭐ Auto-derive the plate-solve FOV per frame from the FITS header (S30 ≈ 2.1°, S50 ≈ 1.27°) +
- **v0.196.0** — ⭐⭐ Full-res PNG offered on every beginner picture-download surface (consistency follow-up to
- **v0.195.0** — ⭐⭐ Full-resolution PNG download on the History card (directly answers the owner "my output is
- **v0.184.11** — ⭐ "How's my stack?" now surfaces the #1 cause of the owner-reported faint-field "gibberish": when
- **v0.178.2** — The "why frames were left out" high-drop verdict now names the *dominant actual cause* (soft focus →
- **v0.178.1** — ⭐ Fixed the "One frame vs your stack" reveal rendering its two halves under different tone curves.
- ~~**Calibration exposure-mismatch warning was silenced exactly when a wrong-shaped bias disabled dark-scaling.**~~
- **QA re-audit record (Scout 2026-07-23, branch `claude/kind-mccarthy-49jli6`).** Adversarial correctness sweep
- **v0.141.0** — NEW BEGINNER FEATURE / friendliness (PRIORITY 3 — "annotated results"; Builder 2026-07-21,
- **v0.139.0** — NEW BEGINNER FEATURE / autonomy (PRIORITY 2/3 — pre-stack reassurance; Builder 2026-07-21,
- **v0.137.0** — NEW BEGINNER FEATURE / autonomy (PRIORITY 2/3 — "drop files, walk away, get told when it's
- **v0.136.7** — Stacking-engine correctness (PRIORITY 1 — sub-pixel alignment consistency; Builder 2026-07-17,
- **v0.136.6** — Friendliness (PRIORITY 3 — beginner-facing frames table; Builder 2026-07-17, branch
- **v0.136.5** — Calibration-engine robustness (PRIORITY 4 — image-quality/consistency; Builder 2026-07-17,
- **v0.132.1** — Stacking-engine correctness (PRIORITY 1 — data-integrity of a beginner-facing diagnostic;
- **v0.132.0** — Beginner feature / friendliness (PRIORITY 3 — "should I wait or walk away?"; Builder 2026-07-16,
- **v0.131.3** — Stacking-engine correctness (drizzle edge/floor polish — focus #1; Builder 2026-07-16, branch
- **v0.123.0** — Beginner feature / friendliness (PRIORITY 3 — "enjoy & share a good image"; Builder 2026-07-14,
- **v0.121.5** — Engine robustness (calibration-engine contract-hardening — focus #1; Builder 2026-07-14, branch
- **v0.121.4** — Engine robustness (stacking-engine hardening — focus #1; Builder 2026-07-14, branch
- **v0.121.3** — Engine robustness (stacking-engine hardening — focus #1; Builder 2026-07-14, branch
- **v0.119.8** — Bug fix (**upgrade-safety / data-integrity — §9, top priority class**; Scout 2026-07-14,
- **v0.119.6** — Bug fix (data integrity / autonomy — PRIORITY 2/3; Builder 2026-07-14, branch
- **v0.119.5** — Bug fix (friendliness/trust — PRIORITY 3; Builder 2026-07-14, branch
- **v0.114.0** — Beginner feature (friendliness/workflow — PRIORITY 3; Builder 2026-07-13). "Share card"
- **v0.113.2** — Robustness (Builder 2026-07-13). Harden `session_recap._parse`: coerce a tz-naive timestamp
- **v0.113.1** — Autonomy/image-quality/correctness (Builder 2026-07-13). Re-QC a frame whose Stage-1 cache
- **v0.113.0** — Autonomy/friendliness/image-quality (Builder 2026-07-13). Cross-session quality-drift nudge:
- **v0.109.26** — Correctness/data-retention (image-quality/autonomy; Builder 2026-07-12; found by an
- **v0.109.25** — Determinism/idempotency (image-quality/autonomy; Builder 2026-07-12; found by an
- **v0.109.24** — SECURITY: fixed an unauthenticated path-traversal / arbitrary-file-read in the SPA static
- **v0.109.17** — Data-integrity bug (autonomy/image-quality; Builder 2026-07-11; found + reproduced by an
- **v0.109.16** — Autonomy (PRIORITY 2; Builder 2026-07-11): the **unattended slice** of the pre-flight
- **v0.109.15** — Editor (PRIORITY 1): the **Compare** toggle now disables itself while previewing a trim crop,
- **v0.109.14** — Watcher auto-stack no longer redundantly re-stacks an already-current target after a manual
- **v0.109.12** — Job-worker robustness: `_persist` no longer risks killing the single worker on a
- **v0.109.11** — Job-state correctness bug (Builder 2026-07-11; found by an adversarial webapp-orchestration
- **v0.109.10** — QC-engine correctness hardening (PRIORITY: stacking/QC-engine data-integrity; Builder
- **v0.109.9** — Friendliness / UX bug (PRIORITY 3; Builder 2026-07-11; found by the frontend non-editor route
- **v0.109.8** — Friendliness / display bug (PRIORITY 3; Builder 2026-07-11; found by the frontend non-editor
- **v0.109.7** — Editor bug (PRIORITY 1; Builder 2026-07-11; found by the same frontend editor-logic audit —
- **v0.109.6** — Editor bug (PRIORITY 1; Builder 2026-07-11; found by an adversarial audit of the frontend
- **v0.109.5** — Security / invariant hardening (Builder 2026-07-11; found by an adversarial audit of the
- **v0.109.2** — Friendliness / consistency (PRIORITY 3; Builder 2026-07-11): the History card's **Adjust**
- **v0.109.1** — Two safe, self-contained hardening fixes (Builder 2026-07-11): (1) **image quality** —
- **v0.109.0** — Editor (PRIORITY 1; Builder 2026-07-11): the editor's no-recipe fallback view now uses the
- **v0.108.4** — Editor robustness (PRIORITY 1; Scout 2026-07-11): `recipe_from_dict` no longer 500s on a
- **v0.108.1** — Image-quality / trust (PRIORITY 4; Builder 2026-07-11): surface the colour-cal *clamp* warning.
- **v0.108.0** — Friendliness / trust (PRIORITY 3; Builder 2026-07-11): surface Auto's colour-calibration outcome
- **v0.107.10** — Friendliness / trust (PRIORITY 3/4; Builder 2026-07-11): surface *which* colour-calibration
- **v0.107.9** — Autonomy / image-quality (PRIORITY 2/4; Builder 2026-07-11): when Auto's colour calibration
- **v0.107.5** — Autonomy (PRIORITY 2; found by the same 2026-07-11 auto-stack audit): finish the v0.107.1
- **v0.107.4** — Autonomy / "just works" (PRIORITY 2; found by a fresh adversarial audit of the auto-stack
- **v0.107.2** — Image-quality/correctness (Scout, #238): clamp `_solve_gray_star`'s per-channel colour-cal
- **v0.107.3** — Stacking-engine memory safety (found by a fresh adversarial audit of the stacker
- **v0.107.0** — Editor (PRIORITY 1): one-click **"Neutralize background"** fix for a residual sky
- **v0.106.0** — Image quality / trust (PRIORITY 4): library-wide "does Auto land the background neutral?"
- **v0.105.0** — Image quality / trust (PRIORITY 4): the unattended auto-edit now measures the finished
- **v0.104.1** — Friendliness (PRIORITY 3 / trust): total integration time on the Target detail page.
- **v0.104.0** — Feature (editor, PRIORITY 1 / trust): sky-background colour-cast readout. The
- **v0.103.17** — Fix (editor, PRIORITY 1): the editor's undo/redo hook (`useUndoable`) misbehaved under
- **v0.103.15** — Fix (editor, PRIORITY 1): the per-op "Split this op" / "Without this op" compare
- **v0.103.14** — Fix: the REST job endpoints silently stripped the server-classified `error_kind` (Builder
- **v0.103.13** — Actionable "why uncalibrated" advice on the History Info panel (Builder 2026-07-10). For a
- **v0.103.12** — Auto-enable *dark exposure-scaling* in the unattended chains (Builder 2026-07-10). The
- **v0.103.11** — Gate the auto-bound *dark* on a gain/temperature confidence match too, completing the
- **v0.103.10** — Gate the auto-bound *bias* on a gain/temperature confidence match (Scout 2026-07-10;
- **v0.103.9** — Fix drizzle frame-accounting counting an off-canvas stray sub as *used* (Builder

- **v0.103.8** — Carry the calibration-status trust line onto the editor's auto-note surface (Builder
- **v0.103.7** — Surface calibration provenance in plain language on the run Info panel (Builder 2026-07-10;
- **v0.103.6** — Auto-bind calibration: gate the auto-bound *flat* on a gain/temperature confidence match
- **v0.103.5** — Engine robustness (background flatten; Builder 2026-07-10, found by a fresh adversarial
- **v0.103.4** — Auto-bind calibration: dimension-gate the masters so an unattended stack can't
- **v0.103.2** — Stacking-engine correctness (drizzle reject; Builder 2026-07-10, found by a fresh
- **v0.103.1** — Editor/parity hardening (PRIORITY 1; Builder 2026-07-10, found by a fresh adversarial
- **v0.103.0** — One-click "Reject the N odd-target frames" on the mixed-pointing guard (autonomy/
- **v0.102.0** — Pre-flight "batch looks like two targets" guard on the Stack form too (autonomy/
- **v0.101.0** — Pre-flight "this batch looks like two targets" guard, first slice (autonomy/friendliness/
- **v0.100.0** — Honest per-run frame accounting + large-align-failure diagnosis (friendliness/trust,
- **v0.99.10** — Drizzle pre-run estimate reports the **real** output canvas size (stacking-engine
- **v0.99.9** — Honest per-pixel *frame count* for `coverage_min`/`coverage_max` on the **drizzle**
- **v0.99.6** — Honest per-pixel *frame count* for `coverage_min`/`coverage_max` under quality
- **v0.99.3** — Plain-language help on every advanced Stack-form knob (friendliness — priority 3,
- **v0.99.2** — Retry a transient QC error in the auto-pipeline (autonomy/robustness — priority 2,
- **v0.99.1** — Surface "N frames couldn't be quality-checked" on the Target page (friendliness/trust —
- **v0.99.0** — Auto-bind matching calibration masters to the *unattended* stack chains (autonomy +
- **v0.98.2** — Tonight planner (friendliness — priority 3, Builder dogfood-found 2026-07-09): the
- **v0.97.8** — Tonight planner (friendliness/autonomy — priority 3, Builder §4 top-up): show *when
- **v0.97.7** — Tonight planner (friendliness/trust): a dimmed per-row Moon cue explains *why* a
- **v0.97.6** — Tonight planner (autonomy/trust): the observability score now weights each target's Moon
- **v0.97.5** — Tonight planner (friendliness): the Moon card now shows *when* the Moon rises or sets
- **v0.97.4** — Tonight planner (friendliness): the Moon card now distinguishes a **waxing** from a
- **v0.97.3** — Tonight planner (friendliness): section-accurate empty states. The two target
- **v0.97.2** — Tonight planner (friendliness): the "Minimum altitude" picker no longer renders
- **v0.97.0** — ⭐ OWNER-REQUESTED "Tonight" night planner — widen the bundled catalog beyond Messier.
- **v0.96.0** — ⭐ OWNER-REQUESTED "Tonight" night planner, slice (b) — horizon / tree-cover mask: an opt-in `horizon_profile` (azimuth→min-clear-altitude points) shapes each target's usable window past low obstructions; `HorizonProfile` interpolates with 360° wrap, Settings gets a point editor, Tonight flags `horizon_active`. Additive, upgrade-safe (empty default = old flat-floor behaviour).
- **v0.95.0** — ⭐ OWNER-REQUESTED "Tonight" night planner, slice (a) — the offline astronomy core.
- **v0.94.17** — Friendliness: `post/target_id.py` now maps SIMBAD short OTYPE codes to plain words
- **v0.94.16** — Colour-calibration robustness: `post/color_cal.py::_solve_gaia` now clamps both solved
- **v0.94.15** — Engine/data-integrity fix (found by a fresh adversarial editor-pipeline audit): the
- **v0.94.14** — Friendliness polish: the Dashboard readiness banners' dismissal now keys on the
- **v0.94.13** — Friendliness (first-run): extended the Dashboard readiness banners to a
- **v0.94.12** — Friendliness/autonomy: a proactive, dismissible "plate-solving isn't set up"
- **v0.94.11** — Friendliness (cosmetic): the ASTAP "no star database" hint on Settings now
- **v0.94.10** — Project-DB robustness: opening an empty/foreign `project.sqlite` (a blank or
- **v0.94.9** — Ingest robustness: a transient Stage-1 copy failure (a NAS blip during
- **v0.94.8** — Stacking-engine data-integrity fix (current-focus §1): the bilinear debayer
- **v0.94.7** — Job-progress robustness (autonomy/friendliness): fixed two real `useJobEvents` SSE bugs
- **v0.94.6** — Editor/undo correctness (PRIORITY 1): fixed undo *over-reverting* a second use of the
- **v0.94.5** — Engine/NaN-coverage: `geometry.rotate` now guards degenerate sizes (`h < 3 or
- **v0.94.4** — Robustness/friendliness: `POST /api/calibration/masters` now returns 400 (not 500)
- **v0.94.3** — Engine/NaN-coverage: sub-pixel refine now marks the vacated edge NaN on a
- **v0.94.2** — Editor friendliness: surface the content classification in the "What Auto-process
- **v0.94.1** — Robustness: `detail.denoise` now guards a degenerate 1-px-thin image
- **v0.94.0** — Auto-preset classifier — *safer-first slice* (a preset **suggestion**, not a change
- **v0.93.4** — Extracted the RA 0°/360° unwrap heuristic into one shared dependency-free
- **v0.93.3** — Target aggregate RA is now 0°/360°-wrap-safe (`claude/happy-franklin-te45e2`).
- **v0.93.2** — Reference-frame selection is now RA 0°/360°-wrap-safe
- **v0.93.1** — Make the editor's `denoise-suggestion` recipe-aware, matching its
- **v0.93.0** — Show the auto-edit "why" note in the *editor* when opening a run a background
- **v0.92.0** — Carry the Auto "why" note onto the *autonomous* auto-edit paths
- **v0.91.0** — "Why these steps?" — surface the Auto recipe's *causal inputs*
- **v0.90.0** — "N new subs since your last stack — restack?" nudge on the Target page
- **v0.89.3** — Chain the auto-edit onto the watcher's background auto-stack
- **v0.89.2** — Graceful degradation for `background.final_gradient` on busy / dense-star
- **v0.89.1** — Two verified low-severity webapp-router robustness fixes (Scout,
- **v0.89.0** — Editor "Compare a look" follow-up: a "Switch to this look" action on the
- **v0.88.0** — Editor "Compare a look" split: a picker (Auto + built-in + saved presets)

- **Companion caution: Drizzle on with too few frames (v0.87.1, image-quality/PRIORITY 4).**
- **Proactive Drizzle nudge on the Stack form (v0.87.0, autonomy/image-quality/PRIORITY 2–4).**
- **Don't claim quality weighting influenced a min/max-reject stack (v0.86.2, image-quality/

- **Chain the auto-edit onto library-wide "Reprocess everything" (v0.86.1, autonomy/image-
- **Chain a one-click auto-edit onto the "Process target" result (v0.86.0, autonomy/editor/
- **Deep-link the one-click "Process target" result to its editor in one hop (v0.85.3,

- **Surface the one-click "Process target" job's outcome + a "View result" link on Jobs

- **"Ready to process?" getting-started callout for a fresh target (v0.85.1,

- **One-click "Process target" — QC + solve + auto-grade + stack in one job (v0.85.0,

- **De-flake the Stack-form photometric-nudge test that reddened main CI + fix the underlying

- **Clamp `background.final_gradient`'s box to the image size so Auto can't hard-fail on a

- **Extend the rejection-clipped trust line to the drizzle-reject path (v0.84.11, PRIORITY-4

- **Extend the rejection-clipped trust line to the min/max-reject path (PRIORITY-4

- **Surface how much the stack's rejection actually clipped — a trust line on History

- **Stacking hot path: per-frame weight/scale lookups honour a frame whose DB id is 0

- **Target page: recoverable error state instead of a broken shell when the target 404s

- **One-click actions on the three remaining advisory-only Stack-form rejection nudges

- **Plain-language "Build master" empty-folder failure (PRIORITY-3 friendliness; follow-up to

- **Robust server-side `error_kind` on failed jobs — makes the plain-language job-error

- **Plain-language job failure messages on the Jobs page (PRIORITY-3 friendliness; follow-up to

- **Plain-language job names + a guided empty state on the Jobs page (PRIORITY-3 friendliness).**

- **Robust server-side plate-solve setup classification — makes the star-database "not set up"

- **Actionable "plate-solving isn't set up" banner on the Target page (PRIORITY-3 friendliness +

- **QA — stacking-engine adversarial audit + one-click Auto dogfood (top current-focus areas),

- **Fix (PRIORITY-1 editor): a cropped/geometry-edited live preview letterboxed with spurious

- **Engine hardening (PRIORITY-1 stacking-engine QA): correct a stale `WelfordAccumulator`

- **One-click "Drop N outlier frames" + safety-cap notice on the Stack-form auto-grade hint

- **Surface the deep-rescan count on the finished reprocess-all job summary (follow-up to

- **Reprocess-everything slice (b): optional deep full rescan (re-QC / re-solve / re-grade

- **Proactively nudge dark exposure-scaling from the calibration store (PRIORITY-2 autonomy;

- **Surface dark exposure-scaling provenance on the run Info / History card (PRIORITY-4

- **Dark exposure-scaling — reuse a dark library shot at one exposure to calibrate subs

- **Make the remaining advisory Stack-form nudges one-click actionable (PRIORITY-2/3

- **Fix: mosaic canvas iterative-shrink dropped a good central frame instead of the real

- **Fix: a manual re-stack (or re-export/re-combine) under an existing basename silently

- **Fix: watcher could permanently drop a batch from auto-ingest when a file stabilised

- **Fix four more flaky Editor "From your data" tests that reddened main's CI (test-only,

- **Proactive "N targets are out of date" nudge — reprocessing after an upgrade is no

- **Fix: "Reprocess everything" silently overwrote each target's existing stack output

- **Stack form nudges to enable Photometric normalization when transparency varies a lot

- **Fix flaky Editor "Auto curve" test that was intermittently reddening main's CI.**

- **Surface photometric-normalization provenance on the run Info / History card

- **Photometric (multiplicative) frame normalization before combine — gain-match the

- **Per-op split before/after — drag a divider to see the image with vs without just

- **Personal default recipe — "my house style" one click away on every new run

- **Split before/after compare — drag a divider to see Original vs Edited in one

- **Reprocess-everything gains an "only outdated targets" filter (owner-requested

- **Stack runs record the producing app version ("made with vX") — provenance +

- **Recipe carry-over across re-stacks: one-click "Use my previous edit"** — the Seestar

- **Curves widget now previews the auto-contrast curve (read-only ghost) + "Bake to

- **"Cropped view — showing N% of the frame" indicator + one-click "Remove crop"** —

- **Fix: single-field stacks were misclassified as mosaics (Scout-verified

- **Jobs page surfaces the reprocess-all batch outcome in plain language** —

- **⭐ OWNER-REQUESTED — "Reprocess everything" (slice a): one-click restack of

- **Auto-process now gives its one-click result a gentle, data-driven contrast

- **Auto-process summary names the mosaic coverage-leveling step in plain language** —

- **Fix: SCNR "Protect" tooltip had gentler/stronger reversed (misled the most

- **Fix: a thin crop + downscale no longer crashes the editor preview/export with

- **Editor exports are marked display-space — no more re-edit double-stretch, and

- **"Auto curve" button names its goal + dims when already applied (data-driven

- **Data-driven "Auto curve" starting point for the Curves op (completes the

- **Every tonal control's landing shown on the histogram (Stretch/clip edges +

- **Fix flaky frontend CI at the root: run vitest test files sequentially

- **Data-driven "From your image" Strength + Black point for the asinh Stretch

- **Auto-process summary names the mosaic border trim in plain language** — small

- **Auto-process trims a mosaic's ragged low-coverage border (cleanly framed

- **Coverage overlay now follows the recipe's geometry ops (was frozen on the

- **Fix flaky frontend CI at the root: raise vitest `testTimeout` above

- **Gamma suggestion names the goal it solves for (not just a bare number)** — the

- **"Edited" dot on tuned op rows in the pipeline list** — after Auto-process or a

- **Editable numeric readout beside every editor slider** — the editor rendered

- **Fix (a11y): editor curve points are keyboard-operable** — the last open

- **Fix: trim-crop preview rectangle misaligned on a letterboxed preview** — the

- **Fix: deconvolution's live preview silently understated the export on large

- **Fix: editor overlay-zoom mislabel + keyboard access gaps (a11y)** — three

- **Fix: background/gradient op failures now surface in the editor (were a silent

- **Fix flaky `detail.sharpen` NaN test (route unsharp mask around skimage)** — the

- **Fix: "Use data defaults" toolbar and the per-param "✓ already set" indicator

- **Fix: star-mask overlay now reflects the display-space image the ops gate on

- **Fix: one slider/curve drag no longer floods (and evicts) the editor's undo

- **Fix flaky frontend CI (Editor Levels "From your image" / "Auto levels" tests)** —

- **Editor recipe with a non-mapping `params` no longer 500s** — a recipe body

- **One-click "Reset points" on the Levels op header** — the Levels header had

- **Data-driven midtone (gamma) point for the Levels op** — the Levels suggestion

- **Friendly labels on the last jargon-bare editor dropdown (denoise Method)** — the

- **Show the Levels black/white points as guides on the histogram** — while setting

- **Single-click "Auto levels" on the Levels op** — the data-driven Levels buttons

- **Editor: accurate data-driven value labels (Levels buttons + Auto's crossfaded

- **Smooth the Auto recipe's noisy/clean cliff (denoise ↔ sharpen crossfade)** —

- **One-click "From your image" black/white points for the Levels op** — the Levels

- **Test the PNG-render path also surfaces failed ops** — coverage follow-up to the

- **Warn about a degenerate Levels op (empty black↔white range)** — companion to

- **Guard the Levels op against a degenerate (white ≤ black) range** — the Levels

- **Surface failed ops on export, not just in the live preview** — the preview /

- **Fix stale/misleading maintainer comments & docstrings** — three inaccuracies a

- **Guard the Curves op against a degenerate (blank-the-image) curve** — a tone

- **Expose the Rotate op's `expand` control (was a dead read)** — `geometry.rotate`

- **Warn about a redundant second Stretch (double-stretch bug)** — `apply_recipe`

- **Show the proposed trim over the coverage heatmap** — when the user opened the

- **Show render progress for the full-res PNG download** — "Download full-res PNG"

- **Note the coverage overlay is for the uncropped frame when a crop is applied** —

- **Preview the "Trim border" rectangle before committing** — the one-click "Trim

- **Colour heatmap + legend for the coverage overlay** — the coverage-map overlay

- **Fix a flaky Stack-form vitest ("does not suggest min/max reject when already

- **"Trim border" selects the new Crop op + reports the kept fraction** — polish on

- **Coverage-map overlay in the editor (mosaic trust/explain)** — a Seestar

- **One-click "Trim to well-covered area" for mosaics** — a Seestar mosaic's union

- **Highlight/shadow clipping warning in the editor** — over-stretching is the

- **Explain the editor's TIFF export mode** — the Export panel's "TIFF" dropdown

- **Built-in presets prepend Coverage leveling on a mosaic** — a built-in preset

- **Tell the user when "Coverage leveling" will do nothing** — the op only

- **Auto-add Coverage leveling to the Auto recipe for mosaics** — now that the

- **Fix: "Coverage leveling" editor op was a permanent silent no-op** — the

- **Fix: star-mask overlay ignored the op's star size (always the default 4 px)** —

- **Fix: star-reduction over-shrank stars in the live preview vs export** — the

- **Auto-suggest the min/max reject count (k) from the streaked-frame count** — with

- **Warn when the min/max reject k is too aggressive for the frame count** — the

- **Show the k-count in the rejection badge for a top/bottom-k trim** — follow-on to

- **Top/bottom-k trimmed-mean reject** — generalised `MinMaxRejectAccumulator` to

- **"slower preview" chip in the Add-operation menu** — the `heavy` spec hint

- **Retire the now-dead "export only" preview scaffolding → "slower preview"** —

- **NaN-preservation regression tests for the spatial detail ops** — the

- **Fix: hot-pixel editor op silently did nothing on mosaic (NaN) images** — the

- **Show Auto's chosen data-driven values in the "What Auto-process did" note** —

- **Adaptive live-preview debounce for heavy editor ops** — dragging a slider

- **Data-driven saturation in the one-click Auto recipe** — Auto's final

- **"Your data" context chip in the editor header** — the four data-driven

- **Keep the old preview + "Updating…" badge while re-rendering (editor

- **Cancel superseded live-preview renders (editor responsiveness)** — the live

- **Direct pixel-transform + NaN-safety tests for the tone/colour editor ops** —

- **Built-in presets land sized to your data** — the built-in editor presets

- **"Apply data-driven defaults" one-click on the editor** — a user hand-building

- **Dim the "From your data" suggestion button when the param already matches** —

- **Complete + enforce plain-language help on every editor control** — finished the

- **Plain-language help on the remaining jargon-bare editor sliders** — v0.56.17

- **Data-driven sharpen radius in the one-click Auto recipe** — when Auto-process

- **Star-size-from-stars suggestion for the star-reduce op** — the `stars.reduce`

- **Sharpen-radius-from-stars suggestion** — the editor's Sharpen op made the user

- **Data-driven denoise strength in the one-click Auto recipe** — when Auto-process

- **"Preview is downscaled" hint in the editor** — the live preview always runs on

- **Preview↔export parity for the background ops** — v0.56.19 corrected the spatial

- **Auto-process note clears when the recipe changes** — follow-up to v0.56.18's

- **Preview↔export parity for spatial detail ops** — the live preview runs on a

- **Explain what Auto-process did** — after Auto-process builds a recipe the user

- **Per-op "Reset to defaults" (already shipped)** — the backlog listed this as an

- **Plain-language help on the jargon-heavy editor ops** — several detail/tone ops

- **Per-op "without this op" preview compare** — the editor's Compare button shows

- **Progressive disclosure of the "Add operation" menu** — the menu listed all ~19

- **Auto-place a newly-added op on the correct side of the stretch** — adding an op

- **"No stretch step" nudge in the editor pipeline** — if a recipe has ops but no

- **Friendly names for enum dropdowns (editor + Stack/Settings forms)** — enum

- **Grey out stretch params that don't apply to the chosen curve** — the Stretch op

- **Stage-conflict caution + one-click fix in the editor OpList** — ops declare a

- **Combine-method facet on the Gallery** — a "All / Drizzle / Min-max / σ-clip /

- **One-click "Turn on min/max rejection" on the Stack-form nudge** — the

- **Gentle green-cast removal in the one-click Auto recipe** — an OSC Seestar

- **Guided empty-pipeline nudge in the editor** — a first-timer opening the editor

- **"Export only" flag for preview-approximate editor ops** — the Deconvolution op

- **Plain-language "Combined:" line in the History Info panel** — the Info panel

- **Combine-method badge in the Compare view** — the `RejectionBadge` (v0.56.1)

- **Min/max-reject nudge on the Stack form for small streaked stacks** — below

- **Rejection-method badge on History/Gallery cards** — a stack can be combined

- **Min/max (extremes) rejection for small stacks** — the order-statistic fix

- **Capped exponential backoff for Seestar reconnects** — the poll loop

- **"You have calibration masters but aren't using them" nudge on the Stack

- **Calibration-status filter chip on the Gallery** — building on the searchable

- **Gallery search matches calibration status** — building on this run's

- **Seestar reconnect hygiene (fd-leak fix)** — the manager's poll loop

- **Calibration chip on History/Gallery cards** — a stack now records which

- **Per-target noise-σ trend sparkline** — the History page now shows a small

- **Recommend a master bias for the bias+flat (no-dark) workflow** — completes

- **Record which calibration masters were applied in the FITS header** — a

- **Bias-only calibration for lights when no dark is chosen** (bias slice (a))

- **"Compare with previous run" action on the History page** — the Compare view

- **"Which stack is cleaner" verdict in the Compare view** — when both compared

- **Configurable job-history retention** — the job-history cap (how many finished

- **Compare-two-stacks web view** — a new `/compare?a=<safe>:<run>&b=<safe>:<run>`

- **Noise-improvement readout vs the previous stack** — each History card now

- **Newest/Cleanest sort on the Gallery** — extends the History-page noise sort

- **Newest/Cleanest sort on the History page** — completes the noise series: the

- **Stamp the background-noise σ into the master FITS header** — extends the

- **Per-stack noise-floor readout + "cleanest stack" badge** — `run_stack` now

- **Editor processing chain in the History Info panel** — the run Info endpoint

- **Full editor-recipe HISTORY provenance in exported FITS** — an editor export

- **Code-split the frontend vendor bundle** — the eager app bundle was one

- **"From your image" denoise-strength suggestion** — the editor's noise-

- **Record the deconvolution PSF σ in the exported FITS header** — when an

- **PSF-from-stars for editor deconvolution** — the deconvolution op made the

- **Auto-grade hint on the Stack form** — the Stack form now calls the

- **Nudge quality weighting when frame quality varies a lot** — the Stack form

- **"N trailed frames" badge on the Target view** — mirrors the "N streaked"

- **Auto-grade: automatic, explained frame-quality grading** — the QC layer

- **Plain-language hints on the Target metric columns** — the FWHM, Stars, Ecc.

- **Transparency-night badge on History/Gallery cards** — completes the

- **Surface the quality-weighting summary in the run Info panel** — a

- **Eccentricity factor in quality weighting** — `compute_frame_weights` gained a

- **Library search matches notes + persistent filter view** — the Library

- **Transparency-night hint on the Stack form** — completes the transparency

- **Weight the stack by frame transparency** — `compute_frame_weights` gained a

- **Inline reject-reason chip on rejected frame rows** — rejected rows in the

- **"Reject worst by transparency" bulk action** — building on this run's

- **Editor undo/redo keyboard shortcuts** — the editor's undo/redo buttons now

- **Star-mask preview toggle in the editor** — a new

- **Compute the dead `transparency_score` frame metric** — the column has been

- **Undo the last bulk reject + reject-reason breakdown on the Target view** —

- **Calibration mosaic-edge NaN/coverage audit** — completes the NaN/coverage

- **Suggest the reference canvas when a non-drizzle mosaic is over budget** —

- **Warn when the stack budget exceeds available RAM** — `/api/system` now

- **One-click "reject all streaked frames"** — the "N streaked" badge on the

- **De-flake `Editor.test.tsx`** — `main`'s CI was intermittently red on the

- **Stack memory budget as a Setting** — a new `max_stack_memory_gb` setting

- **Mono mosaic-edge NaN/coverage audit** — added a regression test that stacks

- **Suggest a fitting drizzle scale when over budget** — the `stack-estimate`

- **Streaked-frame count badge on the Target view** — an orange "N streaked" badge

- **Frame count / mosaic flag inline in the Stack estimate** — the pre-run sizing

- **Reclaim streaked subs** — new opt-in `keep_streaked_frames` setting (default

- **Large-stack sigma-kappa hint** — completes the sigma-clip guidance pair. The

- **Show/search run labels in the Gallery** — the gallery response now carries

- **Drizzle memory estimate in the Stack form** — subsumed by the pre-run stack

- **Pre-run stack estimate endpoint** — new `GET /targets/{safe}/stack-estimate`

- **Outlier-safe drizzle** — new opt-in `drizzle_reject`: two-pass κ-σ

- **Editable notes/label on History cards** — the long-standing `notes` column

- **Mono single-frame edge test** — verified the mono stack path on a

- **Low-frame sigma-clip caution** — the Stack form now shows an inline caution

- **Integration time inline on History cards + Reuse settings from Gallery** —

- **Fix red CI (pytest-qt import crash)** — CI had been failing on every merge:

- **Integration time on Gallery cards** — stack runs now record their effective

- **Reuse stack settings from a previous run** — new

- **Warn on a mismatched calibration master pick** — the Stack form now shows an

- **Auto-suggest a matching flat-dark** — `recommend_masters` now also returns

- **Drizzle flux-scale fix** — `DrizzleStacker.result()` no longer divides the

- **Auto-suggest calibration masters** — new `recommend_masters` ranks the

- **Stack info panel** — new `GET /stack-runs/{id}/info` reads the provenance

- `run_stack` edge-case tests — single accepted frame (degenerate stack, coverage

- Editor-export provenance — the derived `master.fits` from an editor recipe now

- Channel-combine provenance — the LRGB/RGB combined FITS now carries
- Accessibility sweep — added `aria-label` to the remaining icon-only
- Channel-combine NaN fix — LRGB pixels covered in G/B/L but uncovered in a
- **Flat-dark support** — a master flat can now be dark-subtracted before
- **Dashboard stats caching** — `GET /api/stats` no longer re-opens every target's
- **Settings backup & restore** — `GET /api/settings/export` downloads a portable
- **FITS output provenance headers** — `master.fits` now records OBJECT (target),
- CI safety net (`.github/workflows/ci.yml`) — full Python + frontend suites run

- **Autonomous run (agent, this session):** security fixes — Seestar `goto`
- **Autonomous run #1 (agent):** security + reliability/operability hardening +
- Autonomous dev playbook (`AGENTS.md`) + this backlog.
- Mono stacking + LRGB/RGB channel combine — `StackOptions.mono`, `channel_combine`,
- Star-mask-aware local edits — `edit/starmask.py`, mask-gated `stars.reduce`,
- Optional HTTP Basic access control (opt-in, PBKDF2, middleware). (v0.10.0, `7a995fc`)
- Dark/flat calibration — engine, master store, build job, API, UI. (v0.9.0)
- Keyboard shortcuts for frame grading on the Target page. (`2de2099`)
- Sigma-clip fix: no longer over-clips single-coverage (mosaic-edge) pixels. (`ab3883d`)
