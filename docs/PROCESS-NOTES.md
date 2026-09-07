# Process notes & QA sweep records

Where the *history of how this project is developed* lives, so
[`IMPROVEMENTS.md`](IMPROVEMENTS.md) can stay a **working list**.

Nothing here is open work. Put a block here when it is a record rather than a
task:

- a **collision diary** or any other "what this run learned about running runs"
  note;
- a **QA sweep record**, including (especially) a clean one — a clean-sweep entry
  at the top of "Bugs (fix these first)" is the first thing every triaging agent
  reads, and it is not a bug;
- a **released claim** from "In progress", once the run that made it has finished.

Newest first, one dated block each. Reading order does not matter: nothing here
is a queue.

---

## 2026-09-07 (Builder, branch `claude/sweet-babbage-8hitfe`) — a fourth clean dogfood, and what to do when the *bugs* are drained but a priority still has an open sentence

**Baseline.** `source scripts/agent-setup.sh` green. Full suite headless started
before any edit; this container ran it markedly slower than the recent runs
report (~80 % in the time the last few took to finish), which is worth knowing
before planning a run around three full passes — the pre-merge run is the gate
that counts, so budget for two.

**Dogfood — clean on both halves again, recorded because a clean sweep is a
record.** `scripts/agent-dogfood.sh --editor`, sample loaded and stacked:
- *Page probe:* nothing overflowing, no console errors. Tallest page still the
  Target page at **3,040 px on a phone** — the ninth baseline, and **identical**
  to the seventh and eighth. `/life-list` 3,008 px, the editor 2,887 px. The
  standing *"do not open a speculative IA slice"* reading now holds for a fourth
  consecutive measurement.
- *Editor drive:* the Add menu offered **21 ops**, all 21 previewed with no
  console error and no failed request, undo+redo applied. Clean.

**Triage — the backlog is drained, and this run re-established that by opening
entries rather than by trusting the last three runs that said so.** Worth
recording is that a *header-only* scan of `IMPROVEMENTS.md` badly overstates how
much is open: several entries carry their `✅ SHIPPED` verdict ten or twenty
lines into the block, so the first pass here produced ~50 "open" candidates and a
whole-block scan reduced it to the real set. Two of those looked open and were
not — the reshaped calibration match-confidence slice is `calibrationFit.ts::
masterRecommendation` (v0.321.0), and the streak root-cause entry's own strongest
candidate signal, cross-frame persistence, is `qc/runner.stationary_streak_frames`.
**If you scan this file programmatically, scan blocks, not bullets.**

**The move that made the run: a priority whose *bug* list is drained can still
have an open sentence.** With every candidate bug gated or closed, the highest
open thing left was one clause inside the "Live preview" entry — *"what remains
here is **responsiveness** (heavy ops on the proxy can lag)"* — which had sat
unquantified since v0.57.0. Timing the 21 ops on a real-sized proxy took ten
minutes and turned a vague clause into a number: the one-click Auto recipe costs
**4.2 s a render**, and the editor fires two such renders per change. That is the
whole of v0.382.2.

**Then the measurement paid a second time, which is the part worth copying.**
Having timed the ops, the arithmetic didn't close: the recipe's ops summed to
less than a render cost. The gap was `proxy._load_map` reading the run's
**full-resolution** coverage canvas whole and striding it afterwards — 2.65 s
cold on a 480 MB map, four times per edit — which is a bigger win (v0.382.3) than
the one the run set out to get, and was invisible to every code-level audit
because the line reads like a memmapped read. **When you time a pipeline, check
the parts sum to the whole**; the residual is where the unaudited cost lives.

**And the fix was already in the codebase, unused.** `EditContext.fit` was built
for the loupe and its docstring already says it is "the place to keep an
expensive measurement (a star solve, a mesh fit)" — nothing was carrying fits
between two renders of the *same* picture. **Look for the existing channel before
designing a new one** is now the second run in a row to record that lesson (the
last one found the Auto colour self-check the same way). No engine file changed.

**The bug that unit tests could not see, kept for the pattern.** The first
implementation keyed the reuse on the op's `uid`. Every pure test passed and
every endpoint test failed at "measured once", because a recipe posted without
uids gets fresh ones per request (`recipe_from_dict` mints them) — so the cache
was a permanent miss through the actual API while looking perfect in isolation.
A cache whose whole value is *hit rate* needs at least one test that measures the
hit through the real entry point; a unit test can only prove it is correct when
it hits.

**One idea closed with a number instead of an argument.** *"Make the difficulty
split data-driven"* wanted magnitudes added to the bundled catalogs because
curation "doesn't scale". Running the real resolver over the real catalog:
**157 of 157 objects already get a verdict**, so the gap was zero — and the
alternative meant writing astronomy data from recall. The measurement is now
`test_the_bundled_catalog_is_covered_end_to_end_today`, so it can't rot.

---

## 2026-09-07 (Builder, branch `claude/sweet-babbage-izlzeq`) — a clean dogfood (pages **and** the editor drive), and two gates approached from opposite ends

**Baseline.** `source scripts/agent-setup.sh` green. Full suite headless started
before any edit and run to **80 % with zero failures** before it was stopped to
free the box for the pre-merge run — enough to say `main` was green on arrival,
and the pre-merge full run is the gate that actually counts (§11).

**Dogfood — clean on both halves, recorded because a clean sweep is a record.**
`scripts/agent-dogfood.sh --editor`, sample loaded and stacked:
- *Page probe:* nothing overflowing, no console errors. Tallest page still the
  Target page at **3,040 px on a phone** — the eighth baseline, and identical to
  the seventh (3,040 px at v0.374.x). `/life-list` 3,008 px, the editor 2,887 px
  (unchanged since v0.377.2 measured it). **The standing "do not open a
  speculative IA slice" reading holds for a third consecutive measurement.**
- *Editor drive:* the Add menu offered **21 ops**, all 21 previewed with no
  console error and no failed request, and undo+redo applied. Clean.

**Backlog state — dry, and confirmed by opening entries rather than skimming.**
"Bugs (fix these first)" is in the gated/stood-down state the recent runs
describe. Every top-level candidate opened in "Features that serve real
workflows" was already shipped or already declined with numbers (*Night by
night*, *Does my colour look right?* — blocked on a catalog field that does not
exist, *N spots instead of a percentage* — measured and closed, *crop anything* —
declined once, the *edited cover* — mostly moot since an Apply-&-save records a
real `stack_runs` row). The two ⭐ Adaptive-Auto entries are complete but for the
optional slice (c). Nothing was invented to fill the gap.

**What shipped, and the shape worth carrying forward.** Both tasks are about the
same structural problem: **this backlog's remaining image-quality work is mostly
gated on data no agent has**, and runs keep meeting a gate, standing down
correctly, and leaving the gate exactly where they found it. There are two honest
moves against that, and this run made one of each.

1. **v0.382.0 — make the app collect the evidence.** The automatic
   highlight-clip cue is real-data-gated; nothing was accruing the distribution
   it needs. Every unattended auto-edit now asks the editor's own solver what
   *"Hold back highlights"* would offer on the picture it just made and stamps
   the answer, aggregated by `/api/auto-highlight-summary` into one Settings
   line. Built as a deliberate sibling of the shipped Auto **colour** self-check
   (`auto_cast_summary`), which is the precedent that made it an S rather than an
   M — **look for an existing self-check before designing a new one.**
   Two details worth reusing: stamping an explicit `{"strength": null}` so
   *measured-and-clean* is distinguishable from *never measured* (an absent key
   would have made the aggregate unreadable), and lifting the endpoint's body
   into `solve_highlight_protect` so the button and the passive record are one
   answer that cannot drift.

2. **v0.382.1 — check whether the gate is still there before deferring again.**
   The *"does the denoise↔sharpen crossfade over-read a sky gradient as noise?"*
   item had been deferred three times. It was filed 2026-07-08 against the
   **level**-MAD `sky_sigma`; **v0.225.0 replaced that with the local
   adjacent-pixel-difference MAD** — for the mosaic "multicolour grid"
   regression, not for this entry — and the local estimator is blind to any
   structure slower than a pixel *by construction*. Running the entry's own
   ladder took ten minutes and produced the opposite of its recorded numbers
   (0.0042→0.0039→0.0035→0.0030 as the gradient goes 0.00→0.20, against the
   pre-fix 0.015→0.028→0.054→0.098).
   **The general lesson: a deferral records the state of the code on the day it
   was written.** An entry gated on behaviour that a *later, unrelated* fix
   changed will never notice — nobody re-reads a stand-down they agree with. So
   before re-deferring a gated item, spend the ten minutes to re-run its own
   measurement against today's code; the entry names it precisely enough to be
   cheap, and the answer is either a confirmation worth dating or a close.

**One backlog pointer, no new ideas.** The SCNR-magenta entry defers on wanting
"a real neutral-vs-cast OSC background sample" — which `/api/auto-cast-summary`
has been collecting all along, by dominant tint. The entry now says so, so the
next run reads the live install's answer instead of measuring another synthetic.

---

## 2026-09-07 (Builder, branch `claude/sweet-babbage-wza0iq`) — the freshest backlog entry was the stalest one, and two closes that were re-traces rather than fixes

**Baseline.** `source scripts/agent-setup.sh` green; full suite headless before any
edit — **5,116 passed, 2 skipped** (22:23), the same number the previous Builder run
recorded, so `main` was green on arrival.

**The day-old idea was two days out of date.** Triage picked the top entry of
"Features that serve real workflows": *"Is my mosaic evenly filled?"*, filed by the
Scout **the same morning**, well-specified, beginner-facing, aimed squarely at the
owner's heaviest workflow. It was already built. `seestack/mosaicmap.py` shipped it
as **v0.355.0** two days earlier — the same `pointing_groups` clustering the entry
says to reuse, the same thin-panel callout, the same plain sentence — and the
"aim there next session" half as **v0.361.0**. One `grep -rn mosaicmap` finds all of
it, and the entry's own text says to grep first.

**The lesson is about *which* stale entry costs most.** The convention warns that
the backlog carries items that shipped months earlier; this one was a day old, and
that made it *more* dangerous, not less. A Builder triaging by "top of the highest
section, most recently filed, unclaimed" reaches a fresh entry first and trusts it
most — the staleness heuristics an agent actually uses (is it struck through? is it
old? does it carry a stand-down?) all pass it. Grepping `SHIPPED.md` for the key
nouns before *filing* is the only place this is cheap to catch.

**Two closes that changed no code, deliberately.** The
`ingest.py::_cache_stale`-refreshes-on-shrink note was re-traced against the current
file and closed as already-defended: `_source_incomplete` (`ingest.py:338`) loads the
pixel data and skips the frame whole before the cache is reached, so the harmful
half — a mid-rewrite truncation overwriting a good Stage-1 cache — cannot happen;
and a source that shrank *and* still reads as a complete FITS is a genuine content
swap, where refreshing is the right answer. Making the test growth-only, as the note
implied, would strip the swap refresh that stops a new capture stacking at the old
sky position. Recorded in the entry so the next run doesn't re-derive it.

**What shipped: v0.381.0**, the standing home for a scan's unexplained folder skips,
closing a "LEAD, NOT FINISHED" filed the previous run. Two things worth carrying
forward:

1. **The feared schema decision wasn't one.** The lead stood the item down because
   persisting the finding "is a schema decision, not a patch". The registry already
   has a `library_meta` key/value table, so it is one JSON value and no bump —
   worth checking for the *existing* store before sizing a persistence task as M.
2. **A per-scan alert and a standing card answer different questions.** Lifting the
   Jobs-page alert onto the Library page unchanged would have produced a permanent
   nag: the convention keeps skipping the folder, so the scan keeps reporting it,
   *including after the owner brought it in*. The standing version needs a "has this
   been dealt with?" test the per-scan one never needed. Any future "move finding X
   somewhere it will be seen" item inherits this question.

**Verified in a real browser, not only jsdom** (AGENTS.md §7's standing advice). A
scratch app on its own data root, the owner's exact folder shape in its `incoming/`,
scan, then Playwright at 1440 px and 420 px: card present at both widths, zero
horizontal overflow, no console errors, no failed requests; clicking *Bring "NGC
6888" in anyway* brought the four real subs in, left the device's `Stacked.fit` out,
and the card went silent. **One trap for a hand-rolled probe:** a fresh
`npm install playwright` wants a newer browser build than `/opt/pw-browsers` ships
(1243 vs 1194) and dies with "run `npx playwright install`", which this container
forbids — launch with `executablePath: "/opt/pw-browsers/chromium"`. The repo's own
`scripts/dogfood_probe.mjs` already does exactly this via its `BUNDLED` lookup, so
**use the repo's probe rather than writing one**; this cost a few minutes only
because the probe was ad-hoc.

---

## 2026-09-07 (Scout, branch `claude/admiring-brahmagupta-8g9218`) — stacking-engine + calibration adversarial QA sweep: CLEAN (no wrong-result bugs); two by-design fail-closed notes in `discover.py` recorded, not filed

**Baseline.** `source scripts/agent-setup.sh` green; stacking subset
(`-k "accumul or stacker or reject or align"`) **534 passed, 2 skipped** before any
edit, so a real engine bug would be distinguishable from a pre-existing failure.

**Scope.** Read adversarially, in full, hunting NaN/coverage-semantics violations,
rejection/weighting/normalisation math errors, memory-bound breaks on the hot path,
dtype/overflow, and error paths that silently ship a wrong-but-plausible image:
- `seestack/stack/`: `accumulator.py`, `weighting.py`, `photometric.py`, `align.py`,
  the κ-σ two-pass + min/max + single-pass dispatch in `stacker.py`
  (`_kappa_sigma_keep_mask`, `combine_method`, `_pass`, `auto_reject_depth`, the
  final result assembly), and `bg/coverage_leveling.py` (runs on *every* stack).
- `seestack/stack/` (via subagent trace): `drizzle_path.py`, `mosaic.py`,
  `pointings.py`, `reference.py`.
- `seestack/calibrate/` (via subagent trace): `apply.py` (read directly too),
  `defects.py`, `discover.py`, `masters.py`.

**Result: clean.** Every candidate hazard is already defended and, in most cases, a
nearby comment names the exact failure mode. Specifically re-confirmed sound: the
NaN="no coverage" invariant across all accumulators + drizzle `result()`; the two
keep-all widenings in `_kappa_sigma_keep_mask` (σ-unknown → +inf tol, mean-unknown →
keep) that stop the clip turning real pass-2 data into a hole; photometric scaling
applied identically in pass-1 stats and pass-2 combine (so the clip reference and the
clip agree); `combine_weights_with_photometric`'s `1/s²` variance correction kept off
the rejection-reference paths on purpose; per-panel (not target-wide) medians in
`weighting`/`photometric` on a mosaic; `level_by_coverage`'s per-level detrended
threshold, envelope-clamped quadratic fill, and NaN-excluding `valid_pix`; the memory
frees before pass 2 (`del wel`) and the bounded `_imap_bounded` in-flight cap;
`calibrate/apply` never double-subtracting bias-with-dark and the no-data
dark/bias/flat sanitisation (0 for pedestals, 1.0 floor for flats); `build_master`'s
NaN-emitting no-data + NaN-aware sigma-clip; and defect detection pulling only
same-CFA-phase, in-bounds neighbours.

**Two `discover.py` notes — recorded here, deliberately NOT filed as bugs:**
1. `calibration_folder_id` (`discover.py:116`) maps every char outside
   `[A-Za-z0-9._-]` to `_`, so two *distinct* real folders that differ only in a
   sanitised char (e.g. `Darks/30s` → `Darks_30s` vs a literal `Darks_30s`) collapse
   to one id and `seen_ids` drops the second — a legitimate cal folder silently not
   *offered*. Fail-closed (never builds/applies a wrong master), needs two
   near-identically-named sibling folders, and the app already lets the user pick a
   folder by hand. Low-value broken-UX; the collision is real but the subagent's
   `Dark-30s`/`Dark_30s` example is wrong (`-` is preserved, so those don't collide).
2. One unreadable sampled header makes `classify_folder` return `None` for the whole
   folder (`discover.py:227`), so a 100-frame dark folder with one corrupt file isn't
   offered. This is **by design** and documented ("an unreadable file is 'didn't
   say'", and "don't know is not an offer" — the strict rule that stops a master dark
   being built out of somebody's subs), so it is not a bug; the per-frame build path
   tolerates the same file if the user picks the folder anyway.

No code changed in this sweep — Scout leaves building to the Builder.

---

## 2026-09-07 (Builder, branch `claude/sweet-babbage-dyd578`) — a fifth dry-backlog triage that shipped a feature anyway: the editor control with no direct manipulation, and four traps from driving it in a real browser

**Baseline.** `source scripts/agent-setup.sh`; full suite headless green before any
edit — **5,116 passed, 2 skipped** (30:06). *(Note the setup script's environment
does not survive between tool calls: `source .venv/bin/activate` belongs in every
shell, and without it the first "baseline" run exits instantly with `No module
named pytest` from the **system** python — a different failure from the one
v0.378.1 documents, and it reads the same.)*

**Backlog state — the same gated state four prior runs describe, re-confirmed
mechanically** (walk the section bounds, treat every `- **` as an entry, drop any
whose **whole** body matches SHIPPED/CLOSED/DECLINED/BLOCKED/MOOT/RECORDED). Nothing
in "Bugs (fix these first)" is actionable without real data, an external binary or
an owner decision. **So this run took the standing "grow the app on a cadence"
allocation instead of reporting dry a fifth time**, and looked for the gap by
listing the editor's ops and asking which had no direct manipulation.

**The gap, and the stand-down that had to be read first.** `geometry.crop` has been
in the registry for a long time and could only be aimed through the descriptor
form's **Left/Top/Right/Bottom fractions** — arithmetic against a canvas over
10,000 px wide, done while looking at a decimated proxy. The 2026-08-06 entry
"a beginner can crop the Moon, but there is no way to crop anything else" declines
building *a manual crop tool*, and it is right to. **What shipped is not that**: no
op was added, no new expert surface — an existing, already-exposed control got a
rectangle you can drag. The entry now carries a note saying so, because the next
triage pass would otherwise read v0.379.0 as contradicting it, or as licence to
build the disk-shaped deep-sky crop it actually declines.

**Four traps, all found by running it rather than reading it.**

1. **`page.mouse` coordinates are the *viewport*, not the page.** The first browser
   probe drove a drag on the `se` handle and nothing happened: the caption stayed
   "Keeping the whole picture" through the whole gesture. It looked exactly like a
   dead event handler. The handle was at **y = 1098 in a 1000 px viewport** — below
   the fold — so the `pointerdown` landed on `HTML`. `scrollIntoViewIfNeeded()`
   first, and do not aim at the *exact* centre of a control whose edge touches the
   viewport boundary: the second attempt still missed by ~1 px until the target was
   nudged 3 px inward. Instrument by adding a capture-phase document listener that
   logs `e.target`'s `aria-label` — the answer arrived in one run once it printed
   `target=HTML`.
2. **jsdom has no `PointerEvent`, so `fireEvent.pointerDown` silently drops
   `clientX`/`clientY`.** `@testing-library`'s event map falls back to bare `Event`,
   which ignores those init keys — so a drag test passes `NaN` through the whole
   pipeline and fails on the *caption*, several steps from the cause. Dispatch a
   `MouseEvent` under the pointer event's name instead
   (`fireEvent(el, new MouseEvent("pointerdown", { clientX, clientY, bubbles: true }))`);
   React reads the coordinates off the native event either way.
3. **A fractional overlay needs the *underlying* picture's aspect, and no endpoint
   reports it here.** A crop's fractions are relative to the image **entering** it,
   so the rectangle is drawn over the recipe rendered with that op bypassed — and
   the histogram's `render_width/height` are the *recipe's* dims, with the crop
   applied. Measuring `naturalWidth`/`naturalHeight` off the loaded `<img>` (and
   holding the rectangle back until the measurement belongs to the image on screen)
   is right whatever earlier ops did to the frame. Verified: the rectangle's
   `boundingBox()` is byte-identical to the image's.
4. **A header button whose label equals an op's label breaks every
   `getByText(<label>)` in the suite.** Adding a "Crop" button made *one* existing
   test fail with "Found multiple elements with the text: Crop" — and only one, which
   is the misleading part; the other nine queries happened to run before it rendered
   or after it unmounted. The pipeline rows already carry
   `aria-label="Select <label>"` (`OpList.tsx`), which is the precise handle; all
   eleven now use it. **Before adding a button, grep the tests for its label.**

**QA records from this run, both clean.**
* **`scripts/agent-dogfood.sh --editor`** on the sample-loaded app: **21/21 ops
  previewed** with no console error and no failed request, undo + redo applied,
  nothing overflowing. Page heights: phone Target **3,040 px**, `/life-list`
  3,008 px, phone editor **2,887 px**, desktop editor 1,841 px — *identical* before
  and after both features, i.e. the new header button costs **zero** page height (on
  a 420 px phone it shares the Auto-process row rather than starting a new one).
  The eighth height baseline, and it says what the last three said: **do not open a
  speculative IA slice.**
* **Drag-to-crop end to end against the running app** (custom probe, kept in the
  session scratchpad): rectangle box identical to the picture's, a `se` drag updates
  the caption live and commits to the op (`x1` 0.62, `y1` 0.55 in the sliders), and
  "Done cropping" reshapes the preview to the cropped aspect. No console errors.

**One aborted-request observation, recorded as a non-finding.** A probe run that
navigated straight into the editor logged two `requestfailed`s for
`editor/preview` and `editor/histogram` carrying `recipe=…{"ops":[],…}` — React
Query cancelling the pre-seed empty recipe when the saved one arrives. It does not
reproduce once the page settles, and the dogfood editor drive is clean. Not a bug.

**Collisions: none, but one merge landed mid-run.** `origin/main` moved
`4b61646 → 8dacbc7` (a Scout run: a clean stacking-engine + calibration QA sweep,
plus a filed mosaic panel-balance feature). Docs only; merged cleanly, and it is
also why this run did not spend its second half on its own engine audit.

---

## 2026-09-07 (Builder, branch `claude/sweet-babbage-7wv8l8`) — a fourth dry-backlog run that found one real task in it after all: the greps that turned it up, and the two candidates measured and declined

**Baseline.** `source scripts/agent-setup.sh` — note that its `pip install -q -e
".[dev,web]"` **can fail and still print "agent env ready"**: the script is
`source`d, and a `ReadTimeoutError` from `files.pythonhosted.org` mid-resolve left
a `.venv` holding nothing but `pip`. The tell is `No module named pytest` from
`.venv/bin/python`, not from the system python. `pip install --timeout 120
--retries 5 -e ".[dev,web]"` recovered it. Worth knowing before diagnosing a
"broken" checkout — nothing was broken.
Full suite headless green before any edit: **5,105 passed, 2 skipped** (22:50).

**Triage method, because three prior runs reported the backlog dry and this one
did not.** The sections are far too long to read, so entries were enumerated
mechanically — walk `IMPROVEMENTS.md` by section bounds, treat every `- **` as an
entry, and drop any whose text contains `SHIPPED` / `CLOSED` / `DECLINED` /
`BLOCKED` / `MOOT`. **The first pass windowed that regex to the entry's first 1,000
characters and was wrong twice** (the calibration "agreement, not more copy" slice
and Levels' "From your image" black point both carry their ✅ block a screen below
the header). Scan the **whole** entry. With that fixed the genuinely-open set is
small and mostly gated, which is the state three runs have described.

**What was open and got built: `POST /api/scan`'s `root` (v0.378.0).** The 2026-08-30
entry asked a run to pick one of its two answers. It was worth (a) rather than (b)
for a reason the entry only half-stated: the folder the convention skips as "the
device's own picture" is *reported* but its only recovery was **rename the folder** —
inside `incoming/`, which the app may never do and shouldn't ask a non-technical
owner to do by hand either. A scan that can be pointed at one folder is the recovery
that touches nothing. Write-up in [`SHIPPED.md`](SHIPPED.md).

**Two things worth recording from building it.**
1. **The stale comment was the bug's own description, sitting in a passing test.**
   `test_scan_root_confined.py` said a sub-folder root "loses the folder-name
   target … filed rather than changed here". Grepping the *tests* for the entry's
   nouns found the defect's exact shape faster than reading the scanner did.
2. **`reject_seestar_output_frames` was the wrong tool for the scoped path, and
   nearly used.** It rejects a folder's *unnamed* frames too when the folder holds
   `≤ _MAX_SEESTAR_OUTPUT_FRAMES` (2) — right for the upgrade path it exists for,
   and exactly backwards for a user who has just said "these are my subs, bring
   them in": a small folder would have been ingested and immediately rejected. The
   scoped scan filters by `is_seestar_output_filename` at selection time instead,
   which also makes the count it reports the same count the alert already showed.

**The grep that was one directory too narrow, and cost a full 22-minute suite run.**
Adding an additive `path` key to the reported skipped folder, I grepped
`skipped_folders` across `frontend/src` and `webapp/` — and not `tests/`.
`tests/webapp/test_pipeline.py` compares that dict with `==`, so an *additive*
field broke it, and the only thing that said so was the pre-merge full run.
**When adding a field to a response, grep the tests for the field's container
first**: this repo pins several response shapes exactly, on purpose, and an
`==` on a dict is precisely the assertion an additive change is supposed to be
safe against and is not.

**Two candidates measured and declined, so a fifth run doesn't re-open them.**
- **"Re-scan just this target" on the Target page** — the original entry's own named
  prize, and the endpoint now supports it. Declined *this* run on value, not effort:
  with `auto_ingest` on, the watcher already brings a night's subs in unprompted, so
  the button saves a tree walk rather than enabling anything. It is a power-user
  shortcut. Kept filed, down-weighted, with the multi-folder decision it needs stated.
- **"Try harder to locate these N subs"** (a faint-field solve profile) reads like the
  biggest open autonomy item and is **already answered negatively** by the 2026-07-24
  audit that ran the real ASTAP CLI: the extra sensitivity flags (`-check`, `-m 1`,
  `-speed slow`) measured **zero** detection change on faint frames, radius/timeout are
  not levers, and the one thing that did work — the stack-then-solve bootstrap — has
  shipped. The measurements are in the Bugs section's audit block, several hundred
  lines from the idea itself, which is why it still reads open.

**Collisions:** none. `origin/main` was `cdf78d8` from the start of the run to the merge.

---

## 2026-09-07 (Builder, branch `claude/sweet-babbage-9wdpb4`) — a third run finds the backlog dry, so it builds the *missing QA reach* instead (v0.377.1); plus three editor probes that all came back clean, with their methods

**Baseline.** `source scripts/agent-setup.sh`; full suite headless green before
any edit — **5,105 passed, 2 skipped** (20:43). Only docs, `scripts/` and the
version line were touched afterwards, none of which pytest imports.

**Backlog state — dry for the third consecutive run, and again confirmed by
opening entries rather than skimming.** Everything ready-looking that was opened
turned out already answered, and each cost a read. Recorded so a fourth run does
not re-walk them:
- *"Does my colour look right?"* — still blocked on the catalog field that does
  not exist (one flat `nebula` bucket over 157 entries).
- *a 3-frame stack gets no rejection* — overtaken by `auto_reject` on both
  beginner paths, and the advisory half shipped as v0.323.1.
- *auto-scale `min_max_reject_count` k with the frame count* — self-defeating as
  filed, and the Builder note under it already says why: `auto_reject` resolves
  to min/max only **below** `_auto_kappa_min_frames(κ)` (n < 11 at κ=3), where the
  idea's own `2k ≤ n/4` cap forces k=1. It would be a no-op exactly where it fires.
- *the background-mesh `_scaled_box` floor* — measured and closed **twice**
  (2026-09-03 at the default box, 2026-09-04 at the small boxes it had not
  measured); do not reopen without real mosaic pixels.
- *"N spots instead of a percentage"*, *the trailing-"what these buttons do"
  sweep*, *Levels' "From your image" black point*, *the `library_hygiene` double
  walk* — all closed by their own authors with numbers.
- *quiet hours / scheduling for auto-stack* — genuinely not filed and not
  shipped, and deliberately **not** invented here: the Builder's lane (§4) is to
  pick from the list, and the premise (why the owner keeps `auto_stack` off)
  is not in the §1 OWNER FACTS block, so it would have been a guess.
- Also re-checked as already-built before spending anything on them: target
  **merging** (`Library.merge_targets`), the per-panel **mosaic depth map**
  (v0.355.0 + the v0.361.0 aim hint), and the **min/max ignores quality
  weighting** honesty note (`weightingHint.ts`, shared with Settings).

**So the run's move was the one thing three dry runs point at: the QA method
still finding defects is *running the app*, and its reach stopped short of the
priority-1 surface.** `dogfood_probe.mjs` visits the editor and photographs it;
nothing in this repo had ever *clicked* a control in it. That is v0.377.1 —
write-up in [`SHIPPED.md`](SHIPPED.md), including the four things about the Add
menu the drive had to learn (the "More operations" toggle, the label hiding
inside the item's first `<p>`, the Common duplicates forcing index addressing,
and `addOp` inserting on the correct side of the stretch so the op just added is
**not** the last row).

**Three editor/engine probes, run rather than read. All clean — recorded with
their methods so nobody repeats them.** Each was written to be tolerance-free or
ground-truthed, because the file's own history says a badly-shaped fixture
manufactures editor bugs as readily as it hides them.

1. **A generative preview↔export parity sweep over *every* registered op** (the
   A2 class), not the named instances `tests/test_edit_proxy_parity.py` pins. A
   1200×1800 synthetic OSC field (gradient sky, 300 stars, an extended nebula
   blob, a per-channel sensor cast), rendered full-res then decimated, against
   the same field decimated first and rendered at `proxy_scale` 3. Ratio of
   |Δ| proxy to |Δ| full: **0.998–1.003 for every op except four** —
   `detail.sharpen` 0.75, `detail.deconvolve` 0.72, `detail.denoise` 0.75,
   `stars.reduce` 0.88. All four are the *documented* decimation limit (an S30
   star is ~1 px on a step-3 proxy), three of them already carry their own
   advisory helper (`sharpen_understates_on_proxy`, `deconv_understates_on_proxy`,
   `star_reduce_differs_on_proxy`), and the denoise figure is the proxy having
   less noise to remove, not a missing scale term. **No new A2 instance.**
2. **The tolerance-free version of the same question: does each op *respond* to
   `proxy_scale` at all?** Render the same image twice, once with
   `proxy_scale=1` and once with `3`; an op whose pixel-unit parameter is not
   divided by the factor is bit-identical between the two. Result: **every op
   with a pixel-measured parameter responds** (`final_gradient` `dilate_px`,
   `subtract` `box_size`, `chroma_denoise` `radius`, `deconvolve` `psf_sigma`,
   `sharpen` `radius`, `stars.reduce`/`boost_nebula` `size` — the last via
   `star_mask(ctx=…)`, plus `hot_pixels`, whose skip is `proxy_scale`-gated by
   design), and **every op without one is invariant**. This is the cheap check
   worth re-running on any *new* op: it needs no reference render and no
   threshold, and a "flat" row on an op with a `(px)` parameter is the bug.
3. **NaN = no coverage, across every op at both scales.** A picture with a ragged
   uncovered corner and an interior hole, through all 21 ops at `proxy_scale` 1
   and 3: **zero** gap pixels turned finite (a gap becoming 0 would print as
   black *data*) and **zero** NaN leaks into covered pixels. Nothing to fix.

**Dogfood — clean on both drives.** The page probe: **nothing overflowing, no
console errors**; the eighth page-height baseline puts the tallest page at
**3,040 px on a phone** (the Target page), *identical* to the 2026-09-07
measurement and 26 px off the v0.338.1 one. That is now three consecutive
measurements saying the same thing: **do not open a speculative IA slice.** The
new editor drive: all **21** ops added, previewed and removed, undo and redo
applied, **no console error and no failed request**, and every op re-rendered the
preview — including the three geometry ops at their identity defaults, which
issue a render regardless (so "unchanged" in that output really would mean an op
that rendered nothing).

**And then the run got a second task out of the first one's output — by *looking*
at it.** The `--editor` drive came back clean, but the phone screenshot it took
did not: the preview's own control row was sitting on top of a quarter of the
picture. Measured (`toolbar` vs `img[alt="preview"]` bounding boxes, both
widths): **6.2 % of the picture covered at 1440 px in one row, 25.9 % at 420 px
in two**, on six buttons — a mosaic renders a seventh. That is v0.377.2, and it
is the argument for the tool in one step: the drive itself reported "clean",
because *"a quarter of the preview is behind the toolbar"* is not a console
error, a failed request or a preview that stopped re-rendering. **A probe finds
what it was told to look for; the screenshots are still for a person to read.**

**Harness trap that cost this run a 20-minute suite, for whoever next runs the
suite more than twice.** The fourth full `pytest -q` of the session died mid-run
with a traceback and `EXIT=1` — not a test failure: **`No space left on
device`**. `/tmp/pytest-of-root` held **28 GB**. This suite's fixtures write real
FITS libraries, so one full run leaves several GB behind, and pytest keeps the
*three previous* runs' `tmp_path` trees by default — so a run that executes the
suite four times (baseline, per-task, and the sync re-run §11 requires) fills the
session's whole writable allowance on its own. `df` misleads here exactly as the
environment notes say: it read **Used 37 G of 252 G, Avail 59 M**. `rm -rf
/tmp/pytest-of-root` took it to 28 G free and the re-run was clean. **Symptom to
recognise:** a suite that ends in a traceback rather than a `N passed` summary
line, and any shell command afterwards failing with `write error: No space left
on device`. It is not your change.

**A method note worth carrying.** Probes 1 and 2 answer the same question and
only one of them is worth keeping in a run's budget: probe 2 is a handful of
lines, needs no fixture design, and cannot be argued with, while probe 1 needs a
scene shaped like the owner's sky and produces numbers that then need
interpreting. Reach for the invariant before the measurement when the invariant
exists.

**Collisions:** none. `origin/main` was `b7d798c` from the start of the run to
the merge.

---

## 2026-09-07 (Builder, branch `claude/sweet-babbage-0dli9u`) — one task, deep: the measured quantity two runs said the black bands needed (v0.377.0); and a survey that says the backlog is dry, with the greps to prove it

**Baseline.** `source scripts/agent-setup.sh`. The baseline suite was started
first, as §2 requires, but was **cut short at ~75 %** and is not the run's
evidence — see the harness trap below. The authoritative run is the full suite on
the finished tree, reported in the merge.

**What was picked, and the survey behind it — recorded so the next run doesn't
repeat the search.** Every ready-looking entry I opened turned out to be already
answered, and each one cost a read:

- *"Does my colour look right?"* — blocked on a catalog field that does not exist
  (one flat `nebula` bucket over 157 entries).
- *auto-detect a dark↔light exposure mismatch* — **closed in place**: slices (b)
  and (c) shipped long ago and (a) shipped as `calibration_warnings`.
- *calibration match-confidence on the Stack form* — shipped as v0.321.0.
- *"Try harder to locate these" / relaxed ASTAP retry* — the levers it guesses at
  were **measured as non-levers** in 2026-07, and the ladder in `astap.py` already
  implements what the measurement said does work (never bin past 2×, keep a
  full-res `-s 1000` rung).
- *a 3-frame stack gets no rejection* — overtaken; both beginner paths seed
  `auto_reject`.
- *the trailing-"what these buttons do" sweep* and *Levels' "From your image"
  black point* — both closed by their own authors the day they were filed.
- *"N spots instead of a percentage"* — stood down with numbers (1,323 blobs on a
  scene with **no** trail).

That is the state AGENTS.md §1 describes, and it is now two runs deep. **The
useful move was not another backlog read**: it was to take the one thing a prior
run had explicitly left as a *requirement* rather than a task.

**The task: two declinations had already specified it.** 2026-09-04 declined a new
caption for the black bands around a mosaic (the health panel already speaks on
that page); 2026-09-07 declined *"four words inside the existing sentence"* after
going to the statistic and finding they would be **false** —
`stacker.coverage_thin_fraction` excludes uncovered pixels from **both** of its
terms. That second declination ended: *"If the black is ever worth a sentence it
needs its own measured quantity (an uncovered share, which nothing records
today)."* Building that quantity — and only then the sentence — is v0.377.0.
**The pattern worth reusing: a well-written stand-down is a spec.** Two runs had
already done the hard part (establishing what would be dishonest and why); what
was left was a small, well-fenced piece of work that neither of them could take
without it.

**The measurement decided the threshold, and one row of it was a surprise.** Eight
geometries through real `run_stack`: an **undithered single field on the reference
canvas is already 3.10 % uncovered**, because reprojection leaves a NaN margin a
couple of pixels wide. So "any black at all" would have fired on every stack the
app has ever made — the same mistake the pre-v0.320.2 `coverage_min` test made —
and the floor had to be set from data (12 %, against honest cases at 1.1–5.1 % and
ragged ones at 19.8 % / 36.6 %). The full table is in [`SHIPPED.md`](SHIPPED.md).
Also worth carrying: **the thin share reads 0.00 % on all eight rows**, including
the two that are a fifth and a third empty — the existing note is not merely quiet
about the black, it is structurally incapable of mentioning it.

**An upgrade-safety decision, taken the same way v0.375.0 took its own.** The
column needed no `SCHEMA_VERSION` bump: `Project._check_schema` *raises* on a DB
stamped newer than the build, so a bump would stop the **previous** Docker image
opening the owner's projects — a rollback bomb on an install with no backup. The
column went into `SCHEMA_SQL` and arrives through `_reconcile_table_columns`,
which already runs on every open and already promises exactly this ("any additive
column (past or future)"). It had a mechanism and no user; now it has one. Two
tests pin both directions.

**Harness trap that cost this run ~25 minutes — the sibling of the `pgrep -f`
self-match already recorded on 2026-09-07.** `pkill -f "pytest -q"`, used to stop
the contaminated baseline before starting the real run, **also killed the run it
was about to start**: the launching shell's own command line contains that literal
string, so the new process matched the pattern the moment it started (both jobs
died with exit 144). Same root cause as the `pgrep` loop that never terminates,
same fix: match on something the launching command does not itself contain, or
just let the old run finish.

**A smaller one, for whoever next edits a long-running baseline.** Editing the
working tree while the baseline suite is still running makes that baseline
worthless from the first edit onward — pytest imports modules as it reaches them.
Either wait, or accept that only the post-change run is evidence and say so.

**Collisions:** none. `origin/main` was `a0c9ea8` from the start of the run to the
merge.

---

## 2026-09-07 (Builder, branch `claude/sweet-babbage-25fa4c`) — two measured performance/friendliness fixes (v0.376.1, v0.376.2) and one copy change declined *because* it was measured

**Baseline.** `source scripts/agent-setup.sh`; full suite headless green before
any edit — **5071 passed, 2 skipped** (21m46s); `tsc` clean, `vitest` 3290 across
238 files, `vite build` clean.

**What was picked and why.** The Bugs section is still in the state AGENTS.md §1
describes — every open entry gated on data an agent cannot supply, or a
stand-down that already carries its numbers — and the last run shipped the
⭐ wishlist beginner feature, so the cadence did not owe another one. What *was*
ready was the four-shape performance lead whose shape (a) shipped as v0.374.9:
shapes (b)–(d) were re-sized against the new number, as that entry instructs, and
**(c)** was taken. The Sky-map coverage-mask idea was taken as the second task
because its own gate — "measure before building" — was answerable from the repo.

**The lesson of the run: the measurement decided all three outcomes, in three
different directions.**

1. **v0.376.1 (shape (c)) — measured, then built.** The Stack page fired two
   `stackEstimate` requests, and the whole cost of a sizing is
   `compute_mosaic_canvas` (one WCS read per sub), which the second request
   re-derived identically because it asked about a different *drizzle scale*.
   Split into `estimate_stack_basis` + `estimate_stack_from_basis`: **2.18 s →
   1.13 s** on a 9-panel, 5,477-sub mosaic, and a second sizing off a held basis
   costs **44 µs**.
2. **v0.376.2 (the Sky-map idea) — measured, and the measurement split the
   entry in half.** `stack_coverage_mask` on a 104 MB (3494×2470×3) master costs
   **14–23 ms warm**, which *declines* the entry's shape (b) (a composed-RGBA
   cache would buy tens of milliseconds and own an invalidation bug). It says
   nothing about the case the entry was really about — those megabytes come off
   a NAS, per target, on every visit — so shape (a) shipped: a strong `ETag` and
   `private, no-cache` in place of `no-store`.
3. **The "say the thin edge looks dark" follow-up — measured, and declined.** The
   backlog left it as "four words inside the existing sentence". The statistic
   behind the sentence, `stacker.coverage_thin_fraction`, **excludes uncovered
   pixels by construction**: `count((cov > 0) & (cov < 0.25 * peak))` over
   `count(cov > 0)`. Probed with the thin fringe held at 500 px and the black
   region grown, the thin count stays **500** while the reported share moves
   0.0500 → 0.0625 → 0.0833 → 0.1250 purely because the covered denominator
   shrinks. The black band is in neither term, so the four words would have been
   false. Recorded in the entry with the numbers so nobody ships them.

**A trap worth naming for the next run.** `estimate_stack` returns
`budget_bytes` derived from the box's *available* memory when
`memory_budget_gb=None` — so "the refactor returns exactly what the original
returned" cannot be asserted across two calls at the default budget; the number
moves by a few kilobytes for reasons that have nothing to do with the change.
The equivalence test parametrises over two **explicit** budgets instead. Anything
comparing two `StackEstimate`s has the same problem.

**A shape that paid off.** Both shipped tasks are "the answer is fully determined
by inputs cheaper than the answer" — a canvas determined by the frames and
`mosaic_canvas`; an overlay determined by two files' `mtime:size` plus the saved
orientation. Naming those inputs in code (`StackCanvasBasis`, `_file_stamp` +
`_derived_image_etag`) is what makes the saving safe, and in the first case a
test now *enforces* the claim (a basis refuses options whose `mosaic_canvas`
disagrees with it). Four sibling `no-store` image endpoints were left open on
purpose: same shape, different invalidation inputs, none measured — one at a
time, with the inputs enumerated, not as a sweep.

**Collisions:** none. `origin/main` was unchanged (`984e8576`) from the start of
the run through the merge.

---

## 2026-09-07 (Builder, branch `claude/sweet-babbage-rb61y0`) — shipped the ⭐ "My wishlist" beginner feature whole (v0.375.0 + v0.376.0); dogfood CLEAN; one upgrade-safety decision taken *against* the backlog entry

**Baseline.** `source scripts/agent-setup.sh`; full suite headless green before
any edit — **5045 passed, 2 skipped** (22m53s). Ended at **5071 passed, 2
skipped** (+26 Python), with `tsc` clean, `vitest` 3290 across 238 files (+12),
and `vite build` clean. Both commits independently green; PR #757 merged.

**What was picked and why.** The Bugs section is in the state AGENTS.md §1
describes — every open entry is gated on data an agent cannot supply (a real
cloudy night's subs, a real solved frame with non-zero field rotation) or is a
stand-down that already carries its measurement — so nothing there was startable
without blind-flipping a threshold on the on-by-default hot path. The last eleven
merges were patch-level polish (v0.374.1 → .11), so a feature was genuinely due
under the standing beginner-feature cadence, and the Scout had filed a ⭐ M-sized
one that morning with its slicing already worked out. Taken top-down, not
invented.

**The one decision worth recording: the backlog entry asked for a
`SCHEMA_VERSION` bump, and shipping it that way would have been a latent
rollback bomb.** The entry's own words were *"a new additive table +
`SCHEMA_VERSION` bump + `_migrate_schema`, §9 — never a reset"*, which is the
right instinct and the wrong mechanism for **this** table. `Library._check_schema`
raises `RuntimeError("… is newer than this build")` on `v > LIBRARY_SCHEMA_VERSION`
— so bumping 5 → 6 means the **previous Docker image cannot open the registry at
all**. On an install that is upgraded in place, has no backup, and whose owner is
non-technical, that converts "pull the old image back" — the one recovery move
available when a release misbehaves — into a bricked app. The table went into a
new `_AUX_TABLES_SQL` instead, re-run idempotently on every open via
`_ensure_aux_tables` (called from *both* `_init_schema` and `_check_schema`), so
it is additive in **both** directions: a new build adds it to an old registry,
and an old build ignores a table it has never heard of. That is exactly what
`_check_schema`'s own comment already promised ("the schema only ever *adds*; the
new code simply ignores any leftover tables") — the promise just had no mechanism
behind it for tables, only for columns (`_ensure_columns`). Two tests pin it: a
hand-built v2 registry gains the table with its targets intact, and a
current-version registry with the table dropped self-heals.
**Generalisation for the next agent:** `LIBRARY_SCHEMA_VERSION` should be bumped
only for a change an older build would *mis-read*. A purely additive table is not
that, and neither is an additive column (`_ensure_columns` already backfills
those). Prefer the idempotent-DDL route and leave the version alone.

**Two smaller things learned in the code.**
- **A second-resolution timestamp is not an order.** `_utc_iso()` is
  `%Y-%m-%dT%H:%M:%SZ`, so three objects starred in one burst all carry the same
  `added_utc` and `ORDER BY added_utc` fell back to whatever SQLite felt like —
  in practice alphabetical, an order the owner never chose. Fixed with
  `ORDER BY added_utc, rowid`. Worth checking wherever a user-ordered list is
  keyed on `_utc_iso()`.
- **The `<button>`-inside-`<a>` trap, one door down from v0.374.11's
  labelable-`<button>`-in-a-`<label>`.** A captured life-list tile is a `<Link>`;
  putting the wishlist star inside it is invalid HTML and swallows one of the two
  clicks. The star is a **sibling**, absolutely positioned over the tile
  (top-left, so it never lands on the top-right "Got it" badge). Same family of
  bug, different element pair — if a third turns up, it is worth a lint rule.

**Dogfood (`scripts/agent-dogfood.sh`, sample) — CLEAN.** No overflow, no console
errors. Tallest page on a phone is still the Target page at **3040 px** (the
v0.338.1 baseline measured 3014 px), and `/life-list` — the page this run added a
section and ~160 star buttons to — comes in at **3008 px on a phone / 1453 px on
desktop**, i.e. the new section costs nothing while the wishlist is empty,
because it renders nothing at all. So the standing IA measurement still says
"don't open a speculative slice": three passes now agree.

**Nothing filed.** No verified bug found, and per §4 a Builder does not invent
features — the one lead worth noting is recorded in `IMPROVEMENTS.md`'s Shipped
line, not here.

---

## 2026-09-07 (Scout, branch `agent/scout-qa-mosaic-fold`) — stacking-engine re-audit CLEAN (with empirical probes of the newest code); dogfood CLEAN; one beginner feature filed

**Baseline.** Fresh `source scripts/agent-setup.sh`; the stacking + calibrate
subset green — **1653 passed / 2 skipped / 3392 deselected** (`-k "stack or
accumul or align or mosaic or drizzle or calibrat or reject or weight"`,
`-p no:pytest-qt` fallback), 8m41s. So a real bug was distinguishable from a
pre-existing failure. No new verified bug filed — nothing rose above the noise
floor, so per AGENTS.md §2 nothing was manufactured.

**Lead: the newest stacking-engine code, read adversarially *and* probed.** The
engine has ~18 prior clean audits, so this run led with the code changed since
the last one rather than re-treading the repeatedly-clean math:

- **`stack/pointings.py` — the v0.374.7 fold optimisation** (`fold_pointings`,
  `_cluster_distinct`, `pointing_groups`, `detect_mixed_pointings`). Traced the
  wrap-safety argument (a cell key never straddles the 0°/360° seam; the seam is
  handled by the unit-vector clustering, not the fold) and the soundness gate,
  then **drove it empirically**: (a) a 3-panel mosaic of 900 dithered subs folded
  to distinct cells gives a grouping **bit-identical** to the exact O(n²)
  clustering, with each panel's 300 subs correctly its own; (b) a dithered panel
  straddling RA≈0 folds into two cells but `pointing_groups` still returns one
  panel (`None` — no split), because the clustering links them on the sphere;
  (c) two panels 5° apart split into two labels as intended. Correct — the fold
  cannot move the answer that matters. **CLEAN.**
- **`calibrate/defects.py` — the v0.367–v0.371 sensor-defect repair** (the newest
  code that *writes* image pixels, so the highest corruption risk).
  `find_sensor_defects` (per-phase local-median outlier + the `max(global,
  local)` scale + the `max_fraction` refusal), `_local_fill`, `_local_robust_scale`,
  and `DefectMap.repair`. **Probed:** a defect surrounded on all 8 same-phase
  neighbours by *other* defects is left untouched (all-NaN column → the documented
  "leave it alone" case), while the surrounding defects that still have working
  neighbours repair; a lone defect is replaced by the exact median of its 8
  same-phase neighbours (44.0 vs the hand-computed 44.0). The repair is applied
  after the pedestal subtract and before the flat divide (`apply.py::apply_raw`),
  in the raw Bayer domain, with a shape-mismatch/`None` no-op. **CLEAN.**
- **`stack/output.py` parity** (`pack_unit` rounding shared by all six export
  paths; `_to_uint16_linear` / `linear_scale_anchors` — the "full data" TIFF).
  The min→max white-point anchor is the already-traced, deliberately-left item
  under Bugs (severity: not a new find), not a regression. **CLEAN.**
- **`stack/align.py`** (the v0.367.1 `not (both within cap)` NaN-safe subpixel
  guard at both sites) and **`webapp/watcher.py`** (`StabilityTracker`
  in-place-rewrite re-arm, stranded-batch re-offer, the mtime clock-skew note
  already filed under Bugs). Read; **CLEAN**.

**Dogfood (`scripts/agent-dogfood.sh`, sample-loaded).** Boot → sample → stack →
probe all succeeded; **no element overflowing, no console errors**, page heights
in line with the recorded baseline (tallest **3,040 px**, phone Target page;
desktop Target 2,037 px). Eyeballed the stack→result path the run was told to
weight: the Stack page's Auto defaults + plain-language method/luminance notes,
the Target page's guidance banners / "Is it enough yet?" / frames table, all
read clean and beginner-safe. Nothing to fix.

**Backlog.** Idea supply is not the constraint here — nearly every beginner
feature I generated while looking for a gap (moon-aware planning, "try something
new tonight", mosaic panel-balance guidance, a night-after-night deepening reel,
before/after, A/B compare, a famous-objects bucket life-list) is **already built**
— so I filed exactly one that I verified is genuinely absent (a *personal*,
user-curated wishlist that drives the Tonight planner, as opposed to the fixed
famous-objects life-list) rather than pad the ~49 open ideas. No pruning needed:
the Bugs section is already open-bugs-only and the last three runs found it clean.

## 2026-09-07 (later still) — Builder run (branch `claude/sweet-babbage-mg8isx`): three shipped, and two traps worth carrying forward

**The run.** Baseline green before any change (**5,023 passed / 2 skipped**, full
suite headless, 21:40). Shipped **v0.374.9** (the `wcs_from_text` fast path — the
residue the previous run filed with its number), **v0.374.10** (the
grainier-restack note's runaway percentage) and **v0.374.11** (`HintLabel`'s
info icon, which turned out to be a bug). Write-ups in
[`SHIPPED.md`](SHIPPED.md) and the entries themselves.

**Backlog state, checked the same way the last three runs checked it.** "Bugs
(fix these first)" still holds only gated entries and stand-downs that carry
numbers. The Performance section's own top lead was the best available work and
its shape (a) was taken; (b)–(d) were **left open with a note that the problem
they were sized against is now ~1 s rather than ~4.7 s**, because a lead that
keeps its old numbers after the fix gets re-picked at the wrong priority.
Task 2 and task 3 came off the Autonomy/Friendliness lists. Nothing was invented.

**Trap 1 — an `astropy.io.fits.Header` is expensive to *read*, not just to
build.** The v0.374.8 lead correctly identified `astropy.wcs.WCS()` construction
as the cost and `Header.fromstring` (0.047 ms) as cheap. Both true, and a
prototype built on exactly that — keep the `Header`, replace only the `WCS`
construction — measured **0.47 ms** against the full path's 0.85 ms, i.e. it
left most of the win on the table. The missing term is `Card._verify`, which is
re-run on **every `key in header` lookup**: ten membership tests cost about as
much as the parse. Scanning the 80-column records directly measures **0.07 ms**.
If you are optimising anything that reads a FITS header a few keys at a time,
count the lookups, not just the parse.

**Trap 2 — an interactive element inside a Mantine control's `<label>` is
labelled by that label.** Making `HintLabel`'s info icon a `<button>` broke
seven `Settings.test.tsx` queries at once (`getByLabelText(/ASTAP path/)` →
"found multiple elements"), and changing the `aria-label` did **not** fix it:
testing-library matches a wrapping `<label>` independently of `aria-label`,
because a `<button>` is a *labelable* element per HTML — so the field's own name
genuinely named two controls, for a screen reader as much as for the test. The
fix is `component="span" role="button" tabIndex={0}` (plus Enter/Space
handling): a span is not labelable, so the label keeps naming exactly one
control. Worth knowing before adding any control inside a Mantine `label` prop.

**Method note — the "does it change anything?" bar for a speed-only change.**
v0.374.9 claims to be a pure optimisation, so the tests assert the fast WCS
re-serialises **byte-identically** through `to_header(relax=True)` and
transforms a pixel grid **bit-identically**, across ten header shapes, and
`test_mosaic.py` pins the union canvas identical with the fast path disabled.
That is the same standard the 09-07 (earlier) run set for its two changes (664
clustering configurations; 0.0 deviation over 200 WCSs) and it is the right one:
none of these would have been safe to ship on the argument alone. The one place
the fast path is *deliberately* wrong is by refusing — it declines anything
outside a plain equatorial TAN header rather than approximating it.

**And one micro-optimisation deliberately not taken**, so nobody re-finds it:
assigning `wcs.cunit` parses `"deg"` into an `astropy.units.Unit` and costs
~0.09 s of the remaining 1.06 s on 5,477 subs. Setting it only when the header
carries `CUNIT1` passes every byte-identity test and buys ~8 % — and was
reverted, because it makes the object's construction depend on a keyword's
presence for no gain on the owner's own data (both our serialisation and an
ASTAP sidecar carry `CUNIT`).

---

## 2026-09-07 (later) — Builder run (branch `claude/sweet-babbage-retf5t`): the backlog was dry, so the app was **timed at the owner's scale** — and two 14-second endpoints fell out

**The run.** Baseline green before any change (**5,012 passed / 2 skipped**, full
suite headless, 17:17). Shipped **v0.374.7** and **v0.374.8**, both pure
performance with no behaviour change; write-ups in [`SHIPPED.md`](SHIPPED.md).

**Backlog state — dry again, and confirmed the same way the 09-06/09-07 runs
confirmed it.** "Bugs (fix these first)" holds only gated entries (real
elongated-target data, a legacy library shape, an external binary) and
deliberate stand-downs that carry numbers. The **Features that serve real
workflows** list was opened top-down: both ⭐ owner-requested entries are drained
to their sign-off-gated slices (*Tonight* (a)+(b) shipped v0.95.0/v0.96.0, only
the network weather slice remains; *Bulk upload* (a)+dropzone+progress+folder
picker all shipped), *"Did it get better?"*, *"Have I shot enough?"*, *"Night by
night"*, *"Will it fit?"*, *"Share card"* and *"Last night"* are all shipped in
their named slices, *"Does my colour look right?"* is still blocked on the
catalog field that does not exist, and the crop-anything idea is still declined.
`grep -rn "TODO\|FIXME"` over `seestack/` and `webapp/` returns **one** hit, in
the deprioritised desktop GUI. Nothing was invented to fill the gap.

**So the run went looking empirically instead — and the method is the finding.**
Almost every `tests/webapp/` test builds a library of a *handful* of frames, so
**no per-target endpoint's cost had ever been measured at the size the owner
actually has**. Seeding one target with **5,477 solved subs on a 9-panel mosaic**
directly into the project DB (no FITS on disk — these endpoints read frame rows;
~2 s to seed) and timing all **36** per-target read-only GETs, enumerated from
the app's own OpenAPI schema the way `test_first_run_endpoints.py` does, took
about a minute and found two endpoints at **13.8 s** and **13.3 s**. Both are
user-facing on every load. Neither is visible at test scale, and neither would
ever have surfaced from reading the code.

**The distribution, for whoever measures next** (5,477 frames, best of 3, after
both fixes; the two headline rows are `before → after`):

| endpoint | ms |
|---|---|
| `/stack-estimate` | 13 762 → **4 664** |
| `/rejection-outlook` | 13 306 → **4 774** |
| `/frames/reject-summary` | 138 |
| `/frames/auto-grade` | 127 |
| `/frames` | 96 |
| `/transparency-trend` | 96 |
| `/calibration-suggestions` | 91 |
| `/frames/sky-brightness` | 90 |
| `/focus-trend`, `/live-session` | 90, 89 |
| `/best-frame`, `/nights`, `/session-recap`, `/restack-gain` | 83, 81, 75, 71 |
| `/mosaic-map` | 25 |
| the other 22 | ≤ 11 each |
| **all 36 together** | **28 304 → 10 619** |

Everything outside the top two is healthy for 5,477 rows; the ~90 ms band is
frame-table reads and is not worth touching. **Do not re-measure this** — it is
the same shape and the same method both times; re-measure only after changing
one of these paths.

**Two fixes, both exact.** v0.374.7 folded the shared panel-clustering gate
(`pointing_groups` 1.152 s → 0.012 s; `detect_mixed_pointings` 2.650 s →
0.021 s) and v0.374.8 vectorised `footprint_radec_deg`
(`compute_mosaic_canvas` 13.87 s → 4.75 s, identical canvas). Both were verified
against the unfolded / per-corner path rather than merely tested: **664**
clustering configurations sweeping panel separations through both link distances
with zero mismatches, and a **0.0** deviation on the footprint transform over 200
WCSs. That is the standard to hold a "this only changes the speed" claim to —
neither change would have been safe to ship on the argument alone.

**What was deliberately not done.** The remaining ~4.7 s on those two endpoints
is `wcs_from_text` (0.755 ms × 5,477 ≈ 4.1 s, all of it `astropy.wcs.WCS()`
construction). Both plausible fixes — a fast direct-assignment WCS build, and
memoising the canvas per target — are judgement calls that need their own
measurement, and the second is the staleness trade v0.374.6 warned about. Filed
in [`IMPROVEMENTS.md`](IMPROVEMENTS.md) → Performance with the numbers, plus two
smaller frontend-side observations found while checking it: `Stack.tsx` fires
`stack-estimate` **twice** (both legitimately, so ~9.3 s per page load for the
owner), and its query key carries five options that **do not affect the canvas**
— so moving the κ slider re-pays a 4.7 s canvas computation purely to refresh a
rejection note.

**A trap worth knowing.** Editing engine source *while* a `pytest` run is in
flight does **not** contaminate that run — pytest imports the modules at
collection time, so the process holds the pre-edit code, and deferred
`from … import` inside functions resolves from `sys.modules`. That is why the
baseline here is trustworthy despite overlapping the first edits. It also means
the reverse: a suite started before a fix does **not** verify it, so each of the
two versions above got its own full run (17:17, 16:42, and the final one).

---

## 2026-09-07 — Builder run (branch `claude/sweet-babbage-55nznt`): a drained backlog, four empirical probes that all came back clean, and the **first browser measurement of the first-run app**

**The run.** Baseline green before any change (**5,009 passed / 2 skipped**, full
suite headless, 22:30). Shipped **v0.374.5** (a test-only net) and **v0.374.6** (a
measured close). Both write-ups in [`SHIPPED.md`](SHIPPED.md).

**Backlog state — dry, and confirmed by opening things rather than by skimming.**
"Bugs (fix these first)" is in the gated state the runs below describe. The
**Features that serve real workflows** list was opened top-down and every
beginner-facing candidate in it turned out to be already shipped or already
declined with numbers: *"Night by night"* (all four slices, v0.144.0 + v0.171.0),
*"Does my colour look right?"* (blocked on a catalog field that does not exist —
one flat `nebula` bucket over 157 entries), *"N spots instead of a percentage"*
(measured and closed: 1,323 blobs on a scene with **no** trail), *the
calibration match-confidence card* (v0.321.0), *the crop-anything idea* (declined
once, on purpose). Nothing was invented to fill the gap.

**Four probes, run rather than read. All clean — recorded so nobody repeats them.**

1. **Every read-only endpoint on a first-run install** — 52 parameterless GETs on
   an empty data root, 38 per-target GETs on a target ingested and never stacked.
   **0 of 90 returned 5xx.** This one became a permanent test (v0.374.5); the
   other three did not, and this block is their record.
2. **The one-click Auto, across ten realistic scenes** (clean / noisy / very noisy
   single fields, a mosaic with and without NaN gaps, a strong gradient, a blown
   galaxy core, a star cluster, a nearly-blank sky, a dim low-signal sky).
   Healthy everywhere: sky lands at 0.14–0.23, R/G/B stays neutral to ~0.006, no
   non-finite pixel ever appears **inside** the covered area, and a mosaic's gaps
   come through at exactly their input fraction (8.82 %). The output can sit a few
   thousandths **below 0** on the denoise-firing scenes (min −0.005); that is not a
   bug — `output.pack_unit`'s contract is that the caller clips, and all six export
   paths do.
3. **Whole-recipe preview↔export parity**, the A2 class, at mosaic scale
   (3600×2400, `proxy_scale` 3) and single-field scale (2100×1400, scale 2), applied
   **op by op** to the same sampled pixels so the divergence could be attributed
   rather than just observed. Everything up to and including `tone.curves` agrees
   to a mean of **0.0037** (≈1/255). The whole remaining gap is `detail.sharpen`
   — mean 0.0192, chroma 0.180 preview vs 0.215 export — which is the *documented*
   limitation (`sharpen_understates_on_proxy`, `_SHARPEN_PROXY_FLOOR_PX`) and is
   surfaced to the user by the existing advisory. **Do not re-open it as a bug**;
   at `proxy_scale` 3 an S30 star is ~1 px on the proxy, so no parameter scaling
   can recover what the decimation already threw away.
4. **The `library_hygiene` double walk**, the backlog's own "measure before you
   cache" item — closed at ~196 ms a refresh; numbers and method in
   [`SHIPPED.md`](SHIPPED.md) under v0.374.6.

**Dogfood — clean, twice, and the second one is new.** `scripts/agent-dogfood.sh`
on the sample-loaded app: **nothing overflowing, no console errors**, tallest page
still the Target page at **3,040 px on a phone** (3,014 px at v0.338.1 — the
seventh page-height baseline, and it says what the last few have: *do not open a
speculative IA slice*).

**Then the same probe against an app with no data at all** — a first-run install,
which every dogfood measurement before this one has missed, because the script
loads the sample before it probes. Also **nothing overflowing, no console
errors**. First-run heights, for the next run to compare against:

| page | phone | desktop |
|---|---|---|
| `/life-list` | 2,779 px | 1,224 px |
| `/` (Dashboard) | 1,402 px | 1,028 px |
| `/library` | 1,252 px | 923 px |
| `/combine` | 1,196 px | — |
| `/settings` | 1,067 px | — |

`/life-list` is the tallest first-run page by 2× and that is *correct*: it is a
bucket list, it already collapses to 12 of 110 behind "Show all 110 still to
shoot", and its height is the two catalogs' preview grids, not stacked banners.
The Dashboard reads well empty — the plate-solve banner, "Your first image"
(0 of 6, each step linked), the sample-image offer, zeroed stat tiles, then a
proper "No stacks yet" empty state. **Nothing to fix was found on either pass.**

**And it is now a flag, not a method note** — `scripts/agent-dogfood.sh --empty`.
It was an ad-hoc second server for the length of this run, and the script's own
header says why that is not good enough (*"Every run used to reinvent how to get
to that point, so in practice the pass degraded back into reading code"*). It
boots on its own empty data root, its own port (8812) and its own
`$DOGFOOD_DIR/empty/` scratch, so it follows a normal pass without disturbing it,
and reuses the playwright install the normal pass drops in the shared scratch dir.
The default path is untouched (smoke-tested both ways). `AGENTS.md` §7 now points
at it beside the normal pass.

**Harness trap that cost this run ~20 minutes, for the next agent.** A background
wait loop spelled `until ! pgrep -f "python -m pytest -q"; do sleep 20; done`
**never terminates**: `pgrep -f` matches its own shell's command line, which
contains that literal string, so the loop waits on itself for ever. Match on
something the waiting command does not itself contain, or poll the log.

---

## 2026-09-06 (later) — Builder run (branch `claude/sweet-babbage-cqqyi1`): the newest-code audit again — a promise qualified only *after* the click, an engine probe that cleared `defects.py`, and a clean dogfood

**The run.** Baseline green before any change (**5,007 passed / 2 skipped**, full
suite headless, 22:32). Shipped **v0.374.3** and **v0.374.4**; both write-ups in
[`SHIPPED.md`](SHIPPED.md).

**Backlog state.** "Bugs (fix these first)" is in the same gated state the run
below records. What is new is that the **feature** list is now in it too. Four
candidates were opened and put back *before a line was written*:

* *"let the cover also be an edited export"* — its own 2026-08-05 note already
  says the case is served (`_apply_editor_to_run` records a real `stack_runs`
  row, so the existing "Set as cover" works on an edit); only a loose
  download/share export is left, and it is marginal.
* *"a 3-frame default stack gets no rejection"* — overtaken; the advisory half
  shipped v0.323.1.
* *the "is this date when you shot it or when the app did something" sweep* —
  finished at v0.321.3 (Gallery card, History row, sky footprint).
* *"the pinned-options note needs a button"* — **already shipped** as
  `adoptGlobalsPatch` + *"Use my global settings"*, v0.372.0. Found by grepping
  the *mechanism* rather than the feature's title, which is the fifth instance
  of that §4 warning.

**So: audit the newest code, per the run below.** v0.370–v0.374.2 — the
sensor-defect census, its one-click button, the pinned-options report, the
save-the-delta — is what landed after the newest recorded sweep. Two verified
defects came out of it, both in the census/offer *copy*.

**The transferable method, because it is a variation on the last two runs'.**
v0.374.2 found two advisory notes that contradicted **each other** on a shared
trigger. This run found one control that contradicts **itself across time**:
`defect_repair_offer`'s on-state was carefully qualified (*"except 1 target"*,
built deliberately, with its own test), and its off-state — the same fact, the
same targets, read one click *earlier* — made the unqualified promise. So: **for
any button whose copy makes a promise, ask whether the promise is qualified in
the state that persuades, or only in the state that confirms.** The qualified
state is the easy one to get right, because you write it while thinking about
the exception; the offer is written while thinking about the feature.

**Engine half: probed by running it, and `seestack/calibrate/defects.py` traces
CLEAN.** The census/repair code is the newest engine code in the tree and has
already yielded two bugs (v0.369.4, v0.371.1), so it was probed rather than
re-read, on a Seestar-S30-shaped master (1920×1080, bias pedestal + readout ramp
+ dark-current tilt + corner amp glow + per-sub shot/read noise averaged over
*N* subs):

* **False positives: 0**, at every combination of glow peak (0 / 500 / 2,000 /
  8,000 e⁻) and master depth (10 / 30 / 100 subs). This is the v0.371.1 fix
  holding at depths that fix never tested.
* **False negatives: 0** with 400 hot pixels (200–4,000 ADU above local), 40
  stuck-low, and two warm *columns* planted — 2,599 flagged, 2,599 correct. The
  column case matters and had not been probed: within a phase a bad column is
  one of five columns in the 5×5 window, so the median is unmoved, and
  `DefectMap.repair` then medians the six same-phase neighbours that are *not*
  in the column.
* **Census == what a run repairs**, on that master: 2,599 both ways.
* **Repair on a light frame**: only genuinely-defective pixels changed (57 of
  them inside a star's core, all planted); residual at repaired non-star
  defects — median **5.8 ADU** against a sky σ of 8, p99 22.7. The worst
  residual over the *whole* frame is 33 ADU, and every large one sits in a
  star's wing, where a ±2 px same-phase neighbour genuinely carries different
  flux. That is the method's inherent limit, not a defect.

**Cost measured rather than asserted.** v0.374.3 makes the offer's per-target
walk happen with the switch **off** as well as on, so the walk was benchmarked
rather than argued about: **0.65 ms per target** (200 targets → ~130 ms), once
per 60 s poll, and only while the Calibration page is open *and* some master
reports repairable defects. The "clean library never pays for it" guarantee is
unchanged and still tested.

**Dogfood pass — CLEAN** (`scripts/agent-dogfood.sh` at v0.374.2: real app,
bundled M42 sample ingested + stacked + auto-edited, Playwright at 1440 px and
420 px). Probe: *nothing overflowing, no console errors.* **Page-height
baseline, seventh measurement:** tallest on a phone is the Target page at
**3,040 px** — identical to the sixth measurement — with `/life-list` second at
**3,008 px** and the editor third at 2,815 px, i.e. the same three pages in the
same order at the same heights. The standing IA rule still says do not open a
speculative slice.

**One traced non-finding, recorded so it isn't re-investigated.**
`routers/calibration.py`'s census cache evicts with
`cache.pop(next(iter(cache)))`. Two overlapping threadpool requests could in
principle both name the same oldest key, and the second `pop` would raise
`KeyError` → a 500. **Unreachable in practice:** it needs the cache at its
128-entry cap (128+ dark/bias masters in one library) *and* two simultaneous
cache misses. Give the `pop` a `None` default if that file is ever touched for
another reason; not worth a commit of its own.

**Ended the run at two tasks.** Both are small by design — the audit found what
it found — and AGENTS.md §2 is explicit that a short run leaving `main` green
beats a manufactured third item.

---

## 2026-09-06 — Builder run (branch `claude/sweet-babbage-0pqzni`): a clean dogfood, a wrong-advice bug found by reading the *pair* of notes rather than either one, and three stale headers struck

**The run.** Baseline green before any change (**5,004 passed / 2 skipped**, full
suite headless, 20:06). Shipped **v0.374.2** — the streaked-frames caution now
asks the engine what can actually remove a trail; write-up in
[`SHIPPED.md`](SHIPPED.md).

**How the bug was found, because the method generalises.** The backlog entry
that led here (*"`rejectionOn` still asks did a pass dispatch?"*) was filed as a
**consistency** item — two definitions of one fact, worth unifying, no known
defect — and its own note said the gap was already covered by
`minMaxRejectHint`, so it might be a no-op. It was not. Enumerating the
**joint** state of the three notes that can fire on the same stack (the caution,
`minMaxRejectHint`, `rejectionReachNudge`) rather than checking each one alone
turned up a band, **1–2 accepted+solved subs**, where two of them fire together
and say opposite things — and the one reading the hand-written predicate was the
wrong one. Neither note is wrong in isolation; the defect only exists in the
pair. **Worth repeating on any surface where two advisory notes share a
trigger:** tabulate the frame counts / toggle combinations both can reach, not
each note's own logic.

**Dogfood pass — CLEAN (`scripts/agent-dogfood.sh` at v0.374.2: real app,
bundled M42 sample ingested + stacked + auto-edited, Playwright at 1440 px and
420 px).** Probe: *nothing overflowing, no console errors.* Screenshots of the
editor and the Stack form read coherently — the Stack form's own advisory stack
(the Auto-method note, the luminance-flatten nudge with its button, the sizing
line) is three blocks and does not pile up.

**Page-height baseline, sixth measurement — the standing IA rule still says do
not open a speculative slice.** Tallest on a phone is still the Target page at
**3,040 px**, against 3,014 px measured at v0.338.1 — **+26 px across ~36
versions**, i.e. flat. The one number worth carrying forward is that
**`/life-list` is now second at 3,008 px on a phone**, within 32 px of the
Target page and ahead of the editor (2,815 px); it was not in the top three at
the last measurement. That is not a finding — nothing overflows and nothing is
stacked badly — but it is the page to measure first if a *measured* slice is
ever wanted, rather than the Target page the banner still names.

**Backlog curation (three headers, no content deleted).** Each of these read as
live work at the top of a priority section while its own body recorded it
shipped, which is the failure mode the three-file rule exists to prevent:
- the walk-away blind κ-σ entry — closed by v0.334.1 / v0.335.0 / v0.337.0–.1,
  whose ✅ blocks sit ~90 lines *below* the header;
- the cross-target *"plate-solving isn't set up"* Dashboard banner — **already
  built**, and better than the filed shape: `dashboard/astapReadiness.ts` reads
  `GET /api/system`'s `astap.star_db_found` directly, so it fires on a
  brand-new install with **no targets at all**, which the proposed
  frame-reason roll-up could not;
- the third copy of the ⭐ Adaptive Auto spec (slices (a)/(b) shipped v0.159.0,
  v0.169.0, v0.369.0, v0.369.3; only the spec's own *"optional later"* (c) is
  unbuilt).

**Sized and deliberately NOT picked up, with the reason, so the next run need not
re-derive it.** *Slice (c) of the sibling plate-solve hint* — a second solve pass
retrying first-round failures with the sibling centre at
`SIBLING_HINT_RADIUS_DEG`. Its premise is that a tighter radius turns a timeout
into a solve, and the **2026-07-24 measurement already in this backlog** (under
the relaxed-ASTAP-parameters entry) says the opposite: a failed search costs
~4 s at the 30° default and 0.2 s at 5°, so radius is a *speed* lever, not a
detection one, and a Seestar sub already carries a header hint. Building it
would re-litigate a stand-down that carries numbers. It is a wall-clock
optimisation at best, and should be filed as one if anyone wants it.

**Backlog state, honestly.** "Bugs (fix these first)" holds no open, actionable,
un-gated bug: what remains is gated on data no agent has (real elongated-target
frames, a legacy library shape, a cloudy night's subs) or is a recorded
stand-down with measurements. The Ideas sections are in the same state — of the
top-level entries that still *look* open in the two highest-priority sections,
every one checked this run was either shipped, measured-and-declined, or
explicitly blocked. That is the backlog working as intended, not a gap; the
right response is a dogfood pass and a small number of deep tasks, which is what
this run did.

---

## 2026-09-06 — Builder run (branch `claude/sweet-babbage-d5819j`): a clean dogfood, and the one detail op with no proxy term turns out not to need one

**The run.** Baseline green before any change (**4,991 passed / 2 skipped**, full
suite headless, 18:31). Shipped **v0.374.0** (*Save as defaults* stores the delta,
closing shapes (b) and (c) of the v0.372.0 entry) and **v0.374.1** (the note's own
sentence, scoped). Both write-ups are in [`SHIPPED.md`](SHIPPED.md).

**Dogfood pass — CLEAN (`scripts/agent-dogfood.sh` at v0.374.0: real app, bundled
M42 sample ingested + stacked + auto-edited, Playwright at 1440 px and 420 px).**
Probe: *nothing overflowing, no console errors.* Tallest page on a phone is still
the Target page at **3,040 px** (the sixth measurement in this series; 3,014 px at
v0.338.1, 14,584 px before the IA slices), with `/life-list` a close second at
3,008 px — so the standing "measure before opening an IA slice" advice in
AGENTS.md §1 still says **don't**. Read the Dashboard, Target and Editor
screenshots rather than only the numbers: the Target page's one `NoticeBoard`, the
hero, the frames table and the object-info card all render as designed, and the
editor's seven-op Auto pipeline, its measured-cues note and its export panel are
all coherent. Nothing filed.

**MEASURED NON-FINDING — `detail.denoise`'s *wavelet* path has no `proxy_scale`
term, and that is correct. Recorded so nobody "fixes" it.** It is the one detail
op with no proxy scaling: sharpen shrinks its radius, chroma smoothing its kernel,
deconvolution its PSF, and even the *bilateral* branch of this same op scales
`sigma_spatial` — while the wavelet branch (the default, and the one Auto emits)
denoises whatever grid it is handed. Since the proxy is decimated by **striding**
(`seestack/edit/proxy.py`), per-pixel noise is preserved, so the obvious worry is
that the preview removes grain at proxy scale while the export removes it at
full-res scale — the preview↔export mismatch the editor works hard to avoid, and
in the *overstating* direction the sharpen floor's own comment calls the worse one.

**It doesn't happen.** Probe: 1200×1600 synthetic S30-ish stack (sky 0.10, σ 0.004,
a broad faint object, a light-pollution ramp, 400 stars kept out of a 480 px
star-free measurement corner), grain read as the MAD of adjacent-pixel differences
in that corner, comparing the *export strided down* against the *preview* at the
same physical patch. Share of grain removed, export vs preview:

| strength | full res | step 2 | step 4 | step 6 | step 8 |
|---|---|---|---|---|---|
| 0.3 | 29 % | 28 / 28 % | 27 / 26 % | 27 / 26 % | 28 / 24 % |
| 0.6 | 58 % | 55 / 55 % | 53 / 52 % | 53 / 50 % | 53 / 50 % |
| 1.0 | 100 % | 85 / 93 % | 78 / 83 % | 77 / 81 % | 78 / 79 % |

Across the whole range Auto can reach (`_AUTO_DENOISE_MAX` = 0.6) the two agree to
within **3 percentage points at every stride**, and what disagreement there is has
the preview removing *less*, not more. **Why:** BayesShrink sets its threshold from
the noise it actually sees in each subband, and striding preserves per-pixel noise
— so unlike a fixed-radius kernel, the op re-derives the right threshold on
whichever grid it is given. A `proxy_scale` term would be a correction for an error
that isn't there. (At strength 1.0 the ordering flips and the preview removes a few
points *more*, but Auto is capped below that and the absolute residuals are ~0.0005
of a 0.10 sky.) Probe kept in the session scratchpad (`denoise_probe2.py`); it is a
measurement, not a fixture worth adding to the suite.

---

## 2026-09-06 — Builder run (branch `claude/sweet-babbage-owcg4d`): three closed ⭐ leads were still starred, and what the real-stretch fixture measured

**The run.** Baseline green before any change (full suite headless, plus 234
frontend files / 3,237 vitest tests). Shipped **v0.372.0** (the Stack form now
names the saved options a target is holding away from the global defaults) and
**v0.372.1** (the shared display-space test fixture). Two curation passes below.

**Curation: three ⭐ QA LEADs at the top of the highest-priority Ideas section
were fully closed and still starred.** §11 tells every triage pass to take a ⭐
entry *first*, so a closed ⭐ is not merely clutter — it is the entry a run is
told to pick before anything else. All three said, in their own later text, that
every candidate they listed had been measured and fixed:

- the Auto preset picker's depth-dependent cues (both halves fixed, v0.318.1 +
  v0.318.3);
- "sweep every judgement made against a best-so-far" (all four shapes swept, one
  live instance, v0.319.1, no second site);
- "sweep every statistic that normalises against its own non-empty subset"
  (swept three times; v0.313.1, v0.318.1, v0.319.1).

Each is now `✅ CLOSED`, kept for its **method** — the generative test each one
carries is still the right thing to apply to new code — with an explicit "do not
re-run this sweep". Nothing was deleted.

**Curation: the year-recap "slice (b) is still open" sentence had outlived its
slice by weeks.** `yearrecap.draw_year_poster`, `yearrecap.year_caption`,
`GET /api/recap/year/{year}.jpg`, `api.yearPosterUrl` and
`components/YearShareCard.tsx` all exist on `main` with their own tests — this
run sized slice (b) as open work and found it done. Both sentences that claimed
otherwise are struck. **The general lesson, and the reason this is worth a
block:** a "slice (b) is still open" line written *inside* a Shipped entry is
invisible to every status grep, because the entry's own header says ✅. When you
leave a slice open, leave it as its own entry.

**A third stale claim of the same shape, and the systemic point.** The framing
entry's *"Follow-up still open: (b′) prefer a plate-solved frame's actual field
size"* is also done — and it turned out to matter more than that sentence knew:
`seestack/framing.py` shipped with the **S50's** 77′ × 44′ while the owner has an
**S30** (~128′ × 72′), so `framing.FrameField` / `frame_field_from_solve` /
`webapp/frame_field.py` (v0.352.0) derive the field from the owner's own solved
frames' `pixscale_arcsec`. Struck.

**So: `docs/IMPROVEMENTS.md` carries ~44 sentences of the form "still open" /
"remainder still open" / "left open", and three of the four this run happened to
read were already shipped.** Each is invisible to a status grep because it lives
*inside* an entry whose header says ✅, which is precisely the shape that
survives triage and gets re-picked. This run verified and struck the three it
touched; **a full verification pass over the other ~40 is a good Scout task** and
is deliberately not attempted here — spot-checking each one means reading the
code it names, and doing forty of those is a run on its own. The generalisable
rule is the one above: **when you leave a slice open, leave it as its own
entry**, never as a sentence inside a Shipped one.

**Measured while migrating the display-space tests (v0.372.1) — recorded so
nobody re-investigates.**

- **`levels.suggest_levels_points` returns black = 0.0 on any genuinely stretched
  picture, and that is correct.** Its `lo_pct=1.0` percentile lands *inside*
  `autostretch`'s own zero spike (measured: 1.08 % of samples at exactly zero,
  p0.1 = p0.5 = p1.0 = 0.0, p2.0 = 0.022, sky at 0.177). So the black half of the
  "From your image" auto-levels is a no-op on the pictures the owner actually
  has — the honest answer, since the shadows are already at black, but **not**
  what the module's synthetic `_scene()` fixtures show, which return 0.05–0.13.
  Not filed as a bug: raising the black point to the sky's lower tail would crush
  real background, and the white point (0.892) and gamma (1.079) halves still do
  real work. Pinned by
  `test_the_black_point_is_zero_on_a_genuinely_stretched_picture` so the fact is
  documented rather than discovered again.
- **`histogram.measure_sky_cast` — cleared, not migrated.** On the same real
  fixture it reads R/G/B 0.15305/0.15318/0.15259, deviation 0.00035, verdict
  neutral. Its sky population is "finite pixels at or below the luminance
  median", which a 1 % zero spike cannot move; there is nothing for the shared
  fixture to add.

**Why the false-positive guard on the v0.372.0 comparison is the interesting
part.** The obvious implementation — compare a target's saved blob against
`settings.default_stack_options` — fired on **every** target that had ever
pressed Save, because `get_stack_defaults` seeds a never-configured form with
`auto_reject: True` while the descriptor default is `False`. The test that caught
it saves the form *verbatim as the server handed it over* and asserts the note
stays empty; it is worth copying whenever a new surface says "you are overriding
something", because the seed and the stored default are not the same thing.

---

## 2026-09-06 — Builder run (branch `claude/sweet-babbage-f4us4a`): the backlog is genuinely drained, and probing the newest code is what paid

**The run.** Baseline green before any change (**4949 passed / 2 skipped**, full
suite headless). Two tasks shipped — **v0.371.0** (the one-click defect repair)
and **v0.371.1** (the amp-glow false-positive fix). One verified lead filed.

**Triage record: the backlog really is drained, and this is what that looks
like.** Read "Bugs (fix these first)" end to end and every open-looking entry in
the Ideas sections. Of the ~30 entries that survive a status grep, essentially
all are one of three things: **gated** on something no agent has (real
elongated-target data, a cloudy night's subs, a real solved frame with known
field rotation), **stood down with numbers already recorded** (the ASTAP ladder
budget, the "3-frame default stack" entry, the blob-count caption, the drizzle
rejection skip), or **already shipped and merely unstruck**. Four were checked
against the code and found done: the `NOISERAT` stamp is
`stack.py::_cached_noise_ratio` / `stamped_noise_measurement`; the dark↔light
exposure-mismatch item is closed on all three slices; the "sentence that names a
number" sweep is closed; the Auto-preset depth-invariance lead is closed on both
halves. **Do not re-pick any of those** — and do not manufacture work from that
section either, which is what AGENTS.md §2 is warning about.

**What did pay, and the method is the transferable part: probe the newest code
empirically instead of re-reading the mature code.** `seestack/calibrate/`
defects had shipped four days earlier across v0.367–v0.371 and had ~20 tests.
Rather than reading it adversarially (the ~18 clean stacking re-audits say what
that yields), I built a master dark **the way the camera builds one** — mean of
20 frames, each Poisson in the dark current plus read noise — and asked it a
question the existing fixture cannot express, because that fixture adds read
noise of *one fixed sigma everywhere*. The very first probe reproduced a real
image-quality bug (133 healthy photosites flagged as broken at a realistic amp
glow, 1,564 at an extreme one) that had survived two prior fixes to the same
file. **That is the third bug in a row this method has found in this area**
(v0.369.3, v0.369.4, now v0.371.1). The generalisable rule: **when auditing a
measurement, check whether the test fixture can express the case that would break
it.** A fixture with stationary noise cannot catch a bug about non-stationary
noise, however many tests are written against it.

**One design note worth carrying.** The fix's percentile was pinned by an
*existing* test, not by tuning: P90 read best on the glow but silently defeated
the `MAX_DEFECT_FRACTION` refusal (a master with a tenth of the sensor spiked
stopped being refused and started being repaired). P80 keeps the guard and still
clears every false positive at credible glow. When a threshold has two
consumers, tune it against the one that is already tested.

---

## 2026-09-06 — Builder run (branch `claude/sweet-babbage-ks0ild`): big-picture dogfood pass **CLEAN**, plus the measured cost of the new defect census

**The run.** Baseline green before any change (**4930 passed / 2 skipped**, full
suite headless), one task shipped (**v0.370.0**, the master sensor-defect census
on the Calibration page), suite green after (**4949 passed / 2 skipped**; vitest
3221 passed, `tsc` and `vite build` clean). Then a §2 big-picture pass on a real
running app rather than a re-read of route files.

**Dogfood pass (`scripts/agent-dogfood.sh`, full run: sample loaded, stacked,
Playwright probes at 1440 px and 420 px) — nothing found.** Verbatim: *"nothing
overflowing, no console errors"*. Tallest pages, full-page scroll height:

| | phone (420 px) | desktop (1440 px) |
|---|---|---|
| `/targets/<T>` | **3,040 px** | 2,037 px |
| `/life-list` | 3,008 px | 1,453 px |
| `/targets/<T>/edit/1` | 2,815 px | 1,841 px |
| `/` (Dashboard) | 1,837 px | — |
| `/targets/<T>/stack` | 1,748 px | — |

**So the standing IA priority still says "do not open a speculative slice."** The
Target page is the tallest page, at 3,040 px on a phone against the **3,014 px**
the v0.338.1 probe recorded (`IMPROVEMENTS.md`, search **"DOGFOOD BASELINE"**) —
26 px over ~30 versions, i.e. flat, and still far from the 14,584 px the worst
page measured before the 08-13→16 slices. Screenshots were read (Target,
Dashboard on a phone, Calibration): nothing stacked badly, no banner wall, no
clipped control. **This is the third measurement in a row saying the same thing.**

**One honest non-finding, recorded so it isn't re-filed as a bug.** On the
dogfood install the Dashboard's "Your first image" checklist reads *5 of 6 done*
with step 2 (*"Set up plate solving (ASTAP)"*) unticked while steps 3–6 are
struck through — a checklist that presents an order but can complete later steps
first. It is **not a live defect**: it happens only because the scratch container
has no ASTAP while the bundled sample ships pre-solved. The Docker image bundles
ASTAP, so on the owner's install step 2 is done before step 3 can be. Do not
"fix" the ordering from this screenshot.

**Measured: what a defect census costs at the owner's real frame size** (the
number the v0.370.0 endpoint's caching decision rests on, recorded so nobody
re-measures or re-litigates it). `webapp.calibration.master_defect_census` on a
saved master at the **S30 raw mosaic size, 1080×1920 (2.07 Mpx)** with 400
planted defects: **0.87–1.01 s** per master (three runs; the cost is the four
per-phase 5×5 median filters, not the FITS read). At 480×320 it is instant.

* So a library with, say, six dark/bias masters pays ~5 s **once**, on the first
  Calibration page load after a restart, and nothing after that — the answer is
  cached on the app keyed by each file's own identity (`path`, `mtime_ns`,
  `size`) with no TTL, because a master FITS is immutable once written.
* That cost is also exactly why it is **its own query** on the page, like
  `calibrationCoverage`: the master table renders immediately and the defect
  lines arrive a moment later, rather than the list waiting on the read.
* **Considered and deliberately not built:** stamping the census into the
  registry at `register_master` time (free there — the array is already in
  memory). It would be a *second* source for a number the file itself answers,
  and it would say nothing at all about the masters the owner already has, which
  are the ones that matter on a live install. Revisit only if a real library is
  ever slow enough to notice.

**End-to-end check of the shipped feature on the running app** (not just in
tests): eight synthetic 480×320 darks with 37 planted hot photosites were dropped
into the dogfood `incoming/`, discovered by `GET /api/calibration/incoming`,
built through `POST /api/calibration/masters`, and `GET /api/calibration/defects`
answered **exactly 37** with the note *"37 hot or dead pixels (0.024%)"* — which
rendered as the third dimmed sub-line under the master's name, in the same idiom
as `header_note` and the coverage line.

---

## 2026-09-06 — Builder run (branch `claude/sweet-babbage-f1wozl`): the "can a plain run carry a `preview_crop_json`?" sub-question of the full-res-render consolidation lead is a **non-finding**

The open lead *"there are now **two** answers to 'render this run's picture at size N'"*
(`docs/IMPROVEMENTS.md` → Infra / maintainability, Builder 2026-08-30) closes with a
concrete worry worth more than the refactor around it:

> a plain run should never carry a `preview_crop_json` (only the auto-edit writes one, and
> it sets `preview_display_space` too), but **nothing asserts that**, and if it can happen
> the full-res download is showing a differently-*framed* picture the same way it was
> showing a differently-rotated one.

**Checked in the code this run; the invariant holds by construction at both writer sites,
so there is no second v0.311.1 hiding here.** `preview_crop_json` is written in exactly two
places, and both set the display-space marker in the same block:

* `webapp/pipeline._auto_edit_process_run` — `set_stack_preview_crop(...)` at
  `pipeline.py:3199` is followed by `set_run_preview_display_space(run_id)` at `:3208`,
  with no early return between them.
* the North-up "Adjust → Save" endpoint in `webapp/routers/stack.py` — it **refuses a
  non-display-space run up front** (`if not _preview_is_display_space(run.options_json):`
  → 400 *"This run's picture isn't a processed one — save a stretch instead"*, with the
  comment already explaining that doing it would be "a different feature … reached by a
  path nothing offers"), and only then writes `set_stack_preview_crop` +
  `set_run_preview_display_space` together.

The only other mutation is `set_stack_preview_crop(run_id, None)` — a clear, which cannot
create the shape.

**So the crop case is *not* the rotation case.** The rotation went missing from one of the
two renderers because it was written in one and forgotten in the other; the crop is fenced
off at the point where it could be created. **Do not spend a run re-tracing this.** The
rest of the lead — consolidating `stack._native_picture_source` and
`download_full_res_png` onto one `run_picture_png(...)` — is still open on its own
maintainability merits, but it is a pure refactor with no known defect behind it, and
AGENTS.md §10 ("refactor only in service of a concrete improvement") applies: it was
deliberately **not** picked up this run. If a future run does take it, this note is the
answer to the crop question it will otherwise ask first.

---

## SCOUT QA SWEEP — the newest post-audit code (v0.354→v0.366) read adversarially; CLEAN; one new beginner feature + one hardening note filed (Scout 2026-09-06, branch `claude/admiring-brahmagupta-mmvfsy`)

Recorded so the next Scout doesn't re-read these modules. The ~20 recorded stacking-engine audits (see the
blocks below and the ones cut to this file on 2026-09-05) covered the engine up to ~v0.353–0.355. This run
deliberately targeted the code that **post-dates** all of them — the v0.354–v0.366 changes — since that is
the only stacking/calibration surface no prior audit has seen. Baseline before the sweep: the stacking +
calibrate subset is green (**1578 passed / 2 skipped / 3289 deselected**, `-k "stack or accumul or align or
mosaic or drizzle or calibrat or reject or weight"`, on a fresh `source scripts/agent-setup.sh`).

**Traced CLEAN (read end to end for NaN/coverage semantics, rejection/weighting math, preview↔export parity,
and — for the new calibration surface — the `incoming/` read-only guarantee):**
- `seestack/stack/output.py` **`pack_unit`** (v0.354.1/.2) — `np.rint(arr * info.max)` at all six export
  sites; the linear TIFF's own reversibility description is now honest to ±½ DN; `rint(1.0*MAX)==MAX` so no
  overflow; callers all clip (or `nan_to_num`) first. `_to_uint16_linear` routes through it. Correct.
- `seestack/stack/stacker.py` **rejection-reach math** (v0.365.0) — `kappa_min_frames`,
  `lone_outlier_min_depth`, `auto_reject_depth` (grid-snap + `cluster_pointings` + the "≥2 substantial
  panels or None" gate, returning the thinnest panel), `_resolve_auto_reject`'s `n = min(n, depth)` clamp,
  and the `REJDEPTH/REJNEED/REJREACH` stamping in `_build_output_header_meta`. `peak_depth = min(n_used,
  int(nanmax(cov)))` — `int()` truncates toward zero, the conservative direction (understates depth → errs
  toward "blind", never toward "clean"), matching the docstring's stated caution. Consistent with
  `stackhealth`'s `rejection_blind` via the shared `kappa_min_frames`.
- `seestack/stack/accumulator.py` **`MinMaxRejectAccumulator`** — re-verified the k-set ±inf-identity
  insertion sort, the `count≥2k+1 / 3≤count<2k+1 / 1–2 / 0` bands (no inf−inf on the full band because
  ≥2k+1 real contributions fill both k-sets), tie-safety on a shared saturated core, and `rejection_counts`
  matching the drop schedule. Correct.
- `seestack/io/fits_loader.py` **`frame_kind_from_header`** (v0.356.0) — exact-table (not substring) match
  after punctuation-normalisation; one-sided (unknown/missing → `None`, never inferred "light"). The whole
  safety property holds. `_coord_to_deg` sexagesimal sign handling also spot-checked, correct.
- `seestack/calibrate/discover.py` + `webapp/calibration.py` `cached_incoming_folders` /
  `incoming_calibration_advice` + `webapp/routers/calibration.py` (v0.366.0/.1) — **read-only w.r.t.
  `incoming/`** (only `os.scandir` + `load_header`; nothing opens for write/rename/unlink; AGENTS.md §10
  honoured). Confident-offer logic is strict and one-sided (every sampled frame must declare a recognised
  kind mapping to one master slot; a light or a "didn't say" rules the folder out at index 0). Build is
  re-discovered server-side by id; no client path. Correct.

**One hardening note filed to IMPROVEMENTS.md → Bugs** (a landmine to know about, **not** a verified live bug,
so recorded as a note rather than manufactured as a bug per AGENTS.md §2): the one-click discover→build path
classifies a folder by **sampling 4 headers** (`discover.SAMPLE_HEADERS`) but `masters.build_master` then
combines **every** shape-matching FITS in the folder without filtering to the requested kind — so a genuinely
*mixed* folder (its 4 evenly-spaced samples all darks, but other files lights or a second exposure) would
build a contaminated master. Mitigated already: `build_master` tallies each combined frame's own `IMAGETYP`
into `header_kinds` and surfaces it as the v0.356.0 `header_kind_note`, so the user is *told* what went in.
Low severity (needs an unusual folder), low confidence (traced, not reproduced). Details + the "if ever built"
direction in the note.

**Also this run:** filed one genuinely-new beginner feature ("Was last night off for you?" — a whole-history
star-size baseline; grep-confirmed absent, `sky_quality.py` has only a *cloud* baseline). Confirmed by
grepping that essentially every other beginner-feature idea I could generate is **already built** (deepening
reel, montage, wallpaper crop, reveal zoom, year recap, A/B compare, life list, object info, moon-aware
tonight + multi-night `next_observing_windows`, `ShowRemovedToggle` for the rejection map, `stack_health`'s
prioritised next-steps) — a direct confirmation of §4's "idea supply is not the constraint". So no more ideas
were piled on.

---

## DOGFOOD PASS — clean, and the honest outcome was to stop rather than find something (Builder 2026-09-06, branch `claude/sweet-babbage-t53xni`)

`scripts/agent-dogfood.sh` on a scratch data root, at **v0.365.0**: booted the app, loaded and stacked the
bundled sample, probed 22 routes at 1440 px and 420 px, and read the Target, editor and Dashboard shots as the
§1 owner. **Nothing overflowing, no console errors, and no defect worth a fix.** Recorded because a clean pass
is a result — the alternative is the next run re-running it and reaching the same place.

**Page heights (phone, tallest first): Target 3,040 px · life list 3,008 px · editor 2,815 px · Dashboard
1,837 px · stack form 1,748 px.** Every one identical **to the pixel** to the v0.362.0 measurement, across
three more shipped features since (v0.363.0 `FirstLookStrip`, v0.364.0 `RejectionBreakdownCard`, v0.365.0's
header cards) — the standing IA rule working as intended: each of those went **inside** an existing group
rather than appending a banner. Desktop, for completeness: Target 2,037 px (2,010 at v0.351.0), editor
1,841 px and life list 1,453 px, both unchanged. So the worst page reads **14,584 px before the 08-13→16
slices → 3,014 at v0.338.1 → 3,014 at v0.351.0 → 3,040 at v0.362.0 → 3,040 here**: another measurement
telling a run not to open a speculative IA slice (AGENTS.md §1), which is what it is recorded for.

**Two things looked at closely and deliberately not filed**, so they are not re-found:
* The Target page's two columns end at different heights (frames table ~1,290 px, right rail ~1,640 px on
  desktop), leaving blank space on the left. That is what an unequal two-column grid does; equalising it would
  mean moving a card for cosmetic reasons, on the page the owner already calls busy.
* The frames table's `Sky` and `Transp.` columns print raw instrument numbers (1000, 124018) with no units.
  Already answered in place by the *"What do these numbers mean? →"* link directly above the table — a second
  explanation would be the "third place asking the same question" mistake.

**Method note worth carrying:** the one real finding this run produced came from **grepping for an existing
surface before adding a new one**, not from the probe. A prototyped second History line explaining a blind
rejection pass was written and deleted once `StackHealthCard` turned out to render that exact explanation, with
a better cure, further down the same page. The probe confirms the app is not visibly broken; the overlap grep
is what stops it getting noisier.

## DOGFOOD PASS — it earned its keep this run: one real copy/tick defect, caught by looking rather than reading (Builder 2026-09-05, branch `claude/sweet-babbage-pywfmk`)

`scripts/agent-dogfood.sh` on a scratch data root, at v0.362.0: booted the app, loaded and stacked the
bundled sample, probed 22 routes at 1440 px and 420 px. **Nothing overflowing, no console errors** — same as
the two passes before it.

**The finding, and why no amount of re-reading would have produced it.** The Dashboard screenshot showed the
newly-extended "Your first image" checklist reading *"Finish it in the editor ✓ / Save your edited version ○"*
on a picture the app had **already finished**: the sample had been through "Process this target", which saves
the recipe *and* bakes it into the run's stored preview (`preview_display_space`) without ever exporting. The
step's hint — *"until you do, the thumbnail everyone sees is still the un-edited stack"* — was therefore false
about the picture on the same screen, and the card disagreed with `stack._unexported_edit`, which reads that
marker and correctly stays quiet on such a run. Fixed the same run as **v0.362.1** (`n_finished_pictures` is
the union of the export marker and the display-space preview). The general lesson, which is the reason this is
recorded: a new counter is easy to define from the *marker you found first*, and the app's own screens are
where you discover the second route to the same state.

**Page heights (phone, tallest first): Target 3,040 px · life list 3,008 px · editor 2,815 px · Dashboard
1,837 px · stack form 1,748 px.** The **fourth** measurement telling a run not to open a speculative IA slice
(AGENTS.md §1): the worst page was 14,584 px before the 08-13→16 slices, 3,014 px at v0.338.1, 3,040 px at
v0.361.0 and 3,040 px now. The Dashboard's +52 px over the last pass is this run's own two checklist rows, on
a card that **does not render on an established install at all** (`firstImageHasPicture`), so it costs the
owner's Dashboard nothing.

---

## DOGFOOD PASS — clean, and the page-height baseline re-measured at v0.361.0 (Builder 2026-09-05, branch `claude/sweet-babbage-e7p93y`)

`scripts/agent-dogfood.sh` on a scratch data root: booted the app, loaded and stacked the bundled sample, then
probed 22 routes at 1440 px and 420 px. **Nothing overflowing, no console errors.** Recorded so the next run
does not re-run it looking for the same answer.

**Page heights (phone, tallest first): Target 3,040 px · life list 3,008 px · editor 2,815 px · Dashboard
1,785 px.** The standing IA rule (AGENTS.md §1) says to measure before opening another slice, and this is the
**third** measurement to say don't: the worst page was 14,584 px before the 08-13→16 slices, **3,014 px** at
v0.338.1, and 3,040 px now — 26 px over roughly 23 versions, which is the cards those versions added landing
inside the existing grouping rather than stacking on top of it. So the rule is working and there is nothing
here to slice.

**Two things that look like findings and are not, checked so they are not re-filed.**

1. The Dashboard's *"Your first image — 3 of 4 done"* checklist leaves **step 2 (set up plate solving)** unticked
   while steps 3 and 4 are struck through, under a banner saying solving is *"required before you can stack
   anything"* — next to a finished stack. That is honest and container-specific: the dogfood container has no
   ASTAP binary, and the bundled sample ships pre-solved, so the sample legitimately stacked without the
   solver being set up. The owner's Docker image bundles ASTAP, so this state is not reachable there.
2. The sample's stack renders as colour speckle on a dark field. That is the **sample data** — six synthetic
   subs — not a stacking or editor defect; the editor's own measured line under the picture agrees
   (*"stars ≈ 2.1 px FWHM · background noise σ 0.001"*).

## DOGFOOD + COLOUR-CALIBRATION AUDIT — both clean, two leads measured out (Builder 2026-09-05, branch `claude/sweet-babbage-9bfqke`)

Recorded so no future run re-derives any of this. Nothing below is open work; the one real finding of the
run shipped as v0.355.1 and its write-up is in [`SHIPPED.md`](SHIPPED.md).

**1. Dogfood pass (`scripts/agent-dogfood.sh`, full: boot + sample + stack + Playwright probe) — clean.**
`nothing overflowing, no console errors`. Full-page scroll heights, tallest first:
`[phone] /targets/<T>` **3,040 px**, `[phone] /life-list` 3,008, `[phone] .../edit/1` 2,815,
`[desktop] /targets/<T>` 2,037, `[phone] /` 1,785. The tallest page is still the Target page and it has
moved **+26 px** since the v0.338.1 measurement (3,014 px) — the third consecutive measurement saying
**do not open a speculative IA slice** (AGENTS.md §1's standing rule; the two earlier ones are under
"DOGFOOD BASELINE" in `IMPROVEMENTS.md`). The Target page carries one `NoticeBoard` ("1 more note"), the
Dashboard's seven analysis cards are behind `InsightTabs`, and the editor's pipeline/export column reads
cleanly at 1440 px. Screenshots were scratch-only, never the repo.

Two cosmetic things seen and deliberately **not** filed, because neither reaches the owner (ASTAP is bundled
in the Docker image, so the install this run booted is not the owner's): the Dashboard's "Plate-solving isn't
set up yet" banner says solving *"is required before you can stack anything"* on an install that has already
stacked pre-solved sample frames; and the "Your first image" checklist reads *"Next: Plate solving"* with
steps 3 and 4 already ticked. Both are honest for a real Seestar owner, whose frames are not pre-solved.

**2. `seestack/post/color_cal.py` adversarial audit — no bug. Two candidate defects were reproduced at the
per-star level and then measured out at the level that matters.** This module is on the priority-1/4 path
(it is the white balance behind every Auto picture) and is not in the ~18 recorded stacking-engine audits.

- **`_aperture_photometry` zero-fills uncovered (NaN) pixels, so a star beside a mosaic coverage edge has its
  background under-subtracted — real, reproduced, and irrelevant to the answer.** `ch = np.where(isfinite,
  rgb, 0.0)` means an annulus (`r_in=r+2`, `r_out=r+5`) that overlaps uncovered canvas measures a background
  that is too low, and because a raw OSC sky is green-heavy the bias is *per-channel*, i.e. it skews the
  star's **colour**. Reproduced on a single star 5 px from a coverage edge: flux +4.5 %, **R/G 1.0002 →
  0.9793 (−2.1 %), B/G 1.0003 → 0.9837 (−1.7 %)**. **But `_solve_gray_star` takes the median of hundreds of
  stars.** On a synthetic 2×2 dithered mosaic union canvas (1240², 2.6 % uncovered, ragged border + interior
  gap, ~700 planted stars) only **1.4 % of kept stars** are contaminated, and dropping them moves the solved
  scale by the *same magnitude and with no consistent sign* as dropping the same number of **random** stars —
  measured over five seeds: contaminated-drop ΔR `+0.87 / +1.85 / 0.00 / 0.00 / −0.51 %` against a
  random-drop control of `|ΔR|` `0.86 / 0.73 / 0.09 / 0.35 / 0.52 %`. So the per-star bias is real and the
  net effect on the white balance is median jitter, not a systematic shift. **Do not "fix" this**: filtering
  edge-contaminated stars would change the answer by less than the noise, and could push a small or
  star-poor canvas below `min_stars` into the background-neutral fallback — a real regression bought for
  nothing. Worth revisiting **only** if the solver ever stops being a median (a weighted or mean-based fit
  would inherit the bias directly).
- **The annulus offsets `radius + 2` / `radius + 5` are hard-coded absolute pixels and are *not* scaled for
  the editor's decimated proxy — the A2 class — but scaling them does not improve preview↔export parity.**
  `edit/ops/tone._color_calibrate` scales `detect_fwhm_px` and `aperture_radius_px` by `ctx.scaled_px` (the
  A2-era fix) and the annulus offsets ride along unscaled, so at proxy scale 8 the preview samples its
  background in a ring **28–52 full-res px** from the star where the export uses **6–9 px**. Measured on a
  1200² scene with structured nebulosity and 400 colour-spread stars, comparing the proxy's solved scale
  against the full-res one: today's absolute offsets give ΔR/ΔB of `−1.63/+1.50 %` (×2), `−0.15/+5.47 %`
  (×4), `+0.26/+1.70 %` (×8); annulus offsets made **proportional** to the aperture (matching the full-res
  4→6,9 ratios) give `+0.18/−0.81 %`, `+0.82/+4.90 %`, `+5.98/−1.33 %` — better at ×2, no better at ×4,
  **markedly worse at ×8**, where a proportional annulus is only ~1.5 px wide and its background estimate
  goes noisy. The divergence is dominated by the **star population itself** changing with decimation (332 →
  323 → 224 → 66 detections), which is an inherent proxy limit, not a parameter bug. So this is **not** a
  live A2 instance and the obvious fix is not an improvement; leave the offsets alone.

**3. The "Finish what you started" idea was closed as already-built, not implemented.** Its capability is
`GET /api/plan/best-tonight` (`rank_targets_now`) + `PointHereTonightCard`; both halves of its 2026-08-29
reshape had already been declined with measurements. Closing it surfaced the duplication that shipped as
v0.355.1. Entry cut verbatim to `SHIPPED.md`.

---

## QA SWEEP — stacking engine + calibration + QC (Scout 2026-09-05, mostly clean)

Adversarial read of the stack → result path on `origin/main` at v0.353.3. Recorded here so the next Scout
doesn't re-audit the same modules; the rotation should move to the webapp routers / watcher / ingest next.

**Traced clean (no verified defect):**
- `seestack/stack/accumulator.py` — `WeightedSumAccumulator` (weight vs frame-count coverage, any-channel
  `covered`), `MinMaxRejectAccumulator` (k-set ±inf identities, the count≥2k+1 / 3≤count<2k+1 / <3 bands,
  `rejection_counts`), `WelfordAccumulator` (n<2 → NaN variance widen). NaN/coverage semantics hold throughout.
- `seestack/stack/weighting.py` — geometric-mean of clipped [min_weight,1] factors, per-panel positional
  medians with target-wide fallback, `combine_weights_with_photometric` (1/s² inverse-variance).
- `seestack/stack/photometric.py` — `ref/transparency_score` scale, per-panel references, neutral fallbacks.
- `seestack/stack/pointings.py` — union-find single-linkage clustering (wrap/pole-safe), `pointing_groups`
  soundness gate.
- `seestack/stack/align.py` — windowed reproject inset/pad, subpixel refine NaN-ring propagation
  (`cval=1.0`, `>1e-6`), CPU/GPU parity via the explicit valid mask.
- `seestack/calibrate/apply.py` — pedestal sanitisation, `_effective_dark` exposure-scaling with dark/bias
  no-data masks, the `_bias_applies` (never double-subtract) and Bayer-phase guards, `apply_raw` fresh-array
  contract.
- `seestack/qc/metrics.py` + `qc/grading.py` — green-channel float promotion (no uint16 wrap), modified-z
  grading with per-panel + global caps and the `reconsider` fixed-point.
- `seestack/bg/coverage_leveling.py` — per-level detrend-then-threshold, starved-level rescue, `_sky_mode`.

**Parallel agents:** `seestack/stack/drizzle_path.py` (+ its stacker dispatch) traced **CLEAN** by a dedicated
agent — NaN/coverage, two-pass rejection at low neff, float64 variance floor, memory bounds, WCS geometry all
correct. `seestack/stack/mosaic.py` + `output.py` traced clean on every corruption axis; it surfaced one
low-severity item.

**One item filed** (IMPROVEMENTS.md → Bugs, "Minor / low-priority" batch): the float→uint export path
truncates instead of rounds (`output.py:654` +5 siblings), biasing every exported pixel down ~0.5 LSB and
nicking the linear TIFF's "reversible" claim. Near-cosmetic; a Builder task rather than a one-liner because
`test_linear_tiff_no_clip.py`'s strict `at_full_scale == at_true_max` invariants need relaxing under rounding.
Two non-bugs recorded inline in that entry so they aren't re-investigated (`_write_coverage_fits` 2-D-dtype
nit; `_same_map` `array_equal`-on-NaN, moot on 0-filled maps).

**Also curated:** cut the v0.353.0 + v0.353.1 entries (shipped, still sitting in "Bugs") to SHIPPED.md and
reparented the orphaned Scout QA note; filed one new beginner feature ("Your mosaic, panel by panel").

## DOGFOOD BASELINE — running-app probe at v0.352.1 (Builder 2026-09-05)

`scripts/agent-dogfood.sh` on a scratch data root with the bundled sample loaded
and stacked, Playwright full-page at 1440 px and 420 px plus the overflow probe.
**Nothing overflowing, no console errors.** Tallest pages, full-page scroll
height:

| page | phone (420) | desktop (1440) |
|---|---|---|
| `/targets/<T>` | **3,014 px** | 2,010 px |
| `/life-list` | 3,008 px | 1,453 px |
| `/targets/<T>/edit/1` | 2,815 px | 1,841 px |
| `/` | 1,785 px | — |
| `/targets/<T>/stack` | 1,748 px | — |

**The IA number has now been stable across three measurements and ~14 versions.**
The v0.338.1 probe recorded in `AGENTS.md` §1 put the tallest page — the Target
page — at **3,014 px on a phone**, and this run measures **3,014 px**, exactly.
That is a third independent reading agreeing with the standing advice in that
banner: **do not open a speculative IA slice.** (The +26 px the second run of the
day shows is the v0.352.2 panel-count line this run deliberately added, not
drift.)

**What the pass found**, both filed and shipped rather than left here: the
"coverage vs panel count" lead closed by measurement (the sample derives a
40′ × 26.7′ field from its own `pixscale_arcsec`, so 15 % coverage ↔ 3×3 = 9
panels, which agree — the lead was written against the pre-v0.352.0 S50 count),
and the real bug behind the screenshot, that the panel count had nowhere left to
appear once the measured verdict suppressed the predicted line (v0.352.2). Full
write-ups in `IMPROVEMENTS.md` → "Bugs (fix these first)".

**Worth knowing for the next dogfood run:** the sample's frames *do* carry
`pixscale_arcsec` (5.0 on 480 × 320), so the derived-field path is exercised by
the sample, not only by a real library. A framing/mosaic number read off the
sample is therefore trustworthy — which is why the pre-v0.352.0 2×2 stood out.

---

## Released "In progress" claims and collision diaries (moved 2026-09-04)

*Moved wholesale out of `IMPROVEMENTS.md` → "In progress", which had grown to 420
lines carrying **zero live claims** — every header said "claim released" or "run
finished". A section whose only job is to say what is being worked on right now
cannot do it while buried under a diary of what was worked on last week, and the
diary is worth keeping. Verbatim, newest first as it stood.*

> **Builder 2026-09-03, branch `claude/sweet-babbage-axt93w` — claim released, shipped as v0.328.6.** The
> second slice of the full-size loupe — an additive-field channel for the three `background.*` ops, which the
> v0.328.2 fitted-parameter channel explicitly could not carry. Full write-up on the loupe entry under
> "⭐ Editor — make it excellent".

> **⚠️ PROCESS NOTE + Builder 2026-09-02, branch `claude/zen-mccarthy-olkjpm` — collision TEN, two of three
> tasks duplicated by one other Builder inside the same hour, and the first where the *stand-down decision was
> settled by measurement instead of argument*. Run finished; claims released.**
> The `…-t59xya` Builder's PR **#682** landed **A1** as v0.326.1 and the planner's `_times_grid` overhang as
> v0.325.3 — both of which this run had independently built. **Theirs are on `main` and ship; mine are dropped,
> not re-litigated.** What is new is *how* that was decided, and it is cheap enough to be the standing method:
> **run your own test file against their shipped code in a `git worktree` of `origin/main`.** That took two
> minutes and answered the only question that matters — does mine catch anything theirs doesn't?
> * **A1 — 22 of my 23 tests passed on theirs.** The single failure was a *design* difference, not a defect
>   (on a bright image with no headroom mine returns the identity where theirs still pins the sky and scales
>   the shoulder — theirs keeps doing something useful, and is shipped). Decisive for the one place I thought I
>   was ahead: I had added a **noise-aware lift anchor** (`max(p50, sky + 3σ)`) after measuring the mode still
>   reading **0.1357 for a 0.1738 sky** post-spike-fix. Their code passes every sky-movement test I wrote,
>   which means my 0.1357 came from an **unrealistic fixture** — a star-poor scene whose 99.5th percentile is
>   the sky itself, so `autostretch` normalises against the background and spreads it unnaturally wide. **A
>   fixture that isn't shaped like the owner's data manufactures bugs as readily as it hides them**, which is
>   the same lesson A1 itself taught from the other end. The extra layer was therefore speculative hardening,
>   not a fix, and shipping it would have been churn on the on-by-default path. Dropped.
> * **`_times_grid` — theirs is better.** Near-identical clipping, but their `minutes_above_min_alt` sums a
>   per-sample interval array where mine capped `count × step` at the window length. Theirs is the honest
>   quantity; mine was a bound on a wrong one.
>
> **Two genuinely additive pieces were re-applied on top of theirs, in their names, each verified to fail on
> pre-fix code first** (the test for "is this additive?" is not "did I write it" but "does it catch something"):
> the two **sweeps** in `tests/test_edit_curve.py` — across the five stretch targets Auto and the presets
> actually use, and across four stack depths — which pin the audit's own quantified claims (the two branches
> were wrong in *opposite directions*, so a single-point test can sit on one branch and pass while the other
> rots; **9 of the 9 sweep cases fail on pre-fix code**); and the **XS friendliness item their own run filed**
> as the gap it opened (the ghost curve's unexplained fallback branch), built and tested here rather than left
> for another run. Both fold into their fixture rather than standing up a parallel one.
>
> **The one thing that did not collide is the one worth noting for the rotation:** **A3** (plate-solving
> writing `.wcs`/`.ini` sidecars into `incoming/`) — nobody has touched `seestack/solve/` in 25 commits. It was
> filed "verified by code reading, **not reproduced** — no ASTAP binary", and both overlapping runs went
> to the top of the *editor* queue instead. The audit's R5 finding predicted exactly this: sweeps land where
> the code is easy to read, and the findings that survive are the ones needing an **external process, a
> mosaic-shaped canvas, or a proxy scale** to exhibit. If two Builders are running, the cheapest
> de-confliction available is for the second to take the item whose repro needs a *stub binary or a fixture*
> rather than the one whose repro is a function call.

> **⚠️ PROCESS NOTE + Builder 2026-09-02, branch `claude/zen-mccarthy-46ejou` — collision NINE, and the first
> where an entire run was duplicated: all three tasks, by one other Builder, inside the same hour. Run finished,
> everything stood down bar one additive fix.**
> The other Builder's PR **#678** landed **v0.325.0** carrying *the same three items* this run built: the asinh
> full-res parity bug, the `bootstrap_solve` rescued-sub centre bug, and "Plan my week". Not merely the same
> items — the same *shape*, down to an identically-named test
> (`test_rescued_subs_store_their_own_centre_not_the_references` in both). **Theirs is on `main` and ships;
> mine is dropped, not re-litigated**, and PR #679 was rewritten rather than merged. Their versions are equal
> or better at every point, checked rather than assumed:
> * **asinh parity** — theirs is a strict superset. It anchors `render_stack_png` *as well as*
>   `render_preview_png_full_res`, which closes the History-lightbox site at a non-1024 `size` that mine only
>   *filed* as a follow-on idea. (That idea is therefore **not** filed — it would have been open work that was
>   already done.)
> * **rescued-sub centre** — near-identical, and theirs uses `all_pix2world`, so a SIP/distortion term in the
>   solution is honoured. Mine used `wcs_pix2world`.
> * **Plan my week** — theirs extracts the night walk as a shared `upcoming_dark_windows`, so the week view and
>   `next_observing_windows` *cannot structurally* drift about which night is which; mine re-implemented the
>   anchor and pinned the agreement with a test instead. Theirs is the better answer. Placement differs (their
>   card on the Tonight page vs. my nested `/tonight/week` route) and **that is not worth re-opening** — the
>   card is shipped, works, and the "put a feature inside the grouping, not one more banner" rule they cite is
>   the standing one. Filed as an idea under "Friendliness" only if the Tonight page later measures as
>   overlong; it is not a defect today.
>
> **What this run actually shipped, and why it is not churn:** one genuinely additive finding, on top of their
> work — `plan_week`'s 40-target cap kept the first forty targets **alphabetically**
> (`Library.list_targets` is `ORDER BY name COLLATE NOCASE`), so a big library's week was planned around
> whatever sorts first and the owner's deepest project could be silently dropped. That is "finish what I've
> got" answered with the wrong "got". It now keeps the most-shot targets. See the Shipped entry.
>
> **The process lesson, and it is a new one.** The claim-by-site discipline from collisions six–eight cannot
> help here: **both runs started within minutes of each other, from the same front-of-queue backlog, and each
> claimed only in its own first commit — which the other could not see because neither had pushed yet.** The
> backlog is a blackboard read at the *start* of a run; two runs that start together read the same board. The
> only mitigations that would actually have worked are outside a single run's control: (a) stagger the Builder
> schedule so two never start inside the same few minutes, or (b) **push the claim commit before writing any
> code, and re-`git fetch origin main` again immediately before the *first* implementation edit, not only
> between tasks** — the second is cheap and this run did not do it. Recommended for the next Builder: after
> claiming, fetch once more before the first line of code; if `main` has moved, re-read it before starting.

> **Builder 2026-08-31, branch `claude/wizardly-feynman-0lyyjh` — second claim, by site.** The top open item
> under "Friendliness": **"How's my stack?" tells every deep stack its edges are ragged**. Sites:
> `seestack/stack/stacker.py` (`coverage_thin_fraction` + the `add_stack_run` call),
> `seestack/io/project.py` (schema **20**, additive `coverage_thin_frac`), `seestack/stackhealth.py` (the
> coverage note and the "even coverage" strength), `tests/test_stackhealth.py` and a new
> `tests/test_coverage_thin_fraction.py`. — **claim released, shipped as v0.320.2.**

> **Builder 2026-08-31, branch `claude/wizardly-feynman-0lyyjh` — claim released, shipped as v0.320.1.** The top open item under
> "Image quality": **per-panel reference patches, so sub-pixel refinement reaches a mosaic's *other* panels**
> (filed by the v0.319.9 run as the deeper limitation it deliberately left). Sites I am editing:
> `seestack/stack/stacker.py` (the `options.subpixel_refine` setup block that builds `ref_patch`, and `_pass`/
> `_align_for_stack`'s refine plumbing), `seestack/stack/align.py`
> (`_apply_subpixel_shift_windowed`'s too-small-overlap skip → an honest `stats` flag),
> `seestack/stack/reference.py` (a pure `pick_central_frame` extracted from `pick_reference_frame`, so a panel
> can pick its own reference the same way the target does), and
> `tests/test_subpixel_mosaic_reference.py`. Guard: a single-field stack must be bit-for-bit unchanged —
> `pointing_groups` returns `None` when there is no sound split, which is the single-field case by
> construction.

> **Builder 2026-08-30, branch `claude/compassionate-galileo-7y6nlj` — claim released, shipped as v0.317.0.**
> The top open item under "Autonomy & friendliness": **record how many *nights* went into a stack**, so a
> caption can say "over 4 nights" instead of naming two dates. The entry offered two shapes and named the
> read-time one honest; it is, with one refinement — **night dates cannot be what gets stored**, because a
> night date is already the answer to "for which longitude?". *Hours* are the smallest thing that still
> supports re-bucketing, and a 500-sub night is five of them. Full write-up on the entry under "Autonomy &
> friendliness". Sites touched: `seestack/stack/stacker.py`
> (`_capture_hours`, the `add_stack_run` call), `seestack/io/project.py` (schema **19**, additive
> `capture_hours_json`), `webapp/capture_nights.py` (`capture_night_count`), the four run-shaped API payloads
> (`webapp/schemas.py` `StackRunOut`, `webapp/routers/gallery.py` `GalleryItem`/`BestPicture`,
> `webapp/routers/stats.py` `RecentStack`), `seestack/nameplate.py` (`NameplateFields.nights`),
> `webapp/pipeline.py` (`_nameplate_fields`) and `frontend/src/format.ts` (`captureNightsClause`).

> **Builder 2026-08-30, branch `claude/compassionate-galileo-vsy9vz` (second task) — claim released, shipped
> as v0.314.0.** The follow-on the v0.313.0 work exposed, filed and taken in the same run: the acquisition
> **nameplate** — the caption baked into a shared or printed picture — had *no date at all*, on any picture
> the app has ever exported. It read a `DATE-OBS` card the stacker never wrote (this module's own docstring
> claimed it did). Sites: `seestack/nameplate.py` (`format_acq_range`, `NameplateFields.date_end_iso`),
> `seestack/stack/stacker.py` (`_header_meta` stamps `DATE-OBS`/`DATE-END`), `webapp/pipeline.py`
> (`_nameplate_fields`) and its three call sites. Full write-up on the entry under "Autonomy & friendliness".

> **Builder 2026-08-30, branch `claude/compassionate-galileo-vsy9vz` — claim released, shipped as v0.313.0.**
> The date-honesty class filed under "Autonomy & friendliness" as the generalisation of the v0.311.3 "First
> light" bug, taken at the instance that was a **wrong fact on shared output**: the ready-to-post caption and
> the OS share sheet both asserted a picture was "shot on" / "captured" the run's `timestamp_utc`, i.e. when
> the **stack ran**. The app now records when a stack's subs were taken (schema 18) and every caption reads
> that or says nothing. Full write-up on the entry under "Autonomy & friendliness"; the rest of the sweep
> (provenance lines, the keepsake, the Sky footprint line) is still open there.

> **Builder 2026-08-30, branch `claude/compassionate-galileo-q6uois` — run finished, both claims released.**
> **Shipped one, and stood the other down as a duplicate — this was collision number seven, and it is the one
> the claim-by-site discipline could not have prevented.** Read the process note under "Autonomy &
> friendliness" before picking a North-up follow-on.
> **v0.308.2** (under "Autonomy & friendliness") — the rejection tint over a North-up view. The entry's **alpha
> caution turned out not to apply**, and checking it first — as the entry told the next agent to — is the whole
> reason this was XS and not an afternoon: at the point the endpoint turns anything it holds the **drop-count
> plane**, not the RGBA PNG, so the transparent tint is *rendered at* the rotated size rather than rotated. No
> alpha ever passes through a rotate. The call worth carrying forward is **two turns, not one composed angle** —
> the picture takes the baked turn and then the on-the-fly one, and composing them into a single angle lands on
> a different pixel grid (`np.rot90`'s pixel-centre midpoint vs. `PIL.rotate(expand=True)`'s bounding box).
> A new shared `thumbnail.preview_north_up_remainder_deg` is now the single answer to "what rotation will the
> picture actually receive?", so the preview and the tint cannot drift.
> **Stood down, wholesale:** the run's other claim, **"North up" as a *view* control**, which the
> `…-1bqxek` Builder shipped as **v0.308.0** while this run was building it — **their version is on `main` and
> ships**; mine is dropped rather than re-litigating placement. Theirs puts the control in the **lightbox**,
> which is a better answer than my card-header one (it dodges both filed cautions instead of re-solving them,
> and keeps the header at the three controls v0.293.0 fixed as the phone's limit), and takes the availability
> fact off the **annotations** response rather than the dedicated header-only `…/orientation` endpoint mine
> added — one source of that fact is right, and theirs got there first. **One genuinely additive piece is
> re-applied on top of theirs, in their names:** a `NorthUpViewToggle.test.tsx`, which their commit didn't have
> — the preference's failure modes (a store that throws, a value from a build that spelled it differently) and
> the control's a11y contract were untested.
> The bug queue was checked first and is still genuinely dry: every entry under "Bugs (fix these first)" is
> ✅ shipped, a ⚪ audit non-finding, or explicitly stood down pending owner data (the `astap_timeout_s`
> ladder-budget half stays declined — it needs a real cloudy night's subs no agent has).
> Claiming in the run's **first** commit, **by site**, cost under a minute and was pushed immediately. It did
> not help: see the process note.

> **Builder 2026-08-30, branch `claude/compassionate-galileo-1bqxek` — run finished, both claims released.**
> Shipped three, each its own independently-green commit:
> **v0.307.0** (under "Friendliness") — the **"My life list is 14,584 px tall on a phone"** dogfood finding, and
> the entry's own cheap diagnosis was right: the whole bundled catalog was drawn eagerly into one grid. Grouping
> the captured objects ahead of the rest and putting the to-shoot tail behind one count took it to **3,008 px**
> (**−79 %**; desktop 5,236 → 1,453 px), **re-measured with the same probe** as the entry demanded. It was the
> tallest page in the app by nearly 3× and is now level with the Target page. Nothing removed: picking "Still to
> shoot" — the filter that already existed — still lists every one of them, unshortened, and a test pins that.
> **v0.308.0** (under "Autonomy & friendliness") — **North up as a *view*.** The design call worth knowing is
> *where*: putting the toggle in the **lightbox** rather than on the card answers both of the entry's cautions
> outright instead of re-solving them — a plain `<img>` has no pins, scale bar, compass or rejection tint to fall
> out of register — and it keeps the Target card's header row at three controls, which v0.293.0 already
> established is the phone's limit. The endpoint field is taken from `applied_north_up_deg` rather than
> re-derived, and it reports **null** where the turn would do nothing, so the control never appears where it
> would visibly do nothing.
> **v0.308.1** (under "Features that serve real workflows") — a **plain untruth in shipped copy**, found while
> sizing the full-size-zip idea: the card said "Download all" gives you "the full-size pictures themselves", and
> the archive holds each target's **1024 px preview**. Copy fixed and pointed at the per-picture Full-res PNG.
> **Stood down, with the reasoning recorded on its entry:** the *feature* half of that idea. Its filed "prefer
> the TIFF" is a trap — a stack's TIFF is written **linear**, so it opens looking black, and only an editor
> export writes a display-space one. The real full-size picture is the full-res PNG, which has **no file on
> disk**. The honest shape is a job with staged output (an **L**), not `?full=true` on a streaming endpoint.
> The bug queue was checked first and is still genuinely dry: every entry under "Bugs (fix these first)" is
> ✅ shipped, a ⚪ audit non-finding, or explicitly stood down pending owner data.
> Claiming in the run's **first** commit, **by site**, and pushing it immediately cost under a minute; `main` had
> not moved by merge time and there was no collision.

> **Builder 2026-08-30, branch `claude/compassionate-galileo-aj7ysy` — run finished, all three claims
> released.** Shipped three, each its own independently-green commit:
> **v0.306.2** (under "Autonomy & friendliness") — the one thing the v0.305.0 Adjust-trapdoor fix deliberately
> left alone: on a **processed** run the panel showed a live render of the linear master, i.e. a picture
> *neither* of its two buttons writes. The picture now follows the button — stored bytes until a slider
> actually moves — and the North-up caution the entry raised was **answered rather than dodged**:
> `…/preview` learned an optional `north_up` that turns the *saved bytes* on the way out, so the rotation can
> be previewed on the picture it belongs to. Deliberately not a flag on `stackArtifactUrl`, whose test pins
> that the stored PNG/FITS/TIFF stay WCS-aligned.
> **v0.306.3** (under "Features that serve real workflows") — slice 1 of the sky-coverage follow-up: the
> sentence is on the Dashboard, asserted **against the shared helper itself** rather than a copy of its
> wording, so the two surfaces cannot drift. Building it exposed that "See it on My map →" would have landed
> on the real-sky atlas (the Sky page picks its map from `localStorage`), which is half of what the slice was
> for — so `/sky` took a `?view=` read once through a new pure `initialSkyMode`.
> **v0.306.4** (under "Autonomy & friendliness") — the Scout's `POST /api/scan` confinement, with the grep the
> entry demanded done first (**nothing passes a `root`**: the frontend posts `{}`, and the startup and
> post-upload scans pass none). The design call worth knowing is that the check is **lexical, not
> `resolve()`-based** — a symlinked NAS share inside `incoming/` is normal on this box and the scan already
> follows such links, so a strict resolve check would refuse a real setup to close nothing; a test pins the
> symlink case so nobody "hardens" it into a break.
> **Three follow-ons filed**, all turned up by the work rather than invented: North-up as a *view* control
> anywhere a picture is shown (the server half now exists, and it is read-only — today the only way to see
> your picture that way is to overwrite it); turning the rejection tint with the same helper, with the alpha
> question that has to be checked first; and the finding that a **sub-folder scan root files its frames as
> "Unsorted"**, so `root` reads like a "re-scan one target" shortcut and is not one.
> The bug queue was checked first and is still genuinely dry: every entry under "Bugs (fix these first)" is
> ✅ shipped, a ⚪ audit non-finding, or explicitly stood down pending owner data.
> Claiming in the run's **first** commit, **by site**, and pushing it immediately cost under a minute; `main`
> had not moved by merge time and there was no collision.

> **Builder 2026-08-30, branch `claude/compassionate-galileo-1m28nv` — run finished, all claims released.**
> Shipped three, each its own independently-green commit:
> **v0.305.0** (under "Autonomy & friendliness") — the **History → "Adjust" → Save trapdoor**: on a
> "Process target" run, saving replaced the processed picture with a plain stretch of the linear master,
> silently, and a user who opened the panel only to tick **North up** paid the same price. Both filed halves:
> the warning, and a `keep_processed` save that re-bakes the run's own recipe (rotated, if asked) so the one
> control anybody wants there stops flattening the picture. It also *mends* a drifted run rather than
> declining on it. The plain slider save is untouched, and a test pins that beside the new one.
> **v0.305.1** (same section) — the **"counted less in your stack"** promise. Took the *plumbed* option and
> found the identical sentence on the sibling **focus** card, so both were fixed together. The key call:
> `latest_stack_weighting` reads the newest genuine stack's **FITS provenance** (`WGTMODE`), not
> `options_json` — a run can ask for weighting and have an order-statistic min/max combine ignore it
> (`WGTSKIP`), which for the reader is the same as never asking. A test pins exactly that case.
> **v0.306.0** (under "Features that serve real workflows") — the run's new beginner feature, **"how much of
> the sky have you actually seen?"** under My map. The entry warned it needed an equal-area projection pass;
> it doesn't — `|det(pixel_scale_matrix)|` is the solid angle of one pixel, so the area is exact *before*
> anything is projected, and nothing about how the map is drawn can move it (a test renders the map between
> two reads and asserts it didn't budge).
> **Confirmed pre-existing, not mine:** the pytest quirk the `…-fj2p70` Builder filed reproduced again — a
> hand-picked file list interleaving `tests/webapp/…` and `tests/…` paths lost `tests/webapp/conftest.py`
> and errored every webapp test with `fixture 'client' not found`. Re-running the same files without the
> interleave passed. It still looks exactly like "my change broke everything"; the note is worth keeping.
> Claiming in the run's **first** commit, **by site** (file + function, not just the lead), cost under a
> minute; `main` had not moved by merge time and there was no collision.

> **Builder 2026-08-30, branch `claude/compassionate-galileo-ezix3s` — run finished, all claims released.**
> Worked the standing **"sweep the engine for a POSITION-DEPENDENT metric compared across a whole target"** QA
> lead, and shipped three, each reproduced before fixing:
> **v0.304.2** (top of "Bugs") — a perfectly clear three-panel mosaic scored **0.5008** on the per-run
> `transparency_ratio` and got a **"Hazy night"** badge on History, Gallery and Compare, telling the owner to
> reject their haziest subs on a night when nothing about the weather changed.
> **v0.304.3** (under "Image quality") — the bulk **"reject worst N%"** cut ranked target-wide, so all six of
> its rejections landed in the *sparsest panel*: "drop my haziest 10%" was really "delete a sixth of this
> panel's coverage".
> **v0.304.4** (under "Autonomy & friendliness") — the filed *"first zoom clip is a silent wait"*: a shared
> `DownloadMenuItem` that holds the menu open with a spinner while the server builds the file, keeping the
> plain-link fallback for a browser with no blob path.
> **Stood down, wholesale:** this run also fixed `transparency_trend` (the "clouds rolled in" verdict on the
> same mosaic), and so did the `…-xkjuvl` Builder, concurrently — **theirs landed on `main` first, so mine was
> dropped entirely at merge time** and `main`'s implementation ships. The sixth such collision; the process
> note on it (under "Image quality") has the one defence that would actually have helped, which is *naming the
> site* in the claim, not just the lead.
> **The lead is now closed:** the rest of its candidate list — `stackhealth`, `_fwhm_quality_drift`,
> `best_frame` — was swept and came back clean, recorded on the entry so nobody re-treads it.

> **Builder 2026-08-30, branch `claude/compassionate-galileo-6jgh4j` — run finished, claim released.**
> **Shipped two, the second found by measuring the first.**
> **v0.312.0** (under "Features that serve real workflows") — the filed slice (a): the "what stacking removed"
> tint on the full-screen viewer, on the Gallery and the Target hero. The entry's "ship the stand-down gate
> before the feature" was checked first and turned out **not to apply** — History withdraws the tint because
> opening **Adjust** swaps in a live render of the linear master, and neither of these surfaces has such a
> state — which is what kept it small. The one real piece of work was geometric, and it is a CSS trap worth
> knowing: wrapping the picture and the overlay in a shared positioned box makes the picture's
> `max-height: 100%` resolve against an auto-height ancestor, i.e. no cap, and a tall picture overflows the
> viewer. The overlay is a **sibling** instead, `inset: 0` + `margin: auto`, sharing one fit object and one
> transform string with the picture.
> **v0.312.1** (top of "Bugs") — and then I measured what I had just amplified, and it was **wrong**: the tint
> normalised its alpha against the map's *non-empty* pixels, which stops being the signal as the sub count
> rises. On real 64-sub engine output it washed **94 %** of the frame cyan while the caption called those marks
> satellite trails. Fixed by subtracting the map's own uniform noise floor, inert by construction on every
> sparse map and fenced off where the resize didn't average.
> **Two things stood down with numbers rather than left open:** the sibling **"N spots instead of a
> percentage"** idea (no minimum blob area separates marks from speckle across the sub counts this app is for —
> the summed map has thrown that information away), and the **Compare North-up** entry, whose argument against
> "turn each by its own angle" is recorded there as backwards, with the geometric cost that is the real
> objection and the solved-ness gap that makes its preferred shape harder than it reads.
> **One QA lead filed**, generalised from the bug: sweep every statistic that normalises against its own
> non-empty subset, because that subset stops being the signal as the library grows — the same class as the
> position-dependent-metric sites, along the *how much data went in* axis instead.
> The bug queue was checked first and was dry when the run started: every entry under "Bugs (fix these first)"
> was ✅ shipped, a ⚪ audit non-finding, or explicitly stood down pending owner data.

_(nothing else claimed — claim an item here with your branch name)_

> **Builder 2026-08-30, branch `claude/compassionate-galileo-xkjuvl` — run finished, all claims released.**
> **Shipped one, and stood two down as duplicates — read the process note below, this was collisions six AND
> seven in one run.** The one that landed is the **position-dependent-metric sweep** (**v0.304.1**, under
> "Image quality"), which found a real **fourth site** in the bug class behind v0.270.2 / v0.271.0 / v0.272.1:
> the "Clouds & haze" card called a mosaic's move to an emptier panel *"clouds rolled in after 22:21 UTC"*
> (measured 1000 → 450 before, 720 → 720 after). Everything else the QA lead named was swept and is recorded
> as cleared, with the reasoning, in that entry — don't re-tread it.
> **Stood down:** the **recipe-drift guard** and both **"Tonight, live" follow-ons**, both of which the
> `…-fj2p70` Builder shipped concurrently (v0.302.1 / v0.304.0) while this run was building them. Their
> versions are on `main` and this branch takes them wholesale rather than re-litigating naming — but **three
> things this run built that theirs didn't** are re-applied on top of *their* code, in their names: the
> **Adjust → Save** half of the drift (the reachable one — it needs no editor round-trip at all), the
> **`reference-sub` gate** that had been answering where its own info endpoint said "hidden", and
> `AUTO_EDIT_BAKED_LOOK_PREFIX` **registered in `run_meta.py`** so deleting a run takes its stamp with it
> instead of leaving an orphan row. Write-ups are folded into their entries.
> The bug queue was checked first and is still genuinely dry: every entry under "Bugs (fix these first)" is
> ✅ shipped, a ⚪ audit non-finding, or explicitly stood down pending owner data.

> **Builder 2026-08-30, branch `claude/compassionate-galileo-fj2p70` — run finished, all three claims
> released.** Shipped all three: the **recipe-drift stamp** (**v0.302.1**, write-up under "Autonomy &
> friendliness") so nothing silently assumes a re-edited "Process target" run's preview still shows its saved
> recipe; the run's new beginner feature, the **zoom clip** (**v0.303.0**, under "Features that serve real
> workflows") — the backlog's "Reveal", renamed because that word already means the one-frame-vs-stack card
> everywhere here — slices (a)+(b), engine → two endpoints → a Save/share item on History and the Target
> page; and both **"Tonight, live" follow-ons** (**v0.304.0**, under "Autonomy & friendliness"), the
> keep-awake reusing the slideshow's helper by *extracting* it rather than copying, and the one line naming
> the other targets from the same night.
> The bug queue was checked first and is still genuinely dry: every entry under "Bugs (fix these first)" is
> ✅ shipped, a ⚪ audit non-finding, or explicitly stood down pending owner data.
> **Three notes filed for whoever comes next:** the first zoom clip on a run is a silent lazy build behind a
> plain link (fix shape filed); a corner target can't be centred in its own clip, by design, and the shape
> that would fix it; and a ⚠️ process note about a **pre-existing** pytest quirk — a hand-picked file list that
> interleaves `tests/webapp/…` and `tests/…` paths can lose `tests/webapp/conftest.py` and make every later
> webapp test error `fixture 'client' not found`. It reproduces on untouched `origin/main`, it looks exactly
> like "my change broke everything", and it cost real time this run.
> Claiming in the run's **first** commit and pushing immediately (per the five duplicate-collision process
> notes) again cost under a minute; no collision.

> **Builder 2026-08-30, branch `claude/compassionate-galileo-lcagow` — run finished, all claims released.**
> Shipped two: the ~~invisible reveal on "Process target"~~ dogfood finding (**v0.301.0**, write-up under
> "Features that serve real workflows"), taking the *honest full fix* rather than the interim copy slice — the
> reference sub goes through the run's own stored recipe, so both halves carry identical processing; and both
> cheap taps on **"Your universe"** (**v0.302.0**) — the catalog blurb on the read-out, and **fly to it**.
> The bug queue was checked first and is still genuinely dry: every entry under "Bugs (fix these first)" is
> ✅ shipped, a ⚪ audit non-finding, or explicitly stood down pending owner data.
> Claiming in the run's **first** commit and pushing immediately (per the five duplicate-collision process
> notes) again cost under a minute; no collision.

> **Builder 2026-08-29, branch `claude/compassionate-galileo-4txqj1` — run finished, both claims released.**
> Shipped two: **"Share your glow-up"** (**v0.300.0**, write-up under "Features that serve real workflows") —
> all three filed slices, a new pure `seestack/beforeafter.py`, the `before-after.jpg` endpoint and the
> download button on the reveal card; and the **tofu-glyph guard** (**v0.300.1**, under "Friendliness") —
> `tests/glyphs.py` plus a walk over every caption builder in the seven modules that import `ImageDraw`. No
> current caption was affected, which is the honest outcome for a guard filed after its one live instance was
> fixed.
> **Verified in a running app, not just in tests:** `scripts/agent-dogfood.sh` booted a real install with the
> bundled sample, and the composed JPEG came back correct on a plain stack — which is also how the dogfood
> finding below was found (the reveal, and now the share, self-hide on every one-click "Process target" run).
> Filed under "Features that serve real workflows" with the measurement, the honest fix, and the interim
> slice. **Pruned** the Scout's "close the loop when auto-grade brings frames back" idea: grepped before
> starting it and found it already shipped end to end (`auto_regraded_back` → `autoRegradedBackNote`).
> The bug queue was checked first and is still genuinely dry — every entry under "Bugs (fix these first)" is
> ✅ shipped, a ⚪ audit non-finding, or explicitly stood down pending owner data. A fresh adversarial read of
> `stack/accumulator.py` (all three accumulators, the k-set insertion, the min/max drop schedule and its
> coverage semantics) found nothing — recorded so nobody re-treads it this month.
> Claiming in the run's **first** commit and pushing immediately (per the five duplicate-collision process
> notes) cost under a minute; no collision, and `main` never moved while the run ran.

> **Builder 2026-08-29, branch `claude/compassionate-galileo-92mr4d` — run finished, claim released.**
> Shipped one, deep: **"See what stacking removed"** (**v0.299.0**, write-up under "Features that serve real
> workflows") — all three filed slices, engine → endpoint → History toggle, across `stacker.py`,
> `drizzle_path.py`, `output.py`, the memory guard, a new endpoint and the run card. Two findings worth
> carrying forward are in that entry: **min/max rejection is deliberately not mapped** (its drop is structural,
> so a map of it is a canvas-wide wash implying damage that isn't there), and the tint needs a **percentile**
> scale plus an **area-averaging** resize or a single hot pixel and the noise-tail speckle between them bury the
> satellite trail the overlay exists to show. Two follow-ons filed under Ideas (the Gallery lightbox, and a
> connected-component "N spots" count).
> **Stood down** on *"Finish what you started"* after measuring the reshaped slice a previous Builder left on
> it: marginal noise gain is `1 − √(t/(t+1))`, strictly decreasing in `t`, so the proposed "biggest gain per
> hour" sort is **exactly** "least-shot target first" and would stop that card ever finishing anything. The
> ⚠️ note now on that entry has the measured table, why the *line* version was declined too (the Target page
> already answers it from **measured** grain, and `/tonight` carries no `noise_sigma`), and the one shape that
> would earn its place if the owner asks.
> The bug queue was checked first and is genuinely dry: every entry under "Bugs (fix these first)" is either
> ✅ shipped or a ⚪ audit non-finding, and the one live item (the ASTAP ladder's 3× per-frame timeout) is
> explicitly stood down pending owner data — see the Builder note on it. Claiming in the run's **first** commit
> and pushing immediately (per the five duplicate-collision process notes) cost under a minute; no collision.
> **Builder 2026-08-29, branch `claude/compassionate-galileo-1i6x9x` — run finished, all three claims released.**
> Shipped: the finish forecast's **`want` horizon** so a 4+-night goal finally gets a date (**v0.297.1**, under
> "Autonomy & friendliness"), the **one storage alert** a flaking drive now gets instead of two (**v0.297.2**,
> same section), and the run's new beginner feature — **"Tonight, live"** at `/live` (**v0.298.0**, under
> "Features that serve real workflows"). Claiming in the run's **first** commit and pushing immediately (per
> the five duplicate-collision process notes) cost under a minute; no collision this run.
> Two follow-ons filed below, both spotted while building the live page.

> **Builder 2026-08-29, branch `claude/compassionate-galileo-gwhwwd` — run finished, claim released.**
> Shipped three: the stack run's read errors rolled up into a counted sentence on History and the Jobs
> result (**v0.296.5**, under "Image quality"), the two "Show and tell" follow-ons — keep-awake and
> "start the show here" (**v0.296.6**, under "Autonomy & friendliness"), and the observability-aware
> **"When will I finish this?"** forecast (**v0.297.0**, under "Features that serve real workflows").
> **Stood down** on *"Does my colour look right?"* — its premise doesn't hold: measured against the real
> bundled catalog, all 157 entries carry one flat `nebula` type, so emission and reflection (the two
> families whose colour expectations disagree) aren't separable offline. The ⚠️ note now on that entry
> has the measurement and the data task that has to come first.
> Claiming in the run's **first** commit and pushing immediately (per the five duplicate-collision process
> notes) again cost about a minute; no collision this run, and `main` never moved while it ran.

> **Builder 2026-08-29, branch `claude/compassionate-galileo-u3wi1n` — claim released, shipped.**
> Shipped: the ⭐ owner-clarified **real universe map** (true 3D by distance) as **"Your universe"**
> (**v0.296.0**, write-up under "Features that serve real workflows"), **"your last stack didn't run, here's
> the setting that would fix it"** (**v0.296.1**, under "Autonomy & friendliness" — read its note about the
> filed shape missing the unattended case), and the object-label de-confliction that keeps a crowded field
> readable (**v0.296.2**, under "Friendliness"). Claiming in the run's *first* commit and pushing immediately
> (per the five duplicate-collision process notes) cost under a minute; no collision this run.

> **Builder 2026-08-29, branch `claude/compassionate-galileo-eypoyg` — run finished, all claims released.**
> Shipped: the two-pass error-list loose end (**v0.294.3**), "what would it take to print bigger?"
> (**v0.295.0**), and the framing nudge on "Point here tonight" (**v0.295.1**). **Stood down** on *"the picture
> a beginner actually shares is 1024 px wide"* — sizing it against the code showed an **L**, not the filed
> S–M; the ⚠️ Builder note now on that entry has the three pieces, the cache the recipe path needs, and the
> test blast radius. Also pruned *"Was my focus sharp last night?"* as already shipped twice over.
> Claiming in the run's **first** commit and pushing it immediately (per the five duplicate-collision process
> notes) cost about a minute and is worth doing.

---

## QA sweep & audit records moved out of "Bugs" (2026-09-05 bulk move)

The 24 records below were cut verbatim out of `IMPROVEMENTS.md` →
"Bugs (fix these first)", where a clean-sweep record was the first thing every
triaging agent read. None of them is a bug; they are kept so a Scout can rotate
away from ground that has already been swept.

- **⚪ SWEEP RESULT — the rest of the wrong-denominator class is CLEAN; here is the list so nobody re-walks it
  (Builder 2026-09-03, the same sweep that turned up the readiness bug above).** *(No code change wanted.)*
  The class's rule, from the v0.331.2 note: *any per-pixel or per-crop quantity compared against a
  whole-target total is wrong on a mosaic*. Every remaining consumer of `n_frames_used` and of
  `total_exposure_s` was read against it:
  - **`stackhealth.rejection_blind`** — already fixed; it compares against `coverage_max`, the deepest pixel,
    and says *"with no more than N subs overlapping at any one spot"* in the mosaic branch.
  - **`stackhealth.noise_vs_expected` / `noise_yardstick_frames`** — fixed in v0.331.2 / v0.332.0.
  - **`noiseReductionBadge`** — fixed in v0.332.2 (the entry further down).
  - **`stackhealth.roughly_aligned`** — the denominator is `n_frames_used` and that is **right**: a
    roughly-aligned sub is a whole frame, and the population it comes from is the contributing frames. Not a
    per-pixel quantity at all.
  - **`portfolio.py`** (best-picture scoring) and **`restackgain.py`** — both compare target-level facts
    against other *target-level* facts (frame counts against the library's max, a run's count against the
    accepted count). Nothing per-pixel enters.
  - **`imaging_log`'s `n_subs`** — a stated fact about the run, not a claim about a pixel. Correct as it is.
  - **`readiness.noiseReductionHint`** — measured above: the panel count cancels. Correct on a mosaic.
  **All four wrong-denominator instances the sweep found are now shipped**: the readiness goal — the one live
  instance this note used to point at — was fixed in v0.334.0 by the `webapp/field_fulls.py` route the entry
  above named. **If the class is ever re-swept, the generative question is not "does this use
  `n_frames_used`?" but "does this compare a *cleanliness/depth* quantity against a *whole-target* total?"** —
  which is why the fourth instance was in `total_exposure_s` and survived three sweeps that all grepped for
  the frame count.

- **⚪ SCOUT QA RE-AUDIT (2026-09-04, stacking engine core + full-app dogfood) — swept and CLEAN; no new
  verified bug. Recorded so the next Scout rotates away from this ground rather than re-treads it.** Led the
  rotation with `seestack/stack/*` + `seestack/calibrate/*` as AGENTS.md §1 asks, re-read adversarially end to
  end for NaN/coverage semantics, rejection/weighting math, memory bounds and error paths — and it holds,
  confirming the 2026-09-01 note one entry below: `accumulator.py` (all three accumulators; the any-channel
  frame count, the MinMaxReject k-set insertion + count-band degrade, Welford's NaN-for-`n<2` variance),
  `weighting.py` + `photometric.py` (per-panel `pointing_groups` split, geometric-mean floor, the `1/s²`
  photometric-into-combine fold), `calibrate/{apply,masters}.py` (no-data-pedestal→0, flat floor, the
  `bias + (dark−bias)·ratio` exposure-scaling with its two no-data masks, `_bias_applies` never
  double-subtracting), `drizzle_path.py` (the frame-count `neff` gate vs pixfrac-deflated weight, float64
  variance + resolution floor, per-channel reject tally + scatter map), `mosaic.py` (wrap-safe circular-mean
  outlier rejection, px/MP caps), `pointings.py` (union-find single-linkage + ≥2-substantial gate), `align.py`
  (windowed inset/valid mask, the order-1 NaN-propagation ring on both sub-pixel shift paths), and the κ-σ
  pass-2 keep-mask (`_kappa_sigma_keep_mask` — both σ-unknown and mean-unknown widen to keep-all). Combine
  dispatch (`auto_reject_method` / `combine_method` / `auto_reject_depth`) traced clean. **Dogfood pass**
  (`scripts/agent-dogfood.sh`, real app + bundled sample stacked): probe reports **nothing overflowing, no
  console errors**; tallest page 3014 px (phone Target) — bit-for-bit the AGENTS.md §1 baseline, so no IA
  regression. One non-bug surfaced and filed as **log hygiene** under "Infra / maintainability": ~20 benign
  `astropy.stats` NaN warnings per stack (verified result-preserving). Baseline suite green this run
  (**4423 passed, 2 skipped**). **Next Scout: rotate onto the webapp routers not swept recently — `stack.py`/`editor.py`,
  `upload.py`/`scanner.py` ingest, `video.py` — per the 2026-09-02 note directly below; the engine core is
  drained.**

- **⚪ SCOUT QA RE-AUDIT (2026-09-02, webapp routers / ingest / plate-solve / render — swept, mostly CLEAN;
  three verified findings filed above, the rest clean.** This run rotated off the (drained, re-confirmed-clean)
  stacking engine core onto the areas the 2026-09-01 note flagged as higher-marginal. Traced adversarially and
  found **clean**: `seestack/io/ingest.py` (dedup by realpath, the in-place-swap / same-capture / incomplete-
  rewrite recovery, fingerprint backfill), `webapp/watcher.py` (`StabilityTracker` re-arm on in-place rewrite,
  stranded-batch re-offer), `seestack/solve/astap.py` (the 3-rung ladder, timeout-token classification,
  `.ini`/`.wcs` parsing), `seestack/solve/runner.py` (no cross-frame WCS leakage, serial DB apply, RA hours-vs-
  degrees end-to-end), `seestack/qc/noise_ratio.py` + `grading.py` + `metrics.py` (robust z-score / per-panel
  split / caps; the green-channel Bayer layouts; NaN-safe medians), `seestack/render/orient.py` (north-up
  rotation transforms, snap↔PIL split), `webapp/routers/plan.py` (the whole night-planner surface),
  `webapp/routers/gallery.py`/`stats.py` best-picture ranking + night accounting (one low-sev zip-dedup bug
  filed), and `seestack/render/thumbnail.py`/`deepening.py`/`zoomclip.py` (the one asinh full-res parity bug
  filed above; the STF path, NaN-aware downscale, deepening's frozen-STF replay and zoomclip's frame maths all
  clean). Baseline suite green this run (**3844 passed, 2 skipped**). Next Scout: rotate onto the webapp
  **stack.py**/**editor.py** routers, **upload.py**/**scanner.py** ingest, and **video.py** — not swept this run.

- **⚪ SCOUT QA RE-AUDIT (2026-09-01, stacking engine core) — swept and CLEAN; no new verified bug.
  Recorded so the next Scout can rotate away from this ground rather than re-tread it.** Read
  adversarially this run, end to end, hunting NaN/coverage semantics, rejection/weighting math,
  memory bounds and error paths: `seestack/stack/accumulator.py` (all three accumulators — the
  WeightedSum any-channel frame count, the MinMaxReject k-set insertion + graceful count-band
  degrade, and Welford's NaN-for-`n<2` variance contract), `seestack/stack/weighting.py` +
  `photometric.py` (the per-panel `pointing_groups` split, the geometric-mean weight floor, the
  `1/s²` photometric-into-combine variance fold), `seestack/calibrate/{masters,apply}.py` (the
  no-data-pedestal → 0 sanitisation, the flat floor, the exposure-scaling `bias + (dark−bias)·ratio`
  with its two no-data masks, `_bias_applies` never double-subtracting), `seestack/stack/drizzle_path.py`
  (the frame-count `neff` gate vs pixfrac-deflated weight, the float64 variance + resolution floor,
  the per-channel reject tally + scatter map), `seestack/stack/mosaic.py` (wrap-safe circular-mean
  outlier rejection, the px/MP canvas caps), `seestack/stack/pointings.py` (union-find single-linkage,
  the ≥2-substantial-groups soundness gate), `seestack/stack/align.py` (windowed reproject inset/valid
  mask, the order-1 NaN-propagation ring on both sub-pixel shift paths, the `REF_PATCH_MIN_COVERAGE`
  stand-down), and `seestack/stack/output.py` (linear-percentile pack, `_autostretch_for_export` ↔
  saved-preview parity via the shared `EXPORT_AUTOSTRETCH_TARGET_BG`). QC feeders `noise_ratio.py`
  and `grading.py` spot-checked too. Every file carries dense prior-audit provenance and its edge
  cases hold. Baseline suite green this run (**3799 passed, 2 skipped**). The genuinely novel-bug
  surface in the engine core is drained; the higher-marginal QA value has moved to the webapp
  routers / ingest / plate-solve, which this run did not sweep.

- **⚪ AUDIT NOTE (Builder 2026-08-27, swept immediately after fixing the debayer bug — NON-finding, recorded so
  nobody re-treads it) — "a `!= 0` / `> 0` value test standing in for a validity mask" is a bug *class*, and the
  debayer was the only place in the engine where it was wrong.** The pattern is only a bug where **0 is a
  legitimate datum**; everywhere else in `seestack/` it is used where 0 genuinely *means* "none", and is
  correct. Swept and cleared: `drizzle_path.py:375` (`np.where(wht > 0, img, np.nan)` — `wht` is accumulated
  deposit weight, so 0 really is no coverage); `bg/coverage_leveling.py:280` (`cov_int > 0` — a frame count);
  `bg/per_frame.py:453` (`n > 0` — a bin population, paired with the same `np.maximum(n, 1.0)` normalisation);
  `calibrate/masters.py:101` (`mad > 0` — a zero MAD legitimately means "no spread, clip nothing");
  `stack/weighting.py` (`star_count > 0` — zero stars really is unusable). *(Confidence: read, not reproduced —
  each was traced to why 0 means "none" there. Filed as a note, not a bug.)* If a future change makes any of
  those quantities able to be a *measured* zero, this is the shape of the mistake to look for.

- **⚪ QA AUDIT RESULT (Scout 2026-08-27 #21, branch `claude/vigilant-knuth-gcb43u`) — led with the stacking
  engine per the rotation. Ran my own adversarial reads of `accumulator.py`, `weighting.py`, `photometric.py`,
  `stacker.py` (κ-σ two-pass + min/max wiring + output/preview parity) and `render/thumbnail.py`
  (asinh/STF stretch parity), plus **three parallel adversarial audits**: (1) `drizzle_path.py` + `mosaic.py`;
  (2) `calibrate/apply.py` + `masters.py` + `align.py`; (3) `stacker.py` rejection/combine + `reference.py` +
  `pointings.py`. **Result: the stacking engine core stays clean (11th consecutive sweep)** — no verifiable
  data-integrity bug. Only ONE new verified finding, cosmetic: the `estimate_stack` outlier-exclusion
  discrepancy (pre-run UI estimate only; pixels untouched) — **found, fixed and shipped this run (v0.287.2)**,
  see the SHIPPED entry directly above. Baseline green before starting
  (full headless suite: **3144 passed, 2 skipped, 0 failed**). **Traced NON-findings (recorded so they aren't
  re-chased):** drizzle var-moments share weights so `E[v²]−E[v]²` is Jensen-nonneg; drizzle rejection floor /
  `neff`=true-frame-count / `wht>0 ⇒ count≥1` all sound; drizzle CRPIX `(crpix−0.5)·s+0.5` and half-open
  in-bounds edges correct; mosaic RA-wrap uses circular mean + haversine (wrap/pole-safe); calibrate
  exposure-scaling `bias+(dark−bias)·(t_l/t_d)`, flat floor→1.0, pedestal sanitize→0 all correct and no
  double-bias; `_sigma_clip_mean` mad==0→tol=0 rejects a minority spike while all-NaN degrades to NaN;
  κ-σ pass-2 keep-mask widens to keep-all on σ-unknown (+inf tol) and mean-unknown (keep) so pass-2 data is
  never turned into a NaN gap; photometric `pscales` applied once per fresh array in BOTH passes (no double-
  apply — `align_one` has no caching) with the `1/s²` correction folded only into `combine_weights`;
  `WeightedSum` keeps Σ-weights (`coverage`) separate from the true frame count (`frame_coverage`) and the
  diagnostics/leveling read the honest count; min/max k-insertion sort + band schedule + `rejection_counts`
  match `result()` exactly; asinh/STF both normalise over covered pixels with a robust 99.5th-pct ceiling and a
  soft highlight rolloff, NaN excluded from every stat. **Low-severity edge notes (NOT filed — cannot affect a
  real Seestar run):** CPU vs GPU reproject `cval` (NaN vs 0.0) diverge only on ≤12-px synthetic frames where
  the 3-px edge inset is skipped; `win_valid` is left stale after a sub-pixel refine but every accumulator
  recomputes `valid = np.isfinite(window_image)`, so the stale True at a now-NaN pixel is still excluded
  (benign by contract). Editor/webapp not re-audited this run (drained + clean per #18-#20).**

- **⚪ QA AUDIT RESULT (Scout 2026-08-27 #20, branch `claude/vigilant-knuth-upgplg`) — led with the stacking
  engine per the rotation (my own adversarial read), then fanned three parallel audits across the
  **less-recently-swept** subsystems: (1) plate-solve (`seestack/solve/astap.py`, `runner.py`, `bootstrap.py`);
  (2) render / export-parity (`seestack/render/*`, `seestack/stack/output.py` + their `stack.py`/`pipeline.py`
  callers); (3) webapp routers + pipeline auto-stack chain + the `incoming/` guardrail. Also dogfooded the live
  app end to end (`scripts/agent-dogfood.sh`). Result: **THREE verified, reproduced bugs filed at the top of
  this section** — the plate-solve garbage-`.wcs`-stored-as-solved (broken-UX/data-integrity), the full-res PNG
  discarding a saved asinh Adjust (broken-UX), and the Sky-map overlay north-up misalignment (broken-UX/overlay).
  The **stacking engine core stays clean** (10th consecutive sweep) and the **webapp router/pipeline layer +
  `incoming/` read-only guardrail are clean** (independent re-confirmation of audit #19's verdict).**
  **My own engine reads (all NON-findings, traced to guards):** `accumulator.py` — `WeightedSum`/`Welford`/
  `MinMaxReject` all NaN-aware; the min/max k-set insertion sort maintains the k smallest/largest correctly and
  the "full ≥2k+1 / single 3..2k / mean 1-2 / NaN 0" degradation bands are exact with no inf−inf; `frame_coverage`
  counts any-channel contribution so per-channel κ-σ never under-counts. `stacker.py` — `_kappa_sigma_keep_mask`
  widens to keep-all on both σ-unknown (NaN std → +inf tol) and mean-unknown (NaN mean → keep) so pass-2 data is
  never turned into a NaN gap; the two-pass `n_used=min(p1,p2)` guard raises rather than writing a silent all-NaN
  master, with the `not cancel()` clause protecting a routine cancel. `photometric.py` / `weighting.py` /
  `pointings.py` — the mosaic per-panel split (position-dependent metrics judged per panel, seeing/tracking
  target-wide) is sound; `combine_weights_with_photometric` folds the correct `1/s²` inverse-variance term and
  returns the same object (byte-for-byte) when photometric is off; `cluster_pointings` single-linkage union-find
  is wrap- and pole-safe on unit vectors. **Dogfood (happy path clean):** the Target-page IA refactor has landed
  (picture + frames above the fold, banner wall behind a "1 more note" disclosure); Stack and Editor pages read
  clearly with sane defaults and plain-language guidance; no console errors, no overflow, clean boot+stack in the
  server log. Baseline stacking subset green before starting (`test_stack_pipeline`, `test_accumulator`,
  `test_mosaic`, `test_drizzle`, `test_calibrate`, `test_fits_loader` — 218 passed).

- **⚪ QA AUDIT RESULT (Scout 2026-08-27 #19, branch `claude/vigilant-knuth-1azkk1`) — led with the stacking
  engine per the rotation, running **four** parallel adversarial audits plus my own read of the stack→result
  autonomy path and the preview↔export stretch. Areas: (1) stacker rejection math + reference pick
  (`stacker.py`, `reference.py` — κ-σ two-pass, per-channel rejection, weight×photometric folding, NaN/coverage,
  memory bounds, dtype); (2) drizzle + mosaic + pointings + output (`drizzle_path.py`, `mosaic.py`,
  `pointings.py`, `output.py` — kernel weight/coverage normalisation, WCS→pixel scaling, seam/bbox, gap=NaN);
  (3) calibrate + align (`calibrate/apply.py`, `masters.py`, `stack/align.py` — sigma-clip master build, dark
  exposure-scaling, flat divide-by-zero, raw-Bayer domain, GPU/CPU cval parity); (4) watcher + ingest + scanner
  + QC (`watcher.py`, `io/ingest.py`, `io/scanner.py`, `qc/*` — stability re-arm, mid-write/0-byte/truncated
  fingerprint, the `incoming/` read-only guardrail, streak/auto-grade reconcile). **Result: the engine and the
  hot path are CLEAN on the corruption axis — no new verified wrong-result or data-loss bug (9th consecutive
  engine sweep).** The `incoming/` read-only contract holds: the only filesystem write touching an incoming path
  anywhere in the four ingest/watcher files is the `shutil.copy2(src, cached)` in ingest's stage-1 copy (source =
  read, destination = library cache) — no `unlink`/`move`/`rename`/`truncate`/`replace`/`open('w')` resolves into
  `incoming/`. Baseline stacking-subset green before starting (`test_accumulator`, `test_stack_pipeline`,
  `test_mosaic`, `test_drizzle{,_reject}`, `test_calibrate`, `test_windowed_stack`, `test_photometric_stack` —
  225 passed).
  **Two low-severity observations, TRACED but deliberately NOT filed as verified bugs** (recorded so a future
  audit doesn't re-tread them):
  1. **κ-σ `n_frames_used` can be *undercounted* (never over) when pass 2 aligns more frames than pass 1.**
     `stacker.py:1893` sets `n_used = min(n_used_p1, n_used_p2)`, surfaced as `n_frames_used` (`:2187`) and
     `n_align_failed` (`:2195`). A frame that throws a transient load error in pass 1 but succeeds in pass 2
     (the exact NAS-blip case the `mean`-unknown keep-guard in `_kappa_sigma_keep_mask` was added to support)
     *does* contribute pixels to the final image (kept where only it covers, via the NaN-mean widening), yet
     `min()` credits only the smaller pass-1 count — so History's NFRAMES / integration time reads slightly low.
     **Not filed because:** the pixels are correct (no corruption); `min()` is the *right* conservative choice
     for the more consequential reverse case (a frame that aligned in pass 1 but failed pass 2 contributed only
     to the reference, not the final image, and `min()` correctly excludes it); the trigger is a rare cross-pass
     I/O race, not reachable by frame content or config; and the error direction is always fail-safe
     (understates, never overstates, integration time). A tidy fix would count `wsum.frame_coverage.max()` (the
     true per-pixel contributing-frame count) instead of `min(p1,p2)`, but that is a hot-path semantics change
     for a cosmetic gain — left for a Builder to weigh, not urgent. Distinct from the v0.136.4 empty-guard fix on
     the same line (that raised on `n_used==0`; this is about the *value* when both are >0). Confidence: traced.
  2. **Streak self-heal re-accepts a still-streaked `auto:streak` frame when streak auto-reject is *off*.**
     `qc/runner.py:115-127`: the `elif prior_reason == "auto:streak"` branch re-accepts on any non-override
     re-QC without also checking `not m.streak_detected`, though its docstring says it fires only when the frame
     is "now clean". Because it's an `elif` under `if auto_reject and m.streak_detected`, it is **unreachable for
     a still-streaked frame on the default path** (`auto_reject_streaks=True`, `scanner.py:562` — the first `if`
     wins). It only differs when a user has *disabled* streak auto-reject, and there re-accepting a previously
     auto:streak frame is arguably the intended semantics (the user opted out of streak rejection, and the
     stack's own per-pixel κ-σ/drizzle rejection still cleans any real trail). **Judged by-design, not a bug**;
     if anything the docstring could add "(or streak auto-reject is now off)". Confidence: traced, low.
  My own reads (all NON-findings): the walk-away auto-stack chain (`pipeline.py` — `_auto_stack_frame_count`,
  `_auto_stack_readability_hold`, `_readability_recovered`, `_auto_stack_degraded_recheck`,
  `_auto_stack_calibration_recheck`) traces correct — the readability preflight holds without stamping, the
  degraded-heal fingerprint fires once and won't re-fire on a heal that comes out thin, and every crash-loop
  marker is cleared on a survivable failure; and the preview↔export stretch (`output._autostretch_for_export` →
  `thumbnail.autostretch`, `_to_uint16_linear`) is NaN-aware everywhere, computes stats over covered pixels only,
  and clamps the MTF midtone — a mosaic's no-data gaps can't skew the black point.

- **⚪ QA AUDIT RESULT (Scout 2026-08-27 #18, branch `claude/vigilant-knuth-qtz5h4`) — led with the stacking
  engine per the rotation, then fanned three parallel adversarial audits across less-recently-swept areas: the
  **background/gradient** subsystem (`seestack/bg/*`), the **calibration master build+apply**
  (`seestack/calibrate/*`), and the **job manager + video-stacking + library-merge** path (`webapp/jobs.py`,
  `routers/video.py`, `webapp/video.py`, `seestack/io/merge.py`). Result: **one verified, reproduced broken-UX
  bug** in the video re-sharpen path (filed at the top of this section — crop+sharpen stills refuse every
  re-sharpen while advertising the control as editable); **bg, calibrate, and the jobs core all CLEAN.** The
  engine core stays clean (8th consecutive engine sweep). Also shipped the debayer exact-0 fix (v0.284.5,
  above).**
  **What was read adversarially and traced (each a NON-finding except the video bug — traced to a guard):**
  **bg/gradient** (`coverage_leveling.py`, `final_gradient.py`, `per_frame.py`, `sky_poly.py`, `hot_pixels.py`)
  — NaN=no-coverage preserved bit-for-bit through `level_by_coverage`, `suppress_hot_cold_pixels`,
  `subtract_background`, and `final_gradient` (no NaN→0, no number→NaN, inputs copied before mutation); the
  detrend-before-threshold + `_MIN_DETECT_AREA` small-detection drop + faint-extended second pass guard object-
  mask starvation; `fit_sky_poly` requires ≥`n_terms*4` tiles and SVD-`lstsq`, returns `None` on degenerate
  input; the cross-level `polyfit` is try/except-wrapped and every filled offset is `np.clip`-ed to the measured
  `[lo,hi]` envelope (no manufactured seam). *(One GPU-only observation — `_subtract_background_gpu` fills a
  fully-masked tile with the luminance median rather than neighbouring tiles — was traced but is **unreproducible
  without cupy** and nil-impact on fully-NaN tiles, so it is deliberately NOT filed as a bug; noted as a
  low-priority hardening idea below for a GPU-capable follow-up.)*
  **calibrate** (`masters.py`, `apply.py`) — sigma-clip-mean matches intent (MAD clip about the median, mean of
  survivors; `mad==0`/spike `tol=0` branch verified), exposure-scaled dark `bias+(dark−bias)·ratio` sign correct
  and no-data bias/dark pixels restore the right no-correction identity on both scaled and unscaled paths (no
  spurious pedestal), flat divide floors zero/neg/sub-floor/NaN/inf to 1.0, uint16→float32 promotion before any
  subtraction (no wrap), mismatched-shape masters skipped, empty-bundle path returns a fresh array, shared
  masters never mutated. Independently reproduced the four-way no-data pixel matrix.
  **jobs/video/merge** (`webapp/jobs.py`, `routers/video.py`, `webapp/video.py`, `seestack/io/merge.py`,
  `seestack/video/*`) — `_recover_interrupted` runs in `__init__` before `start()` and flips both `running` and
  `queued` → `interrupted`, so no job is left stuck running across a restart; the single-worker cancel↔claim race
  is resolved under one `RLock`; `_persist` serialization and the DB write are both guarded so neither kills the
  worker; ffmpeg `iter_frames` reads exactly one frame at a time with a `finally` that kills+reaps the subprocess
  (memory-bounded, no handle leak, cancel unwinds promptly); the two-pass `select=not(mod(n,stride))` filter
  decodes identical frames in both passes; and **`incoming/` stays strictly read-only** — the video path only
  reads it (via ffmpeg) and writes solely under `<data_root>/video/…`, `merge.py` copies into the *destination*
  project and never touches `incoming/` or rewrites a stored `source_path`. Client capture ids are re-sanitized
  server-side; no client filesystem path reaches disk.

- **⚪ QA AUDIT RESULT (Scout 2026-08-27 #17, branch `claude/vigilant-knuth-s4y5o3`) — a **depth** sweep that
  led with the stacking engine (`seestack/stack/*` + `seestack/calibrate/*`) across three parallel adversarial
  traces, plus a live-app dogfood. Result: the engine core is clean for the **7th** consecutive sweep; one
  low-severity **debayer** imperfection filed above (genuine exact-0 samples excluded from neighbour
  interpolation — `fits_loader.py`, reproduced) and one cosmetic note below.** Baseline green before starting
  (full headless suite: **3094 passed, 2 skipped** in 11:46). Live app booted + sample stacked end-to-end via
  `scripts/agent-dogfood.sh` (happy path clean: no overflow, no console errors; the Target-page IA refactor has
  landed — picture + frames above the fold, banner wall consolidated behind a "1 more note" disclosure).
  **What was read adversarially and traced to a guard (every item a NON-finding except the debayer one filed
  above):**
  **Accumulators** (`accumulator.py`) — `WeightedSum`/`MinMaxReject`/`Welford` all NaN-aware; the min/max k-set
  insertion sort maintains the k smallest/largest correctly and the ±inf identities never form an inf−inf NaN in
  `result()`; the count-band degradation (≥2k+1 → full trim, 3..2k → single drop, 1-2 → mean, 0 → NaN) is exact;
  `frame_coverage` counts a frame via `valid.any(axis=2)` so a per-channel κ-σ drop can't under-count "frames
  per pixel".
  **Weighting/photometric** (`weighting.py`, `photometric.py`) — geometric-mean weight stays in [min,1];
  per-panel positional medians self-disable on a single field; `combine_weights_with_photometric` folds the
  correct `1/s²` inverse-variance correction and returns the same object (byte-for-byte) when no scaling is
  active.
  **Drizzle/mosaic/pointings** (`drizzle_path.py`, `mosaic.py`, `pointings.py`) — NaN gaps stay NaN (never 0);
  off-canvas frames deposit nothing; `_clip_tolerance` regimes all correct; CRPIX super-res scaling
  `(crpix−0.5)·scale+0.5` and canvas bbox pad are exact; union-find pointing clustering wrap-safe.
  **Align/calibrate** (`align.py`, `calibrate/apply.py`, `calibrate/masters.py`) — flat divide floors zero/neg/
  sub-floor pixels to 1.0; dark exposure-scaling `bias+(dark−bias)·ratio` restores no-data pixels; a frame that
  raises mid-stack is skipped cleanly (never touches the accumulator); reproject no-WCS raises, non-intersecting
  footprint → None; all-float32 (no uint16 wrap).
  **Stacker/output** (`stacker.py`, `output.py`) — κ-σ pass-1/pass-2 keep masks correct (NaN mean → keep, NaN
  std → tol=+inf keep-all for single-coverage edges); memory guard `_estimate_peak_bytes` matches the real plane
  counts; preview↔export share `_autostretch_for_export`; NaN→black consistently across FITS/TIFF/PNG.

- **⚪ QA AUDIT RESULT (Scout 2026-08-27 #15, branch `claude/vigilant-knuth-ilxa69`) — a **depth** sweep that
  led with the stacking engine and then rotated onto the **QC metric layer** (`seestack/qc/*`) that feeds
  weighting/photometric/grading, plus the stack **output/parity** path. Result: CLEAN — no verified bug this run,
  the **sixth** consecutive clean engine sweep (#10–#15). Baseline green (full headless suite: **3068 passed, 2
  skipped** in 11:30). Live app booted + sample stacked end-to-end via `scripts/agent-dogfood.sh` (happy path
  clean).**
  **What was read adversarially and traced this run (every item below is a NON-finding — traced to a guard, not a
  bug). The engine combine/drizzle/photometric/mosaic/calibrate paths re-confirmed as in #14; new-this-run
  coverage is the QC + output layer:**
  **QC metrics** (`qc/metrics.py`) — `green_channel` promotes the raw Bayer mosaic to float32 *before* averaging
  the two green sites, so summing two bright 16-bit green pixels can't wrap mod 2¹⁶ and corrupt exactly the bright
  stars QC leans on; all four Bayer layouts map G to the correct sites; `median_star_flux`'s `flux[-top_k:]` is
  slice-safe below `top_k` stars; `median_eccentricity`/`median_fwhm` drop non-finite rows before the median so
  one NaN source can't poison the whole frame's metric.
  **QC grading** (`qc/grading.py`) — the `reconsider` pass grades over the *combined* (accepted + previously
  auto-graded) set, which is invariant under auto-grade's own accept/reject moves, so recommendations are a fixed
  point (no reject↔re-accept churn) and the `max_reject_fraction` rail is cumulative for free; the total order
  `(-worst_z, frame_id)` makes the cap boundary deterministic; `star_count==0` (log-undefined, low-is-bad) is
  treated as maximally bad while the same non-positive value on a high-is-bad metric is correctly skipped; the
  per-panel rail bounds the damage inside one mosaic panel before the target-wide cap.
  **QC streaks** (`qc/streaks.py`) — the probabilistic Hough is seeded (`_HOUGH_SEED`) so `streak_count` written
  to the DB is deterministic and QC stays idempotent; compact bright blobs (stars) are removed by an
  elongation+length test on the pixel covariance before line-fitting, so a dense star field isn't mistaken for a
  trail.
  **QC noise-ratio** (`qc/noise_ratio.py`) — the √N "cut your noise ~N×" badge measures a *raw* neighbour-diff
  MAD σ (`Var(Iᵢ₊₁−Iᵢ)=2σ²`) over covered pairs only, with a `_MIN_PAIRS` floor and a two-pass object-drop so a
  bright extended target doesn't inflate the background σ; returns `None` rather than a bogus ratio when either
  side can't be measured.
  **QC sky-quality** (`qc/sky_quality.py`) — the "brighter than usual?" read normalises each frame's sky by
  exposure, keys on the *dominant* (gain, exposure) group so a mixed-setting session can't read as a sky change,
  buckets by observing night (noon-to-noon) with `MIN_FRAMES_PER_NIGHT`/`MIN_NIGHTS` floors, and stays silent
  (returns `None`) rather than guessing when there's no "usual" to compare against.
  **weighting** (`weighting.py`) — geometric mean keeps the weight in `[min_weight, 1.0]`; each factor guards its
  own zero divisor (`frame_sky<=0`, `frame_ecc==0`) as neutral; the position-dependent trio (stars/sky/transp) is
  taken per mosaic panel and the `combine_weights_with_photometric` inverse-variance `1/s²` correction only fires
  on a genuinely-applied scale (returns the same object untouched when photometric is off — byte-for-byte).
  **stack output / preview↔export parity** (`stack/output.py`) — an editor export is stamped `SSDISPLY`
  display-space and written verbatim (no double-stretch) across FITS/TIFF/PNG; `_sanitize_basename` blocks path
  traversal from the web "output name"; `_archive_existing_outputs` moves the whole run set to one timestamped
  basename (siblings stay siblings) rather than overwriting, and the `_framecov` sibling is only written when it
  differs from the weighted coverage map — so an ordinary unweighted stack's output set is exactly the size it
  always was, and the sky-leveling pass reads the honest frame count on a weighted/drizzle mosaic.
  **pointings** (`pointings.py`) — single-linkage union-find on unit vectors is wrap-safe (RA 359↔1) and pole-safe;
  `pointing_groups` returns `None` (one target-wide population, today's behaviour) unless ≥2 groups each carry
  `min_members` eligible frames, so a single-field/unsolved/tightly-packed target is unaffected by every per-panel
  path that gates on it.
  **What was read adversarially and traced this run (every item below is a NON-finding — traced to a guard, not
  a bug):**
  **stack combine** (`accumulator.py`, `stacker.py`) — the `WeightedSumAccumulator` any-channel frame-count
  (`covered = valid.any(axis=2)`) equals `valid[...,0]` in the all-or-nothing common case; the
  `MinMaxRejectAccumulator` k-set insertion-sort keeps the true k smallest/largest and is tie-safe on a
  saturated star core (each extreme *value* subtracted once); the κ-σ two-pass `_kappa_sigma_keep_mask` widens
  to keep-all on both NaN-σ (single-coverage mosaic edge) and NaN-mean (pass-1/pass-2 coverage divergence), so
  the clip can never turn real pass-2 data into a NaN hole; the pass-1 Welford accumulator is `del`-freed before
  pass 2 allocates, so peak stays at the 4 canvas planes the OOM guard charges; `frame_cov=None` is handled by
  every downstream consumer (min/max coverage is already an exact frame count).
  **drizzle** (`drizzle_path.py`) — `_clip_tolerance` computes the variance in float64 to dodge the
  catastrophic-cancellation trap on ~counts² operands, gates rejection on the true **frame count** (`self._count`,
  not the pixfrac-deflated `out_wht`), and disables clipping below the float32 resolution floor so a bright flat
  region can't be punched into NaN; the half-open `[-0.5, N-0.5]` bounds correctly admit edge-band pixel centres;
  `result()` returns `out_img` directly (already a running weighted mean — dividing again would deflate flux).
  **photometric** (`photometric.py`) — neutral-fallback everywhere (no/≤0 transparency → scale 1.0, <3 measured
  frames → whole run neutral), each scale clipped to `[1/max_ratio, max_ratio]`, and mosaic panels normalised
  against *their own* pointing-group median (not one target-wide median that would read intrinsic panel star-field
  differences as haze).
  **mosaic** (`mosaic.py`) — the wrap-safe circular-mean centre RA (`_circ_mean_ra_deg` via `atan2`) is used
  consistently in both outlier passes, so a frame straddling RA=0 isn't flung to ~180° and wrongly rejected;
  MAX_CANVAS_PX + megapixel budget + "never drop >half" guards all hold.
  **calibrate/apply** (`apply.py`) — no-data dark/bias pixels are remembered *before* sanitising to 0 and
  restored to "no correction" on the exposure-scaling path (`bias + (dark−bias)·ratio` never scales a sanitized 0
  into a spurious pedestal); flat non-finite → NaN sentinel (floored to 1.0), never the dark's 0; `apply_raw`
  honours the "returns a fresh array" contract even on the empty-bundle path; the exposure/temperature mismatch
  advisories gate on the *same* `_dark_scaling_applies` predicate the scaling path uses.
  **coverage leveling** (`bg/coverage_leveling.py`) — the per-level detrend-before-threshold, the level-local
  rescue of a starved level's sky, the "too structured to be sky" refusal, and the gapped-extrapolation clamp to
  the measured envelope are all correct; a single-coverage-level (ordinary single-field) stack is byte-for-byte
  unchanged.
  **walk-away orchestration** (`webapp/pipeline.py`) — `_auto_stack_readability_hold` holds (without stamping the
  attempt) when stacking now would land below the min-frames floor *or* thinner than the target's best existing
  stack, gated on `unreadable > 0` so a healthy install is untouched; the crash-loop marker is cleared on a
  *recoverable* exception so a transient I/O error doesn't disable auto-stack forever.
  **Also cross-checked with two independent adversarial subagents** over `align.py`/`pointings.py`/`reference.py`/
  `weighting.py` and `solve/*`/`calibrate/masters.py`: both returned CLEAN with every flagged suspicion traced to
  a real guard (CPU/GPU reproject `cval` parity via the valid-mask inset; union-find path-compression termination;
  sky/ecc divide-by-zero guards; `mad==0` sigma-clip using `tol=0` not `+inf`; uint16→float32 promotion before
  every combine; the `solved = returncode==0 and sidecar.exists()` stale-sidecar gate). Curation + new ideas
  filed alongside (a new beginner feature + an improvement idea — see below).

- **⚪ QA AUDIT RESULT (Scout 2026-08-27 #13, branch `claude/vigilant-knuth-ns5hys`) — a **breadth** sweep:
  led with the stacking engine per the rotation, then fanned four independent adversarial audits across the
  areas due for rotation (render, QC, stack combine/weighting/output, and the guardrail-critical webapp
  render/stack/gallery routers), and closed with a **live mixed-quality auto-stack dogfood**. Result: CLEAN
  across the board — no verified bug this run, the fourth consecutive clean engine sweep (#10–#13). Baseline
  green (full headless suite; see the run's commit). Also curated two Ideas entries that had shipped since they
  were filed (see the Autonomy & friendliness section) and added a new beginner feature + two improvement
  ideas.**
  **What was read adversarially and traced (each finding below is a NON-finding — traced to a guard, not a bug):**
  **render** (`thumbnail.py`, `deepening.py`, `orient.py`, `colormap.py`) — every stretch/percentile stat is
  NaN-excluding (`np.nanmin`/`np.nanpercentile`/`_robust_median_sigma(finite)`), uncovered pixels only ever
  become 0/black at the *final display* step (`np.nan_to_num`), never inside a reduction; `np.rot90(k)` verified
  equivalent to `PIL.rotate(k·90)` for the 2×2 and negative-angle cases (no axis/sign error); MTF/asinh
  midtones clamp away from their singularities so no clip/invert path; the baked `_preview.png` and
  `render_preview_png_full_res` share `_autostretch_for_export`, so preview↔export match; the `_downsample_rgb`
  NaN→`nanmin` floor is confirmed no-op on its only two callers (both feed a raw NaN-free sub) — matches the
  latent-not-live note already in this file. **QC** (`streaks.py`, `noise_ratio.py`, `sky_quality.py`,
  `metrics.py`, `runner.py`) — all four Bayer layouts map the two green sites correctly and `green_channel`
  promotes to float32 *before* the add (no uint16 wrap); FWHM border check uses the right axis extents; every
  median metric appends only finite fits so a NaN can't sort a frame to best/worst; streak accept/reject sign
  correct and `detect_streaks` needs area≥8 ∧ major≥80px ∧ elongation≥4 (round stars can't qualify, stationary
  extended targets are re-accepted by `reconcile_streak_rejections`); MAD-on-constant/empty → `None`, not a
  divide. **stack combine/weighting/output** (`accumulator.py`, `weighting.py`, `photometric.py`,
  `pointings.py`, `channel_combine.py`, `output.py`) — `WeightedSum` returns NaN wherever `_weight==0` (gap
  survives), all five quality factors are `clip(min_weight,1)` so the geometric mean is provably in
  `[min_weight,1]`, `combine_weights_with_photometric` folds `1/s²` only on a genuinely-applied scale
  (`s>0 ∧ |s−1|>1e-9`, `s∈[0.5,2]`), photometric `scale=clip(ref/transparency,lo,hi)` guards both `ref>0` and
  `transparency>0`, `pointing_groups` self-disables on a single field (byte-for-byte the OSC path), `_count` is
  uint32 (no overflow), and float32 accumulation error is sub-0.1 ADU at realistic sub counts. **webapp routers**
  (`stack.py`, `pipeline.py`, `gallery.py`) — `{safe}` resolves only through `Library.find_target` (404s an
  unknown, never composes a path), all served artifact paths come from the run row not the client,
  client `output_name` passes through `_sanitize_basename` (`../../etc/passwd`→`etc_passwd`), render query
  params clamp via `_clamp`/typed ints (no NaN crash), every encoder `nan_to_num`+`clip` before uint8, the
  auto-edit vs editor-export full-res render forks correctly (parity), and the gallery/best-pictures/video-stills
  list endpoints all degrade per-item under `except…continue` (the v0.277.6 boundary holds).
  **Live dogfood (the part code review can't do):** built a 14-sub dithered synthetic target (two satellite
  streaks, one hazy sub, per-frame independent noise) and ran the real `run_stack(auto_reject=True,
  quality_weighted=True, photometric_normalize=True)`. Result clean and trustworthy — auto-reject fired
  (`REJFRAC≈0.016`, clipping the streaks), 96.9 % finite with the ragged dither corners correctly NaN, no
  inf/garbage, sky-subtracted linear output centred near zero (median ≈ 2.2 ADU) with star cores preserved
  (p99.9 ≈ 1146 ADU). The stack→result path is doing the right thing end to end.

- **⚪ QA AUDIT RESULT (Scout 2026-08-27 #12, branch `claude/vigilant-knuth-f9chv3`) — led with the stacking
  engine again, then rotated onto the data-integrity path the last real bug lived in (scanner + ingest), and
  **closed with a live end-to-end auto-stack dogfood** rather than pure code review. Result: CLEAN — no verified
  bug this run. Baseline green: full headless suite **2965 passed, 2 skipped** (822 s), and a 208-test targeted
  re-run over the audited engine areas (accumulator, quality-weighting, photometric-normalize, qc-grading,
  mosaic, drizzle, drizzle-reject, calibrate) passed in 58 s.
  **What was read adversarially and traced:**
  **weighting.py** — the geometric-mean-of-factors keeps every weight in `[min_weight, 1]`; the
  per-panel positional-median split (`group_by_pointing`) self-disables on a single field so an OSC target is
  byte-for-byte unchanged; `combine_weights_with_photometric` folds the `1/s²` inverse-variance correction only
  on a genuinely-applied scale (`|s−1|>1e-9`) and returns the *same object* when photometric is off.
  **photometric.py / pointings.py** — `_pointing_references` normalises each mosaic panel against itself and
  returns `None` (one target-wide reference) unless ≥2 groups each carry `min_frames`; single-linkage
  clustering on unit vectors is wrap/pole-safe. **accumulator.py** — `WeightedSum`/`MinMaxReject`/`Welford`
  all keep NaN = "no coverage" (uncovered → NaN, not 0/0), the min/max k-set sums each side's ±inf identities
  *before* combining so an uncovered pixel can't form inf−inf, and `frame_coverage` counts a frame on **any**
  channel so per-channel κ-σ never under-counts. **mosaic.py** — wrap-safe circular-mean centres, MAD outlier
  drop capped at ½ the frames, and both the pixel-dimension and megapixel budgets fail fast. **drizzle_path.py**
  — the reject gate reads the true `frame_coverage`, not the pixfrac-deflated weight, and the float64
  catastrophic-cancellation floor disables clipping where variance is below ULP(m²). **calibrate/apply.py** —
  no-data dark/bias/flat pixels sanitize to the correct "no correction" identity on both the plain and
  exposure-scaling paths; `apply_raw` honours its "returns a fresh array" contract even on the empty-bundle
  path. **qc/grading.py** — per-panel yardstick fallback to target-wide is sound; the reconsider pass is a
  fixed point over the invariant combined set; the per-panel *and* global reject caps are deterministic.
  **io/scanner.py + io/ingest.py** — the v0.277.4 parent-scoped sibling skip holds; the in-place content-swap
  recovery (`_same_capture` requires a *positive* DATE-OBS match, else conservatively "changed") and the
  fingerprint backfill are correct, and `incoming/` stays strictly read-only (copy, never move). **nightplan
  `session_moon`** — midpoint eval, `end<start` swap, and the shared `_moon_geometry` are consistent with the
  forward-looking warning.
  **Live dogfood (the part code review can't do):** built a 20-sub dithered synthetic target (one satellite
  streak, per-frame independent noise) and ran the real `run_stack(auto_reject, quality_weighted,
  photometric_normalize)`. The result was clean and trustworthy — auto-reject resolved to κ-σ and clipped the
  streak (`rejection_fraction≈0.016`), coverage/NaN handled exactly as designed (97.6 % finite; the ragged
  dither-edge corners are NaN, `coverage_min=0` at the extreme corner, `coverage_max=20`), sky-subtracted
  linear output centred near zero (median ≈ 1.4 ADU), no inf/garbage. The stack→result path is doing the right
  thing end to end.

- **⚪ QA AUDIT RESULT (Scout 2026-08-27 #11, branch `claude/vigilant-knuth-bsx6dh`) — led the rotation with the
  stacking engine's combine/reject + calibrate + auto-reject resolution, then swept the guardrail-critical
  routers the #10 note pointed at (gallery, stack, **upload**) and the render/proxy path. Result: the engine,
  calibration, routers and render all came back CLEAN again; no verified bug this run. Environment healthy — a
  219-test targeted subset across the audited areas passed (`test_accumulator`, `test_qc_grading`, `test_scanner`,
  `test_stack_pipeline`, `test_gallery`, `test_autostack_hold`, `test_one_sub_vs_stack`; 141 s), and a full
  headless run was green through 50 % (0 failures) before the container reclaimed the background runner twice —
  a resource/harness limit, not a test failure. What was read adversarially and, where a trigger was
  constructible, traced:**
  **accumulator.py** — the `MinMaxRejectAccumulator` k-set insertion keeps `_mins` ascending / `_maxs` descending
  (traced insertion of 5→3→4 at k=2 stays sorted), so `_mins[0]`/`_maxs[0]` are the true extremes the degrade
  bands rely on; the ±inf identities at uncovered slots are summed *per side before combining* so an uncovered
  pixel can't form an inf−inf NaN; the three-band schedule (`≥2k+1` full k-trim / `3≤cnt<2k+1` single min/max /
  `1–2` plain mean / `0` NaN) and the any-channel `frame_coverage` count (so per-channel κ-σ never under-counts a
  frame) are correct; `WelfordAccumulator.variance` is NaN for n<2 — the keep-single-coverage signal the clip
  widens on. **reference.py** — candidate RAs are unwrapped *before* the median/distance/span, so an RA=0
  straddler isn't flung ~180° and passed over for an edge frame; a no-wrap target is untouched. **stacker.py** —
  `_resolve_auto_reject` explicitly forces min/max below 4 frames so the reachable small-κ case
  (`sigma_kappa≲1.155` → `kappa_min_frames`=3) can't pick κ-σ and then silently fall through its `n≥4` gate to
  *no* rejection despite `auto_reject`; `_afford_drizzle_reject` forgives only the reject *pass* on the walk-away
  path (never the canvas — a canvas that doesn't fit is still refused with a named fix) and passes an explicit
  user tick straight through to refuse loudly. **calibrate/apply.py** — `_effective_dark` restores the plain dark
  at genuinely-no-data *bias* pixels and 0 at no-data *dark* pixels, so exposure-scaling can never inject a
  spurious `bias·(1−ratio)` pedestal into every calibrated light; `_bias_applies` / `_dark_scaling_applies` gate
  consistently across `validate`, `calibration_warnings` and `dark_scaling_provenance` (a wrong-shaped bias
  silences neither the warning nor scaling incorrectly); `apply_raw` honours the "returns a fresh array" contract
  even on the empty-bundle path so a caller can't mutate the shared source frame. **qc/metrics.py** —
  `green_channel` promotes to float32 *before* averaging the two green Bayer pixels, so summing two bright 16-bit
  greens can't wrap mod-2¹⁶ and corrupt exactly the stars QC needs; all four Bayer layouts map G correctly.
  **qc/grading.py** — the per-panel reject rail plus the deterministic `(-worst_z, frame_id)` total order make the
  `reconsider` pass a genuine fixed point (no reject↔re-accept churn at the cap boundary); `re_accept` reads the
  *post-cap* list on purpose. **solve/astap.py** — the 3-rung ladder falls through on a per-rung timeout (each rung
  gets the full `timeout_s`, the documented ≤3× cost the #4 note already tracks) and surfaces the tally-able
  `SOLVE_FAILED_TIMEOUT` only when *every* rung timed out; `_parse_astap_ini`'s hard `CRVAL*`/`CDELT2` key access
  sits inside the solved-only guard and its `KeyError` is caught → `solved=True` with null coords, handled
  downstream. **render/thumbnail.py + edit/proxy.py** — preview↔export both route through the STF /
  `_autostretch_for_export`; a display-space editor export is rendered verbatim (a second asinh would
  double-process it); `_nan_aware_area_downscale_plane` keeps a fully-uncovered block as NaN and reads each
  big-endian plane one at a time to stay RAM-bounded on a giant mosaic; the proxy cache is keyed on
  `src_mtime`+`PROXY_VERSION` and returns a writable copy off the memmap. **routers/upload.py** (guardrail-
  critical, §10) — traversal is refused twice (`safe_relpath` per-segment + `confined_dest` symlink-escape
  re-confirm), an *absolute* zip member is refused rather than silently de-slashed, the per-member write is capped
  at the archive's declared `file_size` (which is what makes the pre-write free-space guard *binding* against a
  zip bomb), `zipfile` CRC-verifies each member at EOF, every stream lands as a unique `.part` (concurrent
  same-name POSTs can't interleave) atomically renamed only when complete, and a final-flush ENOSPC still unlinks
  the temp — `incoming/` stays strictly create-new/read. **routers/gallery.py + stack.py** — every cross-target
  read degrades per-item (one corrupt project / bad run / unusable video meta costs one card, never the page); the
  noise-ratio measure slices the memmap window before the float cast (46 MB→0 MB peak); `full-res-png` renders the
  *saved recipe* for a display-space run so the download matches the clicked preview. **pipeline walk-away** —
  `_auto_stack_frame_count` compares against the *max* prior coverage and retries a marked attempt only when
  *fewer* subs are unreadable than last time; `_auto_stack_readability_hold` holds without stamping the marker;
  `_solved_accepted_count` and `_solved_accepted_unreadable` share the identical solved+accepted filter, so
  `readable = offered − unreadable` is exact. **This audit's conclusion:** the stacking engine, calibration,
  routers (upload included) and render are all hardened; the marginal QA value has moved off them — future runs
  should lead with the **editor-reload ↔ proxy-render interaction** and a **running-app dogfood** of the Target /
  Stack information architecture (the standing §1 friendliness priority), and re-audit the engine only occasionally.

- **⚪ QA AUDIT RESULT (Scout 2026-08-27 #10, branch `claude/vigilant-knuth-nozq4i`) — led the rotation back
  onto the stacking engine's per-frame geometry + the walk-away auto-orchestration layer the #8/#9 notes
  pointed at, since the combine/reject core has now come back clean three audits running. Result: the engine
  and the auto-stack helpers both came back CLEAN again; no verified bug this run. Baseline green before
  touching anything (full headless suite). What was read adversarially and, where a trigger was
  constructible, traced:**
  **align.py** — `reproject_rgb_windowed`'s inset/valid mask keeps the GPU `cval=0.0` blend strictly inside
  the trusted interior (valid requires `src ∈ [inset, N-1-inset]`, inset ≥3 for real frames, and the GPU
  path only runs ≥1.5 MP so tiny inset-0 synthetic frames never reach it); the sub-pixel refine propagates
  the NaN coverage ring with the *same* order-1 footprint (`cval=1.0`) so a darkened boundary pixel can't
  survive as covered-but-dimmed; the `SUBPIXEL_SHIFT_CAP_PX` window-pad guard stops a near-cap shift clipping
  real footprint-edge coverage. **mosaic.py** — the primary + iterative outlier passes both use the wrap-safe
  circular-mean centre RA (`_circ_mean_ra_deg`), never a plain corner-RA median, so a frame straddling RA=0
  can't be flung to ~180° and dropped as an outlier; the `max_excluded`/`n//2` caps keep a genuinely wide
  mosaic intact; both the px-dimension and the megapixel budget fail fast with actionable errors. **pointings.py**
  — the union-find single-linkage clusterer (path-halving `find`) is deterministic first-appearance labelled,
  unit-vector wrap/pole safe; `pointing_groups` returns `None` (→ target-wide, today's behaviour) unless ≥2
  substantial panels split, so a single field / unsolved / tightly-packed mosaic is byte-for-byte unchanged.
  **weighting.py** — `_positional_medians` keys the per-panel medians on `f.id` only for id-bearing frames
  (the loop skips `f.id is None` before indexing), falls back to the target-wide median per-metric for a thin
  panel, and `combine_weights_with_photometric` returns the *same* dict object (no `1/s²` fold) when no scale
  is active. **output.py / render/thumbnail.py** — preview↔export both route through `_autostretch_for_export`;
  `already_display` skips the double-stretch on editor exports across FITS/TIFF/PNG; `load_stack_rgb`'s
  memmap-per-channel NaN-aware area downscale keeps the RAM-bounded path and is bit-for-bit the old arithmetic;
  `asinh_stretch`/`autostretch` degenerate-image guards (`hi<=lo`, all-NaN) return black rather than dividing
  by zero; `_archive_existing_outputs` keeps coverage/preview siblings resolvable from one archived basename.
  **drizzle_path.py** — `_clip_tolerance` gates rejection on the true unweighted frame count (`self._count`),
  not the pixfrac-deflated weight, and disables it below the `_VAR_RESOLUTION_FACTOR·m²` cancellation floor
  rather than punching NaN holes through a bright flat region; out-of-bounds pixmap pixels (set to -1) carry
  zero weight and never double-count into the frame-coverage OR. **pipeline auto-orchestration** — the
  frame-count trigger, readability preflight/recovery, calibration-recheck and degraded-heal markers each
  fire once-per-situation, are written *before* the stack (crash-loop-safe) and cleared on a survivable
  failure; `_auto_stack_frame_count` compares against the *max* prior coverage (never a tiny editor-export
  run) and only retries a marked attempt when *fewer* subs are now unreadable. **scanner.py / project.py** —
  re-verified the #8 fix: `_apply_seestar_convention`'s sibling test is parent-scoped, `incoming/` stays
  strictly read-only (every mutation is `shutil.copy2` into the target cache), and
  `reject_seestar_output_frames`'s per-folder ≤2-frame size guard protects a real ≥3-sub bare `<T>/` folder
  (the documented 1–2-sub residual stays non-destructive and recoverable). **This audit's lead-worthy
  conclusion:** the stacking engine and the walk-away orchestration are both hardened; the marginal QA value
  has moved fully off them — future runs should lead with the routers (`stack.py`, `gallery.py`) and the
  editor-reload / proxy render path, and re-audit the engine only occasionally.

- **⚪ QA AUDIT RESULT (Scout 2026-08-27 #9, branch `claude/vigilant-knuth-um7mfa`) — adversarial re-sweep of the
  stacking engine's combine/reject core plus the auto-orchestration helpers the #8 note pointed at next. Result:
  the engine came back CLEAN again; found ONE verified §3 friendliness gap on the Stack form (filed under
  Friendliness, not here — it is not a wrong-result). Baseline green before touching anything (**2935 passed, 2
  skipped** — full headless suite) and the `agent-dogfood.sh` boot+stack+probe pass was clean (no overflow, no
  console errors; the sample stacked to a min/max 6-frame master exactly as `_resolve_auto_reject` predicts for a
  sub-11-frame stack).** What was read adversarially and, where a trigger was constructible, traced:
  **accumulators** (`accumulator.py`) — `WeightedSumAccumulator` any-channel frame count vs Σ-weight coverage
  split is correct; `MinMaxRejectAccumulator`'s k-set insertion sort + the three-band degrade schedule
  (`≥2k+1` / `3≤cnt<2k+1` / `1–2`) subtract each extreme *value* once (tie-safe) and never form an inf−inf NaN
  at an uncovered pixel; `WelfordAccumulator` variance is NaN for n<2 (the keep-single-coverage signal).
  **drizzle** (`drizzle_path.py`) — the `neff`-gated clip tolerance reads the true unweighted frame count (not
  the pixfrac-deflated weight), the `_VAR_RESOLUTION_FACTOR·m²` cancellation floor disables rejection on bright
  flats rather than punching NaN holes, and `result()` returns the library's running weighted mean un-re-divided.
  **κ-σ two-pass** (`stacker.py`) — `_kappa_sigma_keep_mask` widens to keep-all on both "no reference" cases
  (σ-unknown → +inf tol, mean-unknown → keep), pass 1 frees the Welford buffers before pass 2 (the 4-array peak
  the OOM guard charges), and `photometric_scales` is threaded into **both** passes so mean/σ and the clip test
  live in the same scaled domain. **calibrate/apply** — no-data dark/bias pedestals stay "no correction" on both
  the unscaled and exposure-scaled paths; `_bias_applies`/`_dark_scaling_applies` gate shape-mismatched masters
  consistently across `validate`, the warnings, and the provenance stamp. **weighting/photometric** — the
  per-panel-vs-target-wide median split (`group_by_pointing`) and the `1/s²` inverse-variance fold compose
  orthogonally; the geometric-mean weight stays in `[min_weight, 1.0]`. **output.py** — preview↔export both go
  through `_autostretch_for_export`; `already_display` skips the double-stretch on editor exports; the archive
  dance keeps coverage/preview siblings resolvable. **pipeline auto-orchestration** — the frame-count trigger,
  readability preflight/recovery, calibration-recheck and degraded-heal markers each fire once-per-situation and
  clear on a survivable failure (crash-loop-safe); `_stack_target`'s "user chose nothing" guards apply
  `auto_reject`/`quality_weighted`/`drizzle_reject` only when the merged options carry no explicit key.
  **qc** — `grade_frames`'s reconsider set is a fixed point (invariant combined set, deterministic total order,
  per-panel + global caps); `reconcile_streak_rejections`/`apply_qc_result_to_db` only ever *un*-reject an
  `auto:streak`/`qc_error` reason and never touch a `user_override`. **This audit's lead-worthy conclusion:** the
  combine/reject core and the auto-orchestration layer are both hardened; the marginal value has moved off the
  engine — future runs can lead with the render/proxy/editor-reload path and the routers (`stack.py`,
  `gallery.py`), and re-audit the engine only occasionally.

- **⚪ QA AUDIT RESULT (Scout 2026-08-27 #8, branch `claude/vigilant-knuth-gnif14`) — rotated the lead QA onto
  the still-un-swept-in-depth storage/config layer the #5–#7 notes flagged: the watcher-ingest-scanner path,
  `webapp/config.py` load/save + `deps.py`, and both DB migration paths (`project.py`, `library.py`).
  Result: found + FIXED one real WRONG-RESULT data-loss bug in the Seestar scanner (cross-parent `_sub` sibling
  collision → v0.277.4, see Shipped at top of Bugs), plus two verified LOW-severity robustness gaps filed
  below. The DB migrations, the config load path, and the render/preview path came back clean. Dogfood
  end-to-end clean.** Baseline green before touching anything (**2900 passed, 2 skipped** — full headless
  suite). What was traced (and, where a trigger was constructible, reproduced):
  **scanner/ingest** — `incoming/` is strictly read-only (every mutation is `shutil.copy2` into the target
  cache; no `unlink`/`rename`/`move`/truncate in `ingest.py`/`scanner.py`/`merge.py`/`watcher.py`); filename
  traversal neutralised (`CacheManager.stage1_path_for` names files `frame_{id:06d}` and keeps only the
  suffix); `_dedup_key` (realpath) symmetric so a re-scan can't double-add; `_same_capture` / `content_changed`
  in-place-swap recovery (force re-copy, reset QC, clear stale WCS) correct. The one real bug was the folder-
  *convention* sibling test being global rather than same-parent (fixed).
  **config/deps** — the bounds added in `ee81acf` (`watch_*`, `astap_timeout_s`, `cpu_workers`, `seestar_*`)
  are isolated by `_load_resilient`, which resets ONLY the out-of-bounds fields (verified: a legacy
  `seestar_poll_interval_s=0` config keeps `auth_*`, `auto_stack`, `site_lat`, …); no field's own default is
  self-rejecting; `open_target_project` resolves the client `safe` via a parameterised registry lookup +
  DB-stored `safe_name`, so no raw client path reaches the filesystem.
  **DB migrations** — drove a real oldest-layout (v1) in-memory `Project` through `_migrate_schema`: migrates
  v1→current, the pre-existing frame row survives, every expected column is present, and a second run is
  idempotent; every step is `ALTER TABLE ADD COLUMN` / `CREATE … IF NOT EXISTS` guarded by
  `try/except OperationalError`, zero backfill `UPDATE`s (no ordering hazard), no `DROP`/`DELETE`/rewrite;
  `library.py` additive columns all nullable and read-guarded with `in row.keys()`.
  **render/preview** — every stretch/normalisation anchor is NaN-aware (`np.nanmin`/`nanpercentile`/`nanmax`;
  autostretch writes only finite positions so gaps stay black); preview↔export use the same
  `_autostretch_for_export`; `rotate_image_north_up`'s `np.rot90` snap matches `PIL.rotate(expand=True)`
  (verified empirically); constant/flat/single-pixel images degrade to black rather than divide-by-zero.
  **This audit's lead-worthy conclusion:** the storage layer had the one remaining reachable data-loss bug;
  with it fixed, future runs can lead with `jobs.py` / `webapp/pipeline.py`'s remaining auto-orchestration
  helpers, and re-audit the engine + routers only occasionally.

- **⚪ QA AUDIT RESULT (Scout 2026-08-27 #7, branch `claude/vigilant-knuth-yeeeim`) — re-audited the stacking
  engine's weighting/photometric/pointing math + the un-swept-in-depth routers the #6 audit flagged
  (`gallery.py`, `plan.py`, `stats.py`, `targets.py`, `video.py`) + `calibrate/masters.py`, adversarially.
  Result: engine core still CLEAN; one real on-path memory gap found and FIXED (masters 3-copy peak → v0.277.3,
  see Shipped); two low-severity latent robustness gaps filed below. Dogfood end-to-end clean.** Baseline green
  before touching anything (**2898 passed, 2 skipped** — full headless suite). Traced by hand and, where cheap,
  probed: `weighting.py` (geometric-mean of five clipped sub-weights, per-panel positional medians with
  target-wide fallback, the `1/s²` photometric variance fold), `photometric.py` (per-panel references, neutral
  fallback when <3 measured, `[1/max_ratio, max_ratio]` clamp), `pointings.py` (union-find single-linkage,
  wrap/pole-safe unit vectors, the ≥2-substantial-groups soundness gate), `reference.py` (RA-unwrap median,
  FWHM tiebreak), `align.py` (windowed-reproject inset valid-mask, order-1 sub-pixel-shift NaN-ring propagation
  with the `cval=1.0` mask, GPU/CPU `cval` parity), and `stacker.py`'s `kappa_min_frames` / `_resolve_auto_reject`
  (n<4 → min/max so `auto_reject` intent is always met) / `_kappa_sigma_keep_mask` (both σ-unknown and
  mean-unknown widenings) / `_afford_drizzle_reject` (walk-away forgiveness of the extra planes) — every
  NaN/coverage/rejection edge I could build was already handled and commented. The routers were swept via three
  focused sub-audits: `gallery.py`/`plan.py`/`stats.py` (path resolution, offset/limit clamps, empty-population
  medians, divide-by-zero, timezone/moon math, missing-column upgrade guards — all correct); `targets.py`/
  `video.py` (client `capture_id`/`safe` sanitised server-side, `incoming/` strictly read-only, ffmpeg decode
  guards, Pydantic-bounded numeric params, additive-column reads); `masters.py` (NaN/inf combine, `mad==0` tol=0
  rejection, uint16→float32 no-overflow, empty/n=1/all-identical, `incoming/` read-only — all sound). **This is
  the seventh consecutive essentially-clean engine-side audit.** Future runs can lead with the watcher-ingest
  storage layer / `deps.py` / `config.py` load path, or re-audit the engine only occasionally.

- **⚪ QA AUDIT RESULT (Scout 2026-08-26 #5, branch `claude/vigilant-knuth-t39r9x`) — led the rotation back
  through the stacking engine's remaining un-swept surface (the accumulators, mosaic-canvas sizing, the
  drizzle path, the video/lucky-imaging stack) and the calibration apply path, all adversarially; came back
  CLEAN — no new verified bug. Also re-ran the running-app dogfood end to end (clean).** Baseline green before
  touching anything (**2872 passed, 2 skipped** — full headless suite). Read adversarially and, where cheap,
  traced breaking cases against the real code:
  `seestack/stack/accumulator.py` — `WeightedSumAccumulator`'s Σweights-vs-frame-count split (`coverage` vs
  `frame_coverage`, the any-channel `valid.any(axis=2)` count that stops per-channel κ-σ from under-counting a
  frame), the `_mask_bool` `(H,W)`→`(H,W,1)` broadcast, `MinMaxRejectAccumulator`'s ±inf k-set identities +
  the ≥2k+1 / 3..2k / 1..2 degrade bands + its structural `rejection_counts`, and `WelfordAccumulator`'s
  `n_safe` divide-guard and unbiased-variance-NaN-for-n<2 contract — all correct.
  `seestack/stack/mosaic.py` — the wrap-safe `_circ_mean_ra_deg`/`unwrap_ra_deg` per-frame centres, the
  robust median+MAD outlier pass with its "never drop >½ the frames" rail, the iterative dimension-cap drop
  loop and the megapixel budget, the half-open CRPIX shift — every RA=0-straddle and bad-solve edge I could
  build was already handled.
  `seestack/stack/drizzle_path.py` — the float64 `E[x²]−E[x]²` variance with its ULP(m²) resolution floor,
  the `neff`=true-frame-count gate (so pixfrac<1/scale>1 weight deflation can't silently disable rejection on
  a low-coverage edge), the Bessel correction applied only to the tol (not the floor test), the `[-0.5,N-0.5]`
  half-open pixel bounds, the any-channel `deposited` frame count, and `intersects` vs deposited-footprint —
  all correct and commented.
  `seestack/video/lucky.py` — the two-pass streaming grade→keep→align→average (flat memory bound), the
  argsort-stable tie-to-earlier keeper that makes "the sharpest frame is always a keeper and is the align
  reference" true by construction, the `_MAX_SHIFT_FRACTION` reject, `cval=np.nan` vacated-edge honesty, and
  the disk-appropriate linear `normalize_for_display` (percentile anchors, not an STF) — correct.
  `seestack/calibrate/apply.py` — the pedestal `nan_to_num` sanitisation with its no-data masks, the flat's
  NaN-not-0 sentinel + `_FLAT_FLOOR`, the `_bias_applies` "never double-subtract the bias through a dark"
  rule, `_effective_dark`'s exposure-scaling with both no-data-mask restorations, and the fresh-array
  contract; **confirmed both `apply_raw` call sites (`align.py:137`, `stacker.py:2183`) pass
  `light_exposure_s=info.exposure_s`, so dark exposure-scaling is never silently skipped for want of the
  exposure.** The one still-open unguarded gap here is the already-filed Bayer-pattern note below (a flat with
  a matching shape but a different CFA phase isn't refused) — trigger requires mixed-source masters, doesn't
  fire on normal Seestar input.
  The dogfood pass (`scripts/agent-dogfood.sh`: real app, bundled M42 sample stacked + auto-processed,
  Playwright 1440 px + 420 px across Target / Stack / Editor / Sky-so-far) reported **nothing overflowing, no
  console errors**; the sample stacks and auto-edits cleanly. **Also confirmed by grep that the walk-away
  `auto` chain already auto-enables `auto_reject`, `quality_weighted`, `photometric_normalize` (mosaic) and
  `drizzle_reject` (`webapp/pipeline.py` ~2417–2462) — so no "single-pass drizzle silently keeps trails"
  autonomy gap exists.** **This is the fifth consecutive clean engine-side audit** — the engine and its
  neighbours are drained. Front of the *actionable* bug queue is unchanged: the ASTAP per-frame timeout-budget
  behavioural half (item (b) at the top of this section), then the two trigger-gated hardening notes (watcher
  in-place re-arm; flat Bayer-pattern guard). Future Scout runs can lead with the still-un-swept-in-depth
  routers (`stack.py`, `editor.py`) / storage and re-audit the engine only occasionally.

- **⚪ QA AUDIT RESULT (Scout 2026-08-26 #6, branch `claude/vigilant-knuth-izen6g`) — took the lead onto the two
  still-un-swept-in-depth routers the prior audits flagged (`stack.py` 2054 lines, `editor.py` 1579 lines),
  swept both adversarially end-to-end (each via a focused sub-audit that traced into the helpers), plus the
  storage / calibration routers by hand and re-ran the running-app dogfood. Result: essentially clean — the one
  latent-robustness gap above (now fixed) was the only actionable finding; no wrong-result or data-integrity
  bug.** Baseline green before touching anything (full headless suite). What was traced:
  `webapp/routers/stack.py` — `_clamp` bounds order at every call site (stretch/black 0..1, crop size 128..4096);
  the noise-crop `_crop_origin`/`_measure_noise_ratio` axis alignment (no transposed crop); the
  trigger→`submit_stack`→`_stack_target` option build (client `dark_path`/etc. popped before use, only master
  *ids* resolved server-side, `validate_stack_options` before submit, `coerce_stack_options` drops `None`/unknown
  so a cleared numeric field can't reach the dataclass); the download/`FileResponse` endpoints (paths from the DB
  row not the URL — no traversal via `kind`/`safe`; literal routes declared before the `/{kind}` catch-all;
  missing→404, corrupt FITS→422); resource cleanup (`proj`+`lib` closed in `finally` on every early-raise path);
  and the single-serial-worker JobManager making a double stack-trigger sequential, not concurrent.
  `webapp/routers/editor.py` — preview↔export parity (both build `EditContext` from the same inputs and run the
  identical op loop; the `already_display` suppression reads different *sources* — `run.options_json` vs the FITS
  `SSDISPLY` card — but both are written together by `_apply_editor_to_run`, and only the fallback autostretch
  reads it, mirrored on both paths; the only genuine preview≠export divergences — `gaia` colour-cal / deconv /
  star-reduce on the proxy — are intrinsic, deliberate, and disclosed to the user in op help + histogram flags);
  recipe coercion (`recipe_from_dict` drops unknown ops, coerces non-mapping params to `{}`, clamps every param —
  malformed input degrades to `Recipe()`); the cache is only the raw *linear* proxy keyed on `run_id`+mtime+version
  (no recipe-hash image cache to go stale; previews `no-store`); export `output_name` sanitised in
  `write_stack_outputs` (no traversal); overwrite archives-and-repoints rather than destroying data. Two truly
  unreachable latent nits noted and deliberately **not** filed (they need a hand-corrupted non-dict `options_json`
  or a non-list presets row, neither of which the app ever writes): `_run_display_space` and `delete_preset`'s
  missing `isinstance` guards. **The routers are now swept in depth and clean.** Front of the *actionable* bug
  queue is unchanged: the ASTAP per-frame timeout-budget behavioural half (item (b) at the top), then the two
  trigger-gated hardening notes (watcher in-place re-arm; flat Bayer-pattern guard). Future runs can lead with
  the remaining routers (`gallery.py`, `plan.py`, `stats.py`, `targets.py`, `video.py`) / the watcher-ingest
  storage layer, and re-audit the engine + editor only occasionally.

- **⚪ QA AUDIT RESULT (Scout 2026-08-26 #4, branch `claude/vigilant-knuth-243xct`) — rotated the lead QA off the
  (drained) stacking engine per the prior audits' advice and swept the webapp routers + plate-solve + watcher/
  ingest/QC + the post-processing colour chain; the engine's neighbours hold up, with the two low-severity traced
  findings above the only new open items. Also dogfooded the running app end to end (clean).** Baseline green
  before touching anything (**2790 passed, 2 skipped**). Read adversarially and, where cheap, probed the real code:
  `seestack/post/color_cal.py` (gray-star / Gaia / background-neutral solvers — every scale clamped to
  `[0.05, 20]`, G locked to 1.0, NaN-aware `_apply_scale`, the per-detection `idx`/`matched` index alignment in
  `_solve_gaia` that a length-mismatch would otherwise silently break, the `MAX_CALIBRATION_STARS` cap that stops a
  bad mosaic sky estimate from spawning hundreds of thousands of spurious detections — all correct); the
  `webapp/routers/frames.py` list/preview/reject-summary endpoints (whitelisted `_SORTABLE`, clamped
  `offset`/`limit`, nulls-last sort in *both* directions, server-side path resolution + bayer/int validation on the
  preview so no filename separator or traversal reaches the cache path, `OperationalError`→503 read-only mapping);
  and the plate-solve + watcher/ingest/QC paths via focused sub-audits (the `_store_solve_failed_reason`
  preserve-guard that stops a re-QC-forever loop; the ladder's per-rung timeout fall-through vs fatal-error break;
  `-ra`=deg/15, `-spd`=dec+90 pole-safety; `incoming/` strictly copy-only — `shutil.copy2` the only mutation, no
  `unlink`/`rename`/`move`/truncate anywhere in ingest/watcher, filename traversal neutralised by
  `stage1_path_for` building the stem from `frame_id`; QC modified-z direction, the `min_frames` gate closing the
  empty-population/`_median([])` paths, the 25% rail only ever *reducing* rejections, per-panel fallback to
  target-wide stats). The dogfood pass (`scripts/agent-dogfood.sh`: real app, bundled M42 sample stacked, Playwright
  1440 px + 420 px across the Target / Stack / Editor / History / Library / planner routes) reported **nothing
  overflowing, no console errors**, and by eye the whole journey is polished and beginner-friendly — the Target
  page's IA (prioritised notes + "1 more note" disclosure, picture + actions + frames table above the fold, "Is it
  enough yet?" goal card), the well-defaulted Stack form, and the auto-processed Editor with its plain-language
  pipeline all read cleanly. **Backlog note:** the two items AGENTS.md §1's "2026-08-17 critical bug" paragraph and
  the #2/#3 audit notes call "the front of the bug queue" — the mosaic `photometric_normalize` auto-enable and the
  mosaic per-panel auto-grade — have **both since shipped** (v0.271.0 and v0.270.2), and the `_framecov.fits` prereq
  with them (v0.270.4); so the actionable bug queue is now the two traced findings above plus the older
  trigger-gated hardening notes (flat Bayer-pattern guard; non-windowed `reproject_rgb` inset), none of which fire
  on the normal path. Future Scout runs can keep the lead on the routers (`stack.py`, `editor.py` are still
  un-swept in depth) / video / storage and re-audit the engine only occasionally.

- **⚪ QA AUDIT RESULT (Scout 2026-08-26 #3, branch `claude/vigilant-knuth-r0qxeh`) — re-audited the stacking
  engine + plate-solve + render adversarially (came back CLEAN), and dogfooded the running app end to end,
  where I found and FIXED one real friendliness bug (the mislabelled Lucky-imaging knob — see Shipped).**
  Baseline green before touching anything (2789 passed, 2 skipped). Adversarially re-traced the engine hot path
  and its neighbours, building breaking cases where I could: `accumulator.py` (WeightedSum any-channel
  frame-count vs Σ-weight `coverage`, MinMaxReject k-set tie-safety + the ≥2k+1 / 3..2k / 1..2 degrade bands,
  Welford unbiased-variance NaN-for-n<2), `drizzle_path.py` (the `neff`=true-frame-count gate that stops
  `pixfrac<1`/`scale>1` weight deflation from silently disabling rejection on low-coverage edges; the float64
  `E[x²]−E[x]²` variance with its ULP(m²) resolution floor; half-open `[-0.5, N-0.5]` pixel bounds;
  `intersects` vs deposited-footprint counting), `solve/runner.py` + `solve/astap.py` (the `_store_solve_failed_reason`
  preserve-guard that keeps a `qc_error`/`auto:grade:` prior reason from being clobbered into `solve_failed:`
  and re-QC'd forever; WCS-centre recovery when the `.ini` is unparseable; the adaptive ladder's per-rung
  timeout fall-through vs fatal-error break; `_parse_astap_ini` KeyError → caught → None), `qc/grading.py`
  (modified-z direction-awareness, the practical-significance floors, the per-panel `_pointing_groups` split +
  its per-panel cap, and the `reconsider` fixed-point over the invariant combined set), `stack/pointings.py`
  (union-find single-linkage, `-1` for unsolved, wrap/pole-safety), and `render/deepening.py` (one shared STF
  solved from the deepest *linear* master, `_fit_onto` letterboxing so a portrait night-1 and a landscape
  mosaic night-5 don't squash). Every NaN/coverage edge, rejection band, memory bound and preview↔export path I
  could construct a breaking case for was already handled and commented. **This confirms the engine remains
  drained** (matching the two prior 2026-08-26 audits). The dogfood pass (`scripts/agent-dogfood.sh`: real app,
  bundled sample stacked, Playwright 1440px + 420px) showed a clean Target-page IA (3 notes + a "1 more note"
  disclosure, picture + actions + frames table above the fold), a clean beginner-friendly Stack form, and an
  excellent well-hardened editor — no overflow, no console errors. The one real snag was the Lucky-imaging
  label (below). Front-of-queue for the Builder is unchanged: the two `photometric_normalize`/mosaic
  auto-grade items AGENTS.md §1 points at. Future Scout runs can lead with the webapp routers (`stack.py`,
  `editor.py`, `frames.py`) or ingest/watcher and re-audit the engine only occasionally.

- **⚪ QA AUDIT RESULT (Scout 2026-08-26 #2, branch `claude/vigilant-knuth-xh4b6y`) — rotated the lead QA off
  the (already-drained) stacking engine and adversarially re-audited the subsystems the engine feeds and is
  fed by: QC (`qc/grading.py`, `metrics.py`, `streaks.py`, `noise_ratio.py`), ingest (`io/ingest.py`),
  the folder watcher (`webapp/watcher.py`), the render/output path (`render/orient.py`, `render/deepening.py`,
  `stack/output.py`) and the final-gradient/coverage-leveling bg passes (`bg/final_gradient.py`,
  `bg/coverage_leveling.py`). Came back CLEAN — no new verified bug.** Traced adversarially and, where cheap,
  *probed* the real code: `final_gradient.remove_final_gradient` on an all-NaN canvas (both modes → input
  returned, no crash), a 12×12 image (box clamp degrades, finite out), and `green_channel` on odd dims / a 1×1
  frame (empty array, no uint16 overflow — the float32-before-add cast holds). Re-verified the recently-shipped
  v0.270.4 `{base}_framecov.fits` path end to end: `output._same_map` writes the sibling *only* when Σ-weights ≠
  frame count, `proxy.load_frame_coverage` returns `None` when it's absent, and `coverage_leveling._level_context`
  falls back to the weighted map on `None` — so an unweighted run is byte-for-byte unchanged and a weighted one
  bins panels by the honest count. The per-panel auto-grade split (v0.270.2), the QC `cluster_pointings` None/
  unsolved handling, the ingest fingerprint/`_same_capture` benign-touch-vs-swap logic, the watcher
  stranded-batch re-arm, and the north-up rotation math all held under the edges I could construct. **Also
  confirmed the front-of-queue `photometric_normalize` Builder item's traced site is exact:** `is_mosaic_canvas`
  is set at `stacker.py:1259` and `compute_photometric_scales` is gated at `stacker.py:1321` — the one-line
  mirror `if options.photometric_normalize or is_mosaic_canvas:` lands *after* the canvas is known, and the
  1341–1344 comment already documents the coverage-map shift that v0.270.4 addresses. So both front-of-queue
  Builder items below are accurately shaped. **This confirms the drained state now extends past the engine into
  its neighbours;** future Scout runs can lead with the webapp routers / plate-solve (`solve/`) or re-audit the
  engine only occasionally.

- **⚪ QA AUDIT RESULT (Scout 2026-08-26, branch `claude/vigilant-knuth-7slpid`) — the stacking engine was
  deeply re-audited this run and came back CLEAN: no new verified bug found.** Adversarially traced the whole
  `seestack/stack/*` + `seestack/calibrate/*` hot path, trying to break each edge: `accumulator.py`
  (WeightedSum divide-by-weight NaN semantics, MinMaxReject k-set insertion + the ≥2k+1 / 3..2k / 1..2 degrade
  bands + tie-safety, Welford unbiased-variance NaN-for-n<2 contract), `align.py` (windowed reproject
  `FRAME_EDGE_INSET_PX` valid-mask inset, order-1 sub-pixel-shift NaN-ring propagation with `cval=1.0` mask,
  GPU/CPU `cval` parity), `stacker.py` (κ-σ two-pass keep-mask's σ-unknown/mean-unknown widenings,
  `_resolve_auto_reject` n<4 dispatch — the v0.270.3 fix holds, per-pass in-place photometric-scale multiply,
  `frame_cov` persistence + pass-2 empty-guard), `drizzle_path.py` (neff-gated clip tolerance, float64
  variance-resolution floor, unweighted frame-count coverage, half-open pixel bounds), `mosaic.py` (wrap-safe
  circular-mean outlier rejection, px/megapixel canvas caps), `photometric.py` / `weighting.py` (neutral
  fallbacks everywhere, inverse-variance 1/s² folding), `coverage_leveling.py` (per-level detrend → object
  mask → rescue → gapped-fit-clamp → interpolated fill) and `calibrate/apply.py` (pedestal `nan_to_num`
  sanitisation, exposure-scaling no-data-mask restores, fresh-array contract). Every NaN/coverage edge,
  rejection-math band, memory-bound and preview↔export parity path I could construct a breaking case for was
  already handled and commented. **This mirrors the editor's drained state: the stacking engine is now
  well-hardened.** Future Scout runs can rotate the lead QA subsystem to the webapp routers / watcher /
  ingest-QC / plate-solve / render and re-audit the engine only occasionally. The two trigger-gated hardening
  notes just below (flat Bayer-pattern guard; non-windowed `reproject_rgb` inset) stay open — neither fires on
  the normal Seestar path — plus the still-open mosaic auto-grade / `photometric_normalize` items AGENTS.md §1
  points at.

---

## 2026-09-06 — Builder run (branch `claude/sweet-babbage-v7xsyy`): the bug list is gated, so audit the *newest* code

**Backlog state at the start of the run.** "Bugs (fix these first)" holds nothing
startable: every open entry is either a recorded stand-down that carries its own
measurement (the ASTAP ladder budget, the `_scaled_box` mesh floor), gated on data no
agent has (the sky-atlas `_tan_wcs` rotation sign needs a real solved frame with field
rotation), or a "fix only if touching this file" cosmetic. The Scout's two items filed
this morning had both already shipped by the time this run started (`off_night` as
v0.368.0, the mixed-folder master note as v0.369.1).

**So the productive move was auditing the code that had just landed and that nobody had
read.** The ~20 recorded clean sweeps all reached ~v0.353–v0.366; v0.367–v0.369 was
unreviewed. Two verified bugs came out of it, both shipped this run:

* **v0.369.3** — `edit/auto_prefs.record_feedback`: a fresh `by_type` override started at
  neutral, so the first type-scoped tap replaced the global bias instead of moving it one
  step (global `+2` → one "too bright" on a galaxy → `−1`, and `+1` unreachable).
* **v0.369.4** — `calibrate/defects.find_sensor_defects`: no-data samples were filled with
  the *whole plane's* median, so a hole inside amp glow read as a defect and dragged its
  real neighbours in with it (115 flagged pixels on a synthetic-but-believable master).

**The transferable lesson: audit new code, not old code.** Both bugs are in code less than
a day and less than three days old respectively, and both are in files a clean-sweep record
already covers by *area*. Neither would have been found by re-walking `stack/`. **Suggested
default for a Builder that finds the bug list gated: diff `main` for what has landed since
the newest recorded audit and read that, rather than picking a lower-value backlog item.**

**Also: two Ideas entries were struck as already-shipped-under-another-name.** "Reveal"
(Scout 2026-08-27 #15) shipped as **Zoom clip**, v0.303.0 — grepping for *Reveal* finds
nothing, which is why it read as open; the module is `seestack/render/zoomclip.py`. The
Compare-view North-up entry shipped as v0.359.0 (`compareNorthUpOffer`). Both were opened
this run as candidate work and abandoned once the code turned up. That is the third and
fourth instance of the §4 warning; **the name in the backlog entry is not the name in the
code, so grep the *mechanism* (`zoom`, `north_up`), not the feature's title.**

**Ended the run at two tasks rather than manufacturing a third.** The feature backlog is
genuinely dry (the Scout's own 2026-09-06 note says as much), and AGENTS.md §2 is explicit
that a short run leaving `main` green beats a marginal third item.
